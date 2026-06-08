"""
اختبار محاكاة لفتح عقد يدوي - نفس البيانات التي ترسلها main_gui
"""
from datetime import datetime
from telegram_manager import TelegramManager

# محاكاة البيانات من main_gui بالضبط
# strike يُرسل كـ string (من tree.item['text'])
# bid, ask, entry_price float (من _get_best_contract_from_tree)

symbol = 'SPX'
trade_type = 'CALL'
strike = '6825'  # ⚠️ STRING - كما من tree
bid = 51.0       # float
ask = 51.5       # float
entry_price = 51.5  # float (= ask)
contract_name = f"{symbol} {strike} {trade_type}"

# Format expiry
expiry_date = datetime.now().strftime('%Y%m%d')
try:
    from datetime import datetime as dt
    expiry_dt = dt.strptime(expiry_date, '%Y%m%d')
    expiry_formatted = expiry_dt.strftime('%d%b%y').upper()
except:
    expiry_formatted = datetime.now().strftime('%d%b%y').upper()

notification_data = {
    'symbol': symbol,
    'type': trade_type,
    'contract': contract_name,
    'strike': strike,  # STRING!
    'entry_price': entry_price,
    'current_price': entry_price,
    'bid': bid,
    'ask': ask,
    'expiry': expiry_formatted,
    'emoji': '📈',  # CALL
    'channel_link': 'https://t.me/GeneralSmatrPro',
    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
}

print("=" * 80)
print("🧪 اختبار محاكاة فتح عقد يدوي")
print("=" * 80)
print(f"\n📊 البيانات المُرسلة:")
for key, value in notification_data.items():
    print(f"   {key}: {value} ({type(value).__name__})")

print(f"\n{'='*80}")
print("📤 إرسال إشعار position_opened...")
print("=" * 80)

telegram = TelegramManager()

# Test with async_loop = None (simulate manual trade without system)
telegram.send_notification_sync('position_opened', notification_data, symbol, async_loop=None)

print("\n" + "=" * 80)
print("✅ انتهى الاختبار")
print("=" * 80)
