print("BOT FILE STARTED", flush=True)
import os
import json
import threading
import traceback
from flask import Flask
import requests
import discord
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# CONFIG CHECKS
# -----------------------------

def get_required_env(name):
    value = os.getenv(name)

    if value is None or value.strip() == "":
        print(f"ERROR: Missing environment variable: {name}")
        raise SystemExit(1)

    return value.strip()


DISCORD_TOKEN = get_required_env("DISCORD_TOKEN")
ETHERSCAN_API_KEY = get_required_env("ETHERSCAN_API_KEY")
WALLET_ADDRESS = get_required_env("WALLET_ADDRESS").lower()
CHAIN_ID = os.getenv("CHAIN_ID", "1").strip()

try:
    CHANNEL_ID = int(get_required_env("DISCORD_CHANNEL_ID"))
except ValueError:
    print("ERROR: DISCORD_CHANNEL_ID must be numbers only.")
    raise SystemExit(1)


CHECK_SECONDS = 60
STATE_FILE = "last_tx.json"


# -----------------------------
# SMALL WEB SERVER FOR RENDER
# -----------------------------

app = Flask(__name__)

@app.route("/")
def home():
    return "Crypto Discord bot is running."

@app.route("/health")
def health():
    return "OK", 200


def run_web_server():
    port = int(os.getenv("PORT", 10000))
    print(f"Starting web server on port {port}")
    app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_web_server, daemon=True).start()


# -----------------------------
# DISCORD BOT
# -----------------------------

intents = discord.Intents.default()
client = discord.Client(intents=intents)


def load_last_tx_hash():
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r") as file:
            data = json.load(file)
            return data.get("last_tx_hash")
    except Exception as error:
        print(f"Could not read {STATE_FILE}: {error}")
        return None


def save_last_tx_hash(tx_hash):
    try:
        with open(STATE_FILE, "w") as file:
            json.dump({"last_tx_hash": tx_hash}, file)
    except Exception as error:
        print(f"Could not save {STATE_FILE}: {error}")


def etherscan_request(params):
    url = "https://api.etherscan.io/v2/api"

    full_params = {
        **params,
        "apikey": ETHERSCAN_API_KEY,
        "chainid": CHAIN_ID
    }

    response = requests.get(url, params=full_params, timeout=20)
    return response.json()


def get_recent_transactions():
    data = etherscan_request({
        "module": "account",
        "action": "txlist",
        "address": WALLET_ADDRESS,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": 10,
        "sort": "desc"
    })

    if data.get("status") != "1":
        print(f"Etherscan transaction response: {data}")
        return []

    return data.get("result", [])


def get_wallet_balance():
    data = etherscan_request({
        "module": "account",
        "action": "balance",
        "address": WALLET_ADDRESS,
        "tag": "latest"
    })

    if data.get("status") != "1":
        print(f"Etherscan balance response: {data}")
        return None

    return int(data["result"]) / 10**18


def get_eth_price():
    url = "https://api.etherscan.io/v2/api"

    params = {
        "chainid": 1,
        "module": "stats",
        "action": "ethprice",
        "apikey": ETHERSCAN_API_KEY
    }

    response = requests.get(url, params=params, timeout=20)
    data = response.json()

    if data.get("status") != "1":
        print(f"Etherscan price response: {data}")
        return None

    return float(data["result"]["ethusd"])


def tx_link(tx_hash):
    explorers = {
        "1": "https://etherscan.io/tx/",
        "56": "https://bscscan.com/tx/",
        "137": "https://polygonscan.com/tx/",
        "8453": "https://basescan.org/tx/",
        "42161": "https://arbiscan.io/tx/"
    }

    return explorers.get(CHAIN_ID, "https://etherscan.io/tx/") + tx_hash


async def send_transaction_alert(tx):
    try:
        eth_price = get_eth_price()

        tx_hash = tx["hash"]
        from_address = tx["from"]
        to_address = tx["to"]

        amount_eth = int(tx["value"]) / 10**18
        amount_usd = amount_eth * eth_price if eth_price else 0

        balance_eth = get_wallet_balance()
        balance_usd = balance_eth * eth_price if balance_eth is not None and eth_price else 0

        direction = "Incoming" if to_address.lower() == WALLET_ADDRESS else "Outgoing"

        message = (
            f"🚨 New ETH Transaction\n"
            f"Type: {direction}\n"
            f"Amount: {amount_eth:.8f} ETH\n"
            f"USD Value: ${amount_usd:,.2f}\n"
            f"Current Balance: {balance_eth:.8f} ETH\n"
            f"Balance USD: ${balance_usd:,.2f}\n"
            f"From: `{from_address}`\n"
            f"To: `{to_address}`\n"
            f"{tx_link(tx_hash)}"
        )

        channel = client.get_channel(CHANNEL_ID)

        if channel is None:
            print("ERROR: Could not find Discord channel. Check DISCORD_CHANNEL_ID.")
            return

        await channel.send(message)

    except Exception:
        print("ERROR while sending transaction alert:")
        traceback.print_exc()


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    if not check_wallet.is_running():
        check_wallet.start()


@tasks.loop(seconds=CHECK_SECONDS)
async def check_wallet():
    try:
        last_tx_hash = load_last_tx_hash()
        transactions = get_recent_transactions()

        if not transactions:
            print("No transactions found or Etherscan returned no result.")
            return

        newest_hash = transactions[0]["hash"]

        if last_tx_hash is None:
            save_last_tx_hash(newest_hash)
            print("First run. Saved latest transaction as baseline.")
            return

        new_transactions = []

        for tx in transactions:
            if tx["hash"] == last_tx_hash:
                break
            new_transactions.append(tx)

        if not new_transactions:
            print("No new transactions.")
            return

        new_transactions.reverse()

        for tx in new_transactions:
            await send_transaction_alert(tx)

        save_last_tx_hash(newest_hash)
        print(f"Posted {len(new_transactions)} new transaction(s).")

    except Exception:
        print("ERROR inside check_wallet:")
        traceback.print_exc()


try:
    print("Starting Discord bot...")
    client.run(DISCORD_TOKEN)
except Exception:
    print("CRITICAL ERROR: Discord bot crashed.")
    traceback.print_exc()
    raise
