from msal import PublicClientApplication, SerializableTokenCache
import os, requests

CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["Mail.Read"]

CACHE_FILE = "token_cache.json"
token_cache = SerializableTokenCache()

# Load cache from file
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        token_cache.deserialize(f.read())

# Create app with cache
app = PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=token_cache)

# Try silent refresh
accounts = app.get_accounts()
if accounts:
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
else:
    result = None

# If no cached token, do interactive (first run only)
if not result:
    result = app.acquire_token_interactive(scopes=SCOPES)

# Save cache back to file
with open(CACHE_FILE, "w") as f:
    f.write(token_cache.serialize())

# Use the access token
headers = {"Authorization": f"Bearer {result['access_token']}"}
resp = requests.get("https://graph.microsoft.com/v1.0/me/messages?$top=5", headers=headers)
print(resp.json())
