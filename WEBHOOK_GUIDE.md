# 📡 دليل استخدام Webhook مع TradingView

## نظرة عامة
يدعم النظام الآن استقبال إشارات TradingView مع تحديد **عدد العقود** تلقائياً.

---

## 🎯 صيغة الإشارة (JSON)

### 1️⃣ إشارة بسيطة (بدون تحديد عدد العقود)
```json
{
  "type": "CALL",
  "symbol": "SPX"
}
```
**النتيجة:** سيتم فتح صفقة CALL على SPX بعدد العقود الافتراضي (1 عقد)

---

### 2️⃣ إشارة مع تحديد عدد العقود
```json
{
  "type": "CALL",
  "symbol": "SPX",
  "quantity": 3
}
```
**النتيجة:** سيتم فتح صفقة CALL على SPX بـ **3 عقود**

---

### 3️⃣ أمثلة أخرى

#### فتح 5 عقود PUT على NDX
```json
{
  "type": "PUT",
  "symbol": "NDX",
  "quantity": 5
}
```

#### فتح 2 عقد CALL على SPY
```json
{
  "type": "CALL",
  "symbol": "SPY",
  "quantity": 2
}
```

---

## ⚙️ المتطلبات

| المعلمة | نوع البيانات | إلزامي؟ | الوصف |
|---------|--------------|---------|-------|
| `type` | String | ✅ نعم | نوع الصفقة: `CALL` أو `PUT` فقط |
| `symbol` | String | ✅ نعم | رمز السهم: `SPX`, `NDX`, `SPY` |
| `quantity` | Integer | ⚪ اختياري | عدد العقود (رقم صحيح موجب) |

### ملاحظات:
- ✅ إذا لم تحدد `quantity`، سيتم استخدام العدد الافتراضي المحدد في النظام
- ⚠️ العدد يجب أن يكون **1 أو أكثر**
- ❌ العدد يجب أن يكون **رقم صحيح** (ليس عشري)

---

## 🔗 إعداد TradingView

### الخطوة 1: انسخ رابط Webhook
1. شغّل النظام
2. في قسم "TradingView Integration"
3. انسخ الرابط من "رابط Ngrok"

### الخطوة 2: إنشاء تنبيه في TradingView
1. افتح الرسم البياني في TradingView
2. اضغط **Create Alert**
3. في Notifications > Webhook URL، الصق الرابط
4. في Message، اكتب صيغة JSON المطلوبة:

```json
{
  "type": "{{strategy.order.action}}",
  "symbol": "SPX",
  "quantity": 2
}
```

أو ببساطة:
```json
{
  "type": "CALL",
  "symbol": "SPX",
  "quantity": 5
}
```

---

## 📊 سجل الإشارات

عند استقبال إشارة جديدة، سيظهر في Console:
```
============================================================
📡 WEBHOOK RECEIVED #1: 2026-03-06 14:30:00
🎯 Signal: CALL SPX
📦 Quantity: 3 contracts
📦 Data: {'type': 'CALL', 'symbol': 'SPX', 'quantity': 3}
============================================================
✅ Triggering manual CALL button for SPX
📦 Setting contract quantity to: 3
```

---

## 🧪 اختبار الإشارة

يمكنك اختبار الـ webhook باستخدام **Postman** أو **curl**:

### باستخدام curl:
```bash
curl -X POST http://YOUR_NGROK_URL/webhook \
  -H "Content-Type: application/json" \
  -d '{"type": "CALL", "symbol": "SPX", "quantity": 2}'
```

### باستخدام PowerShell:
```powershell
$body = @{
    type = "CALL"
    symbol = "SPX"
    quantity = 3
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://YOUR_NGROK_URL/webhook" `
                  -Method Post `
                  -ContentType "application/json" `
                  -Body $body
```

---

## ✅ الرد المتوقع

### نجاح:
```json
{
  "status": "success",
  "message": "CALL signal #1 received for SPX x3 - Manual button triggered",
  "timestamp": "2026-03-06 14:30:00"
}
```

### خطأ في البيانات:
```json
{
  "status": "error",
  "message": "Invalid signal type. Must be CALL or PUT"
}
```

---

## 🔍 استكشاف الأخطاء

### المشكلة: لا يتم فتح الصفقة
- ✅ تحقق من أن النظام **مُشغّل**
- ✅ تحقق من وجود **بيانات في جدول المراقبة**
- ✅ تحقق من صيغة JSON صحيحة

### المشكلة: العدد لا يتطابق
- ✅ تأكد من أن `quantity` رقم صحيح (ليس نص)
- ✅ تحقق من Console للتأكد من القيمة المستلمة

### المشكلة: "GUI not initialized"
- ✅ انتظر حتى يكتمل تشغيل النظام
- ✅ أعد المحاولة بعد ثوانٍ قليلة

---

## 📝 ملاحظات مهمة

1. **العدد المؤقت:** عند استقبال إشارة بعدد محدد، يتم تطبيق هذا العدد **فقط على هذه الصفقة**، ثم يعود النظام للعدد الافتراضي

2. **السجل:** يتم حفظ جميع الصفقات في قاعدة البيانات مع عدد العقود المحدد

3. **الإغلاق الجزئي:** يمكنك إغلاق جزء من العقود بعد فتح الصفقة من خلال واجهة النظام

4. **التتبع التلقائي:** جميع الصفقات المفتوحة عبر Webhook تُتبع تلقائياً مثل الصفقات اليدوية

---

## 🎓 أمثلة عملية

### سيناريو 1: فتح 10 عقود عند اختراق مستوى
```json
{
  "type": "CALL",
  "symbol": "SPX",
  "quantity": 10
}
```

### سيناريو 2: فتح عقد واحد للتجربة
```json
{
  "type": "PUT",
  "symbol": "NDX"
}
```
*لم نحدد quantity، سيستخدم النظام القيمة الافتراضية (1)*

### سيناريو 3: استراتيجية متعددة المراحل
1. إشارة أولى: افتح 3 عقود
```json
{"type": "CALL", "symbol": "SPX", "quantity": 3}
```

2. إشارة إضافية: افتح 2 عقد إضافي
```json
{"type": "CALL", "symbol": "SPX", "quantity": 2}
```

**النتيجة:** سيكون لديك صفقتين منفصلتين:
- صفقة #1: 3 عقود
- صفقة #2: 2 عقد

---

## 🆘 الدعم

لأي استفسار أو مشكلة:
1. راجع ملف `spx_smart.log`
2. تحقق من Console في البرنامج
3. اطلع على جدول الصفقات النشطة

**تاريخ آخر تحديث:** 6 مارس 2026
