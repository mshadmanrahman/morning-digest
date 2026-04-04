#!/usr/bin/env python3
"""Morning Digest v2.1 — Calendar, Gmail, News, Telegram delivery.

Replaces OpenClaw-powered digest. Uses gws CLI for Google APIs,
Brave Search for news, Telegram Bot API for delivery. Zero pip dependencies.
"""
import html as _html
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

# --- Config ---
APP_DIR = Path.home() / ".morning-digest"
CONFIG_PATH = APP_DIR / "config.json"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
BRAVE_NEWS_API = "https://api.search.brave.com/res/v1/news/search"
GWS = str(Path.home() / ".npm-global/bin/gws")
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
HAIKU_COST_INPUT = 0.80 / 1_000_000   # $ per input token
HAIKU_COST_OUTPUT = 4.00 / 1_000_000  # $ per output token

DEFAULT_CONFIG = {
    "name": "Shadman",
    "timezone": "Europe/Stockholm",
    "calendars": [
        {"label": "Personal", "id": "connectshadman@gmail.com"},
        {"label": "Work", "id": "k5amq2b5457n0v0mspai32pqn2umqp7s@import.calendar.google.com"},
    ],
    "gmail_queries": [
        "is:unread is:important newer_than:1d",
        "is:unread category:primary newer_than:1d",
        "is:unread newer_than:1d",
    ],
    "telegram": {
        "chat_id": "160135380",
    },
    "news": {
        "ai_query": "artificial intelligence AI launch release breakthrough",
        "product_query": "SaaS product launch developer tools startup",
        "local_query": "Uppsala OR Sweden migration policy OR crime OR new rules regulations",
        "local_label": "SWEDEN / UPPSALA",
        "local_keywords": ["uppsala", "sweden", "swedish", "stockholm", "migration", "migrationsverket", "crime", "police", "regulation", "work permit"],
    },
}


# --- Utilities ---

def run(cmd, timeout=30):
    """Run a command and return stdout."""
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[:200] or f"failed: {' '.join(cmd)}")
    return p.stdout


def run_json(cmd, timeout=30):
    """Run a command and parse JSON from stdout, skipping non-JSON preamble lines."""
    raw = run(cmd, timeout)
    lines = raw.strip().split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return json.loads("\n".join(lines[i:]))
    raise RuntimeError(f"No JSON found in output of: {' '.join(cmd)}")


def clean_text(text):
    """Unescape HTML entities, strip tags, and remove invisible Unicode filler."""
    text = _html.unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    # Remove invisible Unicode characters (zero-width spaces, word joiners, etc.)
    text = re.sub(r"[\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufe00-\ufe0f\ufeff\u034f\u00ad]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate(text, max_len=150):
    text = clean_text(text)
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "..."


def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return DEFAULT_CONFIG


def get_telegram_token():
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text())
        return cfg["channels"]["telegram"]["botToken"]
    except Exception:
        return None


def brave_api_key():
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text())
        # Try the plugin path first (where OpenClaw stores it), then legacy path
        key = (
            cfg.get("plugins", {}).get("entries", {}).get("brave", {})
            .get("config", {}).get("webSearch", {}).get("apiKey")
        )
        if key:
            return key
        return cfg["tools"]["web"]["search"]["apiKey"]
    except Exception:
        return None


# --- Claude ---

def get_anthropic_key():
    """Get Anthropic API key: env → openclaw config → digest config."""
    import os
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        cfg = json.loads(OPENCLAW_CONFIG.read_text())
        for path in [
            lambda c: c["anthropic"]["apiKey"],
            lambda c: c["plugins"]["entries"]["anthropic"]["config"]["apiKey"],
            lambda c: c["llm"]["anthropic"]["apiKey"],
        ]:
            try:
                k = path(cfg)
                if k:
                    return k
            except (KeyError, TypeError):
                continue
    except Exception:
        pass
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        return cfg.get("anthropic_api_key") or None
    except Exception:
        return None


