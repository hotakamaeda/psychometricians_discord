
import difflib
import time
import json
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime
from dateutil import parser as dateparser
from openai import OpenAI
import glob
import os
from dateutil.relativedelta import relativedelta
import re
from typing import List, Tuple



# ---- Config ----
load_dotenv()
SNAPSHOT_DIR = "conference_url_snapshots"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
DISCORD_WEBHOOK_CONFERENCE_UPDATES = os.getenv("DISCORD_WEBHOOK_CONFERENCE_UPDATES")


def parse_date_safe(date_str):
    """Try to parse a date string safely, return datetime or None."""
    try:
        return dateparser.parse(date_str, fuzzy=True)
    except Exception:
        return None

def clean_past_dates(conference):
    """Update submission/conference fields if they are in the past."""
    updated = conference.copy()

    # Check submission deadline
    sub_deadline = updated.get("submission_deadline", "")
    if sub_deadline and sub_deadline.lower() not in ["closed", "unknown"]:
        parsed = parse_date_safe(sub_deadline)
        if parsed and parsed.date() < datetime.today().date():
            updated["submission_deadline"] = "Closed"

    # Check conference date
    conf_end_date = updated.get("end_date", "")
    if conf_end_date and conf_end_date.lower() not in ["unknown"]:
        parsed = parse_date_safe(conf_end_date)
        if parsed and parsed.date() < datetime.today().date():
            updated["date"] = "unknown"
            updated["submission_deadline"] = "unknown"

    return updated


