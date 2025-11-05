import os
import re
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from dotenv import load_dotenv
import asyncio

# ---- Load environment variables ----
load_dotenv()
TOKEN = os.getenv("popo_token")
SHARE_CHANNEL_ID = int(os.getenv("share_your_work_channel"))
INTRO_CHANNEL_ID = int(os.getenv("introduce_yourself_channel"))  # new channel ID
WELCOME_CHANNEL_ID = int(os.getenv("welcome_channel"))
GENERAL_CHANNEL_ID = int(os.getenv("general_channel"))
RESEARCH_CHANNEL_ID = int(os.getenv("daily_research_channel"))


# ---- Discord setup ----
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True
intents.presences = True  # required for idle detection

bot = commands.Bot(command_prefix="!", intents=intents)

# ---- Voice activity tracking ----
voice_join_times = {}
CHECK_INTERVAL = 60  # seconds
IDLE_LIMIT = timedelta(minutes=30)
TOTAL_LIMIT = timedelta(minutes=180)

# ============================================================
#                         BOT READY
# ============================================================

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    check_inactive_users.start()


# ============================================================
#                     NEW MEMBER GREETING
# ============================================================

@bot.event
async def on_member_join(member):
    """Prompt new members to introduce themselves and explore the server."""
    await asyncio.sleep(5)  # short delay to avoid race condition

    intro_channel = bot.get_channel(INTRO_CHANNEL_ID)
    if not intro_channel:
        print("⚠️ Introduce-yourself channel not found.")
        return

    try:
        await intro_channel.send(
            f"👋 Welcome {member.mention} to the Psychometricians Community!\n\n"
            f"Take a moment to **introduce yourself** here! What is your background? Or your interests?\n\n"
            f"📘 Please read <#{WELCOME_CHANNEL_ID}> for server tips, "
            f"browse research papers in <#{RESEARCH_CHANNEL_ID}>, "
            f"and chat casually in <#{GENERAL_CHANNEL_ID}>!"
        )
    except Exception as e:
        print(f"⚠️ Could not send intro message: {e}")

# ============================================================
#                    MESSAGE MODERATION
# ============================================================

@bot.event
async def on_message(message):
    """Moderate posts in 'share-your-work' channel."""
    if message.author.bot:
        return

    if message.channel.id == SHARE_CHANNEL_ID:
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

    await bot.process_commands(message)  # allow commands to work too

# ============================================================
#                  VOICE ACTIVITY TRACKING
# ============================================================

@bot.event
async def on_voice_state_update(member, before, after):
    """Track when users join or leave voice channels."""
    if before.channel is None and after.channel is not None:
        voice_join_times[member.id] = datetime.utcnow()
    elif before.channel is not None and after.channel is None:
        voice_join_times.pop(member.id, None)

@tasks.loop(seconds=CHECK_INTERVAL)
async def check_inactive_users():
    """Periodically disconnect idle or long-staying users."""
    now = datetime.utcnow()
    to_remove = []

    for user_id, join_time in list(voice_join_times.items()):
        member = bot.get_user(user_id)
        if not member:
            continue

        # Skip if not in voice anymore
        if not member.voice or not member.voice.channel:
            to_remove.append(user_id)
            continue

        time_in_channel = now - join_time

        # Idle users after 30 minutes
        if member.status == discord.Status.idle and time_in_channel > IDLE_LIMIT:
            try:
                await member.move_to(None)
                print(f"😴 Disconnected idle user {member.display_name}")
            except Exception as e:
                print(f"⚠️ Could not disconnect idle user {member}: {e}")
            to_remove.append(user_id)

        # All users after 3 hours
        elif time_in_channel > TOTAL_LIMIT:
            try:
                await member.move_to(None)
                print(f"🕒 Disconnected {member.display_name} after 3 hours")
            except Exception as e:
                print(f"⚠️ Could not disconnect long user {member}: {e}")
            to_remove.append(user_id)

    # Cleanup
    for uid in to_remove:
        voice_join_times.pop(uid, None)

# ============================================================
#                         RUN BOT
# ============================================================

if __name__ == "__main__":
    bot.run(TOKEN)
