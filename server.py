"""
SPX Smart - VPS/headless entry point.

Runs the trading system and Flask webhook without the Tkinter GUI.
"""
import asyncio
import logging
import threading
from logging.handlers import RotatingFileHandler

import config
import webhook_server
from database import DatabaseManager
from trading_system import TradingSystem


logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT,
    handlers=[
        RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class HeadlessRuntime:
    def __init__(self, loop):
        self.loop = loop
        self.db = DatabaseManager()
        self.trading_system = TradingSystem()
        self.system_running = False

    def trigger_manual_button(self, symbol, signal_type, quantity=None):
        qty = quantity if quantity and quantity > 0 else 1
        logger.info("Webhook signal queued: %s %s x%s", symbol, signal_type, qty)
        future = asyncio.run_coroutine_threadsafe(
            self.trading_system.process_signal(symbol, signal_type, qty),
            self.loop
        )
        future.add_done_callback(self._log_signal_result)

    def _log_signal_result(self, future):
        try:
            future.result()
        except Exception:
            logger.exception("Webhook signal processing failed")


async def start_runtime(runtime):
    ok = await runtime.trading_system.start()
    runtime.system_running = ok
    if not ok:
        raise RuntimeError("Trading system failed to start")


def main():
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()

    runtime = HeadlessRuntime(loop)
    asyncio.run_coroutine_threadsafe(start_runtime(runtime), loop).result()
    webhook_server.set_gui(runtime)

    logger.info("SPX Smart server started")
    try:
        webhook_server.run_webhook_server()
    finally:
        loop.call_soon_threadsafe(loop.stop)


if __name__ == "__main__":
    main()
