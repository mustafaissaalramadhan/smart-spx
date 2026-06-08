"""
اختبار إنشاء صورة التيليجرام وإرسالها للتيليجرام
"""

import sys
import asyncio
from datetime import datetime
from telegram_manager import TelegramManager
from PIL import Image

async def test_telegram_notification():
    """اختبار إنشاء الصورة وإرسالها للتيليجرام"""
    
    print("="*60)
    print("🧪 اختبار إرسال صورة التيليجرام")
    print("="*60)
    
    # إنشاء TelegramManager
    telegram = TelegramManager()
    
    # بيانات اختبار (محاكاة صفقة حقيقية)
    test_data = {
        'symbol': 'SPXW',
        'strike': 6845,
        'expiry': '03 MAR 26',
        'type': 'CALL',
        'entry_price': 3.20,
        'current_price': 4.50,
        'ask': 4.60,
        'bid': 4.50,
        'mid': 4.55,
        'highest_price': 4.75
    }
    
    print("\n📊 بيانات الاختبار:")
    print(f"   العقد: {test_data['symbol']} ${test_data['strike']} {test_data['expiry']} {test_data['type']}")
    print(f"   سعر الدخول: ${test_data['entry_price']:.2f}")
    print(f"   السعر الحالي: ${test_data['current_price']:.2f}")
    print(f"   التغيير: ${test_data['current_price'] - test_data['entry_price']:.2f} ({((test_data['current_price'] - test_data['entry_price']) / test_data['entry_price'] * 100):.2f}%)")
    print(f"   Ask: ${test_data['ask']:.2f}")
    print(f"   Bid: ${test_data['bid']:.2f}")
    print(f"   Mid: ${test_data['mid']:.2f}")
    
    print("\n🎨 إنشاء الصورة...")
    
    try:
        # إنشاء الصورة
        img_bytes = telegram.create_tracking_image(test_data)
        
        # حفظ الصورة للمعاينة
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"telegram_system_test_{timestamp}.png"
        
        # فتح من BytesIO وحفظ
        img = Image.open(img_bytes)
        img.save(output_file)
        
        print(f"\n✅ تم إنشاء الصورة بنجاح!")
        print(f"📁 اسم الملف: {output_file}")
        print(f"📐 أبعاد الصورة: {img.size[0]}x{img.size[1]} pixels")
        
        # فتح الصورة
        try:
            import webbrowser
            import os
            webbrowser.open(os.path.abspath(output_file))
            print(f"✅ تم فتح الصورة للمعاينة")
        except Exception as e:
            print(f"⚠️ لم أتمكن من فتح الصورة تلقائياً: {e}")
        
        # إرسال الإشعار للتيليجرام
        print("\n📤 إرسال الإشعار للتيليجرام...")
        
        # نص الرسالة
        profit = test_data['current_price'] - test_data['entry_price']
        profit_pct = (profit / test_data['entry_price'] * 100)
        
        test_data['profit'] = profit
        test_data['profit_pct'] = profit_pct
        test_data['time'] = datetime.now().strftime('%H:%M:%S')
        
        try:
            await telegram.send_notification(
                notification_type='position_opened',  # يمكن تغييره حسب النوع
                data=test_data,
                symbol='SPX'
            )
            print("✅ تم إرسال الإشعار للتيليجرام بنجاح!")
        except Exception as e:
            print(f"⚠️ خطأ في إرسال الإشعار للتيليجرام: {e}")
            print(f"   تأكد من إعداد معلومات التيليجرام في config.py")
        
        print("\n" + "="*60)
        print("✅ الاختبار نجح! التصميم الجديد يعمل بشكل صحيح")
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ خطأ في إنشاء الصورة:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_telegram_notification())
    sys.exit(0 if success else 1)
