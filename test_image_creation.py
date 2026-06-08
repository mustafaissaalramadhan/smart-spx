"""
اختبار إنشاء صورة التيليجرام
"""
import sys
from datetime import datetime

# Test data similar to what main_gui sends
test_data = {
    'symbol': 'SPXW',
    'type': 'CALL',
    'contract': 'SPXW 5800 14MAR25 CALL',
    'strike': 5800,
    'entry_price': 25.50,
    'current_price': 25.50,
    'bid': 25.45,
    'ask': 25.55,
    'expiry': datetime.now().strftime('%d%b%y').upper(),
    'emoji': '📈',
    'channel_link': 'https://t.me/GeneralSmatrPro',
    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
}

print("=" * 80)
print("🧪 اختبار إنشاء صورة التيليجرام")
print("=" * 80)

# Try to import TelegramManager
try:
    from telegram_manager import TelegramManager
    print("✅ تم استيراد TelegramManager بنجاح")
except Exception as e:
    print(f"❌ فشل استيراد TelegramManager: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Try to create instance
try:
    telegram = TelegramManager()
    print("✅ تم إنشاء instance من TelegramManager بنجاح")
except Exception as e:
    print(f"❌ فشل إنشاء TelegramManager: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Try to create image
print("\n" + "=" * 80)
print("🎨 محاولة إنشاء الصورة...")
print("=" * 80)
print(f"البيانات: {test_data}")
print()

try:
    image = telegram.create_tracking_image(test_data)
    print("\n✅✅✅ تم إنشاء الصورة بنجاح!")
    print(f"نوع الصورة: {type(image)}")
    print(f"حجم البيانات: {len(image.getvalue())} bytes")
    
    # Try to save it to file for inspection
    with open("test_image.png", "wb") as f:
        f.write(image.getvalue())
    print("✅ تم حفظ الصورة في test_image.png")
    
except Exception as e:
    print(f"\n❌❌❌ فشل إنشاء الصورة!")
    print(f"الخطأ: {e}")
    print("\nتفاصيل الخطأ:")
    import traceback
    traceback.print_exc()
    
    # Check PIL installation
    print("\n" + "=" * 80)
    print("🔍 فحص مكتبة PIL/Pillow:")
    print("=" * 80)
    try:
        from PIL import Image, ImageDraw, ImageFont
        print("✅ PIL/Pillow مثبتة")
        print(f"   مسار PIL: {Image.__file__}")
    except ImportError as ie:
        print(f"❌ PIL/Pillow غير مثبتة: {ie}")
        print("\n💡 يجب تثبيت Pillow:")
        print("   pip install Pillow")
    
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ نجح الاختبار - الصورة تعمل بشكل صحيح!")
print("=" * 80)
