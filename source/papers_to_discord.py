#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from itertools import groupby
import requests
import feedparser
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
load_dotenv()  # loads .env in the same directory

# ========== CONFIG ==========

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_PAPERS")

# Journals: either RSS (if available) or fallback scrape URL.
# You must fill or verify the fallback scrape URLs.
JOURNAL_SOURCES = {
    # "Computers and Education: Artificial Intelligence (CAEAI)": {
    #     "rss": "https://rss.sciencedirect.com/publication/science/2666920X",
    #     "scrape": "https://www.sciencedirect.com/journal/computers-and-education-artificial-intelligence/vol/9/suppl/C"  # Example “current issue” page
    # },
    "International Journal of Testing (IJT)": {
        "rss": "https://www.tandfonline.com/feed/rss/hijt20",
        "scrape": "https://www.tandfonline.com/action/showAxaArticles?journalCode=hijt20"
    },
    "Chinese/English Journal of Educational Measurement and Evaluation (CEJEME)": {
        "rss": "https://www.ce-jeme.org/journal/recent.rss",
        "scrape": "https://www.ce-jeme.org/"  # Example “current issue” page
    },
    # "Journal of Educational Computing Research (JECR)": {
    #     "rss": "https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=jec&type=axatoc&feed=rss",
    #     "scrape": "https://journals.sagepub.com/connected/jec"  # Example “current issue” page
    # },
    "Educational Measurement: Issues and Practice (EM:IP)": {
        "rss": "https://onlinelibrary.wiley.com/feed/17453992/most-recent",
        "scrape": "https://onlinelibrary.wiley.com/journal/17453992"  # Example “current issue” page
    },
    "Educational and Psychological Measurement (EPM)": {
        "rss": "https://journals.sagepub.com/action/showFeed?type=etoc&feed=rss&jc=epm",
        "scrape": "https://journals.sagepub.com/toc/epma/current"  # Example “current issue” page
    },
    "Psychometrika": {
        "rss": "https://www.cambridge.org/core/rss/product/id/103E7D27F001B3B09BE8FD6800A549BA",
        "scrape": "https://link.springer.com/journal/11336/online-first"  # “Online first / latest articles” page
    },
    "Applied Psychological Measurement (APM)": {
        "rss": "https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=apm&type=axatoc&feed=rss",
        "scrape": "https://journals.sagepub.com/toc/apm/current"
    },
    "Journal of Educational Measurement (JEM)": {
        "rss": "https://onlinelibrary.wiley.com/feed/17453984/most-recent",
        "scrape": "https://onlinelibrary.wiley.com/journal/17453984"  # Wiley’s journal page (latest articles listed)
    },
    "Journal of Educational and Behavioral Statistics (JEBS)": {
        "rss": "https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=jeb&type=axatoc&feed=rss",
        "scrape": "https://journals.sagepub.com/toc/jeba/current"
    },
    # "Multivariate Behavioral Research (MBR)": {
    #     "rss": "https://www.tandfonline.com/feed/rss/hmbr20",
    #     "scrape": "https://www.tandfonline.com/toc/pmbr20/current"
    # },
    # "Structural Equation Modeling (SEM)": {
    #     "rss": "https://www.tandfonline.com/feed/rss/hsem20",
    #     "scrape": "https://www.tandfonline.com/toc/hsem20/current"
    # },
    # "Assessment": {
    #     "rss": "https://journals.sagepub.com/action/showFeed?type=etoc&feed=rss&jc=asma",
    #     "scrape": "https://journals.sagepub.com/toc/asma/current"
    # },
    # "Journal of Personality Assessment (JPA)": {
    #     "rss": "https://www.tandfonline.com/feed/rss/hjpa20",
    #     "scrape": "https://www.tandfonline.com/toc/hjpa20/current"
    # },
    "Applied Measurement in Education (AME)": {
        "rss": "https://www.tandfonline.com/feed/rss/hame20",
        "scrape": "https://www.tandfonline.com/toc/hame20/current"
    },
    "Educational Assessment": {
        "rss": "https://www.tandfonline.com/feed/rss/heda20",
        "scrape": "https://www.tandfonline.com/toc/heda20/current"
    },
    "Large-scale Assessments in Education": {
        "rss": "https://largescaleassessmentsineducation.springeropen.com/articles/most-recent/rss.xml",
        "scrape": "https://largescaleassessmentsineducation.springeropen.com/"
    },
    # "Educational Assessment, Evaluation and Accountability": {
    #     "rss": None,
    #     "scrape": "https://link.springer.com/journal/11092/online-first"
    # },
    # "International Journal of Artificial Intelligence in Education (IJAIED)": {
    #     "rss": None,
    #     "scrape": "https://link.springer.com/journal/40593/online-first"
    # },
    # "Journal of Learning Analytics (JLA)": {
    #     "rss": None,
    #     "scrape": "https://learning-analytics.info/index.php/JLA/issue/current"
    # },
    # "Journal of Educational Data Mining (JEDM)": {
    #     "rss": None,
    #     "scrape": "https://jedm.educationaldatamining.org/index.php/JEDM/issue/current"
    # },
    # "Computers & Education": {
    #     "rss": "https://rss.sciencedirect.com/publication/science/03601315",
    #     "scrape": "https://www.sciencedirect.com/journal/computers-and-education"  # Latest articles listed here
    # },
    # "British Journal of Educational Technology (BJET)": {
    #     "rss": 'https://bera-journals.onlinelibrary.wiley.com/feed/14678535/most-recent',
    #     "scrape": "https://bera-journals.onlinelibrary.wiley.com/journal/14678535"  # Wiley’s journal homepage
    # },
    # "IEEE Transactions on Learning Technologies (TLT)": {
    #     "rss": "https://ieeexplore.ieee.org/rss/TOC69.XML",
    #     "scrape": "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=69"  # adjust for TLT’s ISSN/identifier
    # },
    # "Frontiers in Education (Assessment, Testing & Measurement section)": {
    #     "rss": "https://www.frontiersin.org/journals/education/sections/assessment-testing-and-applied-measurement/rss",
    #     "scrape": "https://www.frontiersin.org/journals/education/sections/assessment-testing-and-applied-measurement/latest"
    # }
}

