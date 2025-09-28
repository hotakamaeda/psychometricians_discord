#!/usr/bin/env python3
"""
Psychometrics / Educational Assessment News Summarizer
Focus: policy, politics, media, professional/career-related items.
Reads all config from .env (no command-line args).
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import feedparser
from dateutil import parser as dtparser
import requests
import urllib.parse
# from bs4 import BeautifulSoup  # already useful for cleaning
from dotenv import load_dotenv
import re
import string

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()  # loads .env in the same directory

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
# OPENAI_MODEL = "gpt-5-nano"
OPENAI_MODEL = "gpt-5-mini"

if not OPENAI_API_KEY:
    print("ERROR: Please set OPENAI_API_KEY in your .env", file=sys.stderr)
    sys.exit(1)

# -----------------------------
# Config
# -----------------------------
SEARCH_TERMS = [
    '"educational assessment" policy OR reform',
    '"standardized testing" legislation OR politics',
    '"psychometrician licensure" OR "board exam"',
    '"psychometric career" OR "psychometricians job market"',
    '"testing agency" OR "assessment company"',
    '"NCME conference" OR "IMPS conference" psychometrics',
    '"NAEP results" OR "PISA results"',
    'Department of education',
    'Assessment company',
    '"acquisition" OR "merge" assessment company',
    'No Child Left Behind',
    "psychometrics news",
]

GOOGLE_NEWS_RSS_TMPL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
MAX_ARTICLES_PER_WINDOW = 2000
MAX_PER_QUERY = 999
HTTP_TIMEOUT = 15

# -----------------------------
# Helpers
# -----------------------------

# def resolve_final_url(url: str) -> str: # doesnt work right now.
#     """
#     Follow redirects and return the final destination URL.
#     Useful for Google News RSS or other aggregator links.
#     """
#     try:
#         resp = requests.head(url, allow_redirects=True, timeout=10)
#         return resp.url
#     except Exception as e:
#         print(f"[warn] Could not resolve {url}: {e}")
#         return url  # fallback to original

# def clean_summary(summary: str) -> str:
#     if not summary:
#         return ""
#     # Strip HTML
#     text = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
#     return text

def fetch_rss_for_query(query: str):
    """
    Fetch RSS items from Google News for a given query.
    Resolves each link to its final destination.
    """
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(url)

    items = []
    for entry in feed.entries[:MAX_PER_QUERY]:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "")
        # link = resolve_final_url(getattr(entry, "link", ""))
        # Summary is actually the same as title. redundant.
        # summary_raw = getattr(entry, "summary", "")
        # summary = clean_summary(summary_raw)

        # Try published date
        published = None
        for attr in ("published", "updated"):
            if hasattr(entry, attr):
                try:
                    dt = dtparser.parse(getattr(entry, attr))
                    published = dt.date().isoformat()  # YYYY-MM-DD only
                    break
                except Exception:
                    pass


        published = None
        if hasattr(entry, "published"):
            try:
                published = dtparser.parse(entry.published).isoformat()
            except Exception:
                pass
        elif hasattr(entry, "updated"):
            try:
                published = dtparser.parse(entry.updated).isoformat()
            except Exception:
                pass

        items.append({
            "title": title,
            "link": link,
            # "summary": summary,
            "published": published,
            "query": query,   # 👈 add back so payload has context
        })
    return items


def harvest_articles(terms: List[str]) -> List[Dict[str, Any]]:
    all_items = []
    for q in terms:
        try:
            items = fetch_rss_for_query(q)
            all_items.extend(items)
            time.sleep(0.4)
        except Exception as e:
            print(f"[warn] RSS fetch failed for: {q} :: {e}", file=sys.stderr)

    # Deduplicate by link or title
    seen = set()
    deduped = []
    for it in all_items:
        key = it.get("link") or it.get("title")
        if key and key not in seen:
            seen.add(key)
            deduped.append(it)

    # Sort by published date (newest first)
    def sort_key(it):
        pub = it.get("published")
        if not pub:
            return datetime.min  # put undated at the end
        try:
            return dtparser.parse(pub)
        except Exception:
            return datetime.min

    deduped.sort(key=sort_key, reverse=True)
    return deduped


