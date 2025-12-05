import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import pytz  # pip install pytz

# ---- Config ----
load_dotenv()
TOKEN = os.getenv("popo_token")
GENERAL_CHANNEL_ID = int(os.getenv("general_channel"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # if you want access to member info
intents.guilds = True   # always recommended
bot = commands.Bot(command_prefix="!", intents=intents)

eastern = pytz.timezone("US/Eastern")

def format_event(event):
    # Convert event start time to Eastern Time
    start_et = event.start_time.astimezone(eastern)
    date_time_str = start_et.strftime("%A, %B %d, %Y - %I:%M %p ET")

    # Event URL is available
    event_link = event.url if hasattr(event, "url") else "(No link available)"

    return f"{'[**' + event.name + '**](<' + event_link + '>)'}\n📅 {date_time_str}"


async def send_daily_event_reminders():
    """Your function that pulls Discord scheduled events and sends reminders."""
    # Get the guild
    guild = bot.guilds[0]

    if guild is None:
        print("Bot has no access to guild or guild ID is wrong.")
        return

    # Fetch scheduled events
    events = await guild.fetch_scheduled_events()

    eastern = pytz.timezone("US/Eastern")
    today_et = datetime.now(eastern).date()
    tomorrow_et = (datetime.now(eastern) + timedelta(days=1)).date()

    todays_events = []
    tomorrows_events = []

    for event in events:
        start_et = event.start_time.astimezone(eastern).date()
        if start_et == today_et:
            todays_events.append(event)
        elif start_et == tomorrow_et:
            tomorrows_events.append(event)

    if not todays_events and not tomorrows_events:
        return  # send nothing

    channel = bot.get_channel(GENERAL_CHANNEL_ID)

    msg = "## :date: **Upcoming Events!**\n\n"

    if todays_events:
        for e in todays_events:
            if hasattr(e, "url"):
                event_link = e.url
            else:
                continue
            msg += event_link + "\n"

    if tomorrows_events:
        for e in tomorrows_events:
            if hasattr(e, "url"):
                event_link = e.url
            else:
                continue
            msg += event_link + "\n"

    print(msg)
    await channel.send(msg)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Wait briefly to ensure guild list is populated
    await asyncio.sleep(2)

    await send_daily_event_reminders()

    # After sending, safely close the bot so the script exits
    await bot.close()


bot.run(TOKEN)
