import requests

def monday_alerts_end(today_is_monday, DISCORD_WEBHOOK_ANNOUNCEMENTS):
    """Send final Monday announcement via webhook."""

    if not today_is_monday:
        return

    if not DISCORD_WEBHOOK_ANNOUNCEMENTS:
        print("Missing DISCORD_WEBHOOK in environment.")
        return

    response = requests.post(
        DISCORD_WEBHOOK_ANNOUNCEMENTS,
        json={
            "content": "That's all the Monday announcements.\nHave a nice week! 😄"
        }
    )

    if response.status_code not in (200, 204):
        print(f"Webhook failed: {response.status_code} {response.text}")

