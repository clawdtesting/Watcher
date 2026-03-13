import os
import json
import sqlite3
import requests
from flask import Flask, request, abort
from web3 import Web3
from dotenv import load_dotenv

# --------------------------------------------------
# Load environment variables
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
# Flask app
# --------------------------------------------------

app = Flask(__name__)

# --------------------------------------------------
# Web3 setup
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
CREATE TABLE IF NOT EXISTS jobs(
    job_id TEXT,
    payout TEXT,
    duration INTEGER,
    ipfs TEXT,
    details TEXT
)
""")

db.commit()

# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def fetch_ipfs(uri):

    if uri.startswith("ipfs://"):
        uri = uri.replace("ipfs://", "https://ipfs.io/ipfs/")

    try:
        r = requests.get(uri, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("IPFS fetch failed:", e)
        return {}

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

        print("Processing log:", log)

        try:
            decoded = contract.events.JobCreated().process_log(log)
        except Exception as e:
            print("Log not JobCreated event:", e)
            continue

        try:
            jobSpecURI = decoded["args"]["_jobSpecURI"]
            payout_raw = decoded["args"]["_payout"]
            duration = decoded["args"]["_duration"]
            details = decoded["args"]["_details"]
        except Exception as e:
            print("Event decoding failed:", e)
            continue

        payout = w3.from_wei(payout_raw, "ether")

        spec = fetch_ipfs(jobSpecURI)

        try:
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?)",
                (
                    spec.get("id", "unknown"),
                    str(payout),
                    duration,
                    jobSpecURI,
                    details
                )
            )
            db.commit()
        except Exception as e:
            print("Database write failed:", e)

        title = spec.get("title", "New Job")
        summary = spec.get("summary", "")

        message = f"""
🚨 *NEW AGI JOB*

*Title:* {title}

*Summary:*  
{summary}

*Details:*  
{details}

*Payout:* {payout}

*Duration:* {duration}

*IPFS:*  
{jobSpecURI}
"""

        send_telegram(message)

    return "ok"

# --------------------------------------------------
# Render / production startup
# --------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("Starting server on port", port)
    app.run(host="0.0.0.0", port=port)