def filter_by_window(
    items: List[Dict[str, Any]],
    days: int,
    exclude_days: int = 0
) -> List[Dict[str, Any]]:
    """
    Keep articles from the past `days` (inclusive),
    but exclude anything in the most recent `exclude_days`.
    Example: days=30, exclude_days=7 → covers 8–30 days ago.
    Handles 'YYYY-MM-DD' or full ISO timestamps.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    exclude_after = now - timedelta(days=exclude_days) if exclude_days else None

    kept: List[tuple[datetime, Dict[str, Any]]] = []

    for it in items:
        pub = it.get("published")
        if not pub:
            continue
        try:
            dt = dtparser.parse(pub)
        except Exception:
            continue

        # If parsed datetime has no tz (e.g., just a date), assume UTC midnight
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # In-range check
        if dt < since:
            continue
        if exclude_after and dt >= exclude_after:
            continue

        kept.append((dt, it))

    # Sort newest → oldest using the parsed datetime (not the raw string)
    kept.sort(key=lambda x: x[0], reverse=True)

    # Apply window cap
    return [it for _, it in kept[:MAX_ARTICLES_PER_WINDOW]]

def make_prompt_payload(window_name: str, items: List[Dict[str, Any]], include_link: bool) -> Dict[str, Any]:
    if include_link:
        articles = [
            {"title": it["title"], "link": it["link"], "published": it["published"], "query": it["query"]}
            # {"title": it["title"], "published": it["published"], "query": it["query"]}
            for it in items
        ]
    else:
        articles = [
            {"title": it["title"], "published": it["published"], "query": it["query"]}
            for it in items
        ]
    return {"window": window_name, "count": len(articles), "articles": articles}


def summarize_with_openai(model: str, windows_payload: Dict[str, Any]) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    system = (
        "You are a senior editor focusing on psychometrics and educational assessment news. "
        "Prioritize: policy, legislation, politics, testing reforms, professional society updates, licensure/career news, "
        "and media coverage. De-emphasize technical validation studies unless directly relevant. "
        "Summarize the important news and trends in a paragraph for each time window. "
        "Many articles will be recent articles, so pay attention to the published dates and make sure your summary covers the entire timeframe."
        "\n\n"
        "Output format rules:\n"
        "- Use plain text with clear section headings:\n"
        "  ## :newspaper2: Past 7 Days\n"
        "  ## :newspaper2: Past 2 Months\n"
        "  ## :newspaper2: Past 1 Year\n"
        "- Under each heading:\n"
        "  One summary paragraph.\n"
        "  Under every heading, list of 5 important sources in this format. Keep the source title unchanged.\n"
        " * Source Title\n"
        " * Source Title\n"
        " * Source Title\n"
        " * Source Title\n"
        " * Source Title\n"
    )
    # "    * [Source Title](https://link)\n"
    # "    * [Source Title](https://link)\n"
    # "    * [Source Title](https://link)\n"
    # "  At the very end, add a short TrendLines section comparing the three windows in bullet points. Header should be:"
    # "  ## :chart_with_upwards_trend: **Trendlines**\n"

    user_input = {
        "task": "Summarize psychometrics/assessment-related news.",
        "windows": windows_payload,
    }

    # Try up to 3 times on flex, then fallback to default
    for attempt in range(3):
        try:
            print(f"[i] Attempt {attempt+1} with flex tier...")
            resp = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user_input, ensure_ascii=False)},
                ],
                # temperature=0.25, # gpt-5-nano doesnt have temperature
                service_tier="flex",
            )
            break  # success
        except Exception as e:
            print(f"[warn] flex attempt {attempt+1} failed: {e}")
            time.sleep(30)  # wait before retry
    else:
        # All flex attempts failed → fallback to default
        print("[i] Falling back to default tier...")
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_input, ensure_ascii=False)},
            ],
            # temperature=0.25, # gpt-5-nano doesnt have temperature
            service_tier="default",
        )

    # Extract text output
    parts = []
    for o in resp.output:
        for c in getattr(o, "content", []):
            if c.type == "output_text":
                parts.append(c.text)
    return "\n".join(parts).strip()

def post_to_discord(webhook_url: str, content: str):
    MAX_LEN = 2000

    # Split into safe chunks
    chunks = []
    while len(content) > MAX_LEN:
        # Try to break at last newline before limit
        split_at = content.rfind("\n", 0, MAX_LEN)
        if split_at == -1:
            split_at = MAX_LEN
        chunks.append(content[:split_at])
        content = content[split_at:].lstrip()
    chunks.append(content)  # last piece

    # Send each chunk
    for i, chunk in enumerate(chunks, 1):
        msg = chunk
        # print(msg)
        # if len(chunks) > 1:
        #     msg = f"**Part {i}/{len(chunks)}**\n{msg}"

        try:
            r = requests.post(
                webhook_url,
                headers={"Content-Type": "application/json"},
                json={"content": msg},
                timeout=HTTP_TIMEOUT
            )
            r.raise_for_status()
            print(f"[ok] posted chunk {i}/{len(chunks)}")
        except Exception as e:
            print(f"[warn] Failed to post chunk {i}: {e}", file=sys.stderr)
            print(f"[debug] Chunk content (first 200 chars):\n{msg[:200]}...\n")
            break

        # Delay between messages to avoid rate limiting
        if i < len(chunks):
            time.sleep(1)

    print(f"[ok] finished posting {len(chunks)} message(s) to Discord")


def wrap_links_with_angle_brackets(text: str) -> str:
    """
    Ensure every Markdown-style [title](link) has <> around the link.
    Example: [Example](https://example.com) → [Example](<https://example.com>)
    """
    pattern = r'(\[.*?\]\()([^)]+)(\))'
    return re.sub(pattern, lambda m: f"{m.group(1)}<{m.group(2)}>{m.group(3)}", text)


def ensure_blank_before_headers(text: str) -> str:
    return re.sub(r'(?<!\n)\n?(## )', r'\n\n\1', text)


def normalize_title(title: str) -> str:
    # Lowercase + strip punctuation and whitespace
    return re.sub(rf"[{re.escape(string.punctuation)}\s]+", "", title.lower())

def attach_real_links(text: str, all_items: list[dict]) -> str:
    # Build lookup table from normalized title → link
    title_to_link = {
        normalize_title(it["title"]): it["link"]
        for it in all_items if it.get("title") and it.get("link")
    }

    lines = []
    for raw_line in text.splitlines():
        candidate = raw_line.strip()
        if not candidate:
            lines.append(raw_line)
            continue

        # Extract [Title](link) if GPT already formatted it
        linked = re.match(r'^\*?\s*\[(.+?)\]\((.*?)\)$', candidate)
        if linked:
            visible_title = linked.group(1).strip()
        else:
            visible_title = candidate.lstrip("-*• ").strip()

        norm = normalize_title(visible_title)
        link = title_to_link.get(norm)

        if link:
            # Ensure Discord-friendly link wrapping
            lines.append(f"* [{visible_title}](<{link}>)")
        else:
            # Keep line untouched if no match
            lines.append(raw_line)

    return "\n".join(lines)


# -----------------------------
# Main
# -----------------------------
def main():
    # # Monday-only guard
    # if datetime.today().weekday() != 0:  # Monday=0
    #     print("[i] Not Monday → skipping digest.")
    #     return

    print("[i] harvesting news…")
    all_items = harvest_articles(SEARCH_TERMS)
    print(f"[i] harvested {len(all_items)} articles total:")
    # if all_items:
    #     print(all_items[0])

    # # Write full harvested list to JSON file
    # with open("harvest_debug.json", "w", encoding="utf-8") as f:
    #     json.dump(all_items, f, ensure_ascii=False, indent=2)
    # print("[i] wrote harvest_debug.json")

    last_7 = filter_by_window(all_items, 7)
    last_60 = filter_by_window(all_items, 60, exclude_days=7)
    last_365 = filter_by_window(all_items, 365, exclude_days=60)

    windows_payload = {
        "last_7_days": make_prompt_payload("last_7_days", last_7, False),
        "last_60_days_excluding_past_7_days": make_prompt_payload("last_60_days_excluding_past_7_days", last_60, False),
        "last_365_days_excluding_past_60_days": make_prompt_payload("last_365_days_excluding_past_60_days", last_365, False),
    }

    # # Debug by dumping json.
    # with open("harvest_debug7.json", "w", encoding="utf-8") as f:
    #     json.dump(last_7, f, ensure_ascii=False, indent=2)
    # print(f"{len(last_7)} articles written to harvest_debug7.json")
    # with open("harvest_debug60.json", "w", encoding="utf-8") as f:
    #     json.dump(last_60, f, ensure_ascii=False, indent=2)
    # print(f"{len(last_60)} articles written to harvest_debug60.json")
    # with open("harvest_debug365.json", "w", encoding="utf-8") as f:
    #     json.dump(last_365, f, ensure_ascii=False, indent=2)
    # print(f"{len(last_365)} articles written to harvest_debug365.json")
    # with open("harvest_debugwindows_payload.json", "w", encoding="utf-8") as f:
    #     json.dump(windows_payload, f, ensure_ascii=False, indent=2)
    # print(f"written to harvest_debugwindows_payload.json")
    # # Stop execution here
    # raise SystemExit("[i] Stopping early for manual inspection")
    # # raise

    print("[i] summarizing with OpenAI…")
    report = summarize_with_openai(OPENAI_MODEL, windows_payload)

    # Clean spacing
    report = re.sub(r"\n\s*\n", "\n", report)
    report = ensure_blank_before_headers(report)
    report = attach_real_links(report, all_items)

    # # Fix link formatting
    # report = wrap_links_with_angle_brackets(report)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"# Monday News Digest\nGenerated: {now}\nModel: {OPENAI_MODEL}\nSummarized: {len(all_items)} Articles"
    report_txt = header + report

    if DISCORD_WEBHOOK_URL:
        try:
            post_to_discord(DISCORD_WEBHOOK_URL, report_txt)
        except Exception as e:
            print(f"[warn] Discord post failed: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()






# def clean_link(link: str, max_len: int = 500) -> str:
#     """
#     Clean Google News RSS redirect links into real article URLs.
#     Truncate overly long links to avoid Discord errors.
#     """
#     if not link:
#         return link
#
#     # Handle Google News redirect links
#     if "news.google.com/rss/articles" in link:
#         # Try to extract final URL from "url=" param if present
#         if "url=" in link:
#             parsed = urllib.parse.urlparse(link)
#             qs = urllib.parse.parse_qs(parsed.query)
#             if "url" in qs:
#                 link = qs["url"][0]
#
#     # Truncate absurdly long links
#     if len(link) > max_len:
#         link = link[:max_len - 3] + "..."
#
#     return link
#
#
# def fetch_rss_for_query(query: str) -> List[Dict[str, Any]]:
#     url = GOOGLE_NEWS_RSS_TMPL.format(query=requests.utils.quote(query))
#     feed = feedparser.parse(url)
#     items = []
#     for e in feed.entries[:MAX_PER_QUERY]:
#         raw_link = getattr(e, "link", "")
#         link = clean_link(raw_link)
#         title = getattr(e, "title", "").strip()
#         summary = getattr(e, "summary", "")
#         published = None
#         if hasattr(e, "published"):
#             try:
#                 published = dtparser.parse(e.published)
#             except Exception:
#                 published = None
#         elif hasattr(e, "updated"):
#             try:
#                 published = dtparser.parse(e.updated)
#             except Exception:
#                 published = None
#
#         items.append({
#             "title": title,
#             "link": link,
#             "summary": summary,
#             "published": published.isoformat() if published else None,
#             "query": query,
#         })
#     return items


    # resp = client.responses.create(
    #     model=model,
    #     input=[
    #         {"role": "system", "content": system},
    #         {"role": "user", "content": json.dumps(user_input, ensure_ascii=False)},
    #     ],
    #    # temperature=0.3,
    # )
    #
    # parts = []
    # for o in resp.output:
    #     for c in getattr(o, "content", []):
    #         if c.type == "output_text":
    #             parts.append(c.text)
    # return "\n".join(parts).strip()