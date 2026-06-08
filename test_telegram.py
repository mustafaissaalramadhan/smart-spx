"""
اختبار قنوات التيليجرام
"""
from telegram_manager import TelegramManager
from database import DatabaseManager
import config

print("\n" + "="*60)
print("📱 اختبار قنوات التيليجرام")
print("="*60 + "\n")

# إنشاء مدير التيليجرام
telegram = TelegramManager()

# عرض القنوات المحملة
print(f"\n📊 القنوات المُحمّلة:")
for symbol, channels in telegram.channels.items():
    print(f"\n  الرمز: {symbol}")
    for ch in channels:
        print(f"    - الاسم: {ch['name']}")
        print(f"      Token: {ch['token'][:20]}...")
        print(f"      Chat ID: {ch['chat_id']}")

# اختبار الاتصال
print(f"\n{'='*60}")
print("🧪 اختبار إرسال رسالة...")
print("="*60)

success = telegram.test_connection()

if success:
    print("\n✅ النجاح! تم إرسال رسائل اختبار بنجاح.")
else:
    print("\n❌ فشل! لم يتم إرسال الرسائل.")
    print("\nتحقق من:")
    print("  1. التوكن صحيح")
    print("  2. Chat ID صحيح")
    print("  3. البوت مضاف للقناة كـ Admin")
    print("  4. اتصال الإنترنت يعمل")

# عرض قائمة القنوات في قاعدة البيانات
print(f"\n{'='*60}")
print("📋 القنوات في قاعدة البيانات:")
print("="*60)

db = DatabaseManager()
channels = db.get_all_telegram_channels()

if channels:
    for ch in channels:
        print(f"\n  ID: {ch['id']}")
        print(f"  الرمز: {ch['symbol']}")
        print(f"  الاسم: {ch['channel_name']}")
        print(f"  Token: {ch['token'][:20]}...")
        print(f"  Chat ID: {ch['chat_id']}")
        print(f"  نشط: {'نعم' if ch['active'] else 'لا'}")
else:
    print("\n  ❌ لا توجد قنوات في قاعدة البيانات!")
    print("\n  سيتم استخدام القناة الافتراضية من config.py:")
    print(f"    الرمز: {config.DEFAULT_SYMBOL}")
    print(f"    Token: {config.TELEGRAM_BOT_TOKEN[:20]}...")
    print(f"    Chat ID: {config.TELEGRAM_CHAT_ID}")

print("\n" + "="*60 + "\n")
