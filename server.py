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
# Helpers
# --------------------------------------------------

def ipfs_to_http(uri):

    if uri.startswith("ipfs://"):
        return uri.replace("ipfs://", "https://ipfs.io/ipfs/")

    return uri


def fetch_ipfs_json(uri):

    try:

        url = ipfs_to_http(uri)

        r = requests.get(url, timeout=10)

        if r.status_code == 200:
            return r.json()

    except Exception as e:
        print("IPFS fetch error:", e)

    return {}


def format_duration(seconds):

    days = seconds // 86400

    if days == 1:
        return "1 day"

    return f"{days} days"


def send_telegram(message):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:

        r = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )

        print("Telegram response:", r.text)

    except Exception as e:

        print("Telegram error:", e)


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

        decoded = decode_event(log)

        if not decoded:
            print("Event not recognized")
            continue

        event_name = decoded["event"]
        args = dict(decoded["args"])

        tx_hash = log.get("transactionHash")
        block_number = log.get("blockNumber")

        print("Event detected:", event_name)

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

        # --------------------------------------------------
        # Handle JobCreated
        # --------------------------------------------------

        if event_name == "JobCreated":

            job_id = args.get("jobId")
            payout = int(args.get("payout"))
            duration = int(args.get("duration"))
            job_spec_uri = args.get("jobSpecURI")

            payout_display = f"{payout / 10**18:,.0f} AGIALPHA"
            duration_display = format_duration(duration)

            spec = fetch_ipfs_json(job_spec_uri)

            summary = spec.get("summary", "No summary provided.")

            ipfs_link = ipfs_to_http(job_spec_uri)
            tx_link = f"https://etherscan.io/tx/{tx_hash}"

            message = f"""
🚨 <b>NEW AGI JOB</b>

<b>Job ID:</b> {job_id}
<b>Payout:</b> {payout_display}
<b>Duration:</b> {duration_display}

<b>Spec link:</b>
<a href="{ipfs_link}">{ipfs_link}</a>

<b>Spec summarize:</b>
{summary}

<b>Transaction:</b>
<a href="{tx_link}">{tx_hash}</a>
"""

            send_telegram(message)

    return "ok"


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    print("Starting watcher on port", port)

    app.run(host="0.0.0.0", port=port)