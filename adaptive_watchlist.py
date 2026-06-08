"""
Adaptive Watchlist System - Smart Group-Based Market Data Management
النظام الذكي لإدارة بيانات السوق باستخدام المجموعات المتكيفة

Features:
- Dynamic group fetching (unlimited groups until range found)
- Dedicated connection per group (no collision)
- Dual range system (monitoring $1-$7 + entry $3-$4)
- Symbol-specific optimization (SPY/QQQ: 1 group, SPX/NDX: 3-4 groups)
- Independent group updates (5-second intervals)
- Smart activation/deactivation based on price changes
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import config
from ibkr_client import IBKRClient

logger = logging.getLogger(__name__)


@dataclass
class GroupInfo:
    """معلومات المجموعة"""
    group_id: int
    strikes: List[float]
    data: List[Dict]
    active: bool
    last_update: Optional[datetime]
    connection: Optional[IBKRClient]
    update_task: Optional[asyncio.Task]


class PriceRangeManager:
    """إدارة النطاقات السعرية"""
    
    def __init__(self):
        self.monitoring_range = (config.MIN_OPTION_PRICE, config.MAX_OPTION_PRICE)
        self.entry_range = (3.0, 4.0)  # افتراضي للدخول
    
    def update_monitoring_range(self, min_price: float, max_price: float):
        """تحديث نطاق المتابعة"""
        self.monitoring_range = (min_price, max_price)
        logger.info(f"📊 Monitoring range updated: ${min_price}-${max_price}")
    
    def update_entry_range(self, min_price: float, max_price: float):
        """تحديث نطاق الدخول"""
        if min_price < self.monitoring_range[0] or max_price > self.monitoring_range[1]:
            logger.error("❌ Entry range must be within monitoring range!")
            return False
        
        self.entry_range = (min_price, max_price)
        logger.info(f"🎯 Entry range updated: ${min_price}-${max_price}")
        return True
    
    def is_in_monitoring_range(self, price: float) -> bool:
        """هل السعر ضمن نطاق المتابعة؟"""
        return self.monitoring_range[0] <= price <= self.monitoring_range[1]
    
    def is_in_entry_range(self, price: float) -> bool:
        """هل السعر ضمن نطاق الدخول؟"""
        return self.entry_range[0] <= price <= self.entry_range[1]


class AdaptiveWatchlistMaster:
    """المتحكم الرئيسي - Master Orchestrator"""
    
    def __init__(self, gui_callback=None):
        self.groups: Dict[str, Dict[str, Dict[int, GroupInfo]]] = {}
        self.range_mgr = PriceRangeManager()
        self.active_symbols = set()
        self.gui_callback = gui_callback
        self.connection_counter = 0
        self.max_connections = 8
        self.update_interval = 5  # ثوان
    
    def initialize_symbol(self, symbol: str):
        """تهيئة symbol جديد"""
        if symbol not in self.groups:
            self.groups[symbol] = {
                'CALL': {},
                'PUT': {}
            }
            logger.info(f"✅ Initialized {symbol} in adaptive watchlist")
    
    def calculate_smart_start_strike(self, symbol: str, current_price: float, option_type: str) -> float:
        """حساب strike البداية بذكاء"""
        interval = config.STRIKE_INTERVALS[symbol]
        
        if option_type == 'CALL':
            # CALL: ابدأ من 2 strikes فوق السعر
            start = current_price + (2 * interval)
        else:  # PUT
            # PUT: ابدأ من 2 strikes تحت السعر
            start = current_price - (2 * interval)
        
        # تقريب للـinterval الأقرب
        rounded = round(start / interval) * interval
        logger.info(f"📍 {symbol} {option_type}: Price=${current_price:.2f}, Start strike=${rounded:.2f}")
        
        return rounded
    
    def generate_group_strikes(self, start_strike: float, group_id: int, symbol: str, option_type: str) -> List[float]:
        """توليد strikes للمجموعة"""
        interval = config.STRIKE_INTERVALS[symbol]
        strikes = []
        
        # كل group = 5 عقود
        base_strike = start_strike + ((group_id - 1) * 5 * interval)
        
        for i in range(5):
            if option_type == 'CALL':
                strike = base_strike + (i * interval)
            else:  # PUT
                strike = base_strike - (i * interval)
            
            strikes.append(strike)
        
        return strikes
    
    async def fetch_group(self, symbol: str, option_type: str, group_id: int, 
                         strikes: List[float], connection: IBKRClient) -> List[Dict]:
        """جلب بيانات مجموعة محددة"""
        try:
            logger.info(f"📥 Fetching {symbol} {option_type} Group {group_id}: {len(strikes)} contracts")
            
            # جلب expiry
            expiry = await connection.get_expiry_date()
            
            # جلب العقود باستخدام الاتصال المخصص
            contracts_data = []
            
            for strike in strikes:
                # إنشاء العقد وجلب السعر
                contract_data = await connection.fetch_single_option(
                    symbol=symbol,
                    strike=strike,
                    expiry=expiry,
                    option_type=option_type
                )
                
                if contract_data:
                    contracts_data.append(contract_data)
            
            logger.info(f"✅ Group {group_id}: Got {len(contracts_data)}/{len(strikes)} contracts")
            return contracts_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching group {group_id}: {e}")
            return []
    
    async def create_dedicated_connection(self) -> IBKRClient:
        """إنشاء اتصال مخصص جديد"""
        if self.connection_counter >= self.max_connections:
            raise Exception(f"Max connections reached ({self.max_connections})!")
        
        self.connection_counter += 1
        client_id = self.connection_counter
        
        conn = IBKRClient(base_client_id=client_id)
        success = await conn.connect()
        
        if not success:
            raise Exception(f"Failed to create connection (clientId={client_id})")
        
        logger.info(f"🔌 Created dedicated connection: clientId={client_id}")
        return conn
    
    async def initial_discovery(self, symbol: str, option_type: str, current_price: float) -> List[int]:
        """
        المرحلة الأولى: اكتشاف المجموعات المستهدفة
        يجلب groups حتى إيجاد النطاق (غير محدود)
        """
        logger.info(f"🔍 Starting discovery for {symbol} {option_type} @ ${current_price:.2f}")
        
        self.initialize_symbol(symbol)
        
        start_strike = self.calculate_smart_start_strike(symbol, current_price, option_type)
        found_groups = []
        group_id = 1
        max_groups = 20  # safety limit
        
        while group_id <= max_groups:
            # توليد strikes للمجموعة
            strikes = self.generate_group_strikes(start_strike, group_id, symbol, option_type)
            
            # إنشاء اتصال مخصص لهذه المجموعة
            try:
                connection = await self.create_dedicated_connection()
            except Exception as e:
                logger.error(f"❌ Cannot create more connections: {e}")
                break
            
            # جلب بيانات المجموعة
            data = await self.fetch_group(symbol, option_type, group_id, strikes, connection)
            
            if not data:
                logger.warning(f"⚠️ Group {group_id}: No data received")
                await connection.disconnect()
                break
            
            # حفظ المجموعة
            group_info = GroupInfo(
                group_id=group_id,
                strikes=strikes,
                data=data,
                active=False,
                last_update=datetime.now(),
                connection=connection,
                update_task=None
            )
            
            self.groups[symbol][option_type][group_id] = group_info
            
            # تحقق: هل توجد عقود ضمن نطاق المتابعة؟
            in_range = [c for c in data if self.range_mgr.is_in_monitoring_range(c.get('ask', 0))]
            
            if in_range:
                found_groups.append(group_id)
                logger.info(f"🎯 Group {group_id}: Found {len(in_range)} contracts in monitoring range")
            
            # شروطالتوقف
            # 1. وجدنا 2-3 groups ضمن النطاق
            if len(found_groups) >= 2:
                logger.info(f"✅ Discovery complete: Found {len(found_groups)} groups with target range")
                break
            
            # 2. الأسعار أصبحت صفرية أو قريبة من الصفر
            avg_price = sum(c.get('ask', 0) for c in data) / len(data) if data else 0
            if avg_price < 0.1:
                logger.info(f"🛑 Prices too low (avg=${avg_price:.2f}) - stopping discovery")
                break
            
            # 3. الأسعار خرجت من النطاق تماماً (للأسفل)
            max_price = max((c.get('ask', 0) for c in data), default=0)
            if max_price < self.range_mgr.monitoring_range[0]:
                logger.info(f"🛑 All prices below monitoring range - stopping")
                break
            
            group_id += 1
        
        if not found_groups:
            logger.warning(f"⚠️ No groups found with contracts in range ${self.range_mgr.monitoring_range}")
        
        return found_groups
    
    async def activate_group(self, symbol: str, option_type: str, group_id: int):
        """تفعيل مجموعة للتحديث المستمر"""
        group = self.groups[symbol][option_type].get(group_id)
        
        if not group:
            logger.error(f"❌ Group {group_id} not found for {symbol} {option_type}")
            return
        
        if group.active:
            logger.info(f"ℹ️ Group {group_id} already active")
            return
        
        group.active = True
        
        # بدء loop التحديث
        group.update_task = asyncio.create_task(
            self._group_update_loop(symbol, option_type, group_id)
        )
        
        logger.info(f"✅ Activated {symbol} {option_type} Group {group_id} (updates every {self.update_interval}s)")
    
    async def deactivate_group(self, symbol: str, option_type: str, group_id: int):
        """تعطيل مجموعة"""
        group = self.groups[symbol][option_type].get(group_id)
        
        if not group or not group.active:
            return
        
        group.active = False
        
        # إيقاف loop التحديث
        if group.update_task:
            group.update_task.cancel()
            try:
                await group.update_task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"🛑 Deactivated {symbol} {option_type} Group {group_id}")
    
    async def _group_update_loop(self, symbol: str, option_type: str, group_id: int):
        """Loop تحديث مستمر للمجموعة"""
        try:
            while True:
                await asyncio.sleep(self.update_interval)
                
                group = self.groups[symbol][option_type].get(group_id)
                if not group or not group.active:
                    break
                
                # تحديث البيانات
                new_data = await self.fetch_group(
                    symbol, option_type, group_id,
                    group.strikes, group.connection
                )
                
                if new_data:
                    group.data = new_data
                    group.last_update = datetime.now()
                    
                    # إرسال للـGUI
                    if self.gui_callback:
                        self.gui_callback(symbol, option_type, group_id, new_data)
                    
                    # مراقبة التغيرات
                    await self.monitor_price_changes(symbol, option_type, group_id)
                    
        except asyncio.CancelledError:
            logger.info(f"Update loop cancelled for group {group_id}")
        except Exception as e:
            logger.error(f"❌ Error in update loop for group {group_id}: {e}")
    
    async def monitor_price_changes(self, symbol: str, option_type: str, group_id: int):
        """مراقبة تغيرات الأسعار وتفعيل groups جديدة عند الحاجة"""
        group = self.groups[symbol][option_type].get(group_id)
        if not group:
            return
        
        # تحقق: كم عقد ضمن النطاق؟
        in_range = [c for c in group.data if self.range_mgr.is_in_monitoring_range(c.get('ask', 0))]
        
        if len(in_range) == 0:
            # ❌ لا توجد عقود ضمن النطاق - تفعيل المجموعة السابقة
            logger.warning(f"⚠️ Group {group_id}: No contracts in range - considering previous group")
            
            if group_id > 1:
                prev_group = self.groups[symbol][option_type].get(group_id - 1)
                if prev_group and not prev_group.active:
                    logger.info(f"🔄 Activating previous group {group_id - 1}")
                    await self.activate_group(symbol, option_type, group_id - 1)
            
            # تعطيل المجموعة الحالية
            await self.deactivate_group(symbol, option_type, group_id)
            
        elif len(in_range) < 3:
            # ⚠️ قليلة - تفعيل مجموعة إضافية
            logger.info(f"⚠️ Group {group_id}: Only {len(in_range)} contracts in range - activating adjacent group")
            
            # تفعيل المجموعة السابقة
            if group_id > 1:
                prev_group = self.groups[symbol][option_type].get(group_id - 1)
                if prev_group and not prev_group.active:
                    await self.activate_group(symbol, option_type, group_id - 1)
    
    def get_active_groups(self, symbol: str, option_type: str) -> List[int]:
        """الحصول على المجموعات النشطة"""
        if symbol not in self.groups:
            return []
        
        return [gid for gid, g in self.groups[symbol][option_type].items() if g.active]
    
    def get_all_active_data(self, symbol: str, option_type: str) -> List[Dict]:
        """الحصول على بيانات جميع المجموعات النشطة"""
        if symbol not in self.groups:
            return []
        
        all_data = []
        for group_id, group in self.groups[symbol][option_type].items():
            if group.active:
                all_data.extend(group.data)
        
        return all_data
    
    def get_entry_contracts(self, symbol: str, option_type: str) -> List[Dict]:
        """الحصول على العقود الصالحة للدخول (webhooks)"""
        all_data = self.get_all_active_data(symbol, option_type)
        
        entry_contracts = [
            c for c in all_data 
            if self.range_mgr.is_in_entry_range(c.get('ask', 0))
        ]
        
        return entry_contracts
    
    def is_symbol_initialized(self, symbol: str) -> bool:
        """Check if a symbol has been initialized in the adaptive watchlist"""
        return symbol in self.active_symbols
    
    async def start_symbol_watchlist(self, symbol: str, current_price: float):
        """بدء قائمة المراقبة لرمز معين"""
        logger.info(f"🚀 Starting adaptive watchlist for {symbol} @ ${current_price:.2f}")
        
        self.active_symbols.add(symbol)
        
        # اكتشاف وتفعيل CALL groups
        call_groups = await self.initial_discovery(symbol, 'CALL', current_price)
        for gid in call_groups:
            await self.activate_group(symbol, 'CALL', gid)
        
        # اكتشاف وتفعيل PUT groups
        put_groups = await self.initial_discovery(symbol, 'PUT', current_price)
        for gid in put_groups:
            await self.activate_group(symbol, 'PUT', gid)
        
        logger.info(f"✅ {symbol} watchlist started: CALL groups {call_groups}, PUT groups {put_groups}")
    
    async def stop_symbol_watchlist(self, symbol: str):
        """إيقاف قائمة المراقبة لرمز معين"""
        logger.info(f"🛑 Stopping adaptive watchlist for {symbol}")
        
        if symbol not in self.active_symbols:
            return
        
        self.active_symbols.remove(symbol)
        
        # تعطيل جميع المجموعات
        for option_type in ['CALL', 'PUT']:
            for group_id in list(self.groups[symbol][option_type].keys()):
                await self.deactivate_group(symbol, option_type, group_id)
                
                # قطع الاتصال
                group = self.groups[symbol][option_type][group_id]
                if group.connection:
                    await group.connection.disconnect()
        
        logger.info(f"✅ {symbol} watchlist stopped")
    
    async def cleanup(self):
        """تنظيف جميع الموارد"""
        logger.info("🧹 Cleaning up adaptive watchlist system...")
        
        for symbol in list(self.active_symbols):
            await self.stop_symbol_watchlist(symbol)
        
        logger.info("✅ Cleanup complete")
