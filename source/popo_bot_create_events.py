import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import requests
from ics import Calendar
from datetime import datetime, timedelta
import pytz

# ---- Config ----
load_dotenv()
TOKEN = os.getenv("popo_token")
NEWS_CHANNEL_ID = int(os.getenv("news_channel"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Currently creates only NCME events

# ---- Download NCME ICS ----
url = "https://ncme.org/ncme-events/list/?shortcode=6e6d5282&ical=1"
ics_data = requests.get(url).text
cal = Calendar(ics_data)

# ---- Convert ICS events into Python dicts ----
events = []
utc = pytz.utc
now = datetime.now(tz=utc)

for e in cal.events:
    begin = e.begin.to(utc).datetime
    end = e.end.to(utc).datetime

    # --- 1. Skip events that already ended ---
    if end < now:
        continue

    # --- 2. If already started, shift begin time to 15 minutes from now ---
    if begin < now:
        begin = now + timedelta(minutes=15)

    events.append({
        "name": e.name,
        "begin": begin,
        "end": end,
        "description": (e.location or "") + "\n" + (e.description or ""),
        "url": getattr(e, "url", None) or (e.location or "")
    })


# ---- Scheduling Function ----
async def schedule_events(events):
    guild = bot.guilds[0] if bot.guilds else None
    if guild is None:
        print("No guild found. Bot may not be in the server yet.")
        return

    # Pull scheduled events already in Discord
    preexisting_events = await guild.fetch_scheduled_events()
    existing_names = {ev.name for ev in preexisting_events}

    channel = bot.get_channel(NEWS_CHANNEL_ID)

    print(f"Found {len(events)} ICS events")
    print(f"Found {len(preexisting_events)} preexisting Discord events")
    # print(existing_names)

    for ev in events:
        print(ev["name"])
        if ev["name"] not in existing_names:
            # Create new event
            try:
                created = await guild.create_scheduled_event(
                    name=ev["name"],
                    start_time=ev["begin"],
                    end_time=ev["end"],
                    description=ev["description"],
                    privacy_level=discord.PrivacyLevel.guild_only,
                    entity_type=discord.EntityType.external,
                    location=ev["url"]
                )
                msg = (
                    f"## :date: **New NCME Event!**\n"
                    f"{created.url}"  # ← This is the clickable Discord event link
                )
                await channel.send(msg)
                await asyncio.sleep(0.3)

            except Exception as e:
                print(f"Error creating event: {e}")


# ---- Bot Ready ----
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await asyncio.sleep(2)
    await schedule_events(events)
    await bot.close()


bot.run(TOKEN)
