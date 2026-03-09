# morning-digest

A lightweight morning digest generator for PMs and busy professionals.

It creates one compact text digest with:
- your next 24 hours of calendar events
- important unread Gmail messages
- AI news with short TL;DRs
- product news with short TL;DRs
- local news with short TL;DRs when material

## Why this exists

If your mornings start with too many tabs, too many inbox checks, and too much context switching, this script gives you one clean briefing instead.

It is built for people who want:
- a fast view of the day ahead
- inbox signal without scanning everything
- a lightweight intelligence brief
- something simple enough to self-host and tweak

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
- [`gog`](https://github.com/shadmanrahman/gog) configured for your Google account
- a Brave Search API key available in OpenClaw config at `~/.openclaw/openclaw.json`

### 2. Make sure `gog` works

Before using the digest, make sure your Google tooling is already authenticated.

For example:

```bash
gog calendar list --json
gog gmail labels --json
```

If those work, the digest will usually work too.

### 3. Run the setup wizard

```bash
python3 morning_digest.py --setup
```

You’ll be prompted for your personal details and calendar setup.

### 4. Generate your digest

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

## Sample output

```text
Shadman's Morning Digest Tue Mar 10, 07:30 (Stockholm)

CALENDAR (next 24h; checked 2 calendars)
Personal
• 08:30–09:00 Dentist appointment
Work
• 09:35–10:00 Team standup
• 13:00–14:00 Product review

GMAIL (top 5 important unread)
• Stripe: New login detected — worth checking in case it was not you

AI NEWS (3 items)
• OpenAI launches new enterprise workflow tools: https://example.com/story
  TL;DR: OpenAI introduced new workflow and admin controls aimed at larger teams managing internal AI usage.

PRODUCT NEWS (2 items)
• Notion rolls out new AI meeting notes: https://example.com/story
  TL;DR: The update focuses on summarization, action items, and faster follow-up after team meetings.

LOCAL NEWS (only if material)
• Major transit disruption in your city: https://example.com/story
  TL;DR: Morning commuters may face delays due to infrastructure maintenance and reduced service.
```

## Best use cases

This is especially useful if you are:
- a PM managing a busy cross-functional calendar
- a founder or operator juggling meetings, inbox, and market awareness
- a consultant or executive who wants one message instead of five dashboards
- anyone building a personal daily briefing workflow

## Notes

This project is intentionally simple and easy to fork.

It is not trying to be a giant SaaS product. It is a practical, hackable script you can adapt to your own workflow and automation stack.

## License

MIT
