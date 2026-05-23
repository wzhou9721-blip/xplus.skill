import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import x_monitorplus_service as svc


DEFAULT_API_BASE = "https://xquik.com"
DEFAULT_API_KEY_ENVS = ("HERMES_TWEET_API_KEY", "XQUIK_API_KEY")
DEFAULT_LIMIT = 20
DEFAULT_TIMEOUT_SECONDS = 30
MAX_LIMIT = 100


def clean_text(value):
    return svc.clean_text(value)


def compact_error_text(value, limit=280):
    return svc.compact_error_text(value, limit=limit)


def config_bool(value, default=False):
    return svc.config_bool(value, default)


def parse_json_like(value, fallback=None):
    return svc.parse_json_like(value, fallback=fallback)


def clamp_limit(value, default=DEFAULT_LIMIT):
    return svc.clamp_int(value, default, minimum=1, maximum=MAX_LIMIT)


def config_list(value):
    parsed = parse_json_like(value, fallback=value)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, str):
        return [line.strip() for line in parsed.splitlines() if line.strip()]
    return []


def normalize_query_configs(config):
    raw_queries = config_list((config or {}).get("hermes_tweet_queries", []))
    default_limit = clamp_limit((config or {}).get("hermes_tweet_limit", DEFAULT_LIMIT))
    queries = []
    seen = set()
    for raw_entry in raw_queries:
        if isinstance(raw_entry, str):
            entry = {"query": raw_entry}
        elif isinstance(raw_entry, dict):
            entry = dict(raw_entry)
        else:
            continue
        query = clean_text(entry.get("query", ""))
        if not query or query in seen:
            continue
        seen.add(query)
        if not config_bool(entry.get("enabled", True), True):
            continue
        queries.append(
            {
                "query": query,
                "name": clean_text(entry.get("name", "")) or query,
                "limit": clamp_limit(entry.get("limit", default_limit), default=default_limit),
            }
        )
    return queries


def api_base(config):
    return clean_text((config or {}).get("hermes_tweet_api_base", "")) or DEFAULT_API_BASE


def api_key_env_names(config):
    configured = clean_text((config or {}).get("hermes_tweet_api_key_env", ""))
    names = []
    if configured:
        names.append(configured)
    names.extend(DEFAULT_API_KEY_ENVS)
    return list(dict.fromkeys(name for name in names if name))


def api_key_from_env(config):
    for name in api_key_env_names(config):
        value = clean_text(os.environ.get(name, ""))
        if value:
            return value, name
    return "", ""


def auth_headers(api_key):
    value = clean_text(api_key)
    if value.lower().startswith("bearer "):
        return {"Authorization": value}
    return {"X-API-Key": value}


