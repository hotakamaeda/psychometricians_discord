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
INTRO_CHANNEL_ID = int(os.getenv("introduce_yourself_channel"))
WELCOME_CHANNEL_ID = int(os.getenv("welcome_channel"))
GENERAL_CHANNEL_ID = int(os.getenv("general_channel"))
RESEARCH_CHANNEL_ID = int(os.getenv("daily_research_channel"))
ANNOUNCEMENT_CHANNEL_ID = int(os.getenv("announcement_channel"))

# ---- Discord setup ----
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True
intents.presences = True
intents.guild_scheduled_events = True  # important for scheduled event hooks/cache

bot = commands.Bot(command_prefix="!", intents=intents)

# ---- Voice activity tracking ----
voice_join_times = {}
CHECK_INTERVAL = 60  # seconds
IDLE_LIMIT = timedelta(minutes=30)
TOTAL_LIMIT = timedelta(minutes=180)

# ---- Scheduled event tracking ----
EVENT_REMINDER_WINDOW = timedelta(minutes=5)
EVENT_START_GRACE = timedelta(minutes=1)   # small grace window
EVENT_END_GRACE = timedelta(minutes=1)

reminded_event_ids = set()
started_event_ids = set()
ended_event_ids = set()


# ============================================================
#                         BOT READY
# ============================================================

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    if not check_inactive_users.is_running():
        check_inactive_users.start()

    if not event_reminder_loop.is_running():
        event_reminder_loop.start()

    if not voice_event_status_loop.is_running():
        voice_event_status_loop.start()


# ============================================================
#                     NEW MEMBER GREETING
# ============================================================

@bot.event
async def on_member_join(member):
    """Prompt new members to introduce themselves and explore the server."""
    await asyncio.sleep(5)

    intro_channel = bot.get_channel(INTRO_CHANNEL_ID)
    if not intro_channel:
        print("⚠️ Introduce-yourself channel not found.")
        return

    try:
        await intro_channel.send(
            f"👋 Welcome {member.mention} to the Psychometricians Community!\n\n"
            f"**Introduce yourself** here! What is your background/interests?\n\n"
            f"📘 Read <#{WELCOME_CHANNEL_ID}> first for server tips, "
            f"browse research papers in <#{RESEARCH_CHANNEL_ID}>, "
            f"and chat casually in <#{GENERAL_CHANNEL_ID}>!"
        )
    except Exception as e:
        print(f"⚠️ Could not send intro message: {e}")


# ============================================================
#                    MESSAGE MODERATION
# ============================================================
#
# @bot.event
# async def on_message(message):
#     """Moderate posts in 'share-your-work' channel."""
#     if message.author.bot:
#         return
#
#     if message.channel.id == SHARE_CHANNEL_ID:
#         has_attachment = len(message.attachments) > 0
#         url_pattern = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
#         has_link = bool(url_pattern.search(message.content.lower()))
#
#         if not (has_attachment or has_link):
#             await message.delete()
#             await message.channel.send(
#                 f"Hey {message.author.mention}! This channel is for sharing **papers, presentations, and programs.**\n"
#                 f"✅ Please __include a link or attachment__ plus optional title & authors of your work!\n"
#                 f"💬 Want to discuss instead? Right-click a post and create a thread! :hippopotamus:",
#                 delete_after=60
#             )
#
#     await bot.process_commands(message)


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

        if not member.voice or not member.voice.channel:
            to_remove.append(user_id)
            continue

        time_in_channel = now - join_time

        if member.status == discord.Status.idle and time_in_channel > IDLE_LIMIT:
            try:
                await member.move_to(None)
                print(f"😴 Disconnected idle user {member.display_name}")
            except Exception as e:
                print(f"⚠️ Could not disconnect idle user {member}: {e}")
            to_remove.append(user_id)

        elif time_in_channel > TOTAL_LIMIT:
            try:
                await member.move_to(None)
                print(f"🕒 Disconnected {member.display_name} after 3 hours")
            except Exception as e:
                print(f"⚠️ Could not disconnect long user {member}: {e}")
            to_remove.append(user_id)

    for uid in to_remove:
        voice_join_times.pop(uid, None)

