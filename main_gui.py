"""
SPX Smart - Main GUI
الواجهة الرسومية الكاملة
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
try:
    from tkcalendar import Calendar
    CALENDAR_AVAILABLE = True
    print("✅ مكتبة التقويم (tkcalendar) جاهزة ومثبتة بنجاح!")
except ImportError:
    CALENDAR_AVAILABLE = False
    print("⚠️ تحذير: مكتبة tkcalendar غير مثبتة - سيتم استخدام إدخال التاريخ اليدوي")
    print("   لتثبيت المكتبة، شغّل: pip install tkcalendar")
from datetime import datetime, timedelta
import asyncio
import threading
import time
import sqlite3
import os
import config
from database import DatabaseManager
from trading_system import TradingSystem
from telegram_manager import TelegramManager
import webhook_server
from adaptive_watchlist import AdaptiveWatchlistMaster
from simple_watchlist import SimpleWatchlistManager  # النظام المبسط الجديد
import logging
from logging.handlers import RotatingFileHandler

# Setup logging with rotation (max 10MB per file, keep 3 backups)
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT,
    handlers=[
        RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=10*1024*1024,   # 10 MB حد أقصى لكل ملف
            backupCount=3,           # 3 نسخ احتياطية (spx_smart.log.1, .2, .3)
            encoding='utf-8'
        )
    ]
)

logger = logging.getLogger(__name__)


class ModernButton(tk.Button):
    """Custom button with hover effect"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.defaultBackground = self["background"]
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)

    def on_enter(self, e):
        self['background'] = self['activebackground']

    def on_leave(self, e):
        self['background'] = self.defaultBackground

class SPXSmartGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"SPX Smart - نظام تداول احترافي")
        self.root.geometry("1100x900")
        
        # System components
        self.db = DatabaseManager()
        
        # Reset all risk settings to NONE on startup
        self.db.reset_all_risk_settings()
        
        self.trading_system = TradingSystem()
        self.trading_system.gui_instance = self  # Link GUI for fast watchlist access
        self.telegram = TelegramManager()
        self.telegram.db = self.db  # Link database to telegram manager for alerts
        
        # Simple watchlist system (النظام المبسط)
        self.simple_watchlist = None  # Will be initialized when system starts
        
        # Adaptive watchlist system (النظام المعقد - معطل)
        self.adaptive_master = None  # Will be initialized when system starts
        
        # Print loaded telegram channels for debugging
        print(f"\n{'='*60}")
        print(f"📱 قنوات التيليجرام المُحمّلة عند بدء البرنامج:")
        for symbol, channels in self.telegram.channels.items():
            print(f"   {symbol}: {len(channels)} قناة")
            for ch in channels:
                print(f"      - {ch['name']} (Chat: {ch['chat_id'][:20]}...)")
        print(f"{'='*60}\n")
        
        # Note: webhook_server.set_gui will be called in start_system
        # after event loop is created
        
        # Variables
        self.watchlist_data = {'CALL': [], 'PUT': []}  # Legacy for webhooks
        self.watchlist_contracts = {}  # Store contracts per symbol: {symbol: {'CALL': [...], 'PUT': [...]}}
        self.last_page_update = {}  # Store last contract update time: {symbol: timestamp}
        self.watchlist_widgets = {}  # Initialize watchlist widgets dict
        self.selected_expiry_dates = {}  # Store selected expiry date for each symbol (default: None = 0DTE)
        self.update_tasks_running = False
        self.system_running = False
        self.async_loop = None  # Store the async event loop
        self.async_thread = None  # Store the async thread
        self.alert_check_running = False  # Alert checker status
        self.active_tracking = {}  # Track active auto-tracking: {contract_key: stop_flag}
        self.current_contract_quantity = 1  # Default: 1 contract per trade
        self.watchlist_contracts = {}  # Store qualified contracts from watchlist: {symbol: {option_type: {strike: contract}}}
        self.stock_countdown = {}  # Countdown timer for stock price updates (per symbol)
        self.contract_countdown = {}  # Countdown timer for contract price updates (per symbol)
        
        # Colors
        self.colors = config.COLORS
        self.root.configure(bg=self.colors['bg_main'])
        
        # Setup UI
        self.setup_styles()
        self.create_ui()
        
        # Load telegram channels
        self.load_telegram_channels()
        
        # Set close window handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Auto-start if enabled
        if config.AUTO_START_SYSTEM:
            self.root.after(1000, self.start_system)
    
    def format_contract_name(self, contract_str):
        """
        Format contract string to simplified readable name
        Input formats:
          1. "Option(conId=850544545, symbol='SPX', lastTradeDateOrContractMonth='20260304', strike=6880.0, right='C', ...)"
          2. "SPX 6845 CALL" (from manual trading)
        Output: "SPX $6880 CALL" (simplified - no date)
        """
        try:
            if not contract_str or contract_str == 'N/A':
                return 'N/A'
            
            # If already in simplified format, return as is
            if '$' in contract_str and len(contract_str.split()) == 3:
                return contract_str
            
            # Case 1: Simple format from manual trading "SPX 6845 CALL"
            if 'Option(' not in contract_str:
                parts = contract_str.split()
                if len(parts) >= 3:
                    symbol = parts[0]
                    strike = parts[1]
                    trade_type = parts[2]
                    
                    # Use original symbol (SPX, NDX, SPY, QQQ - no W or P suffix)
                    return f"{symbol} ${strike} {trade_type}"
                return contract_str
            
            # Case 2: Full Option object string
            # Extract details from Option string
            import re
            
            # Extract symbol
            symbol_match = re.search(r"symbol='([^']+)'", contract_str)
            symbol = symbol_match.group(1) if symbol_match else 'SPX'
            
            # Extract strike
            strike_match = re.search(r"strike=([\d.]+)", contract_str)
            strike = float(strike_match.group(1)) if strike_match else 0
            
            # Extract right (C/P)
            right_match = re.search(r"right='([CP])'", contract_str)
            if right_match:
                right = 'CALL' if right_match.group(1) == 'C' else 'PUT'
            else:
                right = 'CALL'
            
            # Format: SPX $6880 CALL (simplified - no date, no W/P suffix)
            return f"{symbol} ${int(strike)} {right}"
            
        except Exception as e:
            logger.error(f"Error formatting contract name: {e}")
            return contract_str
    
    def format_strike_only(self, contract_str):
        """
        Extract only strike price from contract
        Input formats:
          1. "Option(...strike=6880.0...)"
          2. "SPXW $6880 04 MAR 26 CALL"
          3. "SPX 6845 CALL" (manual trading)
        Output: "6880"
        """
        try:
            if not contract_str or contract_str == 'N/A':
                return 'N/A'
            
            # If contains $, extract number after $
            if '$' in contract_str:
                import re
                match = re.search(r'\$(\d+)', contract_str)
                if match:
                    return match.group(1)
            
            # If Option string, extract strike
            if 'strike=' in contract_str:
                import re
                match = re.search(r'strike=([\d.]+)', contract_str)
                if match:
                    return str(int(float(match.group(1))))
            
            # If simple format "SPX 6845 CALL", extract middle number
            parts = contract_str.split()
            if len(parts) >= 2:
                try:
                    # Try to parse second part as number
                    strike = int(float(parts[1]))
                    return str(strike)
                except:
                    pass
            
            return contract_str
            
        except Exception as e:
            logger.error(f"Error extracting strike: {e}")
            return contract_str
    
    def show_auto_close_message(self, title, message, msg_type='info', duration=3, parent=None):
        """
        Show message using standard messagebox (reverted from auto-close)
        """
        if msg_type == 'warning':
            messagebox.showwarning(title, message, parent=parent)
        elif msg_type == 'error':
            messagebox.showerror(title, message, parent=parent)
        else:  # info
            messagebox.showinfo(title, message, parent=parent)
    
    def setup_styles(self):
        """Setup TTK styles"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure styles for dark theme
        style.configure('Card.TLabelframe',
                       background=self.colors['bg_card'],
                       bordercolor=self.colors['accent_blue'],
                       borderwidth=2)
        style.configure('Card.TLabelframe.Label',
                       background=self.colors['bg_card'],
                       foreground=self.colors['accent_blue'],
                       font=('Arial', 11, 'bold'))
        
        style.configure('Treeview',
                       background=self.colors['bg_card_light'],
                       foreground=self.colors['text_white'],
                       fieldbackground=self.colors['bg_card_light'],
                       font=('Consolas', 9))
        style.map('Treeview', background=[('selected', self.colors['accent_blue'])])
        style.configure('Treeview.Heading',
                       background=self.colors['bg_card'],
                       foreground=self.colors['accent_blue'],
                       font=('Arial', 9, 'bold'))
    
    def create_ui(self):
        """Create the complete UI"""
        # Main container with scrollbar
        main_canvas = tk.Canvas(self.root, bg=self.colors['bg_main'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)
        scrollable_frame = tk.Frame(main_canvas, bg=self.colors['bg_main'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # ✅ دعم عجلة الفأرة للتمرير
        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def _bind_mousewheel(widget):
            """ربط عجلة الفأرة بالعنصر وجميع أبنائه"""
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Enter>", lambda e: main_canvas.bind_all("<MouseWheel>", _on_mousewheel))
            widget.bind("<Leave>", lambda e: main_canvas.unbind_all("<MouseWheel>"))
        
        _bind_mousewheel(main_canvas)
        _bind_mousewheel(scrollable_frame)
        
        # حفظ الدالة لاستخدامها لاحقاً مع العناصر الجديدة
        self._bind_mousewheel = _bind_mousewheel
        self.main_canvas = main_canvas
        
        # Header
        self.create_header(scrollable_frame)
        
        # Main content - Single column (vertical layout)
        main_content = tk.Frame(scrollable_frame, bg=self.colors['bg_main'])
        main_content.pack(fill='both', expand=True, padx=10, pady=5)
        
        # All sections in one column
        self.create_system_controls(main_content)
        self.create_telegram_section(main_content)
        self.create_watchlist_section(main_content)
        self.create_risk_management(main_content)
        self.create_active_trades_section(main_content)
        self.create_trade_history_section(main_content)
        self.create_summary_section(main_content)
        self.create_cleanup_section(main_content)
        self.create_status_bar(scrollable_frame)
    
    def create_header(self, parent):
        """Create header"""
        header = tk.Frame(parent, bg=self.colors['bg_card'], height=80)
        header.pack(fill='x', padx=10, pady=10)
        
        title = tk.Label(header, text="SPX Smart",
                        font=('Arial', 28, 'bold'),
                        bg=self.colors['bg_card'],
                        fg=self.colors['accent_blue'])
        title.pack(side='left', padx=20, pady=20)
        
        subtitle = tk.Label(header, text="نظام تداول الخيارات الاحترافي",
                           font=('Arial', 14),
                           bg=self.colors['bg_card'],
                           fg=self.colors['text_gray'])
        subtitle.pack(side='left', padx=10, pady=20)
        
        # Connection counter
        conn_frame = tk.Frame(header, bg=self.colors['bg_card_light'],
                             relief='solid', borderwidth=2, padx=10, pady=5)
        conn_frame.pack(side='right', padx=10, pady=20)
        
        tk.Label(conn_frame, text="🔗",
                font=('Arial', 14),
                bg=self.colors['bg_card_light'],
                fg=self.colors['accent_blue']).pack(side='left', padx=2)
        
        self.connection_label = tk.Label(conn_frame, text="0",
                                        font=('Arial', 14, 'bold'),
                                        bg=self.colors['bg_card_light'],
                                        fg=self.colors['accent_green'])
        self.connection_label.pack(side='left', padx=2)
        
        tk.Label(conn_frame, text="IBKR",
                font=('Arial', 10),
                bg=self.colors['bg_card_light'],
                fg=self.colors['text_gray']).pack(side='left', padx=2)
        
        time_label = tk.Label(header, text="",
                             font=('Arial', 12),
                             bg=self.colors['bg_card'],
                             fg=self.colors['text_gray'])
        time_label.pack(side='right', padx=20, pady=20)
        self.time_label = time_label
        self.update_time()
    
    def update_time(self):
        """Update time display"""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.time_label.config(text=f"⏰ {current_time}")
        
        # Update connection counter
        self.update_connection_counter()
        
        self.root.after(1000, self.update_time)
    
    def update_connection_counter(self):
        """Update IBKR connection counter"""
        try:
            # Count active tracking threads
            active_count = len([k for k, v in self.active_tracking.items() if not v.is_set()])
            
            # Update label
            if hasattr(self, 'connection_label'):
                self.connection_label.config(text=str(active_count))
                
                # Change color based on count
                if active_count == 0:
                    self.connection_label.config(fg=self.colors['text_gray'])
                elif active_count < 5:
                    self.connection_label.config(fg=self.colors['accent_green'])
                elif active_count < 10:
                    self.connection_label.config(fg=self.colors['accent_yellow'])
                else:
                    self.connection_label.config(fg=self.colors['accent_red'])
        except Exception as e:
            logger.error(f"Error updating connection counter: {e}")
    
    def create_system_controls(self, parent):
        """Create system controls section with new organized layout"""
        frame = tk.LabelFrame(parent, text="⚙️ التحكم بالنظام",
                             bg=self.colors['bg_card'],
                             fg=self.colors['accent_green'],
                             font=('Arial', 11, 'bold'),
                             borderwidth=2, relief='solid')
        frame.pack(fill='x', pady=5)
        
        # Main container with three sections
        main_container = tk.Frame(frame, bg=self.colors['bg_card'])
        main_container.pack(fill='x', padx=10, pady=10)
        
        # ═══════════════════════════════════════════════════════════
        # SECTION 1: SYSTEM CONTROL (LEFT) - 2x2 Grid
        # ═══════════════════════════════════════════════════════════
        control_section = tk.Frame(main_container, bg=self.colors['bg_card'])
        control_section.pack(side='left', fill='y', padx=(0, 15))
        
        # Row 1: Start + IBKR
        row1 = tk.Frame(control_section, bg=self.colors['bg_card'])
        row1.pack(fill='x', pady=(0, 5))
        
        # Start Button (Top Left)
        self.start_btn = ModernButton(row1, text="▶️ تشغيل",
                                      command=self.start_system,
                                      bg=self.colors['accent_green'], fg='black',
                                      activebackground='#00cc66',
                                      font=('Arial', 9, 'bold'),
                                      relief='raised', bd=3, padx=15, pady=10,
                                      cursor='hand2')
        self.start_btn.pack(side='left', padx=(0, 5))
        
        # IBKR Connection Status (Top Right)
        ibkr_status_frame = tk.Frame(row1, bg=self.colors['bg_card_light'],
                                     relief='solid', borderwidth=2)
        ibkr_status_frame.pack(side='left')
        
        tk.Label(ibkr_status_frame, text="IBKR",
                bg=self.colors['bg_card_light'], fg=self.colors['text_gray'],
                font=('Arial', 8, 'bold')).pack(padx=8, pady=2)
        
        self.ibkr_status_indicator = tk.Canvas(ibkr_status_frame, width=25, height=25,
                                               bg=self.colors['bg_card_light'],
                                               highlightthickness=0)
        self.ibkr_status_indicator.pack(padx=8, pady=2)
        
        # Draw red circle (disconnected by default)
        self.ibkr_circle = self.ibkr_status_indicator.create_oval(4, 4, 21, 21,
                                                                   fill=self.colors['accent_red'],
                                                                   outline='')
        
        self.ibkr_status_text = tk.Label(ibkr_status_frame, text="غير متصل",
                                         bg=self.colors['bg_card_light'],
                                         fg=self.colors['accent_red'],
                                         font=('Arial', 7, 'bold'))
        self.ibkr_status_text.pack(padx=8, pady=2)
        
        # Row 2: Stop + Balance
        row2 = tk.Frame(control_section, bg=self.colors['bg_card'])
        row2.pack(fill='x')
        
        # Stop Button (Bottom Left)
        self.stop_btn = ModernButton(row2, text="⏸️ إيقاف",
                                     command=self.stop_system,
                                     bg=self.colors['accent_red'], fg='white',
                                     activebackground='#cc0044',
                                     font=('Arial', 9, 'bold'),
                                     relief='raised', bd=3, padx=15, pady=10,
                                     cursor='hand2', state='disabled')
        self.stop_btn.pack(side='left', padx=(0, 5))
        
        # Balance Display (Bottom Right)
        balance_frame = tk.Frame(row2, bg=self.colors['profit_bg'],
                                relief='solid', borderwidth=2)
        balance_frame.pack(side='left')
        
        tk.Label(balance_frame, text="💰 الرصيد",
                bg=self.colors['profit_bg'], fg=self.colors['accent_green'],
                font=('Arial', 7, 'bold')).pack(padx=8, pady=2)
        
        self.balance_label = tk.Label(balance_frame, text="$0.00",
                                      bg=self.colors['profit_bg'],
                                      fg=self.colors['accent_green'],
                                      font=('Arial', 11, 'bold'))
        self.balance_label.pack(padx=8, pady=2)
        
        # Separator 1
        tk.Frame(main_container, bg=self.colors['border'], width=3).pack(side='left', fill='y', padx=10)
        
        # ═══════════════════════════════════════════════════════════
        # SECTION 2: PRICE RANGE (MIDDLE) - DUAL RANGES
        # ═══════════════════════════════════════════════════════════
        range_section = tk.Frame(main_container, bg=self.colors['bg_card'])
        range_section.pack(side='left', fill='both', expand=False, padx=10)
        
        # Title
        tk.Label(range_section, text="💰 إعدادات النطاق السعري",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(pady=(0, 5))
        
        # ─────────────────────────────────────────────────────────
        # MONITORING RANGE (for display and updates)
        # ─────────────────────────────────────────────────────────
        monitor_frame = tk.Frame(range_section, bg=self.colors['bg_card_light'],
                                relief='solid', borderwidth=1)
        monitor_frame.pack(fill='x', pady=5)
        
        tk.Label(monitor_frame, text="📊 نطاق المتابعة والتحديث",
                bg=self.colors['bg_card_light'], fg=self.colors['accent_blue'],
                font=('Arial', 9, 'bold')).pack(pady=3)
        
        # Min monitoring
        mon_min_row = tk.Frame(monitor_frame, bg=self.colors['bg_card_light'])
        mon_min_row.pack(fill='x', pady=2)
        
        tk.Label(mon_min_row, text="من $",
                bg=self.colors['bg_card_light'], fg=self.colors['text_gray'],
                font=('Arial', 8)).pack(side='left', padx=5)
        
        self.monitoring_range_min = tk.Spinbox(mon_min_row, from_=0.50, to=20.00, increment=0.50, width=6,
                                              bg='white',
                                              fg=self.colors['accent_blue'],
                                              font=('Arial', 9, 'bold'),
                                              format="%.2f")
        self.monitoring_range_min.delete(0, 'end')
        self.monitoring_range_min.insert(0, f"{config.MONITORING_RANGE_MIN:.2f}")
        self.monitoring_range_min.pack(side='left', padx=3)
        
        tk.Label(mon_min_row, text="إلى $",
                bg=self.colors['bg_card_light'], fg=self.colors['text_gray'],
                font=('Arial', 8)).pack(side='left', padx=5)
        
        self.monitoring_range_max = tk.Spinbox(mon_min_row, from_=0.50, to=20.00, increment=0.50, width=6,
                                              bg='white',
                                              fg=self.colors['accent_blue'],
                                              font=('Arial', 9, 'bold'),
                                              format="%.2f")
        self.monitoring_range_max.delete(0, 'end')
        self.monitoring_range_max.insert(0, f"{config.MONITORING_RANGE_MAX:.2f}")
        self.monitoring_range_max.pack(side='left', padx=3)
        
        tk.Label(monitor_frame, text="(العقود التي ستظهر بالجدول)",
                bg=self.colors['bg_card_light'], fg=self.colors['text_gray'],
                font=('Arial', 7, 'italic')).pack(pady=2)
        
        # ─────────────────────────────────────────────────────────
        # ENTRY RANGE (for actual trades)
        # ─────────────────────────────────────────────────────────
        entry_frame = tk.Frame(range_section, bg=self.colors['profit_bg'],
                              relief='solid', borderwidth=1)
        entry_frame.pack(fill='x', pady=5)
        
        tk.Label(entry_frame, text="🎯 نطاق الدخول الفعلي",
                bg=self.colors['profit_bg'], fg=self.colors['accent_green'],
                font=('Arial', 9, 'bold')).pack(pady=3)
        
        # Min entry
        entry_min_row = tk.Frame(entry_frame, bg=self.colors['profit_bg'])
        entry_min_row.pack(fill='x', pady=2)
        
        tk.Label(entry_min_row, text="من $",
                bg=self.colors['profit_bg'], fg=self.colors['text_gray'],
                font=('Arial', 8)).pack(side='left', padx=5)
        
        self.entry_range_min = tk.Spinbox(entry_min_row, from_=0.50, to=20.00, increment=0.50, width=6,
                                          bg='white',
                                          fg=self.colors['accent_green'],
                                          font=('Arial', 9, 'bold'),
                                          format="%.2f")
        self.entry_range_min.delete(0, 'end')
        self.entry_range_min.insert(0, f"{config.ENTRY_RANGE_MIN:.2f}")
        self.entry_range_min.pack(side='left', padx=3)
        
        tk.Label(entry_min_row, text="إلى $",
                bg=self.colors['profit_bg'], fg=self.colors['text_gray'],
                font=('Arial', 8)).pack(side='left', padx=5)
        
        self.entry_range_max = tk.Spinbox(entry_min_row, from_=0.50, to=20.00, increment=0.50, width=6,
                                          bg='white',
                                          fg=self.colors['accent_green'],
                                          font=('Arial', 9, 'bold'),
                                          format="%.2f")
        self.entry_range_max.delete(0, 'end')
        self.entry_range_max.insert(0, f"{config.ENTRY_RANGE_MAX:.2f}")
        self.entry_range_max.pack(side='left', padx=3)
        
        tk.Label(entry_frame, text="(فقط العقود بهذا النطاق ستُستخدم للصفقات)",
                bg=self.colors['profit_bg'], fg=self.colors['text_gray'],
                font=('Arial', 7, 'italic')).pack(pady=2)
        
        # Apply Button
        ModernButton(range_section, text="✓ تطبيق التغييرات",
                    command=self.apply_dual_ranges,
                    bg=self.colors['accent_yellow'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=15, pady=5,
                    cursor='hand2').pack(pady=8)
        
        # Status Note
        self.range_note = tk.Label(range_section,
                                   text=f"✓ متابعة: ${config.MONITORING_RANGE_MIN:.2f}-${config.MONITORING_RANGE_MAX:.2f} | دخول: ${config.ENTRY_RANGE_MIN:.2f}-${config.ENTRY_RANGE_MAX:.2f}",
                                   bg=self.colors['bg_card'],
                                   fg=self.colors['accent_green'],
                                   font=('Arial', 7, 'italic'))
        self.range_note.pack(pady=3)
        
        # Separator 2
        tk.Frame(main_container, bg=self.colors['border'], width=3).pack(side='left', fill='y', padx=10)
        
        # ═══════════════════════════════════════════════════════════
        # SECTION 3: CONTRACT QUANTITY (RIGHT)
        # ═══════════════════════════════════════════════════════════
        quantity_section = tk.Frame(main_container, bg=self.colors['bg_card'])
        quantity_section.pack(side='left', fill='both', expand=False, padx=10)
        
        # Title
        tk.Label(quantity_section, text="📊 عدد العقود",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(pady=(0, 10))
        
        # Quantity Input
        qty_row = tk.Frame(quantity_section, bg=self.colors['bg_card'])
        qty_row.pack(fill='x', pady=3)
        
        self.contract_quantity = tk.Spinbox(qty_row, from_=1, to=9999, increment=1, width=7,
                                           bg=self.colors['bg_card_light'],
                                           fg=self.colors['accent_yellow'],
                                           font=('Arial', 10, 'bold'),
                                           format="%1.0f")
        self.contract_quantity.delete(0, 'end')
        self.contract_quantity.insert(0, "1")
        self.contract_quantity.pack(padx=3)
        
        # Apply Button
        ModernButton(quantity_section, text="✓ تطبيق",
                    command=self.apply_quantity,
                    bg=self.colors['accent_blue'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=20, pady=5,
                    cursor='hand2').pack(pady=5)
        
        # Quantity Note
        self.quantity_note = tk.Label(quantity_section,
                                     text="✓ العدد: 1",
                                     bg=self.colors['bg_card'],
                                     fg=self.colors['accent_green'],
                                     font=('Arial', 8, 'italic'))
        self.quantity_note.pack(pady=3)
        
        # Separator 3
        tk.Frame(main_container, bg=self.colors['border'], width=3).pack(side='left', fill='y', padx=10)
        
        # ═══════════════════════════════════════════════════════════
        # SECTION 4: MANUAL TRADING (يدوي + TradingView)
        # ═══════════════════════════════════════════════════════════
        trading_section = tk.Frame(main_container, bg=self.colors['bg_card'])
        trading_section.pack(side='left', fill='both', expand=True, padx=(10, 0))
        
        # Title
        tk.Label(trading_section, text="🎯 التداول (يدوي + TradingView)",
                bg=self.colors['bg_card'], fg=self.colors['accent_yellow'],
                font=('Arial', 9, 'bold')).pack(pady=(0, 8))
        
        # Buttons Container
        buttons_container = tk.Frame(trading_section, bg=self.colors['bg_card'])
        buttons_container.pack(fill='both', expand=True)
        
        # CALL Column (Left)
        call_column = tk.Frame(buttons_container, bg=self.colors['bg_card'])
        call_column.pack(side='left', fill='both', expand=True, padx=3)
        
        tk.Label(call_column, text="📈 CALL",
                bg=self.colors['bg_card'], fg=self.colors['call_color'],
                font=('Arial', 9, 'bold')).pack(pady=(0, 5))
        
        for symbol in config.SUPPORTED_SYMBOLS:
            ModernButton(call_column, 
                        text=f"🚀 {symbol}",
                        command=lambda s=symbol: self.open_manual_trade(s, 'CALL'),
                        bg=self.colors['call_color'], 
                        fg='black',
                        font=('Arial', 8, 'bold'),
                        relief='raised', bd=2, 
                        padx=8, pady=4,
                        cursor='hand2').pack(pady=2, fill='x')
        
        # PUT Column (Right)
        put_column = tk.Frame(buttons_container, bg=self.colors['bg_card'])
        put_column.pack(side='left', fill='both', expand=True, padx=3)
        
        tk.Label(put_column, text="📉 PUT",
                bg=self.colors['bg_card'], fg=self.colors['put_color'],
                font=('Arial', 9, 'bold')).pack(pady=(0, 5))
        
        for symbol in config.SUPPORTED_SYMBOLS:
            ModernButton(put_column, 
                        text=f"🚀 {symbol}",
                        command=lambda s=symbol: self.open_manual_trade(s, 'PUT'),
                        bg=self.colors['put_color'], 
                        fg='white',
                        font=('Arial', 8, 'bold'),
                        relief='raised', bd=2, 
                        padx=8, pady=4,
                        cursor='hand2').pack(pady=2, fill='x')
        
        # Info Note
        info_note = tk.Label(trading_section,
                            text="ℹ️ موحدة | نطاق + فحوصات + عدد",
                            bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                            font=('Arial', 7, 'italic'))
        info_note.pack(pady=(3, 0))
    
    def create_telegram_section(self, parent):
        """Create Telegram settings section"""
        frame = tk.LabelFrame(parent, text="📱 إعدادات التيليجرام",
                             bg=self.colors['bg_card'],
                             fg=self.colors['accent_purple'],
                             font=('Arial', 11, 'bold'),
                             borderwidth=2, relief='solid')
        frame.pack(fill='both', expand=True, pady=5)
        
        # Top row: Buttons on left, Alerts button on right
        top_row = tk.Frame(frame, bg=self.colors['bg_card'])
        top_row.pack(fill='x', padx=15, pady=10)
        
        # Buttons on left
        btn_frame = tk.Frame(top_row, bg=self.colors['bg_card'])
        btn_frame.pack(side='left', fill='x', expand=True)
        
        ModernButton(btn_frame, text="📧 إعدادات الإشعارات",
                    command=self.show_telegram_settings,
                    bg=self.colors['accent_purple'], fg='white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=12, pady=6,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="✏️ تعديل نصوص الرسائل",
                    command=self.edit_message_texts,
                    bg=self.colors['accent_blue'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=12, pady=6,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="🎨 إعدادات الصور",
                    command=self.edit_image_settings,
                    bg=self.colors['accent_yellow'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=12, pady=6,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="📊 رسائل التتبع",
                    command=self.edit_tracking_messages,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=12, pady=6,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="🔄 إعادة تحميل القنوات",
                    command=self.reload_telegram_channels,
                    bg=self.colors['accent_blue'], fg='white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=12, pady=6,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="🧪 اختبار الاتصال",
                    command=self.test_telegram_connection,
                    bg=self.colors['accent_green'], fg='white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=12, pady=6,
                    cursor='hand2').pack(side='left', padx=5)
        
        # Alerts button on right
        ModernButton(top_row, text="⏰ التنبيهات",
                    command=self.manage_telegram_alerts,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=3, padx=20, pady=8,
                    cursor='hand2').pack(side='right', padx=5)
        
        # Channels Table
        table_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        table_frame.pack(fill='both', expand=True, padx=15, pady=10)
        
        columns = ('token', 'chat_id', 'name', 'symbol', 'channel_link')
        self.tg_tree = ttk.Treeview(table_frame, columns=columns, height=4, show='headings')
        
        self.tg_tree.heading('token', text='التوكن')
        self.tg_tree.heading('chat_id', text='Chat ID')
        self.tg_tree.heading('name', text='اسم القناة')
        self.tg_tree.heading('symbol', text='الشركة')
        self.tg_tree.heading('channel_link', text='رابط القناة')
        
        self.tg_tree.column('token', width=150)
        self.tg_tree.column('chat_id', width=100)
        self.tg_tree.column('name', width=120)
        self.tg_tree.column('symbol', width=80)
        self.tg_tree.column('channel_link', width=200)
        
        self.tg_tree.pack(fill='both', expand=True)
        
        # Add/Edit buttons
        tg_btns = tk.Frame(frame, bg=self.colors['bg_card'])
        tg_btns.pack(fill='x', padx=15, pady=5)
        
        ModernButton(tg_btns, text="➕ إضافة قناة",
                    command=self.add_telegram_channel,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=10, pady=5,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(tg_btns, text="✏️ تعديل",
                    command=self.edit_telegram_channel,
                    bg=self.colors['accent_blue'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=10, pady=5,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(tg_btns, text="🗑️ حذف",
                    command=self.delete_telegram_channel,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=10, pady=5,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(tg_btns, text="🔄 تحديث",
                    command=self.load_telegram_channels,
                    bg=self.colors['accent_yellow'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=10, pady=5,
                    cursor='hand2').pack(side='left', padx=5)
        
        # TradingView Commands
        tv_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        tv_frame.pack(fill='x', padx=15, pady=10)
        
        ModernButton(tv_frame, text="📝 أوامر تريدنج فيو",
                    command=self.show_tradingview_commands,
                    bg=self.colors['accent_yellow'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=12, pady=6,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(tv_frame, text="🔗 نسخ رابط Webhook",
                    command=self.copy_webhook_url,
                    bg=self.colors['accent_blue'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=12, pady=6,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(tv_frame, text="🔄 تحديث الرابط",
                    command=self.update_webhook_url_display,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=12, pady=6,
                    cursor='hand2').pack(side='left', padx=5)
        
        self.ngrok_label = tk.Label(tv_frame,
                                   text="⏳ انتظر تشغيل النظام...",
                                   bg=self.colors['bg_card'],
                                   fg=self.colors['accent_yellow'],
                                   font=('Arial', 9, 'bold'),
                                   cursor='hand2')
        self.ngrok_label.pack(side='left', padx=10)
        self.ngrok_label.bind("<Button-1>", lambda e: self.copy_webhook_url())
    
    def create_watchlist_section(self, parent):
        """Create watchlist section with tabs"""
        frame = tk.LabelFrame(parent, text="📊 قائمة المراقبة (تحديث كل 5 ثواني)",
                             bg=self.colors['bg_card'],
                             fg=self.colors['accent_green'],
                             font=('Arial', 11, 'bold'),
                             borderwidth=2, relief='solid')
        frame.pack(fill='both', expand=True, pady=5)
        
        # Notebook for company tabs
        notebook = ttk.Notebook(frame)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create tabs for default watchlist symbols (SPX, SPY only)
        default_symbols = getattr(config, 'DEFAULT_WATCHLIST_SYMBOLS', config.SUPPORTED_SYMBOLS)
        for symbol in default_symbols:
            tab = self.create_watchlist_tab(notebook, symbol)
            notebook.add(tab, text=f' {symbol} ')
            logger.info(f"Created watchlist tab for {symbol}")
            # جلب العقود فورًا عند إنشاء التبويب
            self.root.after(1000, lambda s=symbol: self.update_symbol_watchlist(s, force_full_update=True))
        
        # Add company button
        add_btn_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        add_btn_frame.pack(fill='x', padx=15, pady=5)
        
        ModernButton(add_btn_frame, text="➕ إضافة شركة",
                    command=self.add_company_to_watchlist,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=12, pady=6,
                    cursor='hand2').pack(side='left')
        
        self.watchlist_notebook = notebook
    
    def add_company_to_watchlist(self):
        """Add new company to watchlist"""
        # Create dialog window
        dialog = tk.Toplevel(self.root)
        dialog.title("إضافة شركة")
        dialog.geometry("350x200")
        dialog.configure(bg=self.colors['bg_main'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (350 // 2)
        y = (dialog.winfo_screenheight() // 2) - (200 // 2)
        dialog.geometry(f"+{x}+{y}")
        
        frame = tk.Frame(dialog, bg=self.colors['bg_card'], bd=2, relief='raised')
        frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        tk.Label(frame, text="اختر الشركة:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 11, 'bold')).pack(pady=(15, 10))
        
        # Symbol selection
        symbol_var = tk.StringVar()
        symbol_combo = ttk.Combobox(frame, textvariable=symbol_var,
                                    values=config.SUPPORTED_SYMBOLS,
                                    width=15, font=('Arial', 11),
                                    state='readonly')
        symbol_combo.pack(pady=10)
        
        if config.SUPPORTED_SYMBOLS:
            symbol_combo.current(0)
        
        def add_symbol():
            symbol = symbol_var.get()
            if not symbol:
                self.show_auto_close_message("تحذير", "الرجاء اختيار شركة!", 'warning', 3)
                return
            
            # Check if already exists
            existing_tabs = [self.watchlist_notebook.tab(i, 'text').strip()
                           for i in range(self.watchlist_notebook.index('end'))]
            
            if symbol in existing_tabs:
                self.show_auto_close_message("معلومات", f"الشركة {symbol} موجودة بالفعل!", 'info', 3)
                dialog.destroy()
                return
            
            # Create new tab
            new_tab = self.create_watchlist_tab(self.watchlist_notebook, symbol)
            self.watchlist_notebook.add(new_tab, text=f' {symbol} ')
            
            # Create IBKR connection for this symbol if system is running
            if self.system_running and self.trading_system:
                async def create_connection():
                    await self.trading_system.get_or_create_ibkr_connection(symbol)
                
                # Schedule connection creation in async loop
                asyncio.run_coroutine_threadsafe(create_connection(), self.async_loop)
                logger.info(f"Creating IBKR connection for newly added symbol: {symbol}")
            
            # Update immediately
            if self.system_running:
                threading.Thread(target=lambda: self.update_symbol_watchlist(symbol),
                               daemon=True).start()
            
            self.show_auto_close_message("نجح", f"تمت إضافة {symbol} بنجاح!", 'info', 3)
            dialog.destroy()
        
        # Buttons
        btn_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        btn_frame.pack(pady=15)
        
        ModernButton(btn_frame, text="✓ إضافة",
                    command=add_symbol,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=20, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="✗ إلغاء",
                    command=dialog.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=20, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
    
    def create_watchlist_tab(self, parent, symbol):
        """Create watchlist tab for a symbol"""
        logger.info(f"Creating watchlist tab for {symbol}")
        
        tab = tk.Frame(parent, bg=self.colors['bg_card'])
        
        # Container for three columns
        container = tk.Frame(tab, bg=self.colors['bg_card'])
        container.pack(fill='both', expand=True, padx=5, pady=5)
        
        # CALL column (left)
        call_frame = tk.LabelFrame(container, text="📈 CALL",
                                  bg=self.colors['bg_card'],
                                  fg=self.colors['call_color'],
                                  font=('Arial', 10, 'bold'),
                                  borderwidth=2)
        call_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        call_tree = ttk.Treeview(call_frame, columns=('bid', 'ask'), height=10, show='tree headings')
        call_tree.heading('#0', text='Strike')
        call_tree.heading('bid', text='Bid')
        call_tree.heading('ask', text='Ask')
        call_tree.column('#0', width=80)
        call_tree.column('bid', width=80)
        call_tree.column('ask', width=80)
        call_tree.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Price separator (middle)
        price_frame = tk.Frame(container, bg=self.colors['bg_card'], width=150)
        price_frame.pack(side='left', fill='y', padx=10)
        
        tk.Label(price_frame, text="السعر الحالي",
                bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                font=('Arial', 10, 'bold')).pack(pady=(80, 10))
        
        price_label = tk.Label(price_frame, text="⏳ جاري التحميل...",
                              bg=self.colors['bg_card'],
                              fg=self.colors['accent_yellow'],
                              font=('Arial', 18, 'bold'))
        price_label.pack(pady=10)
        
        # Countdown timer for stock price
        stock_countdown_label = tk.Label(price_frame, text="⏱️ التحديث: --s",
                                        bg=self.colors['bg_card'],
                                        fg=self.colors['accent_green'],
                                        font=('Arial', 9, 'bold'))
        stock_countdown_label.pack(pady=2)
        
        # Countdown timer for contracts
        contract_countdown_label = tk.Label(price_frame, text="📊 العقود: --s",
                                           bg=self.colors['bg_card'],
                                           fg=self.colors['accent_blue'],
                                           font=('Arial', 9, 'bold'))
        contract_countdown_label.pack(pady=2)
        
        # Expiry date label
        expiry_label = tk.Label(price_frame, text="⏳ انتظر...",
                               bg=self.colors['bg_card'],
                               fg=self.colors['text_gray'],
                               font=('Arial', 9))
        expiry_label.pack(pady=5)
        
        # Manual refresh button
        refresh_btn = ModernButton(price_frame, text="🔄 تحديث يدوي",
                                   command=lambda s=symbol: self.manual_refresh_watchlist(s),
                                   bg=self.colors['accent_green'], fg='white',
                                   font=('Arial', 8, 'bold'),
                                   relief='raised', bd=2, padx=8, pady=3,
                                   cursor='hand2')
        refresh_btn.pack(pady=5)
        
        # Change expiry date button
        change_expiry_btn = ModernButton(price_frame, text="📅 تغيير التاريخ",
                                         command=lambda s=symbol: self.change_expiry_date(s),
                                         bg=self.colors['accent_blue'], fg='white',
                                         font=('Arial', 8, 'bold'),
                                         relief='raised', bd=2, padx=8, pady=3,
                                         cursor='hand2')
        change_expiry_btn.pack(pady=5)
        
        # Info label showing contract counts
        contracts_info_label = tk.Label(price_frame, text=f"⏳ انتظر...",
                                       bg=self.colors['bg_card'],
                                       fg=self.colors['text_gray'],
                                       font=('Arial', 8))
        contracts_info_label.pack(pady=(10, 5))
        
        # Line separator
        tk.Frame(price_frame, bg=self.colors['accent_yellow'], height=3).pack(fill='x', padx=20, pady=10)
        
        # PUT column (right)
        put_frame = tk.LabelFrame(container, text="📉 PUT",
                                 bg=self.colors['bg_card'],
                                 fg=self.colors['put_color'],
                                 font=('Arial', 10, 'bold'),
                                 borderwidth=2)
        put_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        put_tree = ttk.Treeview(put_frame, columns=('bid', 'ask'), height=10, show='tree headings')
        put_tree.heading('#0', text='Strike')
        put_tree.heading('bid', text='Bid')
        put_tree.heading('ask', text='Ask')
        put_tree.column('#0', width=80)
        put_tree.column('bid', width=80)
        put_tree.column('ask', width=80)
        put_tree.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Close button at top right (for all tabs including SPX)
        close_btn = ModernButton(tab, text="✕",
                                command=lambda s=symbol: self.close_watchlist_tab(s),
                                bg=self.colors['accent_red'], fg='white',
                                font=('Arial', 10, 'bold'),
                                relief='flat', bd=0, padx=8, pady=2,
                                cursor='hand2')
        close_btn.place(relx=0.98, rely=0.01, anchor='ne')
        
        # Store references
        if not hasattr(self, 'watchlist_widgets'):
            self.watchlist_widgets = {}
        
        self.watchlist_widgets[symbol] = {
            'put_tree': put_tree,
            'call_tree': call_tree,
            'price_label': price_label,
            'stock_countdown': stock_countdown_label,
            'contract_countdown': contract_countdown_label,
            'expiry_label': expiry_label,
            'contracts_info': contracts_info_label,
            'tab': tab
        }
        
        logger.info(f"Registered {symbol} in watchlist_widgets. Total widgets: {len(self.watchlist_widgets)}")
        
        return tab
    
    def create_risk_management(self, parent):
        """Create risk management section"""
        frame = tk.LabelFrame(parent, text="⚠️ إدارة المخاطر",
                             bg=self.colors['bg_card'],
                             fg=self.colors['accent_yellow'],
                             font=('Arial', 11, 'bold'),
                             borderwidth=2, relief='solid')
        frame.pack(fill='x', padx=10, pady=5)
        
        # Four risk options
        options_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        options_frame.pack(fill='x', padx=10, pady=10)
        
        self.create_risk_option(options_frame, "🛑 وقف الخسارة", self.colors['accent_red'], 0)
        self.create_risk_option(options_frame, "📊 وقف متحرك", self.colors['accent_blue'], 1)
        self.create_risk_option(options_frame, "🛡️ حماية رأس المال", self.colors['accent_green'], 2)
        self.create_risk_option(options_frame, "🎯 الهدف", self.colors['accent_yellow'], 3)
        
        # Container for table and signals counter
        bottom_container = tk.Frame(frame, bg=self.colors['bg_card'])
        bottom_container.pack(fill='x', padx=10, pady=10)
        
        # Risk params table (left side)
        table_frame = tk.Frame(bottom_container, bg=self.colors['bg_card'])
        table_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        tk.Label(table_frame, text="📋 معلومات الشركات",
                bg=self.colors['bg_card'], fg=self.colors['accent_blue'],
                font=('Arial', 10, 'bold')).pack(anchor='w', pady=5)
        
        columns = ('symbol', 'stop_loss', 'trailing', 'capital', 'target')
        self.risk_tree = ttk.Treeview(table_frame, columns=columns, height=4, show='headings')
        
        self.risk_tree.heading('symbol', text='الشركة')
        self.risk_tree.heading('stop_loss', text='وقف الخسارة')
        self.risk_tree.heading('trailing', text='الوقف المتحرك')
        self.risk_tree.heading('capital', text='حماية رأس المال')
        self.risk_tree.heading('target', text='الهدف')
        
        self.risk_tree.column('symbol', width=80)
        self.risk_tree.column('stop_loss', width=120)
        self.risk_tree.column('trailing', width=120)
        self.risk_tree.column('capital', width=140)
        self.risk_tree.column('target', width=120)
        
        self.risk_tree.pack(fill='x')
        
        # Signals counter (right side)
        signals_frame = tk.LabelFrame(bottom_container, text="📡 عدد الإشارات",
                                     bg=self.colors['bg_card'],
                                     fg=self.colors['accent_purple'],
                                     font=('Arial', 11, 'bold'),
                                     borderwidth=2, relief='solid')
        signals_frame.pack(side='left', fill='y', padx=5)
        
        signals_inner = tk.Frame(signals_frame, bg=self.colors['bg_card'])
        signals_inner.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.signals_labels = {}
        
        for label, color in [('CALL', self.colors['call_color']), 
                            ('PUT', self.colors['put_color']),
                            ('إجمالي', self.colors['accent_blue'])]:
            row = tk.Frame(signals_inner, bg=self.colors['bg_card'])
            row.pack(fill='x', pady=5)
            
            tk.Label(row, text=f"{label}:",
                    bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                    font=('Arial', 12, 'bold')).pack(side='left', padx=10)
            
            count_label = tk.Label(row, text="0",
                                  bg=self.colors['bg_card'], fg=color,
                                  font=('Arial', 16, 'bold'))
            count_label.pack(side='right', padx=10)
            
            self.signals_labels[label] = count_label
        
        # Load and display default settings
        self.update_risk_table()
    
    def create_risk_option(self, parent, title, color, column):
        """Create risk option card"""
        card = tk.LabelFrame(parent, text=title,
                           bg=self.colors['bg_card_light'],
                           fg=color, font=('Arial', 10, 'bold'),
                           borderwidth=2, relief='groove')
        card.grid(row=0, column=column, padx=5, pady=5, sticky='ew')
        parent.columnconfigure(column, weight=1)
        
        inner = tk.Frame(card, bg=self.colors['bg_card_light'])
        inner.pack(fill='both', padx=10, pady=10)
        
        # Symbol selection
        tk.Label(inner, text="الشركة:",
                bg=self.colors['bg_card_light'], fg=self.colors['text_gray'],
                font=('Arial', 9)).pack(anchor='w', pady=2)
        
        symbol_combo = ttk.Combobox(inner, values=config.SUPPORTED_SYMBOLS,
                                   width=10, font=('Arial', 9))
        symbol_combo.set(config.DEFAULT_SYMBOL)
        symbol_combo.pack(fill='x', pady=2)
        
        # Type selection
        var = tk.StringVar(value="none")
        tk.Radiobutton(inner, text="نسبة %", variable=var, value="percentage",
                      bg=self.colors['bg_card_light'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card'],
                      font=('Arial', 9)).pack(anchor='w', pady=2)
        tk.Radiobutton(inner, text="مبلغ $", variable=var, value="amount",
                      bg=self.colors['bg_card_light'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card'],
                      font=('Arial', 9)).pack(anchor='w', pady=2)
        tk.Radiobutton(inner, text="NONE", variable=var, value="none",
                      bg=self.colors['bg_card_light'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card'],
                      font=('Arial', 9)).pack(anchor='w', pady=2)
        
        # Value entry
        entry = tk.Entry(inner, width=12, bg=self.colors['bg_card'],
                        fg=color, font=('Arial', 10, 'bold'),
                        insertbackground=color, bd=2, relief='solid')
        entry.insert(0, "10")
        entry.pack(fill='x', pady=5)
        
        # Apply button
        ModernButton(inner, text="✓ تطبيق",
                    command=lambda: self.apply_risk_setting(title, symbol_combo.get(), var.get(), entry.get()),
                    bg=color, fg='black' if color != self.colors['accent_red'] else 'white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=10, pady=5,
                    cursor='hand2').pack(fill='x')
    
    def create_active_trades_section(self, parent):
        """Create active trades and signals section"""
        container = tk.Frame(parent, bg=self.colors['bg_main'])
        container.pack(fill='x', padx=10, pady=5)
        
        # Active trades (left)
        active_frame = tk.LabelFrame(container, text="📊 الصفقات النشطة",
                                    bg=self.colors['bg_card'],
                                    fg=self.colors['accent_green'],
                                    font=('Arial', 11, 'bold'),
                                    borderwidth=2, relief='solid')
        active_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        table = tk.Frame(active_frame, bg=self.colors['bg_card'])
        table.pack(fill='both', expand=True, padx=10, pady=10)
        
        columns = ('symbol', 'contract', 'entry', 'high', 'current', 'stop_loss', 'trailing', 'capital', 'target', 'tracks', 'quantity', 'close')
        self.active_tree = ttk.Treeview(table, columns=columns, height=6, show='headings')
        
        # إضافة شريط التمرير العمودي للصفقات النشطة
        active_scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.active_tree.yview)
        self.active_tree.configure(yscrollcommand=active_scrollbar.set)
        
        self.active_tree.heading('symbol', text='الشركة')
        self.active_tree.heading('contract', text='العقد')
        self.active_tree.heading('entry', text='سعر الدخول')
        self.active_tree.heading('high', text='🔥 أعلى سعر')
        self.active_tree.heading('current', text='💰 السعر الحالي')
        self.active_tree.heading('stop_loss', text='🛑 وقف الخسارة')
        self.active_tree.heading('trailing', text='📊 وقف متحرك')
        self.active_tree.heading('capital', text='🛡️ حماية رأس المال')
        self.active_tree.heading('target', text='🎯 الهدف')
        self.active_tree.heading('tracks', text='⚡ التتبع')
        self.active_tree.heading('quantity', text='📦 الكمية')
        self.active_tree.heading('close', text='❌')
        
        self.active_tree.column('symbol', width=60)
        self.active_tree.column('contract', width=100)
        self.active_tree.column('entry', width=70)
        self.active_tree.column('high', width=70)
        self.active_tree.column('current', width=70)
        self.active_tree.column('stop_loss', width=80)
        self.active_tree.column('trailing', width=80)
        self.active_tree.column('capital', width=80)
        self.active_tree.column('target', width=80)
        self.active_tree.column('tracks', width=60)
        self.active_tree.column('quantity', width=60)
        self.active_tree.column('close', width=40)
        
        self.active_tree.pack(side='left', fill='both', expand=True)
        active_scrollbar.pack(side='right', fill='y')
        
        # Quantity adjustment section
        qty_adjust_frame = tk.Frame(active_frame, bg=self.colors['bg_card'])
        qty_adjust_frame.pack(fill='x', padx=10, pady=5)
        
        # Left side - Quantity adjustment controls
        qty_controls = tk.Frame(qty_adjust_frame, bg=self.colors['bg_card'])
        qty_controls.pack(side='left', fill='x', expand=True)
        
        # Trade selection
        tk.Label(qty_controls, text="📋 اختر العقد:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 9, 'bold')).pack(side='left', padx=5)
        
        self.active_trade_selector = ttk.Combobox(qty_controls, width=25,
                                                  font=('Arial', 9),
                                                  state='readonly')
        self.active_trade_selector.pack(side='left', padx=5)
        self.active_trade_selector.bind('<<ComboboxSelected>>', self.on_trade_selected)
        
        # Quantity input
        tk.Label(qty_controls, text="📦 عدد العقود للإغلاق:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 9, 'bold')).pack(side='left', padx=5)
        
        self.adjust_quantity_entry = tk.Entry(qty_controls, width=8,
                                              font=('Arial', 10, 'bold'),
                                              justify='center',
                                              bg='#ffffff', fg='#000000')
        self.adjust_quantity_entry.pack(side='left', padx=5)
        self.adjust_quantity_entry.insert(0, "1")
        
        # Apply button - CHANGED to immediate partial close
        ModernButton(qty_controls, text="❌ إغلاق جزئي",
                    command=self.apply_trade_quantity,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=15, pady=4,
                    cursor='hand2').pack(side='left', padx=5)
        
        # Refresh button
        ModernButton(qty_controls, text="🔄 تحديث القائمة",
                    command=self.refresh_active_trades_selector,
                    bg=self.colors['accent_blue'], fg='white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=10, pady=4,
                    cursor='hand2').pack(side='left', padx=5)
        
        # Restart tracking button - NEW!
        ModernButton(qty_controls, text="🔄 إعادة تنشيط التتبع",
                    command=self.restart_all_tracking,
                    bg=self.colors['accent_green'], fg='white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=10, pady=4,
                    cursor='hand2').pack(side='left', padx=5)
        
        # Close all button (right side)
        close_all_frame = tk.Frame(active_frame, bg=self.colors['bg_card'])
        close_all_frame.pack(fill='x', padx=10, pady=5)
        
        ModernButton(close_all_frame, text="🔒 إغلاق جميع الصفقات",
                    command=self.close_all_active_trades,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=15, pady=6,
                    cursor='hand2').pack(side='right')
        
        # Single click on 'close' column to close trade
        self.active_tree.bind('<Button-1>', self.on_active_trade_click)
        # Double-click to show tracking history
        self.active_tree.bind("<Double-1>", self.show_tracking_history)
    
    def create_trade_history_section(self, parent):
        """Create trade history section"""
        frame = tk.LabelFrame(parent, text="📜 سجل الصفقات",
                             bg=self.colors['bg_card'],
                             fg=self.colors['accent_blue'],
                             font=('Arial', 11, 'bold'),
                             borderwidth=2, relief='solid')
        frame.pack(fill='x', padx=10, pady=5)
        
        # Filter frame
        filter_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        filter_frame.pack(fill='x', padx=15, pady=5)
        
        tk.Label(filter_frame, text="🔍 الشركة:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(side='left', padx=5)
        
        filter_symbols = ["الكل"] + config.SUPPORTED_SYMBOLS
        self.history_filter_symbol = ttk.Combobox(filter_frame, values=filter_symbols,
                                                  width=12, font=('Arial', 10),
                                                  state='readonly')
        self.history_filter_symbol.set("الكل")
        self.history_filter_symbol.bind('<<ComboboxSelected>>', lambda e: self.update_trades_history())
        self.history_filter_symbol.pack(side='left', padx=5)
        
        table_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        table_frame.pack(fill='x', padx=15, pady=10)
        
        columns = ('num', 'symbol', 'type', 'contract', 'entry', 'high', 'close', 'profit', 'loss')
        self.history_tree = ttk.Treeview(table_frame, columns=columns, height=6, show='headings')
        
        self.history_tree.heading('num', text='#')
        self.history_tree.heading('symbol', text='الشركة')
        self.history_tree.heading('type', text='النوع')
        self.history_tree.heading('contract', text='رقم العقد')
        self.history_tree.heading('entry', text='سعر الدخول')
        self.history_tree.heading('high', text='أعلى سعر')
        self.history_tree.heading('close', text='سعر الإغلاق')
        self.history_tree.heading('profit', text='💰 الأرباح')
        self.history_tree.heading('loss', text='📉 الخسائر')
        
        self.history_tree.column('num', width=40)
        self.history_tree.column('symbol', width=60)
        self.history_tree.column('type', width=60)
        self.history_tree.column('contract', width=100)
        self.history_tree.column('entry', width=70)
        self.history_tree.column('high', width=70)
        self.history_tree.column('close', width=70)
        self.history_tree.column('profit', width=90)
        self.history_tree.column('loss', width=90)
        
        # Add vertical scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        
        self.history_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Clear history button
        btn_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        btn_frame.pack(fill='x', padx=15, pady=5)
        
        ModernButton(btn_frame, text="🗑️ مسح السجل",
                    command=self.clear_trade_history,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=15, pady=5,
                    cursor='hand2').pack(side='left')
        
        note = tk.Label(btn_frame,
                       text="⚠️ العقود التي لا تصل أرباحها 100$ تُسجل كخسارة",
                       bg=self.colors['bg_card'], fg=self.colors['accent_red'],
                       font=('Arial', 9, 'italic'))
        note.pack(side='left', padx=10)
    
    def create_summary_section(self, parent):
        """Create summary section"""
        frame = tk.LabelFrame(parent, text="💰 الملخص",
                             bg=self.colors['bg_card'],
                             fg=self.colors['accent_yellow'],
                             font=('Arial', 11, 'bold'),
                             borderwidth=2, relief='solid')
        frame.pack(fill='x', padx=10, pady=5)
        
        summary = tk.Frame(frame, bg=self.colors['bg_card'])
        summary.pack(fill='x', padx=15, pady=15)
        
        # Profit card
        profit_card = tk.Frame(summary, bg=self.colors['profit_bg'],
                              relief='solid', borderwidth=3)
        profit_card.pack(side='left', padx=10)
        
        tk.Label(profit_card, text="💰 إجمالي الأرباح",
                bg=self.colors['profit_bg'], fg=self.colors['accent_green'],
                font=('Arial', 11, 'bold')).pack(padx=20, pady=5)
        
        self.profit_label = tk.Label(profit_card, text="$0.00",
                                     bg=self.colors['profit_bg'],
                                     fg=self.colors['accent_green'],
                                     font=('Arial', 20, 'bold'))
        self.profit_label.pack(padx=20, pady=5)
        
        # Loss card
        loss_card = tk.Frame(summary, bg=self.colors['loss_bg'],
                            relief='solid', borderwidth=3)
        loss_card.pack(side='left', padx=10)
        
        tk.Label(loss_card, text="📉 إجمالي الخسائر",
                bg=self.colors['loss_bg'], fg=self.colors['accent_red'],
                font=('Arial', 11, 'bold')).pack(padx=20, pady=5)
        
        self.loss_label = tk.Label(loss_card, text="$0.00",
                                   bg=self.colors['loss_bg'],
                                   fg=self.colors['accent_red'],
                                   font=('Arial', 20, 'bold'))
        self.loss_label.pack(padx=20, pady=5)
        
        # Print button
        ModernButton(summary, text="🖨️ طباعة الملخص",
                    command=self.print_summary,
                    bg=self.colors['accent_blue'], fg='black',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=3, padx=20, pady=10,
                    cursor='hand2').pack(side='left', padx=30)
        
        # Settings
        settings = tk.Frame(frame, bg=self.colors['bg_card'])
        settings.pack(fill='x', padx=15, pady=10)
        
        tk.Label(settings, text="⚙️ الوضع:",
                bg=self.colors['bg_card'], fg=self.colors['accent_yellow'],
                font=('Arial', 11, 'bold')).pack(side='left', padx=10)
        
        self.mode_var = tk.StringVar(value=config.DEFAULT_MODE)
        
        tk.Radiobutton(settings, text="📖 قراءة فقط", variable=self.mode_var,
                      value="readonly",
                      bg=self.colors['bg_card'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card_light'],
                      font=('Arial', 10)).pack(side='left', padx=10)
        
        tk.Radiobutton(settings, text="🔴 حقيقي (تداول فعلي)",
                      variable=self.mode_var, value="live",
                      bg=self.colors['bg_card'], fg=self.colors['accent_red'],
                      selectcolor=self.colors['bg_card_light'],
                      font=('Arial', 10, 'bold')).pack(side='left', padx=10)
        
        ModernButton(settings, text="🗑️ تنظيف العقود",
                    command=self.cleanup_contracts,
                    bg=self.colors['accent_yellow'], fg='black',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=3, padx=15, pady=8,
                    cursor='hand2').pack(side='left', padx=40)
    
    def create_cleanup_section(self, parent):
        """Create database cleanup section"""
        frame = tk.LabelFrame(parent, text="🧹 التنظيف التلقائي لقاعدة البيانات",
                             bg=self.colors['bg_card'],
                             fg=self.colors['accent_purple'],
                             font=('Arial', 11, 'bold'),
                             borderwidth=2, relief='solid')
        frame.pack(fill='x', padx=10, pady=5)
        
        inner = tk.Frame(frame, bg=self.colors['bg_card'])
        inner.pack(fill='x', padx=15, pady=10)
        
        # Top row: Manual cleanup button + Settings button
        top_row = tk.Frame(inner, bg=self.colors['bg_card'])
        top_row.pack(fill='x', pady=(0, 10))
        
        ModernButton(top_row, text="🗑️ تنظيف يدوي الآن",
                    command=self.manual_cleanup,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=20, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(top_row, text="⚙️ تطبيق إعدادات",
                    command=self.cleanup_settings,
                    bg=self.colors['accent_green'], fg='white',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=20, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
        
        # Status card
        status_frame = tk.Frame(inner, bg=self.colors['bg_card_light'],
                               relief='solid', borderwidth=2)
        status_frame.pack(fill='x', pady=5)
        
        status_inner = tk.Frame(status_frame, bg=self.colors['bg_card_light'])
        status_inner.pack(fill='x', padx=10, pady=10)
        
        # Load current settings
        cleanup_settings = self.db.get_cleanup_settings()
        
        # Status row
        status_row = tk.Frame(status_inner, bg=self.colors['bg_card_light'])
        status_row.pack(fill='x', pady=3)
        
        tk.Label(status_row, text="الحالة:",
                bg=self.colors['bg_card_light'], fg=self.colors['text_gray'],
                font=('Arial', 9, 'bold')).pack(side='left', padx=5)
        
        self.cleanup_status_label = tk.Label(status_row,
                                             text="⏸️ معطل" if not cleanup_settings or not cleanup_settings['enabled'] else "✅ مُفعّل",
                                             bg=self.colors['bg_card_light'],
                                             fg=self.colors['accent_red'] if not cleanup_settings or not cleanup_settings['enabled'] else self.colors['accent_green'],
                                             font=('Arial', 10, 'bold'))
        self.cleanup_status_label.pack(side='left', padx=5)
        
        # Frequency row
        freq_row = tk.Frame(status_inner, bg=self.colors['bg_card_light'])
        freq_row.pack(fill='x', pady=3)
        
        tk.Label(freq_row, text="التكرار:",
                bg=self.colors['bg_card_light'], fg=self.colors['text_gray'],
                font=('Arial', 9, 'bold')).pack(side='left', padx=5)
        
        freq_text = self._get_frequency_text(cleanup_settings['frequency'] if cleanup_settings else 'monthly')
        self.cleanup_frequency_label = tk.Label(freq_row,
                                                text=freq_text,
                                                bg=self.colors['bg_card_light'],
                                                fg=self.colors['accent_blue'],
                                                font=('Arial', 9))
        self.cleanup_frequency_label.pack(side='left', padx=5)
        
        # Next cleanup row
        next_row = tk.Frame(status_inner, bg=self.colors['bg_card_light'])
        next_row.pack(fill='x', pady=3)
        
        tk.Label(next_row, text="التنظيف القادم:",
                bg=self.colors['bg_card_light'], fg=self.colors['text_gray'],
                font=('Arial', 9, 'bold')).pack(side='left', padx=5)
        
        next_text = cleanup_settings['next_cleanup'] if cleanup_settings and cleanup_settings['next_cleanup'] else "غير محدد"
        self.cleanup_next_label = tk.Label(next_row,
                                           text=next_text,
                                           bg=self.colors['bg_card_light'],
                                           fg=self.colors['accent_yellow'],
                                           font=('Arial', 9, 'bold'))
        self.cleanup_next_label.pack(side='left', padx=5)
        
        # Last cleanup row
        last_row = tk.Frame(status_inner, bg=self.colors['bg_card_light'])
        last_row.pack(fill='x', pady=3)
        
        tk.Label(last_row, text="آخر تنظيف:",
                bg=self.colors['bg_card_light'], fg=self.colors['text_gray'],
                font=('Arial', 9, 'bold')).pack(side='left', padx=5)
        
        last_text = cleanup_settings['last_cleanup'] if cleanup_settings and cleanup_settings['last_cleanup'] else "لم يتم بعد"
        self.cleanup_last_label = tk.Label(last_row,
                                           text=last_text,
                                           bg=self.colors['bg_card_light'],
                                           fg=self.colors['text_gray'],
                                           font=('Arial', 9))
        self.cleanup_last_label.pack(side='left', padx=5)
    
    def _get_frequency_text(self, frequency):
        """Convert frequency code to Arabic text"""
        frequency_map = {
            'daily': 'يومي',
            'weekly': 'أسبوعي',
            'monthly': 'شهري',
            'month+week': 'شهر وأسبوع'
        }
        return frequency_map.get(frequency, frequency)
    
    def manual_cleanup(self):
        """Perform manual cleanup immediately"""
        try:
            # Get settings to determine days_to_keep
            settings = self.db.get_cleanup_settings()
            days_to_keep = settings['days_to_keep'] if settings else 30
            
            # Confirm with user
            result = messagebox.askyesno(
                "تأكيد التنظيف",
                f"هل تريد تنظيف قاعدة البيانات الآن؟\n\n"
                f"سيتم حذف:\n"
                f"• الصفقات المغلقة الأقدم من {days_to_keep} يوم\n"
                f"• سجلات التتبع القديمة (توفير 90% من المساحة)\n"
                f"• الإشارات القديمة من TradingView\n"
                f"• التنبيهات المرسلة\n\n"
                f"⚠️ لا يمكن التراجع عن هذا الإجراء!",
                icon='warning'
            )
            
            if not result:
                return
            
            # Show progress window
            progress_win = tk.Toplevel(self.root)
            progress_win.title("جاري التنظيف...")
            progress_win.geometry("400x200")
            progress_win.configure(bg=self.colors['bg_main'])
            progress_win.transient(self.root)
            progress_win.grab_set()
            
            # Center window
            progress_win.update_idletasks()
            x = (progress_win.winfo_screenwidth() // 2) - 200
            y = (progress_win.winfo_screenheight() // 2) - 100
            progress_win.geometry(f"+{x}+{y}")
            
            tk.Label(progress_win, text="🧹 جاري تنظيف قاعدة البيانات...",
                    bg=self.colors['bg_main'], fg=self.colors['text_primary'],
                    font=('Arial', 12, 'bold')).pack(pady=20)
            
            status_label = tk.Label(progress_win, text="⏳ انتظر...",
                                   bg=self.colors['bg_main'], fg=self.colors['accent_yellow'],
                                   font=('Arial', 10))
            status_label.pack(pady=10)
            
            progress_win.update()
            
            # Perform cleanup
            status_label.config(text="🗑️ حذف البيانات القديمة...")
            progress_win.update()
            
            results = self.db.perform_auto_cleanup(days_to_keep)
            
            status_label.config(text="✅ اكتمل التنظيف!")
            progress_win.update()
            
            time.sleep(1)
            progress_win.destroy()
            
            # Show results
            results_msg = (
                f"✅ اكتمل التنظيف بنجاح!\n\n"
                f"📊 النتائج:\n"
                f"• الصفقات المغلقة: {results['trades_deleted']}\n"
                f"• سجلات التتبع: {results['tracking_deleted']}\n"
                f"• الإشارات: {results['signals_deleted']}\n"
                f"• التنبيهات: {results['alerts_deleted']}\n\n"
                f"💾 تم تحسين قاعدة البيانات (VACUUM)"
            )
            
            self.show_auto_close_message("نجح", results_msg, 'info', 5)
            
            # Update labels
            self.cleanup_last_label.config(text=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            logger.info(f"Manual cleanup completed: {results}")
            
        except Exception as e:
            logger.error(f"Error in manual cleanup: {e}")
            messagebox.showerror("خطأ", f"فشل التنظيف:\n{str(e)}")
    
    def cleanup_settings(self):
        """Show cleanup settings dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("إعدادات التنظيف التلقائي")
        dialog.geometry("550x600")
        dialog.configure(bg=self.colors['bg_main'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 275
        y = (dialog.winfo_screenheight() // 2) - 300
        dialog.geometry(f"+{x}+{y}")
        
        # Get current settings
        settings = self.db.get_cleanup_settings()
        
        # Title
        title_frame = tk.Frame(dialog, bg=self.colors['bg_card'])
        title_frame.pack(fill='x', padx=15, pady=15)
        
        tk.Label(title_frame, text="⚙️ إعدادات التنظيف التلقائي",
                bg=self.colors['bg_card'], fg=self.colors['accent_purple'],
                font=('Arial', 13, 'bold')).pack(pady=10)
        
        # Enable/Disable
        enable_frame = tk.LabelFrame(dialog, text="🔘 حالة التنظيف",
                                    bg=self.colors['bg_card'],
                                    fg=self.colors['accent_blue'],
                                    font=('Arial', 11, 'bold'))
        enable_frame.pack(fill='x', padx=20, pady=10)
        
        enabled_var = tk.BooleanVar(value=settings['enabled'] if settings else False)
        
        tk.Checkbutton(enable_frame, text="✅ تفعيل التنظيف التلقائي",
                      variable=enabled_var,
                      bg=self.colors['bg_card'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card_light'],
                      font=('Arial', 10, 'bold')).pack(anchor='w', padx=15, pady=10)
        
        # Frequency
        freq_frame = tk.LabelFrame(dialog, text="📅 تكرار التنظيف",
                                  bg=self.colors['bg_card'],
                                  fg=self.colors['accent_blue'],
                                  font=('Arial', 11, 'bold'))
        freq_frame.pack(fill='x', padx=20, pady=10)
        
        freq_var = tk.StringVar(value=settings['frequency'] if settings else 'monthly')
        
        tk.Radiobutton(freq_frame, text="📆 يومي (كل يوم)",
                      variable=freq_var, value='daily',
                      bg=self.colors['bg_card'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card_light'],
                      font=('Arial', 10)).pack(anchor='w', padx=15, pady=5)
        
        tk.Radiobutton(freq_frame, text="📅 أسبوعي (كل 7 أيام)",
                      variable=freq_var, value='weekly',
                      bg=self.colors['bg_card'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card_light'],
                      font=('Arial', 10)).pack(anchor='w', padx=15, pady=5)
        
        tk.Radiobutton(freq_frame, text="📊 شهري (كل 30 يوم) - موصى به ⭐",
                      variable=freq_var, value='monthly',
                      bg=self.colors['bg_card'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card_light'],
                      font=('Arial', 10, 'bold')).pack(anchor='w', padx=15, pady=5)
        
        tk.Radiobutton(freq_frame, text="📈 شهر وأسبوع (كل 37 يوم)",
                      variable=freq_var, value='month+week',
                      bg=self.colors['bg_card'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card_light'],
                      font=('Arial', 10)).pack(anchor='w', padx=15, pady=5)
        
        # Days to keep
        days_frame = tk.LabelFrame(dialog, text="🗓️ عمر البيانات المحفوظة",
                                  bg=self.colors['bg_card'],
                                  fg=self.colors['accent_blue'],
                                  font=('Arial', 11, 'bold'))
        days_frame.pack(fill='x', padx=20, pady=10)
        
        days_inner = tk.Frame(days_frame, bg=self.colors['bg_card'])
        days_inner.pack(padx=15, pady=10)
        
        tk.Label(days_inner, text="الاحتفاظ بالبيانات لمدة:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10)).pack(side='left', padx=5)
        
        days_var = tk.IntVar(value=settings['days_to_keep'] if settings else 30)
        days_spin = tk.Spinbox(days_inner, from_=7, to=365, increment=1, width=8,
                              textvariable=days_var,
                              bg=self.colors['bg_card_light'],
                              fg=self.colors['accent_yellow'],
                              font=('Arial', 11, 'bold'))
        days_spin.pack(side='left', padx=5)
        
        tk.Label(days_inner, text="يوم",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10)).pack(side='left', padx=5)
        
        # Info
        info_frame = tk.Frame(dialog, bg=self.colors['bg_main'])
        info_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(info_frame, text="💡 سيتم حذف الصفقات المغلقة والبيانات الأقدم من المدة المحددة",
                bg=self.colors['bg_main'], fg=self.colors['accent_yellow'],
                font=('Arial', 9)).pack()
        
        def save_settings():
            try:
                enabled = enabled_var.get()
                frequency = freq_var.get()
                days_to_keep = days_var.get()
                
                # Calculate next cleanup date
                now = datetime.now()
                
                if frequency == 'daily':
                    next_cleanup = now + timedelta(days=1)
                elif frequency == 'weekly':
                    next_cleanup = now + timedelta(days=7)
                elif frequency == 'monthly':
                    next_cleanup = now + timedelta(days=30)
                elif frequency == 'month+week':
                    next_cleanup = now + timedelta(days=37)
                else:
                    next_cleanup = now + timedelta(days=30)
                
                next_cleanup_str = next_cleanup.strftime('%Y-%m-%d %H:%M:%S')
                
                # Save to database
                self.db.save_cleanup_settings(enabled, frequency, next_cleanup_str, days_to_keep)
                
                # Update GUI labels
                self.cleanup_status_label.config(
                    text="✅ مُفعّل" if enabled else "⏸️ معطل",
                    fg=self.colors['accent_green'] if enabled else self.colors['accent_red']
                )
                self.cleanup_frequency_label.config(text=self._get_frequency_text(frequency))
                self.cleanup_next_label.config(text=next_cleanup_str if enabled else "غير محدد")
                
                logger.info(f"Updated cleanup settings: enabled={enabled}, frequency={frequency}, days_to_keep={days_to_keep}")
                
                self.show_auto_close_message("نجح",
                    f"✅ تم حفظ الإعدادات!\n\n"
                    f"الحالة: {'مُفعّل' if enabled else 'معطل'}\n"
                    f"التكرار: {self._get_frequency_text(frequency)}\n"
                    f"الاحتفاظ بالبيانات: {days_to_keep} يوم\n"
                    f"{'التنظيف القادم: ' + next_cleanup_str if enabled else 'التنظيف التلقائي معطل'}",
                    'info', 5, parent=dialog
                )
                
                dialog.destroy()
                
            except Exception as e:
                logger.error(f"Error saving cleanup settings: {e}")
                messagebox.showerror("خطأ", f"فشل حفظ الإعدادات:\n{str(e)}", parent=dialog)
        
        # Buttons
        btn_frame = tk.Frame(dialog, bg=self.colors['bg_main'])
        btn_frame.pack(pady=15)
        
        ModernButton(btn_frame, text="💾 حفظ",
                    command=save_settings,
                    bg=self.colors['accent_green'], fg='white',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=30, pady=10,
                    cursor='hand2').pack(side='left', padx=10)
        
        ModernButton(btn_frame, text="✗ إلغاء",
                    command=dialog.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=30, pady=10,
                    cursor='hand2').pack(side='left', padx=10)
    
    def check_auto_cleanup(self):
        """Check if auto cleanup should run and execute if needed"""
        try:
            settings = self.db.get_cleanup_settings()
            
            if not settings or not settings['enabled']:
                logger.info("Auto-cleanup is disabled")
                return
            
            next_cleanup = settings.get('next_cleanup')
            if not next_cleanup:
                logger.warning("Auto-cleanup enabled but no next_cleanup date set")
                return
            
            # Parse next_cleanup date
            next_date = datetime.strptime(next_cleanup, '%Y-%m-%d %H:%M:%S')
            now = datetime.now()
            
            # Check if it's time to clean
            if now >= next_date:
                logger.info("🧹 Auto-cleanup triggered!")
                
                # Perform cleanup
                results = self.db.perform_auto_cleanup(settings['days_to_keep'])
                
                logger.info(f"Auto-cleanup completed: {results}")
                
                # Update last_cleanup timestamp
                self.db.update_last_cleanup()
                self.cleanup_last_label.config(text=now.strftime('%Y-%m-%d %H:%M:%S'))
                
                # Calculate next cleanup date
                frequency = settings['frequency']
                
                if frequency == 'daily':
                    next_cleanup_date = now + timedelta(days=1)
                elif frequency == 'weekly':
                    next_cleanup_date = now + timedelta(days=7)
                elif frequency == 'monthly':
                    next_cleanup_date = now + timedelta(days=30)
                elif frequency == 'month+week':
                    next_cleanup_date = now + timedelta(days=37)
                else:
                    next_cleanup_date = now + timedelta(days=30)
                
                next_cleanup_str = next_cleanup_date.strftime('%Y-%m-%d %H:%M:%S')
                
                # Update next_cleanup in database
                self.db.save_cleanup_settings(
                    settings['enabled'],
                    settings['frequency'],
                    next_cleanup_str,
                    settings['days_to_keep']
                )
                
                # Update GUI label
                self.cleanup_next_label.config(text=next_cleanup_str)
                
                logger.info(f"Next auto-cleanup scheduled for: {next_cleanup_str}")
                
                # Show notification (optional)
                self.show_auto_close_message("تنظيف تلقائي",
                    f"✅ تم تنظيف قاعدة البيانات تلقائياً!\n\n"
                    f"الصفقات المحذوفة: {results['trades_deleted']}\n"
                    f"سجلات التتبع: {results['tracking_deleted']}\n"
                    f"الإشارات: {results['signals_deleted']}\n"
                    f"التنبيهات: {results['alerts_deleted']}\n\n"
                    f"التنظيف القادم: {next_cleanup_str}",
                    'info', 5
                )
            else:
                time_remaining = next_date - now
                days_remaining = time_remaining.days
                hours_remaining = time_remaining.seconds // 3600
                logger.info(f"Auto-cleanup not due yet. {days_remaining}d {hours_remaining}h remaining until {next_cleanup}")
                
        except Exception as e:
            logger.error(f"Error in check_auto_cleanup: {e}")
    
    def create_status_bar(self, parent):
        """Create status bar"""
        status = tk.Frame(parent, bg=self.colors['bg_card'], height=50)
        status.pack(fill='x', padx=10, pady=10)
        
        self.status_label = tk.Label(status,
                                     text="⏸️ النظام متوقف - جاهز للتشغيل",
                                     bg=self.colors['bg_card'],
                                     fg=self.colors['accent_yellow'],
                                     font=('Arial', 12, 'bold'))
        self.status_label.pack(pady=12)
    
    def update_ibkr_status(self, connected: bool):
        """Update IBKR connection status indicator"""
        if connected:
            self.ibkr_status_indicator.itemconfig(self.ibkr_circle,
                                                 fill=self.colors['accent_green'])
            self.ibkr_status_text.config(text="متصل",
                                        fg=self.colors['accent_green'])
        else:
            self.ibkr_status_indicator.itemconfig(self.ibkr_circle,
                                                 fill=self.colors['accent_red'])
            self.ibkr_status_text.config(text="غير متصل",
                                        fg=self.colors['accent_red'])
    
    # ==================== Event Handlers ====================
    
    def start_system(self):
        """Start the trading system"""
        if self.system_running:
            self.show_auto_close_message("معلومات", "النظام يعمل بالفعل!", 'info', 3)
            return
        
        self.status_label.config(text="🔄 جاري تشغيل النظام...",
                                fg=self.colors['accent_blue'])
        self.root.update()
        
        # Start system in background thread
        def start_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.async_loop = loop  # Store loop for later use
            
            # Link GUI instance to webhook server (for triggering manual buttons)
            webhook_server.set_gui(self)
            
            success = loop.run_until_complete(self.trading_system.start())
            
            if success:
                self.system_running = True
                
                # Initialize Simple Watchlist Manager (النظام المبسط)
                if config.SIMPLE_WATCHLIST_ENABLED:
                    try:
                        self.simple_watchlist = SimpleWatchlistManager()
                        # Start in async loop
                        def start_simple_watchlist():
                            future = asyncio.run_coroutine_threadsafe(
                                self.simple_watchlist.start(),
                                self.async_loop
                            )
                            result = future.result(timeout=30)
                            if result:
                                logger.info("✅ Simple Watchlist Manager initialized successfully")
                            else:
                                logger.error("❌ Failed to initialize Simple Watchlist Manager")
                                self.simple_watchlist = None
                        
                        threading.Thread(target=start_simple_watchlist, daemon=True).start()
                    except Exception as e:
                        logger.error(f"❌ Failed to initialize Simple Watchlist Manager: {e}")
                        self.simple_watchlist = None
                
                # Initialize Adaptive Watchlist Master (معطل)
                elif config.ADAPTIVE_WATCHLIST_ENABLED:
                    try:
                        self.adaptive_master = AdaptiveWatchlistMaster()
                        logger.info("✅ Adaptive Watchlist Master initialized successfully")
                    except Exception as e:
                        logger.error(f"❌ Failed to initialize Adaptive Watchlist Master: {e}")
                        self.adaptive_master = None
                
                # Update IBKR status to connected
                self.root.after(0, lambda: self.update_ibkr_status(True))
                self.root.after(0, lambda: self.status_label.config(
                    text="✅ النظام يعمل - جميع الوظائف نشطة",
                    fg=self.colors['accent_green']))
                self.root.after(0, lambda: self.start_btn.config(state='disabled'))
                self.root.after(0, lambda: self.stop_btn.config(state='normal'))
                
                # Start update loops
                self.update_tasks_running = True
                self.root.after(100, self.update_active_trades)
                self.root.after(100, self.update_trades_history)
                self.root.after(100, self.update_signal_counts)
                self.root.after(100, self.update_balance)
                self.root.after(100, self.update_ibkr_connection_status)
                
                # Force immediate watchlist update for all symbols
                logger.info("🚀 Forcing immediate watchlist update after system start...")
                self.root.after(3000, lambda: self._force_initial_watchlist_update())
                
                # Start regular watchlist updates
                self.root.after(10000, self.update_watchlist)  # Start regular updates after 10s
                
                # Start countdown timer updates
                self.root.after(1000, self.update_countdown_timers)  # Start countdown after 1s
                
                # Update webhook URL display after system starts
                self.root.after(3000, self.update_webhook_url_display)
                
                # Check for auto cleanup
                self.root.after(5000, self.check_auto_cleanup)
            else:
                # Update IBKR status to disconnected
                self.root.after(0, lambda: self.update_ibkr_status(False))
                self.root.after(0, lambda: self.status_label.config(
                    text="❌ فشل تشغيل النظام - تحقق من الاتصال",
                    fg=self.colors['accent_red']))
            
            # Keep event loop running
            while self.system_running:
                loop.run_until_complete(asyncio.sleep(0.1))
        
        # Start webhook server in separate thread
        webhook_thread = threading.Thread(target=webhook_server.run_webhook_server, daemon=True)
        webhook_thread.start()
        
        # Start async thread
        self.async_thread = threading.Thread(target=start_async, daemon=True)
        self.async_thread.start()
    
    def stop_system(self):
        """Stop the trading system"""
        if not self.system_running:
            return
        
        self.system_running = False
        self.update_tasks_running = False
        
        # Stop simple watchlist if running
        if self.simple_watchlist:
            def stop_simple():
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.simple_watchlist.stop(),
                        self.async_loop
                    )
                    future.result(timeout=10)
                    logger.info("✅ Simple Watchlist stopped")
                except Exception as e:
                    logger.error(f"❌ Error stopping simple watchlist: {e}")
            
            threading.Thread(target=stop_simple, daemon=True).start()
        
        # Stop system in background thread
        def stop_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.trading_system.stop())
            except Exception as e:
                logging.error(f"Error stopping system: {e}")
        
        stop_thread = threading.Thread(target=stop_async, daemon=True)
        stop_thread.start()
        
        # Update IBKR status to disconnected
        self.update_ibkr_status(False)
        
        self.status_label.config(text="⏸️ النظام متوقف",
                                fg=self.colors['accent_yellow'])
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
    
    def on_closing(self):
        """Handle window closing - close all active positions first"""
        try:
            # Get active trades
            active_trades = self.db.get_active_trades()
            
            if active_trades and len(active_trades) > 0:
                # Show confirmation dialog
                result = messagebox.askyesno(
                    "تأكيد الإغلاق",
                    f"⚠️ لديك {len(active_trades)} صفقة نشطة!\n\n"
                    f"هل تريد إغلاق جميع الصفقات والخروج من البرنامج؟\n\n"
                    f"✅ نعم = إغلاق كل الصفقات + الخروج\n"
                    f"❌ لا = إلغاء",
                    icon='warning'
                )
                
                if not result:
                    # User cancelled
                    return
                
                # Check if system is running - if not, we need to start it temporarily
                system_was_stopped = not self.system_running
                
                if system_was_stopped:
                    logger.info("🔄 Starting system temporarily to close positions...")
                    
                    # Show connection window
                    conn_win = tk.Toplevel(self.root)
                    conn_win.title("الاتصال")
                    conn_win.geometry("350x120")
                    conn_win.configure(bg=self.colors['bg_main'])
                    conn_win.transient(self.root)
                    conn_win.grab_set()
                    
                    tk.Label(conn_win,
                            text="⏳ جاري الاتصال بـ IBKR...",
                            bg=self.colors['bg_main'],
                            fg=self.colors['text_primary'],
                            font=('Arial', 11, 'bold')).pack(pady=30)
                    
                    conn_win.update()
                    
                    # Start system
                    self.start_system()
                    
                    # Wait for connection
                    max_wait = 30  # 30 seconds max
                    waited = 0
                    while (not self.system_running or not self.trading_system or 
                           not self.trading_system.ibkr or not self.trading_system.ibkr.connected):
                        time.sleep(1)
                        waited += 1
                        if waited >= max_wait:
                            conn_win.destroy()
                            self.show_auto_close_message(
                                "خطأ",
                                "❌ فشل الاتصال بـ IBKR!\n\nلن تُغلق الصفقات.\n\nالرجاء إغلاقها يدوياً من TWS",
                                'error', 3
                            )
                            return
                    
                    conn_win.destroy()
                    logger.info("✅ System started temporarily for closing positions")
                
                # Close all positions
                logger.info(f"🔴 Closing {len(active_trades)} active positions before exit...")
                
                # Show progress window
                progress_win = tk.Toplevel(self.root)
                progress_win.title("إغلاق الصفقات")
                progress_win.geometry("400x200")
                progress_win.configure(bg=self.colors['bg_main'])
                progress_win.transient(self.root)
                progress_win.grab_set()
                
                tk.Label(progress_win, 
                        text="🔄 جاري إغلاق الصفقات النشطة...",
                        bg=self.colors['bg_main'],
                        fg=self.colors['text_primary'],
                        font=('Arial', 12, 'bold')).pack(pady=20)
                
                progress_label = tk.Label(progress_win,
                                         text=f"0 / {len(active_trades)}",
                                         bg=self.colors['bg_main'],
                                         fg=self.colors['accent_blue'],
                                         font=('Arial', 10))
                progress_label.pack(pady=10)
                
                status_label = tk.Label(progress_win,
                                       text="",
                                       bg=self.colors['bg_main'],
                                       fg=self.colors['text_secondary'],
                                       font=('Arial', 9))
                status_label.pack(pady=5)
                
                progress_win.update()
                
                # Close each position
                closed_count = 0
                for trade in active_trades:
                    try:
                        trade_id = trade['id']
                        symbol = trade['symbol']
                        contract_str = trade.get('contract', 'N/A')
                        
                        status_label.config(text=f"جاري إغلاق: {contract_str}")
                        progress_win.update()
                        
                        logger.info(f"🔴 Closing trade #{trade_id} ({symbol})...")
                        
                        # Get current price from IBKR
                        exit_price = None
                        try:
                            # Try to get current market price
                            ibkr_conn = self.trading_system.ibkr_connections.get(symbol, self.trading_system.ibkr)
                            if ibkr_conn and ibkr_conn.connected:
                                # Create contract from trade data
                                from ib_insync import Option
                                contract = Option(
                                    symbol=symbol,
                                    lastTradeDateOrContractMonth=trade.get('expiry', ''),
                                    strike=trade.get('strike', 0),
                                    right=trade['type'][0],  # 'C' or 'P'
                                    exchange='SMART'
                                )
                                
                                # Get current ticker
                                ticker = ibkr_conn.ib.reqMktData(contract, '', True, False)
                                ibkr_conn.ib.sleep(2)  # Wait for data
                                
                                # Get bid/ask
                                if ticker.bid and ticker.bid > 0:
                                    exit_price = ticker.bid
                                elif ticker.ask and ticker.ask > 0:
                                    exit_price = ticker.ask
                                elif ticker.last and ticker.last > 0:
                                    exit_price = ticker.last
                                
                                # Close market data
                                ibkr_conn.ib.cancelMktData(contract)
                        except Exception as price_err:
                            logger.warning(f"Could not get current price for trade #{trade_id}: {price_err}")
                        
                        # If we couldn't get price, use entry price as fallback
                        if not exit_price or exit_price <= 0:
                            exit_price = trade.get('entry_price', 0.01)
                            logger.warning(f"Using entry price as exit price for trade #{trade_id}: ${exit_price}")
                        
                        # Close position via trading system
                        future = asyncio.run_coroutine_threadsafe(
                            self.trading_system.close_position(
                                trade_id,
                                exit_price,
                                reason='إغلاق البرنامج | Program Exit',
                                close_quantity=None  # Close all
                            ),
                            self.async_loop
                        )
                        
                        # Wait for close with timeout
                        future.result(timeout=20)
                        
                        closed_count += 1
                        logger.info(f"✅ Closed trade #{trade_id}")
                        
                        # Update progress
                        progress_label.config(text=f"{closed_count} / {len(active_trades)}")
                        progress_win.update()
                        
                    except Exception as e:
                        logger.error(f"❌ Error closing trade #{trade_id}: {e}")
                        # Continue with next trade even if one fails
                
                # Wait for all telegram notifications to send
                status_label.config(text="⏳ جاري إرسال إشعارات التيليجرام...")
                progress_win.update()
                time.sleep(3)
                
                progress_win.destroy()
                
                logger.info(f"✅ Closed {closed_count}/{len(active_trades)} positions")
                
                if closed_count < len(active_trades):
                    self.show_auto_close_message(
                        "تحذير",
                        f"⚠️ تم إغلاق {closed_count} من {len(active_trades)} صفقة\n\n"
                        f"بعض الصفقات لم تُغلق بنجاح",
                        'warning', 3
                    )
            
            # Stop system
            if self.system_running:
                self.stop_system()
                time.sleep(1)
            
            # Destroy window
            logger.info("🔴 Closing application...")
            self.root.quit()
            self.root.destroy()
            
        except Exception as e:
            logger.error(f"Error in on_closing: {e}")
            # Force close anyway
            self.root.quit()
            self.root.destroy()
    
    def apply_range(self):
        """Apply price range for manual trading"""
        try:
            min_price = float(self.range_start.get())
            max_price = float(self.range_end.get())
            
            if min_price < 0.50 or max_price > 9999.00 or min_price >= max_price:
                self.show_auto_close_message("خطأ", "نطاق سعري غير صحيح!\n\nيجب أن يكون:\n• الحد الأدنى: $0.50+\n• الحد الأقصى: بدون حد\n• الحد الأدنى < الحد الأقصى", 'error', 3)
                return
            
            config.MIN_OPTION_PRICE = min_price
            config.MAX_OPTION_PRICE = max_price
            
            self.range_note.config(text=f"✓ ${min_price:.2f}-${max_price:.2f}")
            
            logger.info(f"Updated price range: ${min_price:.2f} - ${max_price:.2f}")
            self.show_auto_close_message("نجح", f"✅ تم تطبيق النطاق السعري\n\nمن: ${min_price:.2f}\nإلى: ${max_price:.2f}\n\nسيتم اختيار العقد بأعلى Bid من هذا النطاق", 'info', 3)
            
        except ValueError:
            self.show_auto_close_message("خطأ", "الرجاء إدخال أرقام صحيحة!", 'error', 3)
    
    def apply_quantity(self):
        """Apply contract quantity"""
        try:
            quantity = int(self.contract_quantity.get())
            
            if quantity < 1 or quantity > 9999:
                self.show_auto_close_message("خطأ", "عدد عقود غير صحيح!\n\nيجب أن يكون:\n• الحد الأدنى: 1\n• الحد الأقصى: بدون حد", 'error', 3)
                return
            
            # Store quantity for use in trading
            self.current_contract_quantity = quantity
            
            self.quantity_note.config(text=f"✓ العدد: {quantity}")
            
            logger.info(f"Updated contract quantity: {quantity}")
            self.show_auto_close_message("نجح", f"✅ تم تطبيق عدد العقود\n\nالعدد: {quantity}\n\nسيتم استخدام هذا العدد عند فتح الصفقات", 'info', 3)
            
        except ValueError:
            self.show_auto_close_message("خطأ", "الرجاء إدخال رقم صحيح!", 'error', 3)
    
    def apply_dual_ranges(self):
        """Apply dual price ranges for monitoring + entry"""
        try:
            # Get monitoring range
            mon_min = float(self.monitoring_range_min.get())
            mon_max = float(self.monitoring_range_max.get())
            
            # Get entry range
            entry_min = float(self.entry_range_min.get())
            entry_max = float(self.entry_range_max.get())
            
            # Validation
            if mon_min >= mon_max:
                self.show_auto_close_message("خطأ", "نطاق المتابعة غير صحيح!\n\nالحد الأدنى يجب أن يكون أقل من الحد الأقصى", 'error', 3)
                return
            
            if entry_min >= entry_max:
                self.show_auto_close_message("خطأ", "نطاق الدخول غير صحيح!\n\nالحد الأدنى يجب أن يكون أقل من الحد الأقصى", 'error', 3)
                return
            
            if entry_min < mon_min or entry_max > mon_max:
                self.show_auto_close_message("تحذير", "⚠️ نطاق الدخول يجب أن يكون داخل نطاق المتابعة\n\nسيتم تطبيق التغييرات ولكن قد لا تجد عقوداً للتداول", 'warning', 4)
            
            # Update config
            config.MONITORING_RANGE_MIN = mon_min
            config.MONITORING_RANGE_MAX = mon_max
            config.ENTRY_RANGE_MIN = entry_min
            config.ENTRY_RANGE_MAX = entry_max
            
            # Keep legacy config updated (watchlist will use monitoring range)
            config.MIN_OPTION_PRICE = mon_min
            config.MAX_OPTION_PRICE = mon_max
            
            # Update status note
            self.range_note.config(
                text=f"✓ متابعة: ${mon_min:.2f}-${mon_max:.2f} | دخول: ${entry_min:.2f}-${entry_max:.2f}"
            )
            
            # Update adaptive watchlist master if running
            if self.adaptive_master:
                # Update price range manager
                from adaptive_watchlist import PriceRangeManager
                PriceRangeManager.monitoring_range = (mon_min, mon_max)
                PriceRangeManager.entry_range = (entry_min, entry_max)
                logger.info(f"Updated adaptive watchlist ranges live")
            
            logger.info(f"Updated dual ranges - Monitoring: ${mon_min:.2f}-${mon_max:.2f}, Entry: ${entry_min:.2f}-${entry_max:.2f}")
            self.show_auto_close_message("نجح", 
                f"✅ تم تطبيق النطاقات\n\n"
                f"📊 نطاق المتابعة: ${mon_min:.2f}-${mon_max:.2f}\n"
                f"   (العقود التي ستظهر في الجدول)\n\n"
                f"🎯 نطاق الدخول: ${entry_min:.2f}-${entry_max:.2f}\n"
                f"   (العقود المؤهلة للتداول)", 
                'info', 4)
            
        except ValueError:
            self.show_auto_close_message("خطأ", "الرجاء إدخال أرقام صحيحة!", 'error', 3)
    
    def update_risk_table(self):
        """Update risk settings table with current settings"""
        try:
            # Clear existing items
            for item in self.risk_tree.get_children():
                self.risk_tree.delete(item)
            
            # Add each symbol's settings
            for symbol in config.SUPPORTED_SYMBOLS:
                settings = self.db.get_risk_settings(symbol)
                
                # Format each setting
                def format_setting(setting_dict):
                    if setting_dict.get('type') == 'none' or not setting_dict.get('type'):
                        return 'NONE'
                    elif setting_dict.get('type') == 'percentage':
                        return f"{setting_dict.get('value', 0):.1f}%"
                    elif setting_dict.get('type') == 'amount':
                        return f"${setting_dict.get('value', 0):.2f}"
                    return 'NONE'
                
                stop_loss = format_setting(settings.get('stop_loss', {}))
                trailing = format_setting(settings.get('trailing_stop', {}))
                capital = format_setting(settings.get('capital_protection', {}))
                target = format_setting(settings.get('profit_target', {}))
                
                self.risk_tree.insert('', 'end', values=(
                    symbol, stop_loss, trailing, capital, target
                ))
        except Exception as e:
            logger.error(f"Error updating risk table: {e}")
    
    def apply_risk_setting(self, title, symbol, type_val, value):
        """Apply risk setting"""
        try:
            if type_val == 'none':
                # Still save to database as 'none'
                risk_type = None
                if "وقف الخسارة" in title:
                    risk_type = 'stop_loss'
                elif "وقف متحرك" in title:
                    risk_type = 'trailing_stop'
                elif "حماية" in title:
                    risk_type = 'capital_protection'
                elif "الهدف" in title:
                    risk_type = 'profit_target'
                
                if risk_type:
                    self.db.save_risk_setting(symbol, risk_type, 'none', 0)
                    self.update_risk_table()
                    self.show_auto_close_message("معلومات", f"تم تعطيل {title} على {symbol}", 'info', 3)
                return
            
            # Validate value
            try:
                val = float(value)
                if val <= 0:
                    self.show_auto_close_message("خطأ", "الرجاء إدخال قيمة موجبة!", 'error', 3)
                    return
            except ValueError:
                self.show_auto_close_message("خطأ", "الرجاء إدخال رقم صحيح!", 'error', 3)
                return
            
            # Determine risk type
            risk_type = None
            if "وقف الخسارة" in title:
                risk_type = 'stop_loss'
            elif "وقف متحرك" in title:
                risk_type = 'trailing_stop'
            elif "حماية" in title:
                risk_type = 'capital_protection'
            elif "الهدف" in title:
                risk_type = 'profit_target'
            
            if risk_type:
                # Save to database
                self.db.save_risk_setting(symbol, risk_type, type_val, val)
                # Update table display
                self.update_risk_table()
                self.show_auto_close_message("نجح", f"تم تطبيق {title} على {symbol}\nالنوع: {type_val}\nالقيمة: {val}", 'info', 3)
            
        except Exception as e:
            logger.error(f"Error applying risk setting: {e}")
            self.show_auto_close_message("خطأ", f"حدث خطأ: {str(e)}", 'error', 3)
    
    # ... (continued in next part due to length)
    
    def update_signal_counts(self):
        """Update signal counts from database"""
        if not self.update_tasks_running:
            return
        
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            counts = self.db.get_signal_count(today)
            
            self.signals_labels['CALL'].config(text=str(counts['CALL']))
            self.signals_labels['PUT'].config(text=str(counts['PUT']))
            self.signals_labels['إجمالي'].config(text=str(counts['total']))
            
            logger.debug(f"📊 Signal counts updated: CALL={counts['CALL']}, PUT={counts['PUT']}, Total={counts['total']}")
        except Exception as e:
            logger.error(f"Error updating signal counts: {e}")
        
        # Update every 2 seconds
        self.root.after(2000, self.update_signal_counts)
    
    def update_balance(self):
        """Update balance display"""
        if not self.update_tasks_running:
            return
        
        balance = self.trading_system.get_current_balance()
        self.balance_label.config(text=f"${balance:,.2f}")
        
        self.root.after(10000, self.update_balance)
    
    def update_ibkr_connection_status(self):
        """Update IBKR connection status indicator"""
        if not self.update_tasks_running:
            return
        
        # Check actual connection status from IBKR client
        is_connected = self.trading_system.ibkr.connected
        self.update_ibkr_status(is_connected)
        
        # Check every 3 seconds
        self.root.after(3000, self.update_ibkr_connection_status)
    
    def update_watchlist(self):
        """Update watchlist data - staggered updates for better performance"""
        if not self.update_tasks_running:
            return
        
        # Check if we have any widgets to update
        if not hasattr(self, 'watchlist_widgets') or not self.watchlist_widgets:
            logger.warning("No watchlist widgets to update")
            self.root.after(config.STOCK_PRICE_UPDATE_INTERVAL * 1000, self.update_watchlist)
            return
        
        # Get list of symbols to update (ordered: SPX, NDX, SPY, QQQ)
        symbols = list(self.watchlist_widgets.keys())
        ordered_symbols = []
        for preferred in ['SPX', 'NDX', 'SPY', 'QQQ']:
            if preferred in symbols:
                ordered_symbols.append(preferred)
        # Add any remaining symbols
        for sym in symbols:
            if sym not in ordered_symbols:
                ordered_symbols.append(sym)
        
        # Update symbols with 0.25-second stagger between each using root.after
        for idx, symbol in enumerate(ordered_symbols):
            # Delay: 0ms for first, 250ms for second, 500ms for third, etc.
            delay_ms = int(idx * 250)
            # Use root.after instead of threading.Timer for thread safety
            # Only update stock price (quick update)
            self.root.after(delay_ms, lambda s=symbol: self.update_symbol_watchlist(s, price_only=True))
            logger.debug(f"Scheduled {symbol} stock price update with {delay_ms}ms delay")
            
            # Reset stock countdown timer when update starts
            self.stock_countdown[symbol] = config.STOCK_PRICE_UPDATE_INTERVAL
        
        # Repeat every 1 second for stock prices
        self.root.after(config.STOCK_PRICE_UPDATE_INTERVAL * 1000, self.update_watchlist)
        
        # Schedule contract price updates separately (every 15 seconds)
        if not hasattr(self, '_contract_update_scheduled'):
            self._contract_update_scheduled = True
            self.root.after(config.CONTRACT_PRICE_UPDATE_INTERVAL * 1000, self.update_contract_prices)
    
    def manual_refresh_watchlist(self, symbol: str):
        """Manual refresh for a specific symbol - triggered by button click"""
        from config import WATCHLIST_CONTRACTS
        
        contract_count = WATCHLIST_CONTRACTS.get(symbol, 20)
        logger.info(f"🔄 Manual refresh requested for {symbol} ({contract_count} contracts)")
        
        if not self.system_running:
            self.show_auto_close_message("تحذير", 
                                  f"⚠️ يجب تشغيل النظام أولاً!\n\n"
                                  f"اضغط على زر '▶️ تشغيل النظام' في الأعلى", 'warning', 3)
            return
        
        if not hasattr(self, 'trading_system') or not self.trading_system:
            messagebox.showerror("خطأ", "❌ نظام التداول غير متاح!")
            return
        
        # Show loading message
        if symbol in self.watchlist_widgets:
            widgets = self.watchlist_widgets[symbol]
            widgets['price_label'].config(text="🔄 جاري التحديث...")
            widgets['expiry_label'].config(text=f"⏳ جلب {contract_count} عقد...")
            widgets['contracts_info'].config(text="⏳ انتظر...")
        
        # Force update immediately
        logger.info(f"✅ Triggering full refresh for {symbol}")
        self.update_symbol_watchlist(symbol, force_full_update=True)
    
    def _force_initial_watchlist_update(self):
        """Force initial watchlist update for all symbols immediately after system start"""
        logger.info("="*60)
        logger.info("🚀 FORCING INITIAL WATCHLIST UPDATE FOR ALL SYMBOLS")
        logger.info("="*60)
        
        if not self.system_running:
            logger.error("❌ System not running - skipping initial update")
            return
        
        if not hasattr(self, 'watchlist_widgets') or not self.watchlist_widgets:
            logger.error("❌ No watchlist widgets - skipping initial update")
            return
        
        # Get all symbols
        symbols = list(self.watchlist_widgets.keys())
        logger.info(f"📋 Symbols to update: {symbols}")
        
        # Update SPX first (highest priority), then others with small delays
        for idx, symbol in enumerate(symbols):
            delay_ms = idx * 1000  # 1 second between each symbol
            logger.info(f"⏰ Scheduling {symbol} initial update in {delay_ms}ms")
            self.root.after(delay_ms, lambda s=symbol: self.update_symbol_watchlist(s))
    
    def update_contract_prices(self):
        """Update contract prices for all symbols (separate from stock price update)"""
        if not self.update_tasks_running:
            return
        
        # Check if we have any widgets to update
        if not hasattr(self, 'watchlist_widgets') or not self.watchlist_widgets:
            self.root.after(config.CONTRACT_PRICE_UPDATE_INTERVAL * 1000, self.update_contract_prices)
            return
        
        # Get list of symbols
        symbols = list(self.watchlist_widgets.keys())
        ordered_symbols = []
        for preferred in ['SPX', 'NDX', 'SPY', 'QQQ']:
            if preferred in symbols:
                ordered_symbols.append(preferred)
        for sym in symbols:
            if sym not in ordered_symbols:
                ordered_symbols.append(sym)
        
        # Update contract prices for each symbol
        for idx, symbol in enumerate(ordered_symbols):
            delay_ms = int(idx * 250)
            self.root.after(delay_ms, lambda s=symbol: self.update_symbol_watchlist(s, price_only=False))
            logger.debug(f"Scheduled {symbol} contract price update with {delay_ms}ms delay")
            
            # Reset contract countdown timer when update starts
            self.contract_countdown[symbol] = config.CONTRACT_PRICE_UPDATE_INTERVAL
        
        # Repeat every 15 seconds
        self.root.after(config.CONTRACT_PRICE_UPDATE_INTERVAL * 1000, self.update_contract_prices)
    
    def update_symbol_watchlist_simple(self, symbol: str, force_init: bool = False, price_only: bool = False):
        """Update watchlist for a specific symbol using Simple Watchlist System
        
        Args:
            symbol: Symbol to update
            force_init: If True, forces re-fetch of contracts
            price_only: If True, only updates stock price
        """
        try:
            logger.info(f"🚀 Simple watchlist update for {symbol} (force_init={force_init}, price_only={price_only})")
            
            # Check if system is running
            if not self.system_running:
                logger.error(f"❌ System not running - cannot update {symbol}")
                return
            
            # Check if symbol exists in widgets
            if symbol not in self.watchlist_widgets:
                logger.warning(f"❌ {symbol} not found in watchlist_widgets")
                return
            
            widgets = self.watchlist_widgets[symbol]
            
            # Check simple watchlist availability
            if not self.simple_watchlist:
                logger.error("❌ Simple Watchlist Manager not initialized")
                return
            
            # Update in background thread
            def update_thread():
                try:
                    # 1. جلب السعر الحالي
                    future = asyncio.run_coroutine_threadsafe(
                        self.simple_watchlist.get_current_price(symbol),
                        self.async_loop
                    )
                    price = future.result(timeout=15)
                    
                    if price and price > 0:
                        # تحديث السعر في الواجهة
                        self.root.after(0, lambda p=price: widgets['price_label'].config(text=f"${p:.2f}"))
                        logger.info(f"✅ {symbol} price: ${price:.2f}")
                    else:
                        logger.error(f"❌ Could not get price for {symbol}")
                        return
                    
                    # إذا price_only، نتوقف هنا
                    if price_only:
                        return
                    
                    # 2. جلب أو تحديث العقود
                    if force_init or symbol not in self.simple_watchlist.active_contracts:
                        # جلب تاريخ الانتهاء (0DTE)
                        ibkr_conn = None
                        if hasattr(self.trading_system, 'ibkr_connections') and symbol in self.trading_system.ibkr_connections:
                            ibkr_conn = self.trading_system.ibkr_connections[symbol]
                        else:
                            ibkr_conn = getattr(self.trading_system, 'ibkr', None)
                        
                        if not ibkr_conn:
                            logger.error("❌ No IBKR connection available")
                            return
                        
                        future_expiry = asyncio.run_coroutine_threadsafe(
                            ibkr_conn.get_expiry_date(),
                            self.async_loop
                        )
                        expiry = future_expiry.result(timeout=10)
                        expiry_formatted = f"{expiry[6:8]}/{expiry[4:6]}/{expiry[0:4]}"
                        
                        # تحديث تاريخ الانتهاء في الواجهة
                        self.root.after(0, lambda e=expiry_formatted: widgets['expiry_label'].config(text=f"0DTE: {e}"))
                        
                        logger.info(f"📅 Using 0DTE: {expiry_formatted}")
                        
                        # جلب عقود CALL
                        logger.info(f"🔍 Searching for {symbol} CALL contracts...")
                        future_call = asyncio.run_coroutine_threadsafe(
                            self.simple_watchlist.find_contracts_in_range(
                                symbol, expiry, 'CALL',
                                config.MONITORING_RANGE_MIN,
                                config.MONITORING_RANGE_MAX
                            ),
                            self.async_loop
                        )
                        call_contracts = future_call.result(timeout=60)
                        
                        # جلب عقود PUT
                        logger.info(f"🔍 Searching for {symbol} PUT contracts...")
                        future_put = asyncio.run_coroutine_threadsafe(
                            self.simple_watchlist.find_contracts_in_range(
                                symbol, expiry, 'PUT',
                                config.MONITORING_RANGE_MIN,
                                config.MONITORING_RANGE_MAX
                            ),
                            self.async_loop
                        )
                        put_contracts = future_put.result(timeout=60)
                        
                    else:
                        # تحديث أسعار العقود الموجودة
                        logger.info(f"🔄 Updating prices for existing {symbol} contracts...")
                        
                        future_call = asyncio.run_coroutine_threadsafe(
                            self.simple_watchlist.update_contracts_prices(symbol, 'CALL'),
                            self.async_loop
                        )
                        call_contracts = future_call.result(timeout=30)
                        
                        future_put = asyncio.run_coroutine_threadsafe(
                            self.simple_watchlist.update_contracts_prices(symbol, 'PUT'),
                            self.async_loop
                        )
                        put_contracts = future_put.result(timeout=30)
                        
                        # ✅ فحص ذكي: إذا خرجت العقود عن النطاق، أعد جلب عقود جديدة
                        call_in_range = sum(1 for c in call_contracts if config.MONITORING_RANGE_MIN <= (c.get('ask', 0) or 0) <= config.MONITORING_RANGE_MAX)
                        put_in_range = sum(1 for c in put_contracts if config.MONITORING_RANGE_MIN <= (c.get('ask', 0) or 0) <= config.MONITORING_RANGE_MAX)
                        
                        if call_in_range < 5 or put_in_range < 5:
                            logger.warning(f"⚠️ {symbol}: Only {call_in_range} CALL and {put_in_range} PUT in range - fetching new contracts!")
                            
                            # جلب تاريخ الانتهاء (0DTE)
                            ibkr_conn = None
                            if hasattr(self.trading_system, 'ibkr_connections') and symbol in self.trading_system.ibkr_connections:
                                ibkr_conn = self.trading_system.ibkr_connections[symbol]
                            else:
                                ibkr_conn = getattr(self.trading_system, 'ibkr', None)
                            
                            if ibkr_conn:
                                future_expiry = asyncio.run_coroutine_threadsafe(
                                    ibkr_conn.get_expiry_date(),
                                    self.async_loop
                                )
                                expiry = future_expiry.result(timeout=10)
                                
                                # جلب عقود جديدة
                                logger.info(f"🔍 Re-fetching {symbol} contracts at current price ${price:.2f}...")
                                
                                future_call_new = asyncio.run_coroutine_threadsafe(
                                    self.simple_watchlist.find_contracts_in_range(
                                        symbol, expiry, 'CALL',
                                        config.MONITORING_RANGE_MIN,
                                        config.MONITORING_RANGE_MAX
                                    ),
                                    self.async_loop
                                )
                                call_contracts = future_call_new.result(timeout=60)
                                
                                future_put_new = asyncio.run_coroutine_threadsafe(
                                    self.simple_watchlist.find_contracts_in_range(
                                        symbol, expiry, 'PUT',
                                        config.MONITORING_RANGE_MIN,
                                        config.MONITORING_RANGE_MAX
                                    ),
                                    self.async_loop
                                )
                                put_contracts = future_put_new.result(timeout=60)
                                
                                logger.info(f"✅ Fetched new contracts: {len(call_contracts)} CALL, {len(put_contracts)} PUT")
                    
                    # 3. تحديث الواجهة
                    def update_gui():
                        # مسح العقود القديمة
                        for item in widgets['call_tree'].get_children():
                            widgets['call_tree'].delete(item)
                        for item in widgets['put_tree'].get_children():
                            widgets['put_tree'].delete(item)
                        
                        # حساب العقود ضمن النطاق
                        call_in_range = sum(1 for c in call_contracts if config.MONITORING_RANGE_MIN <= (c.get('ask', 0) or 0) <= config.MONITORING_RANGE_MAX)
                        put_in_range = sum(1 for c in put_contracts if config.MONITORING_RANGE_MIN <= (c.get('ask', 0) or 0) <= config.MONITORING_RANGE_MAX)
                        
                        # إضافة عقود CALL
                        for contract in call_contracts[:10]:  # أول 10 فقط
                            strike = contract['strike']
                            bid = f"${contract['bid']:.2f}" if contract['bid'] else "N/A"
                            ask = f"${contract['ask']:.2f}" if contract['ask'] else "N/A"
                            widgets['call_tree'].insert('', 'end', text=f"${strike:.0f}", values=(bid, ask))
                        
                        # إضافة عقود PUT
                        for contract in put_contracts[:10]:  # أول 10 فقط
                            strike = contract['strike']
                            bid = f"${contract['bid']:.2f}" if contract['bid'] else "N/A"
                            ask = f"${contract['ask']:.2f}" if contract['ask'] else "N/A"
                            widgets['put_tree'].insert('', 'end', text=f"${strike:.0f}", values=(bid, ask))
                        
                        # تحديث معلومات العقود مع عرض العقود ضمن النطاق
                        info_text = f"CALL: {len(call_contracts)} ({call_in_range} in range) | PUT: {len(put_contracts)} ({put_in_range} in range)"
                        widgets['contracts_info'].config(text=info_text, fg=self.colors['accent_green'])
                        
                        logger.info(f"✅ Updated {symbol}: {len(call_contracts)} CALL ({call_in_range} in range), {len(put_contracts)} PUT ({put_in_range} in range)")
                    
                    self.root.after(0, update_gui)
                    
                except Exception as e:
                    logger.error(f"❌ Error in simple watchlist update: {e}", exc_info=True)
            
            threading.Thread(target=update_thread, daemon=True).start()
            
        except Exception as e:
            logger.error(f"❌ Error in update_symbol_watchlist_simple: {e}", exc_info=True)
    
    def update_symbol_watchlist_adaptive(self, symbol: str, force_init: bool = False, price_only: bool = False):
        """Update watchlist for a specific symbol using Adaptive Watchlist System
        
        Args:
            symbol: Symbol to update
            force_init: If True, forces reinitialization of watchlist
            price_only: If True, only updates stock price (not contract prices)
        """
        try:
            logger.info(f"🚀 Adaptive watchlist update for {symbol} (force_init={force_init}, price_only={price_only})")
            
            # Check if system is running
            if not self.system_running:
                logger.error(f"❌ System not running - cannot update {symbol}")
                return
            
            # Check if symbol exists in widgets
            if symbol not in self.watchlist_widgets:
                logger.warning(f"❌ {symbol} not found in watchlist_widgets")
                return
            
            widgets = self.watchlist_widgets[symbol]
            
            # Get dedicated IBKR connection for this symbol
            ibkr_conn = None
            if hasattr(self.trading_system, 'ibkr_connections') and symbol in self.trading_system.ibkr_connections:
                ibkr_conn = self.trading_system.ibkr_connections[symbol]
            else:
                ibkr_conn = getattr(self.trading_system, 'ibkr', None)
            
            if not ibkr_conn or not getattr(ibkr_conn, 'connected', False):
                logger.error(f"❌ IBKR connection not available for {symbol}")
                return
            
            # Update stock price in background
            def update_price_thread():
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        ibkr_conn.get_underlying_price(symbol),
                        self.async_loop
                    )
                    price = future.result(timeout=15)
                    
                    if price and price > 0:
                        self.root.after(0, lambda p=price: widgets['price_label'].config(text=f"${p:.2f}"))
                        logger.info(f"✅ {symbol} price: ${price:.2f}")
                        
                        # If not price-only mode, start/update adaptive watchlist
                        if not price_only:
                            self._start_adaptive_watchlist_for_symbol(symbol, price, force_init)
                    
                except Exception as e:
                    logger.error(f"❌ Error updating {symbol} price: {e}")
            
            threading.Thread(target=update_price_thread, daemon=True).start()
            
        except Exception as e:
            logger.error(f"❌ Error in adaptive watchlist update for {symbol}: {e}", exc_info=True)
    
    def _start_adaptive_watchlist_for_symbol(self, symbol: str, price: float, force_init: bool):
        """Start or update adaptive watchlist for a symbol"""
        try:
            # Run in async loop
            def async_start():
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self._async_start_adaptive_watchlist(symbol, price, force_init),
                        self.async_loop
                    )
                    future.result(timeout=30)
                except Exception as e:
                    logger.error(f"❌ Error starting adaptive watchlist for {symbol}: {e}", exc_info=True)
            
            threading.Thread(target=async_start, daemon=True).start()
            
        except Exception as e:
            logger.error(f"❌ Error in _start_adaptive_watchlist_for_symbol for {symbol}: {e}", exc_info=True)
    
    async def _async_start_adaptive_watchlist(self, symbol: str, price: float, force_init: bool):
        """Async: Start adaptive watchlist for a symbol"""
        try:
            logger.info(f"🔄 Starting adaptive watchlist for {symbol} at ${price:.2f}")
            
            # Check if symbol already initialized
            if not force_init and self.adaptive_master.is_symbol_initialized(symbol):
                logger.info(f"✅ {symbol} already initialized - updating display")
                self._update_adaptive_display(symbol)
                return
            
            # Initialize symbol in adaptive master
            await self.adaptive_master.start_symbol_watchlist(symbol, price)
            logger.info(f"✅ Adaptive watchlist initialized for {symbol}")
            
            # Wait a bit for initial data
            await asyncio.sleep(2)
            
            # Update display
            self._update_adaptive_display(symbol)
            
            # Schedule periodic updates
            if not hasattr(self, '_adaptive_update_tasks'):
                self._adaptive_update_tasks = {}
            
            # Cancel existing task if any
            if symbol in self._adaptive_update_tasks:
                self._adaptive_update_tasks[symbol].cancel()
            
            # Create new periodic update task
            async def periodic_update():
                while self.system_running:
                    await asyncio.sleep(5)  # Update every 5 seconds
                    if symbol in self.watchlist_widgets:
                        self._update_adaptive_display(symbol)
            
            task = asyncio.create_task(periodic_update())
            self._adaptive_update_tasks[symbol] = task
            
        except Exception as e:
            logger.error(f"❌ Error in _async_start_adaptive_watchlist for {symbol}: {e}", exc_info=True)
    
    def _update_adaptive_display(self, symbol: str):
        """Update GUI display with data from adaptive watchlist"""
        try:
            if symbol not in self.watchlist_widgets:
                return
            
            widgets = self.watchlist_widgets[symbol]
            
            # Get data from adaptive master
            call_contracts = self.adaptive_master.get_entry_contracts(symbol, 'CALL')
            put_contracts = self.adaptive_master.get_entry_contracts(symbol, 'PUT')
            
            # Get active groups (for status display)
            call_groups = self.adaptive_master.get_active_groups(symbol, 'CALL')
            put_groups = self.adaptive_master.get_active_groups(symbol, 'PUT')
            
            # Update trees
            def update_trees():
                # Clear existing items
                for item in widgets['call_tree'].get_children():
                    widgets['call_tree'].delete(item)
                for item in widgets['put_tree'].get_children():
                    widgets['put_tree'].delete(item)
                
                # Populate CALL tree
                for contract in call_contracts[:10]:  # Show top 10
                    strike = contract['strike']
                    bid = f"${contract['bid']:.2f}" if contract['bid'] else "N/A"
                    ask = f"${contract['ask']:.2f}" if contract['ask'] else "N/A"
                    widgets['call_tree'].insert('', 'end', text=f"${strike:.0f}", values=(bid, ask))
                
                # Populate PUT tree
                for contract in put_contracts[:10]:  # Show top 10
                    strike = contract['strike']
                    bid = f"${contract['bid']:.2f}" if contract['bid'] else "N/A"
                    ask = f"${contract['ask']:.2f}" if contract['ask'] else "N/A"
                    widgets['put_tree'].insert('', 'end', text=f"${strike:.0f}", values=(bid, ask))
                
                # Update contract info label
                info_text = f"📊 CALL: {len(call_contracts)} عقد (🟢 {len(call_groups)} groups) | PUT: {len(put_contracts)} عقد (🟢 {len(put_groups)} groups)"
                widgets['contracts_info'].config(text=info_text, fg=self.colors['accent_green'])
                
                logger.debug(f"✅ Updated {symbol} display: {len(call_contracts)} CALL, {len(put_contracts)} PUT")
            
            self.root.after(0, update_trees)
            
        except Exception as e:
            logger.error(f"❌ Error updating adaptive display for {symbol}: {e}", exc_info=True)
    
    def update_countdown_timers(self):
        """Update countdown timers for all symbols"""
        if not self.update_tasks_running:
            return
        
        # Check if we have any widgets to update
        if not hasattr(self, 'watchlist_widgets') or not self.watchlist_widgets:
            self.root.after(1000, self.update_countdown_timers)
            return
        
        # Update countdown for each symbol
        for symbol in self.watchlist_widgets:
            widgets = self.watchlist_widgets[symbol]
            
            # Update stock price countdown
            if symbol in self.stock_countdown:
                self.stock_countdown[symbol] -= 1
                if self.stock_countdown[symbol] < 0:
                    self.stock_countdown[symbol] = config.STOCK_PRICE_UPDATE_INTERVAL
                
                widgets['stock_countdown'].config(text=f"⏱️ السعر: {self.stock_countdown[symbol]}s")
            else:
                # Initialize countdown
                self.stock_countdown[symbol] = config.STOCK_PRICE_UPDATE_INTERVAL
                widgets['stock_countdown'].config(text=f"⏱️ السعر: {self.stock_countdown[symbol]}s")
            
            # Update contract price countdown
            if symbol in self.contract_countdown:
                self.contract_countdown[symbol] -= 1
                if self.contract_countdown[symbol] < 0:
                    self.contract_countdown[symbol] = config.CONTRACT_PRICE_UPDATE_INTERVAL
                
                widgets['contract_countdown'].config(text=f"📊 العقود: {self.contract_countdown[symbol]}s")
            else:
                # Initialize countdown
                self.contract_countdown[symbol] = config.CONTRACT_PRICE_UPDATE_INTERVAL
                widgets['contract_countdown'].config(text=f"📊 العقود: {self.contract_countdown[symbol]}s")
        
        # Repeat every second
        self.root.after(1000, self.update_countdown_timers)
    
    def update_symbol_watchlist(self, symbol: str, force_full_update: bool = False, price_only: bool = False):
        """Update watchlist for a specific symbol
        
        Args:
            symbol: Symbol to update
            force_full_update: If True, forces full page fetch (50 contracts)
            price_only: If True, only updates stock price (not contract prices)
        """
        # Use simple watchlist system if enabled
        if config.SIMPLE_WATCHLIST_ENABLED and self.simple_watchlist:
            logger.info(f"🚀 Using Simple Watchlist System for {symbol}")
            self.update_symbol_watchlist_simple(symbol, force_full_update, price_only)
            return
        
        # Use adaptive watchlist system if enabled and master is available
        if config.ADAPTIVE_WATCHLIST_ENABLED and self.adaptive_master:
            logger.info(f"🚀 Using Adaptive Watchlist System for {symbol}")
            self.update_symbol_watchlist_adaptive(symbol, force_full_update, price_only)
            return
        
        # Otherwise, use old system (current implementation)
        try:
            print(f"\n{'='*60}")
            print(f"🔄 بدء تحديث جدول المراقبة لـ {symbol}")
            print(f"{'='*60}")
            logger.info(f"🔄 Updating watchlist for {symbol}...")
            
            # Check if system is running
            if not self.system_running:
                print(f"❌ النظام غير مشغل!")
                logger.error(f"❌ System not running - cannot update {symbol}")
                return
            
            print(f"✅ النظام مشغل")
            
            # Check if symbol still exists in widgets
            if symbol not in self.watchlist_widgets:
                print(f"❌ {symbol} غير موجود في watchlist_widgets")
                logger.warning(f"❌ {symbol} not found in watchlist_widgets")
                return
            
            print(f"✅ {symbol} موجود في watchlist_widgets")
            
            # Check if tab is still open (not closed)
            widgets = self.watchlist_widgets[symbol]
            tab_exists = False
            try:
                # Check if the tab widget still exists in notebook
                for i in range(self.watchlist_notebook.index('end')):
                    tab_text = self.watchlist_notebook.tab(i, 'text').strip()
                    if tab_text == symbol:
                        tab_exists = True
                        break
            except Exception as e:
                logger.debug(f"Error checking tab existence for {symbol}: {e}")
            
            if not tab_exists:
                logger.info(f"ℹ️ Tab for {symbol} is closed - skipping update")
                return
            
            # Check if trading system exists
            if not hasattr(self, 'trading_system') or not self.trading_system:
                print(f"❌ نظام التداول غير مهيأ!")
                logger.error(f"❌ Trading system not initialized!")
                return
            
            print(f"✅ نظام التداول مهيأ")
            
            # Get dedicated IBKR connection for this symbol
            ibkr_conn = None
            if hasattr(self.trading_system, 'ibkr_connections') and symbol in self.trading_system.ibkr_connections:
                ibkr_conn = self.trading_system.ibkr_connections[symbol]
                print(f"✅ استخدام اتصال مخصص لـ {symbol}")
                logger.info(f"✅ Using dedicated connection for {symbol}")
            else:
                # Fallback to main connection
                if hasattr(self.trading_system, 'ibkr'):
                    ibkr_conn = self.trading_system.ibkr
                    print(f"ℹ️ استخدام الاتصال الرئيسي لـ {symbol}")
                    logger.info(f"ℹ️ Using main IBKR connection for {symbol}")
                else:
                    print(f"❌ لا يوجد اتصال IBKR متاح!")
                    logger.error(f"❌ No IBKR connection available!")
                    return
            
            # Check if IBKR is connected
            if not ibkr_conn:
                print(f"❌ كائن اتصال IBKR فارغ لـ {symbol}")
                logger.error(f"❌ IBKR connection object is None for {symbol}")
                return
                
            if not hasattr(ibkr_conn, 'connected') or not ibkr_conn.connected:
                print(f"❌ اتصال IBKR لـ {symbol} غير متصل!")
                print(f"   حالة الاتصال: {getattr(ibkr_conn, 'connected', 'N/A')}")
                logger.error(f"❌ IBKR connection for {symbol} not available or not connected")
                logger.error(f"   Connection status: connected={getattr(ibkr_conn, 'connected', 'N/A')}")
                return
            
            print(f"✅ اتصال IBKR متصل لـ {symbol}")
            
            # Check if async loop is available - wait if not ready yet
            if not self.async_loop:
                print(f"⚠️ Async loop غير جاهز، إعادة المحاولة بعد ثانيتين...")
                logger.warning("⚠️ Async loop not ready yet, will retry in 2 seconds...")
                # Retry after 2 seconds
                self.root.after(2000, lambda: self.update_symbol_watchlist(symbol))
                return
            
            print(f"✅ Async loop جاهز")
            
            # If price_only mode, just update stock price and return
            if price_only:
                logger.debug(f"💹 Price-only mode for {symbol} - updating stock price only")
                
                # Run in separate thread
                def update_stock_price():
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            ibkr_conn.get_underlying_price(symbol), 
                            self.async_loop)
                        price = future.result(timeout=15)
                        
                        if price and price > 0:
                            self.root.after(0, lambda p=price: widgets['price_label'].config(text=f"${p:.2f}"))
                            logger.debug(f"✅ {symbol} stock price: ${price:.2f}")
                    except Exception as e:
                        logger.debug(f"⚠️ Error updating {symbol} stock price: {e}")
                
                threading.Thread(target=update_stock_price, daemon=True).start()
                return
            
            # Check if we should do full update (fetch 50 contracts) or just price update
            should_fetch_pages = force_full_update
            time_since_last_update = None
            
            if symbol in self.last_page_update:
                time_since_last_update = (datetime.now() - self.last_page_update[symbol]).total_seconds()
                # Full update every 30 minutes (1800 seconds)
                if time_since_last_update >= config.WATCHLIST_UPDATE_INTERVAL:
                    should_fetch_pages = True
                    logger.info(f"⏰ {time_since_last_update/60:.1f} minutes since last update - full refresh needed")
            else:
                # First time - always fetch contracts
                should_fetch_pages = True
                logger.info(f"🆕 First update for {symbol} - fetching all contracts")
            
            print(f"📊 بدء Thread للحصول على البيانات...")
            logger.info(f"✅ All checks passed for {symbol}, starting update thread (full_update={should_fetch_pages})...")
            
            # Run in separate thread to avoid blocking GUI
            def update_in_thread():
                nonlocal should_fetch_pages  # Allow modifying parent scope variable
                try:
                    # Use the existing async loop with run_coroutine_threadsafe
                    import concurrent.futures
                    
                    print(f"\n📊 Thread بدأ لـ {symbol}")
                    logger.info(f"📊 Thread started for {symbol}")
                    
                    # Get underlying price using dedicated connection
                    print(f"📊 جلب سعر {symbol} من IBKR...")
                    logger.info(f"📊 Getting {symbol} price...")
                    future = asyncio.run_coroutine_threadsafe(
                        ibkr_conn.get_underlying_price(symbol), 
                        self.async_loop)
                    
                    try:
                        print(f"⏳ انتظار السعر (مهلة 15 ثانية)...")
                        price = future.result(timeout=15)  # Increased timeout to 15 seconds
                    except concurrent.futures.TimeoutError:
                        print(f"❌ انتهت المهلة! لم يتم الحصول على سعر {symbol} خلال 15 ثانية")
                        logger.error(f"❌ Timeout getting {symbol} price (15s)")
                        return
                    except Exception as e:
                        print(f"❌ خطأ في الحصول على سعر {symbol}: {e}")
                        logger.error(f"❌ Exception getting {symbol} price: {e}")
                        return
                    
                    if price and price > 0:
                        print(f"✅✅ تم الحصول على سعر {symbol}: ${price:.2f}")
                        logger.info(f"✅ {symbol} price: ${price:.2f}")
                        self.root.after(0, lambda p=price: widgets['price_label'].config(
                            text=f"${p:.2f}"))
                        
                        # Check if price is outside contract range - trigger refetch if yes
                        if not should_fetch_pages and symbol in self.watchlist_contracts:
                            price_out_of_range = self._check_price_out_of_range(symbol, price)
                            if price_out_of_range:
                                logger.warning(f"⚠️ {symbol} price ${price:.2f} is outside contract range - forcing refetch!")
                                should_fetch_pages = True
                    else:
                        print(f"❌ فشل الحصول على سعر {symbol} - القيمة: {price}")
                        logger.error(f"❌ Could not get {symbol} price - returned: {price}")
                        return
                    
                    # Decide what to do based on should_fetch_pages flag
                    if should_fetch_pages:
                        # FULL UPDATE: Fetch all 50 contracts (5 pages)
                        logger.info(f"📥 Full update mode: fetching all 50 contracts for {symbol}")
                        
                        # Get expiry date (use custom if set, otherwise get 0DTE)
                        custom_expiry = self.selected_expiry_dates.get(symbol, None)
                        
                        if custom_expiry:
                            # Use custom expiry date
                            expiry = custom_expiry
                            expiry_formatted = f"{expiry[6:8]}/{expiry[4:6]}/{expiry[0:4]}"
                            logger.info(f"📅 Using custom expiry: {expiry} ({expiry_formatted})")
                        else:
                            # Get 0DTE from IBKR
                            logger.info(f"📅 Getting 0DTE expiry for {symbol}...")
                            future = asyncio.run_coroutine_threadsafe(
                                ibkr_conn.get_expiry_date(),
                                self.async_loop)
                            expiry = future.result(timeout=10)
                            expiry_formatted = f"{expiry[6:8]}/{expiry[4:6]}/{expiry[0:4]}"
                            logger.info(f"✅ Using 0DTE expiry: {expiry} ({expiry_formatted})")
                        
                        # Update expiry label
                        display_text = f"0DTE: {expiry_formatted}" if not custom_expiry else expiry_formatted
                        self.root.after(0, lambda e=display_text: widgets['expiry_label'].config(text=e))
                        
                        # Get contracts for CALL options
                        logger.info(f"📊 Getting {symbol} CALL options for expiry {expiry}...")
                        from config import WATCHLIST_CONTRACTS, MIN_OPTION_PRICE, MAX_OPTION_PRICE
                        contract_count = WATCHLIST_CONTRACTS.get(symbol, 20)
                        timeout = 120  # زيادة timeout إلى 120 ثانية لجميع الرموز للأمان
                        
                        # Define target price range for Smart Grouping
                        target_range = (MIN_OPTION_PRICE, MAX_OPTION_PRICE)
                        logger.info(f"🎯 Target price range: ${target_range[0]}-${target_range[1]}")
                        
                        try:
                            future = asyncio.run_coroutine_threadsafe(
                                ibkr_conn.get_watchlist_options(symbol, 'CALL', count=contract_count, expiry_date=expiry, target_price_range=target_range),
                                self.async_loop)
                            call_data = future.result(timeout=timeout)
                            logger.info(f"✅ Got {len(call_data)} CALL contracts for {symbol} (Target Groups Only)")
                        except concurrent.futures.TimeoutError:
                            logger.error(f"❌ Timeout getting {symbol} CALL contracts ({timeout}s)")
                            call_data = []
                        except Exception as e:
                            logger.error(f"❌ Exception getting {symbol} CALL contracts: {e}")
                            call_data = []
                        
                        # Get contracts for PUT options
                        logger.info(f"📊 Getting {symbol} PUT options for expiry {expiry}...")
                        
                        try:
                            future = asyncio.run_coroutine_threadsafe(
                                ibkr_conn.get_watchlist_options(symbol, 'PUT', count=contract_count, expiry_date=expiry, target_price_range=target_range),
                                self.async_loop)
                            put_data = future.result(timeout=timeout)
                            logger.info(f"✅ Got {len(put_data)} PUT contracts for {symbol} (Target Groups Only)")
                        except concurrent.futures.TimeoutError:
                            logger.error(f"❌ Timeout getting {symbol} PUT contracts ({timeout}s)")
                            put_data = []
                        except Exception as e:
                            logger.error(f"❌ Exception getting {symbol} PUT contracts: {e}")
                            put_data = []
                        
                        # Store contracts data
                        self.watchlist_contracts[symbol] = {'CALL': call_data, 'PUT': put_data}
                        self.last_page_update[symbol] = datetime.now()
                        
                        # Update contract count info
                        info_text = f"📊 CALL: {len(call_data)} | PUT: {len(put_data)}"
                        self.root.after(0, lambda t=info_text: widgets['contracts_info'].config(text=t))
                        
                        # Display all contracts directly
                        self.root.after(0, lambda c=call_data, s=symbol: self._update_tree_data(
                            widgets['call_tree'], c, s, 'CALL'))
                        self.root.after(0, lambda p=put_data, s=symbol: self._update_tree_data(
                            widgets['put_tree'], p, s, 'PUT'))
                        
                        logger.info(f"✅ Successfully updated {symbol} watchlist with {len(call_data)} CALLs, {len(put_data)} PUTs")
                    
                    else:
                        # PRICE UPDATE ONLY: Just refresh display with existing data
                        logger.info(f"💹 Price update mode: refreshing display")
                        
                        if symbol not in self.watchlist_contracts:
                            logger.warning(f"⚠️ No contract data for {symbol} - skipping")
                            return
                        
                        contracts_data = self.watchlist_contracts[symbol]
                        call_data = contracts_data.get('CALL', [])
                        put_data = contracts_data.get('PUT', [])
                        
                        # Refresh the display
                        self.root.after(0, lambda c=call_data, s=symbol: self._update_tree_data(
                            widgets['call_tree'], c, s, 'CALL'))
                        self.root.after(0, lambda p=put_data, s=symbol: self._update_tree_data(
                            widgets['put_tree'], p, s, 'PUT'))
                        
                        logger.info(f"✅ Successfully updated {symbol} prices for active pages")
                    
                except Exception as e:
                    logger.exception(f"Error in update thread for {symbol}:")
            
            # Start update in background thread
            threading.Thread(target=update_in_thread, daemon=True).start()
            
        except Exception as e:
            logger.exception(f"Error updating {symbol} watchlist:")
            traceback.print_exc()
    
    def _check_price_out_of_range(self, symbol: str, current_price: float) -> bool:
        """Check if current price is outside the range of displayed contracts
        
        Args:
            symbol: Symbol to check
            current_price: Current underlying price
            
        Returns:
            True if price is out of range (need refetch), False otherwise
        """
        try:
            if symbol not in self.watchlist_contracts:
                return False
            
            contracts_data = self.watchlist_contracts[symbol]
            
            # Get strikes from both CALL and PUT
            call_contracts = contracts_data.get('CALL', [])
            put_contracts = contracts_data.get('PUT', [])
            
            all_strikes = []
            
            # Collect all strikes
            for contract in call_contracts:
                strike = contract.get('strike')
                if strike:
                    all_strikes.append(strike)
            
            for contract in put_contracts:
                strike = contract.get('strike')
                if strike:
                    all_strikes.append(strike)
            
            if not all_strikes:
                logger.warning(f"⚠️ No strikes found for {symbol}")
                return True  # No contracts = need refetch
            
            # Get min and max strikes
            min_strike = min(all_strikes)
            max_strike = max(all_strikes)
            
            logger.debug(f"📊 {symbol} - Price: ${current_price:.2f}, Strike range: ${min_strike:.2f} - ${max_strike:.2f}")
            
            # Check if price is outside range
            # For CALL: we display strikes ABOVE the price
            # For PUT: we display strikes BELOW the price
            # So we want price to be near the middle of the range
            
            # If price is below minimum strike OR above maximum strike, refetch
            if current_price < min_strike or current_price > max_strike:
                logger.warning(f"🚨 {symbol} price ${current_price:.2f} is OUT OF RANGE [{min_strike:.2f} - {max_strike:.2f}]")
                return True
            
            # Also check if price is too close to edges (within 10% of range)
            strike_range = max_strike - min_strike
            buffer = strike_range * 0.1  # 10% buffer
            
            if current_price < (min_strike + buffer):
                logger.warning(f"📉 {symbol} price ${current_price:.2f} too close to lower edge - refetch recommended")
                return True
            
            if current_price > (max_strike - buffer):
                logger.warning(f"📈 {symbol} price ${current_price:.2f} too close to upper edge - refetch recommended")
                return True
            
            logger.debug(f"✅ {symbol} price ${current_price:.2f} is within safe range")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking price range for {symbol}: {e}")
            return False  # On error, don't force refetch
    
    def _update_tree_data(self, tree, options_data, symbol, option_type):
        """Update tree widget with options data"""
        try:
            logger.info(f"📝 Updating {symbol} {option_type} tree with {len(options_data) if options_data else 0} options")
            
            # Clear existing items
            for item in tree.get_children():
                tree.delete(item)
            
            # Add new data
            if options_data and len(options_data) > 0:
                valid_count = 0
                zero_count = 0
                
                for opt in options_data:
                    strike = opt.get('strike', 0)
                    bid = opt.get('bid', 0.0)
                    ask = opt.get('ask', 0.0)
                    
                    # Insert into tree
                    tree.insert('', 'end', text=f"{strike}",
                               values=(f"${bid:.2f}", f"${ask:.2f}"))
                    
                    if bid > 0 or ask > 0:
                        valid_count += 1
                    else:
                        zero_count += 1
                
                logger.info(f"✅ Added {len(options_data)} options to tree - {valid_count} valid, {zero_count} zero prices")
                
                if zero_count > 0:
                    logger.warning(f"⚠️ {zero_count} contracts displayed with zero prices")
            else:
                logger.warning("⚠️ No options data to display - tree will remain empty")
                # Add a placeholder message
                tree.insert('', 'end', text="جاري التحميل...",
                           values=("-", "-"))
                
        except Exception as e:
            logger.error(f"Error updating tree: {e}")
            import traceback
            traceback.print_exc()
    
    def show_telegram_settings(self):
        """Show telegram notification settings"""
        win = tk.Toplevel(self.root)
        win.title("إعدادات إشعارات التيليجرام")
        win.geometry("750x800")
        win.configure(bg=self.colors['bg_main'])
        win.transient(self.root)
        
        # Title
        title_frame = tk.Frame(win, bg=self.colors['bg_card'])
        title_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(title_frame, text="📱 إعدادات الإشعارات",
                bg=self.colors['bg_card'], fg=self.colors['accent_purple'],
                font=('Arial', 14, 'bold')).pack(pady=10)
        
        tk.Label(title_frame, text="اختر ما تريد إرساله: نص فقط، صورة فقط، أو الاثنين معاً",
                bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                font=('Arial', 9)).pack(pady=5)
        
        # Scrollable frame for notifications
        canvas = tk.Canvas(win, bg=self.colors['bg_main'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors['bg_main'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=10)
        scrollbar.pack(side="right", fill="y")
        
        # Notification types with icons and descriptions
        notifications = [
            ('signal_received', '📡 استقبال الإشارة', 'عند استقبال إشارة CALL أو PUT'),
            ('contract_found', '✅ العثور على العقد', 'عند العثور على عقد مناسب في النطاق'),
            ('position_opened', '🚀 فتح الصفقة', 'عند فتح صفقة جديدة'),
            ('new_high', '🎉 أعلى سعر جديد', 'عند وصول السعر لقمة جديدة'),
            ('price_update', '🔄 تحديث السعر', 'تحديثات الأسعار المستمرة'),
            ('stop_loss_hit', '🛑 تفعيل وقف الخسارة', 'عند الوصول لوقف الخسارة'),
            ('profit_target_hit', '🎯 تحقيق الهدف', 'عند الوصول للهدف المحدد'),
            ('position_closed', '🔒 إغلاق الصفقة', 'عند إغلاق الصفقة'),
            ('daily_summary', '📊 الملخص اليومي', 'ملخص صفقات اليوم'),
        ]
        
        # Store checkbox variables
        checkbox_vars = {}
        
        for notif_type, title, description in notifications:
            settings = config.TELEGRAM_NOTIFICATIONS.get(notif_type, {})
            
            frame = tk.LabelFrame(scrollable_frame, text=title,
                                 bg=self.colors['bg_card'],
                                 fg=self.colors['accent_blue'],
                                 font=('Arial', 10, 'bold'),
                                 borderwidth=2, relief='groove')
            frame.pack(fill='x', padx=10, pady=8)
            
            # Description
            tk.Label(frame, text=description,
                    bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                    font=('Arial', 9, 'italic')).pack(anchor='w', padx=15, pady=(10, 5))
            
            inner = tk.Frame(frame, bg=self.colors['bg_card'])
            inner.pack(fill='x', padx=15, pady=10)
            
            # Enabled checkbox
            enabled_var = tk.BooleanVar(value=settings.get('enabled', True))
            tk.Checkbutton(inner, text="✓ تفعيل",
                          variable=enabled_var,
                          bg=self.colors['bg_card'], fg=self.colors['accent_green'],
                          selectcolor=self.colors['bg_card_light'],
                          font=('Arial', 9, 'bold')).pack(side='left', padx=10)
            
            # Image checkbox
            image_var = tk.BooleanVar(value=settings.get('image', True))
            tk.Checkbutton(inner, text="🖼️ صورة",
                          variable=image_var,
                          bg=self.colors['bg_card'], fg=self.colors['accent_blue'],
                          selectcolor=self.colors['bg_card_light'],
                          font=('Arial', 9)).pack(side='left', padx=10)
            
            # Text checkbox
            text_var = tk.BooleanVar(value=settings.get('text', True))
            tk.Checkbutton(inner, text="📝 نص",
                          variable=text_var,
                          bg=self.colors['bg_card'], fg=self.colors['accent_yellow'],
                          selectcolor=self.colors['bg_card_light'],
                          font=('Arial', 9)).pack(side='left', padx=10)
            
            checkbox_vars[notif_type] = {
                'enabled': enabled_var,
                'image': image_var,
                'text': text_var
            }
        
        # Save button
        btn_frame = tk.Frame(win, bg=self.colors['bg_main'])
        btn_frame.pack(pady=15)
        
        def save_settings():
            try:
                for notif_type, vars_dict in checkbox_vars.items():
                    config.TELEGRAM_NOTIFICATIONS[notif_type]['enabled'] = vars_dict['enabled'].get()
                    config.TELEGRAM_NOTIFICATIONS[notif_type]['image'] = vars_dict['image'].get()
                    config.TELEGRAM_NOTIFICATIONS[notif_type]['text'] = vars_dict['text'].get()
                
                self.show_auto_close_message("نجح", "تم حفظ إعدادات الإشعارات بنجاح!", 'info', 3, parent=win)
                logger.info("Updated telegram notification settings")
            except Exception as e:
                logger.error(f"Error saving telegram settings: {e}")
                messagebox.showerror("خطأ", f"فشل حفظ الإعدادات: {str(e)}", parent=win)
        
        ModernButton(btn_frame, text="💾 حفظ الإعدادات",
                    command=save_settings,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=40, pady=10,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="✗ إغلاق",
                    command=win.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=40, pady=10,
                    cursor='hand2').pack(side='left', padx=5)
    
    def edit_tracking_messages(self):
        """Edit tracking message templates"""
        win = tk.Toplevel(self.root)
        win.title("رسائل التتبع التلقائي")
        win.geometry("900x750")
        win.configure(bg=self.colors['bg_main'])
        win.transient(self.root)
        
        # Title
        title_frame = tk.Frame(win, bg=self.colors['bg_card'])
        title_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(title_frame, text="📊 رسائل التتبع التلقائي",
                bg=self.colors['bg_card'], fg=self.colors['accent_green'],
                font=('Arial', 14, 'bold')).pack(pady=10)
        
        tk.Label(title_frame, text="يمكنك التعديل على النصوص. المتغيرات: {strike}, {entry_price}, {current_price}, {profit_usd}, {profit_sar}, {type}, {date}",
                bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                font=('Arial', 9)).pack(pady=5)
        
        # Get messages from database
        messages = self.db.get_all_tracking_messages()
        
        # Notebook for message types
        notebook = ttk.Notebook(win)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        message_widgets = {}
        
        # Message types with titles
        message_types = {
            'entry': ('🚀 رسالة دخول الصفقة', 'تُرسل فور اختيار العقد والدخول في الصفقة'),
            'update': ('🔔 رسالة تحديث الأرباح', 'تُرسل عند كل زيادة في سعر BID'),
            'target': ('🎯 رسالة تحقيق الهدف', 'تُرسل عند الوصول للهدف المحدد (مثلاً +$100)')
        }
        
        for msg_type, (title, description) in message_types.items():
            # Find message data
            msg_data = next((m for m in messages if m['message_type'] == msg_type), None)
            
            # Create tab
            tab = tk.Frame(notebook, bg=self.colors['bg_card'])
            notebook.add(tab, text=title)
            
            # Description
            tk.Label(tab, text=description,
                    bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                    font=('Arial', 9, 'italic')).pack(anchor='w', padx=15, pady=10)
            
            # Text area
            text_label = tk.Label(tab, text="النص:",
                                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                                font=('Arial', 10, 'bold'))
            text_label.pack(anchor='w', padx=15, pady=(10, 5))
            
            text_frame = tk.Frame(tab, bg=self.colors['bg_card'])
            text_frame.pack(fill='both', expand=True, padx=15, pady=5)
            
            text_widget = scrolledtext.ScrolledText(text_frame, width=80, height=15,
                                                   bg=self.colors['bg_card_light'],
                                                   fg=self.colors['text_white'],
                                                   font=('Arial', 9),
                                                   wrap=tk.WORD)
            text_widget.pack(fill='both', expand=True)
            
            if msg_data:
                text_widget.insert('1.0', msg_data['message_text'])
            
            # Image path
            img_label = tk.Label(tab, text="مسار الصورة (اختياري):",
                               bg=self.colors['bg_card'], fg=self.colors['text_white'],
                               font=('Arial', 10, 'bold'))
            img_label.pack(anchor='w', padx=15, pady=(15, 5))
            
            img_frame = tk.Frame(tab, bg=self.colors['bg_card'])
            img_frame.pack(fill='x', padx=15, pady=5)
            
            img_entry = tk.Entry(img_frame, width=60,
                               bg=self.colors['bg_card_light'],
                               fg=self.colors['text_white'],
                               font=('Arial', 9), insertbackground='white')
            img_entry.pack(side='left', fill='x', expand=True, padx=(0, 10))
            
            if msg_data and msg_data['image_path']:
                img_entry.insert(0, msg_data['image_path'])
            
            def browse_image(entry=img_entry):
                from tkinter import filedialog
                filename = filedialog.askopenfilename(
                    title="اختر صورة",
                    filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("All Files", "*.*")]
                )
                if filename:
                    entry.delete(0, tk.END)
                    entry.insert(0, filename)
            
            ModernButton(img_frame, text="📁 استعراض",
                        command=browse_image,
                        bg=self.colors['accent_blue'], fg='black',
                        font=('Arial', 9, 'bold'),
                        relief='raised', bd=2, padx=15, pady=5,
                        cursor='hand2').pack(side='left')
            
            message_widgets[msg_type] = {
                'text': text_widget,
                'image': img_entry
            }
        
        # Save button
        btn_frame = tk.Frame(win, bg=self.colors['bg_main'])
        btn_frame.pack(pady=15)
        
        def save_tracking_messages():
            try:
                for msg_type, widgets in message_widgets.items():
                    text = widgets['text'].get('1.0', tk.END).strip()
                    image_path = widgets['image'].get().strip() or None
                    
                    self.db.update_tracking_message(msg_type, text, image_path)
                
                self.show_auto_close_message("نجح", "تم حفظ رسائل التتبع بنجاح!", 'info', 3, parent=win)
                logger.info("Updated tracking messages")
            except Exception as e:
                logger.error(f"Error saving tracking messages: {e}")
                messagebox.showerror("خطأ", f"فشل حفظ الرسائل: {str(e)}", parent=win)
        
        ModernButton(btn_frame, text="💾 حفظ الرسائل",
                    command=save_tracking_messages,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=40, pady=10,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="✗ إغلاق",
                    command=win.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=40, pady=10,
                    cursor='hand2').pack(side='left', padx=5)
        
    def show_tradingview_commands(self):
        """Show TradingView commands"""
        win = tk.Toplevel(self.root)
        win.title("أوامر تريدنج فيو")
        win.geometry("650x650")
        win.configure(bg=self.colors['bg_main'])
        win.transient(self.root)
        
        # Center window
        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (325)
        y = (win.winfo_screenheight() // 2) - (325)
        win.geometry(f"+{x}+{y}")
        
        # Title
        title_frame = tk.Frame(win, bg=self.colors['bg_card'], bd=2, relief='raised')
        title_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(title_frame, text="📝 أوامر TradingView Alert",
                bg=self.colors['bg_card'], fg=self.colors['accent_yellow'],
                font=('Arial', 14, 'bold')).pack(pady=10)
        
        tk.Label(title_frame, text="انسخ الأمر المناسب والصقه في TradingView Alert Message",
                bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                font=('Arial', 9)).pack(pady=(0, 10))
        
        # Scrollable frame for commands
        canvas = tk.Canvas(win, bg=self.colors['bg_main'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors['bg_main'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Function to copy command
        def copy_command(command):
            self.root.clipboard_clear()
            self.root.clipboard_append(command)
            self.show_auto_close_message("✅ تم النسخ", 
                              f"تم نسخ الأمر!\n\n{command}\n\n"
                              "اذهب إلى TradingView واختر لصق (Ctrl+V)", 'info', 3)
        
        # Generate commands for all supported symbols
        for symbol in config.SUPPORTED_SYMBOLS:
            symbol_frame = tk.LabelFrame(scrollable_frame, 
                                        text=f"─── {symbol} ───",
                                        bg=self.colors['bg_card'],
                                        fg=self.colors['accent_blue'],
                                        font=('Arial', 11, 'bold'),
                                        bd=2, relief='groove')
            symbol_frame.pack(fill='x', padx=15, pady=8)
            
            # CALL command
            call_frame = tk.Frame(symbol_frame, bg=self.colors['bg_card'])
            call_frame.pack(fill='x', padx=10, pady=8)
            
            tk.Label(call_frame, text="📈 CALL:",
                    bg=self.colors['bg_card'], fg=self.colors['accent_green'],
                    font=('Arial', 10, 'bold')).pack(side='left', padx=5)
            
            call_command = f'{{"type": "CALL", "symbol": "{symbol}"}}'
            
            tk.Label(call_frame, text=call_command,
                    bg=self.colors['bg_card_light'], fg=self.colors['text_white'],
                    font=('Consolas', 9), relief='sunken', bd=1,
                    padx=8, pady=4).pack(side='left', padx=5, fill='x', expand=True)
            
            ModernButton(call_frame, text="📋 نسخ",
                        command=lambda cmd=call_command: copy_command(cmd),
                        bg=self.colors['accent_green'], fg='black',
                        font=('Arial', 8, 'bold'),
                        relief='raised', bd=2, padx=10, pady=4,
                        cursor='hand2').pack(side='right', padx=5)
            
            # PUT command
            put_frame = tk.Frame(symbol_frame, bg=self.colors['bg_card'])
            put_frame.pack(fill='x', padx=10, pady=(0, 8))
            
            tk.Label(put_frame, text="📉 PUT:",
                    bg=self.colors['bg_card'], fg=self.colors['accent_red'],
                    font=('Arial', 10, 'bold')).pack(side='left', padx=5)
            
            put_command = f'{{"type": "PUT", "symbol": "{symbol}"}}'
            
            tk.Label(put_frame, text=put_command,
                    bg=self.colors['bg_card_light'], fg=self.colors['text_white'],
                    font=('Consolas', 9), relief='sunken', bd=1,
                    padx=8, pady=4).pack(side='left', padx=5, fill='x', expand=True)
            
            ModernButton(put_frame, text="📋 نسخ",
                        command=lambda cmd=put_command: copy_command(cmd),
                        bg=self.colors['accent_red'], fg='white',
                        font=('Arial', 8, 'bold'),
                        relief='raised', bd=2, padx=10, pady=4,
                        cursor='hand2').pack(side='right', padx=5)
        
        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=5)
        scrollbar.pack(side="right", fill="y", pady=5)
        
        # Note
        note_frame = tk.Frame(win, bg=self.colors['bg_card'], bd=2, relief='raised')
        note_frame.pack(fill='x', padx=10, pady=(0, 10))
        
        tk.Label(note_frame, text="💡 اضغط على زر 'نسخ' ثم اذهب إلى TradingView والصق الأمر (Ctrl+V)",
                bg=self.colors['bg_card'], fg=self.colors['accent_yellow'],
                font=('Arial', 9)).pack(pady=8)
        
        # Close button
        btn_frame = tk.Frame(win, bg=self.colors['bg_main'])
        btn_frame.pack(pady=5)
        
        ModernButton(btn_frame, text="✓ إغلاق",
                    command=win.destroy,
                    bg=self.colors['accent_purple'], fg='white',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=40, pady=8,
                    cursor='hand2').pack()
    
    def update_webhook_url_display(self):
        """Update webhook URL display from webhook server"""
        try:
            import webhook_server
            url = webhook_server.get_webhook_url()
            
            if url and url != "http://localhost:5000/webhook":
                self.ngrok_label.config(
                    text=url,
                    fg=self.colors['accent_green']
                )
                logger.info(f"✅ Webhook URL updated: {url}")
            else:
                self.ngrok_label.config(
                    text="http://localhost:5000/webhook (محلي فقط)",
                    fg=self.colors['accent_yellow']
                )
        except Exception as e:
            logger.error(f"Error updating webhook URL: {e}")
            self.ngrok_label.config(
                text="❌ خطأ في الحصول على الرابط",
                fg=self.colors['accent_red']
            )
    
    def copy_webhook_url(self):
        """Copy webhook URL to clipboard"""
        try:
            import webhook_server
            url = webhook_server.get_webhook_url()
            
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            
            self.show_auto_close_message("نجح", 
                              f"تم نسخ الرابط إلى الحافظة!\n\n{url}\n\nالصق في TradingView الآن", 'info', 3)
            logger.info(f"✅ Copied webhook URL: {url}")
        except Exception as e:
            logger.error(f"Error copying webhook URL: {e}")
            messagebox.showerror("خطأ", f"فشل نسخ الرابط: {str(e)}")
    
    def show_ngrok_link(self):
        """Show ngrok setup instructions"""
        try:
            import webhook_server
            url = webhook_server.get_webhook_url()
            
            self.show_auto_close_message("رابط Webhook",
                               f"الرابط الحالي:\n\n{url}\n\n"
                               "✅ تم نسخه تلقائياً عند التشغيل\n"
                               "استخدمه في TradingView Alert", 'info', 3)
        except:
            self.show_auto_close_message("رابط Ngrok",
                               "1. قم بتشغيل: ngrok http 5000\n"
                               "2. انسخ الرابط الذي يبدأ بـ https://\n"
                               "3. أضف /webhook في النهاية\n"
                               "4. استخدمه في TradingView", 'info', 3)
    
    def copy_to_clipboard(self, text):
        """Copy text to clipboard"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.show_auto_close_message("نجح", "تم النسخ إلى الحافظة!", 'info', 3)
    
    def close_watchlist_tab(self, symbol):
        """Close watchlist tab for a symbol"""
        try:
            # Confirm closure
            result = messagebox.askyesno("تأكيد",
                                        f"هل تريد إغلاق متابعة {symbol}؟")
            if not result:
                return
            
            # Find and remove tab
            for i in range(self.watchlist_notebook.index('end')):
                tab_text = self.watchlist_notebook.tab(i, 'text').strip()
                if tab_text == symbol:
                    self.watchlist_notebook.forget(i)
                    break
            
            # Remove from widgets dict
            if symbol in self.watchlist_widgets:
                del self.watchlist_widgets[symbol]
            
            # Disconnect IBKR connection if not a default symbol
            default_symbols = getattr(config, 'DEFAULT_WATCHLIST_SYMBOLS', config.SUPPORTED_SYMBOLS)
            if symbol not in default_symbols and self.trading_system:
                if symbol in self.trading_system.ibkr_connections:
                    conn = self.trading_system.ibkr_connections[symbol]
                    conn.disconnect()
                    del self.trading_system.ibkr_connections[symbol]
                    logger.info(f"Disconnected IBKR connection for {symbol}")
            
            logger.info(f"Closed watchlist tab for {symbol}")
            
        except Exception as e:
            logger.error(f"Error closing tab for {symbol}: {e}")
            messagebox.showerror("خطأ", f"فشل إغلاق {symbol}")
    
    def change_expiry_date(self, symbol):
        """Change expiry date for watchlist using calendar picker (if available) or manual input"""
        
        # Use calendar picker if tkcalendar is installed
        if CALENDAR_AVAILABLE:
            self._change_expiry_date_with_calendar(symbol)
        else:
            self._change_expiry_date_manual(symbol)
    
    def _change_expiry_date_with_calendar(self, symbol):
        """Change expiry date using visual calendar picker"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"تغيير تاريخ العقود - {symbol}")
        dialog.geometry("450x580")
        dialog.configure(bg=self.colors['bg_main'])
        dialog.transient(self.root)
        
        # Title
        title_frame = tk.Frame(dialog, bg=self.colors['bg_card'])
        title_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(title_frame, text=f"📅 تحديد تاريخ انتهاء العقود - {symbol}",
                bg=self.colors['bg_card'], fg=self.colors['accent_blue'],
                font=('Arial', 12, 'bold')).pack(pady=10)
        
        # Current expiry display
        current_frame = tk.Frame(dialog, bg=self.colors['bg_main'])
        current_frame.pack(pady=10)
        
        current_expiry = self.selected_expiry_dates.get(symbol, None)
        current_text = "0DTE (تاريخ اليوم)" if not current_expiry else current_expiry
        
        tk.Label(current_frame, text="التاريخ الحالي:",
                bg=self.colors['bg_main'], fg=self.colors['text_gray'],
                font=('Arial', 10, 'bold')).pack(side='left', padx=5)
        tk.Label(current_frame, text=current_text,
                bg=self.colors['bg_main'], fg=self.colors['accent_green'],
                font=('Arial', 10, 'bold')).pack(side='left', padx=5)
        
        # Selection frame
        sel_frame = tk.Frame(dialog, bg=self.colors['bg_card'], relief='ridge', bd=2)
        sel_frame.pack(fill='both', expand=True, padx=20, pady=15)
        
        # Radio button variable
        mode_var = tk.StringVar(value="0DTE")
        
        # Option 1: Use 0DTE (Today)
        today_frame = tk.Frame(sel_frame, bg=self.colors['bg_card'])
        today_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Radiobutton(today_frame, text="📍 استخدام 0DTE (تاريخ اليوم)",
                      variable=mode_var,
                      value="0DTE",
                      bg=self.colors['bg_card'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card_light'],
                      font=('Arial', 10, 'bold'),
                      activebackground=self.colors['bg_card'],
                      activeforeground=self.colors['accent_green']).pack(anchor='w')
        
        # Separator line
        tk.Frame(sel_frame, bg=self.colors['accent_blue'], height=2).pack(fill='x', padx=10, pady=5)
        
        # Option 2: Custom date with calendar
        custom_frame = tk.Frame(sel_frame, bg=self.colors['bg_card'])
        custom_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        tk.Radiobutton(custom_frame, text="📆 تاريخ مخصص:",
                      variable=mode_var,
                      value="CUSTOM",
                      bg=self.colors['bg_card'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card_light'],
                      font=('Arial', 10, 'bold'),
                      activebackground=self.colors['bg_card'],
                      activeforeground=self.colors['accent_green']).pack(anchor='w', pady=(0, 10))
        
        # Calendar widget
        calendar_container = tk.Frame(custom_frame, bg=self.colors['bg_card'])
        calendar_container.pack(pady=5)
        
        # Get initial date (today or current custom date)
        if current_expiry and current_expiry != "0DTE (تاريخ اليوم)":
            try:
                # Parse YYYYMMDD format
                year = int(current_expiry[:4])
                month = int(current_expiry[4:6])
                day = int(current_expiry[6:8])
                initial_date = datetime(year, month, day)
            except:
                initial_date = datetime.now()
        else:
            initial_date = datetime.now()
        
        # Create Calendar widget
        cal = Calendar(calendar_container,
                      selectmode='day',
                      year=initial_date.year,
                      month=initial_date.month,
                      day=initial_date.day,
                      background=self.colors['bg_card_light'],
                      foreground=self.colors['text_white'],
                      bordercolor=self.colors['accent_blue'],
                      headersbackground=self.colors['accent_blue'],
                      headersforeground='white',
                      selectbackground=self.colors['accent_green'],
                      selectforeground='black',
                      weekendbackground=self.colors['bg_card'],
                      weekendforeground=self.colors['accent_yellow'],
                      othermonthbackground=self.colors['bg_main'],
                      othermonthwebackground=self.colors['bg_main'],
                      othermonthforeground=self.colors['text_gray'],
                      font=('Arial', 9),
                      date_pattern='yyyy-mm-dd')
        cal.pack(padx=5, pady=5)
        
        # Selected date display
        selected_date_frame = tk.Frame(custom_frame, bg=self.colors['bg_card'])
        selected_date_frame.pack(pady=10)
        
        tk.Label(selected_date_frame, text="التاريخ المحدد:",
                bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                font=('Arial', 9)).pack(side='left', padx=5)
        
        selected_date_label = tk.Label(selected_date_frame, text=initial_date.strftime('%d/%m/%Y'),
                                       bg=self.colors['bg_card'], fg=self.colors['accent_yellow'],
                                       font=('Arial', 10, 'bold'))
        selected_date_label.pack(side='left')
        
        # Update selected date label when calendar selection changes
        def on_date_select(event=None):
            selected = cal.get_date()
            # Convert from string to datetime
            date_obj = datetime.strptime(selected, '%Y-%m-%d')
            selected_date_label.config(text=date_obj.strftime('%d/%m/%Y'))
            # Auto-select custom mode when calendar is clicked
            mode_var.set("CUSTOM")
        
        cal.bind("<<CalendarSelected>>", on_date_select)
        
        # Info label
        info_frame = tk.Frame(dialog, bg=self.colors['bg_main'])
        info_frame.pack(pady=5)
        
        tk.Label(info_frame, text="💡 اختر التاريخ من التقويم أو استخدم 0DTE",
                bg=self.colors['bg_main'], fg=self.colors['accent_yellow'],
                font=('Arial', 9)).pack()
        
        def apply_expiry_date():
            selected_mode = mode_var.get()
            
            if selected_mode == "0DTE":
                # Use 0DTE
                self.selected_expiry_dates[symbol] = None  # None means use current date
                logger.info(f"Set {symbol} to use 0DTE")
                
                # Update label
                if symbol in self.watchlist_widgets:
                    self.watchlist_widgets[symbol]['expiry_label'].config(text="0DTE (تاريخ اليوم)")
                
                self.show_auto_close_message("تم التحديث", f"تم تعيين {symbol} لاستخدام 0DTE (تاريخ اليوم)", 'info', 3, parent=dialog)
            
            else:  # CUSTOM
                # Get selected date from calendar
                selected = cal.get_date()
                date_obj = datetime.strptime(selected, '%Y-%m-%d')
                
                # Convert to YYYYMMDD format
                expiry_yyyymmdd = date_obj.strftime('%Y%m%d')
                
                # Save
                self.selected_expiry_dates[symbol] = expiry_yyyymmdd
                logger.info(f"Set {symbol} expiry to {expiry_yyyymmdd} ({date_obj.strftime('%d/%m/%Y')})")
                
                # Format for display: DD/MM/YYYY
                formatted = date_obj.strftime('%d/%m/%Y')
                
                # Update label
                if symbol in self.watchlist_widgets:
                    self.watchlist_widgets[symbol]['expiry_label'].config(text=formatted)
                
                self.show_auto_close_message("تم التحديث", f"تم تعيين تاريخ العقود لـ {symbol}:\n{formatted}", 'info', 3, parent=dialog)
            
            # Refresh watchlist with new date
            self.root.after(100, lambda: self.update_symbol_watchlist(symbol))
            
            dialog.destroy()
        
        # Buttons
        btn_frame = tk.Frame(dialog, bg=self.colors['bg_main'])
        btn_frame.pack(pady=15)
        
        ModernButton(btn_frame, text="✓ تطبيق",
                    command=apply_expiry_date,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=30, pady=10,
                    cursor='hand2').pack(side='left', padx=10)
        
        ModernButton(btn_frame, text="✗ إلغاء",
                    command=dialog.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=30, pady=10,
                    cursor='hand2').pack(side='left', padx=10)
    
    def _change_expiry_date_manual(self, symbol):
        """Change expiry date using manual text input (fallback when tkcalendar is not installed)"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"تغيير تاريخ العقود - {symbol}")
        dialog.geometry("450x400")
        dialog.configure(bg=self.colors['bg_main'])
        dialog.transient(self.root)
        
        # Title
        title_frame = tk.Frame(dialog, bg=self.colors['bg_card'])
        title_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(title_frame, text=f"📅 تحديد تاريخ انتهاء العقود - {symbol}",
                bg=self.colors['bg_card'], fg=self.colors['accent_blue'],
                font=('Arial', 12, 'bold')).pack(pady=10)
        
        # Warning about missing library
        warning_frame = tk.Frame(dialog, bg=self.colors['accent_yellow'], relief='ridge', bd=2)
        warning_frame.pack(fill='x', padx=15, pady=5)
        
        tk.Label(warning_frame, text="⚠️ للحصول على تقويم مرئي، قم بتثبيت: pip install tkcalendar",
                bg=self.colors['accent_yellow'], fg='black',
                font=('Arial', 8, 'bold')).pack(pady=5)
        
        # Current expiry display
        current_frame = tk.Frame(dialog, bg=self.colors['bg_main'])
        current_frame.pack(pady=10)
        
        current_expiry = self.selected_expiry_dates.get(symbol, None)
        current_text = "0DTE (تاريخ اليوم)" if not current_expiry else current_expiry
        
        tk.Label(current_frame, text="التاريخ الحالي:",
                bg=self.colors['bg_main'], fg=self.colors['text_gray'],
                font=('Arial', 10, 'bold')).pack(side='left', padx=5)
        tk.Label(current_frame, text=current_text,
                bg=self.colors['bg_main'], fg=self.colors['accent_green'],
                font=('Arial', 10, 'bold')).pack(side='left', padx=5)
        
        # Selection frame
        sel_frame = tk.Frame(dialog, bg=self.colors['bg_card'])
        sel_frame.pack(fill='x', padx=20, pady=15)
        
        date_var = tk.StringVar(value="0DTE")
        
        # Option 1: Use 0DTE (Today)
        tk.Radiobutton(sel_frame, text="📍 استخدام 0DTE (تاريخ اليوم)",
                      variable=date_var,
                      value="0DTE",
                      bg=self.colors['bg_card'], fg=self.colors['text_white'],
                      selectcolor=self.colors['bg_card_light'],
                      font=('Arial', 10, 'bold')).pack(anchor='w', pady=10)
        
        # Option 2: Custom date
        custom_frame = tk.Frame(sel_frame, bg=self.colors['bg_card'])
        custom_frame.pack(anchor='w', pady=10)
        
        tk.Label(custom_frame, text="📆 تاريخ مخصص:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=5, pady=5)
        
        # Date entry (YYYYMMDD format)
        date_entry = tk.Entry(custom_frame, width=15, font=('Arial', 11),
                             bg=self.colors['bg_card_light'],
                             fg=self.colors['text_white'],
                             insertbackground=self.colors['text_white'])
        date_entry.pack(padx=5, pady=5)
        date_entry.insert(0, "YYYYMMDD")
        date_entry.bind('<FocusIn>', lambda e: date_entry.delete(0, 'end') if date_entry.get() == "YYYYMMDD" else None)
        date_entry.bind('<KeyRelease>', lambda e: date_var.set(date_entry.get()))
        
        # Info label
        info_frame = tk.Frame(dialog, bg=self.colors['bg_main'])
        info_frame.pack(pady=10)
        
        tk.Label(info_frame, text="💡 أدخل التاريخ بصيغة YYYYMMDD",
                bg=self.colors['bg_main'], fg=self.colors['accent_yellow'],
                font=('Arial', 9)).pack()
        tk.Label(info_frame, text="مثال: 20260305 لتاريخ 5 مارس 2026",
                bg=self.colors['bg_main'], fg=self.colors['text_gray'],
                font=('Arial', 9)).pack()
        
        def apply_expiry_date():
            selected = date_var.get().strip()
            
            # Validate
            if selected == "0DTE":
                self.selected_expiry_dates[symbol] = None  # None means use current date
                logger.info(f"Set {symbol} to use 0DTE")
                
                # Update label
                if symbol in self.watchlist_widgets:
                    self.watchlist_widgets[symbol]['expiry_label'].config(text="0DTE (تاريخ اليوم)")
                
                self.show_auto_close_message("تم التحديث", f"تم تعيين {symbol} لاستخدام 0DTE (تاريخ اليوم)", 'info', 3, parent=dialog)
            
            elif len(selected) == 8 and selected.isdigit():
                # Valid date format
                self.selected_expiry_dates[symbol] = selected
                logger.info(f"Set {symbol} expiry to {selected}")
                
                # Format for display: DD/MM/YYYY
                formatted = f"{selected[6:8]}/{selected[4:6]}/{selected[0:4]}"
                
                # Update label
                if symbol in self.watchlist_widgets:
                    self.watchlist_widgets[symbol]['expiry_label'].config(text=formatted)
                
                self.show_auto_close_message("تم التحديث", f"تم تعيين تاريخ العقود لـ {symbol}:\n{formatted}", 'info', 3, parent=dialog)
            
            else:
                self.show_auto_close_message("خطأ", "صيغة التاريخ غير صحيحة!\nيجب أن يكون 8 أرقام بصيغة YYYYMMDD", 'error', 3, parent=dialog)
                return
            
            # Refresh watchlist with new date
            self.root.after(100, lambda: self.update_symbol_watchlist(symbol))
            
            dialog.destroy()
        
        # Buttons
        btn_frame = tk.Frame(dialog, bg=self.colors['bg_main'])
        btn_frame.pack(pady=20)
        
        ModernButton(btn_frame, text="✓ تطبيق",
                    command=apply_expiry_date,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=30, pady=10,
                    cursor='hand2').pack(side='left', padx=10)
        
        ModernButton(btn_frame, text="✗ إلغاء",
                    command=dialog.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=30, pady=10,
                    cursor='hand2').pack(side='left', padx=10)
    
    def load_telegram_channels(self):
        """Load telegram channels from database"""
        try:
            # Clear existing items
            for item in self.tg_tree.get_children():
                self.tg_tree.delete(item)
            
            # Load channels from database
            channels = self.db.get_all_telegram_channels()
            
            # Add default SPX channel if no channels exist
            if len(channels) == 0:
                logger.info("No channels found, adding default SPX channel")
                self.db.add_telegram_channel(
                    token=config.TELEGRAM_BOT_TOKEN,
                    chat_id=config.TELEGRAM_CHAT_ID,
                    channel_name="SPX SMART",
                    symbol="SPX",
                    channel_link="https://t.me/NDXSmartpro"
                )
                # Reload after adding default
                channels = self.db.get_all_telegram_channels()
                # Reload telegram manager channels
                self.telegram.reload_channels()
                logger.info("Default SPX channel added successfully")
            
            # Update channels that don't have a link (old channels)
            for channel in channels:
                if not channel.get('channel_link') or channel.get('channel_link') == 'None':
                    logger.info(f"Updating channel {channel['channel_name']} with default link")
                    self.db.update_telegram_channel(
                        channel['id'],
                        channel['token'],
                        channel['chat_id'],
                        channel['channel_name'],
                        channel['symbol'],
                        "https://t.me/NDXSmartpro"
                    )
            
            # Reload channels after update
            channels = self.db.get_all_telegram_channels()
            
            for channel in channels:
                # Mask token for display (show first 10 and last 5 chars)
                token = channel['token']
                if len(token) > 20:
                    masked_token = f"{token[:10]}...{token[-5:]}"
                else:
                    masked_token = token[:15] + "..."
                
                # Get channel link or empty string
                channel_link = channel.get('channel_link', '')
                
                self.tg_tree.insert('', 'end', values=(
                    masked_token,
                    channel['chat_id'],
                    channel['channel_name'],
                    channel['symbol'],
                    channel_link
                ), tags=(str(channel['id']),))
            
            logger.info(f"Loaded {len(channels)} telegram channels")
            
        except Exception as e:
            logger.error(f"Error loading telegram channels: {e}")
    
    def add_telegram_channel(self):
        """Add new telegram channel"""
        dialog = tk.Toplevel(self.root)
        dialog.title("إضافة قناة تيليجرام")
        dialog.geometry("500x550")
        dialog.configure(bg=self.colors['bg_main'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (250)
        y = (dialog.winfo_screenheight() // 2) - (275)
        dialog.geometry(f"+{x}+{y}")
        
        frame = tk.Frame(dialog, bg=self.colors['bg_card'], bd=2, relief='raised')
        frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        tk.Label(frame, text="📱 إضافة قناة تيليجرام جديدة",
                bg=self.colors['bg_card'], fg=self.colors['accent_purple'],
                font=('Arial', 13, 'bold')).pack(pady=(15, 20))
        
        # Helper function to add copy/paste support
        def add_copy_paste_support(entry_widget):
            """Add right-click copy/paste menu to entry widget"""
            def copy_text(event=None):
                try:
                    if entry_widget.selection_present():
                        text = entry_widget.selection_get()
                        entry_widget.clipboard_clear()
                        entry_widget.clipboard_append(text)
                except:
                    pass
            
            def paste_text(event=None):
                try:
                    text = entry_widget.clipboard_get()
                    if entry_widget.selection_present():
                        entry_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    entry_widget.insert(tk.INSERT, text)
                except:
                    pass
            
            def select_all(event=None):
                entry_widget.select_range(0, tk.END)
                return 'break'
            
            # Create right-click menu
            menu = tk.Menu(entry_widget, tearoff=0, bg=self.colors['bg_card'],
                          fg=self.colors['text_white'])
            menu.add_command(label="📋 نسخ (Copy)", command=copy_text)
            menu.add_command(label="📝 لصق (Paste)", command=paste_text)
            menu.add_separator()
            menu.add_command(label="✅ تحديد الكل (Select All)", command=select_all)
            
            def show_menu(event):
                menu.post(event.x_root, event.y_root)
            
            # Bind events
            entry_widget.bind('<Button-3>', show_menu)  # Right click
            entry_widget.bind('<Control-c>', copy_text)  # Ctrl+C
            entry_widget.bind('<Control-v>', paste_text)  # Ctrl+V
            entry_widget.bind('<Control-a>', select_all)  # Ctrl+A
        
        # Symbol selection
        tk.Label(frame, text="الشركة:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=20, pady=(5, 2))
        
        symbol_var = tk.StringVar()
        symbol_combo = ttk.Combobox(frame, textvariable=symbol_var,
                                   values=config.SUPPORTED_SYMBOLS,
                                   width=35, font=('Arial', 10),
                                   state='readonly')
        symbol_combo.pack(padx=20, pady=5, fill='x')
        if config.SUPPORTED_SYMBOLS:
            symbol_combo.current(0)
        
        # Channel name
        tk.Label(frame, text="اسم القناة:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=20, pady=(10, 2))
        
        name_entry = tk.Entry(frame, width=40, bg=self.colors['bg_card_light'],
                             fg=self.colors['text_white'], font=('Arial', 10),
                             insertbackground=self.colors['text_white'])
        name_entry.pack(padx=20, pady=5, fill='x')
        name_entry.insert(0, "SPX Smart Channel")
        add_copy_paste_support(name_entry)
        
        # Bot Token
        tk.Label(frame, text="Bot Token:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=20, pady=(10, 2))
        
        token_entry = tk.Entry(frame, width=40, bg=self.colors['bg_card_light'],
                              fg=self.colors['text_white'], font=('Arial', 9),
                              insertbackground=self.colors['text_white'])
        token_entry.pack(padx=20, pady=5, fill='x')
        token_entry.insert(0, config.TELEGRAM_BOT_TOKEN)
        add_copy_paste_support(token_entry)
        
        # Chat ID
        tk.Label(frame, text="Chat ID:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=20, pady=(10, 2))
        
        chat_entry = tk.Entry(frame, width=40, bg=self.colors['bg_card_light'],
                             fg=self.colors['text_white'], font=('Arial', 10),
                             insertbackground=self.colors['text_white'])
        chat_entry.pack(padx=20, pady=5, fill='x')
        chat_entry.insert(0, config.TELEGRAM_CHAT_ID)
        add_copy_paste_support(chat_entry)
        
        # Channel Link
        tk.Label(frame, text="رابط القناة:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=20, pady=(10, 2))
        
        link_entry = tk.Entry(frame, width=40, bg=self.colors['bg_card_light'],
                             fg=self.colors['text_white'], font=('Arial', 10),
                             insertbackground=self.colors['text_white'])
        link_entry.pack(padx=20, pady=5, fill='x')
        link_entry.insert(0, "https://t.me/NDXSmartpro")
        add_copy_paste_support(link_entry)
        
        def save_channel():
            symbol = symbol_var.get()
            name = name_entry.get().strip()
            token = token_entry.get().strip()
            chat_id = chat_entry.get().strip()
            channel_link = link_entry.get().strip()
            
            if not symbol or not name or not token or not chat_id:
                self.show_auto_close_message("تحذير", "الرجاء ملء جميع الحقول!", 'warning', 3, parent=dialog)
                return
            
            try:
                self.db.add_telegram_channel(token, chat_id, name, symbol, channel_link)
                self.load_telegram_channels()
                # Reload telegram manager channels
                self.telegram.reload_channels()
                self.show_auto_close_message("نجح", f"تمت إضافة قناة {symbol} بنجاح!", 'info', 3, parent=dialog)
                dialog.destroy()
            except Exception as e:
                logger.error(f"Error adding telegram channel: {e}")
                messagebox.showerror("خطأ", f"فشلت الإضافة: {str(e)}", parent=dialog)
        
        # Buttons
        btn_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        btn_frame.pack(pady=20)
        
        ModernButton(btn_frame, text="✓ حفظ",
                    command=save_channel,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=30, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="✗ إلغاء",
                    command=dialog.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=30, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
    
    def edit_telegram_channel(self):
        """Edit selected telegram channel"""
        selection = self.tg_tree.selection()
        if not selection:
            self.show_auto_close_message("تحذير", "الرجاء اختيار قناة للتعديل!", 'warning', 3)
            return
        
        item = self.tg_tree.item(selection[0])
        channel_id = int(item['tags'][0])
        values = item['values']
        
        # Get full channel data from database
        channels = self.db.get_all_telegram_channels()
        channel = next((ch for ch in channels if ch['id'] == channel_id), None)
        
        if not channel:
            messagebox.showerror("خطأ", "القناة غير موجودة!")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("تعديل قناة تيليجرام")
        dialog.geometry("500x550")
        dialog.configure(bg=self.colors['bg_main'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (250)
        y = (dialog.winfo_screenheight() // 2) - (275)
        dialog.geometry(f"+{x}+{y}")
        
        frame = tk.Frame(dialog, bg=self.colors['bg_card'], bd=2, relief='raised')
        frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        tk.Label(frame, text="✏️ تعديل قناة تيليجرام",
                bg=self.colors['bg_card'], fg=self.colors['accent_blue'],
                font=('Arial', 13, 'bold')).pack(pady=(15, 20))
        
        # Helper function to add copy/paste support
        def add_copy_paste_support(entry_widget):
            """Add right-click copy/paste menu to entry widget"""
            def copy_text(event=None):
                try:
                    if entry_widget.selection_present():
                        text = entry_widget.selection_get()
                        entry_widget.clipboard_clear()
                        entry_widget.clipboard_append(text)
                except:
                    pass
            
            def paste_text(event=None):
                try:
                    text = entry_widget.clipboard_get()
                    if entry_widget.selection_present():
                        entry_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    entry_widget.insert(tk.INSERT, text)
                except:
                    pass
            
            def select_all(event=None):
                entry_widget.select_range(0, tk.END)
                return 'break'
            
            # Create right-click menu
            menu = tk.Menu(entry_widget, tearoff=0, bg=self.colors['bg_card'],
                          fg=self.colors['text_white'])
            menu.add_command(label="📋 نسخ (Copy)", command=copy_text)
            menu.add_command(label="📝 لصق (Paste)", command=paste_text)
            menu.add_separator()
            menu.add_command(label="✅ تحديد الكل (Select All)", command=select_all)
            
            def show_menu(event):
                menu.post(event.x_root, event.y_root)
            
            # Bind events
            entry_widget.bind('<Button-3>', show_menu)  # Right click
            entry_widget.bind('<Control-c>', copy_text)  # Ctrl+C
            entry_widget.bind('<Control-v>', paste_text)  # Ctrl+V
            entry_widget.bind('<Control-a>', select_all)  # Ctrl+A
        
        # Symbol selection
        tk.Label(frame, text="الشركة:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=20, pady=(5, 2))
        
        symbol_var = tk.StringVar(value=channel['symbol'])
        symbol_combo = ttk.Combobox(frame, textvariable=symbol_var,
                                   values=config.SUPPORTED_SYMBOLS,
                                   width=35, font=('Arial', 10),
                                   state='readonly')
        symbol_combo.pack(padx=20, pady=5, fill='x')
        
        # Channel name
        tk.Label(frame, text="اسم القناة:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=20, pady=(10, 2))
        
        name_entry = tk.Entry(frame, width=40, bg=self.colors['bg_card_light'],
                             fg=self.colors['text_white'], font=('Arial', 10),
                             insertbackground=self.colors['text_white'])
        name_entry.pack(padx=20, pady=5, fill='x')
        name_entry.insert(0, channel['channel_name'])
        add_copy_paste_support(name_entry)
        
        # Bot Token
        tk.Label(frame, text="Bot Token:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=20, pady=(10, 2))
        
        token_entry = tk.Entry(frame, width=40, bg=self.colors['bg_card_light'],
                              fg=self.colors['text_white'], font=('Arial', 9),
                              insertbackground=self.colors['text_white'])
        token_entry.pack(padx=20, pady=5, fill='x')
        token_entry.insert(0, channel['token'])
        add_copy_paste_support(token_entry)
        
        # Chat ID
        tk.Label(frame, text="Chat ID:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=20, pady=(10, 2))
        
        chat_entry = tk.Entry(frame, width=40, bg=self.colors['bg_card_light'],
                             fg=self.colors['text_white'], font=('Arial', 10),
                             insertbackground=self.colors['text_white'])
        chat_entry.pack(padx=20, pady=5, fill='x')
        chat_entry.insert(0, channel['chat_id'])
        add_copy_paste_support(chat_entry)
        
        # Channel Link
        tk.Label(frame, text="رابط القناة:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=20, pady=(10, 2))
        
        link_entry = tk.Entry(frame, width=40, bg=self.colors['bg_card_light'],
                             fg=self.colors['text_white'], font=('Arial', 10),
                             insertbackground=self.colors['text_white'])
        link_entry.pack(padx=20, pady=5, fill='x')
        link_entry.insert(0, channel.get('channel_link', ''))
        add_copy_paste_support(link_entry)
        
        def update_channel():
            symbol = symbol_var.get()
            name = name_entry.get().strip()
            token = token_entry.get().strip()
            chat_id = chat_entry.get().strip()
            channel_link = link_entry.get().strip()
            
            if not symbol or not name or not token or not chat_id:
                self.show_auto_close_message("تحذير", "الرجاء ملء جميع الحقول!", 'warning', 3, parent=dialog)
                return
            
            try:
                self.db.update_telegram_channel(channel_id, token, chat_id, name, symbol, channel_link)
                self.load_telegram_channels()
                # Reload telegram manager channels
                self.telegram.reload_channels()
                self.show_auto_close_message("نجح", f"تم تحديث قناة {symbol} بنجاح!", 'info', 3, parent=dialog)
                dialog.destroy()
            except Exception as e:
                logger.error(f"Error updating telegram channel: {e}")
                messagebox.showerror("خطأ", f"فشل التحديث: {str(e)}", parent=dialog)
        
        # Buttons
        btn_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        btn_frame.pack(pady=20)
        
        ModernButton(btn_frame, text="✓ تحديث",
                    command=update_channel,
                    bg=self.colors['accent_blue'], fg='black',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=30, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="✗ إلغاء",
                    command=dialog.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=30, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
    
    def delete_telegram_channel(self):
        """Delete selected telegram channel"""
        selection = self.tg_tree.selection()
        if not selection:
            self.show_auto_close_message("تحذير", "الرجاء اختيار قناة للحذف!", 'warning', 3)
            return
        
        item = self.tg_tree.item(selection[0])
        channel_id = int(item['tags'][0])
        symbol = item['values'][3]
        
        result = messagebox.askyesno("تأكيد الحذف",
                                     f"هل أنت متأكد من حذف قناة {symbol}؟\n\nلن تتمكن من التراجع عن هذا الإجراء!")
        
        if result:
            try:
                self.db.delete_telegram_channel(channel_id)
                self.load_telegram_channels()
                # Reload telegram manager channels
                self.telegram.reload_channels()
                self.show_auto_close_message("نجح", f"تم حذف قناة {symbol} بنجاح!", 'info', 3)
                logger.info(f"Deleted telegram channel for {symbol}")
            except Exception as e:
                logger.error(f"Error deleting telegram channel: {e}")
                messagebox.showerror("خطأ", f"فشل الحذف: {str(e)}")
    
    def reload_telegram_channels(self):
        """Reload telegram channels from database"""
        try:
            print(f"\n{'='*60}")
            print(f"🔄 إعادة تحميل قنوات التيليجرام...")
            print(f"{'='*60}\n")
            
            # Reload in telegram manager
            self.telegram.reload_channels()
            
            # Reload in GUI table
            self.load_telegram_channels()
            
            # Show loaded channels summary
            channels_count = sum(len(v) for v in self.telegram.channels.values())
            symbols = list(self.telegram.channels.keys())
            
            msg = f"✅ تم إعادة تحميل القنوات\n\n"
            msg += f"عدد القنوات: {channels_count}\n"
            msg += f"الرموز: {', '.join(symbols)}"
            
            self.show_auto_close_message("نجح", msg, 'info', 3)
            logger.info(f"Reloaded {channels_count} telegram channels")
            
        except Exception as e:
            logger.error(f"Error reloading telegram channels: {e}")
            messagebox.showerror("خطأ", f"فشل إعادة التحميل: {str(e)}")
    
    def test_telegram_connection(self):
        """Test telegram connection by sending test message"""
        try:
            print(f"\n{'='*60}")
            print(f"🧪 اختبار اتصال التيليجرام...")
            print(f"{'='*60}\n")
            
            # Test connection
            success = self.telegram.test_connection()
            
            if success:
                self.show_auto_close_message("نجح", "✅ اختبار الاتصال ناجح!\n\nتم إرسال رسالة اختبار لجميع القنوات.", 'info', 3)
            else:
                self.show_auto_close_message("فشل", "❌ فشل اختبار الاتصال!\n\nتحقق من:\n- التوكن\n- Chat ID\n- اتصال الإنترنت\n\nراجع Console للتفاصيل.", 'error', 3)
            
        except Exception as e:
            logger.error(f"Error testing telegram connection: {e}")
            messagebox.showerror("خطأ", f"فشل الاختبار: {str(e)}")
    
    def manage_telegram_alerts(self):
        """Manage telegram alerts/reminders"""
        win = tk.Toplevel(self.root)
        win.title("إدارة التنبيهات")
        win.geometry("900x700")
        win.configure(bg=self.colors['bg_main'])
        win.transient(self.root)
        
        # Title
        title_frame = tk.Frame(win, bg=self.colors['bg_card'])
        title_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(title_frame, text="⏰ إدارة التنبيهات والرسائل المجدولة",
                bg=self.colors['bg_card'], fg=self.colors['accent_green'],
                font=('Arial', 14, 'bold')).pack(pady=10)
        
        tk.Label(title_frame, text="📅 جدولة رسائل تليجرام للإرسال في أوقات محددة",
                bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                font=('Arial', 9)).pack(pady=3)
        
        # Alerts table
        table_frame = tk.Frame(win, bg=self.colors['bg_main'])
        table_frame.pack(fill='both', expand=True, padx=15, pady=10)
        
        columns = ('time', 'message', 'repeat', 'status', 'last_sent')
        alerts_tree = ttk.Treeview(table_frame, columns=columns, height=15, show='headings')
        
        alerts_tree.heading('time', text='الوقت')
        alerts_tree.heading('message', text='الرسالة')
        alerts_tree.heading('repeat', text='التكرار')
        alerts_tree.heading('status', text='الحالة')
        alerts_tree.heading('last_sent', text='آخر إرسال')
        
        alerts_tree.column('time', width=100)
        alerts_tree.column('message', width=350)
        alerts_tree.column('repeat', width=100)
        alerts_tree.column('status', width=80)
        alerts_tree.column('last_sent', width=150)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=alerts_tree.yview)
        alerts_tree.configure(yscrollcommand=scrollbar.set)
        
        alerts_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        def load_alerts():
            """Load alerts from database"""
            # Clear existing
            for item in alerts_tree.get_children():
                alerts_tree.delete(item)
            
            # Load from database
            alerts = self.db.get_all_telegram_alerts()
            
            for alert in alerts:
                status_text = "🟢 نشط" if alert['active'] else "⚫ متوقف"
                repeat_text = "🔁 يومي" if alert['repeat_mode'] == 'daily' else "1️⃣ مرة واحدة"
                last_sent = alert['last_sent'] if alert['last_sent'] else "لم يرسل بعد"
                
                # Truncate message if too long
                message = alert['message']
                if len(message) > 50:
                    message = message[:47] + "..."
                
                alerts_tree.insert('', 'end', values=(
                    alert['alert_time'],
                    message,
                    repeat_text,
                    status_text,
                    last_sent
                ), tags=(str(alert['id']),))
        
        def add_alert():
            """Add new alert"""
            dialog = tk.Toplevel(win)
            dialog.title("إضافة تنبيه جديد")
            dialog.geometry("550x500")
            dialog.configure(bg=self.colors['bg_main'])
            dialog.transient(win)
            
            # Title
            tk.Label(dialog, text="⏰ تنبيه جديد",
                    bg=self.colors['bg_main'], fg=self.colors['accent_green'],
                    font=('Arial', 12, 'bold')).pack(pady=10)
            
            # Time selection
            time_frame = tk.LabelFrame(dialog, text="🕐 الوقت",
                                      bg=self.colors['bg_card'],
                                      fg=self.colors['accent_blue'],
                                      font=('Arial', 10, 'bold'))
            time_frame.pack(fill='x', padx=20, pady=10)
            
            time_inner = tk.Frame(time_frame, bg=self.colors['bg_card'])
            time_inner.pack(padx=10, pady=10)
            
            tk.Label(time_inner, text="الساعة:",
                    bg=self.colors['bg_card'], fg=self.colors['text_white'],
                    font=('Arial', 10)).grid(row=0, column=0, padx=5, pady=5)
            
            hour_var = tk.StringVar(value="12")
            hour_spin = tk.Spinbox(time_inner, from_=0, to=23, width=5,
                                  textvariable=hour_var,
                                  bg=self.colors['bg_card_light'],
                                  fg=self.colors['text_white'],
                                  font=('Arial', 11))
            hour_spin.grid(row=0, column=1, padx=5)
            
            tk.Label(time_inner, text=":",
                    bg=self.colors['bg_card'], fg=self.colors['text_white'],
                    font=('Arial', 12, 'bold')).grid(row=0, column=2)
            
            tk.Label(time_inner, text="الدقيقة:",
                    bg=self.colors['bg_card'], fg=self.colors['text_white'],
                    font=('Arial', 10)).grid(row=0, column=3, padx=5, pady=5)
            
            minute_var = tk.StringVar(value="00")
            minute_spin = tk.Spinbox(time_inner, from_=0, to=59, width=5,
                                    textvariable=minute_var,
                                    bg=self.colors['bg_card_light'],
                                    fg=self.colors['text_white'],
                                    font=('Arial', 11))
            minute_spin.grid(row=0, column=4, padx=5)
            
            # Message
            msg_frame = tk.LabelFrame(dialog, text="📝 الرسالة",
                                     bg=self.colors['bg_card'],
                                     fg=self.colors['accent_blue'],
                                     font=('Arial', 10, 'bold'))
            msg_frame.pack(fill='both', expand=True, padx=20, pady=10)
            
            message_text = scrolledtext.ScrolledText(msg_frame, width=50, height=8,
                                                     bg=self.colors['bg_card_light'],
                                                     fg=self.colors['text_white'],
                                                     font=('Arial', 10),
                                                     wrap=tk.WORD)
            message_text.pack(padx=10, pady=10, fill='both', expand=True)
            
            # Repeat mode
            repeat_frame = tk.LabelFrame(dialog, text="🔁 التكرار",
                                        bg=self.colors['bg_card'],
                                        fg=self.colors['accent_blue'],
                                        font=('Arial', 10, 'bold'))
            repeat_frame.pack(fill='x', padx=20, pady=10)
            
            repeat_var = tk.StringVar(value="once")
            
            tk.Radiobutton(repeat_frame, text="1️⃣ مرة واحدة فقط",
                          variable=repeat_var, value="once",
                          bg=self.colors['bg_card'], fg=self.colors['text_white'],
                          selectcolor=self.colors['bg_card_light'],
                          font=('Arial', 10)).pack(anchor='w', padx=15, pady=5)
            
            tk.Radiobutton(repeat_frame, text="🔁 يومياً (كل يوم بنفس الوقت)",
                          variable=repeat_var, value="daily",
                          bg=self.colors['bg_card'], fg=self.colors['text_white'],
                          selectcolor=self.colors['bg_card_light'],
                          font=('Arial', 10)).pack(anchor='w', padx=15, pady=5)
            
            def save_alert():
                try:
                    hour = int(hour_var.get())
                    minute = int(minute_var.get())
                    
                    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
                        self.show_auto_close_message("خطأ", "الوقت غير صحيح!", 'error', 3, parent=dialog)
                        return
                    
                    alert_time = f"{hour:02d}:{minute:02d}"
                    message = message_text.get('1.0', 'end-1c').strip()
                    
                    if not message:
                        self.show_auto_close_message("خطأ", "الرجاء كتابة رسالة!", 'error', 3, parent=dialog)
                        return
                    
                    repeat_mode = repeat_var.get()
                    
                    # Save to database
                    alert_id = self.db.add_telegram_alert(alert_time, message, repeat_mode)
                    
                    logger.info(f"Added telegram alert #{alert_id}: {alert_time} - {repeat_mode}")
                    self.show_auto_close_message("نجح", f"تم إضافة التنبيه!\nسيرسل الساعة {alert_time}", 'info', 3, parent=dialog)
                    
                    dialog.destroy()
                    load_alerts()
                    
                except ValueError:
                    self.show_auto_close_message("خطأ", "الوقت غير صحيح!", 'error', 3, parent=dialog)
                except Exception as e:
                    logger.error(f"Error adding alert: {e}")
                    self.show_auto_close_message("خطأ", f"فشل إضافة التنبيه: {str(e)}", 'error', 3, parent=dialog)
            
            # Buttons
            btn_frame = tk.Frame(dialog, bg=self.colors['bg_main'])
            btn_frame.pack(pady=15)
            
            ModernButton(btn_frame, text="💾 حفظ",
                        command=save_alert,
                        bg=self.colors['accent_green'], fg='black',
                        font=('Arial', 11, 'bold'),
                        relief='raised', bd=3, padx=30, pady=10,
                        cursor='hand2').pack(side='left', padx=10)
            
            ModernButton(btn_frame, text="✗ إلغاء",
                        command=dialog.destroy,
                        bg=self.colors['accent_red'], fg='white',
                        font=('Arial', 11, 'bold'),
                        relief='raised', bd=3, padx=30, pady=10,
                        cursor='hand2').pack(side='left', padx=10)
        
        def edit_alert():
            """Edit selected alert"""
            selection = alerts_tree.selection()
            if not selection:
                self.show_auto_close_message("تحذير", "الرجاء اختيار تنبيه للتعديل!", 'warning', 3, parent=win)
                return
            
            item = alerts_tree.item(selection[0])
            alert_id = int(item['tags'][0])
            
            # Get alert from database
            alerts = self.db.get_all_telegram_alerts()
            alert = next((a for a in alerts if a['id'] == alert_id), None)
            
            if not alert:
                self.show_auto_close_message("خطأ", "التنبيه غير موجود!", 'error', 3, parent=win)
                return
            
            # Similar dialog to add_alert but with pre-filled values
            dialog = tk.Toplevel(win)
            dialog.title("تعديل تنبيه")
            dialog.geometry("550x500")
            dialog.configure(bg=self.colors['bg_main'])
            dialog.transient(win)
            
            tk.Label(dialog, text="✏️ تعديل التنبيه",
                    bg=self.colors['bg_main'], fg=self.colors['accent_blue'],
                    font=('Arial', 12, 'bold')).pack(pady=10)
            
            # Parse existing time
            time_parts = alert['alert_time'].split(':')
            existing_hour = int(time_parts[0])
            existing_minute = int(time_parts[1])
            
            # Time selection
            time_frame = tk.LabelFrame(dialog, text="🕐 الوقت",
                                      bg=self.colors['bg_card'],
                                      fg=self.colors['accent_blue'],
                                      font=('Arial', 10, 'bold'))
            time_frame.pack(fill='x', padx=20, pady=10)
            
            time_inner = tk.Frame(time_frame, bg=self.colors['bg_card'])
            time_inner.pack(padx=10, pady=10)
            
            tk.Label(time_inner, text="الساعة:",
                    bg=self.colors['bg_card'], fg=self.colors['text_white'],
                    font=('Arial', 10)).grid(row=0, column=0, padx=5, pady=5)
            
            hour_var = tk.StringVar(value=str(existing_hour))
            hour_spin = tk.Spinbox(time_inner, from_=0, to=23, width=5,
                                  textvariable=hour_var,
                                  bg=self.colors['bg_card_light'],
                                  fg=self.colors['text_white'],
                                  font=('Arial', 11))
            hour_spin.grid(row=0, column=1, padx=5)
            
            tk.Label(time_inner, text=":",
                    bg=self.colors['bg_card'], fg=self.colors['text_white'],
                    font=('Arial', 12, 'bold')).grid(row=0, column=2)
            
            tk.Label(time_inner, text="الدقيقة:",
                    bg=self.colors['bg_card'], fg=self.colors['text_white'],
                    font=('Arial', 10)).grid(row=0, column=3, padx=5, pady=5)
            
            minute_var = tk.StringVar(value=f"{existing_minute:02d}")
            minute_spin = tk.Spinbox(time_inner, from_=0, to=59, width=5,
                                    textvariable=minute_var,
                                    bg=self.colors['bg_card_light'],
                                    fg=self.colors['text_white'],
                                    font=('Arial', 11))
            minute_spin.grid(row=0, column=4, padx=5)
            
            # Message
            msg_frame = tk.LabelFrame(dialog, text="📝 الرسالة",
                                     bg=self.colors['bg_card'],
                                     fg=self.colors['accent_blue'],
                                     font=('Arial', 10, 'bold'))
            msg_frame.pack(fill='both', expand=True, padx=20, pady=10)
            
            message_text = scrolledtext.ScrolledText(msg_frame, width=50, height=8,
                                                     bg=self.colors['bg_card_light'],
                                                     fg=self.colors['text_white'],
                                                     font=('Arial', 10),
                                                     wrap=tk.WORD)
            message_text.pack(padx=10, pady=10, fill='both', expand=True)
            message_text.insert('1.0', alert['message'])
            
            # Repeat mode
            repeat_frame = tk.LabelFrame(dialog, text="🔁 التكرار",
                                        bg=self.colors['bg_card'],
                                        fg=self.colors['accent_blue'],
                                        font=('Arial', 10, 'bold'))
            repeat_frame.pack(fill='x', padx=20, pady=10)
            
            repeat_var = tk.StringVar(value=alert['repeat_mode'])
            
            tk.Radiobutton(repeat_frame, text="1️⃣ مرة واحدة فقط",
                          variable=repeat_var, value="once",
                          bg=self.colors['bg_card'], fg=self.colors['text_white'],
                          selectcolor=self.colors['bg_card_light'],
                          font=('Arial', 10)).pack(anchor='w', padx=15, pady=5)
            
            tk.Radiobutton(repeat_frame, text="🔁 يومياً (كل يوم بنفس الوقت)",
                          variable=repeat_var, value="daily",
                          bg=self.colors['bg_card'], fg=self.colors['text_white'],
                          selectcolor=self.colors['bg_card_light'],
                          font=('Arial', 10)).pack(anchor='w', padx=15, pady=5)
            
            def update_alert():
                try:
                    hour = int(hour_var.get())
                    minute = int(minute_var.get())
                    
                    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
                        self.show_auto_close_message("خطأ", "الوقت غير صحيح!", 'error', 3, parent=dialog)
                        return
                    
                    alert_time = f"{hour:02d}:{minute:02d}"
                    message = message_text.get('1.0', 'end-1c').strip()
                    
                    if not message:
                        self.show_auto_close_message("خطأ", "الرجاء كتابة رسالة!", 'error', 3, parent=dialog)
                        return
                    
                    repeat_mode = repeat_var.get()
                    
                    # Update in database
                    self.db.update_telegram_alert(alert_id, alert_time, message, repeat_mode)
                    
                    logger.info(f"Updated telegram alert #{alert_id}: {alert_time} - {repeat_mode}")
                    self.show_auto_close_message("نجح", "تم تحديث التنبيه بنجاح!", 'info', 3, parent=dialog)
                    
                    dialog.destroy()
                    load_alerts()
                    
                except ValueError:
                    self.show_auto_close_message("خطأ", "الوقت غير صحيح!", 'error', 3, parent=dialog)
                except Exception as e:
                    logger.error(f"Error updating alert: {e}")
                    self.show_auto_close_message("خطأ", f"فشل تحديث التنبيه: {str(e)}", 'error', 3, parent=dialog)
            
            # Buttons
            btn_frame = tk.Frame(dialog, bg=self.colors['bg_main'])
            btn_frame.pack(pady=15)
            
            ModernButton(btn_frame, text="💾 حفظ",
                        command=update_alert,
                        bg=self.colors['accent_green'], fg='black',
                        font=('Arial', 11, 'bold'),
                        relief='raised', bd=3, padx=30, pady=10,
                        cursor='hand2').pack(side='left', padx=10)
            
            ModernButton(btn_frame, text="✗ إلغاء",
                        command=dialog.destroy,
                        bg=self.colors['accent_red'], fg='white',
                        font=('Arial', 11, 'bold'),
                        relief='raised', bd=3, padx=30, pady=10,
                        cursor='hand2').pack(side='left', padx=10)
        
        def delete_alert():
            """Delete selected alert"""
            selection = alerts_tree.selection()
            if not selection:
                self.show_auto_close_message("تحذير", "الرجاء اختيار تنبيه للحذف!", 'warning', 3, parent=win)
                return
            
            item = alerts_tree.item(selection[0])
            alert_id = int(item['tags'][0])
            
            result = messagebox.askyesno("تأكيد الحذف",
                                        "هل أنت متأكد من حذف هذا التنبيه؟",
                                        parent=win)
            
            if result:
                try:
                    self.db.delete_telegram_alert(alert_id)
                    logger.info(f"Deleted telegram alert #{alert_id}")
                    self.show_auto_close_message("نجح", "تم حذف التنبيه!", 'info', 3, parent=win)
                    load_alerts()
                except Exception as e:
                    logger.error(f"Error deleting alert: {e}")
                    messagebox.showerror("خطأ", f"فشل الحذف: {str(e)}", parent=win)
        
        def toggle_alert():
            """Toggle alert active/inactive"""
            selection = alerts_tree.selection()
            if not selection:
                self.show_auto_close_message("تحذير", "الرجاء اختيار تنبيه!", 'warning', 3, parent=win)
                return
            
            item = alerts_tree.item(selection[0])
            alert_id = int(item['tags'][0])
            
            # Get current status
            alerts = self.db.get_all_telegram_alerts()
            alert = next((a for a in alerts if a['id'] == alert_id), None)
            
            if alert:
                new_status = not alert['active']
                self.db.toggle_alert_active(alert_id, new_status)
                status_text = "تفعيل" if new_status else "تعطيل"
                logger.info(f"Toggled alert #{alert_id} to {'active' if new_status else 'inactive'}")
                self.show_auto_close_message("نجح", f"تم {status_text} التنبيه!", 'info', 3, parent=win)
                load_alerts()
        
        # Buttons
        btn_frame = tk.Frame(win, bg=self.colors['bg_main'])
        btn_frame.pack(fill='x', padx=15, pady=10)
        
        ModernButton(btn_frame, text="➕ إضافة تنبيه",
                    command=add_alert,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=15, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="✏️ تعديل",
                    command=edit_alert,
                    bg=self.colors['accent_blue'], fg='black',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=15, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="🗑️ حذف",
                    command=delete_alert,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=15, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="⏸️ تفعيل/إيقاف",
                    command=toggle_alert,
                    bg=self.colors['accent_yellow'], fg='black',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=15, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="🔄 تحديث",
                    command=load_alerts,
                    bg=self.colors['accent_purple'], fg='white',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=15, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
        
        # Info label
        info_frame = tk.Frame(win, bg=self.colors['bg_main'])
        info_frame.pack(fill='x', padx=15, pady=10)
        
        tk.Label(info_frame, text="💡 التنبيهات اليومية ترسل كل يوم بنفس الوقت | التنبيهات لمرة واحدة ترسل مرة واحدة فقط",
                bg=self.colors['bg_main'], fg=self.colors['accent_yellow'],
                font=('Arial', 9)).pack()
        
        # Load alerts
        load_alerts()
        
        # Start alert checker if not running
        if not self.alert_check_running:
            self.start_alert_checker()
    
    def start_alert_checker(self):
        """Start background alert checker"""
        self.alert_check_running = True
        logger.info("Started telegram alert checker")
        self.check_alerts()
    
    def check_alerts(self):
        """Check and send due alerts"""
        if not self.alert_check_running:
            return
        
        try:
            # Get current time
            now = datetime.now()
            current_time = now.strftime('%H:%M')
            current_date = now.strftime('%Y-%m-%d')
            
            # Get active alerts
            alerts = self.db.get_active_alerts()
            
            for alert in alerts:
                alert_time = alert['alert_time']
                
                # Check if it's time to send
                if alert_time == current_time:
                    # Check if already sent today (for daily) or ever (for once)
                    last_sent = alert['last_sent']
                    
                    should_send = False
                    
                    if alert['repeat_mode'] == 'daily':
                        # Check if not sent today
                        if not last_sent or not last_sent.startswith(current_date):
                            should_send = True
                    else:  # once
                        # Check if never sent
                        if not last_sent:
                            should_send = True
                            # Deactivate after sending
                            self.db.toggle_alert_active(alert['id'], False)
                    
                    if should_send:
                        # Send alert to all channels
                        try:
                            self.telegram.send_alert_message(alert['message'])
                            self.db.update_alert_last_sent(alert['id'])
                            logger.info(f"Sent telegram alert #{alert['id']}: {alert['message'][:50]}")
                        except Exception as e:
                            logger.error(f"Error sending alert #{alert['id']}: {e}")
            
        except Exception as e:
            logger.error(f"Error in alert checker: {e}")
        
        # Check every 30 seconds
        if self.alert_check_running:
            self.root.after(30000, self.check_alerts)
    
    def show_tracking_history(self, event):
        """Show LIVE tracking from database (no extra IBKR connection)"""
        selection = self.active_tree.selection()
        if not selection:
            return
        
        # Get trade ID from tags
        item = selection[0]
        tags = self.active_tree.item(item, 'tags')
        
        if not tags:
            self.show_auto_close_message("خطأ", "لم يتم العثور على معرف الصفقة!", 'error', 3)
            return
        
        trade_id = int(tags[0])
        
        # Get trade from database
        active_trades = self.db.get_active_trades()
        trade = next((t for t in active_trades if t['id'] == trade_id), None)
        
        if not trade:
            self.show_auto_close_message("خطأ", f"الصفقة #{trade_id} غير موجودة!", 'error', 3)
            return
        
        # Format contract name for display
        contract_name = self.format_contract_name(trade.get('option_contract', ''))
        
        # Create tracking window
        track_win = tk.Toplevel(self.root)
        track_win.title(f"📊 تتبع حي - الصفقة #{trade_id}")
        track_win.geometry("900x700")
        track_win.configure(bg=self.colors['bg_main'])
        track_win.transient(self.root)
        
        # Header
        header_frame = tk.Frame(track_win, bg=self.colors['bg_card'])
        header_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(header_frame, text=f"📊 تتبع حي - Live Tracking",
                bg=self.colors['bg_card'], fg=self.colors['accent_blue'],
                font=('Arial', 14, 'bold')).pack(pady=10)
        
        # Trade Info
        info_frame = tk.Frame(track_win, bg=self.colors['bg_card'])
        info_frame.pack(fill='x', padx=15, pady=10)
        
        tk.Label(info_frame, text=f"العقد: {contract_name}",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 11, 'bold')).pack(side='left', padx=10)
        
        tk.Label(info_frame, text=f"سعر الدخول: ${trade.get('entry_price', 0):.2f}",
                bg=self.colors['bg_card'], fg=self.colors['accent_green'],
                font=('Arial', 11)).pack(side='left', padx=10)
        
        # Live highest price label (will update)
        highest_label = tk.Label(info_frame, text=f"أعلى سعر: ${trade.get('highest_price', 0):.2f}",
                bg=self.colors['bg_card'], fg=self.colors['accent_yellow'],
                font=('Arial', 11))
        highest_label.pack(side='left', padx=10)
        
        # Live track count label (will update)
        count_label = tk.Label(info_frame, text=f"عدد التتبع: ⚡{trade.get('track_count', 0)}",
                bg=self.colors['bg_card'], fg=self.colors['accent_purple'],
                font=('Arial', 11))
        count_label.pack(side='left', padx=10)
        
        # Status label
        status_label = tk.Label(track_win, text="✅ التتبع الحي نشط - قراءة من قاعدة البيانات",
                               bg=self.colors['bg_main'], fg=self.colors['accent_green'],
                               font=('Arial', 10))
        status_label.pack(pady=5)
        
        # Tracking history table
        table_frame = tk.Frame(track_win, bg=self.colors['bg_card'])
        table_frame.pack(fill='both', expand=True, padx=15, pady=10)
        
        columns = ('num', 'time', 'bid', 'highest')
        history_tree = ttk.Treeview(table_frame, columns=columns, height=20, show='headings')
        
        history_tree.heading('num', text='⚡ التتبع')
        history_tree.heading('time', text='🕒 الوقت')
        history_tree.heading('bid', text='💰 الطلب (Bid)')
        history_tree.heading('highest', text='🔥 أعلى سعر')
        
        history_tree.column('num', width=100)
        history_tree.column('time', width=150)
        history_tree.column('bid', width=150)
        history_tree.column('highest', width=150)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=history_tree.yview)
        history_tree.configure(yscrollcommand=scrollbar.set)
        
        history_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Close button
        ModernButton(track_win, text="✗ إغلاق",
                    command=track_win.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=40, pady=10,
                    cursor='hand2').pack(pady=15)
        
        # Live tracking state
        tracking_active = [True]
        last_count = [0]
        running_highest = [trade.get('entry_price', 0)]  # Track highest across updates
        
        # Update function - reads from database
        def update_tracking_display():
            """Update display from database every 0.5 seconds"""
            if not tracking_active[0]:
                return
            
            try:
                import sqlite3
                
                # Get latest trade info
                active_trades = self.db.get_active_trades()
                current_trade = next((t for t in active_trades if t['id'] == trade_id), None)
                
                if not current_trade:
                    tracking_active[0] = False
                    return
                
                # Update labels with latest values
                highest_label.config(text=f"أعلى سعر: ${current_trade.get('highest_price', 0):.2f}")
                count_label.config(text=f"عدد التتبع: ⚡{current_trade.get('track_count', 0)}")
                
                # Get new tracking records since last update
                conn = self.db.connect()
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT price, bid, ask, timestamp 
                    FROM price_tracking 
                    WHERE trade_id = ? 
                    ORDER BY id ASC
                ''', (trade_id,))
                
                all_records = cursor.fetchall()
                conn.close()
                
                # Add only new records
                total_records = len(all_records)
                if total_records > last_count[0]:
                    # Add new records only
                    new_records = all_records[last_count[0]:]
                    
                    for idx, (price, bid, ask, timestamp) in enumerate(new_records, start=last_count[0] + 1):
                        # Update running highest
                        if bid and bid > running_highest[0]:
                            running_highest[0] = bid
                        
                        history_tree.insert('', 'end', values=(
                            idx,
                            timestamp,
                            f"${bid:.2f}" if bid else "N/A",
                            f"${running_highest[0]:.2f}"
                        ))
                    
                    last_count[0] = total_records
                    
                    # Auto-scroll to bottom
                    children = history_tree.get_children()
                    if children:
                        history_tree.see(children[-1])
                
            except Exception as e:
                logger.error(f"Error updating tracking display: {e}")
            
            # Schedule next update (every 500ms)
            if tracking_active[0]:
                track_win.after(500, update_tracking_display)
        
        # Start updating immediately
        update_tracking_display()
        
        # Stop tracking when window closes
        def on_closing():
            tracking_active[0] = False
            track_win.destroy()
        
        track_win.protocol("WM_DELETE_WINDOW", on_closing)
    
    def edit_message_texts(self):
        """Edit telegram message texts"""
        win = tk.Toplevel(self.root)
        win.title("تعديل نصوص الرسائل")
        win.geometry("900x850")
        win.configure(bg=self.colors['bg_main'])
        win.transient(self.root)
        
        # Title
        title_frame = tk.Frame(win, bg=self.colors['bg_card'])
        title_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(title_frame, text="✏️ تعديل نصوص رسائل التيليجرام",
                bg=self.colors['bg_card'], fg=self.colors['accent_blue'],
                font=('Arial', 14, 'bold')).pack(pady=10)
        
        tk.Label(title_frame, text="📝 النصوص الحالية مطابقة للنظام القديم - يمكنك تعديلها كما تريد",
                bg=self.colors['bg_card'], fg=self.colors['accent_green'],
                font=('Arial', 9, 'bold')).pack(pady=3)
        
        # Variables reference button
        variables_btn_frame = tk.Frame(title_frame, bg=self.colors['bg_card'])
        variables_btn_frame.pack(pady=5)
        
        ModernButton(variables_btn_frame, text="📋 دليل المتغيرات والحسابات",
                    command=lambda: self.show_variables_reference(win),
                    bg=self.colors['accent_blue'], fg='white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=15, pady=5,
                    cursor='hand2').pack()
        
        # Scrollable frame
        canvas = tk.Canvas(win, bg=self.colors['bg_main'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors['bg_main'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=10)
        scrollbar.pack(side="right", fill="y")
        
        # Message types
        messages = [
            ('signal_received', '📡 استقبال الإشارة'),
            ('contract_found', '✅ العثور على العقد'),
            ('position_opened', '🚀 فتح الصفقة'),
            ('new_high', '🎉 أعلى سعر جديد'),
            ('price_update', '🔄 تحديث السعر'),
            ('stop_loss_hit', '🛑 وقف الخسارة'),
            ('profit_target_hit', '🎯 تحقيق الهدف'),
            ('position_closed', '🔒 إغلاق الصفقة'),
            ('daily_summary', '📊 الملخص اليومي'),
        ]
        
        # Get current texts
        current_texts = self.telegram.custom_texts
        
        # Text entries storage
        text_entries = {}
        
        for msg_type, title in messages:
            frame = tk.LabelFrame(scrollable_frame, text=title,
                                 bg=self.colors['bg_card'],
                                 fg=self.colors['accent_purple'],
                                 font=('Arial', 10, 'bold'),
                                 borderwidth=2, relief='groove')
            frame.pack(fill='x', padx=10, pady=8)
            
            text_widget = scrolledtext.ScrolledText(frame, width=80, height=4,
                                                    bg=self.colors['bg_card_light'],
                                                    fg=self.colors['text_white'],
                                                    font=('Arial', 10),
                                                    wrap=tk.WORD)
            text_widget.pack(padx=10, pady=10, fill='x')
            text_widget.insert('1.0', current_texts.get(msg_type, ''))
            
            text_entries[msg_type] = text_widget
        
        # Save button
        btn_frame = tk.Frame(win, bg=self.colors['bg_main'])
        btn_frame.pack(pady=15)
        
        def save_texts():
            try:
                for msg_type, text_widget in text_entries.items():
                    text = text_widget.get('1.0', 'end-1c').strip()
                    self.telegram.save_custom_text(msg_type, text)
                
                self.show_auto_close_message("نجح", "تم حفظ نصوص الرسائل بنجاح!", 'info', 3, parent=win)
                logger.info("Updated telegram message texts")
            except Exception as e:
                logger.error(f"Error saving message texts: {e}")
                self.show_auto_close_message("خطأ", f"فشل حفظ النصوص: {str(e)}", 'error', 3, parent=win)
        
        def restore_defaults():
            """Restore default texts from old system"""
            if messagebox.askyesno("تأكيد", "هل تريد استعادة النصوص الافتراضية من النظام القديم؟\n\nسيتم حذف جميع التعديلات الحالية.", parent=win):
                try:
                    # Delete saved file
                    import os
                    if os.path.exists('telegram_texts.json'):
                        os.remove('telegram_texts.json')
                    
                    # Reload defaults
                    self.telegram.custom_texts = self.telegram._load_custom_texts()
                    
                    # Update all text widgets
                    for msg_type, text_widget in text_entries.items():
                        text_widget.delete('1.0', 'end')
                        text_widget.insert('1.0', self.telegram.custom_texts.get(msg_type, ''))
                    
                    self.show_auto_close_message("نجح", "تم استعادة النصوص الافتراضية من النظام القديم!", 'info', 3, parent=win)
                    logger.info("Restored default telegram texts")
                except Exception as e:
                    logger.error(f"Error restoring defaults: {e}")
                    self.show_auto_close_message("خطأ", f"فشل استعادة النصوص: {str(e)}", 'error', 3, parent=win)
        
        ModernButton(btn_frame, text="💾 حفظ جميع النصوص",
                    command=save_texts,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=40, pady=10,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="🔄 استعادة الافتراضي",
                    command=restore_defaults,
                    bg=self.colors['accent_yellow'], fg='black',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=30, pady=10,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="✗ إغلاق",
                    command=win.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=40, pady=10,
                    cursor='hand2').pack(side='left', padx=5)
    
    def show_variables_reference(self, parent=None):
        """Show variables and calculations reference"""
        ref_win = tk.Toplevel(parent if parent else self.root)
        ref_win.title("دليل المتغيرات والحسابات")
        ref_win.geometry("800x700")
        ref_win.configure(bg=self.colors['bg_main'])
        if parent:
            ref_win.transient(parent)
        
        # Title
        title_frame = tk.Frame(ref_win, bg=self.colors['bg_card'])
        title_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(title_frame, text="📋 دليل المتغيرات والحسابات",
                bg=self.colors['bg_card'], fg=self.colors['accent_blue'],
                font=('Arial', 14, 'bold')).pack(pady=10)
        
        # Scrollable content
        canvas = tk.Canvas(ref_win, bg=self.colors['bg_main'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(ref_win, orient="vertical", command=canvas.yview)
        content_frame = tk.Frame(canvas, bg=self.colors['bg_main'])
        
        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=10)
        scrollbar.pack(side="right", fill="y")
        
        # Content
        text_widget = scrolledtext.ScrolledText(content_frame, width=90, height=35,
                                                bg=self.colors['bg_card_light'],
                                                fg=self.colors['text_white'],
                                                font=('Consolas', 9),
                                                wrap=tk.WORD)
        text_widget.pack(fill='both', expand=True, padx=10, pady=10)
        
        reference_text = f"""
📋 دليل المتغيرات المتاحة في نصوص الإشعارات
{'='*80}

🔹 المتغيرات الأساسية (متاحة في جميع الإشعارات):
  {{type}}          - نوع الصفقة: CALL أو PUT
  {{symbol}}        - رمز الشركة: SPX, NDX, SPY, QQQ
  {{time}}          - الوقت الحالي
  {{contract}}      - اسم العقد الكامل (مثل: SPX 6950 CALL)
  {{strike}}        - سعر التنفيذ (Strike Price)

🔹 متغيرات الأسعار (بالدولار):
  {{entry_price}}   - سعر الدخول
  {{exit_price}}    - سعر الخروج
  {{current_price}} - السعر الحالي (Bid)
  {{highest_price}} - أعلى سعر تم الوصول إليه
  {{last}}          - آخر سعر
  {{bid}}           - سعر العرض
  {{ask}}           - سعر الطلب
  
🔹 متغيرات الربح/الخسارة:
  {{profit}}        - الربح بالدولار (يمكن أن يكون + أو -)
  {{profit_pct}}    - نسبة الربح المئوية
  {{profit_emoji}}  - رمز تعبيري تلقائي (💰 للربح / 📉 للخسارة)
  {{profit_status}} - نص حالة الربح الكامل

💱 تحويل العملات - استخدام المتغيرات للحسابات:
{'='*80}

سعر الصرف الحالي: 1 USD = {config.SAR_EXCHANGE_RATE} SAR

🔹 طريقة 1: استخدام التنسيق المباشر
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
سعر الدخول: <b>{{entry_price:.2f}} USD ({{entry_price:.2f}} × {config.SAR_EXCHANGE_RATE} = {{entry_price_sar:.2f}} SAR)</b>

🔹 طريقة 2: استخدام متغيرات محسوبة مسبقاً
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
عند استخدام المتغيرات التالية، يتم الحساب تلقائياً:
  
  {{entry_price_usd}}    - سعر الدخول USD
  {{entry_price_sar}}    - سعر الدخول SAR (محسوب تلقائياً)
  {{exit_price_usd}}     - سعر الخروج USD  
  {{exit_price_sar}}     - سعر الخروج SAR
  {{highest_price_usd}}  - أعلى سعر USD
  {{highest_price_sar}}  - أعلى سعر SAR
  {{profit_usd}}         - الربح USD
  {{profit_sar}}         - الربح SAR
  {{profit_display}}     - عرض الربح بالعملتين

مثال على الاستخدام:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💵 سعر الدخول: <b>{{entry_price_usd}} ({{entry_price_sar}})</b>
💰 الربح: <b>{{profit_display}}</b>

✅ الأرباح: <b>{{total_profit_usd}} ({{total_profit_sar}})</b>

📝 أمثلة عملية:
{'='*80}

مثال 1: فتح صفقة (بدون ريال - النظام القديم):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ <b>دخول {{type}}</b>
━━━━━━━━━━━━━━━━━━━━━━━
العقد: <code>{{contract}}</code>
Strike: <b>{{strike}}</b>
سعر الدخول: <b>{{entry_price:.2f}} USD</b>
⏰ الوقت: {{time}}
━━━━━━━━━━━━━━━━━━━━━━━

مثال 2: فتح صفقة (مع ريال):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ <b>دخول {{type}}</b>
━━━━━━━━━━━━━━━━━━━━━━━
العقد: <code>{{contract}}</code>
Strike: <b>{{strike}}</b>
💵 سعر الدخول: <b>{{entry_price_usd}} ({{entry_price_sar}})</b>
⏰ الوقت: {{time}}
━━━━━━━━━━━━━━━━━━━━━━━

مثال 3: تحديث الربح (مع ريال):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 <b>أعلى سعر جديد!</b> ({{time}})
━━━━━━━━━━━━━━━━━━━━━━━
العقد: <code>{{contract}}</code>
━━━━━━━━━━━━━━━━━━━━━━━
  الأخير    |   عرض   |   طلب
   <b>{{last:.2f}}    |   {{current_price:.2f}}   |   {{ask:.2f}}</b>
━━━━━━━━━━━━━━━━━━━━━━━
📊 سعر الدخول: <b>{{entry_price_usd}} ({{entry_price_sar}})</b>
📈 أعلى سعر: <b>{{highest_price_usd}} ({{highest_price_sar}})</b>
💰 الربح: <b>{{profit_display}} {{profit_pct:+.1f}}%</b>
━━━━━━━━━━━━━━━━━━━━━━━

⚙️ إعدادات التحويل:
{'='*80}
• يمكن تفعيل/إيقاف تحويل العملات من ملف config.py
• تعديل سعر الصرف: SAR_EXCHANGE_RATE = {config.SAR_EXCHANGE_RATE}
• عرض العملتين معاً: SHOW_DUAL_CURRENCY = {config.SHOW_DUAL_CURRENCY}

💡 ملاحظات مهمة:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. النصوص الافتراضية مطابقة للنظام القديم (بدون ريال)
2. يمكنك إضافة الريال باستخدام المتغيرات أعلاه
3. استخدم {{:.2f}} لتنسيق الأرقام بعلامتين عشريتين
4. جميع الحسابات تتم تلقائياً قبل إرسال الرسالة
5. يمكنك استعادة النصوص الافتراضية في أي وقت

📌 نصيحة: انسخ الأمثلة أعلاه واستخدمها مباشرة في نصوص الإشعارات!
"""
        
        text_widget.insert('1.0', reference_text)
        text_widget.config(state='disabled')
        
        # Close button
        ModernButton(ref_win, text="✓ فهمت",
                    command=ref_win.destroy,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=40, pady=10,
                    cursor='hand2').pack(pady=15)
    
    def edit_image_settings(self):
        """Edit telegram image settings"""
        win = tk.Toplevel(self.root)
        win.title("إعدادات صور التيليجرام")
        win.geometry("700x750")
        win.configure(bg=self.colors['bg_main'])
        win.transient(self.root)
        
        # Title
        title_frame = tk.Frame(win, bg=self.colors['bg_card'])
        title_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(title_frame, text="🎨 تخصيص الصور",
                bg=self.colors['bg_card'], fg=self.colors['accent_yellow'],
                font=('Arial', 14, 'bold')).pack(pady=10)
        
        tk.Label(title_frame, text="عدّل ألوان وشفافية الصور المرسلة في الإشعارات",
                bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                font=('Arial', 9)).pack(pady=5)
        
        main_frame = tk.Frame(win, bg=self.colors['bg_main'])
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Get current settings
        current_settings = self.telegram.image_settings
        
        # Background Color
        bg_frame = tk.LabelFrame(main_frame, text="🎨 لون الخلفية",
                                bg=self.colors['bg_card'],
                                fg=self.colors['accent_blue'],
                                font=('Arial', 10, 'bold'),
                                borderwidth=2, relief='groove')
        bg_frame.pack(fill='x', pady=10)
        
        bg_inner = tk.Frame(bg_frame, bg=self.colors['bg_card'])
        bg_inner.pack(padx=15, pady=15)
        
        bg_color = current_settings.get('background_color', (0, 0, 0))
        
        tk.Label(bg_inner, text="R:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 9)).grid(row=0, column=0, padx=5)
        bg_r = tk.Scale(bg_inner, from_=0, to=255, orient='horizontal',
                       bg=self.colors['bg_card'], fg=self.colors['accent_red'],
                       highlightthickness=0, length=150)
        bg_r.set(bg_color[0])
        bg_r.grid(row=0, column=1, padx=5)
        
        tk.Label(bg_inner, text="G:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 9)).grid(row=1, column=0, padx=5)
        bg_g = tk.Scale(bg_inner, from_=0, to=255, orient='horizontal',
                       bg=self.colors['bg_card'], fg=self.colors['accent_green'],
                       highlightthickness=0, length=150)
        bg_g.set(bg_color[1])
        bg_g.grid(row=1, column=1, padx=5)
        
        tk.Label(bg_inner, text="B:",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 9)).grid(row=2, column=0, padx=5)
        bg_b = tk.Scale(bg_inner, from_=0, to=255, orient='horizontal',
                       bg=self.colors['bg_card'], fg=self.colors['accent_blue'],
                       highlightthickness=0, length=150)
        bg_b.set(bg_color[2])
        bg_b.grid(row=2, column=1, padx=5)
        
        # Preview color
        preview_bg = tk.Canvas(bg_inner, width=60, height=60, bg='black',
                              highlightthickness=2, highlightbackground=self.colors['accent_blue'])
        preview_bg.grid(row=0, column=2, rowspan=3, padx=20)
        
        def update_bg_preview(*args):
            r, g, b = bg_r.get(), bg_g.get(), bg_b.get()
            color = f'#{r:02x}{g:02x}{b:02x}'
            preview_bg.config(bg=color)
        
        bg_r.config(command=update_bg_preview)
        bg_g.config(command=update_bg_preview)
        bg_b.config(command=update_bg_preview)
        update_bg_preview()
        
        # Background Image
        bg_img_frame = tk.LabelFrame(main_frame, text="🖼️ صورة الخلفية",
                                    bg=self.colors['bg_card'],
                                    fg=self.colors['accent_blue'],
                                    font=('Arial', 10, 'bold'),
                                    borderwidth=2, relief='groove')
        bg_img_frame.pack(fill='x', pady=10)
        
        bg_img_inner = tk.Frame(bg_img_frame, bg=self.colors['bg_card'])
        bg_img_inner.pack(padx=15, pady=15)
        
        current_bg_img = current_settings.get('background_image', None)
        bg_img_path = tk.StringVar(value=current_bg_img if current_bg_img else "لا توجد صورة")
        
        tk.Label(bg_img_inner, textvariable=bg_img_path,
                bg=self.colors['bg_card'], fg=self.colors['text_gray'],
                font=('Arial', 9)).pack(side='left', padx=10)
        
        def choose_bg_image():
            from tkinter import filedialog
            filepath = filedialog.askopenfilename(
                title="اختر صورة الخلفية",
                filetypes=[("صور", "*.png *.jpg *.jpeg *.bmp"), ("جميع الملفات", "*.*")]
            )
            if filepath:
                bg_img_path.set(filepath)
        
        def remove_bg_image():
            bg_img_path.set("لا توجد صورة")
        
        ModernButton(bg_img_inner, text="📂 اختيار صورة",
                    command=choose_bg_image,
                    bg=self.colors['accent_blue'], fg='black',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=10, pady=5,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(bg_img_inner, text="🗑️ إزالة",
                    command=remove_bg_image,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 9, 'bold'),
                    relief='raised', bd=2, padx=10, pady=5,
                    cursor='hand2').pack(side='left', padx=5)
        
        # Opacity
        opacity_frame = tk.LabelFrame(main_frame, text="🔆 الشفافية",
                                     bg=self.colors['bg_card'],
                                     fg=self.colors['accent_purple'],
                                     font=('Arial', 10, 'bold'),
                                     borderwidth=2, relief='groove')
        opacity_frame.pack(fill='x', pady=10)
        
        opacity_inner = tk.Frame(opacity_frame, bg=self.colors['bg_card'])
        opacity_inner.pack(padx=15, pady=15)
        
        tk.Label(opacity_inner, text="الشفافية (%): ",
                bg=self.colors['bg_card'], fg=self.colors['text_white'],
                font=('Arial', 10)).pack(side='left', padx=5)
        
        opacity_var = tk.IntVar(value=current_settings.get('opacity', 100))
        opacity_scale = tk.Scale(opacity_inner, from_=0, to=100, orient='horizontal',
                                variable=opacity_var,
                                bg=self.colors['bg_card'], fg=self.colors['accent_yellow'],
                                highlightthickness=0, length=300)
        opacity_scale.pack(side='left', padx=10)
        
        opacity_label = tk.Label(opacity_inner, text=f"{opacity_var.get()}%",
                                bg=self.colors['bg_card'], fg=self.colors['accent_yellow'],
                                font=('Arial', 12, 'bold'))
        opacity_label.pack(side='left', padx=10)
        
        def update_opacity_label(*args):
            opacity_label.config(text=f"{opacity_var.get()}%")
        
        opacity_scale.config(command=update_opacity_label)
        
        # Colors
        colors_frame = tk.LabelFrame(main_frame, text="🌈 ألوان العناصر",
                                    bg=self.colors['bg_card'],
                                    fg=self.colors['accent_green'],
                                    font=('Arial', 10, 'bold'),
                                    borderwidth=2, relief='groove')
        colors_frame.pack(fill='x', pady=10)
        
        colors_inner = tk.Frame(colors_frame, bg=self.colors['bg_card'])
        colors_inner.pack(padx=15, pady=15)
        
        # Green color (positive)
        green_color = current_settings.get('green_color', (0, 255, 136))
        
        tk.Label(colors_inner, text="🟢 لون الربح (الأخضر):",
                bg=self.colors['bg_card'], fg=self.colors['accent_green'],
                font=('Arial', 9, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w', pady=5)
        
        green_r = tk.Scale(colors_inner, from_=0, to=255, orient='horizontal',
                          bg=self.colors['bg_card'], length=120)
        green_r.set(green_color[0])
        green_r.grid(row=1, column=0, padx=5)
        
        green_g = tk.Scale(colors_inner, from_=0, to=255, orient='horizontal',
                          bg=self.colors['bg_card'], length=120)
        green_g.set(green_color[1])
        green_g.grid(row=1, column=1, padx=5)
        
        green_b = tk.Scale(colors_inner, from_=0, to=255, orient='horizontal',
                          bg=self.colors['bg_card'], length=120)
        green_b.set(green_color[2])
        green_b.grid(row=1, column=2, padx=5)
        
        # Red color (negative)
        red_color = current_settings.get('red_color', (255, 51, 102))
        
        tk.Label(colors_inner, text="🔴 لون الخسارة (الأحمر):",
                bg=self.colors['bg_card'], fg=self.colors['accent_red'],
                font=('Arial', 9, 'bold')).grid(row=2, column=0, columnspan=3, sticky='w', pady=5)
        
        red_r = tk.Scale(colors_inner, from_=0, to=255, orient='horizontal',
                        bg=self.colors['bg_card'], length=120)
        red_r.set(red_color[0])
        red_r.grid(row=3, column=0, padx=5)
        
        red_g = tk.Scale(colors_inner, from_=0, to=255, orient='horizontal',
                        bg=self.colors['bg_card'], length=120)
        red_g.set(red_color[1])
        red_g.grid(row=3, column=1, padx=5)
        
        red_b = tk.Scale(colors_inner, from_=0, to=255, orient='horizontal',
                        bg=self.colors['bg_card'], length=120)
        red_b.set(red_color[2])
        red_b.grid(row=3, column=2, padx=5)
        
        # Blue color
        blue_color = current_settings.get('blue_color', (0, 212, 255))
        
        tk.Label(colors_inner, text="🔵 لون المعلومات (الأزرق):",
                bg=self.colors['bg_card'], fg=self.colors['accent_blue'],
                font=('Arial', 9, 'bold')).grid(row=4, column=0, columnspan=3, sticky='w', pady=5)
        
        blue_r = tk.Scale(colors_inner, from_=0, to=255, orient='horizontal',
                         bg=self.colors['bg_card'], length=120)
        blue_r.set(blue_color[0])
        blue_r.grid(row=5, column=0, padx=5)
        
        blue_g = tk.Scale(colors_inner, from_=0, to=255, orient='horizontal',
                         bg=self.colors['bg_card'], length=120)
        blue_g.set(blue_color[1])
        blue_g.grid(row=5, column=1, padx=5)
        
        blue_b = tk.Scale(colors_inner, from_=0, to=255, orient='horizontal',
                         bg=self.colors['bg_card'], length=120)
        blue_b.set(blue_color[2])
        blue_b.grid(row=5, column=2, padx=5)
        
        # Save button
        btn_frame = tk.Frame(win, bg=self.colors['bg_main'])
        btn_frame.pack(pady=15)
        
        def save_image_settings():
            try:
                bg_img = bg_img_path.get()
                if bg_img == "لا توجد صورة":
                    bg_img = None
                
                settings = {
                    'background_color': (bg_r.get(), bg_g.get(), bg_b.get()),
                    'background_image': bg_img,
                    'opacity': opacity_var.get(),
                    'green_color': (green_r.get(), green_g.get(), green_b.get()),
                    'red_color': (red_r.get(), red_g.get(), red_b.get()),
                    'blue_color': (blue_r.get(), blue_g.get(), blue_b.get())
                }
                
                self.telegram.save_image_settings(settings)
                self.show_auto_close_message("نجح", "تم حفظ إعدادات الصور بنجاح!", 'info', 3, parent=win)
                logger.info("Updated telegram image settings")
            except Exception as e:
                logger.error(f"Error saving image settings: {e}")
                self.show_auto_close_message("خطأ", f"فشل حفظ الإعدادات: {str(e)}", 'error', 3, parent=win)
        
        ModernButton(btn_frame, text="💾 حفظ الإعدادات",
                    command=save_image_settings,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=40, pady=10,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="🔄 استعادة الافتراضي",
                    command=lambda: [
                        bg_r.set(0), bg_g.set(0), bg_b.set(0),
                        opacity_var.set(100),
                        green_r.set(0), green_g.set(255), green_b.set(136),
                        red_r.set(255), red_g.set(51), red_b.set(102),
                        blue_r.set(0), blue_g.set(212), blue_b.set(255),
                        update_bg_preview()
                    ],
                    bg=self.colors['accent_yellow'], fg='black',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=30, pady=10,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="✗ إغلاق",
                    command=win.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 11, 'bold'),
                    relief='raised', bd=3, padx=40, pady=10,
                    cursor='hand2').pack(side='left', padx=5)
    
    def print_summary(self):
        """Print summary with period filter options"""
        try:
            # Ask user to select symbol and period
            dialog = tk.Toplevel(self.root)
            dialog.title("اختيار الشركة للطباعة")
            dialog.geometry("500x680" if CALENDAR_AVAILABLE else "500x450")
            dialog.configure(bg=self.colors['bg_main'])
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Center dialog
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - 250
            y = (dialog.winfo_screenheight() // 2) - (340 if CALENDAR_AVAILABLE else 225)
            dialog.geometry(f"+{x}+{y}")
            
            frame = tk.Frame(dialog, bg=self.colors['bg_card'], bd=2, relief='raised')
            frame.pack(fill='both', expand=True, padx=20, pady=20)
            
            tk.Label(frame, text="📊 اختر الشركة المراد طباعة ملخصها",
                    bg=self.colors['bg_card'], fg=self.colors['accent_blue'],
                    font=('Arial', 12, 'bold')).pack(pady=10)
            
            # Symbol selection
            tk.Label(frame, text="الشركة:",
                    bg=self.colors['bg_card'], fg=self.colors['text_white'],
                    font=('Arial', 10, 'bold')).pack(pady=5)
            
            symbol_var = tk.StringVar()
            symbol_combo = ttk.Combobox(frame, textvariable=symbol_var,
                                       values=config.SUPPORTED_SYMBOLS,
                                       width=20, font=('Arial', 10),
                                       state='readonly')
            symbol_combo.pack(pady=5)
            if config.SUPPORTED_SYMBOLS:
                symbol_combo.current(0)
            
            # Period selection
            period_frame = tk.LabelFrame(frame, text="📅 الفترة الزمنية",
                                        bg=self.colors['bg_card'],
                                        fg=self.colors['accent_green'],
                                        font=('Arial', 10, 'bold'))
            period_frame.pack(fill='x', padx=10, pady=10)
            
            period_var = tk.StringVar(value="daily")
            
            tk.Radiobutton(period_frame, text="📆 يومي (اليوم)",
                          variable=period_var, value="daily",
                          bg=self.colors['bg_card'], fg=self.colors['text_white'],
                          selectcolor=self.colors['bg_card_light'],
                          font=('Arial', 10)).pack(anchor='w', padx=15, pady=5)
            
            tk.Radiobutton(period_frame, text="📅 أسبوعي (آخر 7 أيام)",
                          variable=period_var, value="weekly",
                          bg=self.colors['bg_card'], fg=self.colors['text_white'],
                          selectcolor=self.colors['bg_card_light'],
                          font=('Arial', 10)).pack(anchor='w', padx=15, pady=5)
            
            tk.Radiobutton(period_frame, text="📊 شهري (آخر 30 يوم)",
                          variable=period_var, value="monthly",
                          bg=self.colors['bg_card'], fg=self.colors['text_white'],
                          selectcolor=self.colors['bg_card_light'],
                          font=('Arial', 10)).pack(anchor='w', padx=15, pady=5)
            
            # Date picker for daily (if available)
            date_frame = None
            date_entry = None
            cal_widget = None
            
            if CALENDAR_AVAILABLE:
                date_frame = tk.LabelFrame(frame, text="📅 اختيار التاريخ (للفترة اليومية)",
                                          bg=self.colors['bg_card'],
                                          fg=self.colors['accent_yellow'],
                                          font=('Arial', 10, 'bold'))
                date_frame.pack(fill='x', padx=10, pady=10)
                
                from tkcalendar import Calendar
                cal_widget = Calendar(date_frame,
                                     selectmode='day',
                                     year=datetime.now().year,
                                     month=datetime.now().month,
                                     day=datetime.now().day,
                                     background=self.colors['bg_card_light'],
                                     foreground=self.colors['text_white'],
                                     bordercolor=self.colors['accent_blue'],
                                     headersbackground=self.colors['accent_blue'],
                                     headersforeground='white',
                                     selectbackground=self.colors['accent_green'],
                                     selectforeground='black',
                                     date_pattern='yyyy-mm-dd')
                cal_widget.pack(padx=10, pady=10)
            else:
                # Manual date entry
                date_frame = tk.Frame(frame, bg=self.colors['bg_card'])
                date_frame.pack(fill='x', padx=10, pady=10)
                
                tk.Label(date_frame, text="📅 تاريخ يدوي (YYYY-MM-DD):",
                        bg=self.colors['bg_card'], fg=self.colors['text_white'],
                        font=('Arial', 9)).pack(anchor='w', padx=5)
                
                date_entry = tk.Entry(date_frame, width=15, font=('Arial', 10))
                date_entry.pack(padx=5, pady=5)
                date_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))
            
            def do_print():
                symbol = symbol_var.get()
                if not symbol:
                    self.show_auto_close_message("تحذير", "الرجاء اختيار الشركة!", 'warning', 3, parent=dialog)
                    return
                
                period = period_var.get()
                selected_date = None
                
                # Get date if daily period
                if period == 'daily':
                    if CALENDAR_AVAILABLE and cal_widget:
                        selected_date = cal_widget.get_date()
                    elif date_entry:
                        selected_date = date_entry.get()
                    else:
                        selected_date = datetime.now().strftime('%Y-%m-%d')
                
                dialog.destroy()
                self.generate_print_summary(symbol, period, selected_date)
            
            btn_frame = tk.Frame(frame, bg=self.colors['bg_card'])
            btn_frame.pack(pady=15)
            
            ModernButton(btn_frame, text="✓ طباعة",
                        command=do_print,
                        bg=self.colors['accent_green'], fg='black',
                        font=('Arial', 10, 'bold'),
                        relief='raised', bd=2, padx=30, pady=8,
                        cursor='hand2').pack(side='left', padx=5)
            
            ModernButton(btn_frame, text="✗ إلغاء",
                        command=dialog.destroy,
                        bg=self.colors['accent_red'], fg='white',
                        font=('Arial', 10, 'bold'),
                        relief='raised', bd=2, padx=30, pady=8,
                        cursor='hand2').pack(side='left', padx=5)
            
        except Exception as e:
            logger.error(f"Error in print_summary: {e}")
            self.show_auto_close_message("خطأ", f"حدث خطأ: {str(e)}", 'error', 3)
    
    def generate_print_summary(self, symbol, period='daily', selected_date=None):
        """Generate and display print summary for a specific symbol using HTML
        
        Args:
            symbol: Symbol to generate report for
            period: 'daily', 'weekly', or 'monthly'
            selected_date: Date string in YYYY-MM-DD format (for daily reports)
        """
        try:
            import webbrowser
            import os
            
            # Get channel info from database
            channel = self.db.get_telegram_channel_by_symbol(symbol)
            if not channel:
                self.show_auto_close_message("تحذير", f"لا توجد قناة مسجلة لـ {symbol}!", 'warning', 3)
                return
            
            channel_name = channel.get('channel_name', f'{symbol} Channel')
            channel_link = channel.get('channel_link', 'N/A')
            
            # Calculate date range based on period
            if period == 'daily':
                # Use selected date or today
                if selected_date:
                    try:
                        target_date = datetime.strptime(selected_date, '%Y-%m-%d')
                    except:
                        target_date = datetime.now()
                else:
                    target_date = datetime.now()
                
                start_date = target_date.strftime('%Y-%m-%d')
                end_date = (target_date + timedelta(days=1)).strftime('%Y-%m-%d')
                period_text = f"تقرير يومي - {target_date.strftime('%d/%m/%Y')}"
                
            elif period == 'weekly':
                # Last 7 days (including today)
                now = datetime.now()
                start_date = now - timedelta(days=7)
                end_date = now + timedelta(days=1)  # Include today by adding 1 day
                period_text = f"تقرير أسبوعي ({start_date.strftime('%d/%m')} - {now.strftime('%d/%m/%Y')})"
                start_date = start_date.strftime('%Y-%m-%d')
                end_date = end_date.strftime('%Y-%m-%d')
                
            elif period == 'monthly':
                # Last 30 days (including today)
                now = datetime.now()
                start_date = now - timedelta(days=30)
                end_date = now + timedelta(days=1)  # Include today by adding 1 day
                period_text = f"تقرير شهري ({start_date.strftime('%d/%m')} - {now.strftime('%d/%m/%Y')})"
                start_date = start_date.strftime('%Y-%m-%d')
                end_date = end_date.strftime('%Y-%m-%d')
            else:
                # Default to today
                start_date = datetime.now().strftime('%Y-%m-%d')
                end_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                period_text = "تقرير يومي"
            
            # Get trades for this symbol within date range
            all_closed_trades = self.db.get_closed_trades(symbol=symbol)
            
            # Filter trades by date range
            closed_trades = []
            for trade in all_closed_trades:
                exit_time = trade.get('exit_time', '')
                if exit_time:
                    # Extract date part (YYYY-MM-DD)
                    trade_date = exit_time.split(' ')[0] if ' ' in exit_time else exit_time
                    
                    if start_date <= trade_date < end_date:
                        closed_trades.append(trade)
            
            # Check if no trades found
            if len(closed_trades) == 0:
                self.show_auto_close_message(
                    "لا توجد بيانات",
                    f"❌ لا توجد صفقات مغلقة لـ {symbol}\nفي الفترة المحددة: {period_text}",
                    'warning', 3
                )
                return
            
            # Calculate totals and statistics
            total_profit = 0
            total_loss = 0
            winning_trades = 0
            losing_trades = 0
            trades_rows_html = []
            
            for idx, trade in enumerate(closed_trades, 1):
                entry_price = trade.get('entry_price', 0)
                highest_price = trade.get('highest_price', 0)
                option_contract = trade.get('option_contract', 'N/A')
                trade_type = trade.get('trade_type', 'N/A')
                
                # Extract strike price using helper function
                strike_price = self.format_strike_only(option_contract)
                
                # Calculate profit in USD
                profit_usd = (highest_price - entry_price) * 100
                
                if profit_usd >= 100:
                    profit_display = f"${profit_usd:.2f}"
                    loss_display = "$0.00"
                    total_profit += profit_usd
                    winning_trades += 1
                else:
                    # Record entry price multiplied by 100 as loss
                    profit_display = "$0.00"
                    loss_display = f"${entry_price * 100:.2f}"
                    total_loss += entry_price * 100
                    losing_trades += 1
                
                # Decorate type with icon + color tag
                display_type = '🟢 CALL' if trade_type == 'CALL' else '🔴 PUT'
                tag_class = 'tag-green' if trade_type == 'CALL' else 'tag-red'

                # Create HTML table row (# | نوع الصفقة | السترايك | سعر الدخول | أعلى سعر | الخسارة | الربح)
                row_html = f"""
                <div class="table-row">
                    <div>{idx}</div>
                    <div><span class="tag {tag_class}">{display_type}</span></div>
                    <div>{strike_price}</div>
                    <div>${entry_price:.2f}</div>
                    <div>${highest_price:.2f}</div>
                    <div>{loss_display}</div>
                    <div>{profit_display}</div>
                </div>
                """
                trades_rows_html.append(row_html)
            
            total_trades = len(closed_trades)
            success_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            net_profit = total_profit - total_loss
            
            # Read HTML template
            template_path = os.path.join(os.path.dirname(__file__), 'print_template.html')
            with open(template_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Get current date in Arabic
            months = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
                     'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
            days = ['الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
            now = datetime.now()
            date_str = f"{days[now.weekday()]}، {now.day} {months[now.month-1]} {now.year}"
            
            # Replace placeholders
            replacements = {
                '{symbol}': symbol,
                '{channel_name}': channel_name,
                '{period_text}': period_text,
                '{date_str}': date_str,
                '{channel_link}': channel_link,
                '{total_trades}': str(total_trades),
                '{winning_trades}': str(winning_trades),
                '{losing_trades}': str(losing_trades),
                '{table_rows}': ''.join(trades_rows_html),
                '{net_profit}': f"{net_profit:.2f}",
                '{total_loss}': f"{abs(total_loss):.2f}",
                '{total_profit}': f"{total_profit:.2f}"
            }
            
            for placeholder, value in replacements.items():
                html_content = html_content.replace(placeholder, value)
            
            # Save HTML file
            output_path = os.path.join(os.path.dirname(__file__), f'print_summary_{symbol}.html')
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Open in browser
            webbrowser.open('file://' + output_path)
            
            self.show_auto_close_message("تم", f"تم فتح التقرير في المتصفح!\n\nيمكنك الطباعة باستخدام Ctrl+P", 'info', 3)
            
        except Exception as e:
            logger.error(f"Error generating print summary: {e}")
            self.show_auto_close_message("خطأ", f"حدث خطأ: {str(e)}", 'error', 3)
    
    def clear_trade_history(self):
        """Clear all closed trades from history"""
        try:
            # Confirm deletion
            result = messagebox.askyesno(
                "تأكيد المسح",
                "⚠️ هل تريد حذف جميع الصفقات المغلقة من السجل؟\n\n"
                "هذا الإجراء لا يمكن التراجع عنه!\n\n"
                "سيتم حذف:\n"
                "• جميع الصفقات المغلقة\n"
                "• سجل التتبع المرتبط بها\n"
                "• البيانات التاريخية",
                icon='warning'
            )
            
            if not result:
                return
            
            # Double confirmation
            confirm = messagebox.askyesno(
                "تأكيد نهائي",
                "🚨 هل أنت متأكد تماماً؟\n\n"
                "سيتم حذف جميع البيانات التاريخية!",
                icon='warning'
            )
            
            if not confirm:
                return
            
            # Delete from database
            deleted_count = self.db.clear_closed_trades()
            
            # Update display
            self.update_trades_history()
            
            logger.info(f"✅ Cleared {deleted_count} closed trades from history")
            self.show_auto_close_message(
                "تم المسح",
                f"✅ تم حذف {deleted_count} صفقة من السجل بنجاح!",
                'info', 3
            )
            
        except Exception as e:
            logger.error(f"Error clearing trade history: {e}")
            self.show_auto_close_message("خطأ", f"فشل حذف السجل:\n{str(e)}", 'error', 3)
    
    def cleanup_contracts(self):
        """Cleanup old contracts"""
        # Implementation
        pass
    
    def open_manual_trade(self, symbol, trade_type):
        """
        Open manual trade - DIRECT MODE (لا يعتمد على جدول Watchlist)
        
        الآلية الجديدة:
        1. يجلب السعر الحالي من IBKR
        2. يجلب العقود مباشرة (دفعات من 5)
        3. يختار العقد الأفضل ضمن نطاق الدخول
        4. يؤكد السعر من IBKR
        5. يدخل الصفقة
        """
        logger.info(f"🎯 Manual trade triggered (DIRECT MODE): {symbol} {trade_type}")
        
        # Check system is running
        if not self.system_running:
            self.show_auto_close_message("خطأ", "النظام غير مشغل!\nالرجاء تشغيل النظام أولاً.", 'error', 3)
            return
        
        # Check simple_watchlist is available
        if not self.simple_watchlist or not self.simple_watchlist.data_connection:
            self.show_auto_close_message("خطأ", "اتصال IBKR غير متاح!\nالرجاء التحقق من الاتصال.", 'error', 3)
            return
        
        logger.info(f"🚀 Fetching contracts DIRECTLY from IBKR for {symbol} {trade_type}...")
        
        # Execute trade with direct fetch from IBKR
        self._execute_manual_trade_direct(symbol, trade_type)
    
    def trigger_manual_button(self, symbol, signal_type, quantity=None):
        """Trigger manual button from TradingView webhook - called from webhook thread"""
        logger.info(f"📡 Webhook triggering manual button: {symbol} {signal_type}")
        if quantity:
            logger.info(f"📦 Setting contract quantity to: {quantity}")
        
        # Register signal in database for counter tracking
        try:
            signal_id = self.db.add_signal(symbol, signal_type)
            logger.info(f"✅ Signal #{signal_id} registered: {signal_type} {symbol}")
            
            # Update signal counter display immediately (thread-safe)
            self.root.after(0, self._update_signal_counter_immediate)
        except Exception as e:
            logger.error(f"❌ Failed to register signal: {e}")
        
        # Set quantity before opening trade (if provided)
        if quantity and quantity > 0:
            self.root.after(0, lambda: self._set_quantity_and_open_trade(symbol, signal_type, quantity))
        else:
            # Use current default quantity
            self.root.after(0, lambda: self.open_manual_trade(symbol, signal_type))
    
    def _update_signal_counter_immediate(self):
        """Update signal counter display immediately after receiving webhook"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            counts = self.db.get_signal_count(today)
            
            self.signals_labels['CALL'].config(text=str(counts['CALL']))
            self.signals_labels['PUT'].config(text=str(counts['PUT']))
            self.signals_labels['إجمالي'].config(text=str(counts['total']))
            
            logger.info(f"📊 Signal counters updated: CALL={counts['CALL']}, PUT={counts['PUT']}, Total={counts['total']}")
        except Exception as e:
            logger.error(f"Error updating signal counter: {e}")
    
    def _set_quantity_and_open_trade(self, symbol, signal_type, quantity):
        """Helper: Set quantity then open trade"""
        # Temporarily set the contract quantity
        old_quantity = self.current_contract_quantity
        self.current_contract_quantity = quantity
        logger.info(f"📦 Temporarily set quantity from {old_quantity} to {quantity} for webhook trade")
        
        # Open the trade
        self.open_manual_trade(symbol, signal_type)
        
        # Restore original quantity after trade opens
        # (scheduled slightly later to ensure trade creation uses new quantity)
        self.root.after(100, lambda: self._restore_quantity(old_quantity))
    
    def _restore_quantity(self, old_quantity):
        """Restore previous quantity setting"""
        self.current_contract_quantity = old_quantity
        logger.info(f"📦 Restored contract quantity to {old_quantity}")
    
    def _execute_manual_trade_direct(self, symbol, trade_type):
        """
        🚀 DIRECT MODE: Execute manual trade by fetching contracts directly from IBKR
        (لا يعتمد على جدول Watchlist)
        """
        try:
            import asyncio
            
            logger.info(f"{'='*60}")
            logger.info(f"🚀 DIRECT TRADE EXECUTION: {symbol} {trade_type}")
            logger.info(f"{'='*60}")
            
            # ═══════════════════════════════════════════════════════════════
            # DUPLICATE PREVENTION CHECK #1: Profit Target
            # ═══════════════════════════════════════════════════════════════
            if self.system_running and self.trading_system:
                logger.info(f"🔍 Checking profit target for manual {trade_type} trade...")
                
                target_met, reason = self.trading_system._check_profit_target_met(
                    trade_type, symbol, config.MIN_PROFIT_TARGET
                )
                
                if not target_met:
                    logger.warning(f"❌ MANUAL TRADE REJECTED: {reason}")
                    duplicate_data = self.trading_system.get_profit_target_blocking_trade(trade_type, symbol)
                    if duplicate_data:
                        self.telegram.send_notification_sync('duplicate_prevented', duplicate_data, symbol, self.async_loop)
                    return
            
            # ═══════════════════════════════════════════════════════════════
            # 📢 INSTANT TELEGRAM NOTIFICATION (بعد نجاح فحص العقود!)
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"📢 Sending instant Telegram notification...")
            try:
                type_ar = 'كول' if trade_type == 'CALL' else 'بوت'
                notification_data = {
                    'type': trade_type,
                    'type_ar': type_ar
                }
                self.telegram.send_notification_sync('trade_preparing', notification_data, symbol, self.async_loop)
                logger.info(f"✅ Instant notification sent to Telegram")
            except Exception as e:
                logger.error(f"⚠️ Failed to send instant notification: {e}")
            
            # ═══════════════════════════════════════════════════════════════
            # � GET DEDICATED IBKR CONNECTION (الاتصالات المفتوحة!)
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"🔌 Getting dedicated IBKR connection for {symbol}...")
            
            ibkr_conn = None
            if hasattr(self.trading_system, 'ibkr_connections') and symbol in self.trading_system.ibkr_connections:
                ibkr_conn = self.trading_system.ibkr_connections[symbol]
                logger.info(f"✅ Using dedicated connection for {symbol}")
            else:
                ibkr_conn = getattr(self.trading_system, 'ibkr', None)
                logger.info(f"✅ Using main IBKR connection")
            
            if not ibkr_conn:
                self.show_auto_close_message("خطأ", "اتصال IBKR غير متاح", 'error', 3)
                return
            
            # ═══════════════════════════════════════════════════════════════
            # 🔥 STEP 1: Get current price from IBKR (باستخدام الاتصال المفتوح!)
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"📊 Step 1: Getting current {symbol} price from dedicated connection...")
            
            def get_price():
                future = asyncio.run_coroutine_threadsafe(
                    ibkr_conn.get_underlying_price(symbol),
                    self.async_loop
                )
                return future.result(timeout=10)
            
            current_price = get_price()
            if not current_price or current_price <= 0:
                self.show_auto_close_message("خطأ", f"فشل الحصول على سعر {symbol}", 'error', 3)
                return
            
            logger.info(f"✅ Current {symbol} price: ${current_price:.2f}")
            
            # ═══════════════════════════════════════════════════════════════
            # 🔥 STEP 2: Get expiry date (0DTE)
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"📅 Step 2: Getting 0DTE expiry...")
            
            def get_expiry():
                future = asyncio.run_coroutine_threadsafe(
                    ibkr_conn.get_expiry_date(),
                    self.async_loop
                )
                return future.result(timeout=10)
            
            expiry = get_expiry()
            logger.info(f"✅ Using expiry: {expiry}")
            
            # ═══════════════════════════════════════════════════════════════
            # 🔥 STEP 3: Fetch contracts FAST (20 contracts in single batch)
            # نفس طريقة السكربت القديم للسرعة!
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"🔍 Step 3: Fetching {trade_type} contracts (FAST MODE - 20 contracts, single batch)...")
            logger.info(f"   Entry range (من الواجهة): ${config.ENTRY_RANGE_MIN:.2f} - ${config.ENTRY_RANGE_MAX:.2f}")
            
            def fetch_contracts_fast():
                """
                جلب العقود بطريقة السكربت القديم:
                - 20 عقد فقط
                - دفعة واحدة (qualifyContractsAsync)
                - انتظار 2 ثانية فقط
                - سرعة عالية جداً! ⚡
                """
                async def fetch_batch():
                    try:
                        # Get underlying price
                        underlying_price = await ibkr_conn.get_underlying_price(symbol)
                        if not underlying_price:
                            logger.error("❌ Could not get underlying price")
                            return []
                        
                        logger.info(f"✅ Underlying price: ${underlying_price:.2f}")
                        
                        # Calculate strike range (same as old script)
                        strike_interval = config.STRIKE_INTERVALS.get(symbol, 5)
                        underlying_rounded = round(underlying_price / strike_interval) * strike_interval
                        
                        # Generate 20 strikes based on option type
                        if trade_type == 'CALL':
                            # CALL: start from ATM and go UP (OTM)
                            start_strike = underlying_rounded
                            strikes = [start_strike + (i * strike_interval) for i in range(20)]
                        else:
                            # PUT: start from ATM and go DOWN (OTM)
                            start_strike = underlying_rounded
                            strikes = [start_strike - (i * strike_interval) for i in range(20)]
                        
                        logger.info(f"🎯 {trade_type}: Checking strikes {strikes[0]} to {strikes[-1]} (20 contracts)")
                        
                        # Create Option contracts
                        from ib_insync import Option
                        right = 'C' if trade_type == 'CALL' else 'P'
                        
                        if symbol == 'SPX':
                            exchange = 'CBOE'
                            trading_class = 'SPXW'
                        elif symbol == 'NDX':
                            exchange = 'CBOE'
                            trading_class = 'NDXP'
                        else:
                            exchange = 'SMART'
                            trading_class = symbol
                        
                        batch_options = [
                            Option(symbol, expiry, strike, right, exchange, tradingClass=trading_class)
                            for strike in strikes
                        ]
                        
                        # ⚡ Qualify all contracts at once (FAST!)
                        logger.info(f"⚡ Qualifying {len(batch_options)} contracts in single batch...")
                        qualified_contracts = await ibkr_conn.ib.qualifyContractsAsync(*batch_options)
                        
                        # Request market data for all
                        strike_ticker_map = {}
                        for i, contract in enumerate(qualified_contracts):
                            if contract and contract.conId:
                                ticker = ibkr_conn.ib.reqMktData(contract)
                                strike_ticker_map[strikes[i]] = (contract, ticker)
                        
                        logger.info(f"⏰ Waiting 2 seconds for market data...")
                        # ⚡ Wait only 2 seconds (FAST!)
                        await asyncio.sleep(2.0)
                        
                        # Extract prices and filter by ENTRY range
                        contracts = []
                        for strike, (contract, ticker) in strike_ticker_map.items():
                            bid = ticker.bid if ticker.bid and ticker.bid > 0 else 0
                            ask = ticker.ask if ticker.ask and ticker.ask > 0 else 0
                            
                            # Cancel market data immediately
                            ibkr_conn.ib.cancelMktData(contract)
                            
                            if ask > 0:
                                status = "✓" if config.ENTRY_RANGE_MIN <= ask <= config.ENTRY_RANGE_MAX else "✗"
                                logger.info(f"  {status} Strike {strike}: Bid ${bid:.2f}, Ask ${ask:.2f}")
                                
                                if config.ENTRY_RANGE_MIN <= ask <= config.ENTRY_RANGE_MAX:
                                    # Get contract details from IBKR structure
                                    contracts.append({
                                        'contract': contract,
                                        'strike': strike,
                                        'bid': bid,
                                        'ask': ask
                                    })
                        
                        logger.info(f"✅ Found {len(contracts)} contracts in ENTRY range")
                        return contracts
                        
                    except Exception as e:
                        logger.error(f"❌ Error in fast fetch: {e}")
                        import traceback
                        traceback.print_exc()
                        return []
                
                # Execute async fetch
                future = asyncio.run_coroutine_threadsafe(
                    fetch_batch(),
                    self.async_loop
                )
                return future.result(timeout=15)  # 15 seconds max
            
            contracts = fetch_contracts_fast()
            
            # 🔄 Retry logic: إعادة المحاولة مرة واحدة بعد ثانية (بدون رسائل)
            if not contracts:
                logger.warning(f"⚠️ No contracts found in first attempt - retrying after 1 second...")
                time.sleep(1)  # انتظار ثانية
                contracts = fetch_contracts_fast()  # المحاولة الثانية
                
                if not contracts:
                    # فشلت المحاولتين - إظهار رسالة الخطأ
                    logger.error(f"❌ No contracts found after 2 attempts")
                    self.show_auto_close_message(
                        "خطأ", 
                        f"لم يتم العثور على عقود {trade_type} ضمن نطاق الدخول!\n\n"
                        f"تم البحث في 20 عقد (FAST MODE)\n"
                        f"نطاق الدخول (من الواجهة): ${config.ENTRY_RANGE_MIN:.2f} - ${config.ENTRY_RANGE_MAX:.2f}",
                        'error', 
                        4
                    )
                    return
                else:
                    # نجحت المحاولة الثانية - متابعة بدون رسالة
                    logger.info(f"✅ Retry successful - found {len(contracts)} contracts in second attempt")
            
            logger.info(f"✅ Found {len(contracts)} contracts in ENTRY range")
            
            # Select best contract (highest bid)
            best_contract = max(contracts, key=lambda x: x.get('bid', 0))
            strike = best_contract['strike']
            bid = best_contract['bid']
            ask = best_contract['ask']
            
            logger.info(f"✅ Selected best contract: Strike {strike}, Bid ${bid:.2f}, Ask ${ask:.2f}")
            logger.info(f"⚡ FAST MODE: Entering trade immediately without confirmation (like old script)")
            
            # Use Ask price as entry price (no confirmation needed - FAST!)
            entry_price = ask
            highest_bid = bid
            highest_ask = ask
            
            # ═══════════════════════════════════════════════════════════════
            # ✅ DUPLICATE PREVENTION CHECK #2: REMOVED
            # السماح بفتح نفس Strike عدة مرات - كل واحدة trade منفصل!
            # Scenario: Strike حقق $2.00 ثم رجع لسعر الدخول → نفتح صفقة جديدة
            # ═══════════════════════════════════════════════════════════════
            if self.system_running and self.trading_system:
                existing_strikes = [
                    t['strike_price'] for t in self.trading_system.db.get_active_trades(symbol)
                    if t['trade_type'] == trade_type
                ]
                if strike in existing_strikes:
                    logger.info(f"ℹ️ Strike {strike} already has active trade(s), but allowing new entry (separate tracking)")
            
            # ═══════════════════════════════════════════════════════════════
            # 🔥 STEP 4: Create trade and start tracking (NEW INSTANCE)
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"✅ All checks passed - creating trade...")
            
            contract_name = f"{symbol} {strike} {trade_type}"
            
            try:
                expiry_dt = datetime.strptime(expiry, '%Y%m%d')
                expiry_formatted = expiry_dt.strftime('%d%b%y').upper()
            except:
                expiry_formatted = datetime.now().strftime('%d%b%y').upper()
            
            # Create trade in database
            trade_id = self.db.create_trade(
                symbol=symbol,
                trade_type=trade_type,
                option_contract=contract_name,
                strike_price=float(strike),
                entry_price=entry_price,
                expiry=expiry_formatted,
                bid=highest_bid,
                ask=highest_ask,
                quantity=self.current_contract_quantity
            )
            
            logger.info(f"✅ Trade #{trade_id} created: {contract_name} @ ${entry_price:.2f} (DIRECT MODE)")
            
            # ═══════════════════════════════════════════════════════════════
            # 🔥 STEP 5: Start INDEPENDENT tracking first, then send notification
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"🔄 Starting independent tracking for trade #{trade_id}...")
            tracking_started = self._start_independent_tracking(
                trade_id=trade_id,
                symbol=symbol,
                strike=float(strike),
                trade_type=trade_type,
                entry_price=entry_price,
                expiry_date=expiry
            )
            
            # Check tracking status
            if tracking_started is True:
                # ✅ التتبع بدأ بنجاح - إرسال إشعار
                logger.info(f"✅ Tracking confirmed for trade #{trade_id} - sending notification...")
                
                # Send telegram notification
                channel_link = 'https://t.me/channel'
                if self.telegram and symbol in self.telegram.channels:
                    if self.telegram.channels[symbol]:
                        channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
                
                emoji = '📈' if trade_type == 'CALL' else '📉'
                notification_data = {
                    'symbol': symbol,
                    'type': trade_type,
                    'contract': contract_name,
                    'strike': strike,
                    'entry_price': entry_price,
                    'current_price': entry_price,
                    'bid': highest_bid,
                    'ask': highest_ask,
                    'confirmed_from_ibkr': True,
                    'expiry': expiry_formatted,
                    'emoji': emoji,
                    'channel_link': channel_link,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                self.telegram.send_notification_sync('position_opened', notification_data, symbol, self.async_loop)
                logger.info(f"✅ Notification sent for trade #{trade_id}")
                
            elif tracking_started is False:
                # ❌ التتبع فشل بشكل نهائي
                logger.error(f"❌ Tracking failed for trade #{trade_id} - deleting trade")
                self.db.delete_trade(trade_id)
                self.show_auto_close_message(
                    "خطأ في التتبع", 
                    f"فشل بدء التتبع للصفقة!\n\n"
                    f"تم حذف الصفقة من قاعدة البيانات.\n"
                    f"يرجى المحاولة مرة أخرى.",
                    'error', 
                    3
                )
                return
            else:
                # ⏰ Timeout - لا يزال يحاول في الخلفية
                logger.warning(f"⚠️ Tracking timeout for trade #{trade_id} - sending notification anyway")
                
                # إرسال إشعار على أي حال (قد ينجح التتبع لاحقاً)
                channel_link = 'https://t.me/channel'
                if self.telegram and symbol in self.telegram.channels:
                    if self.telegram.channels[symbol]:
                        channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
                
                emoji = '📈' if trade_type == 'CALL' else '📉'
                notification_data = {
                    'symbol': symbol,
                    'type': trade_type,
                    'contract': contract_name,
                    'strike': strike,
                    'entry_price': entry_price,
                    'current_price': entry_price,
                    'bid': highest_bid,
                    'ask': highest_ask,
                    'confirmed_from_ibkr': True,
                    'expiry': expiry_formatted,
                    'emoji': emoji,
                    'channel_link': channel_link,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                self.telegram.send_notification_sync('position_opened', notification_data, symbol, self.async_loop)
                logger.warning(f"⚠️ Notification sent for trade #{trade_id} (tracking still connecting)")
            
            logger.info(f"✅ Independent tracking started for new trade #{trade_id}")
            
            # Refresh active trades
            self.update_active_trades()
            
            logger.info(f"{'='*60}")
            logger.info(f"✅ DIRECT TRADE COMPLETED: {contract_name} @ ${entry_price:.2f}")
            logger.info(f"{'='*60}")
            
        except Exception as e:
            logger.error(f"❌ Error in direct trade execution: {e}")
            import traceback
            traceback.print_exc()
            self.show_auto_close_message("خطأ", f"فشل تنفيذ الصفقة:\n{str(e)}", 'error', 3)
    
    def _execute_manual_trade_from_range(self, symbol, trade_type, tree):
        """Execute manual trade automatically from price range (no dialog)"""
        try:
            # ═══════════════════════════════════════════════════════════════
            # DUPLICATE PREVENTION CHECK #1: Profit Target
            # ═══════════════════════════════════════════════════════════════
            if self.system_running and self.trading_system:
                logger.info(f"🔍 Checking profit target for manual {trade_type} trade...")
                
                target_met, reason = self.trading_system._check_profit_target_met(
                    trade_type, symbol, config.MIN_PROFIT_TARGET
                )
                
                if not target_met:
                    logger.warning(f"❌ MANUAL TRADE REJECTED: {reason}")
                    
                    # Get data of blocking trade for notification with image
                    duplicate_data = self.trading_system.get_profit_target_blocking_trade(trade_type, symbol)
                    
                    if duplicate_data:
                        self.telegram.send_notification_sync('duplicate_prevented', duplicate_data, symbol, self.async_loop)
                    return
                
                logger.info(f"✅ Profit target check passed: {reason}")
            
            # Get best contract from watchlist tree (show dialogs for manual trading)
            contract_data = self._get_best_contract_from_tree(symbol, trade_type, tree, show_dialogs=True)
            
            if not contract_data:
                return  # Error already shown
            
            strike = contract_data['strike']
            bid = contract_data['bid']
            ask = contract_data['ask']
            entry_price = contract_data['entry_price']
            confirmed_from_ibkr = contract_data.get('confirmed_from_ibkr', False)
            
            # Log price confirmation status
            if confirmed_from_ibkr:
                logger.info(f"✅ Using CONFIRMED real-time price from IBKR: ${entry_price:.2f}")
            else:
                logger.warning(f"⚠️ Using table price (IBKR confirmation failed): ${entry_price:.2f}")
            
            # ═══════════════════════════════════════════════════════════════
            # ═══════════════════════════════════════════════════════════════
            # ✅ DUPLICATE PREVENTION CHECK #2: REMOVED
            # السماح بفتح نفس Strike عدة مرات - كل واحدة trade منفصل!
            # ═══════════════════════════════════════════════════════════════
            if self.system_running and self.trading_system:
                existing_strikes = [
                    t['strike_price'] for t in self.trading_system.db.get_active_trades(symbol)
                    if t['trade_type'] == trade_type
                ]
                if strike in existing_strikes:
                    logger.info(f"ℹ️ Strike {strike} already has active trade(s), but allowing new entry (separate tracking)")
            
            # Execute trade immediately
            contract_name = f"{symbol} {strike} {trade_type}"
            
            # Get expiry date for notification and database
            expiry_date = self.selected_expiry_dates.get(symbol, None)
            if expiry_date is None:
                # Use today's date (0DTE)
                expiry_date = datetime.now().strftime('%Y%m%d')
            
            # Format expiry for display (convert from YYYYMMDD to DD MMM YY)
            try:
                from datetime import datetime as dt
                expiry_dt = dt.strptime(expiry_date, '%Y%m%d')
                expiry_formatted = expiry_dt.strftime('%d%b%y').upper()
            except:
                expiry_formatted = datetime.now().strftime('%d%b%y').upper()
            
            # Create trade in database with quantity
            trade_id = self.db.create_trade(
                symbol=symbol,
                trade_type=trade_type,
                option_contract=contract_name,
                strike_price=float(strike),
                entry_price=entry_price,
                expiry=expiry_formatted,
                bid=bid,
                ask=ask,
                quantity=self.current_contract_quantity
            )
            
            logger.info(f"✅ Created trade #{trade_id}: {contract_name} (Quantity: {self.current_contract_quantity})")
            
            # Get channel link for this symbol
            channel_link = 'https://t.me/channel'  # Default
            if self.telegram and symbol in self.telegram.channels:
                if self.telegram.channels[symbol]:
                    channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
            
            # Determine emoji based on trade type
            emoji = '📈' if trade_type == 'CALL' else '📉'
            
            # Send telegram notification
            notification_data = {
                'symbol': symbol,
                'type': trade_type,
                'contract': contract_name,
                'strike': strike,
                'entry_price': entry_price,
                'current_price': entry_price,  # Initial price = entry price
                'bid': bid,
                'ask': ask,
                'confirmed_from_ibkr': confirmed_from_ibkr,  # Price confirmation status
                'expiry': expiry_formatted,  # Add expiry date
                'emoji': emoji,  # Add emoji
                'channel_link': channel_link,  # Add channel link
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Debug: Print data types being sent
            logger.info(f"📤 Sending position_opened notification:")
            logger.info(f"   symbol: {symbol} ({type(symbol).__name__})")
            logger.info(f"   type: {trade_type} ({type(trade_type).__name__})")
            logger.info(f"   contract: {contract_name} ({type(contract_name).__name__})")
            logger.info(f"   strike: {strike} ({type(strike).__name__})")
            logger.info(f"   entry_price: {entry_price} ({type(entry_price).__name__})")
            logger.info(f"   current_price: {entry_price} ({type(entry_price).__name__})")
            logger.info(f"   bid: {bid} ({type(bid).__name__})")
            logger.info(f"   ask: {ask} ({type(ask).__name__})")
            logger.info(f"   expiry: {expiry_formatted} ({type(expiry_formatted).__name__})")
            
            # Send telegram notification with async_loop for proper threading
            self.telegram.send_notification_sync('position_opened', notification_data, symbol, self.async_loop)
            
            logger.info(f"✅ Manual {trade_type} executed: {contract_name} @ ${entry_price:.2f}")
            
            # Start tracking using trading_system (NOT the old GUI-based tracking)
            expiry_date = self.selected_expiry_dates.get(symbol, None)
            if expiry_date is None:
                # Use today's date (0DTE)
                expiry_date = datetime.now().strftime('%Y%m%d')
            
            # Try to get pre-qualified contract from watchlist cache
            qualified_contract = None
            if symbol in self.watchlist_contracts:
                if trade_type in self.watchlist_contracts[symbol]:
                    # Search in list of contracts for matching strike
                    contracts_list = self.watchlist_contracts[symbol][trade_type]
                    for contract_data in contracts_list:
                        if abs(contract_data.get('strike', 0) - float(strike)) < 0.01:  # Match strike
                            qualified_contract = contract_data.get('contract')
                            if qualified_contract:
                                logger.info(f"✅ Found pre-qualified contract in watchlist for Strike {strike}")
                            break
                    
                    if not qualified_contract:
                        logger.warning(f"⚠️ Strike {strike} not found in cached contracts - will attempt qualification")
            
            logger.info(f"🔄 Starting tracking for manual trade #{trade_id} via trading_system")
            
            # Schedule tracking in trading system's event loop
            if self.async_loop and self.system_running:
                future = asyncio.run_coroutine_threadsafe(
                    self.trading_system.start_tracking_manual_trade(
                        trade_id=trade_id,
                        symbol=symbol,
                        strike=float(strike),
                        option_type=trade_type,
                        entry_price=entry_price,
                        expiry_date=expiry_date,
                        qualified_contract=qualified_contract  # Pass pre-qualified contract (works 24/7)
                    ),
                    self.async_loop
                )
                
                # Wait for result (with timeout)
                try:
                    success = future.result(timeout=5)
                    if success:
                        logger.info(f"✅ Tracking started successfully for trade #{trade_id}")
                        if qualified_contract:
                            tracking_msg = "🔄 بدء التتبع باستخدام العقد المخزن (يعمل 24/7)"
                        else:
                            tracking_msg = "🔄 بدء التتبع التلقائي عبر النظام الرئيسي"
                    else:
                        logger.error(f"❌ Failed to start tracking for trade #{trade_id}")
                        tracking_msg = "⚠️ فشل بدء التتبع - تحقق من اتصال IBKR"
                except Exception as e:
                    logger.error(f"❌ Error scheduling tracking: {e}")
                    tracking_msg = f"⚠️ خطأ في بدء التتبع: {str(e)}"
            else:
                logger.warning("⚠️ Trading system not running - cannot start tracking")
                tracking_msg = "⚠️ النظام غير مشغل - لا يمكن التتبع"
            
            # Log success (no popup)
            logger.info(f"✅ Trade executed: {trade_type} {symbol} @ ${entry_price:.2f} - {tracking_msg}")
            
            # Refresh active trades
            self.update_active_trades()
            
        except Exception as e:
            logger.error(f"Error executing manual trade: {e}")
            import traceback
            traceback.print_exc()
            self.show_auto_close_message("خطأ", f"فشل تنفيذ الصفقة:\n{str(e)}", 'error', 3)
    
    def _confirm_contract_price_from_ibkr(self, symbol: str, trade_type: str, strike: float, ibkr_conn=None) -> dict:
        """
        🔥 Confirm real-time contract price directly from IBKR before entering trade
        Uses dedicated connection for the symbol
        
        Args:
            symbol: Symbol (SPX, SPY, NDX, QQQ)
            trade_type: CALL or PUT
            strike: Strike price to confirm
            ibkr_conn: Dedicated IBKR connection for this symbol
        
        Returns:
            dict with confirmed bid/ask or None if failed
        """
        try:
            import asyncio
            from ib_insync import Option
            
            logger.info(f"🔄 Requesting real-time price confirmation from dedicated connection...")
            logger.info(f"   Symbol: {symbol}, Type: {trade_type}, Strike: {strike}")
            
            # Check if connection is available
            if not ibkr_conn:
                logger.warning("⚠️ No dedicated connection provided")
                return None
            
            if not ibkr_conn.ib.isConnected():
                logger.warning("⚠️ Dedicated connection is not connected")
                return None
            
            # Get expiry date for the contract
            expiry_date = self.selected_expiry_dates.get(symbol, None)
            if expiry_date is None:
                # Use today's date (0DTE)
                expiry_date = datetime.now().strftime('%Y%m%d')
            
            logger.info(f"   Expiry: {expiry_date}")
            
            # Create contract with correct exchange/trading class per symbol
            right = 'C' if trade_type == 'CALL' else 'P'
            
            if symbol == 'SPX':
                exchange = 'CBOE'
                trading_class = 'SPXW'
            elif symbol == 'NDX':
                exchange = 'CBOE'
                trading_class = 'NDXP'
            else:
                exchange = 'SMART'
                trading_class = symbol
            
            contract = Option(
                symbol=symbol,
                lastTradeDateOrContractMonth=expiry_date,
                strike=strike,
                right=right,
                exchange=exchange,
                tradingClass=trading_class
            )
            
            # Request real-time data from IBKR using dedicated connection
            async def get_real_time_price():
                try:
                    # Qualify contract
                    qualified = await ibkr_conn.ib.qualifyContractsAsync(contract)
                    
                    if not qualified or not qualified[0].conId:
                        logger.error(f"❌ Contract qualification failed for Strike {strike}")
                        return None
                    
                    qualified_contract = qualified[0]
                    logger.info(f"✅ Contract qualified: conId={qualified_contract.conId}")
                    
                    # Request market data (real-time)
                    ticker = ibkr_conn.ib.reqMktData(qualified_contract)
                    
                    # Wait for data (max 1 second for speed)
                    await asyncio.sleep(0.8)
                    
                    # Get prices
                    bid = ticker.bid if ticker.bid and ticker.bid > 0 else 0
                    ask = ticker.ask if ticker.ask and ticker.ask > 0 else 0
                    
                    # Cancel subscription immediately
                    ibkr_conn.ib.cancelMktData(qualified_contract)
                    
                    if bid > 0 and ask > 0:
                        logger.info(f"✅ Real-time prices received: Bid=${bid:.2f}, Ask=${ask:.2f}")
                        return {'bid': bid, 'ask': ask}
                    else:
                        logger.warning(f"⚠️ Invalid prices: Bid=${bid:.2f}, Ask=${ask:.2f}")
                        return None
                        
                except Exception as e:
                    logger.error(f"❌ Error in async price fetch: {e}")
                    return None
            
            # Execute in async loop
            if self.async_loop:
                future = asyncio.run_coroutine_threadsafe(
                    get_real_time_price(),
                    self.async_loop
                )
                result = future.result(timeout=2)  # Max 2 seconds total
                return result
            else:
                logger.warning("⚠️ Async loop not available")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error confirming price from IBKR: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_best_contract_from_tree(self, symbol, trade_type, tree, show_dialogs=True):
        """Get best contract from watchlist tree - SHARED by manual and webhook"""
        try:
            # ✅ Get ENTRY price range from config (للدخول في الصفقات - من الواجهة الرسومية)
            min_price = config.ENTRY_RANGE_MIN  # من نطاق الدخول الفعلي بالواجهة
            max_price = config.ENTRY_RANGE_MAX  # من نطاق الدخول الفعلي بالواجهة
            
            # Get all items from tree
            all_items = tree.get_children()
            
            logger.info(f"🎯 ENTRY MODE: Filtering {trade_type} for {symbol} (Found {len(all_items)} contracts in tree)")
            logger.info(f"📊 Entry price range (من الواجهة): ${min_price:.2f} - ${max_price:.2f} (ENTRY_RANGE)")
            
            if not all_items:
                if show_dialogs:
                    self.show_auto_close_message("خطأ", f"لا توجد عقود متاحة!\nالرجاء تشغيل النظام أولاً.", 'error', 3)
                logger.error(f"No contracts in tree for {symbol} {trade_type}")
                return None
            
            # Filter contracts by price range
            valid_contracts = []
            
            for item in all_items:
                item_data = tree.item(item)
                strike_raw = item_data['text']
                values = item_data['values']
                
                if values and len(values) >= 1:
                    try:
                        # Clean strike: remove $, commas, spaces and convert to float
                        strike_clean = str(strike_raw).replace('$', '').replace(',', '').replace(' ', '').strip()
                        strike = float(strike_clean)
                        
                        bid_str = str(values[0]).replace('$', '').replace(',', '').strip()
                        bid = float(bid_str)
                        ask_str = str(values[1]).replace('$', '').replace(',', '').strip() if len(values) > 1 else bid_str
                        ask = float(ask_str)
                        
                        # ✅ Check if ASK is within ENTRY price range (since we buy at Ask)
                        if min_price <= ask <= max_price:
                            valid_contracts.append({
                                'item': item,
                                'strike': strike,
                                'bid': bid,
                                'ask': ask
                            })
                            logger.debug(f"  ✓ Strike {strike}: Bid ${bid:.2f}, Ask ${ask:.2f} - Ask في نطاق الدخول")
                        else:
                            logger.debug(f"  ✗ Strike {strike}: Ask ${ask:.2f} - خارج نطاق الدخول ({min_price}-{max_price})")
                    except Exception as e:
                        logger.warning(f"Error parsing prices for Strike {strike}: {e}")
                        continue
            
            if not valid_contracts:
                error_msg = (
                    f"لم يتم العثور على عقود ضمن نطاق الدخول الفعلي!\n\n"
                    f"نطاق الدخول الفعلي (من الواجهة): ${min_price:.2f} - ${max_price:.2f}\n"
                    f"عدد العقود الكلي: {len(all_items)}\n\n"
                    f"💡 يمكنك تعديل النطاق من:\n"
                    f"إعدادات النطاق السعري → نطاق الدخول الفعلي 🎯"
                )
                if show_dialogs:
                    self.show_auto_close_message("خطأ", error_msg, 'error', 3)
                logger.error(f"No contracts in entry range for {symbol} {trade_type}: ${min_price}-${max_price}")
                return None
            
            # Find contract with highest bid from valid contracts
            best_contract = max(valid_contracts, key=lambda x: x['bid'])
            initial_bid = best_contract['bid']
            initial_ask = best_contract['ask']
            strike = best_contract['strike']
            
            logger.info(f"✅ Found {len(valid_contracts)} contracts in price range")
            logger.info(f"📊 Initial selection from table: Strike {strike}, Bid ${initial_bid:.2f}, Ask ${initial_ask:.2f}")
            
            # ═══════════════════════════════════════════════════════════════
            # 🔥 REAL-TIME PRICE CONFIRMATION FROM IBKR WITH RETRY + FALLBACK
            # ═══════════════════════════════════════════════════════════════
            confirmed_price = None
            max_retries = 12  # 12 retries × 5 seconds = 60 seconds (1 minute)
            retry_count = 0
            
            logger.info(f"🔄 [Attempt 1/{max_retries}] Confirming real-time price from IBKR for Strike {strike}...")
            
            while retry_count < max_retries and confirmed_price is None:
                confirmed_price = self._confirm_contract_price_from_ibkr(symbol, trade_type, strike)
                
                if confirmed_price:
                    # Success!
                    highest_bid = confirmed_price['bid']
                    highest_ask = confirmed_price['ask']
                    logger.info(f"✅ CONFIRMED from IBKR: Strike {strike}, Bid ${highest_bid:.2f}, Ask ${highest_ask:.2f}")
                    
                    # ═══════════════════════════════════════════════════════════
                    # 🛡️ PROTECTION: Check if confirmed price is within ENTRY range
                    # ═══════════════════════════════════════════════════════════
                    if min_price <= highest_ask <= max_price:
                        # ✅ Price is in range!
                        logger.info(f"✅ Price ${highest_ask:.2f} is within entry range ${min_price}-${max_price}")
                        break  # Exit loop - we have valid price
                    else:
                        # ❌ Price is OUT OF RANGE (too high OR too low)
                        logger.warning(f"⚠️ Confirmed Ask ${highest_ask:.2f} is OUTSIDE entry range ${min_price}-${max_price}")
                        
                        # Try next strike from valid_contracts list
                        if len(valid_contracts) > 1:
                            # Remove current strike and try next one
                            valid_contracts = [c for c in valid_contracts if c['strike'] != strike]
                            
                            if valid_contracts:
                                # Try next best strike
                                next_best = max(valid_contracts, key=lambda x: x['bid'])
                                strike = next_best['strike']
                                initial_bid = next_best['bid']
                                initial_ask = next_best['ask']
                                
                                logger.info(f"🔄 Trying alternative Strike {strike} (Bid ${initial_bid:.2f}, Ask ${initial_ask:.2f})...")
                                confirmed_price = None  # Reset to retry with new strike
                                retry_count = 0  # Reset counter for new strike
                                continue
                        
                        # No more strikes to try
                        logger.error(f"❌ No alternative strikes available within entry range")
                        if show_dialogs:
                            self.show_auto_close_message(
                                "❌ إلغاء الصفقة", 
                                f"السعر المؤكد من IBKR خارج نطاق الدخول!\n\n"
                                f"السعر المؤكد (Ask): ${highest_ask:.2f}\n"
                                f"نطاق الدخول: ${min_price:.2f} - ${max_price:.2f}\n\n"
                                f"🛡️ تم إلغاء الصفقة للحماية\n"
                                f"(الحماية من الارتفاع والانخفاض)",
                                'error', 
                                4
                            )
                        return None
                else:
                    # Failed to confirm - retry
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"⚠️ Retry {retry_count + 1}/{max_retries} - waiting 5 seconds...")
                        import time
                        time.sleep(5)  # Wait 5 seconds before retry
            
            # ═══════════════════════════════════════════════════════════════
            # 🚨 FINAL CHECK: Did we get confirmed price?
            # ═══════════════════════════════════════════════════════════════
            if confirmed_price is None:
                # Failed after all retries (1 minute)
                logger.error(f"❌ Failed to confirm price from IBKR after {max_retries} attempts (60 seconds)")
                if show_dialogs:
                    self.show_auto_close_message(
                        "❌ إلغاء الصفقة", 
                        f"فشل التأكد من السعر من IBKR!\n\n"
                        f"تم المحاولة {max_retries} مرة (60 ثانية)\n"
                        f"لم يتم الحصول على سعر مؤكد\n\n"
                        f"❌ تم إلغاء الصفقة للحماية\n"
                        f"(لا يوجد دخول بدون سعر حقيقي)",
                        'error', 
                        4
                    )
                return None
            
            # Entry price = ASK (actual buying price from IBKR - CONFIRMED!)
            entry_price = highest_ask
            
            logger.info(f"🎯 FINAL ENTRY DECISION: Strike {strike} @ ${entry_price:.2f} (Ask - CONFIRMED from IBKR)")
            logger.info(f"✅ All protections passed: Price confirmed, within entry range ${min_price}-${max_price}")
            
            return {
                'strike': strike,
                'bid': highest_bid,
                'ask': highest_ask,
                'entry_price': entry_price,
                'total_valid': len(valid_contracts),
                'confirmed_from_ibkr': True  # Always True here (we cancelled if failed)
            }
            
        except Exception as e:
            logger.error(f"Error getting best contract from tree: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_best_contract_from_watchlist(self, symbol, option_type):
        """Get best contract from GUI watchlist - called by trading_system for webhook signals"""
        try:
            # Check if watchlist widget exists for this symbol
            if symbol not in self.watchlist_widgets:
                logger.error(f"❌ Watchlist widget for {symbol} not found")
                return None
            
            # Get the appropriate tree (CALL or PUT)
            tree_key = 'call_tree' if option_type == 'CALL' else 'put_tree'
            tree = self.watchlist_widgets[symbol].get(tree_key)
            
            if not tree:
                logger.error(f"❌ {option_type} tree for {symbol} not found")
                return None
            
            # Use shared function to get best contract (no dialogs for webhook)
            return self._get_best_contract_from_tree(symbol, option_type, tree, show_dialogs=False)
            
        except Exception as e:
            logger.error(f"Error getting best contract from watchlist: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _show_contract_selection_dialog(self, symbol, trade_type, tree):
        """Show contract selection dialog for manual trading"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"اختيار عقد {trade_type} - {symbol}")
        dialog.geometry("650x500")
        dialog.configure(bg=self.colors['bg_main'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 325
        y = (dialog.winfo_screenheight() // 2) - 250
        dialog.geometry(f"+{x}+{y}")
        
        frame = tk.Frame(dialog, bg=self.colors['bg_card'], bd=2, relief='raised')
        frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        color = self.colors['call_color'] if trade_type == 'CALL' else self.colors['put_color']
        emoji = "📈" if trade_type == 'CALL' else "📉"
        
        tk.Label(frame, text=f"{emoji} اختر عقد {trade_type} للشركة {symbol}",
                bg=self.colors['bg_card'], fg=color,
                font=('Arial', 13, 'bold')).pack(pady=(15, 10))
        
        # Contracts list
        list_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        list_frame.pack(fill='both', expand=True, padx=15, pady=10)
        
        columns = ('strike', 'bid', 'ask')
        contracts_tree = ttk.Treeview(list_frame, columns=columns, height=15, show='headings')
        
        contracts_tree.heading('strike', text='Strike')
        contracts_tree.heading('bid', text='Bid')
        contracts_tree.heading('ask', text='Ask')
        
        contracts_tree.column('strike', width=150)
        contracts_tree.column('bid', width=150)
        contracts_tree.column('ask', width=150)
        
        # Copy data from watchlist tree
        for item in tree.get_children():
            item_data = tree.item(item)
            strike = item_data['text']  # Strike is stored in 'text' field
            values = item_data['values']  # [Bid, Ask, Last]
            if values and len(values) >= 2:
                bid = values[0]
                ask = values[1]
                contracts_tree.insert('', 'end', values=(strike, bid, ask))
        
        contracts_tree.pack(fill='both', expand=True)
        
        # Buttons
        btn_frame = tk.Frame(frame, bg=self.colors['bg_card'])
        btn_frame.pack(pady=15)
        
        def confirm_trade():
            selection = contracts_tree.selection()
            if not selection:
                self.show_auto_close_message("تحذير", "الرجاء اختيار عقد أولاً!", 'warning', 3, parent=dialog)
                return
            
            selected_item = contracts_tree.item(selection[0])
            values = selected_item['values']
            strike = values[0]
            bid = values[1]
            ask = values[2]
            
            # Calculate entry price (ASK = actual buying price)
            try:
                # Remove $ sign if exists
                bid_str = str(bid).replace('$', '').replace(',', '').strip()
                ask_str = str(ask).replace('$', '').replace(',', '').strip()
                bid_float = float(bid_str)
                ask_float = float(ask_str)
                # Entry price = ASK (actual buying price)
                entry_price = ask_float
            except:
                self.show_auto_close_message("خطأ", "أسعار العقد غير صحيحة!", 'error', 3, parent=dialog)
                return
            
            # Confirm with user
            confirm_msg = f"""هل تريد فتح صفقة {trade_type}؟
            
📊 الشركة: {symbol}
💰 Strike: {strike}
📈 Bid: ${bid_float:.2f}
📉 Ask: ${ask_float:.2f}
💵 سعر الدخول: ${entry_price:.2f}

سيتم إرسال إشعار للقنوات المفعلة."""
            
            if messagebox.askyesno("تأكيد الصفقة", confirm_msg, parent=dialog):
                try:
                    # Format expiry for database (use today for manual trades)
                    try:
                        from datetime import datetime as dt
                        expiry_formatted = datetime.now().strftime('%d%b%y').upper()
                    except:
                        expiry_formatted = datetime.now().strftime('%d%b%y').upper()
                    
                    # Create the trade in database with quantity
                    contract_name = f"{symbol} {strike} {trade_type}"
                    trade_id = self.db.create_trade(
                        symbol=symbol,
                        trade_type=trade_type,
                        option_contract=contract_name,
                        strike_price=float(strike),
                        entry_price=entry_price,
                        expiry=expiry_formatted,
                        bid=bid_float,
                        ask=ask_float,
                        quantity=self.current_contract_quantity
                    )
                    
                    # Send telegram notification
                    notification_data = {
                        'symbol': symbol,
                        'type': trade_type,
                        'contract': contract_name,
                        'strike': strike,
                        'entry_price': entry_price,
                        'current_price': entry_price,  # Initial price = entry price
                        'bid': bid_float,
                        'ask': ask_float,
                        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    # Send to all channels for this symbol with async_loop
                    self.telegram.send_notification_sync('position_opened', notification_data, symbol, self.async_loop)
                    
                    logger.info(f"Manual {trade_type} trade opened: {contract_name} at ${entry_price:.2f}")
                    self.show_auto_close_message("نجح", f"تم فتح صفقة {trade_type} بنجاح!\n{contract_name}\nالسعر: ${entry_price:.2f}", 'info', 3, parent=dialog)
                    dialog.destroy()
                    
                    # Refresh active trades display
                    self.update_active_trades()
                    
                except Exception as e:
                    logger.error(f"Error opening manual trade: {e}")
                    self.show_auto_close_message("خطأ", f"فشل فتح الصفقة: {str(e)}", 'error', 3, parent=dialog)
        
        ModernButton(btn_frame, text="✓ تأكيد الصفقة",
                    command=confirm_trade,
                    bg=self.colors['accent_green'], fg='black',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=20, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="✗ إلغاء",
                    command=dialog.destroy,
                    bg=self.colors['accent_red'], fg='white',
                    font=('Arial', 10, 'bold'),
                    relief='raised', bd=2, padx=20, pady=8,
                    cursor='hand2').pack(side='left', padx=5)
    
    def update_active_trades(self):
        """Update active trades display"""
        try:
            if not hasattr(self, 'active_tree'):
                return
            
            # Clear existing items
            for item in self.active_tree.get_children():
                self.active_tree.delete(item)
            
            # Get active trades from database - NO AUTO-CLOSING
            active_trades = self.db.get_active_trades()
            
            for trade in active_trades:
                track_count = trade.get('track_count', 0)
                entry_price = trade.get('entry_price', 0)
                highest_price = trade.get('highest_price', 0)
                current_price = trade.get('current_price', 0)
                symbol = trade.get('symbol', 'SPX')
                
                # Get risk settings for this symbol
                risk_settings = self.db.get_risk_settings(symbol)
                
                # Calculate risk management prices
                def calc_price(setting_dict, is_target=False):
                    if not setting_dict or setting_dict.get('type') == 'none':
                        return 'NONE'
                    
                    setting_type = setting_dict.get('type')
                    setting_value = setting_dict.get('value', 0)
                    
                    if setting_type == 'percentage':
                        if is_target:
                            price = entry_price * (1 + setting_value / 100)
                        else:
                            price = entry_price * (1 - setting_value / 100)
                        return f"${price:.2f}"
                    elif setting_type == 'amount':
                        if is_target:
                            price = entry_price + (setting_value / 100)
                        else:
                            price = entry_price - (setting_value / 100)
                        return f"${price:.2f}"
                    return 'NONE'
                
                # Calculate trailing stop based on highest price
                def calc_trailing():
                    trailing = risk_settings.get('trailing_stop', {})
                    if not trailing or trailing.get('type') == 'none':
                        return 'NONE'
                    
                    trail_type = trailing.get('type')
                    trail_value = trailing.get('value', 0)
                    
                    if trail_type == 'percentage':
                        price = highest_price * (1 - trail_value / 100)
                        return f"${price:.2f}"
                    elif trail_type == 'amount':
                        price = highest_price - (trail_value / 100)
                        return f"${price:.2f}"
                    return 'NONE'
                
                # Calculate capital protection (must be above entry)
                def calc_capital():
                    capital = risk_settings.get('capital_protection', {})
                    if not capital or capital.get('type') == 'none':
                        return 'NONE'
                    
                    cap_type = capital.get('type')
                    cap_value = capital.get('value', 0)
                    
                    if cap_type == 'percentage':
                        price = entry_price * (1 + cap_value / 100)
                        return f"${price:.2f}"
                    elif cap_type == 'amount':
                        price = entry_price + (cap_value / 100)
                        return f"${price:.2f}"
                    return 'NONE'
                
                stop_loss = calc_price(risk_settings.get('stop_loss', {}))
                trailing_stop = calc_trailing()
                capital_protection = calc_capital()
                profit_target = calc_price(risk_settings.get('profit_target', {}), is_target=True)
                
                # Calculate profit in USD (price difference * 100 shares per contract)
                profit_usd = (highest_price - entry_price) * 100
                
                # Determine color: red if profit < $100, green if >= $100
                color_tag = 'profit' if profit_usd >= 100 else 'loss'
                
                # Format contract name for display
                contract_display = self.format_contract_name(trade.get('option_contract', 'N/A'))
                
                # Get pending quantity (default to 1 if not set)
                pending_qty = trade.get('pending_quantity', 1)
                
                # Display active trade
                self.active_tree.insert('', 'end', values=(
                    symbol,  # الشركة
                    contract_display,  # Formatted contract name
                    f"${entry_price:.2f}",
                    f"${highest_price:.2f}",
                    f"${current_price:.2f}",
                    stop_loss,
                    trailing_stop,
                    capital_protection,
                    profit_target,
                    f"{track_count}",
                    f"{pending_qty}",  # Quantity to close
                    "❌"  # Close button
                ), tags=(str(trade['id']), color_tag))
            
            # Configure tag colors
            self.active_tree.tag_configure('profit', foreground='#00ff00')  # Green
            self.active_tree.tag_configure('loss', foreground='#ff6b6b')    # Red
            
            # Update selector dropdown if trade count changed
            if hasattr(self, 'active_trade_selector'):
                if not hasattr(self, '_last_active_count') or self._last_active_count != len(active_trades):
                    self._last_active_count = len(active_trades)
                    self.refresh_active_trades_selector()
            
            logger.info(f"Updated active trades display: {len(active_trades)} trades")
        except Exception as e:
            logger.error(f"Error updating active trades: {e}")
        
        # Schedule next update (every 1 second)
        if self.update_tasks_running:
            self.root.after(1000, self.update_active_trades)
    
    def on_trade_selected(self, event=None):
        """Update quantity field when trade is selected"""
        try:
            if not hasattr(self, 'active_trade_selector') or not hasattr(self, 'trade_selector_map'):
                return
            
            selected = self.active_trade_selector.get()
            
            if selected and selected != 'لا توجد صفقات نشطة' and selected in self.trade_selector_map:
                trade_id, pending_qty = self.trade_selector_map[selected]
                # Set to full pending quantity (user can reduce it)
                self.adjust_quantity_entry.delete(0, tk.END)
                self.adjust_quantity_entry.insert(0, str(pending_qty))
                
        except Exception as e:
            logger.error(f"Error in on_trade_selected: {e}")
    
    def refresh_active_trades_selector(self):
        """Refresh the active trades selector dropdown"""
        try:
            if not hasattr(self, 'active_trade_selector'):
                return
            
            # Get all active trades
            active_trades = self.db.get_active_trades()
            
            if not active_trades:
                self.active_trade_selector['values'] = ['لا توجد صفقات نشطة']
                self.active_trade_selector.set('لا توجد صفقات نشطة')
                self.adjust_quantity_entry.delete(0, tk.END)
                self.adjust_quantity_entry.insert(0, "0")
                self.adjust_quantity_entry.config(state='disabled')
                return
            
            # Build selector list
            trade_options = []
            self.trade_selector_map = {}  # Map display text to trade_id
            
            for trade in active_trades:
                trade_id = trade['id']
                symbol = trade['symbol']
                contract = self.format_contract_name(trade['option_contract'])
                pending_qty = trade.get('pending_quantity', 1)
                entry_price = trade.get('entry_price', 0)
                
                # Format: Simple contract name only (e.g., "SPX $6880 CALL")
                display_text = contract
                
                # Handle duplicates by adding ID if needed
                if display_text in self.trade_selector_map:
                    display_text = f"{contract} (#{trade_id})"
                
                trade_options.append(display_text)
                self.trade_selector_map[display_text] = (trade_id, pending_qty)
            
            # Update combobox
            self.active_trade_selector['values'] = trade_options
            if trade_options:
                self.active_trade_selector.set(trade_options[0])
                # Set quantity to first trade's pending quantity
                first_trade_id, first_qty = self.trade_selector_map[trade_options[0]]
                self.adjust_quantity_entry.config(state='normal')
                self.adjust_quantity_entry.delete(0, tk.END)
                self.adjust_quantity_entry.insert(0, str(first_qty))
            
            logger.info(f"Refreshed active trades selector: {len(active_trades)} trades")
            
        except Exception as e:
            logger.error(f"Error refreshing active trades selector: {e}")
    
    def apply_trade_quantity(self):
        """Close partial quantity of selected trade immediately"""
        try:
            if not hasattr(self, 'active_trade_selector'):
                return
            
            # Get selected trade
            selected = self.active_trade_selector.get()
            
            if not selected or selected == 'لا توجد صفقات نشطة':
                self.show_auto_close_message("تنبيه", "الرجاء اختيار صفقة من القائمة!", 'warning', 3)
                return
            
            if selected not in self.trade_selector_map:
                self.show_auto_close_message("خطأ", "الصفقة المختارة غير موجودة!", 'error', 3)
                return
            
            trade_id, current_pending = self.trade_selector_map[selected]
            
            # Get close quantity
            try:
                close_qty = int(self.adjust_quantity_entry.get())
            except ValueError:
                self.show_auto_close_message("خطأ", "الرجاء إدخال رقم صحيح للكمية!", 'error', 3)
                return
            
            if close_qty < 1:
                self.show_auto_close_message("خطأ", "الكمية يجب أن تكون 1 على الأقل!", 'error', 3)
                return
            
            # Check if trying to close more than available
            if close_qty > current_pending:
                self.show_auto_close_message(
                    "❌ غير مسموح",
                    f"⚠️ لا يمكن إغلاق أكثر من الكمية المتوفرة!\n\n"
                    f"الكمية المتوفرة: {current_pending} عقد\n"
                    f"الكمية المطلوب إغلاقها: {close_qty} عقد\n\n"
                    f"✅ الحد الأقصى المسموح: {current_pending}",
                    'error', 3
                )
                return
            
            # Get trade info
            active_trades = self.db.get_active_trades()
            trade = next((t for t in active_trades if t['id'] == trade_id), None)
            
            if not trade:
                self.show_auto_close_message("خطأ", f"الصفقة #{trade_id} غير موجودة!", 'error', 3)
                return
            
            # Determine if full or partial close
            is_full_close = (close_qty >= current_pending)
            remaining = current_pending - close_qty
            
            # Confirm close
            if is_full_close:
                message = f"هل تريد إغلاق الصفقة #{trade_id} بالكامل؟\n\n" \
                         f"الكمية المراد إغلاقها: {close_qty} عقد"
            else:
                message = f"هل تريد إغلاق جزء من الصفقة #{trade_id}؟\n\n" \
                         f"الكمية المراد إغلاقها: {close_qty} عقد\n" \
                         f"سيتبقى نشط: {remaining} عقد"
            
            result = messagebox.askyesno("تأكيد الإغلاق الجزئي", message)
            
            if not result:
                return
            
            # Get exit price
            exit_price = trade.get('current_price', trade.get('highest_price', trade['entry_price']))
            
            # Close (partial or full)
            if is_full_close:
                # Full close - stop tracking
                symbol = trade['symbol']
                strike = trade['strike_price']
                trade_type = trade['trade_type']
                
                expiry_date = self.selected_expiry_dates.get(symbol, None)
                if expiry_date is None:
                    expiry_date = datetime.now().strftime('%Y%m%d')
                
                self.stop_auto_tracking(symbol, strike, trade_type, expiry_date)
            
            # Close in database
            self.db.close_trade(trade_id, exit_price, close_qty)
            
            logger.info(f"✅ Partially closed trade #{trade_id}: {close_qty} contracts at ${exit_price:.2f}")
            
            # Send telegram notification for partial close
            if self.telegram:
                try:
                    print(f"\n{'='*60}")
                    print(f"🔔 محاولة إرسال إشعار إغلاق جزئي")
                    print(f"   الصفقة: #{trade_id}")
                    print(f"   الكمية المُغلقة: {close_qty}")
                    print(f"   المتبقي: {remaining if not is_full_close else 0}")
                    print(f"   إغلاق كامل: {is_full_close}")
                    print(f"{'='*60}\n")
                    
                    symbol = trade['symbol']
                    trade_type = trade['trade_type']
                    entry_price = trade.get('entry_price', 0)
                    strike = trade.get('strike_price', 0)
                    current_price = exit_price  # Use exit price as current price
                    expiry = trade.get('expiry', datetime.now().strftime('%d%b%y').upper())
                    contract = self.format_contract_name(trade['option_contract'])
                    
                    # Calculate profit
                    profit = exit_price - entry_price
                    profit_pct = (profit / entry_price * 100) if entry_price > 0 else 0
                    profit_dollars = profit * 100 * close_qty  # Per contract * 100 shares * quantity
                    profit_sar = profit_dollars * 3.75
                    
                    # Get emoji
                    emoji = '📈' if trade_type == 'CALL' else '📉'
                    
                    # Get channel link
                    channel_link = 'https://t.me/channel'
                    if symbol in self.telegram.channels:
                        if self.telegram.channels[symbol]:
                            channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
                    
                    notification_data = {
                        'symbol': symbol,
                        'type': trade_type,
                        'contract': contract,
                        'strike': strike,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'current_price': current_price,
                        'bid': exit_price,
                        'ask': exit_price,
                        'profit_pct': profit_pct,
                        'profit_dollars': profit_dollars,
                        'profit_sar': profit_sar,
                        'closed_qty': close_qty,
                        'remaining_qty': remaining if not is_full_close else 0,
                        'expiry': expiry,
                        'emoji': emoji,
                        'channel_link': channel_link,
                        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    # Send partial_close notification only if truly partial (contracts remaining)
                    # For full close, let trading_system.close_position send position_closed
                    if not is_full_close:
                        print(f"📤 إرسال إشعار partial_close (إغلاق جزئي حقيقي)...")
                        self.telegram.send_notification_sync('partial_close', notification_data, symbol, self.async_loop)
                        print(f"✅ تم إرسال إشعار partial_close\n")
                    else:
                        print(f"ℹ️ إغلاق كامل - سيتم الإرسال عبر trading_system.close_position\n")
                    
                except Exception as e:
                    print(f"❌ خطأ في إرسال إشعار التيليجرام: {e}")
                    logger.error(f"Error sending partial close telegram notification: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"⚠️ self.telegram غير متاح - لن يتم إرسال إشعار تيليجرام")
            
            # Try to close in trading system (for notifications)
            if self.async_loop and self.trading_system and is_full_close:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self.trading_system.close_position(trade_id, exit_price, "Partial Close", close_qty),
                        self.async_loop
                    ).result(timeout=5)
                except Exception as e:
                    logger.warning(f"Trading system notification skipped: {e}")
            
            # Refresh displays
            self.update_active_trades()
            self.refresh_active_trades_selector()
            
            # Show result
            if is_full_close:
                self.show_auto_close_message(
                    "تم الإغلاق",
                    f"✅ تم إغلاق الصفقة #{trade_id} بالكامل!\n\n"
                    f"الكمية المُغلقة: {close_qty} عقد\n"
                    f"سعر الخروج: ${exit_price:.2f}",
                    'info', 3
                )
            else:
                self.show_auto_close_message(
                    "تم الإغلاق الجزئي",
                    f"✅ تم إغلاق جزء من الصفقة #{trade_id}\n\n"
                    f"الكمية المُغلقة: {close_qty} عقد\n"
                    f"المتبقي نشط: {remaining} عقد\n"
                    f"سعر الخروج: ${exit_price:.2f}",
                    'info', 3
                )
            
        except Exception as e:
            logger.error(f"Error applying partial close: {e}")
            self.show_auto_close_message("خطأ", f"فشل الإغلاق الجزئي:\n{str(e)}", 'error', 3)
    
    def update_trades_history(self):
        """Update closed trades history display"""
        try:
            if not hasattr(self, 'history_tree'):
                return
            
            # Clear existing items
            for item in self.history_tree.get_children():
                self.history_tree.delete(item)
            
            # Get filter symbol
            filter_symbol = None
            if hasattr(self, 'history_filter_symbol'):
                selected = self.history_filter_symbol.get()
                if selected and selected != "الكل":
                    filter_symbol = selected
            
            # Get closed trades from database
            closed_trades = self.db.get_closed_trades(symbol=filter_symbol)
            
            # Calculate totals
            total_profit = 0
            total_loss = 0
            
            # Display closed trades (latest first)
            for idx, trade in enumerate(closed_trades[:50], 1):  # Limit to 50 recent trades
                entry_price = trade.get('entry_price', 0)
                highest_price = trade.get('highest_price', 0)
                exit_price = trade.get('exit_price', 0)  # Get exit/close price
                symbol = trade.get('symbol', 'N/A')
                
                # Calculate profit in USD (price difference * 100 shares)
                profit_usd = (highest_price - entry_price) * 100
                
                # Logic: If profit < $100, entire contract is a loss
                if profit_usd >= 100:
                    # Profitable trade
                    profit_display = f"${profit_usd:.2f}"
                    loss_display = "$0.00"
                    total_profit += profit_usd
                    color_tag = 'profit'
                else:
                    # Loss: entire contract value is lost
                    contract_value = entry_price * 100
                    profit_display = "$0.00"
                    loss_display = f"${contract_value:.2f}"
                    total_loss += contract_value
                    color_tag = 'loss'
                
                # Format strike for history (just the number)
                strike_display = self.format_strike_only(trade.get('option_contract', 'N/A'))
                
                # Format close price (might be 0 if not set)
                close_display = f"${exit_price:.2f}" if exit_price > 0 else "N/A"
                
                self.history_tree.insert('', 'end', values=(
                    idx,
                    symbol,  # الشركة
                    trade.get('trade_type', 'N/A'),
                    strike_display,  # Just strike number
                    f"${entry_price:.2f}",
                    f"${highest_price:.2f}",
                    close_display,  # سعر الإغلاق
                    profit_display,
                    loss_display
                ), tags=(color_tag,))
            
            # Configure tags for colors
            self.history_tree.tag_configure('profit', foreground='#00ff00')
            self.history_tree.tag_configure('loss', foreground='#ff6b6b')
            
            # Update summary labels
            if hasattr(self, 'profit_label'):
                self.profit_label.config(text=f"${total_profit:.2f}")
            if hasattr(self, 'loss_label'):
                self.loss_label.config(text=f"${abs(total_loss):.2f}")
            
            logger.debug(f"Updated trades history: {len(closed_trades)} closed trades, Profit: ${total_profit:.2f}, Loss: ${abs(total_loss):.2f}")
        except Exception as e:
            logger.error(f"Error updating trades history: {e}")
        
        # Schedule next update (every 5 seconds)
        if self.update_tasks_running:
            self.root.after(5000, self.update_trades_history)
    
    def on_active_trade_click(self, event):
        """Handle click on active trades tree"""
        try:
            region = self.active_tree.identify("region", event.x, event.y)
            if region == "cell":
                column = self.active_tree.identify_column(event.x)
                item = self.active_tree.identify_row(event.y)
                
                if not item:
                    return
                
                # Get column index (column IDs are like '#6' for 6th column)
                col_index = int(column.replace('#', '')) - 1
                
                # Check if clicked on 'close' column (index 11)
                # Columns: symbol(0), contract(1), entry(2), high(3), current(4), stop_loss(5), 
                #          trailing(6), capital(7), target(8), tracks(9), quantity(10), close(11)
                if col_index == 11:  # Close column
                    # Get trade ID from tags
                    tags = self.active_tree.item(item, 'tags')
                    if tags:
                        trade_id = int(tags[0])
                        # Get quantity value from tree
                        values = self.active_tree.item(item, 'values')
                        quantity = int(values[10]) if len(values) > 10 else None
                        self.close_active_trade(trade_id, quantity)
        except Exception as e:
            logger.error(f"Error handling active trade click: {e}")
    
    def close_active_trade(self, trade_id, close_quantity=None):
        """Close an active trade manually (fully or partially)"""
        try:
            # Get trade info
            active_trades = self.db.get_active_trades()
            trade = next((t for t in active_trades if t['id'] == trade_id), None)
            
            if not trade:
                self.show_auto_close_message("خطأ", f"الصفقة #{trade_id} غير موجودة!", 'error', 3)
                return
            
            pending_qty = trade.get('pending_quantity', 1)
            
            # If no quantity specified, use pending quantity
            if close_quantity is None:
                close_quantity = pending_qty
            
            # Ensure we don't close more than available
            if close_quantity > pending_qty:
                close_quantity = pending_qty
            
            # Determine if this is a full or partial close
            is_full_close = (close_quantity >= pending_qty)
            
            # Confirm close
            if is_full_close:
                message = f"هل تريد إيقاف التتبع وإغلاق الصفقة #{trade_id} بالكامل؟\n\n" \
                         f"الكمية: {close_quantity} عقد\n" \
                         "سيتم حفظ الصفقة في السجل بأعلى سعر وصلت له."
            else:
                remaining = pending_qty - close_quantity
                message = f"هل تريد إغلاق جزء من الصفقة #{trade_id}؟\n\n" \
                         f"الكمية المراد إغلاقها: {close_quantity} عقد\n" \
                         f"سيتبقى: {remaining} عقد\n\n" \
                         "الصفقة ستبقى نشطة بالكمية المتبقية."
            
            result = messagebox.askyesno("تأكيد الإغلاق", message)
            
            if not result:
                return
            
            # Get exit price
            exit_price = trade.get('current_price', trade.get('highest_price', trade['entry_price']))
            
            # Close trade (partial or full)
            self.db.close_trade(trade_id, exit_price, close_quantity)
            
            if is_full_close:
                # Stop tracking if fully closed
                symbol = trade['symbol']
                strike = trade['strike_price']
                trade_type = trade['trade_type']
                entry_price = trade['entry_price']
                highest_price = trade.get('highest_price', entry_price)
                
                # Get expiry from contract name or use default
                expiry_date = self.selected_expiry_dates.get(symbol, None)
                if expiry_date is None:
                    expiry_date = datetime.now().strftime('%Y%m%d')
                
                # Stop tracking thread
                self.stop_auto_tracking(symbol, strike, trade_type, expiry_date)
                
                logger.info(f"✅ Fully closed trade #{trade_id}: {close_quantity} contracts at ${exit_price:.2f}")
                
                # Calculate profit for notification
                profit = exit_price - entry_price
                profit_pct = (profit / entry_price * 100) if entry_price > 0 else 0
                profit_dollars = profit * 100
                profit_sar = profit_dollars * 3.75
                profit_emoji = '✅' if profit_dollars >= 100 else '❌'
                
                # Get channel link
                channel_link = 'https://t.me/channel'
                if self.telegram and symbol in self.telegram.channels:
                    if self.telegram.channels[symbol]:
                        channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
                
                # Format expiry
                try:
                    from datetime import datetime as dt
                    expiry_dt = dt.strptime(expiry_date, '%Y%m%d')
                    expiry_formatted = expiry_dt.strftime('%d%b%y').upper()
                except:
                    expiry_formatted = datetime.now().strftime('%d%b%y').upper()
                
                # Send position_closed notification
                self.telegram.send_notification_sync('position_closed', {
                    'symbol': symbol,
                    'type': trade_type,
                    'strike': strike,
                    'contract': f"{symbol} {strike} {trade_type}",
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'highest_price': highest_price,
                    'current_price': exit_price,
                    'bid': exit_price,
                    'ask': exit_price,
                    'last': exit_price,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'profit_dollars': profit_dollars,
                    'profit_sar': profit_sar,
                    'profit_emoji': profit_emoji,
                    'reason': 'Manual Close',
                    'manual': True,
                    'expiry': expiry_formatted,
                    'emoji': '📈' if trade_type == 'CALL' else '📉',
                    'channel_link': channel_link,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }, symbol, self.async_loop)
                
                logger.info(f"📤 Sent position_closed notification to Telegram")
                
                # Try to close in trading system (but don't wait for notifications)
                if self.async_loop and self.trading_system:
                    try:
                        # Just remove from active_trades, don't send duplicate notification
                        if trade_id in self.trading_system.active_trades:
                            del self.trading_system.active_trades[trade_id]
                        if trade_id in self.trading_system.tracking_tasks:
                            self.trading_system.tracking_tasks[trade_id].cancel()
                            del self.trading_system.tracking_tasks[trade_id]
                        logger.info(f"✅ Removed from trading system tracking")
                    except Exception as e:
                        logger.warning(f"Trading system cleanup skipped: {e}")
                
                self.show_auto_close_message("تم الإغلاق", 
                                  f"تم إغلاق الصفقة #{trade_id} بالكامل!\n\n"
                                  f"الكمية: {close_quantity} عقد\n"
                                  f"سعر الخروج: ${exit_price:.2f}", 'info', 3)
            else:
                # Partial close
                remaining = pending_qty - close_quantity
                logger.info(f"✅ Partially closed trade #{trade_id}: {close_quantity} contracts, {remaining} remaining")
                
                # Calculate profit for partial close notification
                symbol = trade['symbol']
                strike = trade['strike_price']
                trade_type = trade['trade_type']
                entry_price = trade['entry_price']
                
                profit = exit_price - entry_price
                profit_pct = (profit / entry_price * 100) if entry_price > 0 else 0
                profit_dollars = profit * 100 * close_quantity  # Profit for closed quantity
                profit_sar = profit_dollars * 3.75
                
                # Get channel link
                channel_link = 'https://t.me/channel'
                if self.telegram and symbol in self.telegram.channels:
                    if self.telegram.channels[symbol]:
                        channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
                
                # Send partial_close notification
                self.telegram.send_notification_sync('partial_close', {
                    'symbol': symbol,
                    'type': trade_type,
                    'strike': strike,
                    'contract': f"{symbol} {strike} {trade_type}",
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'closed_qty': close_quantity,
                    'remaining_qty': remaining,
                    'profit_dollars': profit_dollars,
                    'profit_sar': profit_sar,
                    'profit_pct': profit_pct,
                    'emoji': '📈' if trade_type == 'CALL' else '📉',
                    'channel_link': channel_link,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }, symbol, self.async_loop)
                
                logger.info(f"📤 Sent partial_close notification to Telegram")
                
                self.show_auto_close_message("تم الإغلاق الجزئي", 
                                  f"تم إغلاق {close_quantity} عقد من الصفقة #{trade_id}\n\n"
                                  f"المتبقي: {remaining} عقد\n"
                                  f"سعر الخروج: ${exit_price:.2f}", 'info', 3)
            
            # Force immediate update of displays
            self.update_active_trades()
            self.update_trades_history()
            
        except Exception as e:
            logger.error(f"Error closing trade: {e}")
            self.show_auto_close_message("خطأ", f"فشل إغلاق الصفقة:\n{str(e)}", 'error', 3)
    
    def close_all_active_trades(self):
        """Close all active trades at once"""
        try:
            # Get all active trades
            active_trades = self.db.get_active_trades()
            
            if not active_trades:
                self.show_auto_close_message("تنبيه", "لا توجد صفقات نشطة لإغلاقها!", 'info', 3)
                return
            
            # Confirm close all
            result = messagebox.askyesno(
                "⚠️ تأكيد إغلاق جميع الصفقات",
                f"هل تريد إغلاق جميع الصفقات النشطة ({len(active_trades)} صفقة)؟\n\n"
                "⚠️ هذا الإجراء لا يمكن التراجع عنه!\n"
                "سيتم إغلاق جميع الصفقات بأعلى سعر وصلت له."
            )
            
            if not result:
                return
            
            closed_count = 0
            failed_count = 0
            
            # Close each trade
            for trade in active_trades:
                try:
                    trade_id = trade['id']
                    symbol = trade['symbol']
                    strike = trade['strike_price']
                    trade_type = trade['trade_type']
                    entry_price = trade['entry_price']
                    highest_price = trade.get('highest_price', entry_price)
                    
                    # Get expiry
                    expiry_date = self.selected_expiry_dates.get(symbol, None)
                    if expiry_date is None:
                        expiry_date = datetime.now().strftime('%Y%m%d')
                    
                    # Stop tracking
                    self.stop_auto_tracking(symbol, strike, trade_type, expiry_date)
                    
                    # Use current price (BID) as exit price - the actual selling price
                    exit_price = trade.get('current_price', trade.get('highest_price', trade['entry_price']))
                    
                    # Close in database
                    self.db.close_trade(trade_id, exit_price)
                    logger.info(f"✅ Closed trade #{trade_id} in database at ${exit_price:.2f}")
                    
                    # Calculate profit for notification
                    profit = exit_price - entry_price
                    profit_pct = (profit / entry_price * 100) if entry_price > 0 else 0
                    profit_dollars = profit * 100
                    profit_sar = profit_dollars * 3.75
                    profit_emoji = '✅' if profit_dollars >= 100 else '❌'
                    
                    # Get channel link
                    channel_link = 'https://t.me/channel'
                    if self.telegram and symbol in self.telegram.channels:
                        if self.telegram.channels[symbol]:
                            channel_link = self.telegram.channels[symbol][0].get('link', 'https://t.me/channel')
                    
                    # Format expiry
                    try:
                        from datetime import datetime as dt
                        expiry_dt = dt.strptime(expiry_date, '%Y%m%d')
                        expiry_formatted = expiry_dt.strftime('%d%b%y').upper()
                    except:
                        expiry_formatted = datetime.now().strftime('%d%b%y').upper()
                    
                    # Telegram notification disabled for Close All button
                    logger.info(f"ℹ️ Close All: Telegram notification skipped for trade #{trade_id}")
                    
                    # Remove from trading system tracking (no duplicate notifications)
                    if self.async_loop and self.trading_system:
                        try:
                            if trade_id in self.trading_system.active_trades:
                                del self.trading_system.active_trades[trade_id]
                            if trade_id in self.trading_system.tracking_tasks:
                                self.trading_system.tracking_tasks[trade_id].cancel()
                                del self.trading_system.tracking_tasks[trade_id]
                        except Exception as e:
                            logger.warning(f"Trading system cleanup skipped for #{trade_id}: {e}")
                    
                    closed_count += 1
                    
                except Exception as e:
                    logger.error(f"Error closing trade #{trade.get('id', '?')}: {e}")
                    failed_count += 1
            
            # Update displays
            self.update_active_trades()
            self.update_trades_history()
            
            # Show result
            if failed_count == 0:
                self.show_auto_close_message(
                    "تم الإغلاق", 
                    f"✅ تم إغلاق جميع الصفقات بنجاح!\n\n"
                    f"عدد الصفقات المغلقة: {closed_count}",
                    'info', 3
                )
            else:
                self.show_auto_close_message(
                    "إغلاق جزئي",
                    f"تم إغلاق {closed_count} صفقة بنجاح\n"
                    f"فشل إغلاق {failed_count} صفقة",
                    'warning', 3
                )
            
        except Exception as e:
            logger.error(f"Error in close_all_active_trades: {e}")
            self.show_auto_close_message("خطأ", f"فشل إغلاق الصفقات:\n{str(e)}", 'error', 3)
    
    def restart_all_tracking(self):
        """إعادة تنشيط التتبع لجميع الصفقات النشطة - نظام منفصل تماماً"""
        try:
            # Get all active trades
            active_trades = self.db.get_active_trades()
            
            if not active_trades:
                self.show_auto_close_message("تنبيه", "لا توجد صفقات نشطة!", 'info', 2)
                return
            
            # Confirm restart
            result = messagebox.askyesno(
                "🔄 تأكيد إعادة تنشيط التتبع",
                f"هل تريد إعادة تنشيط التتبع لجميع الصفقات النشطة ({len(active_trades)}  صفقة)؟\n\n"
                "سيتم بدء تتبع منفصل تماماً مع إشعارات تيليجرام كاملة."
            )
            
            if not result:
                return
            
            restarted_count = 0
            failed_count = 0
            
            # Start INDEPENDENT tracking for each trade
            for trade in active_trades:
                try:
                    trade_id = trade['id']
                    symbol = trade['symbol']
                    strike = trade['strike_price']
                    trade_type = trade['trade_type']
                    entry_price = trade['entry_price']
                    
                    # Get expiry
                    expiry_date = self.selected_expiry_dates.get(symbol, None)
                    if expiry_date is None:
                        expiry_date = datetime.now().strftime('%Y%m%d')
                    
                    logger.info(f"🔄 Starting INDEPENDENT tracking for trade #{trade_id}...")
                    
                    # Start independent tracking thread
                    self._start_independent_tracking(
                        trade_id=trade_id,
                        symbol=symbol,
                        strike=float(strike),
                        trade_type=trade_type,
                        entry_price=entry_price,
                        expiry_date=expiry_date
                    )
                    
                    logger.info(f"✅ Independent tracking started for trade #{trade_id}")
                    restarted_count += 1
                    
                    # Small delay between starting trackers
                    import time
                    time.sleep(0.3)
                    
                except Exception as e:
                    logger.error(f"Error starting tracking for trade #{trade.get('id', '?')}: {e}")
                    failed_count += 1
            
            # Show result
            if failed_count == 0:
                self.show_auto_close_message(
                    "تم بنجاح", 
                    f"✅ تم بدء التتبع المستقل لجميع الصفقات!\n\n"
                    f"عدد الصفقات: {restarted_count}",
                    'info', 3
                )
            else:
                self.show_auto_close_message(
                    "بدء جزئي",
                    f"تم بدء التتبع لـ {restarted_count} صفقة\n"
                    f"فشل {failed_count} صفقة",
                    'warning', 3
                )
            
        except Exception as e:
            logger.error(f"Error in restart_all_tracking: {e}")
            self.show_auto_close_message("خطأ", f"فشل بدء التتبع:\n{str(e)}", 'error', 3)
    
    def _start_independent_tracking(self, trade_id, symbol, strike, trade_type, entry_price, expiry_date):
        """بدء تتبع مستقل تماماً باتصال منفصل - يعيد True/False حسب النجاح"""
        import threading
        
        # Events للتحقق من نجاح الاتصال الأولي
        success_event = threading.Event()
        error_event = threading.Event()
        
        def tracking_thread():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                loop.run_until_complete(
                    self._independent_tracker(trade_id, symbol, strike, trade_type, entry_price, expiry_date, 
                                            success_event, error_event)
                )
            except Exception as e:
                logger.error(f"Error in independent tracker thread for #{trade_id}: {e}")
                error_event.set()
            finally:
                loop.close()
        
        thread = threading.Thread(target=tracking_thread, daemon=True, name=f"IndependentTracker-{trade_id}")
        thread.start()
        logger.info(f"🔄 Started independent tracking thread for trade #{trade_id}")
        
        # انتظار دقيقة كاملة قبل اعتبار التتبع فاشل
        logger.info(f"⏰ Waiting for initial connection confirmation (max 60s)...")
        if success_event.wait(timeout=60):
            logger.info(f"✅ Tracking confirmed for trade #{trade_id}")
            return True
        else:
            logger.error(f"❌ Tracking failed to confirm within 60s for trade #{trade_id}")
            return False
    
    async def _independent_tracker(self, trade_id, symbol, strike, trade_type, entry_price, expiry_date, 
                                   success_event=None, error_event=None):
        """متتبع مستقل تماماً مع اتصال IBKR منفصل وإشعارات تيليجرام مع RETRY"""
        from ib_insync import IB, Option
        import sqlite3
        import random
        
        retry_count = 0
        max_retries = 999999  # محاولات غير محدودة
        retry_delay = 3  # 3 ثواني بين المحاولات
        initial_connection_made = False  # للتحقق من نجاح الاتصال الأول
        
        while retry_count < max_retries:
            ib = None
            try:
                # Log attempt number
                if retry_count > 0:
                    logger.info(f"🔄 Retry attempt #{retry_count} for trade #{trade_id}")
                else:
                    logger.info(f"📊 Independent Tracker starting for trade #{trade_id}")
                    logger.info(f"   Symbol: {symbol}, Strike: {strike}, Type: {trade_type}")
                
                # Create INDEPENDENT IBKR connection with UNIQUE Client ID
                ib = IB()
                # استخدام trade_id لضمان Client ID فريد لكل صفقة (5000 + trade_id)
                # هذا يضمن عدم التعارض - كل صفقة لها اتصال منفصل تماماً
                unique_client_id = 5000 + trade_id
                
                logger.info(f"🔌 Connecting with Client ID: {unique_client_id} (5000 + trade_id #{trade_id})")
                await ib.connectAsync(config.IBKR_HOST, config.IBKR_PORT, 
                                     clientId=unique_client_id, readonly=True, timeout=30)
                logger.info(f"✅ Connected to IBKR for trade #{trade_id}")
                
                ib.reqMarketDataType(3)  # Delayed data
                
                # Create and qualify contract
                right = 'C' if trade_type == 'CALL' else 'P'
                
                if symbol == 'SPX':
                    exchange = 'CBOE'
                    trading_class = 'SPXW'
                elif symbol == 'NDX':
                    exchange = 'CBOE'
                    trading_class = 'NDXP'
                else:
                    exchange = 'SMART'
                    trading_class = symbol
                
                contract = Option(symbol, expiry_date, strike, right, exchange, tradingClass=trading_class)
                
                logger.info(f"🔍 Qualifying contract...")
                qualified = await ib.qualifyContractsAsync(contract)
                if not qualified:
                    logger.error(f"❌ Failed to qualify contract for trade #{trade_id}")
                    raise Exception("Failed to qualify contract")
                
                contract = qualified[0]
                logger.info(f"✅ Contract qualified: {contract}")
                
                # Start market data
                ticker = ib.reqMktData(contract)
                await asyncio.sleep(2)
                
                # ✅ الاتصال نجح! إعلام success_event
                if not initial_connection_made:
                    initial_connection_made = True
                    if success_event:
                        success_event.set()
                    logger.info(f"✅ Initial connection successful for trade #{trade_id}")
                
                logger.info(f"🎯 Starting price tracking loop for trade #{trade_id}...")
                
                highest_price = entry_price
                last_target_notified = 0
                
                # Tracking loop - نجح الاتصال، الآن tracking مستمر
                while True:
                    try:
                        await asyncio.sleep(config.TRACKING_UPDATE_INTERVAL)
                        
                        # ⚠️ Check if trade was closed manually from GUI
                        conn = self.db.connect()
                        cursor = conn.cursor()
                        cursor.execute('SELECT status FROM trades WHERE id = ?', (trade_id,))
                        result = cursor.fetchone()
                        conn.close()
                        
                        if not result or result[0] == 'CLOSED':
                            logger.info(f"🛑 Trade #{trade_id} was closed manually - stopping independent tracker")
                            print(f"🛑 Trade #{trade_id} closed manually - stopping tracker")
                            break
                        
                        bid = ticker.bid if ticker.bid == ticker.bid and ticker.bid > 0 else 0
                        ask = ticker.ask if ticker.ask == ticker.ask and ticker.ask > 0 else 0
                        
                        if bid <= 0:
                            continue
                        
                        # ⚡ INSTANT RISK CHECK - RUN FIRST!
                        risk_settings = self.db.get_risk_settings(symbol)
                        
                        logger.info(f"🔍 INDEPENDENT CHECK Trade #{trade_id}: Entry=${entry_price:.2f}, Current=${bid:.2f}, Highest=${highest_price:.2f}")
                        print(f"\n🔍 INDEPENDENT CHECK Trade #{trade_id}")
                        print(f"   Entry: ${entry_price:.2f}, Current: ${bid:.2f}, Highest: ${highest_price:.2f}")
                        print(f"   Risk Settings: {risk_settings}")
                        
                        should_close, reason = self.trading_system._check_risk_management(
                            entry_price, bid, highest_price, risk_settings
                        )
                        
                        print(f"   Result: should_close={should_close}, reason='{reason}'")
                        logger.info(f"🔍 Result: should_close={should_close}, reason='{reason}'")
                        
                        if should_close:
                            print(f"\n⚡ AUTO-CLOSE trade #{trade_id}: {reason}")
                            logger.info(f"⚡ AUTO-CLOSE trade #{trade_id}: {reason}")
                            
                            # Calculate final profit (based on exit_price)
                            profit = bid - entry_price  # Exit price - Entry price
                            profit_pct = (profit / entry_price * 100) if entry_price > 0 else 0
                            profit_dollars = profit * 100  # Contract = 100 shares
                            profit_sar = profit_dollars * 3.75  # Convert to SAR
                            
                            # Determine profit emoji and status
                            if profit_dollars >= 100:
                                profit_emoji = '✅'
                            else:
                                profit_emoji = '❌'
                            
                            # Close in database
                            self.db.close_trade(trade_id, bid)
                            
                            # Choose notification type based on reason
                            notification_type = 'position_closed'  # Default
                            if 'Profit Target' in reason or 'ضرب الهدف' in reason:
                                notification_type = 'profit_target_hit'
                            elif 'Stop Loss' in reason and 'Trailing' not in reason:
                                notification_type = 'stop_loss_hit'
                            elif 'Trailing Stop' in reason or 'متحرك' in reason:
                                notification_type = 'trailing_stop_hit'
                            elif 'Capital Protection' in reason or 'حماية رأس المال' in reason:
                                notification_type = 'capital_protection_hit'
                            
                            # Send notification with complete profit data
                            self.telegram.send_notification_sync(notification_type, {
                                'symbol': symbol,
                                'type': trade_type,
                                'strike': strike,
                                'contract': f"{symbol} {strike} {trade_type}",
                                'entry_price': entry_price,
                                'exit_price': bid,
                                'highest_price': highest_price,
                                'current_price': bid,
                                'bid': bid,
                                'ask': ask,
                                'last': bid,
                                'profit': profit,
                                'profit_pct': profit_pct,
                                'profit_dollars': profit_dollars,
                                'profit_sar': profit_sar,
                                'profit_emoji': profit_emoji,
                                'reason': reason,
                                'manual': False,
                                'expiry': datetime.now().strftime('%d%b%y').upper(),
                                'emoji': '📈' if trade_type == 'CALL' else '📉',
                                'channel_link': 'https://t.me/SPXSmartPro',
                                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }, symbol, self.async_loop)
                            
                            logger.info(f"✅ Trade #{trade_id} closed automatically: {reason}")
                            logger.info(f"💰 Profit: ${profit_dollars:.2f} ({profit_pct:.1f}%) = {profit_sar:.2f} SAR")
                            print(f"✅ Trade #{trade_id} closed and notification sent")
                            print(f"💰 Profit: ${profit_dollars:.2f} ({profit_pct:.1f}%) = {profit_sar:.2f} SAR\n")
                            
                            # Stop tracking
                            break
                        
                        # Update database
                        self.db.update_trade_price(trade_id, bid, bid, ask)
                        
                        # Check for new high
                        if bid > highest_price:
                            highest_price = bid
                            
                            # Calculate profit
                            profit = bid - entry_price
                            profit_pct = (profit / entry_price * 100) if entry_price > 0 else 0
                            profit_dollars = profit * 100
                            profit_sar = profit_dollars * 3.75
                            
                            # Send new_high notification
                            self.telegram.send_notification_sync('new_high', {
                                'symbol': symbol,
                                'type': trade_type,
                                'strike': strike,
                                'contract': f"{symbol} {strike} {trade_type}",
                                'entry_price': entry_price,
                                'current_price': bid,
                                'highest_price': highest_price,
                                'bid': bid,
                                'ask': ask,
                                'last': bid,
                                'profit': profit,
                                'profit_pct': profit_pct,
                                'profit_dollars': profit_dollars,
                                'profit_sar': profit_sar,
                                'expiry': datetime.now().strftime('%d%b%y').upper(),
                                'emoji': '📈' if trade_type == 'CALL' else '📉',
                                'channel_link': 'https://t.me/SPXSmartPro',
                                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }, symbol, self.async_loop)
                            
                            logger.info(f"🔥 Trade #{trade_id}: New high ${highest_price:.2f}")
                        
                        # Check for target achievement
                        profit = bid - entry_price
                        profit_dollars = profit * 100
                        current_target_level = int(profit_dollars // 100) * 100
                        
                        if profit_dollars >= 100 and current_target_level > last_target_notified:
                            profit_sar = profit_dollars * 3.75
                            profit_pct = (profit_dollars / entry_price) * 100 if entry_price > 0 else 0
                            
                            self.telegram.send_notification_sync('target_achieved', {
                                'symbol': symbol,
                                'type': trade_type,
                                'strike': strike,
                                'contract': f"{symbol} {strike} {trade_type}",
                                'entry_price': entry_price,
                                'current_price': bid,
                                'highest_price': highest_price,
                                'bid': bid,
                                'ask': ask,
                                'last': bid,
                                'profit': profit,
                                'profit_dollars': profit_dollars,
                                'profit_sar': profit_sar,
                                'profit_pct': profit_pct,
                                'expiry': datetime.now().strftime('%d%b%y').upper(),
                                'emoji': '📈' if trade_type == 'CALL' else '📉',
                                'channel_link': 'https://t.me/SPXSmartPro',
                                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }, symbol, self.async_loop)
                            
                            last_target_notified = current_target_level
                            logger.info(f"🎯 Trade #{trade_id}: Target ${current_target_level} achieved")
                        
                    except Exception as e:
                        logger.error(f"Error in tracking loop for #{trade_id}: {e}")
                        await asyncio.sleep(1)
                
                # إذا وصلنا هنا، التتبع انتهى بشكل طبيعي
                # Disconnect IBKR connection
                if ib and ib.isConnected():
                    try:
                        ib.disconnect()
                        logger.info(f"🔌 Disconnected IBKR connection for trade #{trade_id}")
                    except:
                        pass
                
                break
                        
            except Exception as e:
                retry_count += 1
                logger.error(f"❌ Error in independent tracker for trade #{trade_id} (attempt {retry_count}): {e}")
                
                # إذا فشل الاتصال الأولي → إعلام error_event
                if not initial_connection_made and error_event and retry_count == 1:
                    error_event.set()
                
                # Disconnect if connected
                if ib and ib.isConnected():
                    try:
                        ib.disconnect()
                    except:
                        pass
                
                # الانتظار قبل المحاولة التالية
                if retry_count < max_retries:
                    logger.info(f"⏰ Waiting {retry_delay} seconds before retry...")
                    await asyncio.sleep(retry_delay)
        
        # إذا انتهت جميع المحاولات
        logger.error(f"❌ Independent tracker failed after {retry_count} attempts for trade #{trade_id}")
    
    # ==================== Auto Tracking ====================
    
    def start_auto_tracking(self, symbol, strike, trade_type, expiry_date, trade_id=None):
        """Start automatic tracking for a contract"""
        try:
            # Check number of active tracking threads
            active_count = len(self.active_tracking)
            if active_count >= 10:
                logger.warning(f"⚠️ WARNING: {active_count} active tracking threads! This may cause connection issues.")
                self.show_auto_close_message(
                    "تحذير",
                    f"⚠️ عدد الصفقات النشطة: {active_count}\n\n"
                    "عدد كبير من الصفقات قد يسبب مشاكل في الاتصال!\n"
                    "يُنصح بإغلاق بعض الصفقات القديمة.",
                    'warning', 3
                )
            
            # Create unique key for this contract
            contract_key = f"{symbol}_{strike}_{trade_type}_{expiry_date}"
            
            # Create stop flag (threading.Event)
            import threading
            stop_flag = threading.Event()
            self.active_tracking[contract_key] = stop_flag
            
            # Run tracking in background thread
            thread = threading.Thread(
                target=self._auto_track_contract_thread,
                args=(symbol, strike, trade_type, expiry_date, stop_flag, trade_id),
                daemon=True
            )
            thread.start()
            
            logger.info(f"✅ Started auto-tracking: {contract_key} (Total active: {len(self.active_tracking)})")
            
        except Exception as e:
            logger.error(f"Error starting auto-tracking: {e}")
            import traceback
            traceback.print_exc()
    
    def stop_auto_tracking(self, symbol, strike, trade_type, expiry_date):
        """Stop automatic tracking for a contract"""
        try:
            contract_key = f"{symbol}_{strike}_{trade_type}_{expiry_date}"
            
            if contract_key in self.active_tracking:
                self.active_tracking[contract_key].set()  # Signal stop
                del self.active_tracking[contract_key]
                logger.info(f"⛔ Stopped auto-tracking: {contract_key} (Remaining active: {len(self.active_tracking)})")
                return True
            else:
                logger.warning(f"No active tracking found for: {contract_key}")
                return False
                
        except Exception as e:
            logger.error(f"Error stopping auto-tracking: {e}")
            return False
    
    def stop_all_tracking(self):
        """Stop all active tracking"""
        try:
            count = len(self.active_tracking)
            for stop_flag in self.active_tracking.values():
                stop_flag.set()
            
            self.active_tracking.clear()
            logger.info(f"Stopped all tracking ({count} contracts)")
            self.show_auto_close_message("تم الإيقاف", f"تم إيقاف التتبع لـ {count} عقد", 'info', 3)
            
        except Exception as e:
            logger.error(f"Error stopping all tracking: {e}")
    
    def _auto_track_contract_thread(self, symbol, strike, trade_type, expiry_date, stop_flag, trade_id=None):
        """Thread function for auto-tracking (runs in background)"""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run tracking coroutine
            loop.run_until_complete(
                self._auto_track_contract(symbol, strike, trade_type, expiry_date, stop_flag, trade_id)
            )
            
        except Exception as e:
            logger.error(f"Error in tracking thread: {e}")
            import traceback
            traceback.print_exc()
        finally:
            loop.close()
    
    async def _auto_track_contract(self, symbol, strike, trade_type, expiry_date, stop_flag, trade_id=None):
        """Auto-track contract and send telegram updates with auto-reconnect"""
        from ib_insync import IB, Option
        from telegram import Bot
        from io import BytesIO
        import asyncio
        import random
        
        ib = None  # Initialize to None
        
        # Create database connection for this thread
        db_tracker = None
        logger.info(f"📊 Trade ID received: {trade_id}")
        if trade_id:
            from database import DatabaseManager
            db_tracker = DatabaseManager()
            logger.info(f"✅ Database tracker created for trade #{trade_id}")
        else:
            logger.warning("⚠️ No trade_id provided - tracking data will NOT be saved to database!")
        
        # Variables for persistent tracking
        entry_ask = None
        update_count = 0
        check_count = 0
        highest_bid = 0
        last_sent_bid = 0
        last_valid_bid = 0
        entry_message_sent = False
        connection_count = 0  # Track total connections
        
        while not stop_flag.is_set():
            try:
                # Clean up any existing connection first
                if ib is not None:
                    try:
                        if ib.isConnected():
                            logger.info("🔌 Closing old connection before reconnect...")
                            ib.disconnect()
                            await asyncio.sleep(1)
                    except Exception as cleanup_error:
                        logger.warning(f"Error cleaning up old connection: {cleanup_error}")
                
                # Create fresh IB instance
                ib = IB()
                connection_count += 1
                
                logger.info(f"\n{'='*60}")
                logger.info(f"🔗 Connecting to IBKR for tracking (Connection #{connection_count})")
                logger.info(f"Symbol: {symbol}, Strike: {strike}, Type: {trade_type}")
                logger.info(f"Expiry: {expiry_date}")
                logger.info(f"{'='*60}")
                
                # Use random client ID to avoid conflicts (10-999)
                random_client_id = random.randint(10, 999)
                logger.info(f"📡 Using random Client ID: {random_client_id}")
                
                # Connect to IBKR
                await ib.connectAsync(config.IBKR_HOST, config.IBKR_PORT, 
                                     clientId=random_client_id, 
                                     readonly=True, timeout=30)
                logger.info(f"✅ Connected to IBKR for tracking (Total connections: {connection_count})")
                
                ib.reqMarketDataType(3)  # Delayed data
                
                # Create contract
                right = 'C' if trade_type == 'CALL' else 'P'
                
                # Set exchange and trading class based on symbol
                if symbol == 'SPX':
                    exchange = 'CBOE'
                    trading_class = 'SPXW'
                elif symbol == 'NDX':
                    exchange = 'CBOE'
                    trading_class = 'NDXP'
                else:
                    exchange = 'SMART'
                    trading_class = symbol
                
                contract = Option(symbol, expiry_date, float(strike), right, exchange, 
                                tradingClass=trading_class)
                
                contracts = await ib.qualifyContractsAsync(contract)
                if not contracts:
                    logger.error("❌ Failed to qualify contract")
                    await asyncio.sleep(5)
                    continue
                
                contract = contracts[0]
                logger.info(f"✅ Contract qualified: {contract.localSymbol}")
                
                # Get ENTRY PRICE from ASK (only first time)
                ticker = ib.reqMktData(contract, '', False, False)  # Streaming mode
                await asyncio.sleep(2)
                
                if entry_ask is None:
                    entry_ask = ticker.ask if ticker.ask == ticker.ask else 0
                    
                    if entry_ask <= 0:
                        logger.error("❌ No ASK price available for entry")
                        await asyncio.sleep(5)
                        continue
                    
                    logger.info(f"💰 ENTRY PRICE (ASK): ${entry_ask:.2f}")
                    highest_bid = entry_ask
                    last_valid_bid = entry_ask
                
                # Send ENTRY MESSAGE (only once)
                if not entry_message_sent:
                    await self._send_tracking_message('entry', {
                        'symbol': symbol,
                        'strike': int(strike),
                        'type': trade_type,
                        'type_en': trade_type,
                        'entry_price': f"{entry_ask:.2f}",
                        'date': datetime.now().strftime('%d %b %y').upper()
                    })
                    logger.info("📤 Sent ENTRY message")
                    entry_message_sent = True
                
                # Start tracking BID
                logger.info(f"\n📡 Started tracking BID price")
                logger.info(f"⏰ Checking every {config.TRACKING_UPDATE_INTERVAL} seconds")
                logger.info(f"📤 Sending updates ONLY when BID increases")
                logger.info("="*60)
                
                # Tracking loop - continues until stop_flag is set
                while not stop_flag.is_set():
                    try:
                        await asyncio.sleep(config.TRACKING_UPDATE_INTERVAL)
                        
                        if stop_flag.is_set():
                            logger.info("⛔ Stop requested - ending tracking")
                            break
                        
                        check_count += 1
                        
                        ask = ticker.ask if ticker.ask == ticker.ask else 0
                        bid = ticker.bid if ticker.bid == ticker.bid else 0
                        
                        if bid <= 0:
                            logger.debug(f"⚠ Check #{check_count}: No BID")
                            continue
                        
                        # Update last valid bid
                        last_valid_bid = bid
                        
                        # Update database
                        if trade_id and db_tracker:
                            try:
                                db_tracker.update_trade_price(trade_id, bid, bid, ask)
                                logger.debug(f"💾 Saved to DB: Trade #{trade_id}, Bid=${bid:.2f}, Ask=${ask:.2f}")
                            except Exception as e:
                                logger.error(f"❌ DB update failed: {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            if not trade_id:
                                logger.debug(f"⚠️ Skipping DB save - no trade_id")
                            elif not db_tracker:
                                logger.debug(f"⚠️ Skipping DB save - no db_tracker")
                        
                        # Update highest bid
                        if bid > highest_bid:
                            highest_bid = bid
                            logger.info(f"🔥 Check #{check_count}: NEW HIGH ${highest_bid:.2f}")
                        
                        # Send update only if BID increased
                        if bid <= last_sent_bid:
                            continue
                        
                        # BID increased! Send update
                        update_count += 1
                        last_sent_bid = bid
                        profit_usd = bid - entry_ask
                        profit_sar = profit_usd * 100 * 3.75
                        
                        logger.info(f"📤 Update #{update_count}: ${bid:.2f} (+${profit_usd:.2f})")
                        
                        # Send appropriate message
                        if profit_usd >= 100:
                            # Send TARGET message (but DON'T close trade)
                            await self._send_tracking_message('target', {
                                'symbol': symbol,
                                'strike': int(strike),
                                'type': trade_type,
                                'entry_price': f"{entry_ask:.2f}",
                                'current_price': f"{bid:.2f}",
                                'profit_usd': f"{profit_usd:.2f}",
                                'profit_sar': f"{profit_sar:.2f}",
                                'date': datetime.now().strftime('%d %b %y').upper()
                            })
                            logger.info("🎯 Target message sent - tracking continues")
                        else:
                            # Send UPDATE message
                            await self._send_tracking_message('update', {
                                'symbol': symbol,
                                'strike': int(strike),
                                'type': trade_type,
                                'entry_price': f"{entry_ask:.2f}",
                                'current_price': f"{bid:.2f}",
                                'profit_usd': f"{profit_usd:.2f}",
                                'profit_sar': f"{profit_sar:.2f}",
                                'date': datetime.now().strftime('%d %b %y').upper()
                            })
                    
                    except Exception as inner_e:
                        logger.error(f"Error in tracking loop: {inner_e}")
                        # Don't break - continue tracking
                        await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Connection error (Connection #{connection_count}): {e}")
                logger.info("🔄 Will retry connection in 5 seconds...")
                
                # CRITICAL: Disconnect old connection to prevent accumulation
                try:
                    if ib is not None and ib.isConnected():
                        logger.info("🔌 Disconnecting failed connection...")
                        ib.disconnect()
                        logger.info("✅ Old connection closed successfully")
                except Exception as disconnect_error:
                    logger.warning(f"⚠️ Error disconnecting: {disconnect_error}")
                
                await asyncio.sleep(5)
                # Loop will retry connection with fresh IB instance
                
        # Final cleanup (only when stop_flag is set)
        logger.info(f"⛔ Stopping tracking for {symbol} {strike} {trade_type}")
        logger.info(f"📊 Total connections made: {connection_count}")
        try:
            if ib is not None and ib.isConnected():
                ib.disconnect()
                logger.info("🔌 Disconnected from IBKR (tracking stopped)")
        except Exception as final_cleanup_error:
            logger.warning(f"Error in final cleanup: {final_cleanup_error}")
    
    async def _send_tracking_message(self, message_type, data):
        """Send tracking message using template from database"""
        try:
            # Get message template
            msg_template = self.db.get_tracking_message(message_type)
            
            if not msg_template:
                logger.warning(f"No template found for {message_type}")
                return
            
            # Format message with data
            message_text = msg_template['message_text'].format(**data)
            image_path = msg_template.get('image_path')
            
            # Get all telegram channels
            channels = self.db.get_telegram_channels()
            
            if not channels:
                logger.warning("No telegram channels configured")
                return
            
            # Send to all channels
            from telegram import Bot
            from io import BytesIO
            
            for channel in channels:
                try:
                    bot = Bot(token=channel['token'])
                    chat_id = channel['chat_id']
                    
                    if image_path and os.path.exists(image_path):
                        # Send with image
                        with open(image_path, 'rb') as img_file:
                            await bot.send_photo(
                                chat_id=chat_id,
                                photo=img_file,
                                caption=message_text
                            )
                    else:
                        # Send text only
                        await bot.send_message(
                            chat_id=chat_id,
                            text=message_text
                        )
                    
                    logger.info(f"✅ Sent {message_type} message to {channel.get('channel_name', 'Unknown')}")
                    
                except Exception as e:
                    logger.error(f"Failed to send to channel {channel.get('channel_name')}: {e}")
            
        except Exception as e:
            logger.error(f"Error sending tracking message: {e}")
            import traceback
            traceback.print_exc()

def main():
    # Setup event loop for asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    root = tk.Tk()
    app = SPXSmartGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
