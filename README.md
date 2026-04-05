# morning-digest

You know that feeling when it's 8:47am and you've already opened six different apps and you still don't know what your day actually looks like?

You checked calendar. Then Gmail. Then Slack. Then a news tab. Then another. You're already behind before you've done a single thing.

**morning-digest fixes this.** One command, one clean briefing. Everything you need to know before 9am — your schedule, your inbox signal, the news that matters — delivered in a single readable output, no subscriptions, no dashboards, no noise.

---

New to Claude Code? Start here: [claudecodeguide.dev](https://claudecodeguide.dev)

---

## What you get

Run the script each morning and you get something like this:

```text
Shadman's Morning Digest — Wed Apr 5, 07:30 (Stockholm)

CALENDAR (next 24h · 2 calendars checked)
Personal
  • 08:30–09:00  Dentist appointment
Work
  • 09:30–10:00  Sprint planning
  • 11:00–11:30  1:1 with Elena
  • 14:00–15:00  Product review — Q2 roadmap
  • 16:00–16:30  Stakeholder sync

GMAIL (top 5 important unread)
  • Elena Park: Feedback on the roadmap doc — she's flagged 3 questions
  • Stripe: New login detected from Berlin — worth checking if it wasn't you
  • Notion: Your shared doc has 4 new comments
  • Legal: NDA for the partnership — please sign by EOD

AI NEWS (3 items)
  • OpenAI launches enterprise workflow tools
    https://techcrunch.com/...
    TL;DR: New admin controls let IT teams manage AI access across departments.
    Deployments and usage limits can now be set org-wide.

  • Anthropic publishes safety update on model alignment
    https://anthropic.com/...
    TL;DR: Research team shares findings from interpretability experiments.
    Covers how models handle conflicting instructions at inference time.

PRODUCT NEWS (2 items)
  • Notion rolls out AI meeting notes for all plans
    https://notion.so/...
    TL;DR: Summary, action items, and follow-ups are now auto-generated
    from meeting recordings. Available in free tier starting this week.

SWEDEN + UPPSALA (only if material)
  • Major rail disruption affecting Uppsala–Stockholm commute
    https://svt.se/...
    TL;DR: Track maintenance causes 40-minute delays on X2000 services.
    Expected to clear by midday.
```

That's it. One output. Read it in 90 seconds. Start your actual work.

---

## Prerequisites

Three things need to be in place before you run the digest. Each one is explained below.

### 1. Python 3.11 or later

This is a Python script, so you need Python installed.

Check if you have it:
```bash
python3 --version
```

If you see `Python 3.11.x` or higher, you're good. If not, install it from [python.org](https://python.org/downloads) or via Homebrew on Mac:

```bash
brew install python@3.11
```

### 2. `gog` — your Google connection

`gog` is a small CLI tool that connects to your Google account and lets the script pull your calendar events and Gmail messages. Think of it as the authenticated bridge between your Google Workspace and this script.

Set it up here: [github.com/shadmanrahman/gog](https://github.com/shadmanrahman/gog)

Once installed and authenticated, confirm it's working:

```bash
gog calendar list --json
gog gmail labels --json
```

If both commands return data, you're connected and the digest will be able to read your calendar and inbox.

### 3. Brave Search API key

The news sections (AI news, product news, local news) are powered by Brave Search. You'll need a free API key.

Get one at [brave.com/search/api](https://brave.com/search/api) — the free tier covers personal use easily.

Once you have the key, the setup wizard (next section) will tell you exactly where to put it.

---

## Your first morning

Five steps. The setup wizard handles the hard parts.

**Step 1 — Clone the repo**

```bash
git clone https://github.com/mshadmanrahman/morning-digest.git
cd morning-digest
```

**Step 2 — Run the setup wizard**

```bash
python3 morning_digest.py --setup
```

The wizard walks you through everything interactively. It will ask for:

- Your name (used in the digest header)
- Your timezone (e.g. `Europe/Stockholm`, `America/New_York`)
- Your calendar labels and IDs (you can add up to two calendars — personal and work is the typical setup)
- Your local news topic and keywords (e.g. `Uppsala OR Sweden` with keywords `["sweden", "stockholm", "uppsala"]`)

Your answers are saved to `~/.morning-digest/config.json`. You only do this once.

**Step 3 — Check your config**

The setup creates a config file at:

```bash
~/.morning-digest/config.json
```

It looks like this — feel free to edit it anytime:

```json
{
  "name": "Shadman",
  "timezone": "Europe/Stockholm",
  "calendars": [
    { "label": "Personal", "id": "your-personal-calendar@gmail.com" },
    { "label": "Work", "id": "your-work-calendar-id@group.calendar.google.com" }
  ],
  "gmail_queries": [
    "in:inbox is:unread is:important",
    "in:inbox is:unread category:primary",
    "in:inbox is:unread"
  ],
  "news": {
    "ai_query": "AI news OR artificial intelligence latest developments",
    "product_query": "product launch OR product update OR release notes SaaS software",
    "local_query": "Sweden OR Uppsala important local news",
    "local_label": "SWEDEN + UPPSALA (only if material)",
    "local_keywords": ["uppsala", "sweden", "swedish", "stockholm"]
  }
}
```

Your calendar ID is the email-style address shown in Google Calendar settings under each calendar's integration options.

**Step 4 — Generate your digest**

```bash
python3 morning_digest.py
```

That's it. The digest prints to your terminal. Read it, then close the tab.

**Step 5 — Make it automatic (optional)**

Run it at 7am every weekday with a cron job:

```bash
crontab -e
```

Add this line (adjust the path to wherever you cloned the repo):

```
0 7 * * 1-5 python3 /path/to/morning-digest/morning_digest.py >> ~/morning-digest.log 2>&1
```

Or pipe the output to a file and open it in your notes app of choice. The output is plain text — easy to integrate anywhere.

---

## What this is (and isn't)

This is a practical, hackable script. It is intentionally simple.

It is not a SaaS product. There is no login, no cloud sync, no dashboard, no pricing page. You run it, you read it, you go do your work.

It is the kind of tool you own completely. Fork it, tweak the queries, swap in different news sources, add a Slack digest, remove the local news — the code is short and easy to read. Make it yours.

---

## Part of the PM Toolkit Family

Open-source tools for PMs and builders who work with AI every day.

| Tool | What it does |
|------|-------------|
| [pm-pilot](https://github.com/mshadmanrahman/pm-pilot) | Claude Code configured for PMs. Meeting prep, PRDs, market sizing — 25 skills, ready to install. |
| [bug-shepherd](https://github.com/mshadmanrahman/bug-shepherd) | Zero-code bug triage for PMs. Reproduce and sync bugs without reading a line of code. |
| [tech-to-pm-translator](https://github.com/mshadmanrahman/tech-to-pm-translator) | Turns developer docs into PM language. Structured knowledge bases, not summaries. |
| [claudecode-guide](https://github.com/mshadmanrahman/claudecode-guide) | The friendly guide to Claude Code. Zero jargon — from first install to daily operating system. |
| **morning-digest** | **You are here** |

---

## License

MIT
