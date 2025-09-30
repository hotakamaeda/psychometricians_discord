import os
import json
import requests
from bs4 import BeautifulSoup
import time
from msal import PublicClientApplication, SerializableTokenCache
from dotenv import load_dotenv

# ---- Load secrets ----
load_dotenv()
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
DISCORD_WEBHOOK_AIME = os.getenv("DISCORD_WEBHOOK_EMAILS_AIME")
DISCORD_WEBHOOK_NCME = os.getenv("DISCORD_WEBHOOK_EMAILS_NCME")
DISCORD_WEBHOOK_IMPS = os.getenv("DISCORD_WEBHOOK_EMAILS_IMPS")

# ---- Config ----
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["Mail.Read"]
CACHE_FILE = "token_cache.json"
SAVE_FILE = "sent_emails.json"
MAX_DISCORD_LEN = 1900  # leave some room for formatting
keywords_AIME = ["AIME", "Artificial Intelligence in Measurement and Education"]
keywords_NCME = ["NCME", "national council on measurement in education"]
keywords_IMPS = ["IMPS", "Psychometrics Society"]

# ---- Setup token cache ----
token_cache = SerializableTokenCache()
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        token_cache.deserialize(f.read())

app = PublicClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    token_cache=token_cache
)

# ---- Try silent login ----
accounts = app.get_accounts()
if accounts:
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
else:
    result = None

# ---- First run fallback ----
if not result:
    result = app.acquire_token_interactive(scopes=SCOPES)

# ---- Save updated cache ----
with open(CACHE_FILE, "w") as f:
    f.write(token_cache.serialize())

# ---- Load sent IDs ----
if os.path.exists(SAVE_FILE):
    with open(SAVE_FILE, "r") as f:
        sent_ids = set(json.load(f))
else:
    sent_ids = set()

# ---- Fetch messages (with body included) ----
headers = {"Authorization": f"Bearer {result['access_token']}"}
url = "https://graph.microsoft.com/v1.0/me/messages?$top=25&$orderby=receivedDateTime desc&$select=id,subject,from,body"
resp = requests.get(url, headers=headers)
data = resp.json()

if "value" not in data:
    raise Exception(f"Graph API error: {data}")

new_sent = False

# ---- Formatting to discord ----
def send_to_discord(webhook, subject, sender, body_text) -> bool:
    header = f"__FROM:__ {sender}\n__SUBJECT:__ {subject}\n\n"
    chunks = [body_text[i:i+MAX_DISCORD_LEN] for i in range(0, len(body_text), MAX_DISCORD_LEN)] or ["(no content)"]

    for idx, chunk in enumerate(chunks):
        content = header + chunk if idx == 0 else chunk
        payload = {"content": content}

        # simple retry with 429 handling
        for attempt in range(3):
            r = requests.post(webhook, json=payload, timeout=15)
            time.sleep(.5)
            if r.status_code in (200, 204):
                break
            if r.status_code == 429:
                try:
                    delay = float(r.json().get("retry_after", 2))
                except Exception:
                    delay = 2.0
                time.sleep(delay)
                continue
            print(f"Discord error {r.status_code}: {r.text}")
            return False
    return True


# ---- Process messages ----
new_sent = False
for msg in data["value"]:
    msg_id = msg["id"]
    subject = msg.get("subject", "(no subject)")
    sender = msg.get("from", {}).get("emailAddress", {}).get("address", "unknown")

    # Skip already-sent
    if msg_id in sent_ids:
        continue

    # Extract & clean body text
    body_content = msg.get("body", {}).get("content", "")
    soup = BeautifulSoup(body_content, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    body_text = soup.get_text(separator="\n", strip=True)

    # Combined text for matching
    text = f"{subject} {sender} {body_text}".lower()

    # If the keywords match, Route to the right webhook
    sent_ok = False
    if any(kw.lower() in text for kw in keywords_AIME):
        sent_ok = send_to_discord(DISCORD_WEBHOOK_AIME, subject, sender, body_text)
    elif any(kw.lower() in text for kw in keywords_NCME):
        sent_ok = send_to_discord(DISCORD_WEBHOOK_NCME, subject, sender, body_text)
    elif any(kw.lower() in text for kw in keywords_IMPS):
        sent_ok = send_to_discord(DISCORD_WEBHOOK_IMPS, subject, sender, body_text)

    if sent_ok:
        sent_ids.add(msg_id)
        new_sent = True
    else:
        # If nothing matched, just continue
        continue

# ---- Save updated sent IDs ----
if new_sent:
    with open(SAVE_FILE, "w") as f:
        json.dump(list(sent_ids), f)