REQUIRED_KEYWORDS = ["item response", "assessment", "psychometric", "measurement", "standardized test"]
ALLOWED_ARXIV_PREFIXES = ("math.", "stat.", "cs.")

# Preprint (only via APIs / fetchers, as before)
PREPRINT_SOURCES = {
    "arXiv": {
        "type": "arxiv",
        "keywords": [
            "item response", "IRT", "differential item functioning",
            "measurement invariance", "test equating", "psychometric",
            "latent trait", "rasch model", "graded response model",
            "1PL", "2PL", "3PL", "4PL", "parameter logistic model",
            "educational assessment","psychological assessment",
            "multidimensional IRT", "test linking", "test calibration",
            "educational measurement", "assessment validity", "fairness in testing",
            "item generation", "classical test theory",
            "item parameter", "item difficulty", "item discrimination"
        ],
        "max_results": 150
    },
    # We omit PsyArXiv / ArXiv / SocArXiv RSS since none reliably found; you can add fallback scrapers similarly.
}

SEEN_PATH = "seen_articles.json"
MAX_AGE_DAYS = 7
DISCORD_MAX_CONTENT = 2000

# ========== UTILITIES ==========

def load_seen() -> Dict[str, float]:
    try:
        with open(SEEN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_seen(seen: Dict[str, float]) -> None:
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)

def now_utc():
    return datetime.utcnow()

def is_recent(dt_obj):
    if not dt_obj:
        return True
    return (now_utc() - dt_obj) <= timedelta(days=MAX_AGE_DAYS)

def entry_authors(entry):
    if hasattr(entry, "authors"):
        names = [a.get("name", "") if isinstance(a, dict) else getattr(a, "name", "") for a in entry.authors]
        return ", ".join(n for n in names if n)
    return entry.get("author", "")

def entry_id(entry):
    if getattr(entry, "id", None):
        return entry.id
    return entry.get("link", "") + "|" + entry.get("title", "")

def parse_entry_time(entry):
    t = None
    for key in ("published_parsed", "updated_parsed"):
        tp = entry.get(key) or getattr(entry, key, None)
        if tp:
            try:
                return datetime(*tp[:6])
            except:
                pass
    return None

# ========== FETCHERS ==========

def fetch_rss(rss_url: str):
    return feedparser.parse(rss_url)

