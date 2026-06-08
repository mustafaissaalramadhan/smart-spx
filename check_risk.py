import sqlite3

conn = sqlite3.connect('spx_smart.db')
cursor = conn.cursor()

print("=" * 60)
print("SPX Risk Settings من قاعدة البيانات:")
print("=" * 60)

cursor.execute('SELECT * FROM risk_settings WHERE symbol="SPX"')
result = cursor.fetchone()

if result:
    print(f"✅ تم العثور على إعدادات SPX:")
    print(f"   Stop Loss: type='{result[2]}', value={result[3]}")
    print(f"   Trailing: type='{result[4]}', value={result[5]}")
    print(f"   Capital: type='{result[6]}', value={result[7]}")
    print(f"   Profit Target: type='{result[8]}', value={result[9]}")
    print(f"   Last Updated: {result[10]}")
else:
    print("❌ لم يتم العثور على إعدادات لـ SPX")
    print("سيتم استخدام الإعدادات الافتراضية (جميعها 'none')")

print("\n" + "=" * 60)
print("الصفقات النشطة:")
print("=" * 60)

cursor.execute('''
    SELECT id, symbol, trade_type, entry_price, current_price, highest_price, status 
    FROM trades 
    WHERE status = "ACTIVE"
''')

trades = cursor.fetchall()
if trades:
    for trade in trades:
        trade_id, symbol, trade_type, entry, current, highest, status = trade
        print(f"\nصفقة #{trade_id}:")
        print(f"   {symbol} {trade_type}")
        print(f"   Entry: ${entry:.2f}")
        print(f"   Current: ${current:.2f}")
        print(f"   Highest: ${highest:.2f}")
        
        # حساب الهدف المتوقع
        cursor.execute('SELECT * FROM risk_settings WHERE symbol=?', (symbol,))
        risk = cursor.fetchone()
        if risk and risk[8] == 'amount':
            target_value = risk[9]
            target_price = entry + (target_value / 100)
            print(f"   Target: ${target_price:.2f} (value={target_value})")
            print(f"   Should Close: {'✅ YES' if current >= target_price else '❌ NO'}")
        else:
            print(f"   Target: NONE")
else:
    print("❌ لا توجد صفقات نشطة")

print("\n" + "=" * 60)
print("آخر 5 صفقات مغلقة:")
print("=" * 60)

cursor.execute('''
    SELECT id, symbol, trade_type, entry_price, exit_price, profit_loss, entry_time, exit_time
    FROM trades 
    WHERE status = "CLOSED"
    ORDER BY id DESC
    LIMIT 5
''')

closed_trades = cursor.fetchall()
if closed_trades:
    for trade in closed_trades:
        tid, sym, ttype, entry, exit_p, pl, entry_t, exit_t = trade
        print(f"\nصفقة #{tid}: {sym} {ttype}")
        print(f"   Entry: ${entry:.2f}, Exit: ${exit_p:.2f}")
        print(f"   P/L: ${pl:.2f}")
        print(f"   {entry_t} -> {exit_t}")
else:
    print("❌ لا توجد صفقات مغلقة")

conn.close()
print("\n" + "=" * 60)
