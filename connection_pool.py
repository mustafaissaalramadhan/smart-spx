"""
Connection Pool Manager for Tracking
إدارة Pool الاتصالات للتتبع - لمنع التضارب والبيانات الخاطئة
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import config
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class TrackingConnection:
    """Represents a single tracking connection"""
    conn_id: int
    symbol: str
    ibkr_client: any  # IBKRClient instance
    active_trades: List[str]  # List of trade IDs being tracked
    created_at: datetime
    is_reserve: bool = False
    
    def is_available(self) -> bool:
        """Check if connection can accept more trades"""
        return len(self.active_trades) < config.MAX_TRADES_PER_CONNECTION
    
    def add_trade(self, trade_id: str) -> bool:
        """Add a trade to this connection"""
        if not self.is_available():
            return False
        self.active_trades.append(trade_id)
        logger.info(f"➕ Connection {self.conn_id} ({self.symbol}): Added trade {trade_id} ({len(self.active_trades)}/{config.MAX_TRADES_PER_CONNECTION})")
        return True
    
    def remove_trade(self, trade_id: str) -> bool:
        """Remove a trade from this connection"""
        if trade_id in self.active_trades:
            self.active_trades.remove(trade_id)
            logger.info(f"➖ Connection {self.conn_id} ({self.symbol}): Removed trade {trade_id} ({len(self.active_trades)}/{config.MAX_TRADES_PER_CONNECTION})")
            return True
        return False
    
    def get_load(self) -> float:
        """Get connection load percentage"""
        return len(self.active_trades) / config.MAX_TRADES_PER_CONNECTION * 100


class ConnectionPoolManager:
    """
    إدارة Pool اتصالات التتبع لمنع التضارب
    - 4 شركات × 4 اتصالات = 16 اتصال رئيسي
    - 2 اتصال احتياطي للتوسع
    - كل اتصال يتتبع صفقتين كحد أقصى
    """
    
    def __init__(self):
        self.pools: Dict[str, List[TrackingConnection]] = {
            'SPX': [],
            'NDX': [],
            'SPY': [],
            'QQQ': []
        }
        self.reserve_pool: List[TrackingConnection] = []
        self.trade_to_connection: Dict[str, TrackingConnection] = {}  # Map trade_id → connection
        self.initialized = False
        self.connection_counter = 0
        
    async def initialize(self, ibkr_clients: Dict[str, any]):
        """
        Initialize the connection pool
        
        Args:
            ibkr_clients: Dict of {symbol: IBKRClient} - main connections for each symbol
        """
        logger.info(f"🔧 Initializing Connection Pool Manager...")
        
        # Create 4 tracking connections per symbol (total: 16)
        for symbol in ['SPX', 'NDX', 'SPY', 'QQQ']:
            if symbol not in ibkr_clients:
                logger.warning(f"⚠️ No IBKR client for {symbol}, skipping pool creation")
                continue
            
            base_client = ibkr_clients[symbol]
            
            for i in range(config.TRACKING_CONNECTIONS_PER_SYMBOL):
                self.connection_counter += 1
                
                # Create new IBKR client for tracking (with unique client ID)
                from ibkr_client import IBKRClient
                tracking_client = IBKRClient(base_client_id=1000 + self.connection_counter)
                
                # Connect
                try:
                    await tracking_client.connect()
                    
                    conn = TrackingConnection(
                        conn_id=self.connection_counter,
                        symbol=symbol,
                        ibkr_client=tracking_client,
                        active_trades=[],
                        created_at=datetime.now(),
                        is_reserve=False
                    )
                    
                    self.pools[symbol].append(conn)
                    logger.info(f"✅ Created tracking connection #{self.connection_counter} for {symbol}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to create tracking connection for {symbol}: {e}")
        
        # Create reserve connections
        for i in range(config.RESERVE_CONNECTIONS):
            self.connection_counter += 1
            
            try:
                from ibkr_client import IBKRClient
                reserve_client = IBKRClient(base_client_id=2000 + self.connection_counter)
                await reserve_client.connect()
                
                conn = TrackingConnection(
                    conn_id=self.connection_counter,
                    symbol='RESERVE',
                    ibkr_client=reserve_client,
                    active_trades=[],
                    created_at=datetime.now(),
                    is_reserve=True
                )
                
                self.reserve_pool.append(conn)
                logger.info(f"✅ Created reserve connection #{self.connection_counter}")
                
            except Exception as e:
                logger.error(f"❌ Failed to create reserve connection: {e}")
        
        self.initialized = True
        self.log_stats()
        logger.info(f"✅ Connection Pool initialized successfully!")
    
    def get_available_connection(self, symbol: str) -> Optional[TrackingConnection]:
        """
        Get an available connection for a symbol
        
        Args:
            symbol: Symbol (SPX, NDX, SPY, QQQ)
            
        Returns:
            Available TrackingConnection or None
        """
        if not self.initialized:
            logger.error("❌ Connection Pool not initialized!")
            return None
        
        # Try to find available connection in symbol pool
        for conn in self.pools.get(symbol, []):
            if conn.is_available():
                logger.info(f"🔍 Found available connection #{conn.conn_id} for {symbol} (load: {conn.get_load():.0f}%)")
                return conn
        
        # No available connection in symbol pool - try reserve
        logger.warning(f"⚠️ No available connections for {symbol}, trying reserve pool...")
        
        for conn in self.reserve_pool:
            if conn.is_available():
                logger.info(f"🔍 Using reserve connection #{conn.conn_id} for {symbol}")
                conn.symbol = symbol  # Assign to symbol
                return conn
        
        # All connections full!
        logger.error(f"❌ All tracking connections full for {symbol}! Cannot track more trades.")
        return None
    
    def assign_trade(self, trade_id: str, symbol: str) -> Optional[TrackingConnection]:
        """
        Assign a trade to an available connection
        
        Args:
            trade_id: Unique trade ID
            symbol: Symbol (SPX, NDX, SPY, QQQ)
            
        Returns:
            Assigned TrackingConnection or None
        """
        # Get available connection
        conn = self.get_available_connection(symbol)
        
        if conn is None:
            logger.error(f"❌ Cannot assign trade {trade_id} - no available connections")
            return None
        
        # Add trade to connection
        success = conn.add_trade(trade_id)
        
        if success:
            self.trade_to_connection[trade_id] = conn
            logger.info(f"✅ Assigned trade {trade_id} to connection #{conn.conn_id}")
            return conn
        
        return None
    
    def release_trade(self, trade_id: str) -> bool:
        """
        Release a trade from its connection
        
        Args:
            trade_id: Trade ID to release
            
        Returns:
            True if released successfully
        """
        if trade_id not in self.trade_to_connection:
            logger.warning(f"⚠️ Trade {trade_id} not found in connection map")
            return False
        
        conn = self.trade_to_connection[trade_id]
        success = conn.remove_trade(trade_id)
        
        if success:
            del self.trade_to_connection[trade_id]
            logger.info(f"✅ Released trade {trade_id} from connection #{conn.conn_id}")
            return True
        
        return False
    
    def get_connection_for_trade(self, trade_id: str) -> Optional[TrackingConnection]:
        """Get the connection assigned to a specific trade"""
        return self.trade_to_connection.get(trade_id)
    
    def log_stats(self):
        """Log pool statistics"""
        logger.info("=" * 70)
        logger.info("📊 Connection Pool Statistics")
        logger.info("=" * 70)
        
        for symbol, conns in self.pools.items():
            total = len(conns)
            available = sum(1 for c in conns if c.is_available())
            full = total - available
            total_trades = sum(len(c.active_trades) for c in conns)
            
            logger.info(f"{symbol:>4}: {total} connections | {available} available | {full} full | {total_trades} trades")
        
        reserve_available = sum(1 for c in self.reserve_pool if c.is_available())
        reserve_total_trades = sum(len(c.active_trades) for c in self.reserve_pool)
        
        logger.info(f"{'RSRV':>4}: {len(self.reserve_pool)} connections | {reserve_available} available | {reserve_total_trades} trades")
        logger.info("=" * 70)
        
        # Log capacity
        total_capacity = (
            sum(len(conns) for conns in self.pools.values()) + len(self.reserve_pool)
        ) * config.MAX_TRADES_PER_CONNECTION
        
        total_active = sum(len(c.active_trades) for conns in self.pools.values() for c in conns)
        total_active += sum(len(c.active_trades) for c in self.reserve_pool)
        
        utilization = (total_active / total_capacity * 100) if total_capacity > 0 else 0
        
        logger.info(f"📊 Total Capacity: {total_capacity} trades | Active: {total_active} | Utilization: {utilization:.1f}%")
        logger.info("=" * 70)
    
    async def cleanup(self):
        """Cleanup all connections"""
        logger.info("🧹 Cleaning up Connection Pool...")
        
        # Disconnect all connections
        all_connections = []
        
        for conns in self.pools.values():
            all_connections.extend(conns)
        
        all_connections.extend(self.reserve_pool)
        
        for conn in all_connections:
            try:
                if conn.ibkr_client.connected:
                    conn.ibkr_client.ib.disconnect()
                    logger.info(f"✅ Disconnected connection #{conn.conn_id}")
            except Exception as e:
                logger.error(f"❌ Error disconnecting connection #{conn.conn_id}: {e}")
        
        self.pools.clear()
        self.reserve_pool.clear()
        self.trade_to_connection.clear()
        self.initialized = False
        
        logger.info("✅ Connection Pool cleaned up")
