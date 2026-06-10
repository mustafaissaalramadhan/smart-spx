"""
SPX Smart - Advanced Telegram Manager
نظام التيليجرام المتقدم مع دعم الصور والنصوص القابلة للتخصيص
"""
import requests
from telegram import Bot
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Optional, List
import config
import logging
import json
import os

logger = logging.getLogger(__name__)
RIYADH_TZ = ZoneInfo("Asia/Riyadh")

def riyadh_now():
    return datetime.now(RIYADH_TZ)

class TelegramManager:
    def __init__(self):
        self.channels = self._load_channels()
        self.notification_settings = config.TELEGRAM_NOTIFICATIONS.copy()
        self.custom_texts = self._load_custom_texts()
        self.image_settings = self._load_image_settings()
        self.db = None  # Will be set from main if needed
        
    def _load_channels(self) -> Dict:
        """Load telegram channels from database or config"""
        channels = {}  # {symbol: [list of channels]}
        
        print(f"\n{'='*60}")
        print(f"🔄 تحميل قنوات التيليجرام...")
        print(f"{'='*60}")
        
        try:
            # Try to load from database
            from database import DatabaseManager
            db = DatabaseManager()
            db_channels = db.get_all_telegram_channels()
            
            print(f"📊 عدد القنوات في قاعدة البيانات: {len(db_channels)}")
            
            for ch in db_channels:
                symbol = ch['symbol']
                channel_info = {
                    'token': ch['token'],
                    'chat_id': ch['chat_id'],
                    'name': ch.get('channel_name', f"{ch['symbol']} Channel"),
                    'link': ch.get('channel_link', 'https://t.me/channel')  # Add channel link
                }
                
                # Support multiple channels per symbol
                if symbol not in channels:
                    channels[symbol] = []
                channels[symbol].append(channel_info)
                print(f"   ✅ تم تحميل قناة: {channel_info['name']} للرمز: {symbol}")
            
            if channels:
                logger.info(f"Loaded {sum(len(v) for v in channels.values())} channels from database")
                print(f"✅ تم تحميل {sum(len(v) for v in channels.values())} قناة من قاعدة البيانات")
        except Exception as e:
            logger.warning(f"Could not load channels from database: {e}")
            print(f"⚠️ لم يتم العثور على قنوات في قاعدة البيانات: {e}")
        
        # If no channels from database, use default from config
        if not channels:
            print(f"\n📌 استخدام القناة الافتراضية من config.py")
            print(f"   الرمز: {config.DEFAULT_SYMBOL}")
            print(f"   التوكن: {config.TELEGRAM_BOT_TOKEN[:20]}...")
            print(f"   Chat ID: {config.TELEGRAM_CHAT_ID}")
            print(f"   الاسم: {config.TELEGRAM_CHANNEL_NAME}")
            print(f"   الرابط: {config.TELEGRAM_CHANNEL_LINK}")
            
            channels = {
                config.DEFAULT_SYMBOL: [{
                    'token': config.TELEGRAM_BOT_TOKEN,
                    'chat_id': config.TELEGRAM_CHAT_ID,
                    'name': config.TELEGRAM_CHANNEL_NAME,
                    'link': config.TELEGRAM_CHANNEL_LINK
                }]
            }
            logger.info("Using default channel from config")
            print(f"✅ تم تحميل القناة الافتراضية")
        
        print(f"\n📋 ملخص القنوات المُحمّلة:")
        for symbol, channel_list in channels.items():
            print(f"   {symbol}: {len(channel_list)} قناة")
            for ch in channel_list:
                print(f"      - {ch['name']} (Chat: {ch['chat_id']})")
        
        print(f"{'='*60}\n")
        
        return channels
    
    def reload_channels(self):
        """Reload channels from database"""
        self.channels = self._load_channels()
    
    def _load_custom_texts(self) -> Dict:
        """Load custom texts for notifications"""
        texts_file = 'telegram_texts.json'
        
        if os.path.exists(texts_file):
            with open(texts_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Default texts (same as old SPX system)
        return {
            'signal_received': '🔍 <b>إشارة {type} مستلمة</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n📡 النوع: <b>{type}</b>\n⏰ الوقت: {time}\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'contract_found': '✅ <b>عقود {type} متاحة</b>\n\n  الأخير    |   عرض   |   طلب\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'position_opened': '✅ <b>دخول {type}</b>\n━━━━━━━━━━━━━━━━━━━━━━━\nالعقد: <code>{contract}</code>\nStrike: <b>{strike}</b>\nسعر الدخول: <b>{entry_price:.2f} USD</b>\n⏰ الوقت: {time}\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'new_high': '📈 <b>أعلى سعر جديد!</b> ({time})\n━━━━━━━━━━━━━━━━━━━━━━━\nالعقد: <code>{contract}</code>\n━━━━━━━━━━━━━━━━━━━━━━━\n  الأخير    |   عرض   |   طلب\n   <b>{last:.2f}    |   {current_price:.2f}   |   {ask:.2f}</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n📊 سعر الدخول: <b>{entry_price:.2f}</b>\n📈 أعلى سعر: <b>{highest_price:.2f}</b>\n💰 الربح: <b>+{profit:.2f} (+{profit_pct:.1f}%)</b>\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'price_update': '🔄 <b>تحديث مستمر</b> ({time})\n━━━━━━━━━━━━━━━━━━━━━━━\nالعقد: <code>{contract}</code>\n━━━━━━━━━━━━━━━━━━━━━━━\n  الأخير    |   عرض   |   طلب\n   <b>{last:.2f}    |   {current_price:.2f}   |   {ask:.2f}</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n📊 سعر الدخول: <b>{entry_price:.2f}</b>\n📈 أعلى سعر: <b>{highest_price:.2f}</b>\n{profit_emoji} الربح: <b>{profit:+.2f} ({profit_pct:+.1f}%)</b>\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'stop_loss_hit': '🛑 <b>تفعيل وقف الخسارة!</b>\n━━━━━━━━━━━━━━━━━━━━━━━\nسعر {symbol} الحالي: <b>{current_price:.2f}</b>\nوقف الخسارة: <b>{stop_loss:.2f}</b>\nالنوع: <b>{type}</b>\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'profit_target_hit': '🎯 <b>تحقيق الهدف!</b>\n━━━━━━━━━━━━━━━━━━━━━━━\nالعقد: <code>{contract}</code>\n💰 الهدف: <b>{target:.2f}</b>\n💵 السعر الحالي: <b>{current_price:.2f}</b>\n✅ <b>ربح: +{profit:.2f} (+{profit_pct:.1f}%)</b>\n⏰ الوقت: {time}\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'partial_close': '🔄 <b>إغلاق جزئي</b>\n\n{emoji} <code>{contract}</code>\n\n📦 المُغلق: <b>{closed_qty}</b> | المتبقي: <b>{remaining_qty}</b>\n\n💰 <b>${entry_price:.2f}</b> → <b>${exit_price:.2f}</b> (+{profit_pct:.0f}%)\n💵 ربح: <b>${profit_dollars:.0f}</b> | <b>{profit_sar:.0f} ر.س</b>',
            
            'position_closed': '🎯 <b>خروج من {type}</b> - {reason}\n━━━━━━━━━━━━━━━━━━━━━━━\nالعقد: <code>{contract}</code>\n━━━━━━━━━━━━━━━━━━━━━━━\n💵 سعر الدخول: <b>${entry_price:.2f}</b>\n💵 سعر الخروج: <b>${exit_price:.2f}</b>\n📈 أعلى سعر: <b>${highest_price:.2f}</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n{profit_status}\n⏰ الوقت: {time}\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'profit_target_hit': '🎯🎯 <b>ضرب الهدف!</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n{profit_emoji} الربح: <b>${pnl:.2f} ({profit_pct:.1f}%)</b>\n━━━━━━━━━━━━━━━━━━━━━━━\nالعقد: <code>{contract}</code>\n💵 سعر الدخول: <b>${entry_price:.2f}</b>\n💵 سعر الخروج: <b>${exit_price:.2f}</b>\n📈 أعلى سعر: <b>${highest_price:.2f}</b>\n⏰ الوقت: {time}\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'stop_loss_hit': '🛑 <b>وقف الخسارة!</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n❌ الخسارة: <b>${pnl:.2f} ({profit_pct:.1f}%)</b>\n━━━━━━━━━━━━━━━━━━━━━━━\nالعقد: <code>{contract}</code>\n💵 سعر الدخول: <b>${entry_price:.2f}</b>\n💵 سعر الخروج: <b>${exit_price:.2f}</b>\n📈 أعلى سعر: <b>${highest_price:.2f}</b>\n⏰ الوقت: {time}\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'trailing_stop_hit': '📉 <b>وقف الخسارة المتحرك!</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n{profit_emoji} الربح: <b>${pnl:.2f} ({profit_pct:.1f}%)</b>\n━━━━━━━━━━━━━━━━━━━━━━━\nالعقد: <code>{contract}</code>\n💵 سعر الدخول: <b>${entry_price:.2f}</b>\n💵 سعر الخروج: <b>${exit_price:.2f}</b>\n📈 أعلى سعر: <b>${highest_price:.2f}</b>\n💎 نزول من القمة: <b>{drop_from_peak:.1f}%</b>\n⏰ الوقت: {time}\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'capital_protection_hit': '🛡️ <b>حماية رأس المال!</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n✅ تم حماية رأس المال عند ربح {protection_level:.1f}%\n━━━━━━━━━━━━━━━━━━━━━━━\nالعقد: <code>{contract}</code>\n💵 سعر الدخول: <b>${entry_price:.2f}</b>\n💵 سعر الخروج: <b>${exit_price:.2f}</b>\n📈 أعلى سعر: <b>${highest_price:.2f}</b>\n💰 الربح المحقق: <b>${pnl:.2f} (+{profit_pct:.1f}%)</b>\n⏰ الوقت: {time}\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'duplicate_prevented': '⚠️ <b>منع تكرار الصفقة!</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n❌ تم رفض الصفقة\n━━━━━━━━━━━━━━━━━━━━━━━\nالسبب: <b>{reason}</b>\n\n📊 الرمز: {symbol}\n💰 Strike: {strike}\n🔄 النوع: {type}\n\n💡 <i>تم منع الصفقة لحمايتك من:</i>\n• فتح نفس السترايك مرتين\n• عدم تحقيق الربح المستهدف في الصفقات السابقة\n⏰ الوقت: {time}\n━━━━━━━━━━━━━━━━━━━━━━━',
            
            'daily_summary': '📊 <b>ملخص اليوم</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n✅ الأرباح: <b>${total_profit:.2f}</b>\n❌ الخسائر: <b>${total_loss:.2f}</b>\n💰 الصافي: <b>${net_profit:.2f}</b>\n📈 صفقات مربحة: {winning_trades}\n📉 صفقات خاسرة: {losing_trades}\n━━━━━━━━━━━━━━━━━━━━━━━'
        }
    
    def _load_image_settings(self) -> Dict:
        """Load image settings"""
        settings_file = 'image_settings.json'
        
        if os.path.exists(settings_file):
            with open(settings_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Default settings
        return {
            'background_color': config.BG_COLOR,
            'background_image': None,
            'opacity': 100,
            'green_color': config.GREEN_COLOR,
            'red_color': config.RED_COLOR,
            'blue_color': config.BLUE_COLOR
        }
    
    def _convert_to_sar(self, usd_value: float) -> float:
        """Convert USD to SAR"""
        return usd_value * config.SAR_EXCHANGE_RATE
    
    def _format_price_with_currency(self, price: float) -> str:
        """Format price with dual currency if enabled"""
        if config.CURRENCY_CONVERSION_ENABLED and config.SHOW_DUAL_CURRENCY:
            sar_price = self._convert_to_sar(price)
            return f"{price:.2f} USD ({sar_price:.2f} SAR)"
        else:
            return f"{price:.2f} USD"
    
    def test_connection(self) -> bool:
        """Test telegram connection by sending a test message to all channels"""
        print(f"\n{'='*60}")
        print(f"🧪 اختبار اتصال التيليجرام...")
        print(f"{'='*60}")
        
        if not self.channels:
            print(f"❌ لا توجد قنوات مُحمّلة!")
            logger.error("No channels loaded for testing")
            return False
        
        success = False
        
        for symbol, channel_list in self.channels.items():
            for channel in channel_list:
                try:
                    print(f"\n📡 اختبار القناة: {channel['name']} ({symbol})")
                    print(f"   Token: {channel['token'][:20]}...")
                    print(f"   Chat ID: {channel['chat_id']}")
                    
                    url = f"https://api.telegram.org/bot{channel['token']}/sendMessage"
                    payload = {
                        'chat_id': channel['chat_id'],
                        'text': f"✅ اختبار الاتصال\n\nالنظام: SPX Smart\nالقناة: {channel['name']}\nالرمز: {symbol}\nالوقت - الرياض: {riyadh_now().strftime('%Y-%m-%d %H:%M:%S')}",
                        'parse_mode': 'HTML'
                    }
                    
                    response = requests.post(url, json=payload, timeout=10)
                    result = response.json()
                    
                    if result.get('ok'):
                        print(f"   ✅ نجح الإرسال!")
                        logger.info(f"✅ Test message sent to {channel['name']}")
                        success = True
                    else:
                        print(f"   ❌ فشل الإرسال: {result}")
                        logger.error(f"❌ Failed to send test message: {result}")
                        
                except Exception as e:
                    print(f"   ❌ خطأ: {e}")
                    logger.error(f"❌ Error testing channel {channel['name']}: {e}")
                    import traceback
                    traceback.print_exc()
        
        print(f"\n{'='*60}")
        if success:
            print(f"✅ تم اختبار الاتصال بنجاح!")
        else:
            print(f"❌ فشل اختبار الاتصال - تحقق من الإعدادات")
        print(f"{'='*60}\n")
        
        return success
    
    def save_custom_text(self, notification_type: str, text: str):
        """Save custom text for notification"""
        self.custom_texts[notification_type] = text
        
        with open('telegram_texts.json', 'w', encoding='utf-8') as f:
            json.dump(self.custom_texts, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved custom text for {notification_type}")
    
    def save_image_settings(self, settings: Dict):
        """Save image settings"""
        self.image_settings.update(settings)
        
        with open('image_settings.json', 'w', encoding='utf-8') as f:
            json.dump(self.image_settings, f, indent=2)
        
        logger.info("Saved image settings")
    
    def update_notification_setting(self, notification_type: str, enabled: bool = None,
                                   image: bool = None, text: bool = None):
        """Update notification settings"""
        if notification_type in self.notification_settings:
            if enabled is not None:
                self.notification_settings[notification_type]['enabled'] = enabled
            if image is not None:
                self.notification_settings[notification_type]['image'] = image
            if text is not None:
                self.notification_settings[notification_type]['text'] = text
    
    def _create_background(self, width, height):
        """إنشاء خلفية تداول داكنة احترافية"""
        import random
        
        # خلفية أزرق داكن جداً
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
        
        # رسم شموع يابانية شفافة في الخلفية
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

    def create_tracking_image(self, data: Dict, notification_type: str = 'new_high') -> BytesIO:
        """Create professional telegram notification image"""
        try:
            print(f"      🎨 بدء إنشاء صورة التتبع...")
            print(f"      📊 البيانات المستلمة:")
            for key, value in data.items():
                print(f"         {key}: {value} (type: {type(value).__name__})")
            
            # Validate required fields
            required_fields = ['symbol', 'strike', 'current_price', 'entry_price', 'bid', 'ask']
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")
            
            print(f"      ✅ جميع الحقول المطلوبة موجودة")
            
            # إعدادات الصورة
            width = 1024
            height = 600
            
            # إنشاء الخلفية
            print(f"      📐 إنشاء الخلفية ({width}x{height})...")
            img = self._create_background(width, height)
            print(f"      ✅ تم إنشاء الخلفية")
            
            # الألوان - فسفورية مشرقة وبارزة
            text_white = (255, 255, 255)
            
            # تحديد اللون حسب نوع الإشعار
            if notification_type == 'position_opened':
                # عقد مقترح → أحمر
                text_cyan = (255, 70, 120)       # أحمر فسفوري ساطع
            else:
                # تحديث أرباح → أخضر
                text_cyan = (0, 255, 200)        # أخضر فسفوري مشرق
            
            text_green = (50, 255, 100)      # أخضر فسفوري للـ Change/Percent
            text_red = (255, 70, 120)        # أحمر فسفوري ساطع للـ Ask
            text_blue = (120, 220, 255)      # أزرق فسفوري ساطع للـ Bid
            text_gray = (240, 240, 255)      # رمادي مضيء ساطع للـ Mid
            box_bg = (15, 30, 60, 200)       # خلفية الصندوق شفافة
            border_color = (50, 80, 120)     # لون الحدود
        except Exception as e:
            print(f"      ❌ خطأ في التحضير الأولي للصورة: {e}")
            import traceback
            traceback.print_exc()
            raise
        
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
        
        # استخراج البيانات بشكل آمن (مع تحويل الأنواع)
        try:
            current_price = float(data.get('current_price', 0))
            entry_price = float(data.get('entry_price', 0))
            ask = float(data.get('ask', current_price + 0.05))
            bid = float(data.get('bid', current_price))
            mid = float(data.get('mid', (ask + bid) / 2))
            strike = float(data.get('strike', 0))
            
            change = current_price - entry_price
            change_pct = (change / entry_price * 100) if entry_price > 0 else 0
            
            print(f"      📊 البيانات الرقمية:")
            print(f"         current_price: {current_price}")
            print(f"         entry_price: {entry_price}")
            print(f"         bid: {bid}")
            print(f"         ask: {ask}")
            print(f"         mid: {mid}")
            print(f"         strike: {strike}")
            print(f"         change: {change} ({change_pct:.2f}%)")
            
        except (ValueError, TypeError) as e:
            print(f"      ❌ خطأ في تحويل البيانات الرقمية: {e}")
            raise ValueError(f"Invalid numeric data in image creation: {e}")
        
        # عنوان العقد
        symbol = str(data.get('symbol', 'SPXW'))
        expiry = str(data.get('expiry', datetime.now().strftime('%d%b%y').upper()))
        trade_type = str(data.get('type', 'CALL'))
        contract_title = f"{symbol} ${strike:.0f} {expiry} {trade_type}"
        
        print(f"      📝 عنوان العقد: {contract_title}")
        
        # ═══════════════════════════════════════════════════════════════
        # الصندوق الرئيسي
        # ═══════════════════════════════════════════════════════════════
        
        box_x = 60
        box_y = 150
        box_width = 900
        box_height = 300
        
        # عنوان العقد أعلى المستطيل مباشرة
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
        
        # السعر الكبير
        price_text = f"{current_price:.2f}"
        price_bbox = draw.textbbox((0, 0), price_text, font=font_huge)
        price_width = price_bbox[2] - price_bbox[0]
        price_x = left_section_x + (left_section_width - price_width) // 2
        draw.text((price_x, box_y + 40), price_text, fill=text_cyan, font=font_huge)
        
        # خط أفقي رفيع
        line_y = box_y + 170
        draw.line([left_section_x, line_y, left_section_x + left_section_width - 40, line_y],
                 fill=border_color, width=1)
        
        # Change
        change_label = "Change"
        change_value = f"+{change:.2f}" if change >= 0 else f"{change:.2f}"
        change_color = text_green if change >= 0 else text_red
        
        draw.text((left_section_x + 30, box_y + 190), change_label, 
                 fill=text_white, font=font_small)
        
        change_bbox = draw.textbbox((0, 0), change_value, font=font_large)
        change_width = change_bbox[2] - change_bbox[0]
        draw.text((left_section_x + left_section_width - change_width - 30, box_y + 182), 
                 change_value, fill=change_color, font=font_large)
        
        # Percent
        percent_label = "Percent"
        percent_value = f"+{change_pct:.2f}%" if change_pct >= 0 else f"{change_pct:.2f}%"
        
        draw.text((left_section_x + 30, box_y + 240), percent_label, 
                 fill=text_white, font=font_small)
        
        percent_bbox = draw.textbbox((0, 0), percent_value, font=font_large)
        percent_width = percent_bbox[2] - percent_bbox[0]
        draw.text((left_section_x + left_section_width - percent_width - 30, box_y + 232), 
                 percent_value, fill=change_color, font=font_large)
        
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
            fill=(255, 50, 100, 20),
            outline=(200, 50, 50),
            width=3
        )
        draw.text((ask_box_x + 30, ask_y), f"{ask:.2f}", 
                 fill=text_red, font=font_medium)
        
        # Bid (أزرق)
        bid_y = ask_y + right_spacing
        draw.text((right_section_x, bid_y), "Bid", fill=text_white, font=font_medium)
        
        bid_box_x = right_section_x + 150
        draw.rounded_rectangle(
            [bid_box_x, bid_y - 5, bid_box_x + 200, bid_y + 50],
            radius=12,
            fill=(100, 200, 255, 20),
            outline=(50, 100, 200),
            width=3
        )
        draw.text((bid_box_x + 30, bid_y), f"{bid:.2f}", 
                 fill=text_blue, font=font_medium)
        
        # Mid (رمادي)
        mid_y = bid_y + right_spacing
        draw.text((right_section_x, mid_y), "Mid", fill=text_white, font=font_medium)
        
        mid_box_x = right_section_x + 150
        draw.rounded_rectangle(
            [mid_box_x, mid_y - 5, mid_box_x + 200, mid_y + 50],
            radius=12,
            fill=(220, 220, 255, 15),
            outline=(100, 100, 100),
            width=3
        )
        draw.text((mid_box_x + 30, mid_y), f"{mid:.2f}", 
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
        
        # Save to BytesIO
        print(f"      💾 حفظ الصورة كـ PNG...")
        try:
            img_bytes = BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            print(f"      ✅ تم حفظ الصورة بنجاح - الحجم: {len(img_bytes.getvalue())} bytes")
            return img_bytes
        except Exception as e:
            print(f"      ❌ فشل حفظ الصورة: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    async def send_notification(self, notification_type: str, data: Dict, symbol: str = None):
        """Send notification to telegram"""
        try:
            print(f"\n{'='*60}")
            print(f"📤 محاولة إرسال إشعار للتيليجرام")
            print(f"   النوع: {notification_type}")
            print(f"   الرمز: {symbol}")
            print(f"   البيانات: {data}")
            print(f"{'='*60}")
            
            if notification_type not in self.notification_settings:
                print(f"❌ نوع الإشعار غير معروف: {notification_type}")
                logger.warning(f"Unknown notification type: {notification_type}")
                return
            
            settings = self.notification_settings[notification_type]
            print(f"✅ إعدادات الإشعار: {settings}")
            
            if not settings['enabled']:
                print(f"⚠️ الإشعار {notification_type} معطل!")
                logger.info(f"Notification {notification_type} is disabled")
                return
            
            print(f"✅ الإشعار مفعّل")
            
            # Get channel info
            if not symbol:
                symbol = config.DEFAULT_SYMBOL
                print(f"ℹ️ استخدام الرمز الافتراضي: {symbol}")
            
            # First try: exact symbol match
            if symbol in self.channels:
                channels_list = self.channels[symbol]
                print(f"✅ عثر على {len(channels_list)} قناة للرمز {symbol}")
            else:
                # Second try: case-insensitive match
                print(f"⚠️ لم يُعثر على قناة للرمز {symbol} - محاولة البحث...")
                found_symbol = None
                for key in self.channels.keys():
                    if key.upper() == symbol.upper():
                        found_symbol = key
                        break
                
                if found_symbol:
                    channels_list = self.channels[found_symbol]
                    print(f"✅ عثر على {len(channels_list)} قناة للرمز {found_symbol} (case-insensitive)")
                else:
                    # No channel found for this symbol - skip sending
                    print(f"⚠️ لم يُعثر على قناة مطابقة للرمز {symbol}")
                    print(f"   القنوات المتاحة: {list(self.channels.keys())}")
                    print(f"❌ لا توجد قناة مخصصة للرمز {symbol} - لن يتم إرسال الإشعار")
                    logger.warning(f"No channel configured for symbol {symbol} - notification skipped")
                    return
            
            print(f"✅ عدد القنوات: {len(channels_list)}")
            
            # Prepare text
            if settings['text']:
                text_template = self.custom_texts.get(notification_type, '')
                try:
                    # Debug: Show required keys in template
                    import re
                    required_keys = re.findall(r'\{(\w+)', text_template)
                    print(f"📝 المفاتيح المطلوبة في النص: {required_keys}")
                    print(f"📝 المفاتيح المتوفرة في البيانات: {list(data.keys())}")
                    
                    # Check for missing keys
                    missing_keys = [key for key in required_keys if key not in data]
                    if missing_keys:
                        print(f"⚠️ مفاتيح ناقصة: {missing_keys}")
                    
                    text = text_template.format(**data)
                    print(f"✅ النص جاهز ({len(text)} حرف)")
                except KeyError as e:
                    print(f"⚠️ مفتاح ناقص في البيانات: {e}")
                    logger.warning(f"Missing key in notification data: {e}")
                    # Try to format with available data only
                    text = text_template
                except Exception as e:
                    print(f"❌ خطأ في تنسيق النص: {e}")
                    logger.error(f"Error formatting text: {e}")
                    text = None
            else:
                text = None
                print(f"ℹ️ بدون نص")
            
            # Send to all channels for this symbol
            for channel in channels_list:
                try:
                    print(f"\n📡 إرسال لقناة: {channel['name']}")
                    print(f"   Token: {channel['token'][:25]}...")
                    print(f"   Chat ID: {channel['chat_id']}")
                    
                    bot = Bot(token=channel['token'])
                    
                    # Send message
                    if settings['image'] and text:
                        # Send photo with caption
                        print(f"🖼️ إرسال صورة + نص...")
                        print(f"   نوع الإشعار: {notification_type}")
                        print(f"   طول النص: {len(text)} حرف")
                        print(f"   البيانات المتاحة: {list(data.keys())}")
                        print(f"   إنشاء الصورة...")
                        try:
                            image = self.create_tracking_image(data, notification_type)
                            print(f"   ✅ تم إنشاء الصورة بنجاح - الحجم: {len(image.getvalue())} bytes")
                        except Exception as img_error:
                            print(f"   ❌ فشل إنشاء الصورة: {img_error}")
                            print(f"   ⚠️ نوع الخطأ: {type(img_error).__name__}")
                            import traceback
                            traceback.print_exc()
                            # Try sending text only if image fails
                            print(f"   📝 محاولة إرسال النص فقط...")
                            await bot.send_message(
                                chat_id=channel['chat_id'],
                                text=text,
                                parse_mode='HTML'
                            )
                            print(f"   ✅ تم إرسال النص بنجاح")
                            continue
                        
                        print(f"   📤 إرسال الصورة مع النص إلى تيليجرام...")
                        await bot.send_photo(
                            chat_id=channel['chat_id'],
                            photo=image,
                            caption=text,
                            parse_mode='HTML'
                        )
                        print(f"✅✅ تم إرسال الصورة + النص بنجاح")
                    elif settings['image']:
                        # Send photo only
                        print(f"🖼️ إرسال صورة فقط...")
                        print(f"   إنشاء الصورة...")
                        try:
                            image = self.create_tracking_image(data, notification_type)
                            print(f"   ✅ تم إنشاء الصورة بنجاح")
                        except Exception as img_error:
                            print(f"   ❌ فشل إنشاء الصورة: {img_error}")
                            import traceback
                            traceback.print_exc()
                            print(f"   ⚠️ تخطي الإرسال بسبب فشل إنشاء الصورة")
                            continue
                        
                        print(f"   إرسال الصورة...")
                        await bot.send_photo(
                            chat_id=channel['chat_id'],
                            photo=image
                        )
                        print(f"✅ تم إرسال الصورة")
                    elif text:
                        # Send text only
                        print(f"📝 إرسال نص فقط...")
                        await bot.send_message(
                            chat_id=channel['chat_id'],
                            text=text,
                            parse_mode='HTML'
                        )
                        print(f"✅ تم إرسال النص")
                    
                    print(f"✅✅ تم الإرسال بنجاح إلى {channel['name']}")
                    logger.info(f"✅ Sent {notification_type} to {channel['name']} ({symbol})")
                    
                except Exception as e:
                    print(f"❌ خطأ في الإرسال لـ {channel['name']}: {e}")
                    logger.error(f"❌ Error sending to {channel['name']}: {e}")
                    import traceback
                    traceback.print_exc()
            
            print(f"\n{'='*60}")
            print(f"✅ انتهى إرسال الإشعارات")
            print(f"{'='*60}\n")
            
        except Exception as e:
            print(f"❌ خطأ عام في إرسال الإشعار: {e}")
            logger.error(f"❌ Error sending notification: {e}")
            import traceback
            traceback.print_exc()
    
    def add_channel(self, symbol: str, token: str, chat_id: str, name: str):
        """Add new telegram channel"""
        channel_info = {
            'token': token,
            'chat_id': chat_id,
            'name': name
        }
        
        # Support multiple channels per symbol
        if symbol not in self.channels:
            self.channels[symbol] = []
        self.channels[symbol].append(channel_info)
        logger.info(f"Added channel for {symbol}")
    
    def send_notification_sync(self, notification_type: str, data: Dict, symbol: str = None, async_loop = None):
        """Send notification synchronously (wrapper for async send_notification)
        
        Args:
            async_loop: The async event loop from GUI (if available)
        """
        import asyncio
        import concurrent.futures
        import threading
        
        try:
            print(f"\n🔔 send_notification_sync called: {notification_type} for {symbol}")
            print(f"   async_loop provided: {async_loop is not None}")
            
            # Use provided loop from GUI if available
            if async_loop and not async_loop.is_closed():
                print(f"✅ Using provided async loop from GUI")
                try:
                    # Run in event loop from another thread (GUI thread → async thread)
                    future = asyncio.run_coroutine_threadsafe(
                        self.send_notification(notification_type, data, symbol),
                        async_loop
                    )
                    
                    # Wait for result with timeout
                    future.result(timeout=10)  # 10 second timeout
                    print(f"✅ Notification sent successfully via threadsafe coroutine")
                    return
                except concurrent.futures.TimeoutError:
                    print(f"❌ Timeout sending notification after 10 seconds")
                    logger.error(f"Timeout sending {notification_type} notification")
                except Exception as e:
                    print(f"❌ Error in threadsafe coroutine: {e}")
                    logger.error(f"Error in threadsafe coroutine: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Fallback: Create new thread with its own event loop
            print(f"⚠️ No async loop available - creating new thread with event loop")
            
            def run_in_thread():
                """Run notification in separate thread with its own event loop"""
                try:
                    # Create new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Run the notification
                    loop.run_until_complete(self.send_notification(notification_type, data, symbol))
                    
                    # Close the loop
                    loop.close()
                    print(f"✅ Notification sent successfully in new thread")
                    
                except Exception as e:
                    print(f"❌ Error in notification thread: {e}")
                    logger.error(f"Error in notification thread: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Start thread and wait for completion
            thread = threading.Thread(target=run_in_thread, daemon=True)
            thread.start()
            thread.join(timeout=15)  # Wait up to 15 seconds
            
            if thread.is_alive():
                print(f"⚠️ Notification thread still running after 15 seconds")
                    
        except Exception as e:
            print(f"❌ Error in send_notification_sync: {e}")
            logger.error(f"Error in send_notification_sync: {e}")
            import traceback
            traceback.print_exc()
    
    def get_tradingview_commands(self) -> Dict[str, str]:
        """Get TradingView webhook commands for each symbol"""
        commands = {}
        
        # Generate commands for all supported symbols
        for symbol in config.SUPPORTED_SYMBOLS:
            commands[f'CALL {symbol}'] = f'{{"type": "CALL", "symbol": "{symbol}"}}'
            commands[f'PUT {symbol}'] = f'{{"type": "PUT", "symbol": "{symbol}"}}'
        
        return commands
    
    # ==================== Simple Text-Based Messages (from old system) ====================
    
    def send_simple_message(self, text: str, parse_mode: str = "HTML"):
        """Send a simple text message using requests (lightweight)"""
        try:
            token = config.TELEGRAM_BOT_TOKEN
            chat_id = config.TELEGRAM_CHAT_ID
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            
            payload = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.json()
        except Exception as e:
            logger.error(f"Error sending simple telegram message: {e}")
            return None
    
    def send_alert_message(self, message: str):
        """Send alert message to all active telegram channels"""
        try:
            # Get all channels from database
            if self.db:
                db_channels = self.db.get_all_telegram_channels()
                
                if not db_channels:
                    logger.warning("No telegram channels found in database")
                    return
                
                # Send to each channel
                success_count = 0
                for channel in db_channels:
                    try:
                        token = channel['token']
                        chat_id = channel['chat_id']
                        
                        url = f"https://api.telegram.org/bot{token}/sendMessage"
                        
                        sent_at = riyadh_now().strftime('%Y-%m-%d %H:%M:%S')
                        payload = {
                            'chat_id': chat_id,
                            'text': f"{message}\n\nوقت السعودية - الرياض: {sent_at}",
                            'parse_mode': 'HTML'
                        }
                        
                        response = requests.post(url, json=payload, timeout=10)
                        
                        if response.status_code == 200:
                            success_count += 1
                            logger.info(f"Alert sent to {channel['symbol']} channel")
                        else:
                            logger.error(f"Failed to send alert to {channel['symbol']}: {response.text}")
                    
                    except Exception as e:
                        logger.error(f"Error sending alert to channel {channel.get('symbol', 'unknown')}: {e}")
                
                logger.info(f"Alert sent to {success_count}/{len(db_channels)} channels")
            
            else:
                # Fallback to default config if no database
                token = config.TELEGRAM_BOT_TOKEN
                chat_id = config.TELEGRAM_CHAT_ID
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                
                sent_at = riyadh_now().strftime('%Y-%m-%d %H:%M:%S')
                payload = {
                    'chat_id': chat_id,
                    'text': f"{message}\n\nوقت السعودية - الرياض: {sent_at}",
                    'parse_mode': 'HTML'
                }
                
                response = requests.post(url, json=payload, timeout=10)
                logger.info(f"Alert sent using default config: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Error sending telegram alert: {e}")
    
    def format_options_list(self, options: List[Dict], option_type: str) -> str:
        """Format options list similar to IBKR display"""
        title = "خيارات الشراء CALL" if option_type == "CALL" else "خيارات البيع PUT"
        
        message = f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"<b>{title}</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"  الأخير    |   عرض   |   طلب\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        for opt in options:
            last = opt.get('last', 0.0)
            bid = opt.get('bid', 0.0)
            ask = opt.get('ask', 0.0)
            change_pct = opt.get('change_percent', 0.0)
            bid_vol = opt.get('bid_volume', 0)
            ask_vol = opt.get('ask_volume', 0)
            strike = opt.get('strike', 0)
            
            message += f"<b>   {last:.2f}    |   {bid:.2f}   |   {ask:.2f}</b>\n"
            message += f"  <i>{change_pct:+.2f}%  |    {bid_vol}    |    {ask_vol}</i>\n"
            message += f"  Strike: {strike}\n\n"
        
        message += f"━━━━━━━━━━━━━━━━━━━━━━━"
        
        return message
    
    def send_options_alert(self, options: List[Dict], option_type: str):
        """Send options information alert"""
        message = f"🔍 <b>عقود {option_type} متاحة</b>\n\n"
        message += self.format_options_list(options, option_type)
        
        return self.send_simple_message(message)
    
    def send_entry_alert(self, trade_info: Dict):
        """Send entry alert"""
        option_type = trade_info.get('type', 'CALL')
        emoji = "✅" if option_type == "CALL" else "🔻"
        
        message = f"{emoji} <b>دخول {option_type}</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"العقد: <code>{trade_info.get('symbol', 'N/A')}</code>\n"
        message += f"Strike: <b>{trade_info.get('strike', 0)}</b>\n"
        message += f"سعر الدخول: <b>{trade_info.get('entry_price', 0):.2f} USD</b>\n"
        message += f"🛑 وقف الخسارة: <b>{trade_info.get('stop_loss', 0):.2f}</b> على SPX\n"
        message += f"⏰ الوقت: {trade_info.get('time', 'N/A')}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━"
        
        return self.send_simple_message(message)
    
    def send_price_update(self, update_info: Dict):
        """Send price update for open position"""
        option_type = update_info.get('type', 'CALL')
        is_new_high = update_info.get('is_new_high', False)
        
        emoji = "📈" if is_new_high else "🔄"
        title = "أعلى سعر جديد!" if is_new_high else "تحديث مستمر"
        
        entry_price = update_info.get('entry_price', 0)
        current_price = update_info.get('current_price', 0)
        highest_price = update_info.get('highest_price', 0)
        profit = current_price - entry_price
        profit_pct = (profit / entry_price * 100) if entry_price > 0 else 0
        
        message = f"{emoji} <b>{title}</b> ({update_info.get('time', 'N/A')})\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"العقد: <code>{update_info.get('symbol', 'N/A')}</code>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"  الأخير    |   عرض   |   طلب\n"
        message += f"   <b>{update_info.get('last', 0):.2f}    |   {current_price:.2f}   |   {update_info.get('ask', 0):.2f}</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"📊 سعر الدخول: <b>{entry_price:.2f}</b>\n"
        message += f"📈 أعلى سعر: <b>{highest_price:.2f}</b>\n"
        
        profit_emoji = "💰" if profit >= 0 else "📉"
        message += f"{profit_emoji} الربح: <b>{profit:+.2f} ({profit_pct:+.1f}%)</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━"
        
        return self.send_simple_message(message)
    
    def send_exit_alert(self, exit_info: Dict):
        """Send exit alert"""
        option_type = exit_info.get('type', 'CALL')
        reason = exit_info.get('reason', 'SIGNAL')
        
        entry_price = exit_info.get('entry_price', 0)
        exit_price = exit_info.get('exit_price', 0)
        highest_price = exit_info.get('highest_price', 0)
        profit = exit_price - entry_price
        profit_pct = (profit / entry_price * 100) if entry_price > 0 else 0
        
        emoji = "🎯" if reason == "SIGNAL" else "🛑"
        reason_text = "إشارة خروج" if reason == "SIGNAL" else "وقف خسارة"
        
        message = f"{emoji} <b>خروج من {option_type}</b> - {reason_text}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"العقد: <code>{exit_info.get('symbol', 'N/A')}</code>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"💵 سعر الدخول: <b>{entry_price:.2f}</b>\n"
        message += f"💵 سعر الخروج: <b>{exit_price:.2f}</b>\n"
        message += f"📈 أعلى سعر: <b>{highest_price:.2f}</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        if profit >= 0:
            message += f"✅ <b>ربح: +{profit:.2f} (+{profit_pct:.1f}%)</b>\n"
        else:
            message += f"❌ <b>خسارة: {profit:.2f} ({profit_pct:.1f}%)</b>\n"
        
        message += f"⏰ الوقت: {exit_info.get('time', 'N/A')}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━"
        
        return self.send_simple_message(message)
    
    def send_stop_loss_alert(self, spx_price: float, stop_loss: float, option_type: str):
        """Send stop loss triggered alert"""
        message = f"🛑 <b>تفعيل وقف الخسارة!</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"سعر SPX الحالي: <b>{spx_price:.2f}</b>\n"
        message += f"وقف الخسارة: <b>{stop_loss:.2f}</b>\n"
        message += f"النوع: <b>{option_type}</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━"
        
        return self.send_simple_message(message)
    
    def send_error_alert(self, error_message: str):
        """Send error alert"""
        message = f"⚠️ <b>تنبيه خطأ</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"{error_message}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━━━━"
        
        return self.send_simple_message(message)
