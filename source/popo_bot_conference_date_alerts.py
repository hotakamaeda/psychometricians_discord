import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime
from dateutil.relativedelta import relativedelta
import requests

# ---- Config ----
load_dotenv()

def conference_alerts(today_is_monday, DISCORD_WEBHOOK_ANNOUNCEMENTS):

    TOKEN = os.getenv("popo_token")
    CONFERENCE_CHANNEL_ID = int(os.getenv("conference_dates_channel"))
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = "gpt-5-nano"

    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    client = OpenAI(api_key=OPENAI_API_KEY)

    def webhook_send(content: str):
        """Send a plain message to Discord via webhook."""
        if not DISCORD_WEBHOOK_ANNOUNCEMENTS:
            print("Missing DISCORD_WEBHOOK in environment.")
            return

        response = requests.post(
            DISCORD_WEBHOOK_ANNOUNCEMENTS,
            json={"content": content},
            timeout=10,  # optional but recommended
        )

        # Discord webhook success is usually 204 No Content (sometimes 200)
        if response.status_code not in (200, 204):
            print(f"Webhook failed: {response.status_code} {response.text}")


    async def fetch_latest_conference_messages(channel):
        """Fetch the most recent message from the conference channel by the bot."""
        messages = [msg async for msg in channel.history(limit=10)]
        if not messages:
            return None
        # Take the most recent message
        combined = "\n".join(reversed([msg.content for msg in messages]))
        # Keep only lines that begin with "[" or "*"
        filtered_lines = [
            line for line in combined.splitlines()
            if line.strip().startswith("[") or line.strip().startswith("*")
        ]

        return "\n".join(filtered_lines)

    def ask_gpt_for_upcoming(text):
        """Ask GPT-5-nano to extract conferences with dates in the next month."""
        today = datetime.today().strftime("%B %d, %Y")

        # Calculate the date one month from now
        one_month_from_now = (datetime.today() + relativedelta(months=1)).strftime("%B %d, %Y")

        prompt = f"""
    Here is a list of conferences and their dates (conference dates and submission deadlines):
    
    {text}
    
    Please return only the conferences that have a conference date or submission deadline
    between today and 1 month from now. 
    Today's date is {today}.
    The date 1 month from now is {one_month_from_now}. 
    Include the name of the conference and its information without altering the text.
    If none are upcoming within a month, say 'NA'
        """

        # return(prompt)
        resp = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": "You are an assistant that extracts and formats conference dates."},
                {"role": "user", "content": prompt}
            ],
            service_tier="flex"
        )
        return resp.output_text.strip()


    @bot.event
    async def on_ready():
        # Monday-only guard
        if not today_is_monday:  # Monday=0
            print("[i] Not Monday → skipping alert.")
            await bot.close()
            return

        print(f"✅ Logged in as {bot.user}")
        conf_channel = bot.get_channel(CONFERENCE_CHANNEL_ID)

        # Step 1: get latest conference dates message
        latest_conf_text = await fetch_latest_conference_messages(conf_channel)
        if not latest_conf_text:
            # await gen_channel.send("⚠️ Could not fetch latest conference dates.")
            summary = "Error"

        else:
            # Step 2: process with GPT
            summary = ask_gpt_for_upcoming(latest_conf_text)
        # print(summary)

        # Step 3: send to general channel
        if summary.strip().upper() != "NA":
            webhook_send("### :calendar_spiral: Upcoming Conferences and Deadlines in the next 1 month\n" + summary)

        await bot.close()

    # Run!
    bot.run(TOKEN)
