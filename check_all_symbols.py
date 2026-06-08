"""
فحص إعدادات إدارة المخاطرة وقنوات التيليجرام لجميع الرموز
"""
from database import DatabaseManager
from telegram_manager import TelegramManager

db = DatabaseManager()

print("=" * 80)
print("📊 إعدادات إدارة المخاطرة لجميع الرموز")
print("=" * 80)

symbols = ['SPX', 'SPY', 'NDX', 'QQQ']

for symbol in symbols:
    settings = db.get_risk_settings(symbol)
    print(f"\n{symbol}:")
    print(f"   Stop Loss: {settings['stop_loss']['type']} = {settings['stop_loss']['value']}")
    print(f"   Trailing Stop: {settings['trailing_stop']['type']} = {settings['trailing_stop']['value']}")
    print(f"   Capital Protection: {settings['capital_protection']['type']} = {settings['capital_protection']['value']}")
    print(f"   Profit Target: {settings['profit_target']['type']} = {settings['profit_target']['value']}")

print("\n" + "=" * 80)
print("📢 قنوات التيليجرام لجميع الرموز")
print("=" * 80)

telegram = TelegramManager()

for symbol in symbols:
    if symbol in telegram.channels:
        channels = telegram.channels[symbol]
        print(f"\n{symbol}: {len(channels)} قناة")
        for ch in channels:
            print(f"   - {ch['name']}")
    else:
        print(f"\n{symbol}: ❌ لا توجد قناة مخصصة")

print("\n" + "=" * 80)
print("✅ انتهى الفحص")
print("=" * 80)
