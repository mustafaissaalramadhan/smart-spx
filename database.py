"""
SPX Smart - Database Manager
ط¥ط¯ط§ط±ط© ظ‚ط§ط¹ط¯ط© ط§ظ„ط¨ظٹط§ظ†ط§طھ ظ„ظ„طµظپظ‚ط§طھ ظˆط§ظ„ط¥ط´ط§ط±ط§طھ
"""
import os
import shutil
import sqlite3
from datetime import datetime
from typing import Optional, Dict, List
import config

class DatabaseManager:
    CONNECT_TIMEOUT_SECONDS = 30
    BUSY_TIMEOUT_MS = 30000

    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self.prepare_database_file()
        self.configure_database()
        self.init_database()

    def connect(self):
        """Create a SQLite connection with lock-friendly defaults."""
        conn = sqlite3.connect(self.db_path, timeout=self.CONNECT_TIMEOUT_SECONDS)
        conn.execute(f'PRAGMA busy_timeout = {self.BUSY_TIMEOUT_MS}')
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    def backup_database_files(self, reason: str):
        """Back up the database and SQLite sidecar files before recovery attempts."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join('db_backups', f'{reason}_{timestamp}')
        os.makedirs(backup_dir, exist_ok=True)

        for suffix in ('', '-journal', '-wal', '-shm'):
            src = self.db_path + suffix
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(backup_dir, os.path.basename(src)))

        return backup_dir

    def prepare_database_file(self):
        """Let SQLite finish any pending recovery before the app starts."""
        if not os.path.exists(self.db_path):
            return

        sidecar_exists = any(os.path.exists(self.db_path + suffix) for suffix in ('-journal', '-wal', '-shm'))
        if sidecar_exists:
            self.backup_database_files('startup_sidecar')

        conn = None
        try:
            conn = self.connect()
            result = conn.execute('PRAGMA integrity_check').fetchone()
            if not result or result[0].lower() != 'ok':
                self.backup_database_files('integrity_problem')
                raise sqlite3.DatabaseError(f'Database integrity check failed: {result[0] if result else "no result"}')
        except sqlite3.OperationalError:
            self.backup_database_files('startup_operational_error')
            raise
        finally:
            if conn:
                conn.close()

    def configure_database(self):
        """Use WAL mode to reduce read/write blocking between app tasks."""
        conn = self.connect()
        try:
            conn.execute('PRAGMA journal_mode = WAL')
            conn.execute('PRAGMA synchronous = NORMAL')
            conn.commit()
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize all required tables"""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trade_type TEXT NOT NULL,
                option_contract TEXT NOT NULL,
                strike_price REAL NOT NULL,
                entry_price REAL NOT NULL,
                entry_time TEXT NOT NULL,
                highest_price REAL,
                current_price REAL,
                exit_price REAL,
                exit_time TEXT,
                profit_loss REAL,
                status TEXT NOT NULL,
                last_update TEXT,
                track_count INTEGER DEFAULT 0
            )
        ''')
        
        # Add track_count column if it doesn't exist (for existing databases)
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN track_count INTEGER DEFAULT 0')
        except:
            pass  # Column already exists
        
        # Add expiry column if it doesn't exist (for existing databases)
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN expiry TEXT')
        except:
            pass  # Column already exists
        
        # Add bid column if it doesn't exist
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN bid REAL DEFAULT 0')
        except:
            pass
        
        # Add ask column if it doesn't exist
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN ask REAL DEFAULT 0')
        except:
            pass
        
        # Add quantity columns for partial closing
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN quantity INTEGER DEFAULT 1')
        except:
            pass
        
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN pending_quantity INTEGER DEFAULT 1')
        except:
            pass
        
        # Price tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER NOT NULL,
                price REAL NOT NULL,
                bid REAL,
                ask REAL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (trade_id) REFERENCES trades (id)
            )
        ''')
        
        # Signals table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                received_time TEXT NOT NULL,
                processed BOOLEAN DEFAULT 0
            )
        ''')
        
        # Risk settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS risk_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                stop_loss_type TEXT,
                stop_loss_value REAL,
                trailing_stop_type TEXT,
                trailing_stop_value REAL,
                capital_protection_type TEXT,
                capital_protection_value REAL,
                profit_target_type TEXT,
                profit_target_value REAL,
                last_updated TEXT
            )
        ''')
        
        # Telegram channels table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS telegram_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                channel_name TEXT,
                symbol TEXT,
                channel_link TEXT,
                active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Add channel_link column if it doesn't exist (for existing databases)
        try:
            cursor.execute('ALTER TABLE telegram_channels ADD COLUMN channel_link TEXT')
        except:
            pass  # Column already exists
        
        # Telegram alerts/reminders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS telegram_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_time TEXT NOT NULL,
                message TEXT NOT NULL,
                repeat_mode TEXT NOT NULL,
                active BOOLEAN DEFAULT 1,
                last_sent TEXT,
                created_time TEXT NOT NULL
            )
        ''')
        
        # Tracking messages templates table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tracking_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_type TEXT NOT NULL UNIQUE,
                message_text TEXT NOT NULL,
                image_path TEXT,
                active BOOLEAN DEFAULT 1,
                last_updated TEXT
            )
        ''')
        
        # Auto cleanup settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cleanup_settings (
                id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT 0,
                frequency TEXT DEFAULT 'monthly',
                last_cleanup TEXT,
                next_cleanup TEXT,
                days_to_keep INTEGER DEFAULT 30
            )
        ''')
        
        # Initialize default cleanup settings if not exist
        cursor.execute("SELECT COUNT(*) FROM cleanup_settings")
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO cleanup_settings (id, enabled, frequency, last_cleanup, next_cleanup, days_to_keep)
                VALUES (1, 0, 'monthly', NULL, NULL, 30)
            ''')
        
        # Initialize default tracking messages if not exist
        cursor.execute("SELECT COUNT(*) FROM tracking_messages")
        if cursor.fetchone()[0] == 0:
            default_messages = [
                ('entry', '''ًں“ٹ ط¹ظ‚ط¯ {type} ظ…ظ‚طھط±ط­   SPX

ًں—“ ط¨طھط§ط±ظٹط® : ط§ظ„ظٹظˆظ…

ًںژ¯ ط§ط³طھط±ط§ظٹظƒ : {strike}

ًں’° ط­ط· ط£ظ…ط± ط§ظ„طھظ†ظپظٹط° ط¨ط§ظ„ط¹ظ‚ط¯ ط¨ط³ط¹ط± : {entry_price}

ًں’،ظٹظپط¶ظ„ ط¬ظ†ظٹ ط§ظ„ط±ط¨ط­ ط¹ظ„ظ‰ 50 - 100
ظ…ط¹ ط±ظپط¹ ط§ظ„ظˆظ‚ظپ ظ„ط¶ظ…ط§ظ† ط§ظ„ط±ط¨ط­

ظ‚ط±ط§ط± ط§ظ„ط¯ط®ظˆظ„ ظˆط§ظ„ط®ط±ظˆط¬ ظ…ط³ط¤ظˆظ„ظٹطھظƒ ط§ظ„ط´ط®طµظٹط© ط¨ط§ظ„ظƒط§ظ…ظ„.
ظ‡ط°ظ‡ ط§ظ„طھظˆطµظٹط© ظ„ط£ط؛ط±ط§ط¶ طھط¹ظ„ظٹظ…ظٹط© ظˆظپظ†ظٹط© ظپظ‚ط· ظˆظ„ط§ طھظڈط¹ط¯ ظ†طµظٹط­ط© ظ…ط§ظ„ظٹط© ظ…ط¨ط§ط´ط±ط©.

ًں“ٹ {type_en}
ًں—“ Date: Today
ًںژ¯ Strike: {strike}
ًں’° Buy Order Price : {entry_price}

ًں’،Profit targets are typically set at 50, or 100, with a stop-loss order raised to guarantee profitability.
The decision to enter and exit is entirely your personal responsibility.
This recommendation is for educational and technical purposes only and does not constitute direct financial advice.

ط¹ظ‚ط¯ ط§ظ„ظٹظˆظ… ط¨ط§ظ„ظ…ط¬ظ…ظˆط¹ط© âœ…''', None, 1),
                ('update', '''ًں”” ط§ط´ط¹ط§ط± طھط­ط¯ظٹط« ط§ط±ط¨ط§ط­ ط¨ط§ظ„ط¹ظ‚ط¯
-----------------------------

ًں“‹ ط§ظ„ط¹ظ‚ط¯:
SPXW ${strike} {date} {type}

ًں’µ ط³ط¹ط± ط§ظ„ط¯ط®ظˆظ„: {entry_price} ط¯ظˆظ„ط§ط±
ًں’µ ط§ظ„ط³ط¹ط± ط§ظ„ط­ط§ظ„ظٹ: {current_price} ط¯ظˆظ„ط§ط±

ًں“ˆ ط§ظ„ط±ط¨ط­: {profit_usd} ط¯ظˆظ„ط§ط± ({profit_sar} ï·¼)

âڑ ï¸ڈ ظٹظپط¶ظ„ ط§ظ„ط®ط±ظˆط¬ ط¨ط±ط¨ط­ 100ًں’²

ًں“‹ Option :
SPXW ${strike} {date} {type}

ًں’µ Entry: {entry_price}
ًں’µ Now: {current_price}

ًں“ˆ Profit: {profit_usd}

âڑ ï¸ڈ Suggestion: Consider taking profits around +$100.

ط¹ظ‚ط¯ ط§ظ„ظٹظˆظ… ط¨ط§ظ„ظ…ط¬ظ…ظˆط¹ط© âœ…''', None, 1),
                ('target', '''ًںژ¯ طھظ… طھط­ظ‚ظٹظ‚ ط§ظ„ظ‡ط¯ظپ
-----------------------------

ًں“‹ ط§ظ„ط¹ظ‚ط¯:
SPXW ${strike} {date} {type}

ًں’µ ط³ط¹ط± ط§ظ„ط¯ط®ظˆظ„: {entry_price} ط¯ظˆظ„ط§ط±
ًں’µ ط§ظ„ط³ط¹ط± ط§ظ„ظ†ظ‡ط§ط¦ظٹ: {current_price} ط¯ظˆظ„ط§ط±

ًں“ˆ ط§ظ„ط±ط¨ط­ ط§ظ„ظƒظ„ظٹ: {profit_usd} ط¯ظˆظ„ط§ط± ({profit_sar} ï·¼)

âœ… طھظ… طھط­ظ‚ظٹظ‚ ط§ظ„ظ‡ط¯ظپ ط¨ظ†ط¬ط§ط­!

ًں“‹ Option :
SPXW ${strike} {date} {type}

ًں’µ Entry: {entry_price}
ًں’µ Final: {current_price}

ًں“ˆ Total Profit: {profit_usd}

âœ… Target achieved successfully!

ط¹ظ‚ط¯ ط§ظ„ظٹظˆظ… ط¨ط§ظ„ظ…ط¬ظ…ظˆط¹ط© âœ…''', None, 1)
            ]
            
            cursor.executemany('''
                INSERT INTO tracking_messages (message_type, message_text, image_path, active)
                VALUES (?, ?, ?, ?)
            ''', default_messages)
        
        conn.commit()
        conn.close()
    
    # ==================== Trades Management ====================
    
    def create_trade(self, symbol: str, trade_type: str, option_contract: str,
                    strike_price: float, entry_price: float, expiry: str = None,
                    bid: float = None, ask: float = None, quantity: int = 1) -> int:
        """Create new trade with quantity support"""
        conn = self.connect()
        cursor = conn.cursor()
        
        entry_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            INSERT INTO trades (symbol, trade_type, option_contract, strike_price,
                              entry_price, entry_time, highest_price, current_price,
                              status, last_update, expiry, bid, ask, quantity, pending_quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, trade_type, option_contract, strike_price, entry_price,
              entry_time, entry_price, entry_price, 'ACTIVE', entry_time, 
              expiry, bid or 0, ask or 0, quantity, quantity))
        
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return trade_id
    
    def update_trade_price(self, trade_id: int, price: float, bid: float = None,
                          ask: float = None):
        """Update trade price and highest"""
        conn = self.connect()
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Get current highest
        cursor.execute('SELECT highest_price, track_count FROM trades WHERE id = ?', (trade_id,))
        result = cursor.fetchone()
        
        if result:
            current_highest = result[0]
            current_count = result[1] if result[1] else 0
            new_highest = max(current_highest, price)
            new_count = current_count + 1
            
            # Update trade
            cursor.execute('''
                UPDATE trades 
                SET highest_price = ?, current_price = ?, last_update = ?, 
                    track_count = ?, bid = ?, ask = ?
                WHERE id = ?
            ''', (new_highest, price, timestamp, new_count, bid or 0, ask or 0, trade_id))
            
            # Add price tracking
            cursor.execute('''
                INSERT INTO price_tracking (trade_id, price, bid, ask, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (trade_id, price, bid, ask, timestamp))
        
        conn.commit()
        conn.close()
    
    def close_trade(self, trade_id: int, exit_price: float, close_quantity: int = None):
        """Close trade fully or partially and calculate P/L"""
        conn = self.connect()
        cursor = conn.cursor()
        
        exit_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Get trade info
        cursor.execute('SELECT entry_price, highest_price, pending_quantity FROM trades WHERE id = ?', (trade_id,))
        result = cursor.fetchone()
        
        if result:
            entry_price = result[0]
            highest_price = result[1] if result[1] else entry_price
            pending_quantity = result[2] if result[2] else 1
            
            # If no quantity specified, close all
            if close_quantity is None or close_quantity >= pending_quantity:
                # Full close
                # Calculate profit based on highest price
                profit_usd = (highest_price - entry_price) * 100
                
                # If profit < $100, entire contract is a loss
                if profit_usd >= 100:
                    profit_loss = profit_usd
                else:
                    profit_loss = -(entry_price * 100)  # Negative for loss
                
                cursor.execute('''
                    UPDATE trades
                    SET exit_price = ?, exit_time = ?, profit_loss = ?, status = 'CLOSED', pending_quantity = 0
                    WHERE id = ?
                ''', (exit_price, exit_time, profit_loss, trade_id))
            else:
                # Partial close - only update pending_quantity
                new_pending = pending_quantity - close_quantity
                cursor.execute('''
                    UPDATE trades
                    SET pending_quantity = ?
                    WHERE id = ?
                ''', (new_pending, trade_id))
        
        conn.commit()
        conn.close()
    
    def get_active_trades(self, symbol: str = None) -> List[Dict]:
        """Get all active trades"""
        conn = self.connect()
        cursor = conn.cursor()
        
        if symbol:
            cursor.execute('''
                SELECT * FROM trades WHERE status = 'ACTIVE' AND symbol = ?
                ORDER BY entry_time DESC
            ''', (symbol,))
        else:
            cursor.execute('''
                SELECT * FROM trades WHERE status = 'ACTIVE'
                ORDER BY entry_time DESC
            ''')
        
        columns = [desc[0] for desc in cursor.description]
        trades = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return trades
    
    def get_closed_trades(self, symbol: str = None, date: str = None) -> List[Dict]:
        """Get closed trades"""
        conn = self.connect()
        cursor = conn.cursor()
        
        query = "SELECT * FROM trades WHERE status = 'CLOSED'"
        params = []
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        if date:
            query += " AND DATE(exit_time) = ?"
            params.append(date)
        
        query += " ORDER BY exit_time DESC"
        
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        trades = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return trades
    
    def get_trade_history(self, trade_id: int) -> List[Dict]:
        """Get price tracking history for a trade"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM price_tracking WHERE trade_id = ?
            ORDER BY timestamp ASC
        ''', (trade_id,))
        
        columns = [desc[0] for desc in cursor.description]
        history = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return history
    
    def clear_closed_trades(self, days_old: int = None) -> Dict:
        """Delete closed trades (and their tracking data)
        
        Args:
            days_old: If specified, only delete trades older than this many days
                     If None, delete all closed trades
        
        Returns:
            Dict with counts of deleted items
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        # Build query based on days_old parameter
        if days_old:
            cutoff_date = (datetime.now() - timedelta(days=days_old)).strftime('%Y-%m-%d')
            query = "SELECT id FROM trades WHERE status = 'CLOSED' AND DATE(exit_time) < ?"
            cursor.execute(query, (cutoff_date,))
        else:
            cursor.execute("SELECT id FROM trades WHERE status = 'CLOSED'")
        
        trade_ids = [row[0] for row in cursor.fetchall()]
        trade_count = len(trade_ids)
        
        # Delete price tracking data for closed trades
        tracking_count = 0
        if trade_ids:
            placeholders = ','.join('?' * len(trade_ids))
            cursor.execute(f"SELECT COUNT(*) FROM price_tracking WHERE trade_id IN ({placeholders})", trade_ids)
            tracking_count = cursor.fetchone()[0]
            
            cursor.execute(f"DELETE FROM price_tracking WHERE trade_id IN ({placeholders})", trade_ids)
        
        # Delete closed trades
        if days_old:
            cursor.execute("DELETE FROM trades WHERE status = 'CLOSED' AND DATE(exit_time) < ?", (cutoff_date,))
        else:
            cursor.execute("DELETE FROM trades WHERE status = 'CLOSED'")
        
        conn.commit()
        conn.close()
        
        return {
            'trades': trade_count,
            'tracking_records': tracking_count
        }
    
    def clear_old_signals(self, days_old: int = 30) -> int:
        """Delete signals older than specified days"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days_old)).strftime('%Y-%m-%d')
        
        cursor.execute("SELECT COUNT(*) FROM signals WHERE DATE(received_time) < ?", (cutoff_date,))
        count = cursor.fetchone()[0]
        
        cursor.execute("DELETE FROM signals WHERE DATE(received_time) < ?", (cutoff_date,))
        
        conn.commit()
        conn.close()
        
        return count
    
    def clear_old_alerts(self) -> int:
        """Delete old one-time alerts that have been sent"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM telegram_alerts 
            WHERE repeat_mode = 'once' AND last_sent IS NOT NULL
        """)
        count = cursor.fetchone()[0]
        
        cursor.execute("""
            DELETE FROM telegram_alerts 
            WHERE repeat_mode = 'once' AND last_sent IS NOT NULL
        """)
        
        conn.commit()
        conn.close()
        
        return count
    
    def perform_auto_cleanup(self, days_to_keep: int = 30) -> Dict:
        """Perform automatic cleanup based on settings
        
        Returns:
            Dict with statistics of what was cleaned
        """
        results = {
            'trades': 0,
            'tracking_records': 0,
            'signals': 0,
            'alerts': 0,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Clean old closed trades and their tracking
        trade_results = self.clear_closed_trades(days_old=days_to_keep)
        results['trades'] = trade_results['trades']
        results['tracking_records'] = trade_results['tracking_records']
        
        # Clean old signals
        results['signals'] = self.clear_old_signals(days_old=days_to_keep)
        
        # Clean sent one-time alerts
        results['alerts'] = self.clear_old_alerts()
        
        # Optimize database (VACUUM)
        conn = self.connect()
        conn.execute('VACUUM')
        conn.close()
        
        return results
    
    def get_cleanup_settings(self) -> Dict:
        """Get current cleanup settings"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM cleanup_settings WHERE id = 1')
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            return {
                'enabled': bool(result[1]),
                'frequency': result[2],
                'last_cleanup': result[3],
                'next_cleanup': result[4],
                'days_to_keep': result[5]
            }
        return None
    
    def save_cleanup_settings(self, enabled: bool, frequency: str, next_cleanup: str, days_to_keep: int):
        """Save cleanup settings"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE cleanup_settings 
            SET enabled = ?, frequency = ?, next_cleanup = ?, days_to_keep = ?
            WHERE id = 1
        ''', (enabled, frequency, next_cleanup, days_to_keep))
        
        conn.commit()
        conn.close()
    
    def update_last_cleanup(self):
        """Update last cleanup timestamp"""
        conn = self.connect()
        cursor = conn.cursor()
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('UPDATE cleanup_settings SET last_cleanup = ? WHERE id = 1', (now,))
        
        conn.commit()
        conn.close()
    
    # ==================== Signals Management ====================
    
    def add_signal(self, symbol: str, signal_type: str) -> int:
        """Add new signal"""
        conn = self.connect()
        cursor = conn.cursor()
        
        received_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            INSERT INTO signals (symbol, signal_type, received_time, processed)
            VALUES (?, ?, ?, ?)
        ''', (symbol, signal_type, received_time, False))
        
        signal_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return signal_id
    
    def mark_signal_processed(self, signal_id: int):
        """Mark signal as processed"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE signals SET processed = 1 WHERE id = ?', (signal_id,))
        
        conn.commit()
        conn.close()
    
    def get_signal_count(self, date: str = None) -> Dict:
        """Get signal count"""
        conn = self.connect()
        cursor = conn.cursor()
        
        query = "SELECT signal_type, COUNT(*) as count FROM signals"
        params = []
        
        if date:
            query += " WHERE DATE(received_time) = ?"
            params.append(date)
        
        query += " GROUP BY signal_type"
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        signal_counts = {'CALL': 0, 'PUT': 0, 'total': 0}
        for row in results:
            signal_counts[row[0]] = row[1]
            signal_counts['total'] += row[1]
        
        conn.close()
        return signal_counts
    
    # ==================== Risk Settings Management ====================
    
    def save_risk_settings(self, symbol: str, settings: Dict):
        """Save risk settings for a symbol"""
        conn = self.connect()
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            INSERT OR REPLACE INTO risk_settings
            (symbol, stop_loss_type, stop_loss_value, trailing_stop_type, trailing_stop_value,
             capital_protection_type, capital_protection_value, profit_target_type, profit_target_value,
             last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            symbol,
            settings.get('stop_loss', {}).get('type'),
            settings.get('stop_loss', {}).get('value'),
            settings.get('trailing_stop', {}).get('type'),
            settings.get('trailing_stop', {}).get('value'),
            settings.get('capital_protection', {}).get('type'),
            settings.get('capital_protection', {}).get('value'),
            settings.get('profit_target', {}).get('type'),
            settings.get('profit_target', {}).get('value'),
            timestamp
        ))
        
        conn.commit()
        conn.close()
    
    def reset_all_risk_settings(self):
        """Reset all risk settings to NONE for all symbols"""
        try:
            for symbol in config.SUPPORTED_SYMBOLS:
                self.save_risk_settings(symbol, config.DEFAULT_RISK_SETTINGS.copy())
        except Exception as e:
            print(f"Error resetting risk settings: {e}")
    
    def save_risk_setting(self, symbol: str, risk_type: str, type_val: str, value: float):
        """Save individual risk setting"""
        # Get current settings
        current = self.get_risk_settings(symbol)
        
        # Update specific risk type
        current[risk_type] = {'type': type_val, 'value': value}
        
        # Save all settings
        self.save_risk_settings(symbol, current)
    
    def get_risk_settings(self, symbol: str) -> Dict:
        """Get risk settings for a symbol"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM risk_settings WHERE symbol = ?', (symbol,))
        result = cursor.fetchone()
        
        if result:
            settings = {
                'stop_loss': {'type': result[2], 'value': result[3]},
                'trailing_stop': {'type': result[4], 'value': result[5]},
                'capital_protection': {'type': result[6], 'value': result[7]},
                'profit_target': {'type': result[8], 'value': result[9]}
            }
        else:
            settings = config.DEFAULT_RISK_SETTINGS.copy()
        
        conn.close()
        return settings
    
    # ==================== Statistics ====================
    
    def get_daily_summary(self, date: str = None) -> Dict:
        """Get daily summary"""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
        
        conn = self.connect()
        cursor = conn.cursor()
        
        # Get totals
        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit_loss >= ? THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN profit_loss < ? THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN profit_loss >= ? THEN profit_loss ELSE 0 END) as total_profit,
                SUM(CASE WHEN profit_loss < ? THEN profit_loss ELSE 0 END) as total_loss
            FROM trades
            WHERE DATE(exit_time) = ? AND status = 'CLOSED'
        ''', (config.MIN_PROFIT_FOR_WIN, config.MIN_PROFIT_FOR_WIN,
              config.MIN_PROFIT_FOR_WIN, config.MIN_PROFIT_FOR_WIN, date))
        
        result = cursor.fetchone()
        
        summary = {
            'date': date,
            'total_trades': result[0] or 0,
            'wins': result[1] or 0,
            'losses': result[2] or 0,
            'total_profit': result[3] or 0.0,
            'total_loss': result[4] or 0.0,
            'net_profit': (result[3] or 0.0) + (result[4] or 0.0)
        }
        
        conn.close()
        return summary

    # ==================== Telegram Channels Management ====================
    
    def add_telegram_channel(self, token: str, chat_id: str, channel_name: str, symbol: str, channel_link: str = '') -> int:
        """Add new telegram channel"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO telegram_channels (token, chat_id, channel_name, symbol, channel_link, active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (token, chat_id, channel_name, symbol, channel_link))
        
        channel_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return channel_id
    
    def update_telegram_channel(self, channel_id: int, token: str, chat_id: str, 
                               channel_name: str, symbol: str, channel_link: str = ''):
        """Update telegram channel"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE telegram_channels
            SET token = ?, chat_id = ?, channel_name = ?, symbol = ?, channel_link = ?
            WHERE id = ?
        ''', (token, chat_id, channel_name, symbol, channel_link, channel_id))
        
        conn.commit()
        conn.close()
    
    def delete_telegram_channel(self, channel_id: int):
        """Delete telegram channel"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM telegram_channels WHERE id = ?', (channel_id,))
        
        conn.commit()
        conn.close()
    
    def get_all_telegram_channels(self) -> List[Dict]:
        """Get all telegram channels"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM telegram_channels WHERE active = 1 ORDER BY symbol')
        columns = [desc[0] for desc in cursor.description]
        channels = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return channels
    
    def get_telegram_channel_by_symbol(self, symbol: str) -> Optional[Dict]:
        """Get telegram channel for a specific symbol"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM telegram_channels WHERE symbol = ? AND active = 1', (symbol,))
        result = cursor.fetchone()
        
        if result:
            columns = [desc[0] for desc in cursor.description]
            channel = dict(zip(columns, result))
        else:
            channel = None
        
        conn.close()
        return channel
    
    # ==================== Telegram Alerts Management ====================
    
    def add_telegram_alert(self, alert_time: str, message: str, repeat_mode: str = 'once') -> int:
        """Add new telegram alert
        
        Args:
            alert_time: Time in HH:MM format (24-hour)
            message: Alert message to send
            repeat_mode: 'once' or 'daily'
        
        Returns:
            Alert ID
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO telegram_alerts (alert_time, message, repeat_mode, active, created_time)
            VALUES (?, ?, ?, 1, ?)
        ''', (alert_time, message, repeat_mode, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        alert_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return alert_id
    
    def update_telegram_alert(self, alert_id: int, alert_time: str, message: str, repeat_mode: str):
        """Update telegram alert"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE telegram_alerts
            SET alert_time = ?, message = ?, repeat_mode = ?
            WHERE id = ?
        ''', (alert_time, message, repeat_mode, alert_id))
        
        conn.commit()
        conn.close()
    
    def delete_telegram_alert(self, alert_id: int):
        """Delete telegram alert"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM telegram_alerts WHERE id = ?', (alert_id,))
        
        conn.commit()
        conn.close()
    
    def toggle_alert_active(self, alert_id: int, active: bool):
        """Toggle alert active status"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE telegram_alerts SET active = ? WHERE id = ?', (1 if active else 0, alert_id))
        
        conn.commit()
        conn.close()
    
    def get_all_telegram_alerts(self) -> List[Dict]:
        """Get all telegram alerts"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM telegram_alerts ORDER BY alert_time')
        columns = [desc[0] for desc in cursor.description]
        alerts = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return alerts
    
    def get_active_alerts(self) -> List[Dict]:
        """Get only active alerts"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM telegram_alerts WHERE active = 1 ORDER BY alert_time')
        columns = [desc[0] for desc in cursor.description]
        alerts = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return alerts
    
    def update_alert_last_sent(self, alert_id: int):
        """Update last sent time for alert"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE telegram_alerts
            SET last_sent = ?
            WHERE id = ?
        ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), alert_id))
        
        conn.commit()
        conn.close()
    
    # ==================== Tracking Messages Management ====================
    
    def get_tracking_message(self, message_type: str) -> Optional[Dict]:
        """Get tracking message template by type (entry/update/target)"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM tracking_messages WHERE message_type = ?', (message_type,))
        result = cursor.fetchone()
        
        if result:
            columns = [desc[0] for desc in cursor.description]
            message = dict(zip(columns, result))
        else:
            message = None
        
        conn.close()
        return message
    
    def update_tracking_message(self, message_type: str, message_text: str, image_path: str = None):
        """Update tracking message template"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE tracking_messages
            SET message_text = ?, image_path = ?, last_updated = ?
            WHERE message_type = ?
        ''', (message_text, image_path, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), message_type))
        
        conn.commit()
        conn.close()
    
    def get_all_tracking_messages(self) -> List[Dict]:
        """Get all tracking message templates"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM tracking_messages ORDER BY message_type')
        columns = [desc[0] for desc in cursor.description]
        messages = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return messages

