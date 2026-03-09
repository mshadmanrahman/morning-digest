# morning-digest

A lightweight morning digest generator for PMs and busy professionals.

It creates one compact text digest with:
- your next 24 hours of calendar events
- important unread Gmail messages
- AI news with short TL;DRs
- product news with short TL;DRs
- local news with short TL;DRs when material

## What makes it usable

You do **not** need to edit the script to get started.

On first run, it prompts you for:
- your name
- your timezone
- your calendar labels + calendar IDs
- your local-news query and keywords

It saves that setup to:
- `~/.morning-digest/config.json`

After that, the digest is ready to run daily.

## Quick start

### 1. Install requirements

You need:
- Python 3.11+
- `gog` configured for your Google account
- a Brave Search API key available in OpenClaw config at `~/.openclaw/openclaw.json`

### 2. Run the setup wizard

```bash
python3 morning_digest.py --setup
```

You’ll be prompted for your personal details and calendar setup.

### 3. Generate your digest

```bash
python3 morning_digest.py
```

## Example setup prompts

- Your name
- Timezone
- Calendar 1 label
- Calendar 1 id
- Calendar 2 label
- Calendar 2 id
- Local news section label
- Local news search query
- Local relevance keywords

## Config file

The script stores a local config here:

```bash
~/.morning-digest/config.json
```

Example:

```json
{
  "name": "Shadman",
  "timezone": "Europe/Stockholm",
  "calendars": [
    { "label": "Personal", "id": "your-personal-calendar-id@example.com" },
    { "label": "Work", "id": "your-work-calendar-id@example.com" }
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

## Output format

The digest includes these sections:
- `CALENDAR`
- `GMAIL`
- `AI NEWS`
- `PRODUCT NEWS`
- local news section of your choice

Each news item includes:
- headline
- URL
- short `TL;DR`

## Notes

This project is intentionally simple and easy to fork.

It is best for people who already have:
- Google Calendar
- Gmail
- a terminal workflow
- a messaging or automation layer they want to plug this into

## License

MIT
