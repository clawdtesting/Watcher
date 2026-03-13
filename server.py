import os
import json
import sqlite3
import requests
from flask import Flask, request, abort
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

ALCHEMY_RPC = os.getenv("ALCHEMY_RPC")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ALCHEMY_SIGNATURE = os.getenv("ALCHEMY_SIGNATURE")

app = Flask(__name__)

# --------------------------------------------------
# Web3
# --------------------------------------------------

w3 = Web3(Web3.HTTPProvider(ALCHEMY_RPC))
CONTRACT_ADDRESS = Web3.to_checksum_address(CONTRACT_ADDRESS)

with open("AGIJobManagerABI.json") as f:
    ABI = json.load(f)

contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=ABI)

# --------------------------------------------------
# Database
# --------------------------------------------------

db = sqlite3.connect("events.db", check_same_thread=False)

db.execute("""
CREATE TABLE IF NOT EXISTS events(
    event_name TEXT,
    block_number TEXT,
    tx_hash TEXT,
    args TEXT
)
""")

db.commit()

# --------------------------------------------------
# Telegram
# --------------------------------------------------

def send_telegram(message):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        r = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=10
        )

        print("Telegram response:", r.text)

    except Exception as e:
        print("Telegram error:", e)

# --------------------------------------------------
# Signature check
# --------------------------------------------------

def verify_alchemy_signature():

    if not ALCHEMY_SIGNATURE:
        return

    incoming = request.headers.get("X-Alchemy-Signature")

    if incoming != ALCHEMY_SIGNATURE:
        abort(403)

# --------------------------------------------------
# Decode event
# --------------------------------------------------

def decode_event(log):

    for event in contract.events:

        try:

            decoded = event().process_log(log)

            return {
                "event": decoded["event"],
                "args": dict(decoded["args"])
            }

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

    print("WEBHOOK RECEIVED")

    verify_alchemy_signature()

    payload = request.get_json(silent=True)

    if not payload:
        return "no payload", 400

    activities = payload.get("event", {}).get("activity", [])

    print("Logs received:", len(activities))

    for activity in activities:

        log = activity.get("log")

        if not log:
            continue

        print("Processing log:", log["topics"][0])

        decoded = decode_event(log)

        if not decoded:
            print("Event not recognized by ABI")
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
AGI EVENT

Event: {event_name}

Block: {block_number}

Tx:
{tx_hash}

Args:
{json.dumps(args, indent=2)}
"""

        send_telegram(message)

    return "ok"


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    print("Starting watcher on port", port)

    app.run(host="0.0.0.0", port=port)