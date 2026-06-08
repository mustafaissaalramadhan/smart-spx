"""
مثال لإنشاء صورة تيليجرام - تصميم مطابق للصورة المرجعية
"""
try:
    from PIL import Image, ImageDraw, ImageFont
    print("✅ مكتبة PIL متوفرة")
except ImportError:
    print("❌ مكتبة PIL غير مثبتة!")
    print("قم بتثبيتها عبر: pip install Pillow")
    input("اضغط Enter للخروج...")
    exit()

import os
from datetime import datetime

def create_background(width, height):
    """إنشاء خلفية تداول داكنة احترافية"""
    import random
    
    # خلفية أزرق داكن جداً (مثل الصورة 1)
    img = Image.new('RGB', (width, height), (5, 10, 25))
    draw = ImageDraw.Draw(img, 'RGBA')
    
    # إضافة تدرج خفيف للخلفية
    for y in range(height):
        alpha = int(20 * (y / height))
        color = (5, 10 + alpha, 25 + alpha)
        draw.rectangle([0, y, width, y+1], fill=color)
    
    # إضافة نجوم صغيرة
    random.seed(42)
    for _ in range(250):
        x = random.randint(0, width)
        y = random.randint(0, height)
        size = random.randint(1, 2)
        brightness = random.randint(80, 150)
        draw.ellipse([x, y, x+size, y+size], 
                    fill=(brightness, brightness, brightness + 20))
    
    # رسم شموع يابانية شفافة في الخلفية (جزء صغير في الأعلى)
    random.seed(123)
    candle_width = 10
    num_candles = 60
    start_x = 100
    spacing = (width - 200) / num_candles
    
    base_price = height // 3
    current_price = base_price
    
    for i in range(num_candles):
        x = start_x + i * spacing
        
        # حركة عشوائية
        change = random.randint(-30, 35)
        current_price += change
        current_price = max(50, min(height//2.5, current_price))
        
        candle_height = random.randint(15, 50)
        open_price = current_price
        close_price = current_price + random.randint(-candle_height, candle_height)
        
        high = max(open_price, close_price) + random.randint(3, 10)
        low = min(open_price, close_price) - random.randint(3, 10)
        
        # لون شفاف جداً
        if close_price > open_price:
            candle_color = (0, 180, 90, 40)  # أخضر شفاف
        else:
            candle_color = (255, 60, 60, 40)  # أحمر شفاف
        
        # رسم الفتيل
        wick_x = x + candle_width // 2
        draw.line([wick_x, high, wick_x, low], 
                 fill=(80, 100, 130, 60), width=1)
        
        # رسم جسم الشمعة
        top = min(open_price, close_price)
        bottom = max(open_price, close_price)
        draw.rectangle([x, top, x + candle_width, bottom], 
                      fill=candle_color, outline=candle_color)
    
    # خطوط منحنية شفافة (moving averages)
    random.seed(456)
    for line_num in range(2):
        points = []
        y_offset = height // 3 + random.randint(-50, 50)
        
        for x in range(0, width, 15):
            y = y_offset + random.randint(-20, 20)
            y = max(80, min(height // 2, y))
            points.append((x, y))
            y_offset = y
        
        line_color = (40, 100, 180, 30) if line_num == 0 else (60, 80, 140, 25)
        
        if len(points) > 1:
            draw.line(points, fill=line_color, width=2)
    
    return img

def create_telegram_image(background_path=None, data=None):
    """إنشاء صورة تيليجرام - تصميم نظيف بصندوق واحد فقط"""
    
    # بيانات افتراضية للمثال
    if data is None:
        data = {
            'price': 4.50,
            'change': 1.30,
            'percent': 40.62,
            'ask': 4.60,
            'bid': 4.50,
            'mid': 4.55
        }
    
    # إعدادات الصورة
    width = 1024
    height = 600  # أقصر لأن ليس لدينا عنوان في الأعلى
    
    # إنشاء أو تحميل الخلفية
    if background_path and os.path.exists(background_path):
        print(f"📂 تحميل الخلفية من: {background_path}")
        img = Image.open(background_path).resize((width, height))
        print(f"✅ تم تحميل الخلفية")
    else:
        print("🎨 إنشاء خلفية تداول...")
        img = create_background(width, height)
        print(f"✅ تم إنشاء الخلفية")
    
    # الألوان - فسفورية مشرقة وبارزة
    text_white = (255, 255, 255)
    text_cyan = (0, 255, 200)        # أخضر فسفوري مشرق للسعر الرئيسي
    text_green = (50, 255, 100)      # أخضر فسفوري للـ Change/Percent
    text_red = (255, 70, 120)        # أحمر فسفوري ساطع للـ Ask
    text_blue = (120, 220, 255)      # أزرق فسفوري ساطع للـ Bid
    text_gray = (240, 240, 255)      # رمادي مضيء ساطع للـ Mid
    box_bg = (15, 30, 60, 200)       # خلفية الصندوق شفافة
    border_color = (50, 80, 120)     # لون الحدود
    
    # إنشاء layer للرسم
    draw = ImageDraw.Draw(img, 'RGBA')
    
    # محاولة تحميل الخطوط
    try:
        font_huge = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 110)
        font_large = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 45)
        font_medium = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 38)
        font_small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 32)
    except:
        font_huge = ImageFont.load_default()
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # ═══════════════════════════════════════════════════════════════
    # الصندوق الرئيسي
    # ═══════════════════════════════════════════════════════════════
    
    box_x = 60
    box_y = 150  # في الوسط تقريباً
    box_width = 900
    box_height = 300
    
    # عنوان العقد أعلى المستطيل مباشرة
    contract_title = "SPXW $6845 03 MAR 26 CALL"
    title_bbox = draw.textbbox((0, 0), contract_title, font=font_small)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = box_x + (box_width - title_width) // 2
    draw.text((title_x, box_y - 45), contract_title, fill=text_white, font=font_small)
    
    # رسم الصندوق بحواف مدورة
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_width, box_y + box_height],
        radius=25,
        fill=box_bg,
        outline=border_color,
        width=3
    )
    
    # ═══════════════════════════════════════════════════════════════
    # القسم الأيسر: السعر + Change + Percent
    # ═══════════════════════════════════════════════════════════════
    
    left_section_x = box_x + 40
    left_section_width = 450
    
    # خط فاصل عمودي
    separator_x = box_x + left_section_width + 20
    draw.line([separator_x, box_y + 30, separator_x, box_y + box_height - 30],
             fill=border_color, width=2)
    
    # السعر الكبير (4.50)
    price_text = f"{data['price']:.2f}"
    price_bbox = draw.textbbox((0, 0), price_text, font=font_huge)
    price_width = price_bbox[2] - price_bbox[0]
    price_x = left_section_x + (left_section_width - price_width) // 2
    draw.text((price_x, box_y + 40), price_text, fill=text_cyan, font=font_huge)
    
    # خط أفقي رفيع (مقصر من اليمين بـ 1 سم)
    line_y = box_y + 170
    draw.line([left_section_x, line_y, left_section_x + left_section_width - 40, line_y],
             fill=border_color, width=1)
    
    # Change
    change_label = "Change"
    change_value = f"+{data['change']:.2f}" if data['change'] >= 0 else f"{data['change']:.2f}"
    
    draw.text((left_section_x + 30, box_y + 190), change_label, 
             fill=text_white, font=font_small)
    
    change_bbox = draw.textbbox((0, 0), change_value, font=font_large)
    change_width = change_bbox[2] - change_bbox[0]
    draw.text((left_section_x + left_section_width - change_width - 30, box_y + 182), 
             change_value, fill=text_green, font=font_large)
    
    # Percent
    percent_label = "Percent"
    percent_value = f"+{data['percent']:.2f}%" if data['percent'] >= 0 else f"{data['percent']:.2f}%"
    
    draw.text((left_section_x + 30, box_y + 240), percent_label, 
             fill=text_white, font=font_small)
    
    percent_bbox = draw.textbbox((0, 0), percent_value, font=font_large)
    percent_width = percent_bbox[2] - percent_bbox[0]
    draw.text((left_section_x + left_section_width - percent_width - 30, box_y + 232), 
             percent_value, fill=text_green, font=font_large)
    
    # ═══════════════════════════════════════════════════════════════
    # القسم الأيمن: Ask / Bid / Mid
    # ═══════════════════════════════════════════════════════════════
    
    right_section_x = separator_x + 40
    right_spacing = 75
    
    # Ask (أحمر)
    ask_y = box_y + 50
    draw.text((right_section_x, ask_y), "Ask", fill=text_white, font=font_medium)
    
    ask_box_x = right_section_x + 150
    draw.rounded_rectangle(
        [ask_box_x, ask_y - 5, ask_box_x + 200, ask_y + 50],
        radius=12,
        fill=(255, 50, 100, 20),  # تظليل أحمر خفيف جداً
        outline=(200, 50, 50),
        width=3
    )
    draw.text((ask_box_x + 30, ask_y), f"{data['ask']:.2f}", 
             fill=text_red, font=font_medium)
    
    # Bid (أزرق)
    bid_y = ask_y + right_spacing
    draw.text((right_section_x, bid_y), "Bid", fill=text_white, font=font_medium)
    
    bid_box_x = right_section_x + 150
    draw.rounded_rectangle(
        [bid_box_x, bid_y - 5, bid_box_x + 200, bid_y + 50],
        radius=12,
        fill=(100, 200, 255, 20),  # تظليل أزرق خفيف جداً
        outline=(50, 100, 200),
        width=3
    )
    draw.text((bid_box_x + 30, bid_y), f"{data['bid']:.2f}", 
             fill=text_blue, font=font_medium)
    
    # Mid (رمادي)
    mid_y = bid_y + right_spacing
    draw.text((right_section_x, mid_y), "Mid", fill=text_white, font=font_medium)
    
    mid_box_x = right_section_x + 150
    draw.rounded_rectangle(
        [mid_box_x, mid_y - 5, mid_box_x + 200, mid_y + 50],
        radius=12,
        fill=(220, 220, 255, 15),  # تظليل رمادي خفيف جداً
        outline=(100, 100, 100),
        width=3
    )
    draw.text((mid_box_x + 30, mid_y), f"{data['mid']:.2f}", 
             fill=text_gray, font=font_medium)
    
    # ═══════════════════════════════════════════════════════════════
    # وقت التحديث أسفل المستطيل مباشرة
    # ═══════════════════════════════════════════════════════════════
    update_time = datetime.now().strftime("%m/%d %H:%M:%S EST")
    update_text = f"Updated: {update_time}"
    update_bbox = draw.textbbox((0, 0), update_text, font=font_small)
    update_width = update_bbox[2] - update_bbox[0]
    update_x = box_x + (box_width - update_width) // 2
    draw.text((update_x, box_y + box_height + 20), update_text, 
             fill=(180, 180, 200), font=font_small)
    
    print("✅ تم رسم التصميم")
    
    # حفظ الصورة
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"telegram_test_{timestamp}.png"
    
    # محاولة حفظ الصورة
    try:
        img.save(output_file)
    except PermissionError:
        # إذا فشل، جرّب في مجلد Temp
        import tempfile
        output_file = os.path.join(tempfile.gettempdir(), f"telegram_test_{timestamp}.png")
        img.save(output_file)
    
    print(f"\n{'='*60}")
    print(f"✅ تم إنشاء الصورة بنجاح!")
    print(f"📁 اسم الملف: {os.path.basename(output_file)}")
    print(f"📂 المسار الكامل: {os.path.abspath(output_file)}")
    print(f"{'='*60}\n")
    
    # فتح الصورة
    try:
        import webbrowser
        webbrowser.open(os.path.abspath(output_file))
        print("✅ تم فتح الصورة في المتصفح/عارض الصور")
    except Exception as e:
        print(f"⚠️ لم أتمكن من فتح الصورة تلقائياً: {e}")
        print(f"افتحها يدوياً من: {os.path.abspath(output_file)}")
    
    return img

if __name__ == "__main__":
    try:
        print("\n" + "="*60)
        print("🎨 برنامج إنشاء صور التيليجرام")
        print("="*60 + "\n")
        
        print("🚀 بدء إنشاء الصورة...")
        print("⏳ الرجاء الانتظار...\n")
        
        # سيتم إنشاء خلفية تلقائياً (لا حاجة لملفات خارجية)
        create_telegram_image()
        
        print("\n" + "="*60)
        print("✅ تم بنجاح!")
        print("="*60)
        
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ حدث خطأ: {e}")
        print(f"{'='*60}")
        import traceback
        traceback.print_exc()
    
    finally:
        # هذا سيتم تنفيذه دائماً حتى لو حدث خطأ
        input("\nاضغط Enter للإغلاق...")
