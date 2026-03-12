from flask import Flask, request
from web3 import Web3
import requests
import json
import sqlite3

app = Flask(__name__)

TELEGRAM_TOKEN = "BOT_TOKEN"
CHAT_ID = "CHAT_ID"

ABI = json.load(open("AGIJobManagerABI.json"))

contract = Web3().eth.contract(abi=ABI)

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

def fetch_ipfs(uri):
    if uri.startswith("ipfs://"):
        uri = uri.replace("ipfs://","https://ipfs.io/ipfs/")
    r = requests.get(uri)
    return r.json()

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url,json={
        "chat_id":CHAT_ID,
        "text":msg
    })

@app.route("/alchemy",methods=["POST"])
def webhook():

    payload = request.json

    logs = payload["event"]["data"]["block"]["logs"]

    for log in logs:

        decoded = contract.events.JobCreated().process_log(log)

        jobSpecURI = decoded["args"]["_jobSpecURI"]
        payout = decoded["args"]["_payout"]
        duration = decoded["args"]["_duration"]
        details = decoded["args"]["_details"]

        spec = fetch_ipfs(jobSpecURI)

        db.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?)",
            (
                spec.get("id","unknown"),
                payout,
                duration,
                jobSpecURI,
                details
            )
        )
        db.commit()

        message = f"""
🚨 NEW AGI JOB

Details:
{details}

Payout:
{payout}

Duration:
{duration}

IPFS:
{jobSpecURI}
"""

        send_telegram(message)

    return "ok"