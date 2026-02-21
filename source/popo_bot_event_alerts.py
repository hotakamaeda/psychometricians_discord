import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import pytz  # pip install pytz
import aiohttp  # pip install aiohttp

# ---- Config ----
load_dotenv()

def event_alerts(today_is_monday, DISCORD_WEBHOOK_ANNOUNCEMENTS):

    TOKEN = os.getenv("popo_token")
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True  # if you want access to member info
    intents.guilds = True   # always recommended
    bot = commands.Bot(command_prefix="!", intents=intents)

    async def webhook_send(content: str):
        """Send a plain message to Discord via webhook."""
        if not DISCORD_WEBHOOK_ANNOUNCEMENTS:
            print("Missing DISCORD_WEBHOOK in environment.")
            return

        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                DISCORD_WEBHOOK_ANNOUNCEMENTS,
                json={"content": content},
            )
            # Discord webhook success is usually 204 No Content
            if resp.status not in (200, 204):
                text = await resp.text()
                print(f"Webhook failed: {resp.status} {text}")


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

        todays_events = []
        this_week_events = []

        for event in events:
            start_et = event.start_time.astimezone(eastern).date()
            if start_et == today_et:
                todays_events.append(event)
            # starting after today, this week
            elif start_et > today_et and start_et <= this_week_et:
                this_week_events.append(event)

        if not todays_events and not today_is_monday:
            print("No Events Today. Today is not Monday")
            return  # send nothing

        if todays_events:
            print("Events Today")
            await asyncio.sleep(.3)
            await webhook_send("# :date: **Events Today!**")
            for e in todays_events:
                if hasattr(e, "url"):
                    event_link = e.url
                    await asyncio.sleep(.3)
                    await webhook_send(event_link)

        # Weekly event list sent only on Mondays
        if this_week_events and today_is_monday:
            print("Events next week and today is monday")
            await asyncio.sleep(.3)
            await webhook_send("### :date: **Events This Week!**")
            for e in this_week_events:
                if hasattr(e, "url"):
                    event_link = e.url
                    await asyncio.sleep(.3)
                    await webhook_send(event_link)


    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user} on {datetime.now(pytz.timezone('US/Eastern')).date()}")

        # Wait briefly to ensure guild list is populated
        await asyncio.sleep(2)

        await send_daily_event_reminders()

        # After sending, safely close the bot so the script exits
        await bot.close()
        print(f"Closing bot on {datetime.now(pytz.timezone('US/Eastern')).date()}")

    # Run!
    bot.run(TOKEN)
    