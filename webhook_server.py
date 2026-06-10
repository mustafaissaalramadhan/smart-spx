"""
SPX Smart - Webhook Server
خادم Webhook لاستقبال الإشارات من TradingView
"""
from flask import Flask, request, jsonify, Response, redirect
import asyncio
from datetime import datetime
import html
import hmac
import config
import logging
import subprocess
import time
import requests
from database import DatabaseManager

logger = logging.getLogger(__name__)

app = Flask(__name__)
gui_instance = None  # Store GUI instance to trigger manual buttons
ngrok_process = None
webhook_url = None
webhook_signal_counter = 0  # Track total signals received

def start_ngrok():
    """Start ngrok tunnel and get public webhook URL"""
    global ngrok_process, webhook_url
    
    try:
        logger.info("🌐 Starting Ngrok tunnel...")
        print("\n🌐 Starting Ngrok tunnel...")
        
        # Ensure stale ngrok state is cleared before starting
        try:
            subprocess.run(
                ['ngrok', 'kill'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception:
            pass

        # Start ngrok process
        ngrok_process = subprocess.Popen(
            ['ngrok', 'http', '5000', '--pooling-enabled'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        
        # Wait for ngrok to start
        logger.info("⏳ Waiting for Ngrok to initialize...")
        print("⏳ Waiting for Ngrok to initialize...")
        time.sleep(6)
        
        # Get public URL from ngrok API
        for attempt in range(10):
            try:
                response = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('tunnels') and len(data['tunnels']) > 0:
                        public_url = data['tunnels'][0]['public_url']
                        webhook_url = f"{public_url}/webhook"
                        
                        logger.info(f"\n{'='*70}")
                        logger.info(f"✅ NGROK TUNNEL ACTIVE!")
                        logger.info(f"{'='*70}")
                        logger.info(f"🌐 Public URL: {public_url}")
                        logger.info(f"📋 Webhook URL: {webhook_url}")
                        logger.info(f"🔗 Dashboard: http://127.0.0.1:4040")
                        logger.info(f"{'='*70}")
                        
                        print(f"\n{'='*70}")
                        print(f"✅ NGROK TUNNEL ACTIVE!")
                        print(f"{'='*70}")
                        print(f"🌐 Public URL: {public_url}")
                        print(f"📋 Webhook URL: {webhook_url}")
                        print(f"🔗 Dashboard: http://127.0.0.1:4040")
                        print(f"{'='*70}")
                        print(f"\n📋 COPY THIS URL TO TRADINGVIEW:")
                        print(f"   {webhook_url}")
                        print(f"{'='*70}\n")
                        
                        # Try to copy to clipboard
                        try:
                            import pyperclip
                            pyperclip.copy(webhook_url)
                            logger.info("✅ URL copied to clipboard!")
                            print("✅ URL copied to clipboard!\n")
                        except:
                            logger.warning("ℹ️  Install 'pyperclip' to auto-copy URL: pip install pyperclip")
                            print("ℹ️  Install 'pyperclip' to auto-copy URL: pip install pyperclip\n")
                        
                        return True
            except:
                pass
            
            time.sleep(1)
        
        logger.warning("⚠️  Could not get Ngrok URL from API")
        print("⚠️  Could not get Ngrok URL from API")
        return False
        
    except FileNotFoundError:
        logger.error("❌ Ngrok not found! Please install ngrok first.")
        logger.error("   Download from: https://ngrok.com/download")
        print("❌ Ngrok not found! Please install ngrok first.")
        print("   Download from: https://ngrok.com/download")
        return False
    except Exception as e:
        logger.error(f"❌ Error starting Ngrok: {e}")
        print(f"❌ Error starting Ngrok: {e}")
        return False

def stop_ngrok():
    """Stop ngrok tunnel"""
    global ngrok_process
    if ngrok_process:
        try:
            ngrok_process.terminate()
            logger.info("🛑 Ngrok tunnel stopped")
            print("\n🛑 Ngrok tunnel stopped")
        except:
            pass

    # Also ensure any remaining ngrok background process is terminated
    try:
        subprocess.run(
            ['ngrok', 'kill'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except Exception:
        pass

def get_webhook_url():
    """Get current webhook URL"""
    return webhook_url if webhook_url else "http://localhost:5000/webhook"

def set_gui(gui):
    """Set the GUI instance to trigger manual buttons"""
    global gui_instance
    gui_instance = gui
    logger.info(f"✅ GUI instance set for webhook triggers")

def _admin_enabled():
    return bool(config.ADMIN_USERNAME and config.ADMIN_PASSWORD)

def _check_admin_auth():
    auth = request.authorization
    if not auth or not _admin_enabled():
        return False
    return (
        hmac.compare_digest(auth.username, config.ADMIN_USERNAME)
        and hmac.compare_digest(auth.password, config.ADMIN_PASSWORD)
    )

def _admin_required():
    return Response(
        "Authentication required",
        401,
        {"WWW-Authenticate": 'Basic realm="SPX Smart Admin"'}
    )

def _reload_runtime_channels():
    if gui_instance and hasattr(gui_instance, 'reload_telegram_channels'):
        gui_instance.reload_telegram_channels()
    elif gui_instance and hasattr(gui_instance, 'trading_system'):
        gui_instance.trading_system.telegram.reload_channels()

def _admin_page(message=''):
    channels = DatabaseManager().get_all_telegram_channels()
    rows = []
    for channel in channels:
        channel_id = int(channel['id'])
        token = html.escape(channel.get('token') or '')
        chat_id = html.escape(channel.get('chat_id') or '')
        name = html.escape(channel.get('channel_name') or '')
        symbol = html.escape(channel.get('symbol') or '')
        link = html.escape(channel.get('channel_link') or '')
        rows.append(f"""
        <form class="row" method="post" action="/admin/channel/{channel_id}/update">
            <input name="symbol" value="{symbol}" placeholder="Symbol">
            <input name="channel_name" value="{name}" placeholder="Name">
            <input name="chat_id" value="{chat_id}" placeholder="Chat ID">
            <input name="channel_link" value="{link}" placeholder="Link">
            <input name="token" value="{token}" placeholder="Bot token">
            <button type="submit">Save</button>
            <button formaction="/admin/channel/{channel_id}/delete" class="danger">Delete</button>
        </form>
        """)

    rows_html = "\n".join(rows) or '<p class="muted">No channels yet.</p>'
    message_html = f'<div class="msg">{html.escape(message)}</div>' if message else ''
    webhook_url = html.escape(request.host_url.rstrip('/') + '/webhook')
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SPX Smart Admin</title>
  <style>
    body {{ margin:0; font-family: Arial, sans-serif; background:#101418; color:#f4f7fb; }}
    main {{ max-width:1180px; margin:0 auto; padding:24px; }}
    h1 {{ margin:0 0 8px; font-size:26px; }}
    .muted {{ color:#9aa7b5; }}
    .panel {{ background:#182029; border:1px solid #2b3745; padding:16px; margin:16px 0; }}
    .msg {{ background:#123d2b; border:1px solid #2e8b57; padding:10px; margin:12px 0; }}
    .row {{ display:grid; grid-template-columns: 80px 150px 170px 220px 1fr 70px 80px; gap:8px; margin:8px 0; }}
    input {{ background:#0f151c; color:#fff; border:1px solid #344252; padding:9px; min-width:0; }}
    button {{ background:#2f80ed; color:white; border:0; padding:9px 12px; cursor:pointer; }}
    .danger {{ background:#c24141; }}
    .actions {{ display:flex; gap:8px; flex-wrap:wrap; }}
    code {{ background:#0f151c; padding:3px 6px; }}
    @media (max-width: 900px) {{ .row {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<main>
  <h1>SPX Smart Admin</h1>
  <div class="muted">Webhook: <code>{webhook_url}</code></div>
  {message_html}

  <section class="panel">
    <h2>Telegram Channels</h2>
    {rows_html}
  </section>

  <section class="panel">
    <h2>Add Channel</h2>
    <form class="row" method="post" action="/admin/channel/add">
      <input name="symbol" placeholder="SPX">
      <input name="channel_name" placeholder="Channel name">
      <input name="chat_id" placeholder="Chat ID">
      <input name="channel_link" placeholder="https://t.me/...">
      <input name="token" placeholder="Bot token">
      <button type="submit">Add</button>
    </form>
  </section>

  <section class="panel actions">
    <form method="post" action="/admin/reload"><button type="submit">Reload Telegram</button></form>
    <a href="/status"><button type="button">Status</button></a>
  </section>
</main>
</body>
</html>
"""

@app.route('/admin', methods=['GET'])
def admin_home():
    if not _check_admin_auth():
        return _admin_required()
    return _admin_page(request.args.get('msg', ''))

@app.route('/admin/channel/add', methods=['POST'])
def admin_add_channel():
    if not _check_admin_auth():
        return _admin_required()
    DatabaseManager().add_telegram_channel(
        request.form.get('token', '').strip(),
        request.form.get('chat_id', '').strip(),
        request.form.get('channel_name', '').strip(),
        request.form.get('symbol', '').strip().upper(),
        request.form.get('channel_link', '').strip()
    )
    _reload_runtime_channels()
    return redirect('/admin?msg=Channel added')

@app.route('/admin/channel/<int:channel_id>/update', methods=['POST'])
def admin_update_channel(channel_id):
    if not _check_admin_auth():
        return _admin_required()
    DatabaseManager().update_telegram_channel(
        channel_id,
        request.form.get('token', '').strip(),
        request.form.get('chat_id', '').strip(),
        request.form.get('channel_name', '').strip(),
        request.form.get('symbol', '').strip().upper(),
        request.form.get('channel_link', '').strip()
    )
    _reload_runtime_channels()
    return redirect('/admin?msg=Channel updated')

@app.route('/admin/channel/<int:channel_id>/delete', methods=['POST'])
def admin_delete_channel(channel_id):
    if not _check_admin_auth():
        return _admin_required()
    DatabaseManager().delete_telegram_channel(channel_id)
    _reload_runtime_channels()
    return redirect('/admin?msg=Channel deleted')

@app.route('/admin/reload', methods=['POST'])
def admin_reload():
    if not _check_admin_auth():
        return _admin_required()
    _reload_runtime_channels()
    return redirect('/admin?msg=Telegram channels reloaded')

@app.route('/', methods=['GET'])
def home():
    """Home page"""
    return """
    <html>
    <head>
        <title>SPX Smart Webhook Server</title>
        <style>
            body { font-family: Arial; background: #0a0e27; color: #fff; padding: 40px; }
            h1 { color: #00d4ff; }
            .endpoint { background: #1a1f3a; padding: 15px; margin: 10px 0; border-radius: 5px; }
            code { background: #252b4a; padding: 5px 10px; border-radius: 3px; color: #00ff88; }
        </style>
    </head>
    <body>
        <h1>🚀 SPX Smart Webhook Server</h1>
        <p>Server is running successfully!</p>
        
        <h2>Endpoints:</h2>
        <div class="endpoint">
            <strong>POST /webhook</strong> - Receive TradingView signals
        </div>
        <div class="endpoint">
            <strong>GET /status</strong> - Check server status
        </div>
        <div class="endpoint">
            <strong>GET /active</strong> - Get active trades
        </div>
        
        <h2>TradingView Alert Format:</h2>
        <p>Send JSON with the following structure:</p>
        <div class="endpoint">
            <strong>Basic (without quantity):</strong><br>
            <code>{"type": "CALL", "symbol": "SPX"}</code><br>
            <code>{"type": "PUT", "symbol": "SPX"}</code><br><br>
            
            <strong>With quantity (number of contracts):</strong><br>
            <code>{"type": "CALL", "symbol": "SPX", "quantity": 2}</code><br>
            <code>{"type": "PUT", "symbol": "NDX", "quantity": 5}</code><br><br>
            
            <strong>Note:</strong> If quantity is not specified, system will use the default quantity (1 contract)
        </div>
        
        <h2>Webhook URL for Ngrok:</h2>
        <div class="endpoint">
            <code>http://localhost:5000/webhook</code>
        </div>
    </body>
    </html>
    """

@app.route('/webhook', methods=['POST'])
def webhook():
    """Receive TradingView webhook signal"""
    global webhook_signal_counter
    
    try:
        # Get JSON data
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        # Extract signal info
        signal_type = data.get('type', '').upper()
        symbol = data.get('symbol', config.DEFAULT_SYMBOL).upper()
        quantity = data.get('quantity', None)  # Optional: number of contracts
        
        # Validate signal type
        if signal_type not in ['CALL', 'PUT']:
            return jsonify({"status": "error", "message": "Invalid signal type. Must be CALL or PUT"}), 400
        
        # Validate symbol
        if symbol not in config.SUPPORTED_SYMBOLS:
            return jsonify({"status": "error", "message": f"Unsupported symbol: {symbol}"}), 400
        
        # Validate quantity if provided
        if quantity is not None:
            try:
                quantity = int(quantity)
                if quantity < 1:
                    return jsonify({"status": "error", "message": "Quantity must be at least 1"}), 400
            except ValueError:
                return jsonify({"status": "error", "message": "Invalid quantity value"}), 400
        
        # Increment counter
        webhook_signal_counter += 1
        signal_number = webhook_signal_counter
        
        # Log signal
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"\n{'='*60}")
        logger.info(f"📡 Webhook Received #{signal_number}: {timestamp}")
        logger.info(f"🎯 Signal: {signal_type} {symbol}")
        if quantity:
            logger.info(f"📦 Quantity: {quantity} contracts")
        logger.info(f"📦 Data: {data}")
        logger.info(f"{'='*60}\n")
        
        # Also print to console for immediate visibility
        print(f"\n{'='*60}")
        print(f"📡 WEBHOOK RECEIVED #{signal_number}: {timestamp}")
        print(f"🎯 Signal: {signal_type} {symbol}")
        if quantity:
            print(f"📦 Quantity: {quantity} contracts")
        print(f"📦 Data: {data}")
        print(f"{'='*60}\n")
        
        # Trigger manual button in GUI (thread-safe)
        if gui_instance:
            logger.info(f"✅ Triggering manual {signal_type} button for {symbol}")
            print(f"✅ Triggering manual {signal_type} button for {symbol}\n")
            
            # Call GUI method to trigger button (thread-safe with root.after)
            gui_instance.trigger_manual_button(symbol, signal_type, quantity)
            
            qty_msg = f" x{quantity}" if quantity else ""
            return jsonify({
                "status": "success",
                "message": f"{signal_type} signal #{signal_number} received for {symbol}{qty_msg} - Manual button triggered",
                "timestamp": timestamp
            }), 200
        else:
            logger.error("❌ GUI instance not set - cannot trigger manual button")
            print("❌ GUI instance not set - cannot trigger manual button\n")
            return jsonify({
                "status": "error",
                "message": "GUI not initialized - cannot trigger manual button"
            }), 503
        
    except Exception as e:
        logger.error(f"❌ Webhook Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    """Check server status"""
    if gui_instance and hasattr(gui_instance, 'trading_system') and gui_instance.trading_system:
        trading_system = gui_instance.trading_system
        active_count = len(trading_system.active_trades)
        balance = trading_system.get_current_balance()
        
        return jsonify({
            "status": "running" if gui_instance.system_running else "stopped",
            "balance": f"${balance:,.2f}",
            "active_trades": active_count,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }), 200
    else:
        return jsonify({
            "status": "not_initialized",
            "message": "GUI/Trading system not initialized"
        }), 503

@app.route('/active', methods=['GET'])
def active_trades():
    """Get active trades"""
    if gui_instance and hasattr(gui_instance, 'trading_system') and gui_instance.trading_system:
        trading_system = gui_instance.trading_system
        trades = []
        for trade_id, trade_data in trading_system.active_trades.items():
            trades.append({
                "id": trade_id,
                "symbol": trade_data['symbol'],
                "type": trade_data['type'],
                "strike": trade_data['strike'],
                "entry_price": trade_data['entry_price'],
                "highest_price": trade_data['highest_price']
            })
        
        return jsonify({
            "status": "success",
            "count": len(trades),
            "trades": trades
        }), 200
    else:
        return jsonify({
            "status": "error",
            "message": "GUI/Trading system not initialized"
        }), 503

def run_webhook_server():
    """Run the webhook server"""
    logger.info("=" * 60)
    logger.info("🚀 SPX Smart Webhook Server")
    logger.info("=" * 60)
    logger.info(f"📍 Local URL: http://localhost:{config.FLASK_PORT}/webhook")
    logger.info(f"📍 Status URL: http://localhost:{config.FLASK_PORT}/status")
    logger.info("=" * 60)
    
    print("=" * 60)
    print("🚀 SPX Smart Webhook Server")
    print("=" * 60)
    print(f"📍 Local URL: http://localhost:{config.FLASK_PORT}/webhook")
    print(f"📍 Status URL: http://localhost:{config.FLASK_PORT}/status")
    print("=" * 60)
    
    # Start Ngrok tunnel only for local desktop use.
    ngrok_started = False
    if getattr(config, 'ENABLE_NGROK', False):
        ngrok_started = start_ngrok()
    
    if getattr(config, 'ENABLE_NGROK', False) and not ngrok_started:
        logger.warning("⚠️  Running without Ngrok (local only)")
        print("⚠️  Running without Ngrok (local only)")
    
    logger.info("✅ Server starting...\n")
    print("✅ Server starting...\n")
    
    try:
        app.run(
            host=config.FLASK_HOST,
            port=config.FLASK_PORT,
            debug=False,
            use_reloader=False
        )
    finally:
        if ngrok_started:
            stop_ngrok()
