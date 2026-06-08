"""
Simple Watchlist System
نظام مراقبة مبسط - جلب 5 عقود في كل دفعة
"""
import asyncio
from ib_insync import IB, Option, Index
from datetime import datetime
import config
import logging

logger = logging.getLogger(__name__)


class SimpleWatchlistManager:
    """مدير قائمة المراقبة المبسط"""
    
    def __init__(self):
        """تهيئة المدير"""
        self.price_connection = None  # اتصال جلب السعر
        self.data_connection = None   # اتصال جلب العقود
        self.current_price = {}       # {symbol: price}
        self.active_contracts = {}    # {symbol: {option_type: [contracts]}}
        self.is_running = False
        
    async def start(self):
        """بدء النظام - إنشاء اتصالين"""
        try:
            # اتصال 1: جلب السعر فقط
            self.price_connection = IB()
            await self.price_connection.connectAsync(
                config.IBKR_HOST,
                config.IBKR_PORT,
                clientId=100,  # Client ID ثابت للسعر
                readonly=True,
                timeout=20
            )
            logger.info("✅ Price connection established (Client ID: 100)")
            
            # اتصال 2: جلب العقود
            self.data_connection = IB()
            await self.data_connection.connectAsync(
                config.IBKR_HOST,
                config.IBKR_PORT,
                clientId=101,  # Client ID ثابت للبيانات
                readonly=True,
                timeout=20
            )
            logger.info("✅ Data connection established (Client ID: 101)")
            
            # استخدام delayed data (مجاني)
            self.price_connection.reqMarketDataType(3)
            self.data_connection.reqMarketDataType(3)
            
            self.is_running = True
            logger.info("✅ Simple Watchlist System started")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start watchlist system: {e}")
            return False
    
    async def stop(self):
        """إيقاف النظام"""
        self.is_running = False
        
        if self.price_connection and self.price_connection.isConnected():
            self.price_connection.disconnect()
            logger.info("🔌 Price connection disconnected")
        
        if self.data_connection and self.data_connection.isConnected():
            self.data_connection.disconnect()
            logger.info("🔌 Data connection disconnected")
    
    async def get_current_price(self, symbol: str) -> float:
        """جلب السعر الحالي من الاتصال المخصص"""
        try:
            if not self.price_connection or not self.price_connection.isConnected():
                logger.error("❌ Price connection not available")
                return 0
            
            # إنشاء contract حسب الرمز
            if symbol == 'SPX':
                contract = Index('SPX', 'CBOE')
            elif symbol == 'NDX':
                contract = Index('NDX', 'CBOE')
            else:
                from ib_insync import Stock
                contract = Stock(symbol, 'SMART', 'USD')
            
            # تأهيل العقد
            qualified = await self.price_connection.qualifyContractsAsync(contract)
            if not qualified:
                logger.error(f"❌ Could not qualify {symbol} contract")
                return 0
            
            # طلب البيانات
            ticker = self.price_connection.reqMktData(qualified[0])
            await asyncio.sleep(1)
            
            # جلب السعر
            price = ticker.last if ticker.last and ticker.last > 0 else ticker.close
            
            # إلغاء الاشتراك
            self.price_connection.cancelMktData(qualified[0])
            
            if price and price > 0:
                self.current_price[symbol] = price
                logger.debug(f"✅ {symbol} price: ${price:.2f}")
                return price
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ Error getting {symbol} price: {e}")
            return 0
    
    async def fetch_contracts_batch(
        self, 
        symbol: str, 
        expiry: str, 
        option_type: str,
        start_strike: int,
        batch_size: int = 5
    ):
        """
        جلب دفعة من العقود (5 عقود)
        
        Args:
            symbol: الرمز (SPX, NDX, SPY, QQQ)
            expiry: تاريخ الانتهاء (YYYYMMDD)
            option_type: نوع العقد (CALL/PUT)
            start_strike: سعر التنفيذ الأول
            batch_size: عدد العقود في الدفعة (افتراضي 5)
        
        Returns:
            قائمة بالعقود مع أسعارها
        """
        try:
            if not self.data_connection or not self.data_connection.isConnected():
                logger.error("❌ Data connection not available")
                return []
            
            # تحديد مسافة strikes حسب الرمز
            strike_interval = config.STRIKE_INTERVALS.get(symbol, 5)
            
            # إنشاء strikes للدفعة
            strikes = [start_strike + (i * strike_interval) for i in range(batch_size)]
            
            # حرف نوع العقد (C أو P)
            right = 'C' if option_type == 'CALL' else 'P'
            
            # إنشاء العقود
            trading_class = 'SPXW' if symbol == 'SPX' else None
            contracts = [
                Option(symbol, expiry, strike, right, 'CBOE', tradingClass=trading_class)
                for strike in strikes
            ]
            
            # تأهيل العقود
            qualified = await self.data_connection.qualifyContractsAsync(*contracts)
            
            if not qualified:
                logger.warning(f"⚠️ No contracts qualified for {symbol} {option_type} batch starting at {start_strike}")
                return []
            
            # طلب بيانات السوق لجميع العقود
            tickers = []
            for contract in qualified:
                if contract and contract.conId:
                    ticker = self.data_connection.reqMktData(contract)
                    tickers.append((contract, ticker))
            
            # انتظار البيانات
            await asyncio.sleep(1.5)
            
            # جمع النتائج
            results = []
            for contract, ticker in tickers:
                bid = ticker.bid if ticker.bid and ticker.bid > 0 else 0
                ask = ticker.ask if ticker.ask and ticker.ask > 0 else 0
                last = ticker.last if ticker.last and ticker.last > 0 else 0
                
                results.append({
                    'contract': contract,
                    'strike': contract.strike,
                    'bid': bid,
                    'ask': ask,
                    'last': last,
                    'right': contract.right
                })
                
                # إلغاء الاشتراك
                self.data_connection.cancelMktData(contract)
            
            logger.info(f"✅ Fetched {len(results)} contracts for {symbol} {option_type} (strikes {strikes[0]}-{strikes[-1]})")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error fetching batch for {symbol} {option_type}: {e}")
            return []
    
    async def find_contracts_in_range(
        self,
        symbol: str,
        expiry: str,
        option_type: str,
        price_min: float = None,
        price_max: float = None,
        max_batches: int = 20
    ):
        """
        البحث عن عقود ضمن النطاق السعري
        
        Strategy:
            1. جلب 5 عقود في كل دفعة
            2. فحص إذا كانت ضمن النطاق ($1-$7)
            3. إذا وُجدت → إرجاعها
            4. إذا لم توجد → جلب الدفعة التالية
            5. الاستمرار حتى إيجاد عقود أو الوصول للحد الأقصى
        
        Returns:
            قائمة بالعقود ضمن النطاق (مرتبة حسب Bid الأعلى)
        """
        try:
            # استخدام النطاق من config إذا لم يُحدد
            # ✅ للبحث والمراقبة - نستخدم MONITORING_RANGE
            if price_min is None:
                price_min = config.MONITORING_RANGE_MIN
            if price_max is None:
                price_max = config.MONITORING_RANGE_MAX
            
            logger.info(f"🔍 Searching for {symbol} {option_type} contracts in range ${price_min:.2f}-${price_max:.2f} (MONITORING)")
            
            # جلب السعر الحالي
            current_price = await self.get_current_price(symbol)
            if current_price <= 0:
                logger.error("❌ Could not get current price")
                return []
            
            logger.info(f"📊 Current {symbol} price: ${current_price:.2f}")
            
            # حساب نقطة البدء
            strike_interval = config.STRIKE_INTERVALS.get(symbol, 5)
            start_offset = config.SEARCH_START_OFFSET.get(symbol, 4)
            
            # ATM strike (أقرب strike للسعر الحالي)
            atm_strike = int(round(current_price / strike_interval) * strike_interval)
            
            if option_type == 'CALL':
                # CALL: نبدأ من ATM + offset صعوداً (للحصول على عقود أرخص - OTM)
                start_strike = atm_strike + (start_offset * strike_interval)
                logger.info(f"🎯 CALL: Starting at {start_strike} (ATM {atm_strike} + {start_offset} strikes)")
            else:
                # PUT: نبدأ من ATM - offset نزولاً (للحصول على عقود أرخص - OTM)
                start_strike = atm_strike - (start_offset * strike_interval)
                logger.info(f"🎯 PUT: Starting at {start_strike} (ATM {atm_strike} - {start_offset} strikes)")
            
            # البحث في دفعات
            all_contracts_in_range = []
            
            for batch_num in range(max_batches):
                # حساب strike البداية لهذه الدفعة
                if option_type == 'CALL':
                    batch_start_strike = start_strike + (batch_num * 5 * strike_interval)
                else:
                    batch_start_strike = start_strike - (batch_num * 5 * strike_interval)
                
                logger.info(f"📦 Batch {batch_num + 1}/{max_batches}: Starting at strike {batch_start_strike}")
                
                # جلب الدفعة
                batch_contracts = await self.fetch_contracts_batch(
                    symbol, expiry, option_type, batch_start_strike, batch_size=5
                )
                
                if not batch_contracts:
                    logger.warning(f"⚠️ No contracts in batch {batch_num + 1}")
                    continue
                
                # فحص العقود في هذه الدفعة
                batch_in_range = []
                for contract_data in batch_contracts:
                    ask = contract_data['ask']
                    bid = contract_data['bid']
                    
                    # فحص النطاق (حسب Ask)
                    if ask > 0 and price_min <= ask <= price_max:
                        batch_in_range.append(contract_data)
                        logger.info(f"  ✓ Strike {contract_data['strike']}: Bid ${bid:.2f}, Ask ${ask:.2f} ✅ IN RANGE")
                    else:
                        logger.debug(f"  ✗ Strike {contract_data['strike']}: Ask ${ask:.2f} ❌ OUT OF RANGE")
                
                # إضافة العقود المناسبة
                all_contracts_in_range.extend(batch_in_range)
                
                # نتوقف إذا وجدنا 10 عقود على الأقل
                if len(all_contracts_in_range) >= 10:
                    logger.info(f"✅ Found {len(all_contracts_in_range)} contracts in range - stopping search")
                    break
                
                # إذا لم نجد عقود في هذه الدفعة، نستمر للدفعة التالية
                if not batch_in_range:
                    logger.debug(f"⚠️ No contracts in range in batch {batch_num + 1}, continuing...")
            
            # إذا لم نجد عقود كافية (أقل من 3)، نعيد المحاولة بنطاق أوسع
            if len(all_contracts_in_range) < 3 and max_batches < 50:
                logger.warning(f"⚠️ Found only {len(all_contracts_in_range)} contracts, searching with extended range...")
                # توسيع البحث (50 دفعة = 250 عقد محتمل)
                return await self.find_contracts_in_range(
                    symbol, expiry, option_type, price_min, price_max, max_batches=50
                )
            
            # ترتيب العقود حسب Bid (الأعلى أولاً)
            all_contracts_in_range.sort(key=lambda x: x['bid'], reverse=True)
            
            logger.info(f"✅ Total contracts found in range: {len(all_contracts_in_range)}")
            
            # حفظ في الذاكرة
            if symbol not in self.active_contracts:
                self.active_contracts[symbol] = {}
            self.active_contracts[symbol][option_type] = all_contracts_in_range
            
            return all_contracts_in_range
            
        except Exception as e:
            logger.error(f"❌ Error finding contracts in range: {e}", exc_info=True)
            return []
    
    async def update_contracts_prices(self, symbol: str, option_type: str):
        """
        تحديث أسعار العقود الموجودة بالفعل
        
        Args:
            symbol: الرمز
            option_type: نوع العقد (CALL/PUT)
        
        Returns:
            قائمة بالعقود المحدثة
        """
        try:
            # التحقق من وجود عقود نشطة
            if symbol not in self.active_contracts or option_type not in self.active_contracts[symbol]:
                logger.warning(f"⚠️ No active contracts for {symbol} {option_type}")
                return []
            
            contracts_to_update = self.active_contracts[symbol][option_type]
            
            if not contracts_to_update:
                return []
            
            logger.info(f"🔄 Updating prices for {len(contracts_to_update)} {symbol} {option_type} contracts")
            
            # طلب بيانات محدثة
            tickers = []
            for contract_data in contracts_to_update:
                contract = contract_data['contract']
                ticker = self.data_connection.reqMktData(contract)
                tickers.append((contract_data, ticker))
            
            # انتظار البيانات
            await asyncio.sleep(1.5)
            
            # تحديث الأسعار
            updated_contracts = []
            for contract_data, ticker in tickers:
                bid = ticker.bid if ticker.bid and ticker.bid > 0 else 0
                ask = ticker.ask if ticker.ask and ticker.ask > 0 else 0
                last = ticker.last if ticker.last and ticker.last > 0 else 0
                
                # تحديث البيانات
                contract_data['bid'] = bid
                contract_data['ask'] = ask
                contract_data['last'] = last
                
                updated_contracts.append(contract_data)
                
                # إلغاء الاشتراك
                self.data_connection.cancelMktData(contract_data['contract'])
            
            # حفظ العقود المحدثة
            self.active_contracts[symbol][option_type] = updated_contracts
            
            logger.info(f"✅ Updated {len(updated_contracts)} contracts")
            return updated_contracts
            
        except Exception as e:
            logger.error(f"❌ Error updating contracts prices: {e}", exc_info=True)
            return []
    
    def get_active_contracts(self, symbol: str, option_type: str):
        """الحصول على العقود النشطة من الذاكرة"""
        if symbol in self.active_contracts and option_type in self.active_contracts[symbol]:
            return self.active_contracts[symbol][option_type]
        return []
