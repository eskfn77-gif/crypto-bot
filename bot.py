import os
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

intents = discord.Intents.default()
client = discord.Client(intents=intents)

last_seen_tx = None


def get_latest_transaction():
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": CHAIN_ID,
        "module": "account",
        "action": "txlist",
        "address": WALLET_ADDRESS,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": 1,
        "sort": "desc",
        "apikey": ETHERSCAN_API_KEY,
    }

    data = requests.get(url, params=params, timeout=15).json()

    if data.get("status") != "1":
        return None

    results = data.get("result", [])
    return results[0] if results else None


def get_eth_usd_price():
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": 1,
        "module": "stats",
        "action": "ethprice",
        "apikey": ETHERSCAN_API_KEY,
    }

    data = requests.get(url, params=params, timeout=15).json()

    if data.get("status") != "1":
        return None

    return float(data["result"]["ethusd"])


def get_wallet_balance():
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": CHAIN_ID,
        "module": "account",
        "action": "balance",
        "address": WALLET_ADDRESS,
        "tag": "latest",
        "apikey": ETHERSCAN_API_KEY,
    }

    data = requests.get(url, params=params, timeout=15).json()

    if data.get("status") != "1":
        return None

    return int(data["result"]) / 10**18


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    check_wallet.start()


@tasks.loop(seconds=60)
async def check_wallet():
    global last_seen_tx

    tx = get_latest_transaction()
    if not tx:
        return

    tx_hash = tx["hash"]

    if last_seen_tx is None:
        last_seen_tx = tx_hash
        return

    if tx_hash != last_seen_tx:
        last_seen_tx = tx_hash

        eth_price = get_eth_usd_price()
        tx_eth = int(tx["value"]) / 10**18
        tx_usd = tx_eth * eth_price if eth_price else 0

        balance_eth = get_wallet_balance()
        balance_usd = balance_eth * eth_price if balance_eth is not None and eth_price else 0

        direction = "Incoming" if tx["to"].lower() == WALLET_ADDRESS else "Outgoing"

        msg = (
            f"🚨 New ETH Transaction\n"
            f"Type: {direction}\n"
            f"Amount: {tx_eth:.8f} ETH\n"
            f"USD Value: ${tx_usd:,.2f}\n"
            f"Current Balance: {balance_eth:.8f} ETH\n"
            f"Balance USD: ${balance_usd:,.2f}\n"
            f"From: `{tx['from']}`\n"
            f"To: `{tx['to']}`\n"
            f"https://etherscan.io/tx/{tx_hash}"
        )

        channel = client.get_channel(CHANNEL_ID)
        if channel:
            await channel.send(msg)


client.run(DISCORD_TOKEN)