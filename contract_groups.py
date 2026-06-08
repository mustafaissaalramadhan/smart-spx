"""
Smart Grouping System for Option Contracts
نظام المجموعات الذكي للعقود
"""
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import config

logger = logging.getLogger(__name__)


class ContractGroupManager:
    """
    إدارة المجموعات الذكية للعقود
    يقسم العقود لمجموعات من 5 ويدير التنقل الذكي بينها
    """
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.group_size = config.GROUP_SIZE  # 5 contracts per group
        self.strike_interval = config.STRIKE_INTERVALS.get(symbol, 5)
        self.contracts_before_price = config.CONTRACTS_BEFORE_PRICE  # 2 contracts before current price
        
        # Storage for fetched contracts
        self.all_contracts = []  # All fetched contracts
        self.groups = {}  # {group_num: [contracts]}
        self.current_underlying_price = None
        self.fetch_timestamp = None
        
    def calculate_start_strike(self, underlying_price: float, option_type: str) -> float:
        """
        حساب نقطة البداية للعقود (عقدين قبل السعر الحالي)
        
        Args:
            underlying_price: سعر السهم/المؤشر الحالي
            option_type: 'CALL' or 'PUT'
            
        Returns:
            Strike price للبداية
        """
        # Round to nearest strike interval
        rounded_price = round(underlying_price / self.strike_interval) * self.strike_interval
        
        if option_type == 'CALL':
            # CALL: ابدأ من عقدين قبل السعر ثم اذهب للأعلى
            # Example: Price=6010, Interval=5 → Start from 6000
            start_strike = rounded_price - (self.contracts_before_price * self.strike_interval)
        else:  # PUT
            # PUT: ابدأ من عقدين بعد السعر ثم اذهب للأسفل
            # Example: Price=6010, Interval=5 → Start from 6020
            start_strike = rounded_price + (self.contracts_before_price * self.strike_interval)
        
        logger.info(f"📍 {self.symbol} {option_type}: Price={underlying_price:.2f}, Start Strike={start_strike}")
        return start_strike
    
    def generate_strikes(self, start_strike: float, count: int, option_type: str) -> List[float]:
        """
        توليد قائمة الـStrikes بناءً على نقطة البداية
        
        Args:
            start_strike: Strike للبداية
            count: عدد العقود المطلوبة
            option_type: 'CALL' or 'PUT'
            
        Returns:
            قائمة الـStrikes
        """
        strikes = []
        
        if option_type == 'CALL':
            # CALL: تصاعدي
            strikes = [start_strike + (i * self.strike_interval) for i in range(count)]
        else:  # PUT
            # PUT: تنازلي
            strikes = [start_strike - (i * self.strike_interval) for i in range(count)]
        
        return strikes
    
    def organize_into_groups(self, contracts: List[Dict]) -> Dict[int, List[Dict]]:
        """
        تقسيم قائمة العقود إلى مجموعات من 5
        
        Args:
            contracts: قائمة العقود مع بياناتها
            
        Returns:
            {group_num: [contracts]} - مثال: {1: [5 contracts], 2: [5 contracts], ...}
        """
        self.all_contracts = contracts
        self.groups = {}
        
        for i in range(0, len(contracts), self.group_size):
            group_num = (i // self.group_size) + 1
            self.groups[group_num] = contracts[i:i + self.group_size]
        
        logger.info(f"📦 {self.symbol}: Organized {len(contracts)} contracts into {len(self.groups)} groups")
        self.fetch_timestamp = datetime.now()
        
        return self.groups
    
    def find_target_groups(self, price_range: Tuple[float, float], option_type: str) -> List[int]:
        """
        إيجاد المجموعات المستهدفة بناءً على نطاق السعر
        
        Args:
            price_range: (min_price, max_price) - نطاق السعر المطلوب
            option_type: 'CALL' or 'PUT'
            
        Returns:
            قائمة أرقام المجموعات المستهدفة
        """
        min_price, max_price = price_range
        target_groups = []
        
        for group_num, contracts in self.groups.items():
            # تحقق إذا أي عقد في المجموعة ضمن النطاق
            group_has_target = False
            
            for contract in contracts:
                bid = contract.get('bid', 0)
                ask = contract.get('ask', 0)
                price = (bid + ask) / 2 if bid and ask else (bid or ask or 0)
                
                if min_price <= price <= max_price:
                    group_has_target = True
                    break
            
            if group_has_target:
                target_groups.append(group_num)
        
        logger.info(f"🎯 {self.symbol} {option_type}: Target range ${min_price}-${max_price} → Groups {target_groups}")
        return target_groups
    
    def get_group_contracts(self, group_nums: List[int]) -> List[Dict]:
        """
        الحصول على عقود مجموعات محددة
        
        Args:
            group_nums: قائمة أرقام المجموعات
            
        Returns:
            قائمة العقود من المجموعات المحددة
        """
        result = []
        for group_num in group_nums:
            if group_num in self.groups:
                result.extend(self.groups[group_num])
        
        return result
    
    def navigate_to_adjacent_group(self, current_group: int, direction: str) -> Optional[int]:
        """
        التنقل للمجموعة المجاورة (Smart Navigation)
        
        Args:
            current_group: رقم المجموعة الحالية
            direction: 'up' للارتفاع، 'down' للانخفاض
            
        Returns:
            رقم المجموعة الجديدة أو None إذا لم توجد
        """
        if direction == 'up':
            next_group = current_group + 1
        else:  # down
            next_group = current_group - 1
        
        if next_group in self.groups:
            logger.info(f"🔄 {self.symbol}: Navigating from Group {current_group} → Group {next_group} (direction: {direction})")
            return next_group
        else:
            logger.warning(f"⚠️ {self.symbol}: Cannot navigate {direction} from Group {current_group} - no more groups")
            return None
    
    def needs_refetch(self, new_underlying_price: float, option_type: str) -> bool:
        """
        تحقق إذا كان يحتاج إعادة جلب العقود من IBKR
        
        Args:
            new_underlying_price: السعر الحالي للسهم/المؤشر
            option_type: 'CALL' or 'PUT'
            
        Returns:
            True إذا احتجنا إعادة جلب، False إذا المجموعات الحالية كافية
        """
        if not self.all_contracts or not self.groups:
            logger.info(f"📥 {self.symbol}: No contracts cached - need initial fetch")
            return True
        
        # Check if price moved outside our contract range
        strikes = [c['strike'] for c in self.all_contracts]
        min_strike = min(strikes)
        max_strike = max(strikes)
        
        if option_type == 'CALL':
            # CALL: إذا السعر أعلى من آخر strike، نحتاج إعادة جلب
            if new_underlying_price > max_strike:
                logger.info(f"📥 {self.symbol} CALL: Price ${new_underlying_price:.2f} > Max Strike ${max_strike} - need refetch")
                return True
        else:  # PUT
            # PUT: إذا السعر أقل من آخر strike، نحتاج إعادة جلب
            if new_underlying_price < min_strike:
                logger.info(f"📥 {self.symbol} PUT: Price ${new_underlying_price:.2f} < Min Strike ${min_strike} - need refetch")
                return True
        
        logger.info(f"✅ {self.symbol}: Current groups cover price ${new_underlying_price:.2f} - no refetch needed")
        return False
    
    def get_stats(self) -> Dict:
        """الحصول على إحصائيات المجموعات"""
        return {
            'symbol': self.symbol,
            'total_contracts': len(self.all_contracts),
            'total_groups': len(self.groups),
            'group_size': self.group_size,
            'strike_interval': self.strike_interval,
            'fetch_timestamp': self.fetch_timestamp,
            'current_price': self.current_underlying_price
        }
