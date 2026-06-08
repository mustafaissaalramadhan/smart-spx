"""
اختبار الحد الأقصى لعدد الاتصالات مع Interactive Brokers
"""
import asyncio
import sys

# إنشاء وتعيين event loop قبل استيراد ib_insync لحل مشكلة Python 3.10+
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# الآن يمكن استيراد ib_insync بأمان
from ib_insync import IB
import time
from datetime import datetime

class ConnectionTester:
    def __init__(self):
        self.connections = []
        self.max_successful = 0
        self.failed_at = None
        
    async def test_connection_limit(self, host='127.0.0.1', port=7497, client_id_start=2000):
        """
        اختبار الحد الأقصى للاتصالات مع IBKR
        """
        print(f"\n{'='*70}")
        print(f"بدء الاختبار: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Host: {host} | Port: {port} | Starting Client ID: {client_id_start}")
        print(f"{'='*70}\n")
        
        connection_num = 0
        
        try:
            # محاولة إنشاء حتى 50 اتصال
            while connection_num < 50:
                connection_num += 1
                client_id = client_id_start + connection_num
                
                print(f"محاولة #{connection_num:02d} (Client ID: {client_id})...", end=" ", flush=True)
                
                try:
                    ib = IB()
                    
                    # محاولة الاتصال مع timeout 15 ثانية
                    await asyncio.wait_for(
                        ib.connectAsync(host, port, clientId=client_id),
                        timeout=15.0
                    )
                    
                    # التحقق من نجاح الاتصال
                    if ib.isConnected():
                        self.connections.append(ib)
                        self.max_successful = connection_num
                        print(f"✓ نجح | إجمالي: {len(self.connections)} اتصال نشط")
                        
                        # انتظار قصير بين كل اتصال لتجنب الضغط الزائد
                        await asyncio.sleep(0.3)
                    else:
                        print(f"✗ فشل - لم يتم الاتصال")
                        self.failed_at = connection_num
                        break
                        
                except asyncio.TimeoutError:
                    print(f"✗ فشل - انتهى الوقت (Timeout)")
                    self.failed_at = connection_num
                    break
                    
                except Exception as e:
                    error_msg = str(e)
                    if len(error_msg) > 60:
                        error_msg = error_msg[:60] + "..."
                    print(f"✗ فشل - {type(e).__name__}: {error_msg}")
                    self.failed_at = connection_num
                    break
                    
        except KeyboardInterrupt:
            print("\n\n⚠️  تم إيقاف الاختبار يدوياً (Ctrl+C)")
        
        finally:
            await self.print_results(host, port)
            await self.cleanup_connections()
    
    async def print_results(self, host, port):
        """طباعة النتائج النهائية"""
        print(f"\n{'='*70}")
        print("النتائج النهائية")
        print(f"{'='*70}")
        print(f"✓ الاتصالات الناجحة: {self.max_successful}")
        print(f"✓ الاتصالات النشطة حالياً: {len(self.connections)}")
        if self.failed_at:
            print(f"✗ فشل الاتصال عند المحاولة: {self.failed_at}")
        print(f"{'='*70}\n")
        
        # كتابة النتائج في ملف
        result_file = 'connection_test_results.txt'
        with open(result_file, 'w', encoding='utf-8') as f:
            f.write(f"نتائج اختبار حدود الاتصال مع Interactive Brokers\n")
            f.write(f"{'='*70}\n")
            f.write(f"التاريخ والوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Host: {host}\n")
            f.write(f"Port: {port}\n")
            f.write(f"\nالنتائج:\n")
            f.write(f"  • الحد الأقصى للاتصالات الناجحة: {self.max_successful}\n")
            f.write(f"  • عدد الاتصالات النشطة: {len(self.connections)}\n")
            if self.failed_at:
                f.write(f"  • فشل الاتصال عند المحاولة رقم: {self.failed_at}\n")
            f.write(f"\nمعلومات مرجعية:\n")
            f.write(f"  • TWS Paper Trading: عادة 8-10 اتصالات\n")
            f.write(f"  • TWS Live Trading: عادة 30-32 اتصالات\n")
            f.write(f"  • IB Gateway: قد يختلف\n")
            f.write(f"  • Market Data Lines Limit: 100 (منفصل عن عدد الاتصالات)\n")
        
        print(f"✓ تم حفظ النتائج في: {result_file}\n")
    
    async def cleanup_connections(self):
        """إغلاق جميع الاتصالات"""
        if not self.connections:
            return
            
        print(f"إغلاق {len(self.connections)} اتصال...")
        total = len(self.connections)
        
        for i, ib in enumerate(self.connections, 1):
            try:
                ib.disconnect()
                if i % 5 == 0 or i == total:
                    print(f"  أُغلق {i}/{total} اتصال")
            except:
                pass
        
        print("✓ تم إغلاق جميع الاتصالات\n")

async def main():
    print(f"\n{'='*70}")
    print("اختبار الحد الأقصى لاتصالات Interactive Brokers API")
    print(f"{'='*70}\n")
    
    print("⚠️  تحذيرات مهمة:")
    print("  1. تأكد من تشغيل TWS أو IB Gateway")
    print("  2. تأكد من تفعيل: Configure → API Settings → Enable ActiveX and Socket Clients")
    print("  3. أغلق النظام الرئيسي (main_gui.py) لتجنب تعارض الاتصالات")
    print("  4. هذا الاختبار سينشئ اتصالات متعددة حتى يفشل\n")
    
    # استخدام Paper Trading بشكل افتراضي إذا كان sys.argv موجود
    if len(sys.argv) > 1 and sys.argv[1] == "live":
        port = 7496
        print("⚠️⚠️⚠️  تحذير: استخدام Live Trading! ⚠️⚠️⚠️\n")
    else:
        port = 7497
        print("✓ استخدام Paper Trading (Port 7497)\n")
    
    print(f"سيبدأ الاختبار في 3 ثوان...")
    await asyncio.sleep(3)
    
    tester = ConnectionTester()
    await tester.test_connection_limit(port=port)
    
    print("\n✓ انتهى الاختبار بنجاح")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n✗ تم إيقاف البرنامج")
    except Exception as e:
        print(f"\n✗ خطأ غير متوقع: {e}")
