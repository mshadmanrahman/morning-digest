#!/usr/bin/env python3
import json
import gzip
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

APP_DIR = Path.home() / ".morning-digest"
CONFIG_PATH = APP_DIR / "config.json"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_CONFIG = {
    "name": "Your Name",
    "timezone": "Europe/Stockholm",
    "calendars": [
        {"label": "Personal", "id": "your-personal-calendar-id@example.com"},
        {"label": "Work", "id": "your-work-calendar-id@example.com"},
    ],
    "gmail_queries": [
        "in:inbox is:unread is:important",
        "in:inbox is:unread category:primary",
        "in:inbox is:unread",
    ],
    "news": {
        "ai_query": "AI news OR artificial intelligence latest developments",
        "product_query": "product launch OR product update OR release notes SaaS software",
        "local_query": "Sweden OR Uppsala important local news",
        "local_label": "SWEDEN + UPPSALA (only if material)",
        "local_keywords": ["uppsala", "sweden", "swedish", "stockholm"],
    },
}


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip() or f"command failed: {' '.join(cmd)}")
    return p.stdout


def clean_title(title):
    return title.replace("&#39;", "'").replace("&amp;", "&")


def clean_summary(text, max_len=180):
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "…"


def prompt(label, default=""):
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def ensure_config_dir():
    APP_DIR.mkdir(parents=True, exist_ok=True)


def write_config(config):
    ensure_config_dir()
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


def setup_wizard():
    print("Morning Digest setup")
    print("This will create a local config at ~/.morning-digest/config.json\n")

    config = json.loads(json.dumps(DEFAULT_CONFIG))
    config["name"] = prompt("Your name", config["name"])
    config["timezone"] = prompt("Timezone", config["timezone"])

    print("\nCalendar setup")
    config["calendars"][0]["label"] = prompt("Calendar 1 label", "Personal")
    config["calendars"][0]["id"] = prompt("Calendar 1 id")
    config["calendars"][1]["label"] = prompt("Calendar 2 label", "Work")
    config["calendars"][1]["id"] = prompt("Calendar 2 id")

    print("\nLocal news setup")
    config["news"]["local_label"] = prompt("Local news section label", config["news"]["local_label"])
    local_query = prompt("Local news search query", config["news"]["local_query"])
    config["news"]["local_query"] = local_query
    keywords = prompt("Local relevance keywords (comma-separated)", ", ".join(config["news"]["local_keywords"]))
    config["news"]["local_keywords"] = [k.strip().lower() for k in keywords.split(",") if k.strip()]

    write_config(config)
    print(f"\nSaved config to {CONFIG_PATH}")
    print("Run `python3 morning_digest.py` to generate your digest.")


def load_config():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config not found: {CONFIG_PATH}. Run `python3 morning_digest.py --setup` first."
        )
    return json.loads(CONFIG_PATH.read_text())


def brave_api_key():
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text())
        return cfg["tools"]["web"]["search"]["apiKey"]
    except Exception:
        return None


def now_local(tz):
    return datetime.now(tz)


def end_of_tomorrow(n):
    t = n + timedelta(days=1)
    return t.replace(hour=23, minute=59, second=59, microsecond=0)


def fetch_calendar(cal_id, start_iso, end_iso):
    base = [
        "gog", "calendar", "events", cal_id,
        "--from", start_iso,
        "--to", end_iso,
        "--json", "--max", "50", "--no-input",
    ]
    for args in (
        base,
        base,
        [
            "gog", "calendar", "events", cal_id,
            "--from", start_iso,
            "--to", (datetime.fromisoformat(start_iso) + timedelta(hours=48)).isoformat(),
            "--json", "--max", "50", "--no-input",
        ],
    ):
        try:
            data = json.loads(run(args))
            events = data.get("events") or []
            if events:
                return events
        except Exception:
            pass
    return []


def parse_dt(obj, tz):
    if not obj:
        return None
    if "dateTime" in obj:
        return datetime.fromisoformat(obj["dateTime"]).astimezone(tz)
    if "date" in obj:
        return datetime.fromisoformat(obj["date"] + "T00:00:00").replace(tzinfo=tz)
    return None


def format_events(events, tz):
    rows = []
    for e in events:
        start = parse_dt(e.get("start"), tz)
        end = parse_dt(e.get("end"), tz)
        if not start or not end:
            continue
        title = (e.get("summary") or "Untitled").strip()
        note = None
        loc = (e.get("location") or "").strip()
        if loc and loc not in ("Microsoft Teams Meeting",):
            note = loc
        line = f"• {start:%H:%M}–{end:%H:%M} {title}"
        if note:
            line += f" (note: {note})"
        rows.append((start, line))
    rows.sort(key=lambda x: x[0])
    return [line for _, line in rows]


def fetch_gmail(queries):
    seen = set()
    out = []
    for q in queries:
        try:
            data = json.loads(run(["gog", "gmail", "messages", "search", q, "--json", "--max", "10", "--no-input"]))
        except Exception:
            continue
        for m in data.get("messages") or []:
            msg_id = m.get("id") or m.get("messageId")
            if not msg_id or msg_id in seen:
                continue
            seen.add(msg_id)
            headers = {h.get("name", "").lower(): h.get("value", "") for h in (m.get("headers") or [])}
            sender = headers.get("from") or m.get("from") or "Unknown sender"
            subject = headers.get("subject") or m.get("subject") or "(no subject)"
            snippet = (m.get("snippet") or "").replace("\n", " ").strip()
            why = snippet[:120].strip() if snippet else "Unread inbox message"
            out.append(f"• {sender}: {subject} — {why}")
            if len(out) >= 5:
                return out
    return out[:5]


