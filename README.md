# morning-digest

A lightweight morning digest generator for busy professionals and PMs.

It pulls together:
- calendar events for the next 24 hours
- important unread Gmail items
- AI news with short TL;DRs
- product news with short TL;DRs
- Sweden + Uppsala news with short TL;DRs when material

The output is plain text, optimized for chat delivery.

## Who this is for

This is useful if you want one compact morning briefing before the day starts, especially if you:
- manage a busy calendar
- want fast signal from inbox + news
- prefer a digest in Telegram or another messaging app
- do not want to manually scan five different places every morning

## What it does

The script currently:
- reads Google Calendar data via `gog`
- reads Gmail via `gog`
- uses Brave Search API for web/news summaries when available
- falls back to RSS/news sources where needed
- formats everything into a single structured digest

## Example sections

- `CALENDAR (next 24h; checked 2 calendars)`
- `GMAIL (top 5 important unread)`
- `AI NEWS (3 items)`
- `PRODUCT NEWS (2 items)`
- `SWEDEN + UPPSALA (only if material)`

## Requirements

- Python 3.11+
- [`gog`](https://github.com/shadmanrahman/gog) or equivalent Google Workspace CLI configured locally
- Brave Search API key available in OpenClaw config at:
  - `~/.openclaw/openclaw.json`

## Config assumptions

This script currently assumes:
- personal calendar id: `connectshadman@gmail.com`
- work calendar id: `k5amq2b5457n0v0mspai32pqn2umqp7s@import.calendar.google.com`
- timezone: `Europe/Stockholm`

You should edit those constants near the top of the script for your own setup.

## Usage

```bash
python3 morning_digest.py
```

## Output style

The digest is designed for messaging apps and includes:
- event bullets
- concise Gmail bullets
- news headlines
- short TL;DR lines under each news item

## Notes

This is intentionally simple and hackable.

It is not a general-purpose packaged product yet. It is a practical script you can fork and adapt for your own workflow.

## License

MIT