def extract_authors(text: str) -> str:
    """
    Extract authors from a string containing 'Author(s): ...'.
    Removes everything before 'Author(s):'.
    """
    match = re.search(r"Author\(s\):\s*(.*)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def translate_if_chinese(text):
    if re.search(r'[\u4e00-\u9fff]', text):
        translated = GoogleTranslator(source='zh-CN', target='en').translate(text)
        return f"{text} ({translated})"
    return text


def fetch_journal_rss(name: str, url: str):
    items = []
    # Use requests first, to handle redirects & headers
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    feed = feedparser.parse(resp.text)
    for e in feed.entries:
        # break
        title = e.get("title", "").strip()
        title = translate_if_chinese(title)
        # skip unwanted titles
        if any(skip in title for skip in ["Editorial Board"]):
            continue
        link = e.get("link", "")
        rid = e.get("id", link + "|" + title)
        t = parse_entry_time(e)

        # Default authors
        authors = entry_authors(e)

        # Special handling for ScienceDirect / Elsevier feeds
        desc = e.get("description", "")
        if "Author(s):" in desc:
            soup = BeautifulSoup(desc, "html.parser")
            text = soup.get_text(" ", strip=True)
            authors = extract_authors(text)
            # # Find "Author(s): ..." part
            # for part in text.split("\n"):
            #     if "Author(s):" in part:
            #         authors = part.replace(".*Author(s):", "").strip()
            #         break

        items.append({
            "source": name,
            "title": title,
            "authors": authors,
            "link": link,
            "id": rid,
            "time": t.isoformat() if t else ""
        })
    return items


def scrape_journal_latest(name: str, toc_url: str):
    items = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                          "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        resp = requests.get(toc_url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as ex:
        print(f"[WARN] Scrape failed for {name}, url {toc_url}: {ex}")
        return items

    soup = BeautifulSoup(resp.text, "html.parser")

    for a in soup.select("h3 a, h4 a, .article-title a, .title a"):
        title = a.get_text(strip=True)
        title = translate_if_chinese(title)
        link = a.get("href")
        if link and not link.startswith("http"):
            link = requests.compat.urljoin(resp.url, link)

        authors = ""

        # 🌟 Springer journals (IJAIED, etc.)
        if "springer.com" in resp.url:
            authors_div = a.find_parent("h3").find_next("div", class_="app-card-open__authors")
            if authors_div:
                authors_list = [li.get_text(strip=True) for li in authors_div.find_all("li", class_="app-author-list__item")]
                authors = ", ".join(authors_list)

        # 🌟 OJS (JEDM and similar)
        if not authors and "educationaldatamining.org" in resp.url:
            meta_div = a.find_parent("div", class_="media-body")
            if meta_div:
                authors_div = meta_div.find("div", class_="authors")
                if authors_div:
                    # Clean out the glyphicon icon
                    authors = authors_div.get_text(" ", strip=True).replace("glyphicon-user", "").strip()

        # 🌟 Generic fallback
        if not authors:
            parent = a.parent
            auth_tag = parent.find_next_sibling(
                lambda t: t.name in ("p", "div", "span") and "author" in (t.get("class") or [])
            )
            if auth_tag:
                authors = auth_tag.get_text(strip=True)

        eid = link or title
        items.append({
            "source": name,
            "title": title,
            "authors": authors,
            "link": link,
            "id": eid,
            "time": ""
        })

    return items



def build_arxiv_query_url(keywords: List[str], max_results: int = 150) -> str:
    clauses = [f'all:"{kw}"' for kw in keywords]
    query = " OR ".join(clauses)
    from urllib.parse import quote_plus
    return (
        "https://export.arxiv.org/api/query?"
        f"search_query={quote_plus(query)}&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )

def fetch_arxiv_items(cfg: Dict[str, Any]):
    url = build_arxiv_query_url(cfg["keywords"], cfg.get("max_results", 150))
    feed = fetch_rss(url)
    items = []
    for e in feed.entries:
        # Categories
        categories = [t["term"] for t in getattr(e, "tags", []) if "term" in t]

        # 🔥 Filter: must have at least one allowed prefix
        if not any(cat.startswith(ALLOWED_ARXIV_PREFIXES) for cat in categories):
            continue
        t = parse_entry_time(e)
        if t and not is_recent(t):
            continue
        title = e.get("title", "").strip()
        title = translate_if_chinese(title)
        # summary = e.get("summary", "")
        authors = entry_authors(e)
        link = e.get("link", "")
        rid = entry_id(e)
        items.append({
            "source": "arXiv (Preprint)",
            "title": title,
            "authors": authors,
            "link": link,
            "id": rid,
            "time": t.isoformat() if t else ""
        })
    # print(items)
    return items


def fetch_preprint_sources():
    all_items = []
    for name, cfg in PREPRINT_SOURCES.items():
        if cfg["type"] == "arxiv":
            items = fetch_arxiv_items(cfg)
        elif cfg["type"] == "rss" and cfg.get("url"):
            feed = fetch_rss(cfg["url"])
            items = []
            for e in feed.entries:
                t = parse_entry_time(e)
                if t and not is_recent(t):
                    continue
                title = e.get("title", "").strip()
                title = translate_if_chinese(title)
                authors = entry_authors(e)
                link = e.get("link", "")
                rid = entry_id(e)
                items.append({
                    "source": name + " (Preprint)",
                    "title": title,
                    "authors": authors,
                    "link": link,
                    "id": rid,
                    "time": t.isoformat() if t else ""
                })
        else:
            items = []

        # 🔥 Filter by required keywords
        for it in items:
            text = (it["title"] + " " + it.get("summary", "")).lower()
            if any(kw in text for kw in REQUIRED_KEYWORDS):
                all_items.append(it)

    return all_items


# ========== DISCORD POSTING ==========
def clean_whitespace(s: str) -> str:
    """Collapse all whitespace (spaces, tabs, newlines) into single spaces."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def clean_authors(text: str) -> str:
    # Remove "Author(s):" prefix if present
    text = re.sub(r".*Author\(s\):", "", text)

    # Cut off affiliations (anything starting with a digit followed by a capital or keyword like Dept/Univ)
    text = re.split(r"(\d[A-Z]|Department|University|Laboratory|Institute|College|School)", text)[0]

    # Collapse whitespace and commas
    text = re.sub(r"\s+", " ", text).strip()
    return text

def format_item_line(item: Dict[str, str]) -> str:
    title = clean_whitespace(item["title"])
    link = clean_whitespace(item["link"])
    authors = clean_authors(item["authors"])
    if authors == '':
        return f"[{title}](<{link}>)"
    else:
        return f"[{title}](<{link}>)\n* {authors}"

def chunk_messages(lines: List[str]) -> List[str]:
    chunks = []
    current = ""
    for ln in lines:
        if len(current) + 2 + len(ln) <= DISCORD_MAX_CONTENT:
            current += "\n" + ln
        else:
            chunks.append(current)
            current = ln
    if current.strip():
        chunks.append(current)
    return chunks

def discord_post(content: str):
    if not DISCORD_WEBHOOK_URL:
        print("[WARN] No webhook set. Would post:\n", content[:500])
        return
    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json={"content": content}, timeout=20)
        if resp.status_code >= 300:
            print(f"[ERR] Discord POST failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"[ERR] Discord POST exception: {e}")

def format_grouped_items(items):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"**:loudspeaker: <@&1421877669494128771> — {today}**"]
    # sort by source so groupby works
    items_sorted = sorted(items, key=lambda x: x["source"])
    for source, group in groupby(items_sorted, key=lambda x: x["source"]):
        lines.append(f"\n:green_book: **{source}**")  # journal name as header
        for it in group:
            lines.append(format_item_line(it))
    return lines

# ========== MAIN ==========

def main():
    seen = load_seen()
    # 1) Journals
    journal_items = []
    for name, info in sorted(JOURNAL_SOURCES.items()):
        # Try RSS first
        rss = info.get("rss")
        try:
            if rss:
                rss_items = fetch_journal_rss(name, rss)
                journal_items.extend(rss_items)
            else:
                raise ValueError("no rss")
        except Exception as e:
            # RSS fetch failed, fallback to scrape
            scrape_url = info.get("scrape")
            if scrape_url:
                scraped = scrape_journal_latest(name, scrape_url)
                journal_items.extend(scraped)
            else:
                print(f"[WARN] No RSS or scrape URL for {name}")
    # 2) Preprints
    pre_items = fetch_preprint_sources()

    # for it in items:
    #     print(it)

    # 3) Filter out seen and too old
    def filter_new(items):
        out = []
        for it in items:
            if it["id"] in seen:
                continue
            # parse time if available
            try:
                if it["time"]:
                    dt_obj = datetime.fromisoformat(it["time"])
                    if not is_recent(dt_obj):
                        continue
            except:
                pass
            out.append(it)
        return out

    journal_items = filter_new(journal_items)
    pre_items = filter_new(pre_items)

    # Sort by time desc
    def sort_key(it):
        try:
            return datetime.fromisoformat(it["time"])
        except:
            return datetime.min
    journal_items.sort(key=sort_key, reverse=True)
    pre_items.sort(key=sort_key, reverse=True)

    # 4) Format and post
    all_items = journal_items + pre_items
    today = datetime.now().strftime("%Y-%m-%d")
    if not all_items:
        print(f"**:loudspeaker: No New Research Found — {today}**\n")
    else:
        # discord_post(f"**:loudspeaker: New Research — {today}**\n")
        lines = format_grouped_items(all_items)
        for chunk in chunk_messages(lines):
            discord_post(chunk)
            time.sleep(0.5)

    # 5) Mark seen
    ts = time.time()
    for it in all_items:
        seen[it["id"]] = ts
    # Prune
    if len(seen) > 10000:
        # keep newest 10000
        sorted_by_ts = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)
        seen = dict(sorted_by_ts[:10000])
    save_seen(seen)

if __name__ == "__main__":
    main()
