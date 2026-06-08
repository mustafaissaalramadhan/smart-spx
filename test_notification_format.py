"""
اختبار تنسيق الإشعارات - التأكد من جميع المتغيرات موجودة
"""
import json

# تحميل النصوص
with open('telegram_texts.json', 'r', encoding='utf-8') as f:
    texts = json.load(f)

# بيانات تجريبية
test_data = {
    'symbol': 'SPX',
    'type': 'PUT',
    'strike': 6710.0,
    'entry_price': 3.30,
    'exit_price': 3.70,
    'profit_emoji': '✅',
    'profit_dollars': 40.0,
    'profit_sar': 150.0,
    'channel_link': 'https://t.me/SPXSmartPro'
}

print("=" * 80)
print("🧪 اختبار تنسيق الإشعارات")
print("=" * 80)

# اختبار كل نوع إشعار إغلاق
notification_types = [
    'position_closed',
    'profit_target_hit',
    'stop_loss_hit',
    'trailing_stop_hit',
    'capital_protection_hit'
]

for notif_type in notification_types:
    print(f"\n{'='*80}")
    print(f"📋 {notif_type}")
    print("=" * 80)
    
    if notif_type in texts:
        template = texts[notif_type]
        
        try:
            # محاولة تنسيق النص
            formatted = template.format(**test_data)
            print("✅ نجح التنسيق!")
            print("\n" + formatted)
        except KeyError as e:
            print(f"❌ مفتاح ناقص: {e}")
            # البحث عن المفاتيح المطلوبة
            import re
            required_keys = re.findall(r'\{(\w+)', template)
            print(f"📝 المفاتيح المطلوبة: {required_keys}")
            missing = [k for k in required_keys if k not in test_data]
            print(f"⚠️ المفاتيح الناقصة: {missing}")
        except Exception as e:
            print(f"❌ خطأ: {e}")
    else:
        print(f"⚠️ نوع الإشعار غير موجود في telegram_texts.json")

print("\n" + "=" * 80)
print("✅ انتهى الاختبار")
print("=" * 80)