def call_claude_haiku(prompt, max_tokens=400):
    """Call Claude Haiku via REST. Returns (text, input_tokens, output_tokens)."""
    key = get_anthropic_key()
    if not key:
        return None, 0, 0
    payload = json.dumps({
        "model": HAIKU_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        ANTHROPIC_API,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        text = data["content"][0]["text"]
        usage = data.get("usage", {})
        return text, usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    except Exception:
        return None, 0, 0


def enhance_news_with_claude(items, topic_hint):
    """Filter and improve news TLDRs with Haiku. Returns (enhanced_items, in_tok, out_tok)."""
    if not items:
        return items, 0, 0
    items_text = "\n".join(
        f"{i + 1}. TITLE: {title}\n   DESC: {desc or '(none)'}"
        for i, (title, _url, desc) in enumerate(items[:6])
    )
    prompt = (
        f"You are a news filter for a software product manager who cares about: "
        f"LLMs, AI coding tools (Claude Code, Cursor, Copilot), Anthropic, developer productivity, "
        f"SaaS product launches, startup funding, and product management.\n\n"
        f"Topic: {topic_hint}\n\n"
        f"From these {min(len(items), 6)} items, pick ONLY the ones that genuinely match the topic. "
        f"Return 0-3 items. If nothing qualifies, return []. "
        f"Write punchy one-sentence TLDRs (max 120 chars). "
        f"Drop generic fluff, sports, entertainment, healthcare AI, retail AI, or off-topic content.\n\n"
        f"Format: [{{\"index\": 1, \"tldr\": \"...\"}}, ...]\n"
        f"Return ONLY valid JSON, nothing else.\n\n"
        f"Items:\n{items_text}"
    )
    content, in_tok, out_tok = call_claude_haiku(prompt)
    if not content:
        return items[:3], 0, 0
    try:
        picks = json.loads(content)
        result = []
        for pick in picks[:3]:
            idx = pick["index"] - 1
            if 0 <= idx < len(items):
                title, url, _ = items[idx]
                result.append((title, url, pick["tldr"]))
        return result, in_tok, out_tok  # trust Haiku's filtering, even if empty
    except Exception:
        return items[:3], in_tok, out_tok


# --- Calendar ---

def fetch_calendar_gws(tz):
    try:
        data = run_json([GWS, "calendar", "+agenda", "--format", "json"], timeout=20)
        if isinstance(data, dict):
            return data.get("events", [])
        return data if isinstance(data, list) else []
    except Exception:
        return []


def format_events_gws(events, tz):
    now = datetime.now(tz)
    tomorrow_end = (now + timedelta(days=1)).replace(hour=23, minute=59)
    rows = []

    for e in events:
        summary = (e.get("summary") or "Untitled").strip()
        start_str = e.get("start", "")
        end_str = e.get("end", "")
        location = (e.get("location") or "").strip()

        try:
            if "T" in start_str:
                start = datetime.fromisoformat(start_str.replace("Z", "+00:00")).astimezone(tz)
                end = datetime.fromisoformat(end_str.replace("Z", "+00:00")).astimezone(tz) if end_str and "T" in end_str else start + timedelta(hours=1)
            else:
                start = datetime.fromisoformat(start_str + "T00:00:00").replace(tzinfo=tz) if start_str else None
                end = None
        except Exception:
            continue

        if start is None or start > tomorrow_end:
            continue
        if "Declined:" in summary:
            continue

        if end and "T" in start_str:
            line = f"  {start:%H:%M}-{end:%H:%M}  {summary}"
        else:
            line = f"  All day  {summary}"

        if location and location not in ("Microsoft Teams Meeting",):
            loc_short = location.split("(")[0].strip()[:30]
            if loc_short:
                line += f"  [{loc_short}]"

        rows.append((start, line))

    rows.sort(key=lambda x: x[0])
    return [line for _, line in rows]


# --- Gmail ---

def fetch_gmail_gws(queries):
    seen = set()
    results = []

    for q in queries:
        try:
            data = run_json([
                GWS, "gmail", "users", "messages", "list",
                "--params", json.dumps({"userId": "me", "maxResults": 8, "q": q})
            ], timeout=20)
            messages = data.get("messages", [])
        except Exception:
            continue

        for msg_ref in messages:
            msg_id = msg_ref.get("id")
            if not msg_id or msg_id in seen:
                continue
            seen.add(msg_id)

            try:
                detail = run_json([
                    GWS, "gmail", "users", "messages", "get",
                    "--params", json.dumps({"userId": "me", "id": msg_id, "format": "full"})
                ], timeout=15)
                headers = {}
                for h in detail.get("payload", {}).get("headers", []):
                    name = h.get("name", "").lower()
                    if name in ("from", "subject"):
                        headers[name] = h.get("value", "")

                sender = headers.get("from", "Unknown")
                subject = headers.get("subject", "(no subject)")
                snippet = clean_text((detail.get("snippet") or "")[:120])

                # Extract display name from "Name <email>" format
                if "<" in sender:
                    sender = sender.split("<")[0].strip().strip('"')
                # Further shorten noreply-style senders
                if "@" in sender:
                    sender = sender.split("@")[0][:15]
                else:
                    sender = sender[:25]

                results.append(f"  {sender} | {subject}")
            except Exception:
                continue

            if len(results) >= 7:
                return results

    return results[:7]


# --- Inbox Summary ---

def fetch_inbox_digest():
    """Fetch newsletters and noteworthy emails from last 24h, extract key insights from snippets."""
    try:
        data = run_json([
            GWS, "gmail", "users", "messages", "list",
            "--params", json.dumps({"userId": "me", "maxResults": 50, "q": "newer_than:1d"})
        ], timeout=25)
        messages = data.get("messages", [])
    except Exception:
        return 0, [], [], []

    # Sender patterns for categorization
    NEWSLETTER_SENDERS = [
        "substack", "beehiiv", "newsletter", "digest", "morning brew", "tldr",
        "hackernews", "producthunt", "techcrunch", "theverge", "wired",
        "ycombinator", "hacker news", "ben's bites", "the hustle", "base44",
        "exa", "readwise", "every.to", "pragmatic", "lenny", "first round",
    ]
    WORK_SENDERS = ["keg.com", "keystoneacademic", "educations.com", "outlook", "microsoft", "keystone", "teams"]
    NOISE_SENDERS = [
        "linkedin", "wellfound", "indeed", "greenhouse", "lever.co",
        "careers", "jobnotification", "noreply", "no-reply", "notification",
        "promo", "marketing", "unsubscribe", "lager 157", "shop", "store",
        "order", "receipt", "shipping", "elgiganten", "cubus", "lagerhaus",
        "hm.com", "h&m", "ica ", "coop", "willys", "mediamarkt",
        "klarna", "postnord", "dhl", "bring", "mecenat", "airhelp",
        "booking.com", "tripadvisor", "hotels.com", "kundtjänst",
        "halebop", "telia", "tele2", "tre.se", "comviq",
        "survey", "tycker du", "feedback",
        "flightnetwork", "momondo", "skyscanner", "flygresor",
        "rabatt", "erbjudande", "kampanj",
    ]

    newsletters = []  # The good stuff: news, insights, industry updates
    work_items = []   # Work emails worth flagging
    stats = {"total": len(messages), "newsletters": 0, "work": 0, "noise": 0}

    seen = set()
    for msg_ref in messages[:30]:
        msg_id = msg_ref.get("id")
        if not msg_id or msg_id in seen:
            continue
        seen.add(msg_id)

        try:
            detail = run_json([
                GWS, "gmail", "users", "messages", "get",
                "--params", json.dumps({"userId": "me", "id": msg_id, "format": "full"})
            ], timeout=10)
        except Exception:
            continue

        headers = {}
        for h in detail.get("payload", {}).get("headers", []):
            name = h.get("name", "").lower()
            if name in ("from", "subject"):
                headers[name] = h.get("value", "")

        sender_raw = headers.get("from", "")
        sender_lower = sender_raw.lower()
        subject = clean_text(headers.get("subject", ""))
        snippet = clean_text(detail.get("snippet", ""))

        # Extract display name
        sender_name = sender_raw
        if "<" in sender_name:
            sender_name = sender_name.split("<")[0].strip().strip('"')
        sender_name = sender_name[:20]

        # Categorize
        snippet_lower = snippet.lower()

        if any(w in sender_lower for w in NOISE_SENDERS):
            stats["noise"] += 1
            continue

        # Skip own sent emails
        if "connectshadman" in sender_lower or "shadman.rahman" in sender_lower:
            continue

        # Teams meeting invites are work, regardless of sender
        if "teams.microsoft.com/meet" in snippet_lower or "teams.microsoft.com/l/meetup" in snippet_lower:
            stats["work"] += 1
            work_items.append({
                "source": sender_name,
                "subject": subject[:60],
                "snippet": "Teams meeting invite",
            })
            continue

        if any(w in sender_lower for w in NEWSLETTER_SENDERS):
            stats["newsletters"] += 1
            # Build a useful one-liner from subject + snippet
            insight = snippet[:150] if snippet else subject
            if insight and subject:
                newsletters.append({
                    "source": sender_name,
                    "subject": subject[:60],
                    "insight": insight,
                })
            continue

        if any(w in sender_lower for w in WORK_SENDERS):
            stats["work"] += 1
            work_items.append({
                "source": sender_name,
                "subject": subject[:60],
                "snippet": snippet[:100],
            })
            continue

        # Everything else: check if snippet has newsworthy content
        if snippet and len(snippet) > 50:
            newsletters.append({
                "source": sender_name,
                "subject": subject[:60],
                "insight": snippet[:150],
            })

    return stats, newsletters, work_items


def format_inbox_digest(stats, newsletters, work_items):
    """Format inbox digest as a curated briefing."""
    lines = []
    lines.append(f"  {stats['total']} emails | {stats['work']} work, {stats['newsletters']} subscriptions, {stats['noise']} noise")
    lines.append("")

    if work_items:
        lines.append("  WORK:")
        for item in work_items[:3]:
            snippet = f" — {item['snippet']}" if item.get("snippet") else ""
            lines.append(f"    {item['source']}: {item['subject']}{snippet}")
        lines.append("")

    if newsletters:
        lines.append("  SUBSCRIPTIONS:")
        for item in newsletters[:5]:
            # One-liner: source + subject only (keep it scannable)
            lines.append(f"    {item['source']}: {item['subject']}")
            # Short insight on next line, capped tight
            if item.get("insight") and item["insight"] != item["subject"]:
                short = item["insight"][:80].rsplit(" ", 1)[0]
                lines.append(f"      {short}")
            lines.append("")  # breathing room between items

    return lines


# --- News ---

def fetch_brave_news(query, count):
    """Fetch news from Brave News API (not web search)."""
    key = brave_api_key()
    if not key:
        return []

    # Try news API first, fall back to web search
    for api_url in [BRAVE_NEWS_API, BRAVE_API]:
        params = urllib.parse.urlencode({
            "q": query,
            "count": count * 3,
            "freshness": "pd",
            "search_lang": "en",
        })
        req = urllib.request.Request(
            api_url + "?" + params,
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
            continue

        # News API returns data.results, Web API returns data.web.results
        results = data.get("results") or (data.get("web") or {}).get("results") or []

        out = []
        for item in results:
            title = clean_text(item.get("title") or "")
            url = item.get("url") or ""
            raw_desc = item.get("description") or ""
            if not raw_desc:
                snippets = item.get("extra_snippets")
                raw_desc = snippets[0] if isinstance(snippets, list) and snippets else ""
            desc = truncate(raw_desc)

            # Skip non-article results
            if not title or not url:
                continue
            if any(skip in url for skip in ["google.com/rss", "news.google.com", "wikipedia.org"]):
                continue
            # Skip homepage/index URLs (no meaningful path after domain)
            path = url.split("//", 1)[-1].split("/", 1)
            if len(path) < 2 or not path[1].strip("/"):
                continue
            # Skip if title looks like a site name, not an article
            if len(title.split()) <= 3 and not desc:
                continue

            out.append((title, url, desc))
            if len(out) >= count:
                break

        if out:
            return out

    return []


def fetch_rss_articles(query, limit):
    """Fetch from Google News RSS, resolving redirect URLs."""
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
    except Exception:
        return []
    try:
        root = ET.fromstring(data)
    except Exception:
        return []

    items = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        # Extract source from " - Source" suffix
        source = ""
        if " - " in title:
            title, source = title.rsplit(" - ", 1)
            title = title.strip()
            source = source.strip()

        # Google News RSS links are redirects; show source instead of ugly URL
        display_url = f"(via {source})" if source else ""
        items.append((title, link, display_url))
        if len(items) >= limit:
            break
    return items


def fetch_rss_feed(feed_url, limit):
    """Fetch items directly from an RSS feed URL."""
    req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
    except Exception:
        return []
    try:
        root = ET.fromstring(data)
    except Exception:
        return []
    items = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        desc = clean_text(item.findtext("description") or "")[:150]
        if not title or not link:
            continue
        items.append((title, link, desc))
        if len(items) >= limit:
            break
    return items


def format_news_item(title, url, desc, index):
    """Format a single news item for Telegram with TLDR."""
    lines = []
    clean_url = url.split("?")[0] if "google.com" not in url else ""

    lines.append(f" {index}. {title}")
    # Always show TLDR if we have a description
    if desc and not desc.startswith("(via"):
        lines.append(f"    TLDR: {desc}")
    # Show source attribution for RSS items
    if desc and desc.startswith("(via"):
        lines.append(f"    {desc}")
    # Show URL
    if clean_url:
        lines.append(f"    {clean_url}")
    return lines


# --- Telegram ---

def _esc(text):
    """Escape HTML entities for Telegram HTML mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def plain_to_telegram_html(text):
    """Convert plain digest text to Telegram HTML for better readability."""
    lines = text.split("\n")
    out = []

    # Section headers to make bold
    HEADERS = {
        "WEATHER", "CALENDAR (next 24h)", "UNREAD INBOX",
        "INBOX DIGEST (last 24h)", "GITHUB", "AI NEWS",
        "PRODUCT NEWS", "SWEDEN + UPPSALA (only if material)",
        "SWEDEN / UPPSALA", "LOCAL NEWS",
    }

    for line in lines:
        stripped = line.strip()

        # Skip separator lines (=== and ---)
        if stripped and all(c in "=-" for c in stripped):
            continue

        # Bold the digest title
        if "Morning Digest" in line:
            out.append(f"<b>{_esc(stripped)}</b>")
            continue

        # Bold section headers
        if stripped in HEADERS or stripped.rstrip(":") in HEADERS:
            out.append(f"\n<b>{_esc(stripped)}</b>")
            continue

        # Make URLs clickable: lines that are just a URL with leading spaces
        url_match = re.match(r"^\s+(https?://\S+)$", line)
        if url_match:
            url = url_match.group(1)
            out.append(f"    <a href=\"{url}\">Read more</a>")
            continue

        # News items with (via Source) — keep as-is but escape
        out.append(_esc(line))

    return "\n".join(out)


def send_telegram(token, chat_id, text):
    """Send message via Telegram Bot API with HTML formatting. Split long messages."""
    html_text = plain_to_telegram_html(text)
    MAX_LEN = 4000
    chunks = []
    if len(html_text) <= MAX_LEN:
        chunks = [html_text]
    else:
        parts = html_text.split("\n\n")
        current = ""
        for part in parts:
            if len(current) + len(part) + 2 > MAX_LEN:
                if current:
                    chunks.append(current)
                current = part
            else:
                current = current + "\n\n" + part if current else part
        if current:
            chunks.append(current)

    for chunk in chunks:
        payload = json.dumps({
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                if not result.get("ok"):
                    print(f"Telegram error: {result}", file=sys.stderr)
        except Exception as e:
            print(f"Telegram send failed: {e}", file=sys.stderr)


# --- Weather ---

def fetch_weather(location, label=None):
    """Fetch weather from wttr.in (free, no API key)."""
    try:
        url = f"https://wttr.in/{urllib.parse.quote(location)}?format=%C+%t+%w+%p+%h&lang=en"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            conditions = resp.read().decode().strip()
        # Get the forecast line too
        url2 = f"https://wttr.in/{urllib.parse.quote(location)}?format=%C+%t+(%f+feels+like)&lang=en"
        req2 = urllib.request.Request(url2, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            feels = resp2.read().decode().strip()
        prefix = f"  {label}: " if label else "  "
        return f"{prefix}{feels}"
    except Exception:
        return None


# --- GitHub Activity ---

def fetch_github_activity():
    """Fetch PRs awaiting review and recent CI status via gh CLI."""
    GH = "gh"
    sections = []

    # PRs awaiting my review
    try:
        raw = subprocess.run(
            [GH, "search", "prs", "--review-requested=@me", "--state=open",
             "--json", "title,repository,number,url,updatedAt", "--limit", "5"],
            capture_output=True, text=True, timeout=15,
        )
        if raw.returncode == 0:
            prs = json.loads(raw.stdout)
            if prs:
                sections.append("  REVIEW REQUESTED:")
                for pr in prs[:5]:
                    repo = pr.get("repository", {}).get("name", "")
                    num = pr.get("number", "")
                    title = (pr.get("title") or "")[:55]
                    sections.append(f"  > {repo}#{num}: {title}")
    except Exception:
        pass

    # My open PRs and their CI status
    try:
        raw = subprocess.run(
            [GH, "search", "prs", "--author=@me", "--state=open",
             "--json", "title,repository,number,url,statusCheckRollup", "--limit", "5"],
            capture_output=True, text=True, timeout=15,
        )
        if raw.returncode == 0:
            prs = json.loads(raw.stdout)
            if prs:
                sections.append("  MY OPEN PRs:")
                for pr in prs[:5]:
                    repo = pr.get("repository", {}).get("name", "")
                    num = pr.get("number", "")
                    title = (pr.get("title") or "")[:45]
                    checks = pr.get("statusCheckRollup") or []
                    failed = sum(1 for c in checks if c.get("conclusion") == "FAILURE")
                    pending = sum(1 for c in checks if c.get("status") == "IN_PROGRESS")
                    ci = ""
                    if failed:
                        ci = f" [CI FAILED x{failed}]"
                    elif pending:
                        ci = " [CI running]"
                    elif checks:
                        ci = " [CI passed]"
                    sections.append(f"  > {repo}#{num}: {title}{ci}")
    except Exception:
        pass

    return sections


# --- Build Digest ---

def build_digest(config):
    tz = ZoneInfo(config["timezone"])
    n = datetime.now(tz)
    news_cfg = config.get("news", DEFAULT_CONFIG["news"])
    ai_stats = {"input_tokens": 0, "output_tokens": 0, "used": False}

    lines = []

    # Header
    lines.append(f"{'=' * 32}")
    lines.append(f"  {config['name']}'s Morning Digest")
    lines.append(f"  {n:%A, %b %d} | {n:%H:%M} CET")
    lines.append(f"{'=' * 32}")
    lines.append("")

    # --- Weather ---
    lines.append("WEATHER")
    lines.append("-" * 28)
    is_thursday = n.weekday() == 3  # Thursday = commute day
    weather_uppsala = fetch_weather("Uppsala,Sweden", "Uppsala")
    if weather_uppsala:
        lines.append(weather_uppsala)
    if is_thursday:
        weather_sthlm = fetch_weather("Stockholm,Sweden", "Stockholm")
        if weather_sthlm:
            lines.append(weather_sthlm)
        lines.append("  🚗 Commute day: Märsta → Odenplan → Garnisonen")
    if not weather_uppsala:
        lines.append("  Weather unavailable")
    lines.append("")

    # --- Calendar ---
    lines.append("CALENDAR (next 24h)")
    lines.append("-" * 28)
    events = fetch_calendar_gws(tz)
    formatted = format_events_gws(events, tz)
    if formatted:
        lines.extend(formatted)
    else:
        lines.append("  No events found")
    lines.append("")

    # --- Gmail: Unread ---
    lines.append("UNREAD INBOX")
    lines.append("-" * 28)
    gmail = fetch_gmail_gws(config.get("gmail_queries", DEFAULT_CONFIG["gmail_queries"]))
    if gmail:
        lines.extend(gmail)
    else:
        lines.append("  Inbox zero!")
    lines.append("")

    # --- Inbox Digest: Last 24h summary ---
    lines.append("INBOX DIGEST (last 24h)")
    lines.append("-" * 28)
    stats, newsletters, work_items = fetch_inbox_digest()
    digest_lines = format_inbox_digest(stats, newsletters, work_items)
    if digest_lines:
        lines.extend(digest_lines)
    else:
        lines.append("  No emails in the last 24 hours")
    lines.append("")

    # --- GitHub Activity ---
    lines.append("GITHUB")
    lines.append("-" * 28)
    gh_lines = fetch_github_activity()
    if gh_lines:
        lines.extend(gh_lines)
    else:
        lines.append("  No PRs needing attention")
    lines.append("")

    # --- AI News ---
    lines.append("AI NEWS")
    lines.append("-" * 28)
    ai_news = fetch_brave_news(news_cfg.get("ai_query", DEFAULT_CONFIG["news"]["ai_query"]), 6)
    if len(ai_news) < 3:
        extra = fetch_rss_articles("Anthropic OR Claude OR LLM OR \"AI agent\" OR Cursor release launch 2026", 5)
        seen = {u for _, u, *_ in ai_news}
        for item in extra:
            if item[1] not in seen:
                ai_news.append(item)
            if len(ai_news) >= 6:
                break
    ai_news, in_tok, out_tok = enhance_news_with_claude(ai_news, "AI/LLM/developer tools news")
    ai_stats["input_tokens"] += in_tok
    ai_stats["output_tokens"] += out_tok
    if in_tok:
        ai_stats["used"] = True
    for i, item in enumerate(ai_news[:3], 1):
        lines.extend(format_news_item(item[0], item[1], item[2] if len(item) > 2 else "", i))
    if not ai_news:
        lines.append("  No AI news today")
    lines.append("")

    # --- Product News ---
    lines.append("PRODUCT NEWS")
    lines.append("-" * 28)
    # Product Hunt RSS = reliable daily launches; HN = developer community picks
    ph_news = fetch_rss_feed("https://www.producthunt.com/feed", 8)
    hn_news = fetch_rss_feed("https://news.ycombinator.com/rss", 8)
    seen_pn: set = set()
    product_news = []
    for item in ph_news + hn_news:
        if item[1] not in seen_pn:
            product_news.append(item)
            seen_pn.add(item[1])
    product_news, in_tok, out_tok = enhance_news_with_claude(product_news, "developer tools / SaaS / startup launches / AI product announcements")
    ai_stats["input_tokens"] += in_tok
    ai_stats["output_tokens"] += out_tok
    if in_tok:
        ai_stats["used"] = True
    for i, item in enumerate(product_news[:3], 1):
        lines.extend(format_news_item(item[0], item[1], item[2] if len(item) > 2 else "", i))
    if not product_news:
        lines.append("  No product news today")
    lines.append("")

    # --- Local News ---
    lines.append(news_cfg.get("local_label", "LOCAL NEWS"))
    lines.append("-" * 28)
    local_keywords = [k.lower() for k in news_cfg.get("local_keywords", DEFAULT_CONFIG["news"]["local_keywords"])]

    # The Local Sweden = English-language Swedish news (reliable, no sports noise)
    thelocal_news = fetch_rss_feed("https://feeds.thelocal.se/rss/se", 8)
    svt_news = fetch_rss_feed("https://www.svt.se/nyheter/rss.xml", 6)
    seen_local: set = set()
    combined = []
    for item in thelocal_news + svt_news:
        if item[1] not in seen_local:
            combined.append(item)
            seen_local.add(item[1])

    # Haiku filters to only work-relevant Sweden news
    combined, in_tok, out_tok = enhance_news_with_claude(
        combined,
        "Swedish news relevant to someone living and working in Sweden: politics, economy, immigration, "
        "work permits, Migrationsverket, crime, regulations, cost of living. "
        "Drop sports, entertainment, culture, and anything not directly affecting daily life in Sweden."
    )
    ai_stats["input_tokens"] += in_tok
    ai_stats["output_tokens"] += out_tok
    if in_tok:
        ai_stats["used"] = True

    for i, item in enumerate(combined[:3], 1):
        lines.extend(format_news_item(item[0], item[1], item[2] if len(item) > 2 else "", i))
    if not combined:
        lines.append("  No relevant local news")

    lines.append("")

    # --- Stats footer ---
    if ai_stats["used"]:
        total_tok = ai_stats["input_tokens"] + ai_stats["output_tokens"]
        cost = (ai_stats["input_tokens"] * HAIKU_COST_INPUT
                + ai_stats["output_tokens"] * HAIKU_COST_OUTPUT)
        lines.append(f"{'=' * 32}")
        lines.append(f"  {HAIKU_MODEL}")
        lines.append(f"  {ai_stats['input_tokens']:,} in · {ai_stats['output_tokens']:,} out · {total_tok:,} total · ~${cost:.4f}")
    else:
        lines.append(f"{'=' * 32}")
        lines.append("  AI enhancement unavailable (no API key)")

    lines.append(f"{'=' * 32}")

    return "\n".join(lines)


def main():
    if "--setup" in sys.argv:
        print("Config at", CONFIG_PATH)
        print("Edit it manually or delete to reset.")
        return

    config = load_config()
    digest = build_digest(config)

    # Always print to stdout
    print(digest)

    # Send to Telegram if configured
    if "--telegram" in sys.argv or "--send" in sys.argv:
        token = get_telegram_token()
        chat_id = config.get("telegram", {}).get("chat_id") or DEFAULT_CONFIG["telegram"]["chat_id"]
        if token and chat_id:
            send_telegram(token, chat_id, digest)
            print("\nSent to Telegram.", file=sys.stderr)
        else:
            print("Telegram token or chat_id not configured.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Morning Digest error: {e}", file=sys.stdout)
        sys.exit(1)
