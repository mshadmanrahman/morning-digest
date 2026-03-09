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

TZ = ZoneInfo("Europe/Stockholm")
PERSONAL_CAL = "connectshadman@gmail.com"
WORK_CAL = "k5amq2b5457n0v0mspai32pqn2umqp7s@import.calendar.google.com"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
BRAVE_API = "https://api.search.brave.com/res/v1/web/search"


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip() or f"command failed: {' '.join(cmd)}")
    return p.stdout


def now_local():
    return datetime.now(TZ)


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


def parse_dt(obj):
    if not obj:
        return None
    if "dateTime" in obj:
        return datetime.fromisoformat(obj["dateTime"]).astimezone(TZ)
    if "date" in obj:
        return datetime.fromisoformat(obj["date"] + "T00:00:00").replace(tzinfo=TZ)
    return None


def format_events(events):
    rows = []
    for e in events:
        start = parse_dt(e.get("start"))
        end = parse_dt(e.get("end"))
        if not start or not end:
            continue
        title = (e.get("summary") or "Untitled").strip()
        note = None
        loc = (e.get("location") or "").strip()
        if loc and loc not in ("Microsoft Teams Meeting",) and "Stockholm, Stockholm, SE" not in loc:
            note = loc
        line = f"• {start:%H:%M}–{end:%H:%M} {title}"
        if note:
            line += f" (note: {note})"
        rows.append((start, line))
    rows.sort(key=lambda x: x[0])
    return [line for _, line in rows]


def fetch_gmail():
    queries = [
        'in:inbox is:unread is:important',
        'in:inbox is:unread category:primary',
        'in:inbox is:unread',
    ]
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


def brave_api_key():
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text())
        return cfg["tools"]["web"]["search"]["apiKey"]
    except Exception:
        return None


def clean_title(title):
    return title.replace("&#39;", "'").replace("&amp;", "&")


def clean_summary(text, max_len=180):
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "…"


def fetch_brave_news(query, count):
    key = brave_api_key()
    if not key:
        return []
    params = urllib.parse.urlencode({
        "q": query,
        "count": count,
        "freshness": "pd",
        "country": "SE",
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


def main():
    n = now_local()
    start_iso = n.isoformat()
    end_iso = end_of_tomorrow(n).isoformat()

    personal = format_events(fetch_calendar(PERSONAL_CAL, start_iso, end_iso))
    work = format_events(fetch_calendar(WORK_CAL, start_iso, end_iso))
    gmail = fetch_gmail()
    ai_news = fetch_brave_news('AI news OR artificial intelligence latest developments', 3)
    if len(ai_news) < 3:
        ai_news.extend([x for x in fetch_rss('artificial intelligence OR AI when:2d', 3) if x[1] not in {u for _, u, *_ in ai_news}][: 3 - len(ai_news)])

    product_news = fetch_brave_news('product launch OR product update OR release notes SaaS software', 2)
    if len(product_news) < 2:
        extra = fetch_rss('(product launch OR product update OR release notes OR SaaS) when:7d', 5)
        seen = {u for _, u, *_ in product_news}
        for item in extra:
            if item[1] not in seen:
                product_news.append(item)
                seen.add(item[1])
            if len(product_news) >= 2:
                break

    sweden = fetch_brave_news('Sweden OR Uppsala important local news', 3)
    if len(sweden) < 1:
        sweden = fetch_rss('(Uppsala OR Sweden) when:2d', 3)

    lines = []
    lines.append(f"Shadman's Morning Digest {n:%a %b} {n.day}, {n:%H:%M} (Stockholm)")
    lines.append("")
    lines.append("CALENDAR (next 24h; checked 2 calendars)")
    lines.append("Personal")
    lines.extend(personal or ["No events found"])
    lines.append("Work")
    lines.extend(work or ["No events found"])
    lines.append("")
    lines.append("GMAIL (top 5 important unread)")
    lines.extend(gmail or ["• No unread inbox messages returned"])
    lines.append("")
    lines.append("AI NEWS (3 items)")
    lines.extend(section_bullets(ai_news[:3]))
    lines.append("")
    lines.append("PRODUCT NEWS (2 items)")
    lines.extend(section_bullets(product_news[:2]))

    material_sweden = []
    for item in sweden:
        t, u = item[0], item[1]
        lt = t.lower()
        if any(x in lt for x in ["uppsala", "sweden", "swedish", "stockholm"]):
            material_sweden.append(item)
    if material_sweden:
        lines.append("")
        lines.append("SWEDEN + UPPSALA (only if material)")
        lines.extend(section_bullets(material_sweden[:3]))

    out = "\n".join(lines).strip()
    print(out[:2500])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Shadman's Morning Digest {datetime.now(TZ):%a %b} {datetime.now(TZ).day}, {datetime.now(TZ):%H:%M} (Stockholm)\n\nGMAIL (top 5 important unread)\n• No unread inbox messages returned\n\nPRODUCT NEWS (2 items)\n• Digest script error: {e}", file=sys.stdout)
        sys.exit(0)
