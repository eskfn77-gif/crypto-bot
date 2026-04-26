import os
import json
import requests
import discord
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS").lower()
CHAIN_ID = os.getenv("CHAIN_ID", "1")

CHECK_SECONDS = 60
STATE_FILE = "last_tx.json"

intents = discord.Intents.default()
client = discord.Client(intents=intents)


def load_last_tx_hash():
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r") as file:
            data = json.load(file)
            return data.get("last_tx_hash")
    except:
        return None


def save_last_tx_hash(tx_hash):
    with open(STATE_FILE, "w") as file:
        json.dump({"last_tx_hash": tx_hash}, file)


def etherscan_request(params):
    url = "https://api.etherscan.io/v2/api"
    params["apikey"] = ETHERSCAN_API_KEY
    params["chainid"] = CHAIN_ID

    response = requests.get(url, params=params, timeout=20)
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

    data = requests.get(url, params=params, timeout=20).json()

    if data.get("status") != "1":
        return None

    return float(data["result"]["ethusd"])


def tx_link(tx_hash):
    if CHAIN_ID == "1":
        return f"https://etherscan.io/tx/{tx_hash}"
    if CHAIN_ID == "56":
        return f"https://bscscan.com/tx/{tx_hash}"
    if CHAIN_ID == "137":
        return f"https://polygonscan.com/tx/{tx_hash}"
    if CHAIN_ID == "8453":
        return f"https://basescan.org/tx/{tx_hash}"
    if CHAIN_ID == "42161":
        return f"https://arbiscan.io/tx/{tx_hash}"

    return f"https://etherscan.io/tx/{tx_hash}"


async def send_transaction_alert(tx):
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

    if channel:
        await channel.send(message)
    else:
        print("Could not find Discord channel. Check DISCORD_CHANNEL_ID.")


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    if not check_wallet.is_running():
        check_wallet.start()


@tasks.loop(seconds=CHECK_SECONDS)
async def check_wallet():
    last_tx_hash = load_last_tx_hash()
    transactions = get_recent_transactions()

    if not transactions:
        print("No transactions found or API issue.")
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


client.run(DISCORD_TOKEN)