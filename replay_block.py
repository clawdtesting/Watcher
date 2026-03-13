import os
import requests
from dotenv import load_dotenv

# --------------------------------------------------
# Load environment variables
# --------------------------------------------------

load_dotenv()

ALCHEMY_RPC = os.getenv("ALCHEMY_RPC")
WATCHER_URL = os.getenv("WATCHER_URL")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")
ALCHEMY_SIGNATURE = os.getenv("ALCHEMY_SIGNATURE")

BLOCK_NUMBER = 24623717
BLOCK_HEX = hex(BLOCK_NUMBER)

print("Replaying events from block:", BLOCK_NUMBER)

# --------------------------------------------------
# Fetch logs
# --------------------------------------------------

rpc_payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "eth_getLogs",
    "params": [
        {
            "fromBlock": BLOCK_HEX,
            "toBlock": BLOCK_HEX,
            "address": CONTRACT_ADDRESS
        }
    ]
}

rpc = requests.post(ALCHEMY_RPC, json=rpc_payload)
logs = rpc.json().get("result", [])

print("Logs found:", len(logs))

# --------------------------------------------------
# Replay logs to watcher
# --------------------------------------------------

for log in logs:

    webhook_payload = {
        "event": {
            "activity": [
                {
                    "log": log
                }
            ]
        }
    }

    headers = {
        "Content-Type": "application/json",
        "X-Alchemy-Signature": ALCHEMY_SIGNATURE
    }

    r = requests.post(WATCHER_URL, json=webhook_payload, headers=headers)

    print("Sent log → watcher | status:", r.status_code)

print("Replay complete.")