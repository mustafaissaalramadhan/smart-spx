"""
اختبار جميع أنواع إشعارات التيليجرام
"""
import asyncio
from telegram_manager import TelegramManager
from datetime import datetime

async def test_all_notifications():
    """Test all notification types"""
    telegram = TelegramManager()
    
    print("\n" + "="*60)
    print("🧪 اختبار جميع أنواع الإشعارات")
    print("="*60 + "\n")
    
    # Define test symbol
    symbol = 'SPX'
    
    # Common expiry for all tests
    expiry = datetime.now().strftime('%d%b%y').upper()  # Format: 05MAR26
    
    # 1. Position Opened
    print("\n1️⃣ اختبار: فتح صفقة (position_opened)")
    await telegram.send_notification('position_opened', {
        'symbol': symbol,
        'type': 'CALL',
        'contract': 'SPX 6000 CALL',
        'strike': 6000,
        'entry_price': 50.00,
        'current_price': 50.00,
        'bid': 49.50,
        'ask': 50.50,
        'expiry': expiry,
        'emoji': '📈',
        'channel_link': 'https://t.me/GeneralSmatrPro',
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }, symbol)
    
    await asyncio.sleep(2)
    
    # 2. New High
    print("\n2️⃣ اختبار: أعلى سعر جديد (new_high)")
    profit = 0.10  # Price difference
    profit_dollars = profit * 100  # 10$
    profit_sar = profit_dollars * 3.75  # 37.5 SAR
    
    await telegram.send_notification('new_high', {
        'symbol': symbol,
        'type': 'CALL',
        'contract': 'SPX 6000 CALL',
        'strike': 6000,
        'entry_price': 50.00,
        'current_price': 50.10,
        'highest_price': 50.10,
        'bid': 50.05,
        'ask': 50.15,
        'last': 50.10,
        'profit': profit,
        'profit_pct': 0.2,
        'profit_dollars': profit_dollars,
        'profit_sar': profit_sar,
        'expiry': expiry,
        'emoji': '📈',
        'channel_link': 'https://t.me/GeneralSmatrPro',
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }, symbol)
    
    await asyncio.sleep(2)
    
    # 3. Profit Target Hit
    print("\n3️⃣ اختبار: ضرب الهدف (profit_target_hit)")
    await telegram.send_notification('profit_target_hit', {
        'symbol': symbol,
        'type': 'CALL',
        'contract': 'SPX 6000 CALL',
        'strike': 6000,
        'entry_price': 50.00,
        'exit_price': 100.00,
        'current_price': 100.00,
        'highest_price': 105.00,
        'pnl': 50.00,
        'profit_pct': 100.0,
        'profit_emoji': '✅',
        'bid': 99.50,
        'ask': 100.50,
        'expiry': expiry,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }, symbol)
    
    await asyncio.sleep(2)
    
    # 4. Stop Loss Hit
    print("\n4️⃣ اختبار: وقف الخسارة (stop_loss_hit)")
    await telegram.send_notification('stop_loss_hit', {
        'symbol': symbol,
        'type': 'CALL',
        'contract': 'SPX 6000 CALL',
        'strike': 6000,
        'entry_price': 50.00,
        'exit_price': 25.00,
        'current_price': 25.00,
        'highest_price': 52.00,
        'pnl': 25.00,
        'profit_pct': -50.0,
        'profit_emoji': '❌',
        'bid': 24.50,
        'ask': 25.50,
        'expiry': expiry,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }, symbol)
    
    await asyncio.sleep(2)
    
    # 5. Trailing Stop Hit
    print("\n5️⃣ اختبار: وقف الخسارة المتحرك (trailing_stop_hit)")
    await telegram.send_notification('trailing_stop_hit', {
        'symbol': symbol,
        'type': 'CALL',
        'contract': 'SPX 6000 CALL',
        'strike': 6000,
        'entry_price': 50.00,
        'exit_price': 80.00,
        'current_price': 80.00,
        'highest_price': 100.00,
        'pnl': 30.00,
        'profit_pct': 60.0,
        'profit_emoji': '✅',
        'drop_from_peak': 20.0,
        'bid': 79.50,
        'ask': 80.50,
        'expiry': expiry,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }, symbol)
    
    await asyncio.sleep(2)
    
    # 6. Capital Protection Hit
    print("\n6️⃣ اختبار: حماية رأس المال (capital_protection_hit)")
    await telegram.send_notification('capital_protection_hit', {
        'symbol': symbol,
        'type': 'CALL',
        'contract': 'SPX 6000 CALL',
        'strike': 6000,
        'entry_price': 50.00,
        'exit_price': 90.00,
        'current_price': 90.00,
        'highest_price': 110.00,
        'pnl': 40.00,
        'profit_pct': 80.0,
        'profit_emoji': '✅',
        'protection_level': 120.0,
        'bid': 89.50,
        'ask': 90.50,
        'expiry': expiry,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }, symbol)
    
    await asyncio.sleep(2)
    
    # 7. Position Closed (General)
    print("\n7️⃣ اختبار: إغلاق عام (position_closed)")
    await telegram.send_notification('position_closed', {
        'symbol': symbol,
        'type': 'CALL',
        'contract': 'SPX 6000 CALL',
        'strike': 6000,
        'entry_price': 50.00,
        'exit_price': 60.00,
        'current_price': 60.00,
        'highest_price': 65.00,
        'pnl': 10.00,
        'profit_pct': 20.0,
        'profit_emoji': '✅',
        'profit_status': 'ربح: +$10.00 (+20.0%)',
        'reason': 'إغلاق يدوي',
        'bid': 59.50,
        'ask': 60.50,
        'expiry': expiry,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }, symbol)
    
    await asyncio.sleep(2)
    
    # 8. Duplicate Prevented
    print("\n8️⃣ اختبار: منع التكرار (duplicate_prevented)")
    await telegram.send_notification('duplicate_prevented', {
        'symbol': symbol,
        'type': 'CALL',
        'strike': 6000,
        'reason': 'السترايك 6000 مفتوح بالفعل',
        'entry_price': 50.00,
        'current_price': 50.00,
        'bid': 49.50,
        'ask': 50.50,
        'expiry': expiry,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }, symbol)
    
    print("\n" + "="*60)
    print("✅ انتهى الاختبار - تحقق من قنوات التيليجرام!")
    print("="*60 + "\n")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_all_notifications())
