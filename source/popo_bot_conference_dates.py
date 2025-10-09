import os
import glob
import discord
from discord.ext import commands
from dotenv import load_dotenv

# ---- Config ----
load_dotenv()
TOKEN = os.getenv("popo_token")
CHANNEL_ID = int(os.getenv("conference_dates_channel"))
LOG_FILE = "conference_post_log.txt"  # remembers last posted file

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def get_latest_md():
    """Find the newest .md file in conference_discord/"""
    files = glob.glob("conference_discord/*.md")
    if not files:
        return None
    latest = max(files, key=os.path.getmtime)
    return latest

def split_by_category(md_text):
    """Split markdown into chunks by ## headers."""
    parts = []
    current = []
    for line in md_text.splitlines():
        if line.startswith("## "):
            if current:
                parts.append("\n".join(current))
                current = []
        current.append(line)
    if current:
        parts.append("\n".join(current))
    return parts

def get_last_posted():
    """Read last posted file from log file."""
    if not os.path.exists(LOG_FILE):
        return None
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

def save_last_posted(filename):
    """Save last posted file to log file."""
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(filename)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    # 1. Get latest file
    latest_file = get_latest_md()
    if not latest_file:
        print("⚠️ No .md files found in conference_discord/")
        await bot.close()
        return

    # 2. End if info has not changed
    last_posted = get_last_posted()
    if last_posted == os.path.basename(latest_file):
        print("Latest file already posted. Skipping.")
        await bot.close()
        return

    with open(latest_file, "r", encoding="utf-8") as f:
        md_text = f.read()

    # 3. Delete old posts
    async for msg in channel.history(limit=100):
        if msg.author == bot.user:
            await msg.delete()

    # 4. Post new info
    sections = split_by_category(md_text)
    for section in sections:
        if section.strip():
            await channel.send(section)

    save_last_posted(os.path.basename(latest_file))
    print(f"✅ Posted {latest_file} and updated log.")
    await bot.close()

if __name__ == "__main__":
    bot.run(TOKEN)




# import os
# import glob
# from datetime import datetime
# import discord
# from discord.ext import commands
# from dotenv import load_dotenv
#
# # ---- Load environment variables ----
# load_dotenv()
# TOKEN = os.getenv("popo_token")
# CHANNEL_ID = int(os.getenv("conference_dates_channel"))
#
# # ---- Bot Setup ----
# intents = discord.Intents.default()
# bot = commands.Bot(command_prefix="!", intents=intents)
#
# def get_latest_md():
#     """Find the newest .md file in conference_discord/"""
#     files = glob.glob("conference_discord/*.md")
#     if not files:
#         return None
#     latest = max(files, key=os.path.getmtime)
#     return latest
#
# def split_by_category(md_text):
#     """Split markdown into chunks by ## headers."""
#     parts = []
#     current = []
#     for line in md_text.splitlines():
#         if line.startswith("## "):
#             if current:
#                 parts.append("\n".join(current))
#                 current = []
#         current.append(line)
#     if current:
#         parts.append("\n".join(current))
#     return parts
#
# @bot.event
# async def on_ready():
#     print(f"✅ Logged in as {bot.user}")
#
#     channel = bot.get_channel(CHANNEL_ID)
#
#     # 1. Get latest file
#     latest_file = get_latest_md()
#     if not latest_file:
#         print("⚠️ No .md files found in conference_discord/")
#         await bot.close()
#         return
#
#     with open(latest_file, "r", encoding="utf-8") as f:
#         md_text = f.read()
#
#     # 2. Delete previous bot messages
#     async for msg in channel.history(limit=200):
#         if msg.author == bot.user:
#             await msg.delete()
#
#     # 3. Split into categories and post
#     sections = split_by_category(md_text)
#     for section in sections:
#         if section.strip():
#             await channel.send(section)
#
#     print("✅ Posted updated conference dates.")
#     await bot.close()
#
#
# if __name__ == "__main__":
#     bot.run(TOKEN)