def call_gpt(current_info, system_prompt, prompt):
    """Ask GPT to validate if candidate dates are relevant and update JSON."""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                service_tier="flex",
                # temperature=0
            )
            break  # success → exit loop
        except Exception as e:
            print(f"Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                time.sleep(5)
            else:
                print("⚠️ GPT response error:", e)
                return current_info
    try:
        updated_json = json.loads(resp.choices[0].message.content)
        return updated_json
    except Exception as e:
        print("⚠️ GPT response parse error:", e)
        return current_info

def load_snapshot(filepath: str) -> str:
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return None

def expand_urls_years(urls, previous_year):
    """Expand URLs with {YEAR} placeholders."""
    expanded = []
    current_year = datetime.today().year
    years = sorted({
        max(previous_year + 1, current_year),
        current_year + 1
    })
    for url in urls:
        if "{YEAR}" in url:
            for y in years:
                expanded.append(url.replace("{YEAR}", str(y)))
        elif "{YR}" in url:
            for y in years:
                expanded.append(url.replace("{YR}", str(y)[-2:]))
        else:
            expanded.append(url)
    return years, expanded


def scrape_and_update(conference):
    updated = clean_past_dates(conference)
    abbreviation = updated.get("abbreviation", [])
    # Find year of next conference
    years, urls = expand_urls_years(updated.get("search_urls", []), int(updated.get("previous_year", [])))
    # previous_year = int(updated.get("previous_year", []))
    # next_conf_year = set([max(previous_year+1, current_year), next_year])
    # next_year = max(previous_year+1, current_year)
    candidates = []
    # pattern_year = f"[^\d]{str(years[0])}[^\d]"
    # if len(years)==2:
    #     pattern_year = pattern_year + f"|[^\d]{str(years[1])}[^\d]"
    # pattern = re.compile("(" + pattern_year + ")", re.IGNORECASE)

    for url in urls:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                              "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text("\n", strip=True)  # keep \n for formatting

            # --- change detection ---
            url_filename = abbreviation + "_" + re.sub(r'\W+', '_', url) + ".txt"
            snapshot_file = os.path.join(SNAPSHOT_DIR, url_filename)
            old_text = load_snapshot(snapshot_file)

            if old_text and old_text.strip() == text.strip():
                print(f"[NO CHANGE] Skipping {url}")
                continue  # skip this URL, no change
            else:
                print(f"[CHANGED] Updating snapshot for {url}")
                with open(snapshot_file, "w", encoding="utf-8") as f:
                    f.write(text)

            # --- proceed only if changed ---
            # (your date regex / search_names logic here)
            # cands = find_dates_with_context(text)
            # candidates.extend(cands)
            candidates.extend(text)

        except Exception as e:
            print(f"Error scraping {url}: {e}")

    # Only call GPT if candidates exist
    if not candidates:
        return updated

    # conference object for GPT
    conference_small = {
        "start_date": conference.get("start_date", "unknown"),
        "end_date": conference.get("end_date", "unknown"),
        "location": conference.get("location", "unknown"),
        "submission_deadline": conference.get("submission_deadline", "unknown"),
        # "notes": conference.get("notes", ""),
    }

    if len(years) == 1:
        years_text = str(years[0])
    else:
        years_text = f"{years[0]} or {years[1]}"
    system_prompt = "You are a JSON editor. Always return valid JSON without additional explanations."
    prompt = f"""
    Conference: {conference['name']}
    Today's date: {datetime.today().strftime("%Y-%m-%d")}
    Potential years when the next conference will be held: {years_text}
    Current info:
    {json.dumps(conference_small, indent=2)}

    Web scraped date, location, and submission deadline text:
    {json.dumps(candidates, indent=2)}

    Task: 
    - If the text indicates a new future conference start and end date, location, or submission_deadline for this conference, update the JSON accordingly.
    - If a submission_deadline has passed, mark it as "Closed". 
    - If a submission deadline date is missing a year, find the year by assuming it occurs less than 1 year prior to the conference start_date.
    - If the conference has ended, set start_date, end_date, location, and submission_deadline to "unknown".
    - Potential year(s) when the next conference will be held are {years_text}. Ignore conference dates beyond these years. 
    - Format any dates as (4 digit year)-(2 digit month)-(2 digit day), like "2000-01-01". 
    - Extract the conference location in this format whenever possible: "City, State/Province, Country" or "City, Country".
    - Examples: "Chicago, Illinois, USA", "Paris, France", "Vancouver, British Columbia, Canada", "Seoul, Republic of Korea".
    - There can be exceptions when the city location is unavailable or irrelevant, such as "University of Washington" or "Virtual" 
    - For if there is both a virtual and in-person meeting, use the in-person meeting dates and location. 
    - Dates and location may be missing from the text, or are not related to the conference. Make sure to ignore these information. 
    - When information is not found or is uncertain, keep current values. 
    - Return only the updated JSON object (not explanations).
    """

    # Call GPT
    updated_conference_small = call_gpt(conference_small, system_prompt, prompt)

    # Merge back into full data
    updated_conference = {**conference, **updated_conference_small}
    return updated_conference


def format_date_range(start_date: str, end_date: str) -> str:
    """
    Format two ISO date strings (YYYY-MM-DD) into a human-readable range.

    Rules:
    - If both are "unknown", return "Date unknown".
    - If only one is known, return it in "Month D, YYYY" form.
    - If both are known:
      * Same month/year → "April 8–11, 2026"
      * Same year, different months → "April 8 to May 2, 2026"
      * Different years → "Dec 29, 2025 to Jan 3, 2026"
    - If a date string is invalid, return it as-is.
    """

    def parse_date(date_str):
        if date_str in ("unknown", "", None):
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            return None

    dt1, dt2 = parse_date(start_date), parse_date(end_date)

    # Case 1: both unknown
    if not dt1 and not dt2:
        return "Date unknown"

    # Case 2: only one known
    if dt1 and not dt2:
        return dt1.strftime("%B %d, %Y")
    if dt2 and not dt1:
        return dt2.strftime("%B %d, %Y")

    # Case 3: both known
    if dt1.year == dt2.year and dt1.month == dt2.month:
        return f"{dt1.strftime('%B')} {dt1.day}–{dt2.day}, {dt1.year}"
    elif dt1.year == dt2.year:
        return f"{dt1.strftime('%B %d')} to {dt2.strftime('%B %d')}, {dt1.year}"
    else:
        return f"{dt1.strftime('%B %d, %Y')} to {dt2.strftime('%B %d, %Y')}"


def replace_url_years(url, start_date):
    """Replace {YEAR} and {YR} in URLs using start_date year."""
    if start_date == "unknown":
        start_date = (datetime.today() + relativedelta(years=1)).strftime("%Y-%m-%d")  # default start date to next year
    try:
        year_full = datetime.strptime(start_date, "%Y-%m-%d").year
        year_short = str(year_full)[-2:]
        url = url.replace("{YEAR}", str(year_full))
        url = url.replace("{YR}", str(year_short))
        return url
    except Exception:
        return url


def convert_to_discord_markdown(conference_data):
    output_lines = []

    for category, conferences in conference_data.items():
        if category == 'Psychometrics / Measurement / Testing Conferences':
            emoji = ":bar_chart:"
        elif category == 'Education / Policy Conferences':
            emoji = ":mortar_board:"
        elif category == 'AI / Machine Learning Conferences':
            emoji = ":robot:"
        elif category == 'Psychology Conferences':
            emoji = ":brain:"
        else:
            emoji = ""

        output_lines.append(f"## {emoji} {category}")
        for conf in conferences:
            # Fix URL placeholders
            url = replace_url_years(conf['url'], conf['start_date'])

            # Title and URL
            line1 = f"[**{conf['name']}**](<{url}>)"
            output_lines.append(line1)

            # Date + location
            date_text = format_date_range(conf["start_date"], conf["end_date"])
            location = conf.get("location", "Location unknown")
            if location != "unknown":
                line2 = f"* {date_text} -- {location}"
            else:
                line2 = f"* {date_text}"
            output_lines.append(line2)

            # Submission deadline
            submission = conf.get("submission_deadline", "unknown")

            if submission not in ("unknown", "Closed"):
                try:
                    # assume ISO format like YYYY-MM-DD
                    dt = datetime.strptime(submission, "%Y-%m-%d")
                    submission_fmt = dt.strftime("%B %d, %Y")  # e.g., "November 12, 2025"
                except ValueError:
                    # if not a valid date string, leave as is
                    submission_fmt = submission
            else:
                submission_fmt = submission

            line3 = f"* Submission Deadline: {submission_fmt}"
            output_lines.append(line3)

        output_lines.append("")  # blank line between categories

    return "\n".join(output_lines)


# ---- Parse file into list of conferences ----
def parse_conferences(file_path):
    conferences = []
    current_conf = []
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("[**"):  # conference heading
                if current_conf:
                    conferences.append(current_conf)
                    current_conf = []
            current_conf.append(line.rstrip("\n"))
        if current_conf:
            conferences.append(current_conf)
    return conferences


# ---- Compare two conference blocks ----
def compare_conference_blocks(old_conf, new_conf):
    diff = list(difflib.unified_diff(old_conf, new_conf, lineterm=""))
    # keep only actual +/- lines, skip headers
    return [line for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]


# ---- Compare full files ----
def compare_files(old_file, new_file):
    old_confs = parse_conferences(old_file)
    new_confs = parse_conferences(new_file)

    changes = {}

    # Compare conference by conference (assumes same order)
    for old_conf, new_conf in zip(old_confs, new_confs):
        conf_name = new_conf[0]  # first line = heading
        diff = compare_conference_blocks(old_conf, new_conf)
        if diff:
            changes[conf_name] = diff

    return changes


# ---- Notify Discord ----
def notify_conference_updates():
    # Find all markdown files
    files = glob.glob("conference_discord/*.md")
    if len(files) < 2:
        print("Not enough files to compare.")
        return

    # Sort chronologically (YYYY_MM_DD.md naming guarantees order)
    files.sort()
    prev_file, latest_file = files[-2], files[-1]

    # Get changes
    changes = compare_files(prev_file, latest_file)

    if not changes:
        print("✅ No changes detected.")
        return

    # Build Discord message (plain text)
    message = f"📢 **Conference Updates Detected** ({datetime.today().strftime('%Y-%m-%d')})\n"
    for conf, lines in changes.items():
        message += f"\n**{conf}**\n"
        for l in lines:
            if l.startswith("+"):
                message += f"{l[1:].strip()}\n"
            elif l.startswith("-"):
                message += f"Removed: {l[1:].strip()}\n"

    # Send to Discord webhook
    try:
        resp = requests.post(DISCORD_WEBHOOK_CONFERENCE_UPDATES, json={"content": message})
        resp.raise_for_status()
        print("✅ Sent grouped conference updates to Discord.")
    except Exception as e:
        print("❌ Failed to send Discord update:", e)


def main():
    # ---- Find Input Data ----
    # Find all files starting with "conferences" and ending with ".json"
    files = glob.glob("conference_data/20*.json")
    if not files:
        raise FileNotFoundError("No conference JSON files found!")
    # Sort by filename (since your naming has YYYY-MM-DD it sorts chronologically)
    files.sort()
    # Take the last one as the most recent
    INPUT_FILE = files[-1]
    print("Using latest file:", INPUT_FILE)
    with open(INPUT_FILE, "r") as f:
        data = json.load(f)
    updated_data = {}
    for category, conferences in data.items():
        updated_data[category] = []
        for conference in conferences:
            print(f"🔎 Checking {conference['name']}...")
            # raise
            updated_conf = scrape_and_update(conference)
            updated_data[category].append(updated_conf)

    # ---- Compare with last saved ----
    if updated_data == data:
        print("✅ No changes detected. Skipping save.")
        return

    # ---- Save JSON ----
    OUTPUT_FILE = "conference_data/" + f"{datetime.today().strftime('%Y_%m_%d')}.json"
    with open(OUTPUT_FILE, "w") as f:
        json.dump(updated_data, f, indent=2)
    print(f"✅ Saved updated JSON to {OUTPUT_FILE}")

    # ---- Save Markdown ----
    markdown_text = convert_to_discord_markdown(updated_data)
    OUTPUT_FILE2 = "conference_discord/" + f"{datetime.today().strftime('%Y_%m_%d')}.md"
    with open(OUTPUT_FILE2, "w", encoding="utf-8") as f:
        f.write(markdown_text)
    print(f"✅ Saved updated Discord md to {OUTPUT_FILE2}")

    # ---- Send Changes to Discord Private Channel ----
    notify_conference_updates()

if __name__ == "__main__":
    main()