# ============================================================
#                   5 Minute Event Reminder using "@"
# ============================================================

async def get_all_scheduled_events():
    """Fetch all scheduled events from all guilds the bot is in."""
    all_events = []
    for guild in bot.guilds:
        try:
            events = await guild.fetch_scheduled_events()
            all_events.extend(events)
        except Exception as e:
            print(f"⚠️ Could not fetch scheduled events for guild {guild.id}: {e}")
    return all_events

@tasks.loop(seconds=30)
async def event_reminder_loop():
    now = discord.utils.utcnow()
    announcement_channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)

    if announcement_channel is None:
        print("⚠️ Announcement channel not found.")
        return

    events = await get_all_scheduled_events()

    for event in events:
        # Ignore events already reminded or not in scheduled state
        if event.id in reminded_event_ids:
            continue
        if event.status != discord.EventStatus.scheduled:
            continue
        if event.start_time is None:
            continue

        time_until_start = event.start_time - now

        # Trigger once when event is within the 5-minute window
        if timedelta(0) <= time_until_start <= EVENT_REMINDER_WINDOW:
            try:
                mentions = []

                # Best source of truth: fetch currently subscribed users from Discord
                async for user in event.users(limit=None):
                    mentions.append(user.mention)

                if mentions:
                    mention_text = " ".join(mentions)
                    msg = f"Event **{event.name}** is starting soon! {mention_text}"
                else:
                    msg = f"Event **{event.name}** is starting soon!"

                await announcement_channel.send(msg)
                reminded_event_ids.add(event.id)
                print(f"🔔 Sent 5-minute reminder for event: {event.name}")

            except Exception as e:
                print(f"⚠️ Could not send reminder for event {event.name}: {e}")

    # cleanup old reminder ids
    for event in events:
        if event.status == discord.EventStatus.ended:
            reminded_event_ids.discard(event.id)


@event_reminder_loop.before_loop
async def before_event_reminder_loop():
    await bot.wait_until_ready()


# ============================================================
#                   Voice Event Starter / Ender
# ============================================================

@tasks.loop(seconds=30)
async def voice_event_status_loop():
    now = discord.utils.utcnow()
    events = await get_all_scheduled_events()

    for event in events:
        try:
            # Only auto-handle voice/stage events
            if event.entity_type not in (discord.EntityType.voice, discord.EntityType.stage_instance):
                continue

            # Auto-start scheduled events
            if (
                event.status == discord.EventStatus.scheduled
                and event.start_time is not None
                and event.id not in started_event_ids
                and now >= (event.start_time - EVENT_START_GRACE)
            ):
                await event.start()
                started_event_ids.add(event.id)
                print(f"▶️ Auto-started event: {event.name}")

            # Auto-end active events
            if (
                event.status == discord.EventStatus.active
                and event.end_time is not None
                and event.id not in ended_event_ids
                and now >= (event.end_time - EVENT_END_GRACE)
            ):
                await event.end()
                ended_event_ids.add(event.id)
                print(f"⏹️ Auto-ended event: {event.name}")

            # If there is no end_time, skip ending
        except Exception as e:
            print(f"⚠️ Could not update event status for {event.name}: {e}")

    # cleanup sets for ended events
    for event in events:
        if event.status == discord.EventStatus.ended:
            reminded_event_ids.discard(event.id)
            started_event_ids.discard(event.id)
            ended_event_ids.discard(event.id)


@voice_event_status_loop.before_loop
async def before_voice_event_status_loop():
    await bot.wait_until_ready()


# ============================================================
#                         RUN BOT
# ============================================================

if __name__ == "__main__":
    bot.run(TOKEN)