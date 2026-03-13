import os
import json
import requests
from dotenv import load_dotenv
from web3 import Web3

# --------------------------------------------------
# Load environment variables
# --------------------------------------------------

load_dotenv()

ALCHEMY_RPC = os.getenv("ALCHEMY_RPC")
WATCHER_URL = os.getenv("WATCHER_URL")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")
ALCHEMY_SIGNATURE = os.getenv("ALCHEMY_SIGNATURE")

if not ALCHEMY_RPC:
    raise Exception("Missing ALCHEMY_RPC in .env")

if not WATCHER_URL:
    raise Exception("Missing WATCHER_URL in .env")

if not CONTRACT_ADDRESS:
    raise Exception("Missing CONTRACT_ADDRESS in .env")

# --------------------------------------------------
# Web3
# --------------------------------------------------

w3 = Web3(Web3.HTTPProvider(ALCHEMY_RPC))

# --------------------------------------------------
# Block to replay
# --------------------------------------------------

BLOCK_NUMBER = 24623717
BLOCK_HEX = hex(BLOCK_NUMBER)

print("========================================")
print("Replay block:", BLOCK_NUMBER)
print("Block hex:", BLOCK_HEX)
print("Contract:", CONTRACT_ADDRESS)
print("Watcher:", WATCHER_URL)
print("========================================")

# --------------------------------------------------
# Fetch logs from Alchemy
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

print("\nRequesting logs from Alchemy...\n")

rpc = requests.post(ALCHEMY_RPC, json=rpc_payload)

if rpc.status_code != 200:
    print("RPC ERROR:", rpc.text)
    exit()

data = rpc.json()

logs = data.get("result", [])

print("Logs found:", len(logs))
print("========================================")

# --------------------------------------------------
# Print raw logs
# --------------------------------------------------

for i, log in enumerate(logs):

    print("\nLOG", i + 1)
    print("----------------------------------------")

    print("TX:", log["transactionHash"])
    print("BLOCK:", log["blockNumber"])
    print("ADDRESS:", log["address"])

    print("\nTOPICS:")
    for topic in log["topics"]:
        print(topic)

    print("\nDATA:")
    print(log["data"])

# --------------------------------------------------
# Send logs to watcher
# --------------------------------------------------

print("\n========================================")
print("Sending logs to watcher")
print("========================================")

headers = {
    "Content-Type": "application/json"
}

if ALCHEMY_SIGNATURE:
    headers["X-Alchemy-Signature"] = ALCHEMY_SIGNATURE

for i, log in enumerate(logs):

    payload = {
        "event": {
            "activity": [
                {
                    "log": log
                }
            ]
        }
    }

    print("\nSending log", i + 1)

    r = requests.post(
        WATCHER_URL,
        headers=headers,
        json=payload
    )

    print("Watcher status:", r.status_code)

    try:
        print("Watcher response:", r.json())
    except:
        print("Watcher response:", r.text)

print("\n========================================")
print("Replay finished")
print("========================================")