def fetch_rss(query, limit):
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    items = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        if title.endswith(" - Google News"):
            title = title[:-14]
        items.append((title, link))
        if len(items) >= limit:
            break
    return items


def fetch_brave_news(query, count):
    key = brave_api_key()
    if not key:
        return []
    params = urllib.parse.urlencode({
        "q": query,
        "count": count,
        "freshness": "pd",
        "search_lang": "en",
    })
    req = urllib.request.Request(
        BRAVE_API + "?" + params,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": key,
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode())
    except Exception:
        return []
    out = []
    for item in ((data.get("web") or {}).get("results") or []):
        title = clean_title(item.get("title") or "")
        url = item.get("url") or ""
        desc = clean_summary(item.get("description") or item.get("extra_snippets", [""])[0])
        if title and url:
            out.append((title, url, desc))
        if len(out) >= count:
            break
    return out


def fallback_summary_from_title(title):
    title = clean_title(title)
    if " - " in title:
        topic, source = title.rsplit(" - ", 1)
        return f"Update from {source} about {topic.lower()}."
    return f"Update related to {title.lower()}."


def section_bullets(items):
    lines = []
    for item in items:
        if len(item) >= 3 and item[2]:
            t, u, s = item[0], item[1], item[2]
            lines.append(f"• {clean_title(t)}: {u}")
            lines.append(f"  TL;DR: {clean_summary(s)}")
        else:
            t, u = item[:2]
            lines.append(f"• {clean_title(t)}: {u}")
            lines.append(f"  TL;DR: {fallback_summary_from_title(t)}")
    return lines


def build_digest(config):
    tz = ZoneInfo(config["timezone"])
    n = now_local(tz)
    start_iso = n.isoformat()
    end_iso = end_of_tomorrow(n).isoformat()

    calendar_sections = []
    for cal in config["calendars"]:
        events = format_events(fetch_calendar(cal["id"], start_iso, end_iso), tz)
        calendar_sections.append((cal["label"], events or ["No events found"]))

    gmail = fetch_gmail(config.get("gmail_queries") or DEFAULT_CONFIG["gmail_queries"])
    news_cfg = config.get("news") or {}

    ai_news = fetch_brave_news(news_cfg.get("ai_query", DEFAULT_CONFIG["news"]["ai_query"]), 3)
    if len(ai_news) < 3:
        ai_news.extend([x for x in fetch_rss('artificial intelligence OR AI when:2d', 3) if x[1] not in {u for _, u, *_ in ai_news}][: 3 - len(ai_news)])

    product_news = fetch_brave_news(news_cfg.get("product_query", DEFAULT_CONFIG["news"]["product_query"]), 2)
    if len(product_news) < 2:
        extra = fetch_rss('(product launch OR product update OR release notes OR SaaS) when:7d', 5)
        seen = {u for _, u, *_ in product_news}
        for item in extra:
            if item[1] not in seen:
                product_news.append(item)
                seen.add(item[1])
            if len(product_news) >= 2:
                break

    local_query = news_cfg.get("local_query", DEFAULT_CONFIG["news"]["local_query"])
    local_label = news_cfg.get("local_label", DEFAULT_CONFIG["news"]["local_label"])
    local_keywords = [k.lower() for k in (news_cfg.get("local_keywords") or DEFAULT_CONFIG["news"]["local_keywords"])]
    local_news = fetch_brave_news(local_query, 3)
    if len(local_news) < 1:
        local_news = fetch_rss(local_query, 3)

    lines = []
    lines.append(f"{config['name']}'s Morning Digest {n:%a %b} {n.day}, {n:%H:%M} ({config['timezone'].split('/')[-1]})")
    lines.append("")
    lines.append(f"CALENDAR (next 24h; checked {len(calendar_sections)} calendars)")
    for label, events in calendar_sections:
        lines.append(label)
        lines.extend(events)
    lines.append("")
    lines.append("GMAIL (top 5 important unread)")
    lines.extend(gmail or ["• No unread inbox messages returned"])
    lines.append("")
    lines.append("AI NEWS (3 items)")
    lines.extend(section_bullets(ai_news[:3]))
    lines.append("")
    lines.append("PRODUCT NEWS (2 items)")
    lines.extend(section_bullets(product_news[:2]))

    material_local = []
    for item in local_news:
        t = item[0].lower()
        if any(x in t for x in local_keywords):
            material_local.append(item)
    if material_local:
        lines.append("")
        lines.append(local_label)
        lines.extend(section_bullets(material_local[:3]))

    return "\n".join(lines).strip()[:4000]


def main():
    if "--setup" in sys.argv:
        setup_wizard()
        return
    config = load_config()
    print(build_digest(config))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Morning Digest error: {e}", file=sys.stdout)
        sys.exit(1)
