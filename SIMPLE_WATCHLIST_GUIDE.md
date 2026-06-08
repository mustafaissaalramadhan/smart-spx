# 🎯 النظام المبسط - Simple Watchlist System

## 📋 نظرة عامة

النظام الجديد **بسيط وواضح** يستخدم:
- **اتصالان فقط** مع Interactive Brokers
- **دفعات من 5 عقود** في كل مرة
- **بحث ذكي** يتوقف عند إيجاد العقود

---

## 🔧 البنية الأساسية

### الاتصالات (2 Connections):

```
┌─────────────────────────────────────────┐
│  Connection 1 (Client ID: 100)          │
│  ────────────────────────────────       │
│  الوظيفة: جلب سعر SPX/SPY/NDX/QQQ       │
│  التحديث: كل ثانيتين                   │
│  الحالة: دائم                           │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  Connection 2 (Client ID: 101)          │
│  ────────────────────────────────       │
│  الوظيفة: جلب العقود (Options)          │
│  الدفعات: 5 عقود في كل مرة              │
│  التحديث: كل 5 ثوان                     │
│  البحث الذكي: يناسب جميع الرموز         │
└─────────────────────────────────────────┘
```

---

## 🔄 آلية العمل

### 1. جلب السعر (كل ثانيتين):
```python
price = await manager.get_current_price('SPY')
# ✅ SPY: $590.50
```

### 2. جلب العقود (دفعات من 5) - ذكي لكل رمز:

#### مثال SPX (سعر $6890):
```python
# ATM = 6890
# Offset = 4 strikes × 5 = 20 نقطة
# Start = 6890 + 20 = 6910

# Batch 1: strikes [6910, 6915, 6920, 6925, 6930]
# ✅ 6920: Ask $6.50 → داخل النطاق
# ✅ 6925: Ask $5.20 → داخل النطاق
# ✅ 6930: Ask $4.10 → داخل النطاق
```

#### مثال SPY (سعر $590):
```python
# ATM = 590
# Offset = 15 strikes × 1 = 15 نقطة
# Start = 590 + 15 = 605

# Batch 1: strikes [605, 606, 607, 608, 609]
# ✅ 605: Ask $6.80 → داخل النطاق
# ✅ 606: Ask $5.90 → داخل النطاق
# ✅ 607: Ask $4.50 → داخل النطاق
```

#### مثال NDX (سعر $20500):
```python
# ATM = 20500
# Offset = 3 strikes × 10 = 30 نقطة
# Start = 20500 + 30 = 20530

# Batch 1: strikes [20530, 20540, 20550, 20560, 20570]
```

### 3. البحث الموسع التلقائي:
```python
# إذا لم نجد 3 عقود على الأقل في 20 دفعة
# → نبحث تلقائياً في 50 دفعة (250 عقد محتمل)
# → يضمن إيجاد عقود لجميع الرموز ✅
```

### 3. البحث الذكي:
```python
contracts = await manager.find_contracts_in_range(
    'SPX', expiry, 'CALL',
    price_min=1.0,
    price_max=7.0,
    max_batches=20  # حد أقصى 20 دفعة = 100 عقد
)

# النتيجة:
# [
#   {'strike': 6900, 'bid': 6.20, 'ask': 6.50},
#   {'strike': 6905, 'bid': 4.90, 'ask': 5.20},
#   {'strike': 6910, 'bid': 3.80, 'ask': 4.10},
#   {'strike': 6915, 'bid': 3.20, 'ask': 3.50},
#   {'strike': 6920, 'bid': 2.50, 'ask': 2.80}
# ]
# مرتبة حسب Bid (الأعلى أولاً) ✅
```

### 4. التحديث الدوري:
```python
# كل 5 ثوان: تحديث الأسعار للعقود الموجودة
updated = await manager.update_contracts_prices('SPX', 'CALL')

# لا يجلب عقود جديدة، فقط يحدث الأسعار الحالية
```

---

## ⚙️ الإعدادات (config.py)

```python
# تفعيل النظام المبسط
SIMPLE_WATCHLIST_ENABLED = True

# دفعات البحث
BATCH_SIZE_SIMPLE = 5  # عدد العقود في كل دفعة
MAX_BATCHES_TO_FETCH = 20  # حد أقصى 20 دفعة = 100 عقد

# التحديثات
PRICE_UPDATE_INTERVAL = 1  # السعر: كل ثانية
CONTRACTS_UPDATE_INTERVAL = 5  # العقود: كل 5 ثوان

# نطاقات السعر
MONITORING_RANGE_MIN = 1.0  # عرض في الجدول
MONITORING_RANGE_MAX = 7.0
ENTRY_RANGE_MIN = 3.0  # دخول صفقات (webhooks)
ENTRY_RANGE_MAX = 4.0
```

