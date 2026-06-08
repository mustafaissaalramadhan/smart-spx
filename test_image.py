"""
اختبار بسيط لإنشاء صورة
"""
print("="*60)
print("بدء الاختبار...")
print("="*60)

try:
    from PIL import Image, ImageDraw, ImageFont
    from datetime import datetime
    import os
    
    print("✅ المكتبات تم تحميلها")
    
    # إنشاء صورة بسيطة
    width = 1024
    height = 600
    img = Image.new('RGB', (width, height), (10, 20, 40))
    draw = ImageDraw.Draw(img, 'RGBA')
    
    print("✅ تم إنشاء الصورة")
    
    # رسم صندوق بسيط
    box_x = 100
    box_y = 100
    box_width = 800
    box_height = 400
    
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_width, box_y + box_height],
        radius=25,
        fill=(20, 40, 80, 200),
        outline=(50, 80, 120),
        width=3
    )
    
    print("✅ تم رسم الصندوق")
    
    # حفظ الصورة
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"test_{timestamp}.png"
    img.save(output_file)
    
    print(f"✅ تم حفظ الصورة: {output_file}")
    print(f"📂 المسار: {os.path.abspath(output_file)}")
    
    # فتح الصورة
    import webbrowser
    webbrowser.open(os.path.abspath(output_file))
    print("✅ تم فتح الصورة")
    
    print("\n" + "="*60)
    print("✅ الاختبار نجح!")
    print("="*60)
    
except Exception as e:
    print(f"\n❌ حدث خطأ: {e}")
    import traceback
    traceback.print_exc()

input("\nاضغط Enter للإغلاق...")
