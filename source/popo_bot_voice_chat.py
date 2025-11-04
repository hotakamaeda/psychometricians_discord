import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.presences = True  # required to detect "Idle" users
bot = commands.Bot(command_prefix="!", intents=intents)

# Track join times
voice_join_times = {}
CHECK_INTERVAL = 60  # check every 60 seconds
IDLE_LIMIT = timedelta(minutes=30)
TOTAL_LIMIT = timedelta(minutes=180)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    check_inactive_users.start()

@bot.event
async def on_voice_state_update(member, before, after):
    """Track who joins/leaves voice channels."""
    if before.channel is None and after.channel is not None:
        voice_join_times[member.id] = datetime.utcnow()
    elif before.channel is not None and after.channel is None:
        voice_join_times.pop(member.id, None)

@tasks.loop(seconds=CHECK_INTERVAL)
async def check_inactive_users():
    now = datetime.utcnow()
    to_remove = []

    for user_id, join_time in list(voice_join_times.items()):
        member = bot.get_user(user_id)
        if not member:
            continue

        # Skip if not currently in a voice channel
        if not member.voice or not member.voice.channel:
            to_remove.append(user_id)
            continue

        time_in_channel = now - join_time

        # Check for Idle users (needs presence intent)
        if member.status == discord.Status.idle and time_in_channel > IDLE_LIMIT:
            try:
                await member.move_to(None)
                print(f"😴 Kicked idle user {member.display_name} (>{IDLE_LIMIT}).")
            except Exception as e:
                print(f"⚠️ Could not move idle {member}: {e}")
            to_remove.append(user_id)

        # Check for total time limit
        elif time_in_channel > TOTAL_LIMIT:
            try:
                await member.move_to(None)
                print(f"🕒 Kicked long-stay user {member.display_name} (>{TOTAL_LIMIT}).")
            except Exception as e:
                print(f"⚠️ Could not move long-stay {member}: {e}")
            to_remove.append(user_id)

    # Cleanup
    for uid in to_remove:
        voice_join_times.pop(uid, None)

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    TOKEN = os.getenv("popo_token")
    bot.run(TOKEN)
