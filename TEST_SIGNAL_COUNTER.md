# 🧪 اختبار عداد الإشارات من TradingView

## المشكلة السابقة
كان جدول "📡 عدد الإشارات" يظهر دائماً:
- CALL: 0
- PUT: 0
- إجمالي: 0

حتى بعد استقبال إشارات من TradingView Webhook.

---

## ✅ الحل المُطبق

### 1. تسجيل الإشارة في قاعدة البيانات
عند استقبال webhook من TradingView، يتم:
- تسجيل الإشارة في جدول `signals` بقاعدة البيانات
- حفظ نوع الإشارة (CALL/PUT)
- حفظ الرمز (Symbol)
- حفظ وقت الاستقبال

### 2. تحديث العداد فورياً
- يتم تحديث العدادات **فوراً** عند استقبال الإشارة
- لا حاجة للانتظار دورة التحديث التلقائي (2 ثانية)

### 3. التحديث الدوري
- يستمر التحديث التلقائي كل 2 ثانية للتأكد من المزامنة

---

## 🧪 كيفية الاختبار

### الطريقة 1: استخدام PowerShell

```powershell
# إرسال إشارة CALL
$body = @{
    type = "CALL"
    symbol = "SPX"
    quantity = 1
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://YOUR_NGROK_URL/webhook" `
                  -Method Post `
                  -ContentType "application/json" `
                  -Body $body
```

### الطريقة 2: استخدام curl

```bash
# إشارة CALL
curl -X POST http://YOUR_NGROK_URL/webhook \
  -H "Content-Type: application/json" \
  -d '{"type": "CALL", "symbol": "SPX"}'

# إشارة PUT
curl -X POST http://YOUR_NGROK_URL/webhook \
  -H "Content-Type: application/json" \
  -d '{"type": "PUT", "symbol": "SPX"}'
```

### الطريقة 3: استخدام Postman

1. افتح Postman
2. اختر **POST**
3. ضع الـ URL: `http://YOUR_NGROK_URL/webhook`
4. اختر Body > raw > JSON
5. اكتب:
```json
{
  "type": "CALL",
  "symbol": "SPX",
  "quantity": 2
}
```
6. اضغط **Send**

---

## 📊 النتيجة المتوقعة

### في Console:
```
============================================================
📡 WEBHOOK RECEIVED #1: 2026-03-06 14:30:00
🎯 Signal: CALL SPX
📦 Quantity: 2 contracts
============================================================
✅ Triggering manual CALL button for SPX
📦 Setting contract quantity to: 2
✅ Signal #1 registered: CALL SPX
📊 Signal counters updated: CALL=1, PUT=0, Total=1
```

### في الواجهة الرسومية:
جدول "📡 عدد الإشارات" سيتحدث فوراً:
```
CALL:   1
PUT:    0
إجمالي: 1
```

### بعد إرسال إشارة PUT:
```
CALL:   1
PUT:    1
إجمالي: 2
```

---

## 🔍 استكشاف الأخطاء

### المشكلة: العدادات لا تتحدث
**الحلول:**
1. ✅ تأكد من تشغيل النظام (System Running)
2. ✅ تحقق من Console - يجب أن يظهر "Signal registered"
3. ✅ تحقق من قاعدة البيانات:
```sql
SELECT * FROM signals WHERE DATE(received_time) = DATE('now');
```

### المشكلة: العدادات تصفر عند إعادة التشغيل
**السبب:** العدادات تعرض إشارات **اليوم فقط**

**التحقق من الإشارات السابقة:**
```sql
SELECT signal_type, COUNT(*) as count, DATE(received_time) as date 
FROM signals 
GROUP BY signal_type, DATE(received_time)
ORDER BY received_time DESC;
```

### المشكلة: الإشارة مُستقبلة لكن الصفقة لا تُفتح
**الأسباب المحتملة:**
1. ❌ جدول المراقبة فارغ (لم يتم تشغيل النظام)
2. ❌ الشركة غير موجودة في قائمة المراقبة
3. ❌ شرط منع التكرار (Duplicate Prevention) فعّال

**الحل:** راجع Console للتفاصيل

---

## 📝 ملاحظات مهمة

1. **العدادات اليومية:** يتم حساب الإشارات لليوم الحالي فقط
2. **الإشارات التاريخية:** محفوظة في قاعدة البيانات، يمكن استعراضها بـ SQL
3. **لا عد للأزرار اليدوية:** الضغط يدوياً على CALL/PUT لا يُحسب في العدادات
4. **فقط Webhook:** العدادات تُحسب فقط للإشارات القادمة من TradingView

---

## 🗄️ قاعدة البيانات

### جدول signals
```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,            -- SPX, NDX, SPY, etc.
    signal_type TEXT NOT NULL,       -- CALL or PUT
    received_time TEXT NOT NULL,     -- timestamp
    processed BOOLEAN DEFAULT 0      -- 0=pending, 1=processed
)
```

### استعلامات مفيدة:

#### عرض إشارات اليوم:
```sql
SELECT * FROM signals 
WHERE DATE(received_time) = DATE('now')
ORDER BY received_time DESC;
```

#### إحصائيات شاملة:
```sql
SELECT 
    signal_type,
    COUNT(*) as total,
    COUNT(CASE WHEN DATE(received_time) = DATE('now') THEN 1 END) as today
FROM signals
GROUP BY signal_type;
```

#### حذف إشارات قديمة (اختياري):
```sql
DELETE FROM signals 
WHERE DATE(received_time) < DATE('now', '-30 days');
```

---

## 🚀 التطويرات المستقبلية (اختياري)

1. **رسم بياني:** عرض توزيع الإشارات خلال اليوم
2. **إحصائيات متقدمة:** نسبة النجاح، أوقات الذروة، إلخ
3. **تصدير CSV:** تصدير سجل الإشارات لتحليل خارجي
4. **تنبيهات:** إرسال تنبيه عند وصول عدد معين من الإشارات

---

**آخر تحديث:** 6 مارس 2026
**الحالة:** ✅ يعمل بشكل صحيح
