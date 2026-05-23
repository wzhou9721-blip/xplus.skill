---
name: xplus.skill
description: Run and operate xplus.skill, a single-profile browser monitor for X/Twitter home feeds and private Lists. It writes captured events to local JSONL for Codex/agents and can optionally distribute alerts to Discord.
---

# xplus.skill

Use this skill when the user wants an agent to monitor X/Twitter through a real browser session.

The default operating model is intentionally simple:

- one runtime root
- one browser profile
- one X login session
- local JSONL as the primary output
- optional Discord distribution

Do not assume any external bot framework exists.

## What It Does

xplus.skill opens X in a Playwright-controlled Chrome/Chromium browser, watches the home feed and/or private Lists, and records newly observed posts.

Primary output:

```text
<runtime-root>/event_archive.jsonl
```

Supporting runtime files:

```text
<runtime-root>/config.json
<runtime-root>/state.json
<runtime-root>/check_archive.jsonl
<runtime-root>/seen_archive.json
<runtime-root>/chrome-profile/
```

`event_archive.jsonl` is the interface another agent should read.

Optional public search companion:

```text
scripts/x_monitorplus_hermes_tweet.py
```

This fetcher uses Hermes Tweet/Xquik read API search results and appends normalized events to the same archive. It does not replace the browser monitor for home feeds or private Lists.

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`
- `python -m playwright install chromium`
- one X/Twitter account for monitoring

Chrome is optional. `browser_channel` defaults to `auto`, which tries system Chrome first and falls back to Playwright's bundled Chromium.

## First-Time Setup

Work from the repository root.

Create a runtime root outside tracked source:

```bash
mkdir .runtime
copy config.example.json .runtime\config.json
```

On non-Windows shells, use `cp` instead of `copy`.

Edit `.runtime/config.json` before starting:

- set `x_home_enabled` or `x_list_enabled`
- set `x_list_url` if using a List
- keep `output_sinks` as `["jsonl"]` unless Discord is requested
- set `browser_channel` to `auto` unless the user asks otherwise

## Login

Open the monitor profile:

```bash
python scripts/x_monitorplus_service.py --root .runtime open-profile
```

This opens a visible Chrome/Chromium window. If Chrome is not installed, bundled Chromium is used.

Ask the user to log in to X in that browser window, confirm the target feed/List loads, then close the browser window. Do not start the watcher while this login window is still open.

## Start And Stop

Start:

```bash
python scripts/x_monitorplus_service.py --root .runtime start
```

Check status:

```bash
python scripts/x_monitorplus_service.py --root .runtime status
```

Stop:

```bash
python scripts/x_monitorplus_service.py --root .runtime stop
```

## Reading Results

Read captured events from:

```text
.runtime/event_archive.jsonl
```

Each line is a JSON object. Important fields usually include:

- `tweet_id`
- `handle`
- `url`
- `created_at`
- `original_text`
- `source_full_text`
- `target_name`
- `target_url`
- `at`
- `output_sinks`

Use `status` first if no events appear.

## Optional Hermes Tweet Search

Use the Hermes Tweet fetcher only when the user asks for public X search terms in the xplus.skill archive, or when browser feed/List monitoring is already running and the agent needs query-based enrichment.

In `.runtime/config.json`:

```json
{
  "hermes_tweet_enabled": true,
  "hermes_tweet_queries": [
    {"name": "Agent Skills", "query": "Hermes Agent skill", "limit": 10},
    "OpenClaw Twitter skill"
  ],
  "hermes_tweet_api_base": "https://xquik.com",
  "hermes_tweet_api_key_env": "XQUIK_API_KEY"
}
```

Run:

```bash
export XQUIK_API_KEY="xq_your_key"
python scripts/x_monitorplus_hermes_tweet.py --root .runtime fetch
```

Rules:

- keep the browser monitor as the default for home feeds and private Lists
- use Hermes Tweet search only for public query collection
- never write API keys to tracked files
- treat the fetcher as read-only; do not post, like, repost, follow, DM, or change account state
- read results from `.runtime/event_archive.jsonl` just like browser-captured events

## Optional Discord

Discord is a distribution sink, not a requirement.

To enable it, set:

```json
{
  "output_sinks": ["jsonl", "discord"],
  "discord_enabled": true,
  "discord_channel_id": "YOUR_CHANNEL_ID",
  "discord_bot_token": "Bot YOUR_TOKEN"
}
```

Never commit real tokens.

## Responsible Use

Use xplus.skill for personal, low-volume monitoring of feeds or Lists the user's own account can access. Do not present it as a compliance workaround for the X API. Do not use it for bulk scraping, resale of X data, spam, bypassing access restrictions, or model training.

## Multiple Profiles

Default to one profile. Only mention multiple profiles if the user asks.

For multiple profiles, create one runtime root per profile:

```bash
python scripts/x_monitorplus_service.py --root .runtime/slot-1 open-profile
python scripts/x_monitorplus_service.py --root .runtime/slot-2 open-profile
```

Each root gets its own login session and event archive. The same Chrome/Chromium binary can be shared.

## Troubleshooting

- `missing_config`: inspect `.runtime/config.json`; at least one source mode must be enabled.
- `chrome_not_found`: only happens when `browser_channel` is explicitly `chrome`; use `auto` or `chromium`.
- browser profile lock/startup errors: close any visible `open-profile` window for the same runtime root.
- no events: run `status`, check target URL, confirm the X account can view the feed/List, and inspect `check_archive.jsonl`.
- Playwright import/browser errors: run `pip install -r requirements.txt` and `python -m playwright install chromium`.

## Verification

Run tests from the repository root:

```bash
python -m unittest discover -s tests
python scripts/x_monitorplus_regression_smoke.py
python scripts/x_monitorplus_hermes_tweet.py --root .runtime fetch
```
