import os
import json
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import feedparser
import re
from datetime import datetime

# ---------- CONFIG ----------
load_dotenv()

TOKEN = os.getenv("popo_token")
FORUM_CHANNEL_ID = int(os.getenv("position_channel"))

POSTED_FILE = "posted_jobs.json"

RSS_FEEDS = {
    "job": "https://ncme.org/?feed=job_feed&job_types&search_location&job_categories=professional-role&search_keywords",
    "internship": "https://ncme.org/?feed=job_feed&job_types&search_location&job_categories=internship&search_keywords",
}

FORUM_TAG_IDS = {
    "job": 1447846201201393738,
    "internship": 1447846351156150283,
}

# ---------- DISCORD ----------
intents = discord.Intents.default()
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- UTIL ----------
def load_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_posted(posted):
    with open(POSTED_FILE, "w") as f:
        json.dump(sorted(list(posted)), f, indent=2)

def clean_html(text):
    if not text:
        return ""
    text = re.sub("<[^<]+?>", "", text)
    return text.strip()

def clean_text(text, max_len=1900):
    if not text:
        return ""
    text = text.replace("</p>", "\n")
    text = text.replace("\xa0", " ")
    text = re.sub("<[^<]+?>", "", text)
    return text[: max_len - 3] + "..." if len(text) > max_len else text

# ---------- RSS ----------
def fetch_rss(feed_url):
    return feedparser.parse(feed_url).entries

# ---------- MAIN ----------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    forum = bot.get_channel(FORUM_CHANNEL_ID)
    if not isinstance(forum, discord.ForumChannel):
        print("ERROR: Channel is not a forum channel.")
        await bot.close()
        return

    # Map tag_id -> ForumTag object
    tag_map = {tag.id: tag for tag in forum.available_tags}

    posted = load_posted()
    new_posted = set(posted)

    for tag_type, feed_url in RSS_FEEDS.items():
        entries = fetch_rss(feed_url)
        forum_tag = tag_map.get(FORUM_TAG_IDS[tag_type])

        if forum_tag is None:
            print(f"Missing forum tag for {tag_type}")
            continue

        for e in entries:
            guid = e.get("id") or e.get("guid") or e.get("link")
            if not guid or guid in posted:
                continue

            title = clean_text(e.get("title", "Untitled Position"), 100)
            link = e.get("link", "")
            summary = clean_text(e.get("content", "")[0].get("value", ""), 1900)
            content = (
                f"{summary}\n"
                f"🔗 **See Posting:** {link}"
            )

            try:
                await forum.create_thread(
                    name=title,
                    content=content[:2000],
                    applied_tags=[forum_tag],
                )
                print(f"Posted: {title}")
                new_posted.add(guid)
                await asyncio.sleep(0.5)

            except Exception as ex:
                print(f"Error posting {title}: {ex}")

    save_posted(new_posted)
    await bot.close()

# ---------- RUN ----------
bot.run(TOKEN)