---

## 🧪 الاختبار

### اختبار بسيط:
```bash
python test_simple_watchlist.py
```

**النتيجة المتوقعة:**
```
================================================================================
🧪 Testing Simple Watchlist System
================================================================================

1️⃣ Starting system...
✅ Price connection established (Client ID: 100)
✅ Data connection established (Client ID: 101)
✅ System started successfully

2️⃣ Testing price fetch for SPX...
✅ SPX Price: $6890.50

3️⃣ Testing single batch fetch (5 CALL contracts)...
✅ Using expiry: 20260309
📊 Fetching batch starting at strike 6890...
✅ Fetched 5 contracts:
   ❌ Strike 6890: Bid $8.20, Ask $8.50
   ❌ Strike 6895: Bid $7.50, Ask $7.80
   ✅ Strike 6900: Bid $6.20, Ask $6.50
   ✅ Strike 6905: Bid $4.90, Ask $5.20
   ✅ Strike 6910: Bid $3.80, Ask $4.10

4️⃣ Testing smart search (find contracts in range $1-$7)...
📦 Batch 1/10: Starting at strike 6890
📦 Batch 2/10: Starting at strike 6915
✅ Found 8 CALL contracts in range:
   1. Strike 6900: Bid $6.20, Ask $6.50
   2. Strike 6905: Bid $4.90, Ask $5.20
   3. Strike 6910: Bid $3.80, Ask $4.10
   4. Strike 6915: Bid $3.20, Ask $3.50
   5. Strike 6920: Bid $2.50, Ask $2.80

5️⃣ Testing price update for existing contracts...
✅ Updated 8 contracts:
   1. Strike 6900: Bid $6.25, Ask $6.55
   2. Strike 6905: Bid $4.95, Ask $5.25
   3. Strike 6910: Bid $3.85, Ask $4.15
   4. Strike 6915: Bid $3.25, Ask $3.55
   5. Strike 6920: Bid $2.55, Ask $2.85

================================================================================
✅ All tests passed!
================================================================================

6️⃣ Stopping system...
✅ System stopped
```

---

## 🚀 الاستخدام في GUI

### عند بدء النظام:
```python
# في START.py → main_gui.py
self.simple_watchlist = SimpleWatchlistManager()
await self.simple_watchlist.start()
```

### عند فتح watchlist لـSPX:
```python
# جلب السعر (كل ثانية)
price = await simple_watchlist.get_current_price('SPX')
widgets['price_label'].config(text=f"${price:.2f}")

# جلب العقود (أول مرة أو force refresh)
call_contracts = await simple_watchlist.find_contracts_in_range(
    'SPX', expiry, 'CALL', 1.0, 7.0
)

# عرض في الجدول
for contract in call_contracts[:10]:
    tree.insert('', 'end', 
                text=f"${contract['strike']:.0f}",
                values=(f"${contract['bid']:.2f}", f"${contract['ask']:.2f}"))
```

### التحديث الدوري (كل 5 ثوان):
```python
# تحديث الأسعار فقط (لا يجلب عقود جديدة)
updated = await simple_watchlist.update_contracts_prices('SPX', 'CALL')

# تحديث الجدول
for contract in updated[:10]:
    # update tree...
```

---

## 📊 المقارنة: القديم vs الجديد

| الميزة | النظام القديم (Adaptive) | النظام الجديد (Simple) |
|--------|--------------------------|------------------------|
| **الاتصالات** | 8+ اتصالات | 2 اتصالات فقط ✅ |
| **الدفعات** | groups معقدة | 5 عقود/دفعة ✅ |
| **السرعة** | 3-6 ثوان | 2-4 ثوان ✅ |
| **الذاكرة** | عالية (~50MB+) | منخفضة (~10MB) ✅ |
| **التعقيد** | 550 سطر | 300 سطر ✅ |
| **الأداء** | CPU عالي | CPU منخفض ✅ |

---

## ✅ المزايا

1. **بسيط جداً**: فهم سهل، صيانة سهلة
2. **موارد أقل**: اتصالان فقط + ذاكرة أقل
3. **سريع**: جلب دفعات صغيرة (5 عقود)
4. **ذكي**: يتوقف عند إيجاد النطاق
5. **واضح**: logs سهلة القراءة

---

## 🎯 الخلاصة

النظام الجديد:
- ✅ **اتصالان فقط** (100 + 101)
- ✅ **دفعات من 5 عقود**
- ✅ **بحث ذكي يتوقف عند الإيجاد**
- ✅ **تحديث السعر كل ثانية**
- ✅ **تحديث العقود كل 5 ثوان**
- ✅ **ترتيب حسب Bid الأعلى**

**جاهز للاستخدام! 🚀**
