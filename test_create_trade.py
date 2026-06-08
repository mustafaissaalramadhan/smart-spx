"""
فحص مباشر لحفظ الصفقات في قاعدة البيانات
"""
from database import DatabaseManager
import config

print("=" * 80)
print("🔍 فحص مسار قاعدة البيانات وعملية حفظ الصفقات")
print("=" * 80)

db = DatabaseManager()

print(f"\n📁 مسار قاعدة البيانات:")
print(f"   {db.db_path}")

print(f"\n✅ محاولة إنشاء صفقة تجريبية...")

try:
    trade_id = db.create_trade(
        symbol='SPX',
        trade_type='CALL',
        option_contract='SPX 6800 CALL',
        strike_price=6800.0,
        entry_price=50.0,
        expiry='25JAN25',
        bid=49.5,
        ask=50.5,
        quantity=1
    )
    print(f"✅ تم إنشاء الصفقة في قاعدة البيانات: trade_id = {trade_id}")
    
    # التحقق من الحفظ
    active_trades = db.get_active_trades('SPX')
    print(f"\n📊 الصفقات النشطة بعد الإنشاء:")
    if active_trades:
        for trade in active_trades:
            print(f"   ID: {trade['id']}, Contract: {trade['option_contract']}, Entry: ${trade['entry_price']:.2f}")
    else:
        print("   ❌ لا توجد صفقات!")
        
    # حذف الصفقة التجريبية
    print(f"\n🧹 حذف الصفقة التجريبية...")
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM trades WHERE id = ?', (trade_id,))
    conn.commit()
    conn.close()
    print("✅ تم الحذف")

except Exception as e:
    print(f"❌ خطأ: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" *80)
