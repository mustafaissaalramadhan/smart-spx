"""
SPX Smart - Configuration File
تكوين النظام الجديد
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==================== Telegram Settings ====================
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
TELEGRAM_CHANNEL_NAME = "SPX SMART"
TELEGRAM_CHANNEL_LINK = "https://t.me/SPXSmartPro"

# ==================== Interactive Brokers Settings ====================
IBKR_HOST = os.getenv('IBKR_HOST', '127.0.0.1')
IBKR_PORT = int(os.getenv('IBKR_PORT', '7497'))  # 7497 for paper, 7496 for live
IBKR_CLIENT_ID = int(os.getenv('IBKR_CLIENT_ID', '10'))
IBKR_READONLY = True  # Always read-only mode

# ==================== Flask/Webhook Settings ====================
FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
FLASK_PORT = int(os.getenv('FLASK_PORT', '5000'))
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', '')

# ==================== Trading Settings ====================
DEFAULT_SYMBOL = 'SPX'  # Default company
SUPPORTED_SYMBOLS = ['SPX', 'NDX', 'SPY', 'QQQ']  # All supported symbols
DEFAULT_WATCHLIST_SYMBOLS = ['SPX', 'SPY', 'QQQ', 'NDX']  # جميع الرموز المدعومة

# Option Search Settings
MIN_OPTION_PRICE = 1.00  # Minimum option price for trading (can adjust from $0.50+)
MAX_OPTION_PRICE = 5.00  # Maximum option price for trading - نطاق الدخول الفعلي
SEARCH_RANGE = 50  # Number of strikes to search
MIN_CONTRACTS_IN_RANGE = 15  # Minimum contracts in range to stop fetching more pages
SELECTION_RANGE_START = 1  # Default: start from 1st contract (for auto trading)
SELECTION_RANGE_END = 4  # Default: end at 4th contract (for auto trading)
SELECTION_MODE = 'highest'  # Options: 'highest', 'lowest', 'closest'

# Duplicate Prevention Settings
MIN_PROFIT_TARGET = 2.00  # Minimum profit ($) required before allowing new trades of same type
FAILED_TRADE_THRESHOLD = 3.00  # Trades below this price are considered failed (ignored in profit check)

# ==================== Watchlist Settings ====================
# Batch Fetching System: Optimized for smart grouping
BATCH_SIZE = 2  # Number of contracts to fetch per batch (2 لتقليل الضغط)
BATCH_DELAY = 1  # Delay (seconds) between batches
SNAPSHOT_WAIT = 1  # Wait time (seconds) for snapshot data per batch

# Symbol-specific contract counts (no pages, single list per symbol)
WATCHLIST_CONTRACTS = {
    'SPX': 30,   # 30 contracts (15 batches of 2) -> 6 groups of 5
    'NDX': 50,   # 50 contracts (25 batches of 2) -> 10 groups of 5
    'SPY': 30,   # 30 contracts (15 batches of 2) -> 6 groups of 5
    'QQQ': 30    # 30 contracts (15 batches of 2) -> 6 groups of 5
}

# ==================== Smart Grouping System ====================
# تقسيم العقود لمجموعات ذكية
GROUP_SIZE = 5  # Each group contains 5 contracts
CONTRACTS_BEFORE_PRICE = 2  # Start fetching 2 contracts before current price
UPDATE_TARGET_GROUPS_ONLY = True  # Update only target groups, not all contracts

# Strike intervals for each symbol
STRIKE_INTERVALS = {
    'SPX': 5,    # SPX: 5 points between strikes (6000, 6005, 6010, ...)
    'NDX': 10,   # NDX: 10 points between strikes (24000, 24010, 24020, ...)
    'SPY': 1,    # SPY: 1 point between strikes (600, 601, 602, ...)
    'QQQ': 1     # QQQ: 1 point between strikes (500, 501, 502, ...)
}

# Start offset: كم strike نبدأ من السعر الحالي
# CALL: ATM + offset صعوداً
# PUT: ATM - offset نزولاً
SEARCH_START_OFFSET = {
    'SPX': 4,    # SPX: نبدأ من 4 strikes بعيداً = 20 نقطة (4×5)
    'NDX': 3,    # NDX: نبدأ من 3 strikes بعيداً = 30 نقطة (3×10)
    'SPY': 15,   # SPY: نبدأ من 15 strikes بعيداً = 15 نقطة (15×1)
    'QQQ': 15    # QQQ: نبدأ من 15 strikes بعيداً = 15 نقطة (15×1)
}

# Update intervals
WATCHLIST_UPDATE_INTERVAL = 1800  # Update contracts every 30 minutes (1800 seconds)
STOCK_PRICE_UPDATE_INTERVAL = 2  # Update stock/index price every 2 seconds
CONTRACT_PRICE_UPDATE_INTERVAL = 15  # Update contract prices every 15 seconds

# Note: Stock price updates cycle through symbols with 0.25s stagger:
# SPX → (0.25s) → NDX → (0.25s) → SPY → (0.25s) → QQQ → (0.25s) → repeat
# Contract prices update separately every 15 seconds

# ==================== Tracking Settings ====================
# ⚡ REAL-TIME STREAMING: Position tracking now uses instant streaming updates (milliseconds)
# TRACKING_UPDATE_INTERVAL is kept for backward compatibility but NOT used in streaming mode
TRACKING_UPDATE_INTERVAL = 0.5  # Legacy setting (NOT USED - streaming is instant!)
POSITION_UPDATE_INTERVAL = 10  # Update account balance every 10 seconds

# ==================== Connection Pool Settings ====================
# Pool اتصالات التتبع لمنع التضارب والبيانات الخاطئة
TRACKING_CONNECTIONS_PER_SYMBOL = 4  # 4 connections per symbol for tracking
MAX_TRADES_PER_CONNECTION = 2  # Maximum 2 trades per connection

# ==================== Simple Watchlist Settings ====================
# نظام المراقبة المبسط - دفعات من 5 عقود
SIMPLE_WATCHLIST_ENABLED = True  # تفعيل النظام المبسط
BATCH_SIZE_SIMPLE = 5  # عدد العقود في كل دفعة
MAX_BATCHES_TO_FETCH = 20  # حد أقصى لدفعات البحث
PRICE_UPDATE_INTERVAL = 2  # تحديث السعر كل ثانيتين
CONTRACTS_UPDATE_INTERVAL = 5  # تحديث أسعار العقود كل 5 ثوان

# نطاقات السعر (Price Ranges) - مبسطة
MONITORING_RANGE_MIN = 1.0  # الحد الأدنى للعرض في الجدول
MONITORING_RANGE_MAX = 7.0  # الحد الأقصى للعرض في الجدول
ENTRY_RANGE_MIN = 1.0  # نطاق الدخول الفعلي للصفقات (من الواجهة الرسومية)
ENTRY_RANGE_MAX = 4.0  # نطاق الدخول الفعلي للصفقات (من الواجهة الرسومية)

# ==================== Old System (Disabled) ====================
# نظام المجموعات الذكية المعقد - معطل
ADAPTIVE_WATCHLIST_ENABLED = False  # ❌ معطل
GROUP_SIZE = 5
MAX_GROUPS_PER_SYMBOL = 20
GROUP_UPDATE_INTERVAL = 5
MAX_CONCURRENT_CONNECTIONS = 8
SMART_START_OFFSET = 2
RESERVE_CONNECTIONS = 2

# Total tracking connections: 4 symbols × 4 connections = 16 main + 2 reserve = 18
# Each connection tracks max 2 trades = 18 × 2 = 36 concurrent trades capacity

# ==================== Entry & Tracking Price Settings ====================
# استخدام سعر العرض (Bid) للدخول وسعر الطلب (Ask) للتتبع
USE_BID_FOR_ENTRY = True  # Use Bid price when entering position
USE_ASK_FOR_TRACKING = True  # Use Ask price when tracking position
PRICE_TYPE_ENTRY = 'bid'  # 'bid' or 'ask' or 'last' or 'midpoint'
PRICE_TYPE_TRACKING = 'ask'  # 'bid' or 'ask' or 'last' or 'midpoint'

# ==================== Risk Management Settings ====================
# Default risk settings (can be customized per symbol)
DEFAULT_RISK_SETTINGS = {
    'stop_loss': {
        'enabled': False,
        'type': 'none',  # 'percentage' or 'amount' or 'none'
        'value': 0
    },
    'trailing_stop': {
        'enabled': False,
        'type': 'none',
        'value': 0
    },
    'capital_protection': {
        'enabled': False,
        'type': 'none',  # Must be above entry price
        'value': 0
    },
    'profit_target': {
        'enabled': False,
        'type': 'none',
        'value': 0
    }
}

# Minimum profit to classify as win
MIN_PROFIT_FOR_WIN = 100.0  # $100

# ==================== Database Settings ====================
DB_PATH = 'spx_smart.db'

# ==================== UI Settings ====================
GUI_TITLE = "SPX Smart"
GUI_THEME = 'dark'  # 'dark' or 'light'
DEFAULT_MODE = 'readonly'  # 'readonly' or 'live'

# Dark Theme Colors
COLORS_DARK = {
    'bg_main': '#0a0e27',
    'bg_card': '#1a1f3a',
    'bg_card_light': '#252b4a',
    'accent_blue': '#00d4ff',
    'accent_green': '#00ff88',
    'accent_red': '#ff3366',
    'accent_yellow': '#ffd700',
    'accent_purple': '#a855f7',
    'text_white': '#ffffff',
    'text_gray': '#b4b4b4',
    'border': '#2a3f5f',
    'profit_bg': '#003322',
    'loss_bg': '#330011',
    'call_color': '#00ff88',
    'put_color': '#ff3366'
}

# Light Theme Colors  
COLORS_LIGHT = {
    'bg_main': '#f5f5f5',
    'bg_card': '#ffffff',
    'bg_card_light': '#f0f0f0',
    'accent_blue': '#0066cc',
    'accent_green': '#00aa44',
    'accent_red': '#cc0033',
    'accent_yellow': '#ff9900',
    'accent_purple': '#7733cc',
    'text_white': '#000000',
    'text_gray': '#666666',
    'border': '#cccccc',
    'profit_bg': '#e6ffe6',
    'loss_bg': '#ffe6e6',
    'call_color': '#00aa44',
    'put_color': '#cc0033'
}

# Get current theme colors
COLORS = COLORS_DARK if GUI_THEME == 'dark' else COLORS_LIGHT

# ==================== Telegram Notifications Settings ====================
TELEGRAM_NOTIFICATIONS = {
    'signal_received': {
        'enabled': True,
        'image': True,
        'text': True
    },
    'trade_preparing': {
        'enabled': True,
        'image': False,
        'text': True
    },
    'contract_found': {
        'enabled': True,
        'image': True,
        'text': True
    },
    'position_opened': {
        'enabled': True,
        'image': True,
        'text': True
    },
    'new_high': {
        'enabled': True,
        'image': True,
        'text': True
    },
    'price_update': {
        'enabled': True,
        'image': False,
        'text': True
    },
    'stop_loss_hit': {
        'enabled': True,
        'image': True,
        'text': True
    },
    'profit_target_hit': {
        'enabled': True,
        'image': True,
        'text': True
    },
    'position_closed': {
        'enabled': True,
        'image': True,
        'text': True
    },
    'partial_close': {
        'enabled': True,
        'image': True,
        'text': True
    },
    'trailing_stop_hit': {
        'enabled': True,
        'image': True,
        'text': True
    },
    'capital_protection_hit': {
        'enabled': True,
        'image': True,
        'text': True
    },
    'duplicate_prevented': {
        'enabled': True,
        'image': False,
        'text': True
    },
    'target_achieved': {
        'enabled': True,
        'image': True,
        'text': True
    },
    'daily_summary': {
        'enabled': True,
        'image': False,
        'text': True
    }
}

# ==================== Image Settings for Telegram ====================
IMG_WIDTH = 1280
IMG_HEIGHT = 540
BG_COLOR = (0, 0, 0)
GREEN_COLOR = (0, 255, 200)
RED_COLOR = (255, 76, 76)
BLUE_COLOR = (0, 150, 255)
GRAY_COLOR = (150, 150, 150)
TEXT_COLOR = (255, 255, 255)

# ==================== Expiry Settings ====================
EXPIRY_TYPE = '0DTE'  # Same day expiry
TRADING_CLASS = 'SPXW'  # SPX Weekly options

# ==================== Logging Settings ====================
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR
LOG_FILE = 'spx_smart.log'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ==================== Currency Settings ====================
CURRENCY_CONVERSION_ENABLED = True  # Enable currency conversion in notifications
SAR_EXCHANGE_RATE = 3.75  # 1 USD = 3.75 SAR (Saudi Riyal)
SHOW_DUAL_CURRENCY = True  # Show both USD and SAR in notifications

# ==================== System Settings ====================
AUTO_START_SYSTEM = False  # Auto-start system when GUI opens (changed to False for stability)
PYTHON_PATH = r"C:\Users\mee1m\AppData\Local\Programs\Python\Python313\python.exe"