def api_url(config, path):
    base = api_base(config).rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def request_timeout(config):
    return svc.clamp_int(
        (config or {}).get("hermes_tweet_timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        DEFAULT_TIMEOUT_SECONDS,
        minimum=5,
        maximum=180,
    )


def fetch_search(config, api_key, query, limit):
    response = requests.get(
        api_url(config, "/api/v1/x/tweets/search"),
        headers=auth_headers(api_key),
        params={"q": query, "limit": limit},
        timeout=request_timeout(config),
    )
    response.raise_for_status()
    return response.json()


def nested_value(payload, *keys):
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return current


def first_text(payload, keys):
    for key in keys:
        if isinstance(key, tuple):
            value = nested_value(payload, *key)
        elif isinstance(payload, dict):
            value = payload.get(key)
        else:
            value = ""
        text = clean_text(value)
        if text:
            return text
    return ""


def collect_tweet_candidates(payload):
    if isinstance(payload, list):
        return list(payload)
    if not isinstance(payload, dict):
        return []
    for key in ("tweets", "data", "results", "items", "statuses"):
        value = payload.get(key)
        if isinstance(value, list):
            return list(value)
        if isinstance(value, dict):
            nested = collect_tweet_candidates(value)
            if nested:
                return nested
    for value in payload.values():
        nested = collect_tweet_candidates(value)
        if nested:
            return nested
    return []


def normalize_handle(value):
    return clean_text(value).lstrip("@")


def tweet_status_url(tweet_id, handle):
    if not tweet_id or not handle:
        return ""
    return f"https://x.com/{handle}/status/{tweet_id}"


def normalize_tweet(item, query_config, observed_at):
    if not isinstance(item, dict):
        return {}
    tweet_id = first_text(item, ("tweet_id", "id", "id_str", "rest_id", "conversation_id"))
    text = first_text(item, ("source_full_text", "full_text", "text", "content", "body"))
    handle = normalize_handle(
        first_text(
            item,
            (
                "handle",
                "username",
                "screen_name",
                ("author", "username"),
                ("author", "screen_name"),
                ("user", "username"),
                ("user", "screen_name"),
            ),
        )
    )
    url = first_text(item, ("url", "status_url", "link", "tweet_url"))
    if not url:
        url = tweet_status_url(tweet_id, handle)
    if not tweet_id and url:
        match = re.search(r"/status/(\d+)", url)
        if match:
            tweet_id = match.group(1)
    if not tweet_id:
        return {}
    created_at = first_text(item, ("created_at", "createdAt", "timestamp", "time"))
    source_full_text = text
    return {
        "tweet_id": tweet_id,
        "handle": handle,
        "url": url,
        "created_at": created_at,
        "original_text": text,
        "source_full_text": source_full_text,
        "source_title_text": svc.source_text_to_title(source_full_text, limit=260),
        "source_body_text": source_full_text,
        "target_key": f"hermes_tweet:{query_config['query']}",
        "target_name": query_config["name"],
        "target_url": "",
        "mode": "hermes_tweet",
        "mode_label": "Hermes Tweet",
        "at": observed_at,
        "output_sinks": ["jsonl"],
        "discord_delivered": False,
        "message_id": "",
        "source": "hermes_tweet",
        "query": query_config["query"],
    }


def remember_fetch_events(store, config, query_config, payload, observed_at):
    state = store.load_state()
    seen = svc.combined_seen_ids(store, config, state, observed_at=observed_at)
    events = []
    skipped_seen = 0
    for item in collect_tweet_candidates(payload):
        event = normalize_tweet(item, query_config, observed_at)
        tweet_id = clean_text(event.get("tweet_id", ""))
        if not tweet_id:
            continue
        if tweet_id in seen:
            skipped_seen += 1
            continue
        events.append(event)
        seen[tweet_id] = observed_at
    for event in events:
        svc.remember_event(store, event, archive_event_type="hermes_tweet_fetch")
    svc.mark_seen_ids(
        store,
        [event["tweet_id"] for event in events],
        stamp=observed_at,
        config=config,
        target_ref={"key": f"hermes_tweet:{query_config['query']}"},
    )
    return {"events": events, "skipped_seen": skipped_seen}


def fetch_once(store, limit_override=0, dry_run=False):
    config = svc.runtime_config(store)
    if not config_bool(config.get("hermes_tweet_enabled", False), False):
        return {
            "ok": True,
            "action": "hermes_tweet_fetch",
            "enabled": False,
            "skipped": True,
            "reason": "hermes_tweet_disabled",
        }
    api_key, key_env = api_key_from_env(config)
    if not api_key:
        return {
            "ok": False,
            "action": "hermes_tweet_fetch",
            "enabled": True,
            "error": "missing_api_key",
            "api_key_envs": api_key_env_names(config),
        }
    queries = normalize_query_configs(config)
    if not queries:
        return {
            "ok": False,
            "action": "hermes_tweet_fetch",
            "enabled": True,
            "error": "missing_queries",
        }
    observed_at = svc.iso_now()
    fetched = []
    written = 0
    skipped_seen = 0
    for query_config in queries:
        effective_query = dict(query_config)
        if limit_override:
            effective_query["limit"] = clamp_limit(limit_override)
        payload = fetch_search(config, api_key, effective_query["query"], effective_query["limit"])
        result = remember_fetch_events(store, config, effective_query, payload, observed_at) if not dry_run else {"events": [], "skipped_seen": 0}
        count = len(collect_tweet_candidates(payload))
        event_count = len(result["events"])
        fetched.append(
            {
                "query": effective_query["query"],
                "name": effective_query["name"],
                "limit": effective_query["limit"],
                "fetched": count,
                "written": event_count,
                "skipped_seen": result["skipped_seen"],
            }
        )
        written += event_count
        skipped_seen += result["skipped_seen"]
    return {
        "ok": True,
        "action": "hermes_tweet_fetch",
        "enabled": True,
        "dry_run": bool(dry_run),
        "api_base": api_base(config),
        "api_key_env": key_env,
        "query_count": len(queries),
        "written": written,
        "skipped_seen": skipped_seen,
        "queries": fetched,
        "event_archive_path": str(store.event_archive_path),
    }


def build_parser():
    parser = argparse.ArgumentParser(description="Fetch X search results through Hermes Tweet into xplus.skill JSONL")
    parser.add_argument("--root", default="")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch_parser = sub.add_parser("fetch")
    fetch_parser.add_argument("--limit", type=int, default=0)
    fetch_parser.add_argument("--dry-run", action="store_true")
    return parser


def main():
    svc.configure_stdio()
    args = build_parser().parse_args()
    store = svc.Store(root=args.root or None)
    try:
        payload = fetch_once(store, limit_override=args.limit, dry_run=args.dry_run)
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload.get("ok", True) else 1
    except requests.HTTPError as exc:
        body = exc.response.text if exc.response is not None else ""
        print(
            json.dumps(
                {
                    "ok": False,
                    "action": "hermes_tweet_fetch",
                    "error": str(exc),
                    "status_code": exc.response.status_code if exc.response is not None else None,
                    "body": compact_error_text(body, limit=500),
                },
                ensure_ascii=False,
            )
        )
        return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "action": "hermes_tweet_fetch", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
