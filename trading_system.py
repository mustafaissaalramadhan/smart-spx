"""
SPX Smart - Trading System Core
النظام الرئيسي لإدارة الصفقات والتتبع
"""
import asyncio
import sqlite3
from datetime import datetime
from typing import Dict, Optional
import config
from database import DatabaseManager
from ibkr_client import IBKRClient
from telegram_manager import TelegramManager
import logging

logger = logging.getLogger(__name__)

class TradingSystem:
    def __init__(self):
        self.db = DatabaseManager()
        self.ibkr = IBKRClient()  # Main connection for balance/trades
        self.ibkr_connections = {}  # Separate connections per symbol for watchlist
        self.telegram = TelegramManager()
        self.running = False
        self.active_trades = {}
        self.tracking_tasks = {}
        self.watchlist_task = None
        self.balance_task = None
        self.current_balance = 0.0
        # Symbol to Client ID mapping (ranges)
        self.symbol_client_ranges = {
            'SPX': 100,  # Client IDs 100-149
            'NDX': 200,  # Client IDs 200-249
            'SPY': 300,  # Client IDs 300-349
            'QQQ': 400   # Client IDs 400-449
        }
        # Signal processing lock to prevent race conditions
        self._signal_lock = asyncio.Lock()
        self._signal_queue_count = 0  # Track signals in queue
        self.gui_instance = None  # Reference to GUI for fast watchlist access
        
    async def start(self):
        """Start the trading system"""
        try:
            logger.info("🚀 Starting SPX Smart Trading System...")
            
            # Connect main IBKR (for balance and trades)
            await self.ibkr.connect()
            
            if not self.ibkr.connected:
                logger.error("Failed to connect to IBKR")
                return False
            
            logger.info("✅ Main IBKR connection established")
            
            # Create dedicated connections only for default watchlist symbols (SPX, SPY)
            default_symbols = getattr(config, 'DEFAULT_WATCHLIST_SYMBOLS', config.SUPPORTED_SYMBOLS)
            logger.info(f"Creating dedicated connections for default watchlist symbols: {default_symbols}")
            for symbol in default_symbols:
                await self.get_or_create_ibkr_connection(symbol)
            
            self.running = True
            
            # Start background tasks
            self.balance_task = asyncio.create_task(self._update_balance_loop())
            
            logger.info("✅ Trading System Started with multiple IBKR connections")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error starting system: {e}")
            return False
    
    async def get_or_create_ibkr_connection(self, symbol: str):
        """Get or create dedicated IBKR connection for a symbol"""
        if symbol not in self.ibkr_connections:
            base_client_id = self.symbol_client_ranges.get(symbol, 500)
            conn = IBKRClient(base_client_id=base_client_id)
            success = await conn.connect()
            if success:
                self.ibkr_connections[symbol] = conn
                logger.info(f"✅ Created dedicated connection for {symbol} (Client ID: {conn.current_client_id})")
            else:
                logger.error(f"❌ Failed to create connection for {symbol}")
                return None
        return self.ibkr_connections[symbol]
    
    async def stop(self):
        """Stop the trading system"""
        logger.info("⏸️ Stopping trading system...")
        
        self.running = False
        
        # Cancel all tracking tasks
        for task in self.tracking_tasks.values():
            task.cancel()
        
        if self.watchlist_task:
            self.watchlist_task.cancel()
        
        if self.balance_task:
            self.balance_task.cancel()
        
        # Disconnect all IBKR connections
        self.ibkr.disconnect()
        for conn in self.ibkr_connections.values():
            conn.disconnect()
        
        logger.info("✅ Trading System Stopped")
    
    async def start_tracking_manual_trade(self, trade_id: int, symbol: str, strike: float, 
                                         option_type: str, entry_price: float, expiry_date: str = None,
                                         qualified_contract = None):
        """Start tracking a manual trade (called from GUI)
        
        Args:
            qualified_contract: Pre-qualified contract from watchlist (preferred - works 24/7)
                              If None, will try to qualify a new contract (may fail after market hours)
        """
        try:
            from ib_insync import Option
            
            logger.info(f"📊 Starting tracking for manual trade #{trade_id}: {option_type} {symbol} Strike {strike}")
            print(f"\n📊 Starting tracking for manual trade #{trade_id}")
            print(f"   Symbol: {symbol}")
            print(f"   Type: {option_type}")
            print(f"   Strike: {strike}")
            print(f"   Entry: ${entry_price:.2f}")
            
            # Get or create dedicated IBKR connection for this symbol
            ibkr_conn = self.ibkr_connections.get(symbol)
            if not ibkr_conn:
                logger.warning(f"⚠️ No existing IBKR connection for {symbol} - creating new connection...")
                print(f"⚠️ No existing connection for {symbol} - creating new...")
                
                # Create connection on-demand
                ibkr_conn = await self.get_or_create_ibkr_connection(symbol)
                
                if not ibkr_conn:
                    logger.error(f"❌ Failed to create IBKR connection for {symbol}")
                    print(f"❌ ERROR: Failed to create IBKR connection for {symbol}")
                    return False
                
                logger.info(f"✅ Created new IBKR connection for {symbol}")
                print(f"✅ New connection created successfully")
            
            logger.info(f"✅ IBKR connection ready for {symbol}")
            print(f"✅ Connection ready")
            
            # Use pre-qualified contract from watchlist if available (preferred - works 24/7)
            if qualified_contract:
                contract = qualified_contract
                logger.info(f"✅ Using pre-qualified contract from watchlist: {contract}")
                print(f"✅ Using cached watchlist contract (works 24/7)")
            else:
                # Fallback: Create and qualify new contract (may fail after market hours)
                logger.warning(f"⚠️ No pre-qualified contract - will try to qualify new contract")
                print(f"⚠️ No cached contract - attempting qualification (may fail after hours)")
                
                # Get expiry date (use 0DTE if not provided)
                if not expiry_date:
                    expiry_date = datetime.now().strftime('%Y%m%d')
                
                # Create contract
                right = 'C' if option_type == 'CALL' else 'P'
                
                # Set exchange and trading class based on symbol
                if symbol == 'SPX':
                    exchange = 'CBOE'
                    trading_class = 'SPXW'
                elif symbol == 'NDX':
                    exchange = 'CBOE'
                    trading_class = 'NDXP'
                else:
                    exchange = 'SMART'
                    trading_class = symbol
                
                contract = Option(symbol, expiry_date, strike, right, exchange, tradingClass=trading_class)
                
                # Qualify contract
                qualified = await ibkr_conn.ib.qualifyContractsAsync(contract)
                if not qualified:
                    logger.error(f"❌ Failed to qualify contract: {symbol} {strike} {option_type}")
                    print(f"❌ ERROR: Failed to qualify contract - is market closed?")
                    return False
                
                contract = qualified[0]
                logger.info(f"✅ Contract qualified: {contract}")
            
            # Extract expiry from contract for notifications
            try:
                contract_expiry = contract.lastTradeDateOrContractMonth
                # Format expiry (from YYYYMMDD to DD MMM YY)
                from datetime import datetime as dt
                expiry_dt = dt.strptime(contract_expiry, '%Y%m%d')
                expiry_formatted = expiry_dt.strftime('%d%b%y').upper()
            except:
                expiry_formatted = datetime.now().strftime('%d%b%y').upper()
            
            # Add to active trades
            self.active_trades[trade_id] = {
                'contract': contract,
                'symbol': symbol,
                'type': option_type,
                'strike': strike,
                'entry_price': entry_price,
                'highest_price': entry_price,
                'expiry': expiry_formatted
            }
            
            logger.info(f"✅ Trade #{trade_id} added to active_trades dictionary")
            
            # Start tracking task
            logger.info(f"🔄 Creating tracking task for trade #{trade_id}...")
            task = asyncio.create_task(self._track_position(trade_id))
            self.tracking_tasks[trade_id] = task
            logger.info(f"✅ Tracking task created and stored for trade #{trade_id}")
            
            logger.info(f"✅ Started tracking manual trade #{trade_id}")
            print(f"✅ Started tracking manual trade #{trade_id}\n")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error starting manual trade tracking: {e}")
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _update_balance_loop(self):
        """Update account balance periodically"""
        while self.running:
            try:
                balance = await self.ibkr.get_account_balance()
                if balance:
                    self.current_balance = balance
                
                await asyncio.sleep(config.POSITION_UPDATE_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating balance: {e}")
                await asyncio.sleep(config.POSITION_UPDATE_INTERVAL)
    
    def _is_strike_already_open(self, strike: float, option_type: str, symbol: str) -> bool:
        """
        Check if a strike is already open for the given option type and symbol.
        
        Args:
            strike: Strike price to check
            option_type: 'CALL' or 'PUT'
            symbol: Trading symbol (e.g., 'SPX')
            
        Returns:
            True if strike is already open, False otherwise
        """
        try:
            # Get active trades from database
            active_trades = self.db.get_active_trades(symbol=symbol)
            
            # Check if any active trade has the same strike and type
            for trade in active_trades:
                if trade['trade_type'] == option_type and abs(trade['strike_price'] - strike) < 0.01:
                    logger.info(f"⚠️ Strike {strike} already open for {option_type} {symbol}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking strike: {e}")
            return False
    
    def get_blocking_trade_data(self, strike: float, option_type: str, symbol: str) -> dict:
        """
        Get complete data of the blocking trade (for duplicate prevention notification).
        
        Args:
            strike: Strike price to check
            option_type: 'CALL' or 'PUT'
            symbol: Trading symbol
            
        Returns:
            Dictionary with complete trade data for notification
        """
        try:
            # Get active trades from database
            active_trades = self.db.get_active_trades(symbol=symbol)
            
            # Find the blocking trade
            for trade in active_trades:
                if trade['trade_type'] == option_type and abs(trade['strike_price'] - strike) < 0.01:
                    # Get channel link
                    channel_link = 'https://t.me/channel'
                    if self.telegram and symbol in self.telegram.channels:
                        if self.telegram.channels[symbol]:
                            channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
                    
                    # Get emoji
                    emoji = '📈' if option_type == 'CALL' else '📉'
                    
                    return {
                        'symbol': symbol,
                        'type': option_type,
                        'strike': trade['strike_price'],
                        'entry_price': trade.get('entry_price', 0),
                        'current_price': trade.get('current_price', 0),
                        'highest_price': trade.get('highest_price', 0),
                        'bid': trade.get('bid', 0),
                        'ask': trade.get('ask', 0),
                        'expiry': trade.get('expiry', datetime.now().strftime('%d%b%y').upper()),
                        'emoji': emoji,
                        'channel_link': channel_link,
                        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
            
            # If not found, return minimal data
            return {
                'symbol': symbol,
                'type': option_type,
                'strike': strike,
                'entry_price': 0,
                'current_price': 0,
                'highest_price': 0,
                'bid': 0,
                'ask': 0,
                'expiry': datetime.now().strftime('%d%b%y').upper(),
                'emoji': '📈' if option_type == 'CALL' else '📉',
                'channel_link': 'https://t.me/channel',
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting blocking trade data: {e}")
            return {}
    
    def get_profit_target_blocking_trade(self, option_type: str, symbol: str) -> dict:
        """
        Get data of first trade that hasn't met profit target (for duplicate prevention).
        
        Args:
            option_type: 'CALL' or 'PUT'
            symbol: Trading symbol
            
        Returns:
            Dictionary with trade data for notification
        """
        try:
            # Get active trades from database
            active_trades = self.db.get_active_trades(symbol=symbol)
            
            # Filter by option type
            same_type_trades = [t for t in active_trades if t['trade_type'] == option_type]
            
            if not same_type_trades:
                return {}
            
            # Find first trade that hasn't met target and is not failed
            for trade in same_type_trades:
                current_price = trade.get('current_price', 0)
                
                # Skip failed trades
                if current_price < config.FAILED_TRADE_THRESHOLD:
                    continue
                
                # Get channel link
                channel_link = 'https://t.me/channel'
                if self.telegram and symbol in self.telegram.channels:
                    if self.telegram.channels[symbol]:
                        channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
                
                # Get emoji
                emoji = '📈' if option_type == 'CALL' else '📉'
                
                return {
                    'symbol': symbol,
                    'type': option_type,
                    'strike': trade['strike_price'],
                    'entry_price': trade.get('entry_price', 0),
                    'current_price': current_price,
                    'highest_price': trade.get('highest_price', 0),
                    'bid': trade.get('bid', 0),
                    'ask': trade.get('ask', 0),
                    'expiry': trade.get('expiry', datetime.now().strftime('%d%b%y').upper()),
                    'emoji': emoji,
                    'channel_link': channel_link,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"❌ Error getting profit target blocking trade: {e}")
            return {}
    
    def _check_profit_target_met(self, option_type: str, symbol: str, target: float = 2.00) -> tuple[bool, str]:
        """
        Check if all active trades of the same type have met the profit target.
        Ignores trades with current price < FAILED_TRADE_THRESHOLD (considered failed).
        
        Args:
            option_type: 'CALL' or 'PUT'
            symbol: Trading symbol (e.g., 'SPX')
            target: Minimum profit target in dollars (default: $2.00)
            
        Returns:
            Tuple of (target_met, reason_message)
        """
        try:
            # Get active trades from database
            active_trades = self.db.get_active_trades(symbol=symbol)
            
            # Filter by option type
            same_type_trades = [t for t in active_trades if t['trade_type'] == option_type]
            
            if not same_type_trades:
                # No active trades of this type, allow new trade
                return (True, "No active trades")
            
            # Check each trade
            blocking_trades = []
            for trade in same_type_trades:
                current_price = trade.get('current_price') or 0
                entry_price = trade.get('entry_price') or 0
                
                # Exception: Ignore trades with current price < FAILED_TRADE_THRESHOLD (considered failed)
                if current_price < config.FAILED_TRADE_THRESHOLD:
                    logger.info(f"⚠️ Ignoring trade #{trade['id']} (price ${current_price:.2f} < ${config.FAILED_TRADE_THRESHOLD:.2f})")
                    continue
                
                # Calculate profit
                profit = current_price - entry_price
                
                if profit < target:
                    blocking_trades.append({
                        'id': trade['id'],
                        'strike': trade['strike_price'],
                        'entry': entry_price,
                        'current': current_price,
                        'profit': profit
                    })
            
            if blocking_trades:
                # Build detailed message
                msg_parts = [f"⚠️ Profit target not met for {len(blocking_trades)} trade(s):"]
                for t in blocking_trades:
                    msg_parts.append(
                        f"  • Trade #{t['id']}: Strike {t['strike']}, "
                        f"Entry ${t['entry']:.2f} → Current ${t['current']:.2f} = "
                        f"Profit ${t['profit']:.2f} (need ${target:.2f})"
                    )
                reason = "\n".join(msg_parts)
                return (False, reason)
            
            return (True, "All trades met profit target")
            
        except Exception as e:
            logger.error(f"❌ Error checking profit target: {e}")
            return (True, "Error occurred, allowing trade")  # Fail-safe
    
    async def process_signal(self, symbol: str, signal_type: str):
        """Process incoming signal from TradingView"""
        # Increment queue counter
        self._signal_queue_count += 1
        queue_position = self._signal_queue_count
        
        logger.info(f"📡 Signal received: {signal_type} {symbol} (Queue position: {queue_position})")
        print(f"\n{'='*60}")
        print(f"📥 SIGNAL RECEIVED")
        print(f"📊 Symbol: {symbol}")
        print(f"📈 Type: {signal_type}")
        print(f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}")
        print(f"🔢 Queue Position: {queue_position}")
        print(f"{'='*60}\n")
        
        # Acquire lock to process signals one at a time
        async with self._signal_lock:
            try:
                logger.info(f"🔒 Lock acquired for {signal_type} {symbol} - Starting processing...")
                print(f"🔓 Lock acquired - Processing {signal_type} {symbol}...\n")
                
                await self._process_signal_internal(symbol, signal_type, queue_position)
                
                logger.info(f"🔓 Lock released for {signal_type} {symbol}")
                print(f"\n✅ Processing complete - Lock released\n")
            except Exception as e:
                logger.error(f"❌ Error in signal processing: {e}")
                print(f"\n{'='*60}")
                print(f"❌ ERROR IN SIGNAL PROCESSING")
                print(f"Error: {e}")
                print(f"{'='*60}\n")
                import traceback
                traceback.print_exc()
    
    async def _process_signal_internal(self, symbol: str, signal_type: str, queue_position: int):
        """Internal signal processing (called within lock)"""
        start_time = datetime.now()
        try:
            logger.info(f"🔄 Processing {signal_type} signal for {symbol}")
            print(f"{'='*60}")
            print(f"🔄 PROCESSING SIGNAL #{queue_position}")
            print(f"📊 Symbol: {symbol}")
            print(f"📈 Type: {signal_type}")
            print(f"⏰ Started: {start_time.strftime('%H:%M:%S.%f')[:-3]}")
            print(f"{'='*60}\n")
            
            # Add signal to database
            signal_id = self.db.add_signal(symbol, signal_type)
            logger.info(f"✅ Signal added to database: ID {signal_id}")
            print(f"✅ Signal added to database: ID {signal_id}")
            
            # Send signal received notification
            await self.telegram.send_notification('signal_received', {
                'type': signal_type,
                'symbol': symbol,
                'time': datetime.now().strftime('%H:%M:%S')
            }, symbol)
            logger.info(f"✅ Telegram notification sent")
            print(f"✅ Telegram notification sent")
            
            # ═══════════════════════════════════════════════════════════════
            # DUPLICATE PREVENTION CHECK #1: Profit Target
            # ═══════════════════════════════════════════════════════════════
            print(f"\n🔍 Checking profit target for existing {signal_type} trades...")
            logger.info(f"🔍 Checking profit target (${config.MIN_PROFIT_TARGET:.2f})...")
            
            target_met, reason = self._check_profit_target_met(signal_type, symbol, config.MIN_PROFIT_TARGET)
            
            if not target_met:
                logger.warning(f"❌ SIGNAL REJECTED: {reason}")
                print(f"\n{'='*60}")
                print(f"❌ SIGNAL REJECTED - PROFIT TARGET NOT MET")
                print(f"{'='*60}")
                print(reason)
                print(f"\nRequired: All active {signal_type} trades must have ${config.MIN_PROFIT_TARGET:.2f}+ profit")
                print(f"Exception: Trades with current price < ${config.FAILED_TRADE_THRESHOLD:.2f} are ignored (considered failed)")
                print(f"{'='*60}\n")
                
                # Mark signal as processed (rejected)
                self.db.mark_signal_processed(signal_id)
                return
            
            logger.info(f"✅ Profit target check passed: {reason}")
            print(f"✅ Profit target check passed: {reason}")
            
            # Find contract using GUI's watchlist (FAST - same as manual trading!)
            print(f"\n🔍 Searching for {signal_type} contract in GUI watchlist...")
            logger.info(f"⚡ Using GUI watchlist for instant execution (like manual trading)")
            
            contract_data = None
            if self.gui_instance:
                # Call GUI's get_best_contract_from_watchlist (thread-safe)
                try:
                    contract_data = self.gui_instance.get_best_contract_from_watchlist(symbol, signal_type)
                except Exception as e:
                    logger.error(f"❌ Error getting contract from GUI watchlist: {e}")
            
            if not contract_data:
                logger.warning(f"⚠️ GUI watchlist not available, falling back to IBKR cache...")
                print(f"⚠️ GUI watchlist not available, using IBKR cache...")
                
                # Fallback to IBKR cache method
                ibkr_conn = self.ibkr_connections.get(symbol)
                
                if not ibkr_conn:
                    logger.error(f"❌ No IBKR connection for {symbol}")
                    print(f"\n❌ ERROR: Cannot get IBKR connection for {symbol}!")
                    return
                
                contract_info = await ibkr_conn.find_contract_from_cache(
                    symbol=symbol,
                    option_type=signal_type,
                    range_start=config.SELECTION_RANGE_START,
                    range_end=config.SELECTION_RANGE_END,
                    selection_mode=config.SELECTION_MODE,
                    max_cache_age=10
                )
                
                if not contract_info:
                    logger.error(f"❌ No suitable contract found for {signal_type} {symbol}")
                    print(f"\n{'='*60}")
                    print(f"❌ ERROR: NO CONTRACT FOUND!")
                    print(f"{'='*60}")
                    print(f"Signal: {signal_type} {symbol}")
                    print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
                    print(f"\n🔍 TROUBLESHOOTING:")
                    print(f"\n1. Check GUI Watchlist:")
                    print(f"   - Ensure system is running and watchlist is updating")
                    print(f"   - Open Watchlist tab in GUI")
                    print(f"   - Verify {symbol} {signal_type} options are showing")
                    print(f"\n2. Check Market Hours:")
                    print(f"   - Options trade 9:30 AM - 4:00 PM EST")
                    print(f"   - Current time: {datetime.now().strftime('%I:%M %p')}")
                    print(f"\n3. Check Price Range (config.py):")
                    print(f"   - MIN_OPTION_PRICE: ${config.MIN_OPTION_PRICE}")
                    print(f"   - MAX_OPTION_PRICE: ${config.MAX_OPTION_PRICE}")
                    print(f"   - Check if any contracts are in this range")
                    print(f"{'='*60}\n")
                    return
                
                # Unpack from IBKR cache format: (contract, strike, bid, ask)
                contract, strike, bid, ask = contract_info
                entry_price = ask  # Use ASK for buying
                logger.info(f"✅ Contract found (IBKR cache): Strike {strike}, Entry ${entry_price:.2f}")
            else:
                # Got contract from GUI watchlist (FAST!)
                strike = contract_data['strike']
                entry_price = contract_data['entry_price']  # Already ASK
                logger.info(f"⚡ Contract found (GUI watchlist): Strike {strike}, Entry ${entry_price:.2f}")
                print(f"⚡ FAST MODE: Contract from GUI watchlist!")
                print(f"   Strike: {strike}")
                print(f"   Entry Price: ${entry_price:.2f}")
                
                # Need to create contract object for tracking
                from ib_insync import Option
                
                # Get dedicated IBKR connection for this symbol
                ibkr_conn = self.ibkr_connections.get(symbol)
                if not ibkr_conn:
                    logger.error(f"❌ No IBKR connection for {symbol}")
                    return
                
                # Get expiry date (use 0DTE if not set)
                expiry_date = datetime.now().strftime('%Y%m%d')
                
                # Create contract
                right = 'C' if signal_type == 'CALL' else 'P'
                
                # Set exchange and trading class based on symbol
                if symbol == 'SPX':
                    exchange = 'CBOE'
                    trading_class = 'SPXW'
                elif symbol == 'NDX':
                    exchange = 'CBOE'
                    trading_class = 'NDXP'
                else:
                    exchange = 'SMART'
                    trading_class = symbol
                
                contract = Option(symbol, expiry_date, float(strike), right, exchange, tradingClass=trading_class)
                
                # Qualify contract
                qualified = await ibkr_conn.ib.qualifyContractsAsync(contract)
                if qualified:
                    contract = qualified[0]
            
            logger.info(f"✅ Final contract: Strike {strike}, Entry ${entry_price:.2f}")
            print(f"✅ Contract ready for execution!")
            print(f"   Strike: {strike}")
            print(f"   Entry Price: ${entry_price:.2f}")
            
            # ═══════════════════════════════════════════════════════════════
            # DUPLICATE PREVENTION CHECK #2: Strike Already Open
            # ═══════════════════════════════════════════════════════════════
            # ✅ DUPLICATE PREVENTION CHECK #2: REMOVED
            # السماح بفتح نفس Strike عدة مرات - كل واحدة trade منفصل!
            # ═══════════════════════════════════════════════════════════════
            print(f"\n📊 Checking strike {strike}...")
            logger.info(f"📊 Strike analysis...")
            
            existing_strikes = [
                t['strike_price'] for t in self.db.get_active_trades(symbol)
                if t['trade_type'] == signal_type
            ]
            if strike in existing_strikes:
                logger.info(f"ℹ️ Strike {strike} already has active trade(s), but allowing new entry (separate tracking)")
                print(f"ℹ️ Strike {strike} has existing position(s), opening new separate entry\n")
            else:
                logger.info(f"✅ New strike - first entry")
                print(f"✅ New strike - first entry\n")
            
            # Extract expiry from contract for database and notifications
            try:
                contract_expiry = contract.lastTradeDateOrContractMonth
                # Format expiry (from YYYYMMDD to DD MMM YY)
                from datetime import datetime as dt
                expiry_dt = dt.strptime(contract_expiry, '%Y%m%d')
                expiry_formatted = expiry_dt.strftime('%d%b%y').upper()
            except:
                expiry_formatted = datetime.now().strftime('%d%b%y').upper()
            
            # Send contract found notification (THEN send to Telegram)
            await self.telegram.send_notification('contract_found', {
                'symbol': symbol,
                'type': signal_type,
                'strike': strike,
                'price': entry_price,
                'time': datetime.now().strftime('%H:%M:%S')
            }, symbol)
            
            # Create trade in database
            trade_id = self.db.create_trade(
                symbol=symbol,
                trade_type=signal_type,
                option_contract=str(contract),
                strike_price=float(strike),  # Ensure float
                entry_price=entry_price,
                expiry=expiry_formatted,
                bid=bid,
                ask=ask
            )
            logger.info(f"✅ Trade created in database: ID {trade_id}")
            print(f"✅ Trade created in database: ID {trade_id}")
            
            # Send position opened notification
            print(f"\n📤 إرسال إشعار position_opened للتيليجرام...")
            print(f"   Symbol: {symbol}")
            print(f"   Type: {signal_type}")
            print(f"   Contract: {str(contract)}")
            print(f"   Strike: {strike}")
            print(f"   Entry Price: {entry_price}")
            
            # Extract expiry from contract for notification
            try:
                contract_expiry = contract.lastTradeDateOrContractMonth
                # Format expiry (from YYYYMMDD to DD MMM YY)
                from datetime import datetime as dt
                expiry_dt = dt.strptime(contract_expiry, '%Y%m%d')
                expiry_formatted = expiry_dt.strftime('%d%b%y').upper()
            except:
                expiry_formatted = datetime.now().strftime('%d%b%y').upper()
            
            # Get channel link for this symbol
            channel_link = 'https://t.me/channel'  # Default
            if self.telegram and symbol in self.telegram.channels:
                if self.telegram.channels[symbol]:
                    channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
            
            # Determine emoji based on signal type
            emoji = '📈' if signal_type == 'CALL' else '📉'
            
            await self.telegram.send_notification('position_opened', {
                'symbol': symbol,
                'type': signal_type,
                'contract': str(contract),
                'strike': strike,
                'entry_price': entry_price,
                'current_price': entry_price,  # Add current_price for image
                'ask': entry_price + 0.05,  # Estimate ask
                'bid': entry_price,  # Use entry_price as bid
                'mid': entry_price + 0.025,  # Midpoint
                'expiry': expiry_formatted,  # Format: DD MMM YY
                'emoji': emoji,  # Add emoji
                'channel_link': channel_link,  # Add channel link
                'time': datetime.now().strftime('%H:%M:%S')
            }, symbol)
            
            print(f"✅ تم إرسال إشعار position_opened")
            
            # Mark signal as processed
            self.db.mark_signal_processed(signal_id)
            
            # Start tracking
            self.active_trades[trade_id] = {
                'contract': contract,
                'symbol': symbol,
                'type': signal_type,
                'strike': float(strike),  # Ensure float
                'entry_price': entry_price,
                'highest_price': entry_price,
                'expiry': expiry_formatted
            }
            
            # Start tracking task
            task = asyncio.create_task(self._track_position(trade_id))
            self.tracking_tasks[trade_id] = task
            
            # Calculate processing time
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info(f"✅ Started tracking trade #{trade_id}")
            print(f"✅ Started tracking trade #{trade_id}")
            print(f"\n{'='*60}")
            print(f"🎉 SIGNAL PROCESSING COMPLETE")
            print(f"📊 Trade ID: {trade_id}")
            print(f"📈 Type: {signal_type} {symbol}")
            print(f"💰 Entry: ${entry_price:.2f} @ Strike {strike}")
            print(f"⚡ Processing Time: {duration:.2f}s")
            print(f"{'='*60}\n")
        
        except Exception as e:
            logger.error(f"❌ Error in _process_signal_internal: {e}")
            import traceback
            traceback.print_exc()
            raise  # Re-raise to be caught by outer exception handler
    
    async def _track_position(self, trade_id: int):
        """Track position price continuously with auto-retry on errors"""
        retry_count = 0
        max_retries = 999999  # Unlimited retries effectively
        retry_delay = 3  # 3 seconds between retries
        
        while retry_count < max_retries:
            try:
                trade = self.active_trades[trade_id]
                contract = trade['contract']
                entry_price = trade['entry_price']
                highest_price = trade['highest_price']
                symbol = trade['symbol']
                last_target_notified = 0  # Track last target level notified (0, 100, 200, ...)
                
                # Get dedicated IBKR connection for this symbol
                ibkr_conn = self.ibkr_connections.get(symbol)
                if not ibkr_conn:
                    logger.error(f"❌ No IBKR connection for {symbol} - retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_count += 1
                    continue
                
                if retry_count > 0:
                    logger.info(f"🔄 Reconnecting tracking for trade #{trade_id} (attempt {retry_count + 1})")
                else:
                    logger.info(f"⚡ Starting REAL-TIME tracking for trade #{trade_id} using {symbol} connection")
                
                # Define callback for instant price updates
                async def price_callback(price_data):
                    nonlocal highest_price, last_target_notified
                    
                    # Current price = BID (actual selling price for exit)
                    current_price = price_data['bid']
                    
                    # ⚡ INSTANT RISK CHECK - ALWAYS RUN, even if bid is nan/0!
                    try:
                        print(f"\n🔍 CALLBACK TRIGGERED - bid={current_price}, ask={price_data.get('ask')}, last={price_data.get('last')}")
                        
                        # Use last price if bid is not available
                        if current_price is None or current_price != current_price or current_price <= 0:  # nan check
                            current_price = price_data.get('last', current_price)
                            print(f"🔍 Using LAST price: {current_price}")
                        
                        if current_price is None or current_price != current_price or current_price <= 0:  # still bad
                            print(f"❌ No valid price data, skipping this update")
                            return
                        
                        risk_settings = self.db.get_risk_settings(symbol)
                        
                        print(f"{'='*60}")
                        print(f"🔍 CHECK Trade #{trade_id}: Entry=${entry_price:.2f}, Current=${current_price:.2f}, Highest=${highest_price:.2f}")
                        print(f"🔍 Risk Settings: {risk_settings}")
                        
                        should_close, reason = self._check_risk_management(
                            entry_price, current_price, highest_price, risk_settings
                        )
                        
                        print(f"🔍 Result: should_close={should_close}, reason='{reason}'")
                        print(f"{'='*60}\n")
                        
                        if should_close:
                            conn = self.db.connect()
                            cursor = conn.cursor()
                            cursor.execute('SELECT pending_quantity FROM trades WHERE id = ?', (trade_id,))
                            result = cursor.fetchone()
                            conn.close()
                            
                            pending_qty = result[0] if result else None
                            
                            print(f"⚡ CLOSING trade #{trade_id} ({pending_qty} contracts): {reason}")
                            logger.info(f"⚡ INSTANT CLOSE trade #{trade_id}: {reason}")
                            await self.close_position(trade_id, current_price, reason, pending_qty)
                            raise asyncio.CancelledError()
                    
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        print(f"❌ ERROR in risk check: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    # Update database
                    self.db.update_trade_price(
                        trade_id=trade_id,
                        price=current_price,
                        bid=price_data['bid'],
                        ask=price_data['ask']
                    )
                    
                    # Check for new high
                    if current_price > highest_price:
                        highest_price = current_price
                        trade['highest_price'] = highest_price
                        
                        # Calculate profit
                        profit = current_price - entry_price  # Price difference
                        profit_pct = (profit / entry_price * 100) if entry_price > 0 else 0
                        profit_dollars = profit * 100  # Each contract = 100 shares
                        profit_sar = profit_dollars * 3.75  # Convert to SAR
                        
                        # Get channel link for this symbol
                        channel_link = 'https://t.me/channel'  # Default
                        if self.telegram and symbol in self.telegram.channels:
                            if self.telegram.channels[symbol]:
                                channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
                    
                        # Determine emoji
                        emoji = '📈' if trade['type'] == 'CALL' else '📉'
                        
                        # Send new high notification with complete data for image
                        await self.telegram.send_notification('new_high', {
                            'symbol': symbol,
                            'type': trade['type'],
                            'strike': trade['strike'],
                            'contract': str(contract),
                            'entry_price': entry_price,
                            'current_price': current_price,
                            'highest_price': highest_price,
                            'bid': price_data['bid'],
                            'ask': price_data['ask'],
                            'last': price_data.get('last', current_price),
                            'profit': profit,
                            'profit_pct': profit_pct,
                            'profit_dollars': profit_dollars,
                            'profit_sar': profit_sar,
                            'expiry': trade.get('expiry', datetime.now().strftime('%d%b%y').upper()),
                            'emoji': emoji,
                            'channel_link': channel_link,
                            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }, symbol)
                    
                    # Check for target achievement (100$, 200$, 300$, ...)
                    profit = current_price - entry_price
                    profit_dollars = profit * 100
                    
                    # Calculate current target level (multiples of 100)
                    current_target_level = int(profit_dollars // 100) * 100
                    
                    # Send target_achieved notification if:
                    # 1. Profit is at or above 100$ threshold
                    # 2. We haven't sent notification for this level yet
                    if profit_dollars >= 100 and current_target_level > last_target_notified:
                        profit_sar = profit_dollars * 3.75
                        
                        # Get channel link
                        channel_link = 'https://t.me/channel'
                        if self.telegram and symbol in self.telegram.channels:
                            if self.telegram.channels[symbol]:
                                channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
                        
                        # Determine emoji
                        emoji = '📈' if trade['type'] == 'CALL' else '📉'
                        
                        # Calculate profit percentage
                        profit_pct = (profit_dollars / entry_price) * 100 if entry_price > 0 else 0
                        
                        await self.telegram.send_notification('target_achieved', {
                            'symbol': symbol,
                            'type': trade['type'],
                            'strike': trade['strike'],
                            'contract': str(contract),
                            'entry_price': entry_price,
                            'current_price': current_price,
                            'highest_price': highest_price,
                            'bid': price_data['bid'],
                            'ask': price_data['ask'],
                            'last': price_data.get('last', current_price),
                            'profit': profit,
                            'profit_dollars': profit_dollars,
                            'profit_sar': profit_sar,
                            'profit_pct': profit_pct,
                            'expiry': trade.get('expiry', datetime.now().strftime('%d%b%y').upper()),
                            'emoji': emoji,
                            'channel_link': channel_link,
                            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }, symbol)
                        
                        # Update last notified target level
                        last_target_notified = current_target_level
                        logger.info(f"🎯 Target achieved notification sent for ${current_target_level} profit")
                
                # ⚡ Start REAL-TIME tracking (callback will be called on every price change)
                logger.info(f"⚡ Starting REAL-TIME price streaming for trade #{trade_id}...")
                await ibkr_conn.track_contract_price(contract, callback=price_callback)
                
                # If we reach here, tracking completed normally
                logger.info(f"✅ Tracking loop completed normally for trade #{trade_id}")
                break
                
            except asyncio.CancelledError:
                retry_count += 1
                logger.error(f"❌ Error tracking trade #{trade_id}: {e}")
                logger.info(f"🔄 Retrying in {retry_delay} seconds... (attempt {retry_count}/{max_retries})")
                import traceback
                traceback.print_exc()
                
                # Wait before retrying
                await asyncio.sleep(retry_delay)
                
                # Check if trade still exists
                if trade_id not in self.active_trades:
                    logger.info(f"✅ Trade #{trade_id} closed - stopping tracking")
                    break
    
    def _check_risk_management(self, entry_price: float, current_price: float,
                               highest_price: float, settings: Dict) -> tuple:
        """Check if risk management rules trigger exit - INSTANT CLOSURE when conditions met!"""
        
        # Stop Loss
        if settings.get('stop_loss', {}).get('type') in ['percentage', 'amount']:
            stop_type = settings['stop_loss']['type']
            stop_value = settings['stop_loss']['value']
            
            if stop_type == 'percentage':
                stop_price = entry_price * (1 - stop_value / 100)
            else:  # amount (in real dollars, convert to contract price)
                stop_price = entry_price - (stop_value / 100)
            
            if current_price <= stop_price:
                return True, f"Stop Loss Hit (${stop_price:.2f})"
        
        # Trailing Stop
        if settings.get('trailing_stop', {}).get('type') in ['percentage', 'amount']:
            trail_type = settings['trailing_stop']['type']
            trail_value = settings['trailing_stop']['value']
            
            if trail_type == 'percentage':
                trail_stop = highest_price * (1 - trail_value / 100)
            else:  # amount (in real dollars, convert to contract price)
                trail_stop = highest_price - (trail_value / 100)
            
            if current_price <= trail_stop:
                return True, f"Trailing Stop Hit (${trail_stop:.2f})"
        
        # Capital Protection (trigger when price reaches protection level above entry)
        if settings.get('capital_protection', {}).get('type') in ['percentage', 'amount']:
            cap_type = settings['capital_protection']['type']
            cap_value = settings['capital_protection']['value']
            
            if cap_type == 'percentage':
                cap_price = entry_price * (1 + cap_value / 100)
            else:  # amount (in real dollars, convert to contract price)
                cap_price = entry_price + (cap_value / 100)
            
            # Trigger when price reaches or exceeds protection level
            if current_price >= cap_price:
                return True, f"Capital Protection Hit (${cap_price:.2f})"
        
        # Profit Target
        if settings.get('profit_target', {}).get('type') in ['percentage', 'amount']:
            target_type = settings['profit_target']['type']
            target_value = settings['profit_target']['value']
            
            if target_type == 'percentage':
                target_price = entry_price * (1 + target_value / 100)
            else:  # amount (in real dollars, convert to contract price)
                target_price = entry_price + (target_value / 100)
            
            if current_price >= target_price:
                return True, f"Profit Target Hit (${target_price:.2f})"
        
        return False, ""
    
    async def close_position(self, trade_id: int, exit_price: float, reason: str = "Manual", close_quantity: int = None):
        """Close a position fully or partially"""
        try:
            if trade_id not in self.active_trades:
                logger.warning(f"Trade #{trade_id} not found in active trades (may be already closed)")
                # Still close in database to ensure it's closed
                self.db.close_trade(trade_id, exit_price, close_quantity)
                return
            
            trade = self.active_trades[trade_id]
            entry_price = trade['entry_price']
            highest_price = trade['highest_price']
            
            # Close in database (supports partial close)
            self.db.close_trade(trade_id, exit_price, close_quantity)
            
            # Check if trade was fully closed or partially closed
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute('SELECT status, pending_quantity FROM trades WHERE id = ?', (trade_id,))
            result = cursor.fetchone()
            conn.close()
            
            is_fully_closed = (result and result[0] == 'CLOSED')
            
            # Calculate P/L (based on exit_price)
            profit = exit_price - entry_price  # Price difference
            pnl = profit * 100  # Total profit in dollars (each contract = 100 shares)
            profit_pct = (profit / entry_price * 100) if entry_price > 0 else 0
            profit_dollars = pnl  # Same as pnl
            profit_sar = profit_dollars * 3.75  # Convert to SAR
            
            # Determine if win or loss
            if pnl >= config.MIN_PROFIT_FOR_WIN:
                profit_emoji = '✅'
            else:
                profit_emoji = '❌'
            
            # Get channel link for this symbol
            channel_link = 'https://t.me/channel'  # Default
            if self.telegram and trade['symbol'] in self.telegram.channels:
                if self.telegram.channels[trade['symbol']]:
                    channel_link = self.telegram.channels[trade['symbol']][0].get('link', 'https://t.me/channel')
            
            # Get emoji based on option type
            emoji = '📈' if trade['type'] == 'CALL' else '📉'
            
            # Determine notification type based on reason
            notification_type = 'position_closed'  # Default
            notification_data = {
                'symbol': trade['symbol'],
                'type': trade['type'],
                'contract': str(trade['contract']),
                'strike': trade['strike'],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'current_price': exit_price,
                'highest_price': highest_price,
                'profit': profit,
                'pnl': abs(pnl),
                'profit_pct': profit_pct,
                'profit_dollars': profit_dollars,
                'profit_sar': profit_sar,
                'profit_emoji': profit_emoji,
                'profit_status': pnl_text,
                'reason': reason,
                'expiry': trade.get('expiry', datetime.now().strftime('%d%b%y').upper()),
                'emoji': emoji,
                'channel_link': channel_link,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'bid': exit_price,
                'ask': exit_price,
                'last': exit_price,
                'manual': False  # Auto-close from risk management
            }
            
            # Choose specific notification type based on reason
            if 'Profit Target' in reason or 'ضرب الهدف' in reason:
                notification_type = 'profit_target_hit'
            elif 'Stop Loss' in reason and 'Trailing' not in reason:
                notification_type = 'stop_loss_hit'
            elif 'Trailing Stop' in reason or 'متحرك' in reason:
                notification_type = 'trailing_stop_hit'
                # Calculate drop from peak
                drop_from_peak = (highest_price - exit_price) / highest_price * 100
                notification_data['drop_from_peak'] = drop_from_peak
            elif 'Capital Protection' in reason or 'حماية رأس المال' in reason:
                notification_type = 'capital_protection_hit'
                # Extract protection level from highest price
                protection_level = (highest_price - entry_price) / entry_price * 100
                notification_data['protection_level'] = protection_level
            
            # Send notification
            await self.telegram.send_notification(notification_type, notification_data, trade['symbol'])
            
            # Only stop tracking and remove if fully closed
            if is_fully_closed:
                # Stop tracking
                if trade_id in self.tracking_tasks:
                    self.tracking_tasks[trade_id].cancel()
                    del self.tracking_tasks[trade_id]
                
                # Remove from active trades
                del self.active_trades[trade_id]
                
                logger.info(f"✅ Fully closed trade #{trade_id} with P/L: ${pnl:.2f} ({reason})")
            else:
                # Partially closed - keep tracking
                logger.info(f"✅ Partially closed trade #{trade_id} ({close_quantity} contracts) with P/L: ${pnl:.2f} ({reason})")
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
    
    def get_active_trades_list(self) -> list:
        """Get list of active trades"""
        return list(self.active_trades.items())
    
    def get_current_balance(self) -> float:
        """Get current account balance"""
        return self.current_balance
