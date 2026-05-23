# xplus.skill

[中文说明](README.zh-CN.md)

Browser-based low-latency monitoring for X/Twitter home feeds and private Lists, designed for Codex and other local agents first. Discord is an optional distribution channel.

This repository contains the public, portable version of the `xplus.skill` Codex skill and service scripts.

## What It Does

- Watches the X home recommendation feed, private Lists, or both.
- Scans visible top posts quickly while using slower hard reloads to avoid excessive page hammering.
- Writes captured events to local JSONL so Codex or another agent can inspect and route them.
- Optionally sends a fast first Discord alert when a new post appears. Discord is the recommended channel for human-facing real-time alerts.
- Optionally edits the same Discord message later with a cleaner translated/editorial draft.
- Tracks seen posts durably to reduce duplicate alerts across restarts.
- Includes watchdog and stability helper scripts for unattended runs.

## Requirements

- Python 3.10 or newer
- Google Chrome, Chromium, or Playwright's bundled Chromium
- Playwright
- `requests`
- A dedicated X/Twitter monitor account
- Optional: a Discord bot token and target channel ID

Install:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

`browser_channel` defaults to `auto`: xplus.skill tries system Chrome first, then falls back to Playwright's bundled Chromium. Set it to `chrome` to require Google Chrome, or `chromium` to use Playwright's bundled browser directly. The same fallback is used by `open-profile`, so users without Chrome can still open a visible Chromium window and log in.

## Quick Start

Create a runtime folder outside the repository:

```bash
mkdir .runtime
copy config.example.json .runtime\config.json
```

Edit `.runtime\config.json` with your X source URLs. The default example writes events locally and does not require Discord.

Open the profile and log in to X:

```bash
python scripts/x_monitorplus_service.py --root .runtime open-profile
```

If Chrome is not installed, this opens Playwright's bundled Chromium instead. Keep the window open while logging in, then close it when the X session is ready.

Then start the watcher:

```bash
python scripts/x_monitorplus_service.py --root .runtime start
python scripts/x_monitorplus_service.py --root .runtime status
```

Stop it:

```bash
python scripts/x_monitorplus_service.py --root .runtime stop
```

On Windows, optional wrapper scripts live in `bin/windows/` and respect `PYTHON_EXE` if you want to use a specific interpreter.

Without `--root`, runtime data defaults to an OS-local `XMonitorPlus` directory. For agent use, passing an explicit `--root` is recommended.

Captured posts are written under the runtime folder:

- `.runtime/event_archive.jsonl` for captured/suppressed/update events
- `.runtime/check_archive.jsonl` for each page check
- `.runtime/seen_archive.json` for durable duplicate prevention

Codex or any other agent can read `event_archive.jsonl` as the primary local interface.

## Optional Multiple Profiles

Start with one runtime root. Add more only when you need multiple X accounts, isolated Lists, or separate delivery settings.

Each runtime root owns its own config, state, cookies, and browser profile:

```text
.runtime/
  slot-1/
    config.json
    chrome-profile/
    event_archive.jsonl
  slot-2/
    config.json
    chrome-profile/
    event_archive.jsonl
```

Create and log in to each profile one at a time:

```bash
mkdir .runtime\slot-1
mkdir .runtime\slot-2
copy config.example.json .runtime\slot-1\config.json
copy config.example.json .runtime\slot-2\config.json

python scripts/x_monitorplus_service.py --root .runtime\slot-1 open-profile
python scripts/x_monitorplus_service.py --root .runtime\slot-2 open-profile
```

For each `open-profile` run, log in to the intended X account in the visible browser window, then close that browser window. The session is saved into that slot's profile. This works with system Chrome or Playwright's bundled Chromium; multiple slots share the same browser binary but use separate profile folders.

Run slots independently:

```bash
python scripts/x_monitorplus_service.py --root .runtime\slot-1 start
python scripts/x_monitorplus_service.py --root .runtime\slot-2 start
```

Do not open-profile and run the watcher for the same slot at the same time. A browser profile can only be owned by one active browser process.

## Configuration

See `config.example.json` for a safe starting point.

Sensitive values belong in your runtime config or environment, never in git:

- Discord bot token
- Discord channel ID if private
- OpenAI-compatible API keys
- X cookies
- browser profile directories
- event archives and state files

To enable Discord delivery, set:

```json
{
  "output_sinks": ["jsonl", "discord"],
  "discord_enabled": true,
  "discord_channel_id": "YOUR_CHANNEL_ID",
  "discord_bot_token": "Bot YOUR_TOKEN"
}
```

Discord is recommended when people need to see alerts immediately. For agent-only workflows, keep `output_sinks` as `["jsonl"]` and let the agent read `event_archive.jsonl`.

## Watchdog

The watchdog can keep a configured monitor running:

```bash
python scripts/x_monitorplus_watchdog.py --root .runtime start
python scripts/x_monitorplus_watchdog.py --root .runtime status
python scripts/x_monitorplus_watchdog.py --root .runtime stop
```

Use it only after manual start/status checks are healthy.

## Tests

```bash
python -m unittest discover -s tests
```

## License

MIT. See `LICENSE`.
