"""
SPX Smart - VPS/headless entry point.

Runs the trading system and Flask webhook without the Tkinter GUI.
"""
import asyncio
import logging
import threading
from logging.handlers import RotatingFileHandler
from datetime import datetime
from zoneinfo import ZoneInfo

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
RIYADH_TZ = ZoneInfo("Asia/Riyadh")


class HeadlessRuntime:
    def __init__(self, loop):
        self.loop = loop
        self.db = DatabaseManager()
        self.trading_system = TradingSystem()
        self.trading_system.telegram.db = self.db
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

    def reload_telegram_channels(self):
        self.trading_system.telegram.reload_channels()

    async def alert_loop(self):
        logger.info("Telegram scheduled alert loop started")
        while True:
            try:
                now = datetime.now(RIYADH_TZ)
                current_time = now.strftime('%H:%M')
                current_date = now.strftime('%Y-%m-%d')
                for alert in self.db.get_active_alerts():
                    if alert['alert_time'] != current_time:
                        continue

                    last_sent = alert.get('last_sent')
                    should_send = False
                    if alert['repeat_mode'] == 'daily':
                        should_send = not last_sent or not last_sent.startswith(current_date)
                    else:
                        should_send = not last_sent

                    if should_send:
                        self.trading_system.telegram.send_alert_message(alert['message'])
                        self.db.update_alert_last_sent(alert['id'])
                        if alert['repeat_mode'] != 'daily':
                            self.db.toggle_alert_active(alert['id'], False)
                        logger.info("Sent scheduled Telegram alert #%s", alert['id'])
            except Exception:
                logger.exception("Scheduled alert loop error")
            await asyncio.sleep(30)


async def start_runtime(runtime):
    ok = await runtime.trading_system.start()
    runtime.system_running = ok
    if not ok:
        raise RuntimeError("Trading system failed to start")


def main():
    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    loop_thread = threading.Thread(target=run_loop, daemon=True)
    loop_thread.start()

    runtime = HeadlessRuntime(loop)
    asyncio.run_coroutine_threadsafe(start_runtime(runtime), loop).result()
    asyncio.run_coroutine_threadsafe(runtime.alert_loop(), loop)
    webhook_server.set_gui(runtime)

    logger.info("SPX Smart server started")
    try:
        webhook_server.run_webhook_server()
    finally:
        loop.call_soon_threadsafe(loop.stop)


if __name__ == "__main__":
    main()
