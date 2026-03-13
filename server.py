import os
import json
import sqlite3
import requests
from flask import Flask, request, abort
from web3 import Web3
from dotenv import load_dotenv

# --------------------------------------------------
# Load environment
# --------------------------------------------------

load_dotenv()

ALCHEMY_RPC = os.getenv("ALCHEMY_RPC")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ALCHEMY_SIGNATURE = os.getenv("ALCHEMY_SIGNATURE")

if not ALCHEMY_RPC:
    raise Exception("Missing ALCHEMY_RPC")

if not CONTRACT_ADDRESS:
    raise Exception("Missing CONTRACT_ADDRESS")

if not TELEGRAM_TOKEN:
    raise Exception("Missing TELEGRAM_TOKEN")

if not CHAT_ID:
    raise Exception("Missing CHAT_ID")

# --------------------------------------------------
# Flask
# --------------------------------------------------

app = Flask(__name__)

# --------------------------------------------------
# Web3
# --------------------------------------------------

w3 = Web3(Web3.HTTPProvider(ALCHEMY_RPC))

with open("AGIJobManagerABI.json") as f:
    ABI = json.load(f)

contract = w3.eth.contract(
    address=Web3.to_checksum_address(CONTRACT_ADDRESS),
    abi=ABI
)

# --------------------------------------------------
# Database
# --------------------------------------------------

db = sqlite3.connect("jobs.db", check_same_thread=False)

db.execute("""
CREATE TABLE IF NOT EXISTS events(
    event_name TEXT,
    block_number TEXT,
    tx_hash TEXT,
    data TEXT
)
""")

db.commit()

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def send_telegram(message):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            },
            timeout=10
        )
    except Exception as e:
        print("Telegram send failed:", e)


def verify_alchemy_signature():

    if not ALCHEMY_SIGNATURE:
        return True

    incoming = request.headers.get("X-Alchemy-Signature")

    if incoming != ALCHEMY_SIGNATURE:
        abort(403)

# --------------------------------------------------
# Decode log using ABI
# --------------------------------------------------

def decode_event(log):

    for event in contract.events:

        try:
            decoded = event().process_log(log)
            return decoded
        except Exception:
            continue

    return None

# --------------------------------------------------
# Routes
# --------------------------------------------------

@app.route("/")
def health():
    return "AGI watcher running"


@app.route("/alchemy", methods=["POST"])
def webhook():

    verify_alchemy_signature()

    payload = request.get_json(silent=True)

    if not payload:
        return "No JSON payload", 400

    print("Webhook received")

    activities = payload.get("event", {}).get("activity", [])

    for activity in activities:

        log = activity.get("log")

        if not log:
            continue

        decoded = decode_event(log)

        if not decoded:
            print("Unknown log:", log)
            continue

        event_name = decoded["event"]
        args = decoded["args"]

        print("Event detected:", event_name)

        tx_hash = log.get("transactionHash")
        block_number = log.get("blockNumber")

        db.execute(
            "INSERT INTO events VALUES (?,?,?,?)",
            (
                event_name,
                block_number,
                tx_hash,
                json.dumps(args)
            )
        )

        db.commit()

        message = f"""
🚨 *AGI EVENT*

*Event:* {event_name}

*Block:* {block_number}

*Transaction:*  
{tx_hash}

*Data:*  
{json.dumps(args, indent=2)}
"""

        send_telegram(message)

    return "ok"

# --------------------------------------------------
# Start server
# --------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("Starting server on port", port)
    app.run(host="0.0.0.0", port=port)