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

        r = requests.get(url, timeout=15)

        if r.status_code == 200:
            return r.json()

    except Exception as e:

        print("IPFS fetch error:", e)

    return {}


def format_list(items):

    if not items:
        return "—"

    return "\n".join([f"• {i}" for i in items])


def send_telegram(message):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:

        r = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
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

        if event_name != "JobCreated":
            continue

        # --------------------------------------------------
        # Extract on-chain args
        # --------------------------------------------------

        job_id = args.get("jobId")
        payout = int(args.get("payout"))
        duration = int(args.get("duration"))
        job_spec_uri = args.get("jobSpecURI")

        payout_display = f"{payout / 10**18:,.0f} AGIALPHA"
        duration_days = duration // 86400

        spec = fetch_ipfs_json(job_spec_uri)

        name = spec.get("name", "Unknown Job")
        description = spec.get("description", "")

        image = spec.get("image", "")

        properties = spec.get("properties", {})

        title = properties.get("title", "")
        summary = properties.get("summary", "")
        deliverables = format_list(properties.get("deliverables", []))
        acceptance = format_list(properties.get("acceptanceCriteria", []))
        requirements = format_list(properties.get("requirements", []))

        payout_prop = properties.get("payoutAGIALPHA", "")
        employer = properties.get("employer", "")

        attributes = spec.get("attributes", [])

        attr_text = "\n".join(
            [f"{a.get('trait_type')}: {a.get('value')}" for a in attributes]
        )

        ipfs_link = ipfs_to_http(job_spec_uri)
        tx_link = f"https://etherscan.io/tx/{tx_hash}"

        message = f"""
🚨 <b>NEW AGI JOB</b>

<b>Name</b>
{name}

<b>Description</b>
{description}

<b>Image</b>
<a href="{image}">Open image</a>

<b>Title</b>
{title}

<b>Summary</b>
{summary}

<b>Deliverables</b>
{deliverables}

<b>Acceptance Criteria</b>
{acceptance}

<b>Requirements</b>
{requirements}

<b>Payout</b>
{payout_display}

<b>Duration</b>
{duration_days} days

<b>Employer</b>
{employer}

<b>Attributes</b>
{attr_text}

<b>Spec</b>
<a href="{ipfs_link}">{ipfs_link}</a>

<b>Transaction</b>
<a href="{tx_link}">{tx_hash}</a>
"""

        send_telegram(message)

    return "ok"


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    print("Starting watcher on port", port)

    app.run(host="0.0.0.0", port=port)