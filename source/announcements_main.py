import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import pytz  # pip install pytz
from source.news_to_discord import gpt_news
from source.popo_bot_event_alerts import event_alerts
from source.popo_bot_conference_date_alerts import conference_alerts
from source.monday_alerts_end import monday_alerts_end

# ---- Config ----
load_dotenv()
DISCORD_WEBHOOK_NEWS = os.getenv("DISCORD_WEBHOOK_NEWS")
DISCORD_WEBHOOK_ANNOUNCEMENTS = os.getenv("DISCORD_WEBHOOK_ANNOUNCEMENTS")

# Is today Monday? (Eastern time) ----
eastern = pytz.timezone("US/Eastern")
today_et = datetime.now(eastern).date()
today_is_monday = today_et.weekday() == 0

# Uncomment this is for testing purposes ---------
DISCORD_WEBHOOK_NEWS = os.getenv("DISCORD_WEBHOOK_DRAFT")
DISCORD_WEBHOOK_ANNOUNCEMENTS = os.getenv("DISCORD_WEBHOOK_DRAFT")
today_is_monday = True

# ------- Run ------
def main():
    # Run individual scripts
    gpt_news(today_is_monday, DISCORD_WEBHOOK_NEWS)
    event_alerts(today_is_monday, DISCORD_WEBHOOK_ANNOUNCEMENTS)
    conference_alerts(today_is_monday, DISCORD_WEBHOOK_ANNOUNCEMENTS)
    monday_alerts_end(today_is_monday, DISCORD_WEBHOOK_ANNOUNCEMENTS)

if __name__ == "__main__":
    main()
