import re
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()  # loads .env in the same directory
TOKEN = os.getenv("popo_token")
CHANNEL_ID = int(os.getenv("share_your_work_channel"))  # Showcase channel ID

intents = discord.Intents.default()
intents.message_content = True  # needed to read messages
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id == CHANNEL_ID:
        has_attachment = len(message.attachments) > 0
        url_pattern = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
        has_link = bool(url_pattern.search(message.content.lower()))

        if not (has_attachment or has_link):
            await message.delete()
            await message.channel.send(
                f"Hey {message.author.mention}! This channel is for sharing **papers, presentations, and programs.**\n"
                f"✅ Please __include a link or attachment__ plus optional title & authors of your work!\n"
                f"💬 Want to discuss instead? Right-click a post and create a thread! :hippopotamus:",
                delete_after=60
            )

    await bot.process_commands(message)  # allow commands too

bot.run(TOKEN)

