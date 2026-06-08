"""
SPX Smart - IBKR Client
Interactive Brokers Client للاتصال وجلب البيانات
"""
from ib_insync import IB, Option, Index, Stock
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import config
import asyncio
import logging
import random
from contract_groups import ContractGroupManager

logger = logging.getLogger(__name__)

class IBKRClient:
    def __init__(self, base_client_id=None):
        self.ib = IB()
        self.connected = False
        self.underlying_contracts = {}
        self.base_client_id = base_client_id  # Base client ID for this connection
        self.current_client_id = None  # Track current client ID
        self.connection_attempts = 0  # Track connection attempts
        
        # Watchlist cache for fast access (used by webhook signals)
        self.watchlist_cache = {}  # Format: {(symbol, option_type, expiry): {'data': [...], 'timestamp': datetime}}
        
        # Pages cache for GUI (5 pages × 10 contracts each)
        self.pages_cache = {}  # Format: {(symbol, option_type, expiry): {'pages': [[...], [...], ...], 'timestamp': datetime}}
        
        # Smart Group Managers for each symbol
        self.group_managers = {
            'SPX': {'CALL': ContractGroupManager('SPX'), 'PUT': ContractGroupManager('SPX')},
            'NDX': {'CALL': ContractGroupManager('NDX'), 'PUT': ContractGroupManager('NDX')},
            'SPY': {'CALL': ContractGroupManager('SPY'), 'PUT': ContractGroupManager('SPY')},
            'QQQ': {'CALL': ContractGroupManager('QQQ'), 'PUT': ContractGroupManager('QQQ')}
        }
        
    async def connect(self, retry_on_conflict=True, max_retries=5):
        """Connect to IBKR with random client ID to avoid conflicts"""
        
        for attempt in range(max_retries):
            try:
                # Generate random client ID based on base_client_id or random
                if self.base_client_id:
                    # Add small random offset to base (e.g., 100 + 0-49 for SPX)
                    client_id = self.base_client_id + random.randint(0, 49)
                else:
                    # Fallback to fully random (100-999)
                    client_id = random.randint(100, 999)
                self.connection_attempts += 1
                
                logger.info(f"🔗 Connecting to IBKR (Attempt {attempt + 1}/{max_retries}, Client ID: {client_id})...")
                
                # Disconnect if already connected
                if self.ib.isConnected():
                    logger.info("Disconnecting existing connection...")
                    self.ib.disconnect()
                    await asyncio.sleep(1)
                
                # Attempt connection
                await self.ib.connectAsync(
                    config.IBKR_HOST,
                    config.IBKR_PORT,
                    clientId=client_id,
                    readonly=config.IBKR_READONLY,
                    timeout=30
                )
                
                self.connected = True
                self.current_client_id = client_id
                logger.info(f"✅ Connected to IBKR at {config.IBKR_HOST}:{config.IBKR_PORT} (Client ID: {client_id}, READ-ONLY)")
                
                # Request delayed market data (free)
                self.ib.reqMarketDataType(3)
                logger.info("✅ Using delayed market data (Type 3 - Free/Delayed)")
                
                # Wait a moment for connection to stabilize
                await asyncio.sleep(1)
                
                return True
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Connection attempt {attempt + 1} failed: {error_msg}")
                
                # Check if it's a client ID conflict
                if 'clientId' in error_msg.lower() or 'already connected' in error_msg.lower():
                    logger.warning(f"⚠️ Client ID conflict detected, retrying with new ID...")
                    await asyncio.sleep(2)
                    continue
                
                # Check if it's a connection timeout
                if 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
                    logger.warning(f"⚠️ Connection timeout, retrying...")
                    await asyncio.sleep(3)
                    continue
                
                # For other errors, wait and retry
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # Exponential backoff
                    logger.info(f"⏳ Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Failed to connect after {max_retries} attempts")
                    self.connected = False
                    return False
        
        self.connected = False
        return False
    
    async def reconnect(self):
        """Reconnect to IBKR in case of disconnection"""
        logger.info("🔄 Attempting to reconnect to IBKR...")
        self.disconnect()
        await asyncio.sleep(2)
        return await self.connect()
    
    def disconnect(self):
        """Disconnect from IBKR"""
        if self.connected or self.ib.isConnected():
            try:
                self.ib.disconnect()
                logger.info(f"🔌 Disconnected from IBKR (Client ID: {self.current_client_id})")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
        self.connected = False
        self.current_client_id = None
    
    def _validate_batch_prices(self, batch_data: List[Dict], option_type: str, batch_num: int) -> bool:
        """Validate batch prices for logical consistency
        
        Args:
            batch_data: List of option data dictionaries
            option_type: 'CALL' or 'PUT'
            batch_num: Batch number for logging
            
        Returns:
            True if prices are logically consistent, False if suspicious
        """
        try:
            if not batch_data or len(batch_data) < 2:
                return True  # Not enough data to validate
            
            # Sort by strike
            sorted_data = sorted(batch_data, key=lambda x: x['strike'])
            
            suspicious_count = 0
            
            for i in range(len(sorted_data) - 1):
                current = sorted_data[i]
                next_contract = sorted_data[i + 1]
                
                current_price = current.get('ask', 0) if current.get('ask', 0) > 0 else current.get('bid', 0)
                next_price = next_contract.get('ask', 0) if next_contract.get('ask', 0) > 0 else next_contract.get('bid', 0)
                
                if current_price <= 0 or next_price <= 0:
                    continue  # Skip if no valid prices
                
                # Check price logic
                if option_type == 'CALL':
                    # CALL: As strike increases, price should decrease or stay similar
                    # Red flag: Price jumps UP significantly (more than 2x)
                    if next_price > current_price * 2:
                        logger.warning(f"⚠️ Batch {batch_num} CALL: Suspicious price jump at Strike {next_contract['strike']}")
                        logger.warning(f"   Previous (Strike {current['strike']}): ${current_price:.2f}")
                        logger.warning(f"   Current (Strike {next_contract['strike']}): ${next_price:.2f} (jumped {(next_price/current_price)*100:.0f}%)")
                        suspicious_count += 1
                
                elif option_type == 'PUT':
                    # PUT: As strike decreases, price should decrease or stay similar
                    # Red flag: Price jumps UP significantly (more than 2x)
                    if next_price > current_price * 2:
                        logger.warning(f"⚠️ Batch {batch_num} PUT: Suspicious price jump at Strike {next_contract['strike']}")
                        logger.warning(f"   Previous (Strike {current['strike']}): ${current_price:.2f}")
                        logger.warning(f"   Current (Strike {next_contract['strike']}): ${next_price:.2f} (jumped {(next_price/current_price)*100:.0f}%)")
                        suspicious_count += 1
            
            if suspicious_count > 0:
                logger.warning(f"🚨 Batch {batch_num} has {suspicious_count} suspicious price anomalies")
                return False
            
            logger.debug(f"✅ Batch {batch_num} prices validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error validating batch prices: {e}")
            return True  # On error, assume valid to avoid blocking progress
    
    def _remove_price_anomalies(self, options_data: List[Dict], option_type: str) -> List[Dict]:
        """Remove contracts with anomalous prices from dataset
        
        Args:
            options_data: List of option data dictionaries
            option_type: 'CALL' or 'PUT'
            
        Returns:
            Cleaned list with anomalies removed
        """
        try:
            if not options_data or len(options_data) < 3:
                return options_data  # Not enough data to clean
            
            # Sort by strike
            sorted_data = sorted(options_data, key=lambda x: x['strike'])
            cleaned_data = []
            removed_count = 0
            
            for i, contract in enumerate(sorted_data):
                current_price = contract.get('ask', 0) if contract.get('ask', 0) > 0 else contract.get('bid', 0)
                
                if current_price <= 0:
                    cleaned_data.append(contract)  # Keep contracts with no price (will be filtered later)
                    continue
                
                # Check against neighbors
                is_anomaly = False
                
                # Check previous contract
                if i > 0:
                    prev_contract = sorted_data[i - 1]
                    prev_price = prev_contract.get('ask', 0) if prev_contract.get('ask', 0) > 0 else prev_contract.get('bid', 0)
                    
                    if prev_price > 0:
                        if option_type == 'CALL':
                            # CALL: Price should not jump UP as strike increases
                            if current_price > prev_price * 2.5:  # 250% jump = anomaly
                                is_anomaly = True
                                logger.warning(f"🗑️ Removing CALL anomaly: Strike {contract['strike']} (${current_price:.2f}) - jumped from ${prev_price:.2f}")
                        
                        elif option_type == 'PUT':
                            # PUT: Price should not jump UP as strike decreases
                            if current_price > prev_price * 2.5:  # 250% jump = anomaly
                                is_anomaly = True
                                logger.warning(f"🗑️ Removing PUT anomaly: Strike {contract['strike']} (${current_price:.2f}) - jumped from ${prev_price:.2f}")
                
                # Check next contract (for additional confirmation)
                if i < len(sorted_data) - 1:
                    next_contract = sorted_data[i + 1]
                    next_price = next_contract.get('ask', 0) if next_contract.get('ask', 0) > 0 else next_contract.get('bid', 0)
                    
                    if next_price > 0 and prev_price > 0:
                        # If current is way higher than both neighbors, definitely anomaly
                        if current_price > prev_price * 3 and current_price > next_price * 3:
                            is_anomaly = True
                            logger.warning(f"🗑️ Removing outlier: Strike {contract['strike']} (${current_price:.2f}) - neighbors: ${prev_price:.2f}, ${next_price:.2f}")
                
                if not is_anomaly:
                    cleaned_data.append(contract)
                else:
                    removed_count += 1
            
            if removed_count > 0:
                logger.info(f"🧹 Removed {removed_count} anomalous contracts from dataset")
            
            return cleaned_data
            
        except Exception as e:
            logger.error(f"Error removing price anomalies: {e}")
            return options_data  # On error, return original data
    
    def _get_underlying_contract(self, symbol: str):
        """Get underlying contract"""
        if symbol not in self.underlying_contracts:
            if symbol == 'SPX':
                self.underlying_contracts[symbol] = Index('SPX', 'CBOE')
            elif symbol == 'NDX':
                self.underlying_contracts[symbol] = Index('NDX', 'NASDAQ')
            else:
                self.underlying_contracts[symbol] = Stock(symbol, 'SMART', 'USD')
        
        return self.underlying_contracts[symbol]
    
    async def get_underlying_price(self, symbol: str) -> Optional[float]:
        """Get current underlying price"""
        try:
            print(f"\n{'='*60}")
            print(f"📊 جلب سعر {symbol} من IBKR...")
            print(f"{'='*60}")
            
            # Check connection and reconnect if needed
            if not self.connected or not self.ib.isConnected():
                print(f"⚠️ غير متصل بـ IBKR، محاولة الاتصال...")
                logger.warning(f"Not connected to IBKR, attempting to connect...")
                success = await self.connect()
                if not success:
                    print(f"❌ فشل الاتصال بـ IBKR")
                    logger.error("Failed to connect to IBKR")
                    return None
            
            print(f"✅ متصل بـ IBKR")
            
            contract = self._get_underlying_contract(symbol)
            print(f"📋 عقد {symbol}: {contract.symbol} {contract.secType} {contract.exchange}")
            
            qualified = await self.ib.qualifyContractsAsync(contract)
            
            if not qualified:
                print(f"❌ فشل التحقق من عقد {symbol}")
                logger.error(f"Could not qualify {symbol} contract")
                return None
            
            print(f"✅ تم التحقق من العقد بنجاح")
            print(f"   ConId: {qualified[0].conId}")
            
            logger.info(f"Requesting market data for {symbol}...")
            print(f"📡 طلب بيانات السوق...")
            
            # Request market data (generic tick list for delayed data)
            ticker = self.ib.reqMktData(qualified[0], '233', False, False)
            
            print(f"⏳ انتظار البيانات...")
            print(f"   Ticker: {ticker}")
            
            # Wait and check ticker data multiple times
            price = None
            for attempt in range(40):  # Try 40 times over 20 seconds
                await asyncio.sleep(0.5)
                
                # Print ticker state every 2 seconds
                if attempt % 4 == 0:
                    print(f"\n📊 محاولة {attempt+1}/40:")
                    print(f"   Last: {ticker.last}")
                    print(f"   Close: {ticker.close}")
                    print(f"   Bid: {ticker.bid}")
                    print(f"   Ask: {ticker.ask}")
                    print(f"   High: {ticker.high}")
                    print(f"   Low: {ticker.low}")
                    print(f"   Time: {ticker.time}")
                
                # Check Last price
                if ticker.last and ticker.last > 0:
                    price = ticker.last
                    print(f"✅ استخدام Last price: ${price:.2f}")
                    logger.info(f"✅ {symbol} Last price: ${price:.2f} (attempt {attempt+1})")
                    break
                # Check Close price
                elif ticker.close and ticker.close > 0:
                    price = ticker.close
                    print(f"✅ استخدام Close price: ${price:.2f}")
                    logger.info(f"✅ {symbol} Close price: ${price:.2f} (attempt {attempt+1})")
                    break
                # Check High price (delayed data might only have high/low)
                elif ticker.high and ticker.high > 0:
                    price = ticker.high
                    print(f"✅ استخدام High price: ${price:.2f}")
                    logger.info(f"✅ {symbol} High price: ${price:.2f} (attempt {attempt+1})")
                    break
                # Check Bid/Ask
                elif ticker.bid and ticker.bid > 0:
                    price = ticker.bid
                    print(f"✅ استخدام Bid price: ${price:.2f}")
                    logger.info(f"✅ {symbol} Bid price: ${price:.2f} (attempt {attempt+1})")
                    break
                elif ticker.ask and ticker.ask > 0:
                    price = ticker.ask
                    print(f"✅ استخدام Ask price: ${price:.2f}")
                    logger.info(f"✅ {symbol} Ask price: ${price:.2f} (attempt {attempt+1})")
                    break
            
            # Cancel market data
            self.ib.cancelMktData(qualified[0])
            print(f"🔴 إلغاء طلب بيانات السوق")
            
            if price and price > 0:
                print(f"\n{'='*60}")
                print(f"✅✅ تم الحصول على سعر {symbol}: ${price:.2f}")
                print(f"{'='*60}\n")
                logger.info(f"✅✅ {symbol} Final Price: ${price:.2f}")
                return price
            else:
                print(f"\n{'='*60}")
                print(f"❌ فشل الحصول على سعر {symbol} بعد 40 محاولة")
                print(f"   آخر حالة للـ Ticker:")
                print(f"   Last={ticker.last}, Close={ticker.close}")
                print(f"   Bid={ticker.bid}, Ask={ticker.ask}")
                print(f"   High={ticker.high}, Low={ticker.low}")
                print(f"   marketDataType: {ticker.marketDataType}")
                print(f"{'='*60}\n")
                logger.error(f"❌ Could not get valid {symbol} price after 40 attempts")
                logger.error(f"   Last={ticker.last}, Close={ticker.close}, Bid={ticker.bid}, Ask={ticker.ask}")
                
                # Try to get historical close price as fallback
                print(f"🔄 محاولة الحصول على آخر سعر من البيانات التاريخية...")
                try:
                    bars = await self.ib.reqHistoricalDataAsync(
                        qualified[0],
                        endDateTime='',
                        durationStr='1 D',
                        barSizeSetting='1 day',
                        whatToShow='TRADES',
                        useRTH=True
                    )
                    if bars and len(bars) > 0:
                        price = bars[-1].close
                        print(f"✅ تم الحصول على آخر سعر إغلاق: ${price:.2f}")
                        logger.info(f"✅ Got historical close price for {symbol}: ${price:.2f}")
                        return price
                except Exception as e:
                    print(f"❌ فشل الحصول على البيانات التاريخية: {e}")
                    logger.error(f"Failed to get historical data: {e}")
                
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting {symbol} price: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_account_balance(self) -> Optional[float]:
        """Get account balance"""
        try:
            if not self.connected:
                await self.connect()
            
            account_values = self.ib.accountValues()
            
            for item in account_values:
                if item.tag == 'NetLiquidation' and item.currency == 'USD':
                    balance = float(item.value)
                    logger.info(f"💰 Account Balance: ${balance:,.2f}")
                    return balance
            
            return None
        except Exception as e:
            logger.error(f"❌ Error getting account balance: {e}")
            return None
    
    async def get_expiry_date(self) -> str:
        """Get current expiry date from IBKR server time (0DTE)"""
        try:
            if not self.connected:
                await self.connect()
            
            ibkr_time = await self.ib.reqCurrentTimeAsync()
            expiry_date = ibkr_time.strftime('%Y%m%d')
            logger.info(f"📅 Expiry Date: {expiry_date}")
            
            return expiry_date
        except Exception as e:
            logger.error(f"❌ Error getting expiry date: {e}")
            return datetime.now().strftime('%Y%m%d')
    
    async def fetch_single_option(self, symbol: str, strike: float, expiry: str, 
                                  option_type: str, snapshot_wait: float = 1.0) -> Optional[Dict]:
        """
        Fetch single option contract (for adaptive watchlist system)
        
        Args:
            symbol: Symbol (SPX, NDX, SPY, QQQ)
            strike: Strike price
            expiry: Expiry date (YYYYMMDD format)
            option_type: 'CALL' or 'PUT'
            snapshot_wait: Wait time for snapshot data (seconds)
            
        Returns:
            Dict with contract data or None
        """
        try:
            if not self.connected or not self.ib.isConnected():
                logger.warning("Not connected, attempting to connect...")
                success = await self.connect()
                if not success:
                    logger.error("Failed to connect to IBKR")
                    return None
            
            # Setup contract
            right = 'C' if option_type == 'CALL' else 'P'
            
            if symbol == 'SPX':
                exchange = 'CBOE'
                trading_class = 'SPXW'
            elif symbol == 'NDX':
                exchange = 'CBOE'
                trading_class = 'NDXP'
            else:
                exchange = 'SMART'
                trading_class = symbol
            
            # Create contract
            contract = Option(
                symbol=symbol,
                lastTradeDateOrContractMonth=expiry,
                strike=strike,
                right=right,
                exchange=exchange,
                tradingClass=trading_class
            )
            
            # Qualify contract
            qualified = await self.ib.qualifyContractsAsync(contract)
            
            if not qualified:
                logger.debug(f"❌ Could not qualify: {symbol} {strike} {right}")
                return None
            
            # Request market data (snapshot)
            ticker = self.ib.reqMktData(qualified[0], '', True, False)
            
            # Wait for snapshot
            await asyncio.sleep(snapshot_wait)
            
            # Extract prices
            bid = ticker.bid if ticker.bid == ticker.bid and ticker.bid > 0 else 0
            ask = ticker.ask if ticker.ask == ticker.ask and ticker.ask > 0 else 0
            last = ticker.last if ticker.last == ticker.last and ticker.last > 0 else 0
            close = ticker.close if ticker.close == ticker.close and ticker.close > 0 else 0
            
            # Cancel market data
            self.ib.cancelMktData(qualified[0])
            
            # Return data
            return {
                'symbol': symbol,
                'strike': strike,
                'expiry': expiry,
                'type': option_type,
                'bid': bid,
                'ask': ask,
                'last': last,
                'close': close,
                'contract': qualified[0]
            }
            
        except Exception as e:
            logger.error(f"❌ Error fetching single option {symbol} {strike} {option_type}: {e}")
            return None
    
    async def get_watchlist_options(self, symbol: str, option_type: str,
                                   count: int = None, expiry_date: str = None,
                                   target_price_range: Tuple[float, float] = None) -> List[Dict]:
        """Get watchlist options using Smart Grouping System (CALL or PUT)
        
        Args:
            symbol: Symbol to get options for (SPX, NDX, SPY, QQQ)
            option_type: 'CALL' or 'PUT'
            count: Number of contracts (default: from config.WATCHLIST_CONTRACTS)
            expiry_date: Optional expiry date in YYYYMMDD format. If None, uses 0DTE (today)
            target_price_range: Optional (min_price, max_price) to filter target groups
            
        Returns:
            List of option contracts with prices, organized in groups
        """
        try:
            # Import config
            from config import WATCHLIST_CONTRACTS, BATCH_SIZE, BATCH_DELAY, SNAPSHOT_WAIT
            
            # Check connection and reconnect if needed
            if not self.connected or not self.ib.isConnected():
                logger.warning("Not connected, attempting to connect...")
                success = await self.connect()
                if not success:
                    logger.error("Failed to connect to IBKR")
                    return []
            
            # Get contract count from config or use provided count
            if count is None:
                count = WATCHLIST_CONTRACTS.get(symbol, 30)
            
            logger.info(f"🔄 Getting {count} {option_type} options for {symbol} using Smart Grouping (Batch size: {BATCH_SIZE})...")
            
            # Get underlying price
            underlying_price = await self.get_underlying_price(symbol)
            if not underlying_price:
                logger.error(f"Cannot get watchlist - no underlying price for {symbol}")
                return []
            
            logger.info(f"💰 Underlying price: ${underlying_price:.2f}")
            
            # Get expiry (use custom date if provided, otherwise use 0DTE)
            if expiry_date:
                expiry = expiry_date
                logger.info(f"📅 Using custom expiry date: {expiry}")
            else:
                expiry = await self.get_expiry_date()
                logger.info(f"📅 Using 0DTE expiry: {expiry}")
            
            # === SMART GROUPING SYSTEM ===
            # Get the group manager for this symbol and option type
            group_mgr = self.group_managers[symbol][option_type]
            
            # Check if we need to refetch or can use cached groups
            if group_mgr.needs_refetch(underlying_price, option_type):
                logger.info(f"📥 Fetching new contracts from IBKR...")
                
                # Calculate start strike (2 contracts before current price)
                start_strike = group_mgr.calculate_start_strike(underlying_price, option_type)
                
                # Generate strikes
                strikes = group_mgr.generate_strikes(start_strike, count, option_type)
                
                logger.info(f"📊 {option_type} Strike range: {strikes[0]} to {strikes[-1]} (Start: {start_strike}, Price: {underlying_price:.2f})")
                
                # Set exchange and trading class based on symbol
                right = 'C' if option_type == 'CALL' else 'P'
                if symbol == 'SPX':
                    exchange = 'CBOE'
                    trading_class = 'SPXW'
                elif symbol == 'NDX':
                    exchange = 'CBOE' 
                    trading_class = 'NDXP'
                else:
                    exchange = 'SMART'
                    trading_class = symbol
                
                # Fetch contracts in batches of 2 (optimized for less pressure)
                options_data = []
                num_batches = (count + BATCH_SIZE - 1) // BATCH_SIZE  # Ceiling division
                
                logger.info(f"📦 Fetching {count} contracts in {num_batches} batches of {BATCH_SIZE}...")
                
                for batch_num in range(num_batches):
                    start_idx = batch_num * BATCH_SIZE
                    end_idx = min(start_idx + BATCH_SIZE, count)
                    batch_strikes = strikes[start_idx:end_idx]
                    
                    logger.info(f"📥 Batch {batch_num + 1}/{num_batches}: Strikes {batch_strikes[0]} to {batch_strikes[-1]} ({len(batch_strikes)} contracts)")
                    
                    # Try to fetch batch data (with retry for failed contracts)
                    max_retries = 2
                    for retry_attempt in range(max_retries):
                        if retry_attempt > 0:
                            logger.warning(f"🔄 Retry attempt {retry_attempt} for batch {batch_num + 1}")
                            await asyncio.sleep(1)
                        
                        # Create option contracts for this batch
                        batch_contracts = [Option(symbol, expiry, strike, right, exchange, tradingClass=trading_class) 
                                          for strike in batch_strikes]
                        
                        # Qualify contracts
                        logger.debug(f"🔍 Qualifying {len(batch_contracts)} contracts...")
                        qualified_results = await asyncio.gather(
                            *[self.ib.qualifyContractsAsync(opt) for opt in batch_contracts],
                            return_exceptions=True
                        )
                        
                        # Request market data for valid contracts
                        tickers_map = {}
                        for strike, result in zip(batch_strikes, qualified_results):
                            if isinstance(result, list) and result:
                                contract = result[0]
                                ticker = self.ib.reqMktData(contract, '', True, False)
                                tickers_map[strike] = (contract, ticker)
                        
                        logger.debug(f"📊 Requesting snapshot data for {len(tickers_map)} contracts...")
                        
                        # Wait for snapshot data
                        check_interval = 0.3
                        elapsed = 0
                        
                        while elapsed < SNAPSHOT_WAIT:
                            await asyncio.sleep(check_interval)
                            elapsed += check_interval
                            
                            # Check progress
                            ready_count = sum(1 for _, (_, ticker) in tickers_map.items() 
                                             if (ticker.bid and ticker.bid > 0) or 
                                                (ticker.ask and ticker.ask > 0) or 
                                                (ticker.last and ticker.last > 0) or 
                                                (ticker.close and ticker.close > 0))
                            
                            # 95% threshold
                            if ready_count >= len(tickers_map) * 0.95:
                                logger.debug(f"✅ {ready_count}/{len(tickers_map)} ready after {elapsed:.1f}s")
                                break
                        
                        # Collect prices from this batch
                        batch_data = []
                        for strike, (contract, ticker) in tickers_map.items():
                            try:
                                bid = ticker.bid if (ticker.bid and ticker.bid > 0) else None
                                ask = ticker.ask if (ticker.ask and ticker.ask > 0) else None
                                last = ticker.last if (ticker.last and ticker.last > 0) else None
                                close = ticker.close if (ticker.close and ticker.close > 0) else None
                                
                                # Smart fallback
                                final_bid = 0
                                final_ask = 0
                                
                                if bid and ask:
                                    final_bid = bid
                                    final_ask = ask
                                elif close:
                                    final_bid = close
                                    final_ask = close
                                elif last:
                                    final_bid = last
                                    final_ask = last
                                
                                batch_data.append({
                                    'strike': strike,
                                    'bid': final_bid,
                                    'ask': final_ask,
                                    'last': last if last else 0,
                                    'bid_size': ticker.bidSize or 0,
                                    'ask_size': ticker.askSize or 0,
                                    'contract': contract
                                })
                                
                                # Cancel market data immediately
                                self.ib.cancelMktData(contract)
                                
                            except Exception as e:
                                logger.debug(f"Error processing strike {strike}: {e}")
                                continue
                        
                        # Validate batch data
                        batch_valid = self._validate_batch_prices(batch_data, option_type, batch_num + 1)
                        
                        if batch_valid or retry_attempt == max_retries - 1:
                            if not batch_valid:
                                logger.warning(f"⚠️ Batch {batch_num + 1} data suspicious but proceeding")
                            options_data.extend(batch_data)
                            break
                    
                    # Delay between batches (except after last batch)
                    if batch_num < num_batches - 1:
                        logger.debug(f"⏳ Waiting {BATCH_DELAY}s before next batch...")
                        await asyncio.sleep(BATCH_DELAY)
                
                # Final validation
                logger.info(f"🔍 Running final validation on all {len(options_data)} contracts...")
                options_data = self._remove_price_anomalies(options_data, option_type)
                
                # === ORGANIZE INTO GROUPS ===
                groups = group_mgr.organize_into_groups(options_data)
                logger.info(f"📦 Organized into {len(groups)} groups of {config.GROUP_SIZE} contracts each")
                
                # Store current price
                group_mgr.current_underlying_price = underlying_price
                
            else:
                # Use cached contracts
                logger.info(f"✅ Using cached contract groups (no refetch needed)")
                options_data = group_mgr.all_contracts
                groups = group_mgr.groups
            
            # Calculate success rate
            valid_prices = sum(1 for opt in options_data if opt['bid'] > 0 or opt['ask'] > 0)
            success_rate = (valid_prices / len(options_data) * 100) if options_data else 0
            
            logger.info(f"✅ Got {len(options_data)} {option_type} options for {symbol} in {len(groups)} groups - {valid_prices}/{len(options_data)} valid ({success_rate:.1f}%)")
            
            if success_rate < 80 and len(options_data) > 0:
                logger.warning(f"⚠️ Low success rate ({success_rate:.1f}%)")
            
            # Filter by target price range if provided
            if target_price_range:
                target_groups = group_mgr.find_target_groups(target_price_range, option_type)
                filtered_contracts = group_mgr.get_group_contracts(target_groups)
                logger.info(f"🎯 Filtered to {len(filtered_contracts)} contracts in groups {target_groups} based on price range ${target_price_range[0]}-${target_price_range[1]}")
                options_data = filtered_contracts
            
            # Cache for webhooks
            cache_key = (symbol, option_type, expiry_date or 'default')
            self.watchlist_cache[cache_key] = {
                'data': options_data,
                'timestamp': datetime.now(),
                'groups': groups
            }
            
            return options_data
            
        except Exception as e:
            logger.error(f"❌ Error getting watchlist options: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_target_group_contracts(self, symbol: str, option_type: str, 
                                   price_range: Tuple[float, float]) -> List[Dict]:
        """
        Get contracts from target groups only (based on price range)
        
        Args:
            symbol: Symbol (SPX, NDX, SPY, QQQ)
            option_type: 'CALL' or 'PUT'
            price_range: (min_price, max_price) tuple
            
        Returns:
            List of contracts in target groups
        """
        try:
            group_mgr = self.group_managers[symbol][option_type]
            
            if not group_mgr.groups:
                logger.warning(f"⚠️ No groups available for {symbol} {option_type}")
                return []
            
            # Find target groups
            target_groups = group_mgr.find_target_groups(price_range, option_type)
            
            if not target_groups:
                logger.warning(f"⚠️ No target groups found for {symbol} {option_type} in range ${price_range[0]}-${price_range[1]}")
                return []
            
            # Get contracts from target groups
            target_contracts = group_mgr.get_group_contracts(target_groups)
            
            logger.info(f"🎯 {symbol} {option_type}: Showing {len(target_contracts)} contracts from groups {target_groups}")
            return target_contracts
            
        except Exception as e:
            logger.error(f"❌ Error getting target group contracts: {e}")
            return []
    
    def navigate_group(self, symbol: str, option_type: str, 
                      current_group: int, direction: str) -> Optional[List[Dict]]:
        """
        Smart Navigation: Navigate to adjacent group without refetching from IBKR
        
        Args:
            symbol: Symbol (SPX, NDX, SPY, QQQ)
            option_type: 'CALL' or 'PUT'
            current_group: Current group number
            direction: 'up' or 'down'
            
        Returns:
            List of contracts in the new group, or None if no group exists
        """
        try:
            group_mgr = self.group_managers[symbol][option_type]
            
            # Navigate to adjacent group
            new_group_num = group_mgr.navigate_to_adjacent_group(current_group, direction)
            
            if new_group_num is None:
                logger.warning(f"⚠️ Cannot navigate {direction} from group {current_group} for {symbol} {option_type}")
                return None
            
            # Get contracts from the new group
            new_contracts = group_mgr.get_group_contracts([new_group_num])
            
            logger.info(f"🔄 {symbol} {option_type}: Navigated to Group {new_group_num} ({len(new_contracts)} contracts)")
            return new_contracts
            
        except Exception as e:
            logger.error(f"❌ Error navigating groups: {e}")
            return None
    
    def get_group_stats(self, symbol: str, option_type: str) -> Dict:
        """Get statistics about groups for a symbol/option_type"""
        try:
            group_mgr = self.group_managers[symbol][option_type]
            return group_mgr.get_stats()
        except Exception as e:
            logger.error(f"❌ Error getting group stats: {e}")
            return {}
    
    async def find_contract_from_cache(self, symbol: str, option_type: str,
                                      range_start: int = 1, range_end: int = 4,
                                      selection_mode: str = 'highest',
                                      expiry_date: str = None,
                                      max_cache_age: int = 5) -> Optional[Tuple]:
        """Find contract from cached watchlist (FAST - for webhook signals)"""
        try:
            # Check cache first (for recent data)
            cache_key = (symbol, option_type, expiry_date or 'default')
            
            if cache_key in self.watchlist_cache:
                cache_entry = self.watchlist_cache[cache_key]
                cache_age = (datetime.now() - cache_entry['timestamp']).total_seconds()
                
                if cache_age <= max_cache_age:
                    # Cache is fresh - use it!
                    watchlist = cache_entry['data']
                    logger.info(f"⚡ Using cached watchlist for {symbol} {option_type} (age: {cache_age:.1f}s)")
                    print(f"⚡ FAST MODE: Using cached data (age: {cache_age:.1f}s) - No IBKR request needed!")
                else:
                    logger.info(f"📦 Cache expired for {symbol} {option_type} (age: {cache_age:.1f}s > {max_cache_age}s) - fetching new data")
                    watchlist = await self.get_watchlist_options(symbol, option_type, count=25, expiry_date=expiry_date)
            else:
                logger.info(f"📦 No cache for {symbol} {option_type} - fetching data")
                watchlist = await self.get_watchlist_options(symbol, option_type, count=25, expiry_date=expiry_date)
            
            if not watchlist:
                logger.error(f"❌ No watchlist data: {symbol} {option_type}")
                return None
            
            # Filter by price range
            valid_options = [
                opt for opt in watchlist
                if config.MIN_OPTION_PRICE <= opt['ask'] <= config.MAX_OPTION_PRICE
            ]
            
            if not valid_options:
                logger.error(f"❌ {symbol} {option_type}: No contracts in price range ${config.MIN_OPTION_PRICE}-${config.MAX_OPTION_PRICE}")
                if watchlist:
                    all_asks = [opt['ask'] for opt in watchlist if opt['ask'] > 0]
                    if all_asks:
                        logger.error(f"   Price range in watchlist: ${min(all_asks):.2f} - ${max(all_asks):.2f}")
                return None
            
            logger.info(f"✅ {symbol} {option_type}: Found {len(valid_options)} contracts in price range")
            
            # Get options in selection range
            if range_end > len(valid_options):
                range_end = len(valid_options)
            
            selected_options = valid_options[range_start-1:range_end]
            
            if not selected_options:
                logger.error(f"❌ {symbol} {option_type}: No contracts in selection range {range_start}-{range_end}")
                return None
            
            logger.info(f"✅ {symbol} {option_type}: {len(selected_options)} contracts in selection range {range_start}-{range_end}")
            
            # Select based on mode
            if selection_mode == 'highest':
                selected = max(selected_options, key=lambda x: x['ask'])
            elif selection_mode == 'lowest':
                selected = min(selected_options, key=lambda x: x['ask'])
            else:  # closest to price
                mid_price = (config.MIN_OPTION_PRICE + config.MAX_OPTION_PRICE) / 2
                selected = min(selected_options, key=lambda x: abs(x['ask'] - mid_price))
            
            logger.info(f"✅ Selected contract: Strike {selected['strike']} @ ${selected['ask']:.2f}")
            
            return (selected['contract'], selected['strike'], selected['bid'], selected['ask'])
            
        except Exception as e:
            logger.error(f"❌ Error finding contract from cache: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def find_contract_in_range(self, symbol: str, option_type: str,
                                    range_start: int = 1, range_end: int = 4,
                                    selection_mode: str = 'highest') -> Optional[Tuple]:
        """Find contract in selection range from watchlist (calls cache version)"""
        try:
            # Just call the cache version (which handles both cache and fresh data)
            return await self.find_contract_from_cache(
                symbol=symbol,
                option_type=option_type,
                range_start=range_start,
                range_end=range_end,
                selection_mode=selection_mode,
                max_cache_age=5  # 5 seconds max cache age
            )
            
        except Exception as e:
            logger.error(f"❌ Error finding contract: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def track_contract_price(self, contract, callback=None, use_bid_ask_logic=True):
        """⚡ Track contract price in REAL-TIME with streaming updates (NO DELAY!)
        
        Uses pendingTickersEvent for instant updates on every price change.
        
        Args:
            contract: Option contract to track
            callback: Callback function to receive price updates
            use_bid_ask_logic: If True, uses Bid for entry and Ask for tracking (default: True)
        """
        ticker = None
        try:
            # Ensure connection
            if not self.connected:
                logger.warning("⚠️ Connection lost - reconnecting...")
                await self.connect()
            
            # Request market data with streaming (NO snapshot delay)
            ticker = self.ib.reqMktData(contract)
            
            logger.info(f"⚡ Started REAL-TIME streaming for {contract.localSymbol}")
            
            # Flag to track if this is the entry (first tick)
            is_entry = True
            entry_price = None
            
            consecutive_errors = 0
            max_consecutive_errors = 10
            
            # Previous data for change detection
            previous_data = {'bid': 0, 'ask': 0, 'last': 0}
            
            # Initial wait for first data
            await asyncio.sleep(0.5)
            
            while True:
                try:
                    # ⚡ INSTANT UPDATE: Wait for ANY ticker event (milliseconds!)
                    await self.ib.pendingTickersEvent
                    
                    # Check connection health
                    if not self.connected or not self.ib.isConnected():
                        logger.warning("⚠️ Connection lost during tracking - reconnecting...")
                        await self.connect()
                        # Re-request market data after reconnection
                        if ticker:
                            self.ib.cancelMktData(ticker)
                        ticker = self.ib.reqMktData(contract)
                        consecutive_errors = 0
                        await asyncio.sleep(0.5)
                        continue
                    
                    bid = ticker.bid if ticker.bid == ticker.bid and ticker.bid > 0 else 0
                    ask = ticker.ask if ticker.ask == ticker.ask and ticker.ask > 0 else 0
                    last = ticker.last if ticker.last == ticker.last and ticker.last > 0 else 0
                    
                    # Check if data actually changed (avoid redundant callbacks)
                    if (bid == previous_data['bid'] and 
                        ask == previous_data['ask'] and 
                        last == previous_data['last']):
                        # No change, wait for next event
                        await asyncio.sleep(0.01)  # Minimal sleep to prevent CPU spin
                        continue
                    
                    # Update previous data
                    previous_data = {'bid': bid, 'ask': ask, 'last': last}
                    
                    # Apply Bid/Ask logic if enabled
                    if use_bid_ask_logic and config.USE_BID_FOR_ENTRY and config.USE_ASK_FOR_TRACKING:
                        if is_entry:
                            # First tick: Use BID price for entry
                            entry_price = bid if bid > 0 else (last if last > 0 else ask)
                            current_price = entry_price
                            is_entry = False
                            logger.info(f"📍 Entry price (BID): ${entry_price:.2f}")
                        else:
                            # Subsequent ticks: Use ASK price for tracking
                            current_price = ask if ask > 0 else (last if last > 0 else bid)
                    else:
                        # Default: Use ASK price for both entry and tracking
                        current_price = ask if ask > 0 else (last if last > 0 else bid)
                        if is_entry:
                            entry_price = current_price
                            is_entry = False
                    
                    price_data = {
                        'bid': bid,
                        'ask': ask,
                        'last': last,
                        'current_price': current_price,  # The price to use (BID for entry, ASK for tracking)
                        'entry_price': entry_price,
                        'is_entry': is_entry,
                        'timestamp': datetime.now()
                    }
                    
                    # ⚡ INSTANT CALLBACK - no delay!
                    if callback and (bid > 0 or ask > 0 or last > 0):
                        await callback(price_data)
                    
                    # Reset error counter on success
                    consecutive_errors = 0
                    
                    # Minimal sleep to prevent CPU overload
                    await asyncio.sleep(0.01)
                    
                except Exception as inner_e:
                    consecutive_errors += 1
                    logger.error(f"❌ Error in tracking loop: {inner_e} (error {consecutive_errors}/{max_consecutive_errors})")
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"❌ Too many consecutive errors ({consecutive_errors}) - raising exception")
                        raise
                    
                    # Wait a bit before continuing
                    await asyncio.sleep(1)
            
        except asyncio.CancelledError:
            logger.info("✅ Tracking cancelled")
            raise  # Re-raise to propagate cancellation
            
        except Exception as e:
            logger.error(f"❌ Fatal error tracking price: {e}")
            import traceback
            traceback.print_exc()
            raise  # Re-raise to trigger retry in _track_position
            
        finally:
            if ticker:
                try:
                    self.ib.cancelMktData(ticker)
                except:
                    pass
