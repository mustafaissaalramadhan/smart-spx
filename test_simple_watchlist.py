"""
Test Simple Watchlist System
اختبار النظام المبسط
"""
import asyncio
import sys

# Fix for Python 3.14+
if sys.version_info >= (3, 14):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from simple_watchlist import SimpleWatchlistManager
import config


async def test_simple_watchlist():
    """Test the simple watchlist system"""
    
    print("="*80)
    print("🧪 Testing Simple Watchlist System")
    print("="*80)
    
    # Create manager
    manager = SimpleWatchlistManager()
    
    # Start system
    print("\n1️⃣ Starting system...")
    success = await manager.start()
    
    if not success:
        print("❌ Failed to start system")
        return
    
    print("✅ System started successfully")
    
    try:
        # Test 1: Get SPX price
        print("\n2️⃣ Testing price fetch for SPX...")
        price = await manager.get_current_price('SPX')
        print(f"✅ SPX Price: ${price:.2f}")
        
        # Test 2: Fetch a single batch of contracts
        print("\n3️⃣ Testing single batch fetch (5 CALL contracts)...")
        
        # Get 0DTE expiry
        from ibkr_client import IBKRClient
        ibkr = IBKRClient()
        await ibkr.connect_async()
        expiry = await ibkr.get_expiry_date()
        print(f"✅ Using expiry: {expiry}")
        await ibkr.disconnect_async()
        
        # Calculate ATM strike
        strike_interval = config.STRIKE_INTERVALS['SPX']
        atm_strike = int(round(price / strike_interval) * strike_interval)
        
        print(f"📊 Fetching batch starting at strike {atm_strike}...")
        batch = await manager.fetch_contracts_batch('SPX', expiry, 'CALL', atm_strike, batch_size=5)
        
        print(f"✅ Fetched {len(batch)} contracts:")
        for contract in batch:
            bid = contract['bid']
            ask = contract['ask']
            strike = contract['strike']
            in_range = "✅" if config.MONITORING_RANGE_MIN <= ask <= config.MONITORING_RANGE_MAX else "❌"
            print(f"   {in_range} Strike {strike}: Bid ${bid:.2f}, Ask ${ask:.2f}")
        
        # Test 3: Find contracts in range
        print("\n4️⃣ Testing smart search (find contracts in range $1-$7)...")
        call_contracts = await manager.find_contracts_in_range(
            'SPX', expiry, 'CALL',
            config.MONITORING_RANGE_MIN,
            config.MONITORING_RANGE_MAX,
            max_batches=10
        )
        
        print(f"✅ Found {len(call_contracts)} CALL contracts in range:")
        for i, contract in enumerate(call_contracts[:5], 1):  # Show top 5
            bid = contract['bid']
            ask = contract['ask']
            strike = contract['strike']
            print(f"   {i}. Strike {strike}: Bid ${bid:.2f}, Ask ${ask:.2f}")
        
        # Test 4: Update prices
        print("\n5️⃣ Testing price update for existing contracts...")
        await asyncio.sleep(2)  # Wait 2 seconds
        updated = await manager.update_contracts_prices('SPX', 'CALL')
        
        print(f"✅ Updated {len(updated)} contracts:")
        for i, contract in enumerate(updated[:5], 1):  # Show top 5
            bid = contract['bid']
            ask = contract['ask']
            strike = contract['strike']
            print(f"   {i}. Strike {strike}: Bid ${bid:.2f}, Ask ${ask:.2f}")
        
        print("\n" + "="*80)
        print("✅ All tests passed!")
        print("="*80)
        
    finally:
        # Stop system
        print("\n6️⃣ Stopping system...")
        await manager.stop()
        print("✅ System stopped")


if __name__ == "__main__":
    asyncio.run(test_simple_watchlist())
