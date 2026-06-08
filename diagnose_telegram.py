"""
فحص شامل لنظام التيليجرام
يفحص القنوات المحملة ويرسل رسالة اختبار
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram_manager import TelegramManager
from database import DatabaseManager
import config
from datetime import datetime

print("\n" + "="*70)
print("🔍 فحص شامل لنظام التيليجرام")
print("="*70)

# 1. فحص قاعدة البيانات
print("\n" + "─"*70)
print("1️⃣  فحص قنوات التيليجرام في قاعدة البيانات")
print("─"*70)

db = DatabaseManager()
db_channels = db.get_all_telegram_channels()

print(f"\n📊 عدد القنوات المحفوظة: {len(db_channels)}")

if db_channels:
    for i, ch in enumerate(db_channels, 1):
        print(f"\n   قناة #{i}:")
        print(f"      الرمز: {ch['symbol']}")
        print(f"      الاسم: {ch.get('channel_name', 'N/A')}")
        print(f"      Token: {ch['token'][:25]}...")
        print(f"      Chat ID: {ch['chat_id']}")
        print(f"      نشطة: {'نعم' if ch.get('active', 1) else 'لا'}")
else:
    print("\n   ❌ لا توجد قنوات في قاعدة البيانات!")
    print("\n   💡 سيتم استخدام القناة الافتراضية من config.py:")
    print(f"      Token: {config.TELEGRAM_BOT_TOKEN[:25]}...")
    print(f"      Chat ID: {config.TELEGRAM_CHAT_ID}")

# 2. فحص تحميل القنوات في TelegramManager
print("\n" + "─"*70)
print("2️⃣  فحص تحميل القنوات في TelegramManager")
print("─"*70)

telegram = TelegramManager()

if telegram.channels:
    print(f"\n✅ تم تحميل القنوات بنجاح!")
    print(f"   عدد الرموز المحملة: {len(telegram.channels)}")
    
    for symbol, channel_list in telegram.channels.items():
        print(f"\n   📍 {symbol}:")
        for ch in channel_list:
            print(f"      - {ch['name']}")
            print(f"        Token: {ch['token'][:25]}...")
            print(f"        Chat ID: {ch['chat_id']}")
else:
    print("\n   ❌ لم يتم تحميل أي قنوات!")

# 3. اختبار إرسال رسالة
print("\n" + "─"*70)
print("3️⃣  اختبار إرسال رسالة")
print("─"*70)

test_data = {
    'symbol': 'SPX',
    'type': 'CALL',
    'contract': 'SPX 6000 CALL',
    'strike': 6000,
    'entry_price': 50.00,
    'current_price': 50.00,
    'bid': 49.50,
    'ask': 50.50,
    'expiry': datetime.now().strftime('%d%b%y').upper(),
    'emoji': '📈',
    'channel_link': 'https://t.me/GeneralSmatrPro',
    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
}

print("\n📤 محاولة إرسال رسالة اختبار...")
print(f"   النوع: position_opened")
print(f"   الرمز: SPX")
print(f"   البيانات: {test_data}")

# Test with None async_loop (simulating manual trade without system running)
telegram.send_notification_sync('position_opened', test_data, 'SPX', async_loop=None)

print("\n" + "="*70)
print("✅ انتهى الفحص!")
print("\n💡 تحقق من قناة التيليجرام - هل وصلت الرسالة؟")
print("\nإذا لم تصل:")
print("  1. تأكد من التوكن صحيح")
print("  2. تأكد من Chat ID صحيح")
print("  3. تأكد من البوت Admin في القناة")
print("  4. راجع الرسائل أعلاه لمعرفة الخطأ")
print("="*70 + "\n")
