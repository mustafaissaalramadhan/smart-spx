"""
SPX Smart - Main Entry Point
"""
import sys
import os
import asyncio

# Setup event loop BEFORE importing anything else
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from main_gui import main
    main()
