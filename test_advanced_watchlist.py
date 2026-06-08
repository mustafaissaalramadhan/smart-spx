"""
Test Adaptive Watchlist System
اختبار نظام المراقبة الذكي الجديد

يختبر:
1. جلب المجموعات الديناميكي
2. الاتصالات المخصصة لكل group
3. التحديث المستمر
4. النطاقات السعرية
"""

import asyncio
import sys

# Create event loop before importing ib_insync (fix for Python 3.14+)
if sys.version_info >= (3, 14):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

import logging
from datetime import datetime
from adaptive_watchlist import AdaptiveWatchlistMaster, PriceRangeManager
from ibkr_client import IBKRClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_adaptive_watchlist():
    """اختبار كامل للنظام"""
    
    print("\n" + "="*70)
    print("🧪 اختبار نظام المراقبة الذكي الجديد")
    print("="*70 + "\n")
    
    # إنشاء Master Controller
    master = AdaptiveWatchlistMaster()
    
    # اختبار SPY (سريع - عادة group واحد فقط)
    print("\n📊 اختبار SPY (سريع)...")
    print("-" * 50)
    
    try:
        # إنشاء اتصال مؤقت للحصول على السعر
        temp_conn = IBKRClient(base_client_id=999)
        await temp_conn.connect()
        
        spy_price = await temp_conn.get_underlying_price('SPY')
        if not spy_price:
            print("❌ لم نتمكن من الحصول على سعر SPY")
            await temp_conn.disconnect()
            return
        
        print(f"✅ SPY Price: ${spy_price:.2f}")
        await temp_conn.disconnect()
        
        # بدء المراقبة
        start_time = datetime.now()
        await master.start_symbol_watchlist('SPY', spy_price)
        end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        
        # عرض النتائج
        print(f"\n⏱️ وقت التهيئة: {duration:.2f} ثانية")
        
        call_groups = master.get_active_groups('SPY', 'CALL')
        put_groups = master.get_active_groups('SPY', 'PUT')
        
        print(f"🟢 CALL Groups Active: {call_groups}")
        print(f"🔴 PUT Groups Active: {put_groups}")
        
        # عرض البيانات
        call_data = master.get_all_active_data('SPY', 'CALL')
        put_data = master.get_all_active_data('SPY', 'PUT')
        
        print(f"\n📈 CALL Contracts: {len(call_data)}")
        for c in call_data[:5]:  # أول 5 فقط
            print(f"   Strike {c['strike']}: Bid=${c['bid']:.2f}, Ask=${c['ask']:.2f}")
        
        print(f"\n📉 PUT Contracts: {len(put_data)}")
        for c in put_data[:5]:
            print(f"   Strike {c['strike']}: Bid=${c['bid']:.2f}, Ask=${c['ask']:.2f}")
        
        # تحقق من النطاق
        entry_call = master.get_entry_contracts('SPY', 'CALL')
        entry_put = master.get_entry_contracts('SPY', 'PUT')
        
        print(f"\n🎯 عقود صالحة للدخول ($3-$4):")
        print(f"   CALL: {len(entry_call)} contracts")
        print(f"   PUT: {len(entry_put)} contracts")
        
        # اختبار التحديث (10 ثوان)
        print(f"\n🔄 اختبار التحديث المستمر (10 ثوان)...")
        await asyncio.sleep(10)
        
        # التحقق من التحديث
        call_data_updated = master.get_all_active_data('SPY', 'CALL')
        update_times = [master.groups['SPY']['CALL'][g].last_update 
                       for g in call_groups]
        
        print(f"✅ آخر تحديث: {max(update_times).strftime('%H:%M:%S')}")
        
        # التنظيف
        print(f"\n🛑 إيقاف المراقبة...")
        await master.stop_symbol_watchlist('SPY')
        
        print("\n✅ الاختبار اكتمل بنجاح!")
        
    except Exception as e:
        logger.error(f"❌ خطأ في الاختبار: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await master.cleanup()


async def test_price_range_manager():
    """اختبار مدير النطاقات"""
    
    print("\n" + "="*70)
    print("🎯  اختبار مدير النطاقات السعرية")
    print("="*70 + "\n")
    
    mgr = PriceRangeManager()
    
    print(f"النطاق الافتراضي:")
    print(f"  المتابعة: ${mgr.monitoring_range[0]}-${mgr.monitoring_range[1]}")
    print(f"  الدخول: ${mgr.entry_range[0]}-${mgr.entry_range[1]}")
    
    # اختبار التحديث
    print(f"\nتحديث النطاقات...")
    mgr.update_monitoring_range(1.5, 8.0)
    success = mgr.update_entry_range(3.5, 5.0)
    
    if success:
        print(f"✅ النطاقات محدثة!")
    else:
        print(f"❌ فشل التحديث")
    
    # اختبار الفلترة
    test_prices = [0.5, 2.0, 3.8, 4.5, 6.0, 9.0]
    
    print(f"\nاختبار الأسعار:")
    for price in test_prices:
        in_monitor = mgr.is_in_monitoring_range(price)
        in_entry = mgr.is_in_entry_range(price)
        
        status = ""
        if in_entry:
            status = "🎯 دخول + متابعة"
        elif in_monitor:
            status = "📊 متابعة فقط"
        else:
            status = "❌ خارج النطاق"
        
        print(f"  ${price:.2f}: {status}")


async def test_connections_isolation():
    """اختبار عزل الاتصالات"""
    
    print("\n" + "="*70)
    print("🔌 اختبار عزل الاتصالات")
    print("="*70 + "\n")
    
    # إنشاء 3 اتصالات مختلفة
    connections = []
    
    for i in range(1, 4):
        try:
            conn = IBKRClient(base_client_id=i)
            success = await conn.connect()
            
            if success:
                print(f"✅ Connection {i} (clientId={i}): متصل")
                connections.append(conn)
            else:
                print(f"❌ Connection {i}: فشل الاتصال")
                
        except Exception as e:
            print(f"❌ Connection {i}: خطأ - {e}")
    
    print(f"\nإجمالي الاتصالات الناجحة: {len(connections)}")
    
    # اختبار الطلبات المتوازية
    if len(connections) >= 2:
        print(f"\n🔄 اختبار الطلبات المتوازية...")
        
        try:
            # طلب السعر من كل اتصال في نفس الوقت
            tasks = [conn.get_underlying_price('SPY') for conn in connections[:2]]
            results = await asyncio.gather(*tasks)
            
            print(f"✅ النتائج:")
            for i, price in enumerate(results, 1):
                print(f"   Connection {i}: ${price:.2f}" if price else f"   Connection {i}: فشل")
            
        except Exception as e:
            print(f"❌ خطأ في الطلبات المتوازية: {e}")
    
    # التنظيف
    print(f"\n🧹 قطع الاتصالات...")
    for i, conn in enumerate(connections, 1):
        try:
            await conn.disconnect()
            print(f"✅ Connection {i}: مفصول")
        except:
            pass


async def main():
    """البرنامج الرئيسي"""
    
    print("\n" + "="*70)
    print("🚀 بدء اختبارات نظام المراقبة الذكي")
    print("="*70)
    
    try:
        # اختبار 1: مدير النطاقات
        await test_price_range_manager()
        
        # اختبار 2: عزل الاتصالات
        await test_connections_isolation()
        
        # انتظار قبل الاختبار الرئيسي
        print(f"\n⏳ انتظار 3 ثوان قبل الاختبار الرئيسي...")
        await asyncio.sleep(3)
        
        # اختبار 3: النظام الكامل
        await test_adaptive_watchlist()
        
        print("\n" + "="*70)
        print("✅ جميع الاختبارات اكتملت!")
        print("="*70 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ تم إيقاف الاختبار من قبل المستخدم")
    except Exception as e:
        print(f"\n\n❌ خطأ عام: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
