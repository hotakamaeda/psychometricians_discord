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
NEWS_CHANNEL_ID = int(os.getenv("news_channel"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # if you want access to member info
intents.guilds = True   # always recommended
bot = commands.Bot(command_prefix="!", intents=intents)

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
    this_week_et = (datetime.now(eastern) + timedelta(days=7)).date()
    today_is_monday = datetime.today().weekday() != 0

    todays_events = []
    this_week_events = []

    for event in events:
        start_et = event.start_time.astimezone(eastern).date()
        if start_et == today_et:
            todays_events.append(event)
        elif start_et <= this_week_et:
            this_week_events.append(event)

    # print(today_is_monday)
    # print(todays_events)
    # print(this_week_events)
    # raise

    if not todays_events and not today_is_monday:
        return  # send nothing

    channel = bot.get_channel(NEWS_CHANNEL_ID)

    if todays_events:
        await asyncio.sleep(.3)
        await channel.send("## :date: **Events Today!**")
        for e in todays_events:
            if hasattr(e, "url"):
                event_link = e.url
                await asyncio.sleep(.3)
                await channel.send(event_link)
            else:
                continue

    # Weekly event list sent only on Mondays
    if this_week_events and today_is_monday:
        await asyncio.sleep(.3)
        await channel.send("## :date: **Events This Week!**")
        for e in this_week_events:
            if hasattr(e, "url"):
                event_link = e.url
                await asyncio.sleep(.3)
                await channel.send(event_link)
            else:
                continue


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Wait briefly to ensure guild list is populated
    await asyncio.sleep(2)

    await send_daily_event_reminders()

    # After sending, safely close the bot so the script exits
    await bot.close()


bot.run(TOKEN)
