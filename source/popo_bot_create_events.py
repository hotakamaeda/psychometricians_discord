import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import requests
from ics import Calendar
from datetime import datetime, timedelta
import pytz
import re

# ---- Config ----
load_dotenv()
TOKEN = os.getenv("popo_token")
DISCORD_WEBHOOK_ANNOUNCEMENTS = os.getenv("DISCORD_WEBHOOK_ANNOUNCEMENTS")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)
VOICE_CHANNEL_ID = int(os.getenv("VOICE_CHANNEL_ID"))
WEEKLY_VOICE_EVENT_NAME = "Weekly voice/video chat!"

# Currently creates only NCME events

def webhook_send(content: str):
    """Send a plain message to Discord via webhook (sync)."""
    if not DISCORD_WEBHOOK_ANNOUNCEMENTS:
        print("Missing DISCORD_WEBHOOK_ANNOUNCEMENTS in environment.")
        return

    resp = requests.post(DISCORD_WEBHOOK_ANNOUNCEMENTS, json={"content": content})
    # Discord webhook success is usually 204 No Content (sometimes 200)
    if resp.status_code not in (200, 204):
        print(f"Webhook failed: {resp.status_code} {resp.text}")

# ---- Download NCME ICS ----
url = "https://ncme.org/ncme-events/list/?ical=1"
ics_data = requests.get(url).text
cal = Calendar(ics_data)

# ---- Convert ICS events into Python dicts ----
events = []
utc = pytz.utc
now = datetime.now(tz=utc)

def shorten_url(url):
    api = "https://is.gd/create.php"
    r = requests.get(api, params={"format": "simple", "url": url})
    if r.status_code == 200:
        return r.text.strip()
    return "https://ncme.org/events/webinars/"  # fallback

for e in cal.events:
    begin = e.begin.to(utc).datetime
    end = e.end.to(utc).datetime

    # --- 1. Skip events that already ended ---
    if end < now:
        continue

    # --- 2. If already started, shift begin time to 15 minutes from now ---
    if begin < now:
        begin = now + timedelta(minutes=15)

    # --- 3. Build raw description
    raw_desc = (e.location or "") + "\n" + (e.description or "")
    raw_desc = re.sub(r"\n+", "\n", raw_desc)
    if len(raw_desc) > 997:  # 997 + "..." = 1000
        raw_desc = raw_desc[:997] + "..."

    # --- 4. Build URL
    URL = getattr(e, "url", None) or (e.location or "")
    if len(URL) > 99:
        URL = shorten_url(URL)

    # --- 5. Build Name
    clean_name = ''.join(ch for ch in e.name if ch.isprintable()).strip()
    clean_name = clean_name[:100].strip()

    events.append({
        "name": clean_name,
        "begin": begin,
        "end": end,
        "description": raw_desc,
        "url": URL
    })

# ---- Scheduling Function ----
async def schedule_events(events):
    guild = bot.guilds[0] if bot.guilds else None
    if guild is None:
        print("No guild found. Bot may not be in the server yet.")
        return

    existing_events = await guild.fetch_scheduled_events()
    existing_by_name = {e.name: e for e in existing_events}

    print(f"Found {len(events)} ICS events")
    print(f"Found {len(existing_events)} preexisting Discord events")

    for ev in events:
        existing = existing_by_name.get(ev["name"])

        # -------------------------
        # CREATE NEW EVENT
        # -------------------------
        if existing is None:
            print(f"creating: {ev['name']}")

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
                    f"{created.url}"
                )
                webhook_send(msg)
                await asyncio.sleep(0.3)
                print("created")

            except Exception as e:
                print(f"Error creating event: {e}")

        # -------------------------
        # UPDATE EXISTING EVENT
        # -------------------------
        else:
            needs_update = False
            updates = {}

            if existing.start_time != ev["begin"]:
                updates["start_time"] = ev["begin"]
                needs_update = True
                print('update start_time')
                print(updates["start_time"])

            if existing.end_time != ev["end"]:
                updates["end_time"] = ev["end"]
                needs_update = True
                print('update end_time')
                print(updates["end_time"])

            if (existing.description or "") != (ev["description"] or ""):
                updates["description"] = ev["description"]
                needs_update = True
                print('update description')
                print(updates["description"])

            if needs_update:
                print(f"updating: {ev['name']}")

                try:
                    await existing.edit(**updates)
                    await asyncio.sleep(0.3)
                    print("updated")

                except Exception as e:
                    print(f"Error updating event {ev['name']}: {e}")

async def schedule_weekly_voice_chat():
    eastern = pytz.timezone("US/Eastern")
    utc = pytz.utc

    guild = bot.guilds[0] if bot.guilds else None
    if guild is None:
        print("No guild found. Bot may not be in the server yet.")
        return

    # Don't schedule if an event with the same name already exists
    existing_events = await guild.fetch_scheduled_events()
    if any(ev.name == WEEKLY_VOICE_EVENT_NAME for ev in existing_events):
        print(f"'{WEEKLY_VOICE_EVENT_NAME}' already exists. Skipping.")
        return

    # Find the next Thursday (ET)
    now_et = datetime.now(eastern)
    today_et = now_et.date()
    days_ahead = (3 - today_et.weekday()) % 7  # Thursday=3
    next_thursday = today_et + timedelta(days=days_ahead)

    # --- NEW: alternate time based on days since Jan 1 (0-based) ---
    jan1 = datetime(next_thursday.year, 1, 1).date()
    days_since_jan1 = (next_thursday - jan1).days  # Jan 1 => 0 (even)

    start_hour = 21 if (days_since_jan1 % 2 == 1) else 12  # odd => 9pm, even => 12pm

    start_et = eastern.localize(
        datetime(next_thursday.year, next_thursday.month, next_thursday.day, start_hour, 0, 0)
    )
    end_et = start_et + timedelta(hours=1)
    start_utc = start_et.astimezone(utc)
    end_utc = end_et.astimezone(utc)

    try:
        channel = bot.get_channel(VOICE_CHANNEL_ID)
        if channel is None:
            channel = await guild.fetch_channel(VOICE_CHANNEL_ID)  # reliable for short-lived scripts

        created = await guild.create_scheduled_event(
            name=WEEKLY_VOICE_EVENT_NAME,
            start_time=start_utc,
            end_time=end_utc,
            description="Chat about psychometrics, research, or off-topic things! Video is optional."
                        "Have fun! :stuck_out_tongue_winking_eye:"
                        "Schedule alternates between 12pm ET / 9pm ET based on even/odd days since January 1st.",
            privacy_level=discord.PrivacyLevel.guild_only,
            entity_type=discord.EntityType.voice,
            channel=channel,  # <-- THIS is how discord.py sets channel_id under the hood
        )
        msg = (
            f"## :date: **New Voice Chat Event!**\n"
            f"{created.url}"
        )
        webhook_send(msg)
        await asyncio.sleep(0.3)
        print("created Weekly voice chat")
    except Exception as e:
        print(f"Error creating weekly voice chat: {e}")


# ---- Bot Ready ----
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await asyncio.sleep(2)
    await schedule_events(events)
    await schedule_weekly_voice_chat()
    await bot.close()
    print(f"Logged out bot")

bot.run(TOKEN)
