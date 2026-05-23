import argparse
from contextlib import contextmanager
from difflib import SequenceMatcher
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import winreg
except ImportError:
    winreg = None

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    PlaywrightTimeoutError = Exception
    sync_playwright = None


SERVICE_NAME = "x-monitor-plus"
MODE_HOME = "home"
MODE_LIST = "list"
MODE_LABELS = {MODE_HOME: "推荐", MODE_LIST: "列表"}
DEFAULT_SOURCE_SLOT = "1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8798
DEFAULT_WATCH_INTERVAL_SECONDS = 4
DEFAULT_RELOAD_INTERVAL_SECONDS = 45
DEFAULT_TARGET_CHECK_JITTER_MILLISECONDS = 900
DEFAULT_RELOAD_INTERVAL_JITTER_SECONDS = 20
DEFAULT_PAGE_TIMEOUT_MS = 30000
DEFAULT_SETTLE_MILLISECONDS = 1800
DEFAULT_EMPTY_PAGE_RETRY_COUNT = 2
DEFAULT_EMPTY_PAGE_RETRY_DELAY_MILLISECONDS = 250
DEFAULT_EMPTY_PAGE_INITIAL_RETRY_COUNT_CAP = 2
DEFAULT_EMPTY_PAGE_INITIAL_RETRY_DELAY_MILLISECONDS_CAP = 250
DEFAULT_EMPTY_PAGE_RECOVERY_SETTLE_MILLISECONDS = 400
DEFAULT_EMPTY_PAGE_RECOVERY_SETTLE_MILLISECONDS_CAP = 500
DEFAULT_EMPTY_PAGE_RECOVERY_RETRY_COUNT_CAP = 1
DEFAULT_EMPTY_PAGE_RECOVERY_RETRY_DELAY_MILLISECONDS_CAP = 250
DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_COUNT = 1
DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_DELAY_MILLISECONDS = 500
DEFAULT_EMPTY_PAGE_RESTART_THRESHOLD = 3
DEFAULT_MULTI_TARGET_EMPTY_PAGE_RESTART_THRESHOLD = 3
DEFAULT_EMPTY_PAGE_FAST_REOPEN_RESTART_THRESHOLD = 3
DEFAULT_EMPTY_PAGE_WAVE_PROBE_WAIT_MILLISECONDS = 500
DEFAULT_EMPTY_PAGE_WAVE_RECOVERY_COOLDOWN_SECONDS = 180
DEFAULT_EMPTY_PAGE_WAVE_CANARY_ENABLED = True
DEFAULT_EMPTY_PAGE_WAVE_CANARY_WAIT_MILLISECONDS = 1500
DEFAULT_LOADING_SHELL_WAIT_MILLISECONDS = 1200
DEFAULT_LOADING_SHELL_BODY_TIMEOUT_MILLISECONDS = 1200
DEFAULT_ZERO_ITEM_SCROLL_RECOVERY_ATTEMPTS = 1
DEFAULT_PARTIAL_PAGE_MIN_VISIBLE_COUNT = 3
DEFAULT_PARTIAL_PAGE_HISTORY_WINDOW_SECONDS = 30 * 60
DEFAULT_PARTIAL_PAGE_NEWER_TOP_GAP_SECONDS = 60
DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_ATTEMPTS = 2
DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_SETTLE_MILLISECONDS = 700
DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_STEP_PIXELS = 900
DEFAULT_CANDIDATE_GAP_SUPPLEMENT_ATTEMPTS = 1
DEFAULT_CANDIDATE_GAP_SUPPLEMENT_SETTLE_MILLISECONDS = 350
DEFAULT_CANDIDATE_GAP_SUPPLEMENT_MIN_DOM_ARTICLE_COUNT = 3
DEFAULT_CANDIDATE_GAP_SUPPLEMENT_MIN_GAP = 2
DEFAULT_TOP_SCAN_COUNT = 8
DEFAULT_MAX_LIST_TARGETS = 5
DEFAULT_MAX_SEEN_IDS = 600
DEFAULT_MAX_DELIVERY_DELAY_SECONDS = 0
DEFAULT_LATE_NEW_ITEM_RECOVERY_DELAY_SECONDS = 90
DEFAULT_STALE_REFRESH_ENABLED = True
DEFAULT_STALE_REFRESH_TOP_DELAY_SECONDS = 180
DEFAULT_STALE_REFRESH_UNCHANGED_COUNT = 12
DEFAULT_STALE_REFRESH_COOLDOWN_SECONDS = 180
DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_ENABLED = True
DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_ATTEMPTS = 1
DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_SETTLE_MILLISECONDS = 500
DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_STEP_PIXELS = 700
DEFAULT_HOT_LIST_ACCELERATION_ENABLED = False
DEFAULT_HOT_LIST_ACCELERATION_SECONDS = 15 * 60
DEFAULT_HOT_LIST_STALE_TOP_DELAY_SECONDS = 120
DEFAULT_HOT_LIST_STALE_UNCHANGED_COUNT = 8
DEFAULT_HOT_LIST_STALE_COOLDOWN_SECONDS = 120
DEFAULT_HOT_LIST_SLOW_DELIVERY_THRESHOLD_SECONDS = 60
DEFAULT_SLOW_ATTRIBUTION_THRESHOLD_SECONDS = 45
DEFAULT_RESTART_GAP_REPLAY_SECONDS = 0
DEFAULT_RECENT_EVENTS_LIMIT = 40
DEFAULT_RECENT_CHECKS_LIMIT = 80
EVENT_ARCHIVE_FILENAME = "event_archive.jsonl"
CHECK_ARCHIVE_FILENAME = "check_archive.jsonl"
SEEN_ARCHIVE_FILENAME = "seen_archive.json"
DEFAULT_SLOT_INTERVENTION_ALERT_COOLDOWN_SECONDS = 30 * 60
DEFAULT_BROWSER_CRASH_AUTO_RESTART_ENABLED = True
DEFAULT_BROWSER_CRASH_AUTO_RESTART_COOLDOWN_SECONDS = 180
DEFAULT_BROWSER_LIGHTWEIGHT_MODE = True
DEFAULT_BROWSER_DISABLE_IMAGES = True
DEFAULT_EDITOR_DRAFT_ENABLED = True
DEFAULT_EDITOR_DRAFT_TIMEOUT_SECONDS = 45
DEFAULT_EDITOR_DRAFT_MIN_INTERVAL_SECONDS = 4
DEFAULT_EDITOR_DRAFT_RATE_LIMIT_COOLDOWN_SECONDS = 90
DEFAULT_EDITOR_DRAFT_TRANSIENT_RETRY_COUNT = 2
DEFAULT_EDITOR_DRAFT_TRANSIENT_RETRY_DELAY_MILLISECONDS = 2000
DEFAULT_TRANSLATE_TO = "zh-CN"
DEFAULT_MACHINE_TRANSLATION_RETRY_COUNT = 1
DEFAULT_MACHINE_TRANSLATION_RETRY_DELAY_MILLISECONDS = 350
DEFAULT_LOCAL_FAST_TRANSLATION_ENABLED = False
DEFAULT_LOCAL_FAST_TRANSLATION_TIMEOUT_SECONDS = 8
DEFAULT_INITIAL_LOCAL_FAST_TRANSLATION_TIMEOUT_SECONDS = 0.8
DEFAULT_LOCAL_FAST_TRANSLATION_INITIAL_FAILURE_COOLDOWN_SECONDS = 30
DEFAULT_ASYNC_ENRICH_MAX_WORKERS = 2
DEFAULT_PENDING_EVENT_RECOVERY_STALE_SECONDS = 90
DEFAULT_PENDING_EVENT_RECOVERY_COOLDOWN_SECONDS = 90
DEFAULT_PENDING_EVENT_RECOVERY_MAX_ATTEMPTS = 2
DEFAULT_SERVICE_START_TIMEOUT_SECONDS = 20
DEFAULT_SERVICE_STOP_TIMEOUT_SECONDS = 15
DEFAULT_DISCORD_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_DISCORD_TRANSIENT_RETRY_COUNT = 2
DEFAULT_DISCORD_TRANSIENT_RETRY_DELAY_MILLISECONDS = 1200
DEFAULT_DURABLE_SEEN_ENABLED = True
DEFAULT_DURABLE_SEEN_RETENTION_SECONDS = 72 * 3600
DEFAULT_MAX_DURABLE_SEEN_IDS = 50000
DEFAULT_NEAR_DUPLICATE_WINDOW_SECONDS = 180
DEFAULT_NEAR_DUPLICATE_SIMILARITY_RATIO = 0.96
DEFAULT_NEAR_DUPLICATE_MIN_TEXT_LENGTH = 24
DEFAULT_STORAGE_BASE = Path(os.environ.get("X_MONITORPLUS_STORAGE_BASE", "")) if os.environ.get("X_MONITORPLUS_STORAGE_BASE", "").strip() else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "XMonitorPlus"
DEFAULT_ROOT = DEFAULT_STORAGE_BASE / SERVICE_NAME
DEFAULT_BROWSER_PROFILE_DIR = DEFAULT_STORAGE_BASE / "chrome-profile"
LEGACY_X_MONITOR_CONFIG = DEFAULT_STORAGE_BASE / "x-monitor" / "config.json"
LEGACY_X_MONITOR_COOKIES = DEFAULT_STORAGE_BASE / "x-monitor" / "x.cookies.json"
DISCORD_DEFAULTS_SOURCE = Path(os.environ.get("X_MONITORPLUS_DISCORD_DEFAULTS_SOURCE", ""))
WINDOWS_DETACHED_PROCESS = 0x00000008
WINDOWS_CREATE_NEW_PROCESS_GROUP = 0x00000200
WINDOWS_CREATE_NO_WINDOW = 0x08000000
DRAFT_REQUEST_LOCK = threading.Lock()
LOCAL_FAST_TRANSLATION_CIRCUIT_LOCK = threading.Lock()
LOCAL_FAST_TRANSLATION_CIRCUIT = {"key": "", "blocked_until": 0.0, "last_error": ""}
CONFIG_PARSE_ERROR_KEY = "__config_parse_error"
STATE_PARSE_ERROR_KEY = "__state_parse_error"
LEGACY_DEFAULTS_PARSE_ERROR_KEY = "__legacy_defaults_parse_error"
LEGACY_DEFAULTS_CONFIG_EXISTS_KEY = "__legacy_defaults_config_exists"
LEGACY_DEFAULTS_CONFIG_PATH_KEY = "__legacy_defaults_config_path"
LOADING_SHELL_SIGNAL_SELECTORS = (
    ("progressbar", '[role="progressbar"]'),
    ("aria_busy", '[aria-busy="true"]'),
)
LOADING_SHELL_TEXT_SIGNALS = (
    ("loading", "text:loading"),
    ("try again", "text:try_again"),
    ("加载", "text:加载"),
)

def normalize_source_slot(value):
    text = str(value or "").strip().lower()
    slot_aliases = {
        "1": {"1", "default", "primary", "main", "\u4e00", "1\u53f7", "1\u53f7\u69fd\u4f4d", "\u69fd\u4f4d1"},
        "2": {"2", "secondary", "second", "\u4e8c", "2\u53f7", "2\u53f7\u69fd\u4f4d", "\u69fd\u4f4d2"},
        "3": {"3", "third", "tertiary", "\u4e09", "3\u53f7", "3\u53f7\u69fd\u4f4d", "\u69fd\u4f4d3"},
        "4": {"4", "fourth", "quaternary", "\u56db", "4\u53f7", "4\u53f7\u69fd\u4f4d", "\u69fd\u4f4d4"},
        "5": {"5", "fifth", "quinary", "\u4e94", "5\u53f7", "5\u53f7\u69fd\u4f4d", "\u69fd\u4f4d5"},
        "6": {"6", "sixth", "senary", "\u516d", "6\u53f7", "6\u53f7\u69fd\u4f4d", "\u69fd\u4f4d6"},
        "7": {"7", "seventh", "septenary", "\u4e03", "7\u53f7", "7\u53f7\u69fd\u4f4d", "\u69fd\u4f4d7"},
    }
    if not text:
        return DEFAULT_SOURCE_SLOT
    for slot_value, aliases in slot_aliases.items():
        if text in aliases:
            return slot_value
    match = re.search(r"([1-7])", text)
    if match:
        return match.group(1)
    return DEFAULT_SOURCE_SLOT



def source_slot_label(slot):
    return f"{normalize_source_slot(slot)}号槽位"


def x_monitor_root_for_slot(slot):
    normalized = normalize_source_slot(slot)
    suffix = "" if normalized == "1" else f"-{normalized}"
    return DEFAULT_STORAGE_BASE / f"x-monitor{suffix}"


def x_monitor_profile_dir_for_slot(slot):
    normalized = normalize_source_slot(slot)
    suffix = "" if normalized == "1" else f"-{normalized}"
    return DEFAULT_STORAGE_BASE / f"chrome-profile{suffix}"


def x_monitor_default_config_for_slot(slot):
    root = x_monitor_root_for_slot(slot)
    return {
        "slot": normalize_source_slot(slot),
        "root": str(root),
        "config_path": str(root / "config.json"),
        "cookies_path": str(root / "x.cookies.json"),
        "profile_dir": str(x_monitor_profile_dir_for_slot(slot)),
    }


def load_x_monitor_slot_binding(slot):
    defaults = x_monitor_default_config_for_slot(slot)
    config_path = Path(defaults["config_path"])
    payload = {}
    parse_error = ""
    if config_path.exists():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            parse_error = compact_error_text(f"{type(exc).__name__}: {exc}", limit=280)
            payload = {}
    return {
        "slot": defaults["slot"],
        "root": defaults["root"],
        "config_path": defaults["config_path"],
        "config_parse_error": parse_error,
        "cookies_path": clean_text(payload.get("x_cookies_path", "")) or defaults["cookies_path"],
        "profile_dir": clean_text(payload.get("x_browser_profile_dir", "")) or defaults["profile_dir"],
        "config_exists": config_path.exists(),
        "cookies_exists": Path(clean_text(payload.get("x_cookies_path", "")) or defaults["cookies_path"]).exists(),
        "profile_exists": Path(clean_text(payload.get("x_browser_profile_dir", "")) or defaults["profile_dir"]).exists(),
    }


def configure_stdio():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def now_utc():
    return datetime.now(timezone.utc)


def iso_now():
    return now_utc().isoformat()


def timestamp_token():
    return now_utc().strftime("%Y%m%dT%H%M%S%fZ")


def log_exception(context, exc):
    try:
        print(f"[{iso_now()}] {context}: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
    except Exception:
        pass


def clean_text(value):
    text = str(value or "")
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compact_error_text(value, limit=280):
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


EMOJI_PASSTHROUGH_EXTRA_CODEPOINTS = {
    0x00A9,
    0x00AE,
    0x200D,
    0x203C,
    0x2049,
    0x20E3,
    0x2122,
    0x2139,
    0x3030,
    0x303D,
    0x3297,
    0x3299,
    0xFE0F,
}

EMOJI_PASSTHROUGH_RANGES = (
    (0x1F1E6, 0x1F1FF),
    (0x1F300, 0x1FAFF),
    (0x2300, 0x23FF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xE0020, 0xE007F),
)


def is_emoji_like_char(char):
    if not char:
        return False
    codepoint = ord(char)
    if codepoint in EMOJI_PASSTHROUGH_EXTRA_CODEPOINTS:
        return True
    return any(start <= codepoint <= end for start, end in EMOJI_PASSTHROUGH_RANGES)


def is_emoji_passthrough_text(text):
    value = clean_text(text)
    if not value:
        return False
    keycap_matches = re.findall(r"[#*0-9]\ufe0f?\u20e3", value)
    has_emoji = bool(keycap_matches)
    value = re.sub(r"[#*0-9]\ufe0f?\u20e3", "", value)
    for char in value:
        if char.isspace():
            continue
        if is_emoji_like_char(char):
            has_emoji = True
            continue
        category = unicodedata.category(char)
        if category.startswith("P") or category.startswith("S") or category in {"Mn", "Mc", "Me"}:
            continue
        return False
    return has_emoji


def normalize_similarity_text(value):
    text = clean_text(value).lower()
    if not text:
        return ""
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"@[A-Za-z0-9_]{1,32}", " ", text)
    text = re.sub(r"[^\w\u00C0-\u024F\u0400-\u04FF\u4e00-\u9fff]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def text_similarity_ratio(left, right):
    left_text = normalize_similarity_text(left)
    right_text = normalize_similarity_text(right)
    if not left_text or not right_text:
        return 0.0
    if left_text == right_text:
        return 1.0
    return SequenceMatcher(None, left_text, right_text).ratio()


def short_text_token_count(value):
    return len(re.findall(r"[\w\u00C0-\u024F\u0400-\u04FF\u4e00-\u9fff']+", clean_text(value).lower()))


REPOST_CONTEXT_MARKERS = (
    "已转帖",
    "转帖了",
    "已转发",
    "转发了",
    "reposted",
    "retweeted",
    "repostó",
    "retuiteó",
)

DEFAULT_REPOST_MIN_MEANINGFUL_TEXT_LENGTH = 24
DEFAULT_REPOST_MIN_COMMENTARY_TEXT_LENGTH = 12

LOW_SIGNAL_REPOST_COMMENTARY_MARKERS = (
    "this",
    "wow",
    "nice",
    "lol",
    "lmao",
    "read this",
    "look at this",
    "interesting",
    "insane",
    "crazy",
    "unreal",
    "thoughts",
    "👀",
)


def extract_repost_context(raw_text, tweet_text, handle="", social_context=""):
    raw_value = clean_text(raw_text)
    text_value = clean_text(tweet_text)
    handle_value = clean_text(handle)
    social_value = clean_text(social_context)
    candidates = []
    if social_value:
        candidates.append(social_value)
    if raw_value and text_value:
        index = raw_value.find(text_value)
        if index > 0:
            candidates.append(clean_text(raw_value[:index]))
    if raw_value and handle_value:
        raw_lines = [clean_text(line) for line in raw_value.splitlines() if clean_text(line)]
        handle_index = next((index for index, line in enumerate(raw_lines) if f"@{handle_value}".lower() in line.lower()), -1)
        if handle_index > 0:
            candidates.append(clean_text("\n".join(raw_lines[:handle_index])))
    if raw_value:
        candidates.extend(clean_text(line) for line in raw_value.splitlines()[:3] if clean_text(line))
        candidates.append(raw_value[:200])
    for candidate in candidates:
        lowered = candidate.lower()
        if any(marker in candidate or marker in lowered for marker in REPOST_CONTEXT_MARKERS):
            return compact_error_text(candidate, limit=160)
    return ""


def extract_repost_added_commentary_text(item):
    item_value = item or {}
    text_blocks = [clean_text(value) for value in list(item_value.get("text_blocks", []) or []) if clean_text(value)]
    if len(text_blocks) >= 2:
        first_block = clean_text(text_blocks[0])
        remaining_blocks = "\n".join(text_blocks[1:])
        if first_block and text_similarity_ratio(first_block, remaining_blocks) < 0.9:
            return compact_error_text(first_block, limit=280)
    raw_value = clean_text(item_value.get("raw_text", ""))
    text_value = clean_text(item_value.get("text", ""))
    social_value = clean_text(item_value.get("social_context", ""))
    prefix = raw_value
    if text_value and text_value in raw_value:
        prefix = clean_text(raw_value[: raw_value.find(text_value)])
    if social_value and prefix.lower().startswith(social_value.lower()):
        prefix = clean_text(prefix[len(social_value) :])
    prefix_lines = [clean_text(line) for line in prefix.splitlines() if clean_text(line)]
    filtered_lines = []
    for line in prefix_lines:
        lowered = line.lower()
        if any(marker in lowered for marker in ("reposted", "retweeted", "转帖", "转发")):
            continue
        if re.fullmatch(r"@[\w.]{1,32}", line, flags=re.I):
            continue
        if re.search(r"^\d+\s*(?:s|m|h|d|秒|分钟|小时|天)$", line, flags=re.I):
            continue
        filtered_lines.append(line)
    return compact_error_text("\n".join(filtered_lines), limit=280) if filtered_lines else ""


def is_meaningful_repost_commentary(text):
    value = clean_text(text)
    if not value:
        return False
    if is_emoji_passthrough_text(value):
        return False
    normalized = normalize_similarity_text(value)
    if not normalized:
        return False
    if any(normalized == normalize_similarity_text(marker) for marker in LOW_SIGNAL_REPOST_COMMENTARY_MARKERS):
        return False
    if short_text_token_count(normalized) >= 4:
        return True
    return len(normalized) >= DEFAULT_REPOST_MIN_COMMENTARY_TEXT_LENGTH


def classify_repost_filter_reason(item):
    item_value = item or {}
    if not bool(item_value.get("is_repost")):
        return ""
    if bool(item_value.get("has_video")) or bool(item_value.get("has_image")) or bool(item_value.get("has_external_link")):
        return ""
    if is_meaningful_repost_commentary(extract_repost_added_commentary_text(item_value)):
        return ""
    signal_text = normalize_similarity_text(item_value.get("text", ""))
    if len(signal_text) >= DEFAULT_REPOST_MIN_MEANINGFUL_TEXT_LENGTH:
        return ""
    return "low_signal_repost_without_media_or_meaningful_text"


def item_repost_filter_reason(item):
    explicit = clean_text((item or {}).get("repost_filter_reason", ""))
    if explicit:
        return explicit
    if bool((item or {}).get("is_filtered_repost")):
        return "low_signal_repost_without_media_or_meaningful_text"
    return classify_repost_filter_reason(item)


def item_is_filtered_repost(item):
    return bool(item_repost_filter_reason(item))


TEASER_ONLY_TEXT_MARKERS = (
    "read more",
    "read more here",
    "watch more here",
    "\u9605\u8bfb\u66f4\u591a",
    "\u70b9\u51fb\u8fd9\u91cc\u89c2\u770b\u66f4\u591a",
)

TEASER_PREFIX_TEXT_MARKERS = (
    "read more",
    "read more here",
    "watch more here",
    "\u9605\u8bfb\u66f4\u591a",
    "\u70b9\u51fb\u9605\u8bfb\u5168\u6587",
    "\u70b9\u51fb\u67e5\u770b\u5168\u6587",
    "\u70b9\u51fb\u8fd9\u91cc\u89c2\u770b\u66f4\u591a",
)

TEASER_URLISH_PATTERN = re.compile(
    r"(https?\s*:\s*/\s*/\s*\S+|www\.\S+|\b[a-z0-9][a-z0-9.-]{0,252}\.(?:com|co|net|org|io|tv|news|live|uk|us|de|jp|cn|es|fr|it|au|ca|fm|gg|me|ly)\b)",
    re.IGNORECASE,
)

TEASER_PROMO_CTA_MARKERS = (
    "watch now",
    "watch here",
    "watch on",
    "watch live",
    "tune in",
    "join us on",
    "join us live",
    "catch up on",
    "stream now",
    "available now",
    "veente ya",
    "vente ya",
    "ven ya",
    "miralo ya",
    "míralo ya",
    "miralo en",
    "míralo en",
    "sigue en",
    "entra ya",
    "no te pierdas",
)

TEASER_PROMO_PLATFORM_MARKERS = (
    "twitch",
    "youtube",
    "stream",
    "streaming",
    "platform",
    "platforms",
    "plataforma",
    "plataformas",
    "app",
    "podcast",
    "spotify",
    "spaces",
    "radio",
    "canal",
    "channel",
)

TEASER_PROMO_SHOW_MARKERS = (
    "show",
    "program",
    "programme",
    "programa",
    "analysis",
    "analizar",
    "analisis",
    "análisis",
    "debate",
    "discussion",
    "episode",
    "podcast",
    "highlights",
    "lo mejor",
    "best of",
    "resumen",
    "especial",
    "special",
    "inside",
)


def normalize_teaser_marker_text(value):
    text = clean_text(value)
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"https?\s*:\s*/\s*/\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"www\.\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[:：\-\u2013\u2014|/\\\\\u00b7]+$", "", text).strip()
    return text.lower()


def normalize_teaser_body_text(value):
    text = clean_text(value)
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"@[a-z0-9_]{1,32}", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_teaser_promo_context(tweet_text):
    value = clean_text(tweet_text)
    if not value:
        return ""
    normalized = normalize_teaser_body_text(value)
    if not normalized:
        return ""
    has_cta = any(marker in normalized for marker in TEASER_PROMO_CTA_MARKERS)
    has_platform = any(marker in normalized for marker in TEASER_PROMO_PLATFORM_MARKERS)
    has_show_context = any(marker in normalized for marker in TEASER_PROMO_SHOW_MARKERS)
    if has_cta and has_platform and has_show_context:
        return compact_error_text(value, limit=160)
    return ""


def extract_teaser_context(tweet_text, has_external_link=False):
    value = clean_text(tweet_text)
    if not value:
        return ""
    normalized_lines = []
    for raw_line in value.splitlines():
        line = clean_text(raw_line)
        if not line:
            continue
        without_standard_urls = re.sub(r"https?://\S+|www\.\S+", "", line, flags=re.IGNORECASE)
        normalized = normalize_teaser_marker_text(without_standard_urls)
        normalized_lines.append((line, normalized))
    if not normalized_lines:
        return ""
    matched_lines = []
    for original, normalized in normalized_lines:
        if normalized in TEASER_ONLY_TEXT_MARKERS:
            matched_lines.append(original)
            continue
        url_match = TEASER_URLISH_PATTERN.search(original)
        if url_match:
            prefix = normalize_teaser_marker_text(original[: url_match.start()])
            if prefix in TEASER_PREFIX_TEXT_MARKERS:
                matched_lines.append(original)
                continue
        if has_external_link and normalized in TEASER_PREFIX_TEXT_MARKERS:
            matched_lines.append(original)
    if matched_lines and len(matched_lines) == len(normalized_lines):
        return compact_error_text(" / ".join(matched_lines), limit=160)
    promo_context = extract_teaser_promo_context(value)
    if promo_context:
        return promo_context
    return ""


def normalize_target_key(value):
    text = clean_text(value)
    if text:
        return text
    return ""


def list_target_key(index):
    value = int(index or 0)
    if value < 1:
        value = 1
    if value > DEFAULT_MAX_LIST_TARGETS:
        value = DEFAULT_MAX_LIST_TARGETS
    return f"list{value}"


def list_target_index(value):
    text = normalize_target_key(value)
    match = re.fullmatch(r"list([1-5])", text)
    if not match:
        return 0
    return int(match.group(1))


def default_list_config(index):
    slot_index = int(index or 0)
    if slot_index < 1:
        slot_index = 1
    if slot_index > DEFAULT_MAX_LIST_TARGETS:
        slot_index = DEFAULT_MAX_LIST_TARGETS
    return {
        "id": list_target_key(slot_index),
        "name": f"列表{slot_index}",
        "url": "",
        "enabled": False,
    }


def parse_json_like(value, fallback=None):
    return parse_json_like_details(value, fallback=fallback)["value"]


def parse_json_like_details(value, fallback=None):
    if isinstance(value, (dict, list)):
        return {"value": value, "parse_error": ""}
    text = clean_text(value)
    if not text:
        return {"value": fallback, "parse_error": ""}
    try:
        return {"value": json.loads(text), "parse_error": ""}
    except Exception as exc:
        return {
            "value": fallback,
            "parse_error": compact_error_text(f"{type(exc).__name__}: {exc}", limit=280),
        }


def normalize_list_configs(config):
    payload = config or {}
    raw_entries = parse_json_like(payload.get("x_lists", []), fallback=payload.get("x_lists", []))
    parsed_entries = []
    if isinstance(raw_entries, dict):
        raw_entries = [raw_entries]
    if isinstance(raw_entries, list):
        parsed_entries = list(raw_entries)
    normalized = []
    seen_ids = set()
    for index in range(1, DEFAULT_MAX_LIST_TARGETS + 1):
        fallback = default_list_config(index)
        raw_entry = parsed_entries[index - 1] if index - 1 < len(parsed_entries) else None
        if isinstance(raw_entry, str):
            raw_entry = {"url": raw_entry}
        if not isinstance(raw_entry, dict):
            raw_entry = {}
        entry_id = normalize_target_key(raw_entry.get("id", "")) or fallback["id"]
        if entry_id in seen_ids or not re.fullmatch(r"list[1-5]", entry_id):
            entry_id = fallback["id"]
        seen_ids.add(entry_id)
        name = clean_text(raw_entry.get("name", "")) or fallback["name"]
        url = clean_text(raw_entry.get("url", ""))
        enabled_default = bool(url)
        entry = {
            "id": entry_id,
            "name": name,
            "url": url,
            "enabled": config_bool(raw_entry.get("enabled", enabled_default), enabled_default),
        }
        for optional_key in (
            "stale_refresh_enabled",
            "stale_refresh_top_delay_seconds",
            "stale_refresh_unchanged_count",
            "stale_refresh_cooldown_seconds",
            "late_new_item_recovery_delay_seconds",
            "max_delivery_delay_seconds",
        ):
            if optional_key in raw_entry:
                entry[optional_key] = raw_entry.get(optional_key)
        for legacy_key, current_key in (
            ("priority_stale_refresh_enabled", "stale_refresh_enabled"),
            ("priority_stale_refresh_top_delay_seconds", "stale_refresh_top_delay_seconds"),
            ("priority_stale_refresh_unchanged_count", "stale_refresh_unchanged_count"),
            ("priority_stale_refresh_cooldown_seconds", "stale_refresh_cooldown_seconds"),
        ):
            if legacy_key in raw_entry and current_key not in entry:
                entry[current_key] = raw_entry.get(legacy_key)
        normalized.append(entry)
    legacy_url = clean_text(payload.get("x_list_url", ""))
    legacy_enabled = config_bool(payload.get("x_list_enabled", False), False)
    if legacy_url and not any(clean_text(entry.get("url", "")) for entry in normalized):
        normalized[0]["url"] = legacy_url
        normalized[0]["enabled"] = legacy_enabled or bool(legacy_url)
    if legacy_enabled and not any(bool(entry.get("enabled", False)) for entry in normalized):
        normalized[0]["enabled"] = True
    return normalized


def sync_legacy_list_config_fields(config):
    entries = normalize_list_configs(config)
    synced = dict(config or {})
    synced["x_lists"] = entries
    first_with_url = next((entry for entry in entries if clean_text(entry.get("url", ""))), None)
    synced["x_list_url"] = clean_text((first_with_url or {}).get("url", ""))
    synced["x_list_enabled"] = any(bool(entry.get("enabled", False)) and clean_text(entry.get("url", "")) for entry in entries)
    return synced


def target_key(target_or_key):
    if isinstance(target_or_key, dict):
        return normalize_target_key(target_or_key.get("key", "")) or normalize_mode(target_or_key.get("mode", ""))
    return normalize_target_key(target_or_key)


def target_mode(target_or_key):
    if isinstance(target_or_key, dict):
        return normalize_mode(target_or_key.get("mode", ""))
    text = normalize_target_key(target_or_key)
    if text == MODE_HOME:
        return MODE_HOME
    if text.startswith("list"):
        return MODE_LIST
    return normalize_mode(text)


def target_label(target_or_key):
    if isinstance(target_or_key, dict):
        return clean_text(target_or_key.get("label", "")) or mode_label(target_or_key.get("mode", ""))
    key = target_key(target_or_key)
    if key == MODE_HOME:
        return mode_label(MODE_HOME)
    index = list_target_index(key)
    if index:
        return f"\u5217\u8868{index}"
    return mode_label(target_mode(key))


def parse_iso_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_local_timestamp(value=None):
    dt = parse_iso_datetime(value) if value else now_utc()
    if dt is None:
        dt = now_utc()
    try:
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value or "")


def elapsed_seconds_between(start_value, end_value=None):
    start_dt = parse_iso_datetime(start_value) if start_value else None
    if start_dt is None:
        return None
    end_dt = parse_iso_datetime(end_value) if end_value else now_utc()
    if end_dt is None:
        end_dt = now_utc()
    try:
        return max(0, int(round((end_dt - start_dt).total_seconds())))
    except Exception:
        return None


def item_created_at_sort_key(item):
    created_at = parse_iso_datetime((item or {}).get("created_at", ""))
    if created_at is None:
        return (0, 0.0)
    try:
        return (1, float(created_at.timestamp()))
    except Exception:
        return (1, 0.0)


def sort_items_by_created_at(items):
    return sorted(list(items or []), key=item_created_at_sort_key, reverse=True)


def merge_items_by_tweet_id(*item_groups):
    merged = {}
    for group in item_groups:
        for item in list(group or []):
            tweet_id = clean_text((item or {}).get("tweet_id", ""))
            if not tweet_id:
                continue
            if tweet_id not in merged:
                merged[tweet_id] = dict(item or {})
    return sort_items_by_created_at(list(merged.values()))


def format_seconds_suffix(label, seconds):
    if seconds is None:
        return ""
    return f"\uff08{label}{int(seconds)}\u79d2\uff09"


def clamp_int(value, default, minimum=None, maximum=None):
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = int(default)
    if minimum is not None:
        out = max(int(minimum), out)
    if maximum is not None:
        out = min(int(maximum), out)
    return out


def clamp_float(value, default, minimum=None, maximum=None):
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = float(default)
    if minimum is not None:
        out = max(float(minimum), out)
    if maximum is not None:
        out = min(float(maximum), out)
    return out


def config_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def parse_discord_defaults():
    if not str(DISCORD_DEFAULTS_SOURCE) or not DISCORD_DEFAULTS_SOURCE.is_file():
        return {}
    text = DISCORD_DEFAULTS_SOURCE.read_text(encoding="utf-8", errors="replace")
    out = {}
    channel_match = re.search(r'CHANNEL_ID\s*=\s*"([^"]+)"', text)
    token_match = re.search(r'(?:DISCORD_BOT_TOKEN|X_MONITORPLUS_DISCORD_BOT_TOKEN)\s*=\s*"([^"]+)"', text)
    if channel_match:
        out["discord_channel_id"] = channel_match.group(1).strip()
    if token_match:
        out["discord_bot_token"] = token_match.group(1).strip()
    return out


def load_legacy_x_monitor_defaults_details():
    if not LEGACY_X_MONITOR_CONFIG.exists():
        return {
            "defaults": {},
            "parse_error": "",
            "config_exists": False,
            "config_path": str(LEGACY_X_MONITOR_CONFIG),
        }
    try:
        payload = json.loads(LEGACY_X_MONITOR_CONFIG.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "defaults": {},
            "parse_error": compact_error_text(f"{type(exc).__name__}: {exc}", limit=280),
            "config_exists": True,
            "config_path": str(LEGACY_X_MONITOR_CONFIG),
        }
    keys = (
        "editor_draft_api_base",
        "editor_draft_api_key",
        "editor_draft_model",
        "editor_draft_proxy",
        "editor_draft_custom_headers_json",
        "editor_draft_fallback_api_base",
        "editor_draft_fallback_api_key",
        "editor_draft_fallback_model",
        "editor_draft_fallback_proxy",
        "editor_draft_fallback_custom_headers_json",
        "x_proxy",
    )
    out = {}
    for key in keys:
        value = clean_text(payload.get(key, ""))
        if value:
            out[key] = value
    return {
        "defaults": out,
        "parse_error": "",
        "config_exists": True,
        "config_path": str(LEGACY_X_MONITOR_CONFIG),
    }


def load_legacy_x_monitor_defaults():
    return load_legacy_x_monitor_defaults_details()["defaults"]


def normalize_proxy_url(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if "=" in text and ";" in text:
        parts = {}
        for item in text.split(";"):
            if "=" in item:
                key, raw_value = item.split("=", 1)
                parts[key.strip().lower()] = raw_value.strip()
        text = parts.get("https") or parts.get("http") or ""
    if not text:
        return ""
    if "://" not in text:
        text = f"http://{text}"
    return text


def is_disabled_proxy_url(value):
    text = normalize_proxy_url(value)
    return text in {"http://127.0.0.1:9", "http://localhost:9"}


def discover_proxy_url():
    for key in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        value = normalize_proxy_url(os.environ.get(key, ""))
        if value and not is_disabled_proxy_url(value):
            return value
    if os.name != "nt" or winreg is None:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
            enabled = int(winreg.QueryValueEx(key, "ProxyEnable")[0])
            if not enabled:
                return ""
            value = normalize_proxy_url(winreg.QueryValueEx(key, "ProxyServer")[0])
            return "" if is_disabled_proxy_url(value) else value
    except Exception:
        return ""


def requests_proxies(config, for_editor=False, proxy_key=""):
    key = clean_text(proxy_key)
    if key:
        proxy_value = clean_text(config.get(key, ""))
        if not proxy_value and for_editor and key != "editor_draft_proxy":
            proxy_value = clean_text(config.get("editor_draft_proxy", ""))
    else:
        proxy_value = clean_text(config.get("editor_draft_proxy" if for_editor else "x_proxy", ""))
    if not proxy_value and for_editor:
        proxy_value = clean_text(config.get("x_proxy", ""))
    if not proxy_value:
        return {"http": None, "https": None}
    return {"http": proxy_value, "https": proxy_value}


def sanitize_proxy_environment():
    proxy_url = discover_proxy_url()
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        if proxy_url:
            os.environ[key] = proxy_url
        else:
            os.environ.pop(key, None)


def base_config():
    return {
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "source_slot": DEFAULT_SOURCE_SLOT,
        "x_home_enabled": True,
        "x_home_url": "https://x.com/home",
        "x_list_enabled": False,
        "x_list_url": "",
        "x_lists": [],
        "watch_interval_seconds": DEFAULT_WATCH_INTERVAL_SECONDS,
        "reload_interval_seconds": DEFAULT_RELOAD_INTERVAL_SECONDS,
        "target_check_jitter_milliseconds": DEFAULT_TARGET_CHECK_JITTER_MILLISECONDS,
        "reload_interval_jitter_seconds": DEFAULT_RELOAD_INTERVAL_JITTER_SECONDS,
        "page_timeout_ms": DEFAULT_PAGE_TIMEOUT_MS,
        "page_settle_milliseconds": DEFAULT_SETTLE_MILLISECONDS,
        "empty_page_retry_count": DEFAULT_EMPTY_PAGE_RETRY_COUNT,
        "empty_page_retry_delay_milliseconds": DEFAULT_EMPTY_PAGE_RETRY_DELAY_MILLISECONDS,
        "empty_page_recovery_settle_milliseconds": DEFAULT_EMPTY_PAGE_RECOVERY_SETTLE_MILLISECONDS,
        "empty_page_priority_recheck_count": DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_COUNT,
        "empty_page_priority_recheck_delay_milliseconds": DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_DELAY_MILLISECONDS,
        "empty_page_restart_threshold": DEFAULT_EMPTY_PAGE_RESTART_THRESHOLD,
        "multi_target_empty_page_restart_threshold": DEFAULT_MULTI_TARGET_EMPTY_PAGE_RESTART_THRESHOLD,
        "empty_page_fast_reopen_restart_threshold": DEFAULT_EMPTY_PAGE_FAST_REOPEN_RESTART_THRESHOLD,
        "empty_page_wave_recovery_cooldown_seconds": DEFAULT_EMPTY_PAGE_WAVE_RECOVERY_COOLDOWN_SECONDS,
        "empty_page_wave_canary_enabled": DEFAULT_EMPTY_PAGE_WAVE_CANARY_ENABLED,
        "empty_page_wave_canary_wait_milliseconds": DEFAULT_EMPTY_PAGE_WAVE_CANARY_WAIT_MILLISECONDS,
        "partial_page_min_visible_count": DEFAULT_PARTIAL_PAGE_MIN_VISIBLE_COUNT,
        "top_scan_count": DEFAULT_TOP_SCAN_COUNT,
        "max_seen_ids": DEFAULT_MAX_SEEN_IDS,
        "max_delivery_delay_seconds": DEFAULT_MAX_DELIVERY_DELAY_SECONDS,
        "late_new_item_recovery_delay_seconds": DEFAULT_LATE_NEW_ITEM_RECOVERY_DELAY_SECONDS,
        "stale_refresh_enabled": DEFAULT_STALE_REFRESH_ENABLED,
        "stale_refresh_top_delay_seconds": DEFAULT_STALE_REFRESH_TOP_DELAY_SECONDS,
        "stale_refresh_unchanged_count": DEFAULT_STALE_REFRESH_UNCHANGED_COUNT,
        "stale_refresh_cooldown_seconds": DEFAULT_STALE_REFRESH_COOLDOWN_SECONDS,
        "stale_refresh_light_scroll_recheck_enabled": DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_ENABLED,
        "stale_refresh_light_scroll_recheck_attempts": DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_ATTEMPTS,
        "stale_refresh_light_scroll_recheck_settle_milliseconds": DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_SETTLE_MILLISECONDS,
        "stale_refresh_light_scroll_recheck_step_pixels": DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_STEP_PIXELS,
        "hot_list_acceleration_enabled": DEFAULT_HOT_LIST_ACCELERATION_ENABLED,
        "hot_list_acceleration_seconds": DEFAULT_HOT_LIST_ACCELERATION_SECONDS,
        "hot_list_stale_top_delay_seconds": DEFAULT_HOT_LIST_STALE_TOP_DELAY_SECONDS,
        "hot_list_stale_unchanged_count": DEFAULT_HOT_LIST_STALE_UNCHANGED_COUNT,
        "hot_list_stale_cooldown_seconds": DEFAULT_HOT_LIST_STALE_COOLDOWN_SECONDS,
        "hot_list_slow_delivery_threshold_seconds": DEFAULT_HOT_LIST_SLOW_DELIVERY_THRESHOLD_SECONDS,
        "slow_attribution_threshold_seconds": DEFAULT_SLOW_ATTRIBUTION_THRESHOLD_SECONDS,
        "restart_gap_replay_seconds": DEFAULT_RESTART_GAP_REPLAY_SECONDS,
        "slot_intervention_alert_cooldown_seconds": DEFAULT_SLOT_INTERVENTION_ALERT_COOLDOWN_SECONDS,
        "browser_crash_auto_restart_enabled": DEFAULT_BROWSER_CRASH_AUTO_RESTART_ENABLED,
        "browser_crash_auto_restart_cooldown_seconds": DEFAULT_BROWSER_CRASH_AUTO_RESTART_COOLDOWN_SECONDS,
        "browser_lightweight_mode": DEFAULT_BROWSER_LIGHTWEIGHT_MODE,
        "browser_disable_images": DEFAULT_BROWSER_DISABLE_IMAGES,
        "browser_headless": True,
        "browser_channel": "auto",
        "x_browser_profile_dir": str(DEFAULT_BROWSER_PROFILE_DIR),
        "x_cookies_path": str(LEGACY_X_MONITOR_COOKIES),
        "x_proxy": "",
        "translate_to": DEFAULT_TRANSLATE_TO,
        "output_sinks": ["discord"],
        "discord_channel_id": "",
        "discord_bot_token": "",
        "discord_request_timeout_seconds": DEFAULT_DISCORD_REQUEST_TIMEOUT_SECONDS,
        "discord_transient_retry_count": DEFAULT_DISCORD_TRANSIENT_RETRY_COUNT,
        "discord_transient_retry_delay_milliseconds": DEFAULT_DISCORD_TRANSIENT_RETRY_DELAY_MILLISECONDS,
        "durable_seen_enabled": DEFAULT_DURABLE_SEEN_ENABLED,
        "durable_seen_retention_seconds": DEFAULT_DURABLE_SEEN_RETENTION_SECONDS,
        "max_durable_seen_ids": DEFAULT_MAX_DURABLE_SEEN_IDS,
        "local_fast_translation_enabled": DEFAULT_LOCAL_FAST_TRANSLATION_ENABLED,
        "local_fast_translation_api_base": "",
        "local_fast_translation_api_key": "",
        "local_fast_translation_model": "",
        "local_fast_translation_timeout_seconds": DEFAULT_LOCAL_FAST_TRANSLATION_TIMEOUT_SECONDS,
        "local_fast_translation_initial_timeout_seconds": DEFAULT_INITIAL_LOCAL_FAST_TRANSLATION_TIMEOUT_SECONDS,
        "local_fast_translation_initial_failure_cooldown_seconds": DEFAULT_LOCAL_FAST_TRANSLATION_INITIAL_FAILURE_COOLDOWN_SECONDS,
        "local_fast_translation_proxy": "",
        "local_fast_translation_custom_headers_json": "",
        "editor_draft_enabled": DEFAULT_EDITOR_DRAFT_ENABLED,
        "async_enrich_max_workers": DEFAULT_ASYNC_ENRICH_MAX_WORKERS,
        "editor_draft_timeout_seconds": DEFAULT_EDITOR_DRAFT_TIMEOUT_SECONDS,
        "editor_draft_min_interval_seconds": DEFAULT_EDITOR_DRAFT_MIN_INTERVAL_SECONDS,
        "editor_draft_rate_limit_cooldown_seconds": DEFAULT_EDITOR_DRAFT_RATE_LIMIT_COOLDOWN_SECONDS,
        "editor_draft_transient_retry_count": DEFAULT_EDITOR_DRAFT_TRANSIENT_RETRY_COUNT,
        "editor_draft_transient_retry_delay_milliseconds": DEFAULT_EDITOR_DRAFT_TRANSIENT_RETRY_DELAY_MILLISECONDS,
        "editor_draft_api_base": "",
        "editor_draft_api_key": "",
        "editor_draft_model": "",
        "editor_draft_proxy": "",
        "editor_draft_custom_headers_json": "",
        "editor_draft_fallback_api_base": "",
        "editor_draft_fallback_api_key": "",
        "editor_draft_fallback_model": "",
        "editor_draft_fallback_proxy": "",
        "editor_draft_fallback_custom_headers_json": "",
    }


def base_state():
    return {
        "recent_events": [],
        "recent_checks": [],
        "last_error": "",
        "last_service_start_at": "",
        "last_service_stop_at": "",
        "last_successful_check_at": "",
        "last_reload_at": "",
        "service_pid": 0,
        "service_heartbeat_at": "",
        "current_top_tweet_id": "",
        "current_top_url": "",
        "auth_ready": False,
        "auth_error": "",
        "bootstrapped": False,
        "seen_ids": {},
        "targets": {},
        "source_slot": DEFAULT_SOURCE_SLOT,
        "slot_operator_action_required": False,
        "slot_operator_action_required_at": "",
        "slot_operator_action_required_kind": "",
        "slot_operator_action_required_error": "",
        "last_slot_operator_alert_at": "",
        "last_slot_operator_alert_kind": "",
        "last_slot_operator_alert_error": "",
        "last_slot_operator_action_cleared_at": "",
        "last_auto_restart_at": "",
        "last_auto_restart_kind": "",
        "last_auto_restart_error": "",
        "auto_restart_count": 0,
        "last_auto_restart_result": "",
        "editor_draft_last_request_at": "",
        "editor_draft_cooldown_until": "",
        "editor_draft_last_error": "",
        "state_last_recovery_at": "",
        "state_last_recovery_error": "",
        "state_last_recovery_backup_path": "",
    }


def base_target_state():
    return {
        "auth_ready": False,
        "auth_error": "",
        "bootstrapped": False,
        "current_top_tweet_id": "",
        "current_top_url": "",
        "last_successful_check_at": "",
        "last_reload_at": "",
        "last_error": "",
        "hot_list_acceleration_until": "",
        "hot_list_acceleration_reason": "",
        "hot_list_acceleration_delay_seconds": None,
    }


def normalize_mode(value):
    text = clean_text(value).lower()
    if text in {MODE_HOME, "recommend", "recommended", "home", "homepage", "timeline", "feed", "推荐", "首页"}:
        return MODE_HOME
    if text in {MODE_LIST, "list", "lists", "列表", "清单"}:
        return MODE_LIST
    return ""


def mode_label(mode):
    normalized = normalize_mode(mode)
    return MODE_LABELS.get(normalized, normalized or "未知")


def ensure_target_states(payload):
    targets = payload.get("targets", {})
    if not isinstance(targets, dict):
        targets = {}
    merged_targets = {}
    for key, existing in targets.items():
        target_id = target_key(key)
        if not target_id:
            continue
        if not isinstance(existing, dict):
            existing = {}
        merged = base_target_state()
        merged.update(existing)
        merged_targets[target_id] = merged
    if MODE_HOME not in merged_targets:
        merged = base_target_state()
        for key in ("auth_ready", "auth_error", "bootstrapped", "current_top_tweet_id", "current_top_url", "last_successful_check_at", "last_reload_at", "last_error"):
            if key in payload:
                merged[key] = payload.get(key, merged.get(key))
        merged_targets[MODE_HOME] = merged
    if MODE_LIST in targets and list_target_key(1) not in merged_targets:
        legacy_list = targets.get(MODE_LIST, {})
        if isinstance(legacy_list, dict):
            merged = base_target_state()
            merged.update(legacy_list)
            merged_targets[list_target_key(1)] = merged
    payload["targets"] = merged_targets
    return payload


def enabled_targets(config):
    targets = []
    if config_bool(config.get("x_home_enabled", True), True):
        targets.append(
            {
                "key": MODE_HOME,
                "mode": MODE_HOME,
                "label": mode_label(MODE_HOME),
                "url": clean_text(config.get("x_home_url", "")) or "https://x.com/home",
            }
        )
    for index, entry in enumerate(normalize_list_configs(config), start=1):
        if not (bool(entry.get("enabled", False)) and clean_text(entry.get("url", ""))):
            continue
        targets.append(
            {
                "key": list_target_key(index),
                "mode": MODE_LIST,
                "label": clean_text(entry.get("name", "")) or f"列表{index}",
                "name": clean_text(entry.get("name", "")) or f"列表{index}",
                "url": clean_text(entry.get("url", "")),
                "list_index": index,
                "max_delivery_delay_seconds": entry.get("max_delivery_delay_seconds", ""),
                "late_new_item_recovery_delay_seconds": entry.get("late_new_item_recovery_delay_seconds", ""),
                "stale_refresh_enabled": entry.get("stale_refresh_enabled", ""),
                "stale_refresh_top_delay_seconds": entry.get("stale_refresh_top_delay_seconds", ""),
                "stale_refresh_unchanged_count": entry.get("stale_refresh_unchanged_count", ""),
                "stale_refresh_cooldown_seconds": entry.get("stale_refresh_cooldown_seconds", ""),
            }
        )
    return targets


def enabled_mode_names(config):
    return list(dict.fromkeys(target_mode(target) for target in enabled_targets(config) if target_mode(target)))


def runtime_signature(config):
    targets = enabled_targets(config)
    return {
        "source_slot": normalize_source_slot(config.get("source_slot", DEFAULT_SOURCE_SLOT)),
        "profile_dir": clean_text(config.get("x_browser_profile_dir", "")),
        "cookies_path": clean_text(config.get("x_cookies_path", "")),
        "targets": [(target_key(target), clean_text(target.get("url", ""))) for target in targets],
    }


def slot_intervention_cooldown_seconds(config):
    return clamp_int(
        config.get(
            "slot_intervention_alert_cooldown_seconds",
            DEFAULT_SLOT_INTERVENTION_ALERT_COOLDOWN_SECONDS,
        ),
        DEFAULT_SLOT_INTERVENTION_ALERT_COOLDOWN_SECONDS,
        minimum=300,
        maximum=24 * 3600,
    )


def browser_crash_auto_restart_enabled(config):
    return config_bool(
        config.get("browser_crash_auto_restart_enabled", DEFAULT_BROWSER_CRASH_AUTO_RESTART_ENABLED),
        DEFAULT_BROWSER_CRASH_AUTO_RESTART_ENABLED,
    )


def browser_crash_auto_restart_cooldown_seconds(config):
    return clamp_int(
        config.get(
            "browser_crash_auto_restart_cooldown_seconds",
            DEFAULT_BROWSER_CRASH_AUTO_RESTART_COOLDOWN_SECONDS,
        ),
        DEFAULT_BROWSER_CRASH_AUTO_RESTART_COOLDOWN_SECONDS,
        minimum=30,
        maximum=24 * 3600,
    )


def max_delivery_delay_seconds(config, target=None):
    target_value = None
    if isinstance(target, dict):
        target_value = target.get("max_delivery_delay_seconds")
    raw_value = target_value
    if raw_value in (None, ""):
        raw_value = (config or {}).get("max_delivery_delay_seconds", DEFAULT_MAX_DELIVERY_DELAY_SECONDS)
    return clamp_int(raw_value, DEFAULT_MAX_DELIVERY_DELAY_SECONDS, minimum=0, maximum=24 * 3600)


def stale_backfill_delay_seconds(item, observed_at):
    return elapsed_seconds_between((item or {}).get("created_at", ""), observed_at)


def should_suppress_stale_backfill(item, observed_at, config, target=None):
    maximum_delay = max_delivery_delay_seconds(config, target)
    if maximum_delay <= 0:
        return False
    delay_seconds = stale_backfill_delay_seconds(item, observed_at)
    if delay_seconds is None:
        return False
    return delay_seconds > maximum_delay


def late_new_item_recovery_delay_seconds(config, target=None):
    target_value = None
    if isinstance(target, dict):
        target_value = target.get("late_new_item_recovery_delay_seconds")
    raw_value = target_value
    if raw_value in (None, ""):
        raw_value = (config or {}).get(
            "late_new_item_recovery_delay_seconds",
            DEFAULT_LATE_NEW_ITEM_RECOVERY_DELAY_SECONDS,
        )
    return clamp_int(
        raw_value,
        DEFAULT_LATE_NEW_ITEM_RECOVERY_DELAY_SECONDS,
        minimum=0,
        maximum=24 * 3600,
    )


def late_unseen_items_for_recovery(state, config, target, items, observed_at, store=None):
    threshold_seconds = late_new_item_recovery_delay_seconds(config, target)
    if threshold_seconds <= 0:
        return []
    state_value = state or {}
    seen = combined_seen_ids(store, config, state_value, observed_at=observed_at) if store is not None else dict(state_value.get("seen_ids", {}))
    service_start_at = clean_text(state_value.get("last_service_start_at", ""))
    late_items = []
    for item in list(items or []):
        tweet_id = clean_text((item or {}).get("tweet_id", ""))
        if not tweet_id or tweet_id in seen:
            continue
        if item_is_filtered_repost(item) or bool((item or {}).get("is_teaser")):
            continue
        if item_should_baseline_on_start(item, service_start_at, config):
            continue
        delay_seconds = elapsed_seconds_between((item or {}).get("created_at", ""), observed_at)
        if delay_seconds is not None and delay_seconds >= threshold_seconds:
            late_items.append(dict(item))
    return late_items


def stale_refresh_enabled(config, target=None):
    target_value = target or {}
    target_enabled = None
    if isinstance(target_value, dict):
        if "stale_refresh_enabled" in target_value:
            target_enabled = target_value.get("stale_refresh_enabled")
        elif "priority_stale_refresh_enabled" in target_value:
            target_enabled = target_value.get("priority_stale_refresh_enabled")
    if not config_bool(
        (config or {}).get(
            "stale_refresh_enabled",
            (config or {}).get("priority_stale_refresh_enabled", DEFAULT_STALE_REFRESH_ENABLED),
        ),
        DEFAULT_STALE_REFRESH_ENABLED,
    ):
        return False
    if target_mode(target) != MODE_LIST:
        return False
    if target_enabled is not None:
        return config_bool(target_enabled, True)
    return True


def stale_refresh_top_delay_seconds(config, target=None):
    target_value = None
    if isinstance(target, dict):
        target_value = target.get("stale_refresh_top_delay_seconds")
        if target_value in (None, ""):
            target_value = target.get("priority_stale_refresh_top_delay_seconds")
    raw_value = target_value
    if raw_value in (None, ""):
        raw_value = (config or {}).get(
            "stale_refresh_top_delay_seconds",
            (config or {}).get("priority_stale_refresh_top_delay_seconds", DEFAULT_STALE_REFRESH_TOP_DELAY_SECONDS),
        )
    return clamp_int(
        raw_value,
        DEFAULT_STALE_REFRESH_TOP_DELAY_SECONDS,
        minimum=15,
        maximum=3600,
    )


def stale_refresh_unchanged_count(config, target=None):
    target_value = None
    if isinstance(target, dict):
        target_value = target.get("stale_refresh_unchanged_count")
        if target_value in (None, ""):
            target_value = target.get("priority_stale_refresh_unchanged_count")
    raw_value = target_value
    if raw_value in (None, ""):
        raw_value = (config or {}).get(
            "stale_refresh_unchanged_count",
            (config or {}).get("priority_stale_refresh_unchanged_count", DEFAULT_STALE_REFRESH_UNCHANGED_COUNT),
        )
    return clamp_int(
        raw_value,
        DEFAULT_STALE_REFRESH_UNCHANGED_COUNT,
        minimum=2,
        maximum=60,
    )


def stale_refresh_cooldown_seconds(config, target=None):
    target_value = None
    if isinstance(target, dict):
        target_value = target.get("stale_refresh_cooldown_seconds")
        if target_value in (None, ""):
            target_value = target.get("priority_stale_refresh_cooldown_seconds")
    raw_value = target_value
    if raw_value in (None, ""):
        raw_value = (config or {}).get(
            "stale_refresh_cooldown_seconds",
            (config or {}).get("priority_stale_refresh_cooldown_seconds", DEFAULT_STALE_REFRESH_COOLDOWN_SECONDS),
        )
    return clamp_int(
        raw_value,
        DEFAULT_STALE_REFRESH_COOLDOWN_SECONDS,
        minimum=15,
        maximum=3600,
    )


def stale_refresh_light_scroll_recheck_enabled(config):
    return config_bool(
        (config or {}).get(
            "stale_refresh_light_scroll_recheck_enabled",
            DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_ENABLED,
        ),
        DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_ENABLED,
    )


def stale_refresh_light_scroll_recheck_settings(config):
    return {
        "attempts": clamp_int(
            (config or {}).get(
                "stale_refresh_light_scroll_recheck_attempts",
                DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_ATTEMPTS,
            ),
            DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_ATTEMPTS,
            minimum=0,
            maximum=3,
        ),
        "settle_milliseconds": clamp_int(
            (config or {}).get(
                "stale_refresh_light_scroll_recheck_settle_milliseconds",
                DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_SETTLE_MILLISECONDS,
            ),
            DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_SETTLE_MILLISECONDS,
            minimum=200,
            maximum=3000,
        ),
        "step_pixels": clamp_int(
            (config or {}).get(
                "stale_refresh_light_scroll_recheck_step_pixels",
                DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_STEP_PIXELS,
            ),
            DEFAULT_STALE_REFRESH_LIGHT_SCROLL_RECHECK_STEP_PIXELS,
            minimum=300,
            maximum=2000,
        ),
    }


def hot_list_acceleration_enabled(config):
    return config_bool(
        (config or {}).get("hot_list_acceleration_enabled", DEFAULT_HOT_LIST_ACCELERATION_ENABLED),
        DEFAULT_HOT_LIST_ACCELERATION_ENABLED,
    )


def hot_list_acceleration_seconds(config):
    return clamp_int(
        (config or {}).get("hot_list_acceleration_seconds", DEFAULT_HOT_LIST_ACCELERATION_SECONDS),
        DEFAULT_HOT_LIST_ACCELERATION_SECONDS,
        minimum=60,
        maximum=3600,
    )


def hot_list_slow_delivery_threshold_seconds(config):
    return clamp_int(
        (config or {}).get("hot_list_slow_delivery_threshold_seconds", DEFAULT_HOT_LIST_SLOW_DELIVERY_THRESHOLD_SECONDS),
        DEFAULT_HOT_LIST_SLOW_DELIVERY_THRESHOLD_SECONDS,
        minimum=15,
        maximum=3600,
    )


def slow_attribution_threshold_seconds(config):
    return clamp_int(
        (config or {}).get("slow_attribution_threshold_seconds", DEFAULT_SLOW_ATTRIBUTION_THRESHOLD_SECONDS),
        DEFAULT_SLOW_ATTRIBUTION_THRESHOLD_SECONDS,
        minimum=15,
        maximum=3600,
    )


def hot_list_stale_thresholds(config):
    return {
        "top_delay_seconds": clamp_int(
            (config or {}).get("hot_list_stale_top_delay_seconds", DEFAULT_HOT_LIST_STALE_TOP_DELAY_SECONDS),
            DEFAULT_HOT_LIST_STALE_TOP_DELAY_SECONDS,
            minimum=15,
            maximum=3600,
        ),
        "unchanged_count": clamp_int(
            (config or {}).get("hot_list_stale_unchanged_count", DEFAULT_HOT_LIST_STALE_UNCHANGED_COUNT),
            DEFAULT_HOT_LIST_STALE_UNCHANGED_COUNT,
            minimum=2,
            maximum=60,
        ),
        "cooldown_seconds": clamp_int(
            (config or {}).get("hot_list_stale_cooldown_seconds", DEFAULT_HOT_LIST_STALE_COOLDOWN_SECONDS),
            DEFAULT_HOT_LIST_STALE_COOLDOWN_SECONDS,
            minimum=15,
            maximum=3600,
        ),
    }


def activate_hot_list_acceleration(store, target_id, config, observed_at, reason, delay_seconds=None):
    if not hot_list_acceleration_enabled(config):
        return {}
    target_ref = target_key(target_id)
    if not target_ref:
        return {}
    observed_dt = parse_iso_datetime(observed_at) or now_utc()
    until = observed_dt + timedelta(seconds=hot_list_acceleration_seconds(config))
    until_text = until.isoformat()

    def updater(state):
        target_state = base_target_state()
        target_state.update(dict(state.get("targets", {}).get(target_ref, {})))
        target_state["hot_list_acceleration_until"] = until_text
        target_state["hot_list_acceleration_reason"] = clean_text(reason)
        target_state["hot_list_acceleration_delay_seconds"] = delay_seconds
        state["targets"][target_ref] = target_state
        return {
            "hot_list_acceleration": True,
            "hot_list_acceleration_until": until_text,
            "hot_list_acceleration_reason": clean_text(reason),
            "hot_list_acceleration_delay_seconds": delay_seconds,
        }

    return store.update_state(updater) or {}


def hot_list_acceleration_state(target_state, observed_at):
    observed_dt = parse_iso_datetime(observed_at) or now_utc()
    until_dt = parse_iso_datetime((target_state or {}).get("hot_list_acceleration_until", ""))
    if until_dt is None or until_dt <= observed_dt:
        return {}
    return {
        "hot_list_acceleration": True,
        "hot_list_acceleration_until": until_dt.isoformat(),
        "hot_list_acceleration_reason": clean_text((target_state or {}).get("hot_list_acceleration_reason", "")),
        "hot_list_acceleration_delay_seconds": (target_state or {}).get("hot_list_acceleration_delay_seconds"),
    }


def stale_refresh_state_update(store, target_id, check, config, target, observed_at):
    if not stale_refresh_enabled(config, target):
        return {"should_refresh": False, "reason": "not_priority"}
    top_id = clean_text((check or {}).get("current_top_tweet_id", ""))
    if not top_id:
        return {"should_refresh": False, "reason": "missing_top"}
    top_delay = (check or {}).get("top_delay_seconds")
    if top_delay is None:
        return {"should_refresh": False, "reason": "missing_top_delay"}
    top_delay_threshold = stale_refresh_top_delay_seconds(config, target)
    unchanged_threshold = stale_refresh_unchanged_count(config, target)
    cooldown_seconds = stale_refresh_cooldown_seconds(config, target)

    def updater(state):
        target_state = base_target_state()
        target_state.update(dict(state.get("targets", {}).get(target_id, {})))
        hot_enabled = hot_list_acceleration_enabled(config)
        hot_state = hot_list_acceleration_state(target_state, observed_at) if hot_enabled else {}
        if not hot_enabled:
            target_state["hot_list_acceleration_until"] = ""
            target_state["hot_list_acceleration_reason"] = ""
            target_state["hot_list_acceleration_delay_seconds"] = None
        active_top_delay_threshold = top_delay_threshold
        active_unchanged_threshold = unchanged_threshold
        active_cooldown_seconds = cooldown_seconds
        if hot_state:
            hot_thresholds = hot_list_stale_thresholds(config)
            active_top_delay_threshold = min(active_top_delay_threshold, hot_thresholds["top_delay_seconds"])
            active_unchanged_threshold = min(active_unchanged_threshold, hot_thresholds["unchanged_count"])
            active_cooldown_seconds = min(active_cooldown_seconds, hot_thresholds["cooldown_seconds"])
        previous_top_id = clean_text(target_state.get("stale_refresh_top_tweet_id", ""))
        unchanged_count = int(target_state.get("stale_refresh_unchanged_count", 0) or 0)
        if previous_top_id == top_id:
            unchanged_count += 1
        else:
            unchanged_count = 1
            target_state["stale_refresh_trigger_count"] = 0
        target_state["stale_refresh_top_tweet_id"] = top_id
        target_state["stale_refresh_unchanged_count"] = unchanged_count
        last_refresh_at = clean_text(target_state.get("stale_refresh_last_at", ""))
        cooldown_age = elapsed_seconds_between(last_refresh_at, observed_at)
        cooldown_ready = not last_refresh_at or cooldown_age is None or cooldown_age >= active_cooldown_seconds
        should_refresh = top_delay >= active_top_delay_threshold and unchanged_count >= active_unchanged_threshold and cooldown_ready
        trigger_count = int(target_state.get("stale_refresh_trigger_count", 0) or 0)
        if should_refresh:
            trigger_count += 1
            target_state["stale_refresh_trigger_count"] = trigger_count
            target_state["stale_refresh_last_at"] = observed_at
        state["targets"][target_id] = target_state
        return {
            "should_refresh": should_refresh,
            "recovery_method": "full_reload" if trigger_count >= 2 else "fast_reopen",
            "trigger_count": trigger_count,
            "top_delay_seconds": int(top_delay),
            "top_delay_threshold_seconds": active_top_delay_threshold,
            "unchanged_count": unchanged_count,
            "unchanged_threshold": active_unchanged_threshold,
            "cooldown_seconds": active_cooldown_seconds,
            "cooldown_age_seconds": cooldown_age,
            "last_refresh_at": last_refresh_at,
            **hot_state,
        }

    return store.update_state(updater)


class Store:
    def __init__(self, root=None):
        self.root = Path(root or DEFAULT_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)
        self.config_path = self.root / "config.json"
        self.state_path = self.root / "state.json"
        self.state_lock_path = self.root / "state.write.lock"
        self.pid_path = self.root / "service.pid"
        self.lock_path = self.root / "service.lock"
        self.log_path = self.root / "service.log"
        self.event_archive_path = self.root / EVENT_ARCHIVE_FILENAME
        self.check_archive_path = self.root / CHECK_ARCHIVE_FILENAME
        self.seen_archive_path = self.root / SEEN_ARCHIVE_FILENAME
        self.event_archive_lock_path = self.root / f"{EVENT_ARCHIVE_FILENAME}.write.lock"
        self._state_thread_lock = threading.RLock()
        self._event_archive_thread_lock = threading.RLock()
        self._state_guard_depth = 0
        self._event_archive_guard_depth = 0
        self._ensure()

    def _ensure(self):
        if not self.config_path.exists():
            self.save_config(base_config())
        if not self.state_path.exists():
            self.save_state(base_state())

    def _normalize_state_payload(self, payload, parse_error=""):
        payload = ensure_target_states(payload)
        payload["recent_events"] = list(payload.get("recent_events", []))
        payload["recent_checks"] = list(payload.get("recent_checks", []))
        payload["seen_ids"] = dict(payload.get("seen_ids", {}))
        payload[STATE_PARSE_ERROR_KEY] = clean_text(parse_error)
        return payload

    def _repair_state_details(self, details):
        parse_error = clean_text((details or {}).get("parse_error", ""))
        recovery_error = parse_error
        backup_path = ""
        if self.state_path.exists():
            backup_target = self.state_path.with_name(f"{self.state_path.stem}.invalid.{timestamp_token()}{self.state_path.suffix}.bak")
            try:
                backup_target.write_bytes(self.state_path.read_bytes())
                backup_path = str(backup_target)
            except Exception as exc:
                backup_error = compact_error_text(f"{type(exc).__name__}: {exc}", limit=180)
                recovery_error = compact_error_text(f"{parse_error}; backup_failed: {backup_error}", limit=500)
        repaired_state = base_state()
        repaired_state["state_last_recovery_at"] = iso_now()
        repaired_state["state_last_recovery_error"] = recovery_error
        repaired_state["state_last_recovery_backup_path"] = backup_path
        snapshot = self._prepare_state_snapshot(repaired_state)
        self._write_state_snapshot(snapshot)
        normalized = self._normalize_state_payload(snapshot, parse_error="")
        return {
            "state": normalized,
            "parse_error": "",
            "state_exists": True,
            "state_path": str(self.state_path),
            "repaired": True,
            "repaired_parse_error": parse_error,
            "repair_backup_path": backup_path,
        }

    def load_state_details(self, repair=True):
        payload = base_state()
        parse_error = ""
        try:
            payload.update(json.loads(self.state_path.read_text(encoding="utf-8")))
        except Exception as exc:
            parse_error = compact_error_text(f"{type(exc).__name__}: {exc}", limit=280)
        normalized = self._normalize_state_payload(payload, parse_error=parse_error)
        details = {
            "state": normalized,
            "parse_error": parse_error,
            "state_exists": self.state_path.exists(),
            "state_path": str(self.state_path),
            "repaired": False,
            "repaired_parse_error": "",
            "repair_backup_path": "",
        }
        if repair and parse_error:
            return self._repair_state_details(details)
        return details

    def _load_state_payload(self):
        return self.load_state_details(repair=True)["state"]

    def _prepare_state_snapshot(self, payload):
        snapshot = base_state()
        snapshot.update(payload or {})
        snapshot.pop(STATE_PARSE_ERROR_KEY, None)
        snapshot = ensure_target_states(snapshot)
        snapshot["recent_events"] = list(snapshot.get("recent_events", []))[-DEFAULT_RECENT_EVENTS_LIMIT:]
        snapshot["recent_checks"] = list(snapshot.get("recent_checks", []))[-DEFAULT_RECENT_CHECKS_LIMIT:]
        snapshot["seen_ids"] = trim_seen_ids(dict(snapshot.get("seen_ids", {})), DEFAULT_MAX_SEEN_IDS)
        return snapshot

    def _write_state_snapshot(self, snapshot):
        atomic_write_text(self.state_path, json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    def _acquire_state_guard(self, timeout_seconds=10):
        current_pid = os.getpid()
        if self._state_guard_depth > 0:
            self._state_guard_depth += 1
            return
        deadline = time.time() + max(1.0, float(timeout_seconds))
        while True:
            try:
                fd = os.open(str(self.state_lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, str(current_pid).encode("utf-8"))
                finally:
                    os.close(fd)
                self._state_guard_depth = 1
                return
            except FileExistsError:
                existing_pid = 0
                try:
                    existing_pid = int(self.state_lock_path.read_text(encoding="utf-8").strip() or "0")
                except Exception:
                    existing_pid = 0
                if existing_pid == current_pid:
                    self._state_guard_depth = 1
                    return
                if existing_pid and is_process_running(existing_pid):
                    if time.time() >= deadline:
                        raise TimeoutError("state_write_lock_timeout")
                    time.sleep(0.05)
                    continue
                try:
                    self.state_lock_path.unlink()
                except FileNotFoundError:
                    pass
                except Exception:
                    if time.time() >= deadline:
                        raise TimeoutError("state_write_lock_timeout")
                    time.sleep(0.05)

    def _release_state_guard(self):
        if self._state_guard_depth <= 0:
            return
        if self._state_guard_depth > 1:
            self._state_guard_depth -= 1
            return
        self._state_guard_depth = 0
        current_pid = os.getpid()
        existing_pid = 0
        try:
            existing_pid = int(self.state_lock_path.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            existing_pid = 0
        if existing_pid and existing_pid != current_pid and is_process_running(existing_pid):
            return
        try:
            self.state_lock_path.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def _acquire_event_archive_guard(self, timeout_seconds=10):
        current_pid = os.getpid()
        if self._event_archive_guard_depth > 0:
            self._event_archive_guard_depth += 1
            return
        deadline = time.time() + max(1.0, float(timeout_seconds))
        while True:
            try:
                fd = os.open(str(self.event_archive_lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, str(current_pid).encode("utf-8"))
                finally:
                    os.close(fd)
                self._event_archive_guard_depth = 1
                return
            except FileExistsError:
                existing_pid = 0
                try:
                    existing_pid = int(self.event_archive_lock_path.read_text(encoding="utf-8").strip() or "0")
                except Exception:
                    existing_pid = 0
                if existing_pid == current_pid:
                    self._event_archive_guard_depth = 1
                    return
                if existing_pid and is_process_running(existing_pid):
                    if time.time() >= deadline:
                        raise TimeoutError("event_archive_write_lock_timeout")
                    time.sleep(0.05)
                    continue
                try:
                    self.event_archive_lock_path.unlink()
                except FileNotFoundError:
                    pass
                except Exception:
                    if time.time() >= deadline:
                        raise TimeoutError("event_archive_write_lock_timeout")
                    time.sleep(0.05)

    def _release_event_archive_guard(self):
        if self._event_archive_guard_depth <= 0:
            return
        if self._event_archive_guard_depth > 1:
            self._event_archive_guard_depth -= 1
            return
        self._event_archive_guard_depth = 0
        current_pid = os.getpid()
        existing_pid = 0
        try:
            existing_pid = int(self.event_archive_lock_path.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            existing_pid = 0
        if existing_pid and existing_pid != current_pid and is_process_running(existing_pid):
            return
        try:
            self.event_archive_lock_path.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass

    @contextmanager
    def edit_state(self, timeout_seconds=10):
        with self._state_thread_lock:
            self._acquire_state_guard(timeout_seconds=timeout_seconds)
            try:
                payload = self._load_state_payload()
                yield payload
                snapshot = self._prepare_state_snapshot(payload)
                self._write_state_snapshot(snapshot)
            finally:
                self._release_state_guard()

    def update_state(self, updater, timeout_seconds=10):
        with self.edit_state(timeout_seconds=timeout_seconds) as payload:
            return updater(payload)

    def load_config(self):
        return self.load_config_details()["config"]

    def load_config_details(self):
        payload = base_config()
        parse_error = ""
        try:
            payload.update(json.loads(self.config_path.read_text(encoding="utf-8-sig")))
        except Exception as exc:
            parse_error = compact_error_text(f"{type(exc).__name__}: {exc}", limit=280)
        return {
            "config": sync_legacy_list_config_fields(payload),
            "parse_error": parse_error,
            "config_exists": self.config_path.exists(),
            "config_path": str(self.config_path),
        }

    def save_config(self, payload):
        snapshot = sync_legacy_list_config_fields(payload)
        atomic_write_text(self.config_path, json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_state(self):
        return self._load_state_payload()

    def save_state(self, payload):
        with self._state_thread_lock:
            self._acquire_state_guard()
            try:
                snapshot = self._prepare_state_snapshot(payload)
                self._write_state_snapshot(snapshot)
            finally:
                self._release_state_guard()

    def append_event_archive(self, event, archive_event_type="delivery"):
        record = dict(event or {})
        record["archive_record_type"] = "event"
        record["archive_event_type"] = clean_text(archive_event_type) or "delivery"
        record["archived_at"] = iso_now()
        text = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._event_archive_thread_lock:
            self._acquire_event_archive_guard()
            try:
                self.event_archive_path.parent.mkdir(parents=True, exist_ok=True)
                with self.event_archive_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(text)
            finally:
                self._release_event_archive_guard()

    def append_check_archive(self, check):
        record = dict(check or {})
        record["archive_record_type"] = "check"
        record["archive_check_type"] = "check"
        record["archived_at"] = iso_now()
        text = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._event_archive_thread_lock:
            self._acquire_event_archive_guard()
            try:
                self.check_archive_path.parent.mkdir(parents=True, exist_ok=True)
                with self.check_archive_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(text)
            finally:
                self._release_event_archive_guard()


def atomic_write_text(path, text, encoding="utf-8"):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(f"{target.name}.tmp")
    temp_path.write_text(text, encoding=encoding)
    last_error = None
    for attempt in range(10):
        try:
            os.replace(temp_path, target)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt >= 9:
                break
            time.sleep(0.05)
    if temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            pass
    if last_error is not None:
        raise last_error


def trim_seen_ids(seen_ids, maximum):
    items = sorted(seen_ids.items(), key=lambda item: item[1])
    if len(items) <= maximum:
        return dict(items)
    return dict(items[-maximum:])


def durable_seen_enabled(config):
    return config_bool(
        (config or {}).get("durable_seen_enabled", DEFAULT_DURABLE_SEEN_ENABLED),
        DEFAULT_DURABLE_SEEN_ENABLED,
    )


def durable_seen_retention_seconds(config):
    return clamp_int(
        (config or {}).get("durable_seen_retention_seconds", DEFAULT_DURABLE_SEEN_RETENTION_SECONDS),
        DEFAULT_DURABLE_SEEN_RETENTION_SECONDS,
        minimum=3600,
        maximum=14 * 24 * 3600,
    )


def max_durable_seen_ids(config):
    return clamp_int(
        (config or {}).get("max_durable_seen_ids", DEFAULT_MAX_DURABLE_SEEN_IDS),
        DEFAULT_MAX_DURABLE_SEEN_IDS,
        minimum=1000,
        maximum=500000,
    )


def normalize_seen_archive_payload(payload):
    raw_items = {}
    if isinstance(payload, dict):
        raw_items = payload.get("items", {})
        if not isinstance(raw_items, dict):
            raw_items = {}
    items = {}
    for tweet_id, value in raw_items.items():
        key = clean_text(tweet_id)
        if not key:
            continue
        if isinstance(value, dict):
            seen_at = clean_text(value.get("seen_at", "")) or clean_text(value.get("at", ""))
            target_value = clean_text(value.get("target_key", ""))
        else:
            seen_at = clean_text(value)
            target_value = ""
        if not seen_at:
            continue
        items[key] = {"seen_at": seen_at, "target_key": target_value}
    return {"version": 1, "items": items}


def trim_durable_seen_items(items, config, observed_at=None):
    observed_dt = parse_iso_datetime(observed_at) or now_utc()
    cutoff = observed_dt - timedelta(seconds=durable_seen_retention_seconds(config))
    normalized = {}
    for tweet_id, value in dict(items or {}).items():
        key = clean_text(tweet_id)
        if not key:
            continue
        entry = dict(value or {}) if isinstance(value, dict) else {"seen_at": clean_text(value)}
        seen_at = clean_text(entry.get("seen_at", ""))
        seen_dt = parse_iso_datetime(seen_at)
        if seen_dt is None or seen_dt < cutoff:
            continue
        normalized[key] = {
            "seen_at": seen_at,
            "target_key": clean_text(entry.get("target_key", "")),
        }
    maximum = max_durable_seen_ids(config)
    ordered = sorted(normalized.items(), key=lambda item: item[1].get("seen_at", ""))
    if len(ordered) > maximum:
        ordered = ordered[-maximum:]
    return dict(ordered)


def load_seen_archive(store):
    try:
        payload = json.loads(store.seen_archive_path.read_text(encoding="utf-8-sig"))
    except Exception:
        payload = {}
    return normalize_seen_archive_payload(payload)


def durable_seen_ids(store, config, observed_at=None):
    if not durable_seen_enabled(config):
        return {}
    payload = load_seen_archive(store)
    items = trim_durable_seen_items(payload.get("items", {}), config, observed_at=observed_at)
    return {tweet_id: clean_text(value.get("seen_at", "")) for tweet_id, value in items.items()}


def combined_seen_ids(store, config, state, observed_at=None):
    seen = dict((state or {}).get("seen_ids", {}))
    seen.update(durable_seen_ids(store, config, observed_at=observed_at))
    return seen


def mark_durable_seen_ids(store, tweet_ids, stamp=None, config=None, target_ref=None):
    config_value = config or {}
    if not durable_seen_enabled(config_value):
        return False
    at = clean_text(stamp or iso_now())
    target_value = target_key(target_ref) if target_ref is not None else ""
    values = list(dict.fromkeys(clean_text(tweet_id) for tweet_id in (tweet_ids or []) if clean_text(tweet_id)))
    if not values:
        return False
    payload = load_seen_archive(store)
    items = trim_durable_seen_items(payload.get("items", {}), config_value, observed_at=at)
    changed = False
    for tweet_id in values:
        previous = items.get(tweet_id)
        if previous and clean_text(previous.get("seen_at", "")):
            if target_value and not clean_text(previous.get("target_key", "")):
                previous["target_key"] = target_value
                changed = True
            continue
        items[tweet_id] = {"seen_at": at, "target_key": target_value}
        changed = True
    if not changed:
        return False
    items = trim_durable_seen_items(items, config_value, observed_at=at)
    atomic_write_text(
        store.seen_archive_path,
        json.dumps({"version": 1, "updated_at": at, "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def finalize_runtime_config(config):
    config = sync_legacy_list_config_fields(config)
    config["source_slot"] = normalize_source_slot(config.get("source_slot", DEFAULT_SOURCE_SLOT))
    env_map = {
        "discord_channel_id": (
            os.environ.get("X_MONITORPLUS_DISCORD_CHANNEL_ID", "").strip()
        ),
        "discord_bot_token": (
            os.environ.get("X_MONITORPLUS_DISCORD_BOT_TOKEN", "").strip()
        ),
        "x_proxy": (
            os.environ.get("X_MONITORPLUS_PROXY", "").strip()
        ),
    }
    for key, value in env_map.items():
        if value and not clean_text(config.get(key, "")):
            config[key] = value
    for key, value in parse_discord_defaults().items():
        if value and not clean_text(config.get(key, "")):
            config[key] = value
    legacy_defaults_details = load_legacy_x_monitor_defaults_details()
    for key, value in legacy_defaults_details["defaults"].items():
        if value and not clean_text(config.get(key, "")):
            config[key] = value
    slot_binding = load_x_monitor_slot_binding(config.get("source_slot", DEFAULT_SOURCE_SLOT))
    config["x_browser_profile_dir"] = clean_text(config.get("x_browser_profile_dir", "")) or slot_binding["profile_dir"]
    config["x_cookies_path"] = clean_text(config.get("x_cookies_path", "")) or slot_binding["cookies_path"]
    if not clean_text(config.get("x_proxy", "")):
        config["x_proxy"] = discover_proxy_url()
    config["x_lists"] = normalize_list_configs(config)
    config[LEGACY_DEFAULTS_PARSE_ERROR_KEY] = clean_text(legacy_defaults_details.get("parse_error", ""))
    config[LEGACY_DEFAULTS_CONFIG_PATH_KEY] = clean_text(legacy_defaults_details.get("config_path", ""))
    config[LEGACY_DEFAULTS_CONFIG_EXISTS_KEY] = bool(legacy_defaults_details.get("config_exists", False))
    return config


def config_parse_error(config):
    return clean_text((config or {}).get(CONFIG_PARSE_ERROR_KEY, ""))


def config_is_valid(config):
    return not bool(config_parse_error(config))


def state_parse_error(state):
    return clean_text((state or {}).get(STATE_PARSE_ERROR_KEY, ""))


def state_is_valid(state):
    return not bool(state_parse_error(state))


def slot_binding_config_parse_error(slot_binding):
    return clean_text((slot_binding or {}).get("config_parse_error", ""))


def slot_binding_is_valid(slot_binding):
    return not bool(slot_binding_config_parse_error(slot_binding))


def invalid_slot_binding_payload(action, slot_binding, running=False):
    parse_error = slot_binding_config_parse_error(slot_binding)
    return {
        "ok": False,
        "action": action,
        "running": bool(running),
        "error": "invalid_slot_binding_config",
        "slot_binding_config_parse_error": parse_error,
        "slot_binding_config_path": clean_text((slot_binding or {}).get("config_path", "")),
        "slot": clean_text((slot_binding or {}).get("slot", "")),
        "slot_label": source_slot_label((slot_binding or {}).get("slot", DEFAULT_SOURCE_SLOT)),
    }


def legacy_defaults_parse_error(config):
    return clean_text((config or {}).get(LEGACY_DEFAULTS_PARSE_ERROR_KEY, ""))


def legacy_defaults_are_valid(config):
    return not bool(legacy_defaults_parse_error(config))


def runtime_config(store):
    details = store.load_config_details()
    config = finalize_runtime_config(details["config"])
    config[CONFIG_PARSE_ERROR_KEY] = clean_text(details.get("parse_error", ""))
    return config


def runtime_config_with_overrides(store, overrides):
    details = store.load_config_details()
    config = dict(details["config"])
    config.update(overrides or {})
    runtime = finalize_runtime_config(config)
    runtime[CONFIG_PARSE_ERROR_KEY] = clean_text(details.get("parse_error", ""))
    return runtime


def normalize_output_sinks(config):
    raw_value = (config or {}).get("output_sinks", ["discord"])
    if isinstance(raw_value, str):
        values = [part.strip() for part in raw_value.split(",")]
    elif isinstance(raw_value, (list, tuple, set)):
        values = [clean_text(part) for part in raw_value]
    else:
        values = []
    sinks = []
    for value in values:
        key = value.lower().strip()
        if key in {"local", "file", "json", "jsonl", "event_archive", "events"}:
            key = "jsonl"
        if key in {"discord", "jsonl", "webhook"} and key not in sinks:
            sinks.append(key)
    return sinks or ["discord"]


def discord_sink_enabled(config):
    if "discord_enabled" in (config or {}):
        return bool((config or {}).get("discord_enabled", False))
    return "discord" in normalize_output_sinks(config)


def load_editable_config_or_error(store, action):
    details = store.load_config_details()
    parse_error = clean_text(details.get("parse_error", ""))
    if parse_error:
        return None, {
            "ok": False,
            "action": action,
            "error": "invalid_config",
            "config_parse_error": parse_error,
            "config_path": clean_text(details.get("config_path", "")),
        }
    return dict(details.get("config", {})), None


def config_missing(config):
    missing = []
    targets = enabled_targets(config)
    if not targets:
        missing.append("enabled_mode")
    enabled_list_requested = any(bool(entry.get("enabled", False)) for entry in normalize_list_configs(config))
    if enabled_list_requested and not any(target_mode(target) == MODE_LIST for target in targets):
        missing.append("x_list_url")
    if discord_sink_enabled(config):
        if not clean_text(config.get("discord_channel_id", "")):
            missing.append("discord_channel_id")
        if not clean_text(config.get("discord_bot_token", "")):
            missing.append("discord_bot_token")
    return missing


def read_pid(store):
    try:
        return int(store.pid_path.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def write_pid(store, pid):
    store.pid_path.write_text(str(int(pid)), encoding="utf-8")


def clear_pid(store):
    try:
        store.pid_path.unlink()
    except FileNotFoundError:
        return
    except Exception:
        pass


def detect_wrapper_python():
    for wrapper_name in ("service_start.cmd", "request.cmd"):
        wrapper_path = Path(__file__).resolve().parent.parent / wrapper_name
        if not wrapper_path.exists():
            continue
        try:
            text = wrapper_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        match = re.search(r'SET\s+"PYTHON_EXE=([^"\r\n]+)"', text, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = Path(match.group(1).strip())
        if candidate.exists():
            return str(candidate)
    return ""


def preferred_background_python():
    wrapper_python = detect_wrapper_python()
    if wrapper_python:
        current = Path(wrapper_python)
        if os.name == "nt":
            pythonw = current.with_name("pythonw.exe")
            if pythonw.exists():
                return str(pythonw)
        return str(current)
    if os.name != "nt":
        return sys.executable
    current = Path(sys.executable)
    pythonw = current.with_name("pythonw.exe")
    if pythonw.exists():
        return str(pythonw)
    return sys.executable


def state_service_pid(state):
    try:
        return int((state or {}).get("service_pid", 0) or 0)
    except Exception:
        return 0


def read_lock_pid(store):
    try:
        return int(store.lock_path.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        return 0


def acquire_service_lock(store, pid=None):
    lock_pid = int(pid or os.getpid())
    for _ in range(2):
        try:
            fd = os.open(store.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing_pid = read_lock_pid(store)
            if existing_pid and is_process_running(existing_pid):
                return False
            try:
                store.lock_path.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                return False
            continue
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(str(lock_pid))
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            try:
                store.lock_path.unlink()
            except Exception:
                pass
            return False
        return True
    return False


def release_service_lock(store):
    current_pid = os.getpid()
    lock_pid = read_lock_pid(store)
    if lock_pid and lock_pid != current_pid and is_process_running(lock_pid):
        return
    try:
        store.lock_path.unlink()
    except FileNotFoundError:
        return
    except Exception:
        pass


def touch_service_runtime(store, pid=None, heartbeat_at=None):
    def updater(state):
        if pid is not None:
            try:
                state["service_pid"] = int(pid)
            except Exception:
                state["service_pid"] = 0
        state["service_heartbeat_at"] = str(heartbeat_at or iso_now())
        state["last_service_stop_at"] = ""

    store.update_state(updater)


def mark_service_stopped(store, pid=None, stopped_at=None):
    def updater(state):
        current_pid = state_service_pid(state)
        if pid is None or not current_pid or int(pid) == current_pid:
            state["service_pid"] = 0
        state["service_heartbeat_at"] = ""
        state["last_service_stop_at"] = str(stopped_at or iso_now())

    store.update_state(updater)


def is_process_running(pid):
    try:
        pid_value = int(pid)
        if pid_value <= 0:
            return False
    except Exception:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid_value)
            if handle:
                try:
                    exit_code = ctypes.c_ulong()
                    if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                        return exit_code.value == STILL_ACTIVE
                finally:
                    kernel32.CloseHandle(handle)
        except Exception:
            pass
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid_value}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            creationflags=WINDOWS_CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception:
        return False
    output = result.stdout or ""
    return str(pid_value) in output and "No tasks are running" not in output and "Access denied" not in output


def resolve_running_service_pid(store, state=None):
    current_state = state or store.load_state()
    file_pid = read_pid(store)
    state_pid = state_service_pid(current_state)
    lock_pid = read_lock_pid(store)
    for candidate in (file_pid, state_pid, lock_pid):
        if candidate and is_process_running(candidate):
            if candidate == file_pid:
                detected_by = "pid"
            elif candidate == state_pid:
                detected_by = "state_pid"
            else:
                detected_by = "lock"
            return int(candidate), detected_by
    return 0, ""


def wait_for_service_start(store, candidate_pid=0, timeout_seconds=DEFAULT_SERVICE_START_TIMEOUT_SECONDS):
    deadline = time.time() + max(1, int(timeout_seconds))
    fallback_allowed_at = time.time() + 2.0
    while time.time() < deadline:
        state = store.load_state()
        running_pid, detected_by = resolve_running_service_pid(store, state)
        if running_pid:
            if read_pid(store) != running_pid:
                write_pid(store, running_pid)
            return True, running_pid, detected_by
        if candidate_pid and time.time() >= fallback_allowed_at and is_process_running(candidate_pid):
            write_pid(store, candidate_pid)
            return True, int(candidate_pid), "process"
        time.sleep(0.5)
    state = store.load_state()
    running_pid, detected_by = resolve_running_service_pid(store, state)
    if running_pid:
        if read_pid(store) != running_pid:
            write_pid(store, running_pid)
        return True, running_pid, detected_by
    if candidate_pid and is_process_running(candidate_pid):
        write_pid(store, candidate_pid)
        return True, int(candidate_pid), "process"
    return False, 0, ""


def wait_for_process_stop(pid, timeout_seconds=DEFAULT_SERVICE_STOP_TIMEOUT_SECONDS):
    if not pid:
        return True
    deadline = time.time() + max(1, int(timeout_seconds))
    while time.time() < deadline:
        if not is_process_running(pid):
            return True
        time.sleep(0.5)
    return not is_process_running(pid)


def suppress_embed_urls(content):
    def repl(match):
        url = match.group(0)
        if url.startswith("<") and url.endswith(">"):
            return url
        return f"<{url}>"

    return re.sub(r"https?://[^\s>]+", repl, str(content or ""))


def discord_request_timeout_seconds(config):
    return clamp_float(
        config.get("discord_request_timeout_seconds", DEFAULT_DISCORD_REQUEST_TIMEOUT_SECONDS),
        DEFAULT_DISCORD_REQUEST_TIMEOUT_SECONDS,
        minimum=3.0,
        maximum=120.0,
    )


def discord_transient_retry_count(config):
    return clamp_int(
        config.get("discord_transient_retry_count", DEFAULT_DISCORD_TRANSIENT_RETRY_COUNT),
        DEFAULT_DISCORD_TRANSIENT_RETRY_COUNT,
        minimum=0,
        maximum=5,
    )


def discord_transient_retry_delay_seconds(config):
    milliseconds = clamp_int(
        config.get("discord_transient_retry_delay_milliseconds", DEFAULT_DISCORD_TRANSIENT_RETRY_DELAY_MILLISECONDS),
        DEFAULT_DISCORD_TRANSIENT_RETRY_DELAY_MILLISECONDS,
        minimum=100,
        maximum=15000,
    )
    return milliseconds / 1000.0


def discord_retry_after_seconds_from_exception(exc, default_seconds):
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        header_value = clean_text(exc.response.headers.get("Retry-After", ""))
        try:
            return clamp_float(float(header_value), default_seconds, minimum=0.1, maximum=30 * 60)
        except Exception:
            pass
    return clamp_float(default_seconds, default_seconds, minimum=0.1, maximum=30 * 60)


def is_transient_discord_error(exc):
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status_code = int(exc.response.status_code or 0)
        return status_code == 429 or status_code >= 500
    return False


def build_discord_nonce(content, seed=""):
    source = f"{clean_text(seed)}\n{suppress_embed_urls(content)}"
    return hashlib.sha1(source.encode("utf-8", errors="replace")).hexdigest()[:24]


def discord_headers(config):
    return {"Authorization": config["discord_bot_token"], "Content-Type": "application/json"}


def discord_request_with_retry(config, request_func, url, payload):
    max_attempts = discord_transient_retry_count(config) + 1
    base_delay_seconds = discord_transient_retry_delay_seconds(config)
    last_exc = None
    for attempt in range(max_attempts):
        try:
            resp = request_func(
                url,
                headers=discord_headers(config),
                json=payload,
                timeout=discord_request_timeout_seconds(config),
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts - 1 or not is_transient_discord_error(exc):
                raise
            delay_seconds = discord_retry_after_seconds_from_exception(
                exc,
                base_delay_seconds * (2 ** attempt),
            )
            time.sleep(delay_seconds)
    raise last_exc


def discord_send(config, content):
    url = f"https://discord.com/api/v10/channels/{config['discord_channel_id']}/messages"
    payload = {
        "content": suppress_embed_urls(content),
        "nonce": build_discord_nonce(content),
        "enforce_nonce": True,
    }
    return discord_request_with_retry(
        config,
        requests.post,
        url,
        payload,
    )


def discord_edit(config, message_id, content):
    url = f"https://discord.com/api/v10/channels/{config['discord_channel_id']}/messages/{message_id}"
    return discord_request_with_retry(
        config,
        requests.patch,
        url,
        {"content": suppress_embed_urls(content)},
    )


def parse_custom_headers(config, config_key="editor_draft_custom_headers_json"):
    text = clean_text(config.get(config_key, ""))
    if not text:
        return {}
    try:
        value = json.loads(text)
    except Exception:
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(key): str(val) for key, val in value.items()}


def build_local_fast_translation_provider(config):
    if not config_bool(
        config.get("local_fast_translation_enabled", DEFAULT_LOCAL_FAST_TRANSLATION_ENABLED),
        DEFAULT_LOCAL_FAST_TRANSLATION_ENABLED,
    ):
        return None
    api_base = clean_text(config.get("local_fast_translation_api_base", ""))
    api_key = clean_text(config.get("local_fast_translation_api_key", ""))
    model = clean_text(config.get("local_fast_translation_model", ""))
    if not (api_base and api_key and model):
        return None
    return {
        "api_base": api_base,
        "api_key": api_key,
        "model": model,
        "headers": parse_custom_headers(config, "local_fast_translation_custom_headers_json"),
        "proxies": requests_proxies(config, for_editor=False, proxy_key="local_fast_translation_proxy"),
    }


def local_fast_translation_timeout_seconds(config, initial_delivery=False):
    timeout_seconds = clamp_float(
        config.get("local_fast_translation_timeout_seconds", DEFAULT_LOCAL_FAST_TRANSLATION_TIMEOUT_SECONDS),
        DEFAULT_LOCAL_FAST_TRANSLATION_TIMEOUT_SECONDS,
        minimum=0.5,
        maximum=60.0,
    )
    if initial_delivery:
        initial_timeout_seconds = clamp_float(
            config.get(
                "local_fast_translation_initial_timeout_seconds",
                DEFAULT_INITIAL_LOCAL_FAST_TRANSLATION_TIMEOUT_SECONDS,
            ),
            DEFAULT_INITIAL_LOCAL_FAST_TRANSLATION_TIMEOUT_SECONDS,
            minimum=0.2,
            maximum=10.0,
        )
        return min(timeout_seconds, initial_timeout_seconds)
    return timeout_seconds


def local_fast_translation_initial_failure_cooldown_seconds(config):
    return clamp_float(
        config.get(
            "local_fast_translation_initial_failure_cooldown_seconds",
            DEFAULT_LOCAL_FAST_TRANSLATION_INITIAL_FAILURE_COOLDOWN_SECONDS,
        ),
        DEFAULT_LOCAL_FAST_TRANSLATION_INITIAL_FAILURE_COOLDOWN_SECONDS,
        minimum=0.0,
        maximum=300.0,
    )


def local_fast_translation_provider_key(provider):
    return "|".join(
        [
            clean_text((provider or {}).get("api_base", "")).rstrip("/"),
            clean_text((provider or {}).get("model", "")),
        ]
    )


def local_fast_translation_circuit_open(config, provider, initial_delivery=False):
    if not initial_delivery:
        return ""
    key = local_fast_translation_provider_key(provider)
    if not key:
        return ""
    now_value = time.time()
    with LOCAL_FAST_TRANSLATION_CIRCUIT_LOCK:
        if LOCAL_FAST_TRANSLATION_CIRCUIT.get("key") != key:
            return ""
        blocked_until = float(LOCAL_FAST_TRANSLATION_CIRCUIT.get("blocked_until", 0.0) or 0.0)
        if blocked_until <= now_value:
            return ""
        last_error = clean_text(LOCAL_FAST_TRANSLATION_CIRCUIT.get("last_error", "")) or "recent_failure"
    return f"local_fast_translation_circuit_open:{last_error}"


def local_fast_translation_error_should_trip_circuit(error):
    value = clean_text(error).lower()
    if not value:
        return False
    markers = (
        "timeout",
        "timed out",
        "connection",
        "connect",
        "refused",
        "reset",
        "max retries",
        "httpconnectionpool",
        "server error",
    )
    return any(marker in value for marker in markers)


def record_local_fast_translation_failure(config, provider, error, initial_delivery=False):
    if not initial_delivery or not local_fast_translation_error_should_trip_circuit(error):
        return
    cooldown_seconds = local_fast_translation_initial_failure_cooldown_seconds(config)
    if cooldown_seconds <= 0:
        return
    key = local_fast_translation_provider_key(provider)
    if not key:
        return
    with LOCAL_FAST_TRANSLATION_CIRCUIT_LOCK:
        LOCAL_FAST_TRANSLATION_CIRCUIT.update(
            {
                "key": key,
                "blocked_until": time.time() + cooldown_seconds,
                "last_error": compact_error_text(error, limit=120),
            }
        )


def clear_local_fast_translation_circuit(provider):
    key = local_fast_translation_provider_key(provider)
    if not key:
        return
    with LOCAL_FAST_TRANSLATION_CIRCUIT_LOCK:
        if LOCAL_FAST_TRANSLATION_CIRCUIT.get("key") == key:
            LOCAL_FAST_TRANSLATION_CIRCUIT.update({"key": "", "blocked_until": 0.0, "last_error": ""})


def async_enrich_max_workers(config):
    return clamp_int(
        config.get("async_enrich_max_workers", DEFAULT_ASYNC_ENRICH_MAX_WORKERS),
        DEFAULT_ASYNC_ENRICH_MAX_WORKERS,
        minimum=1,
        maximum=4,
    )


def local_fast_translation_max_tokens(text):
    return clamp_int(len(clean_text(text)) + 160, 320, minimum=180, maximum=1200)


def local_fast_translation_prompt_language(target_language):
    value = clean_text(target_language)
    key = value.lower().replace("_", "-")
    if key in {"zh", "zh-cn", "chinese", "simplified chinese", "mandarin"}:
        return "Simplified Chinese"
    if key in {"zh-tw", "zh-hant", "traditional chinese"}:
        return "Traditional Chinese"
    return value or DEFAULT_TRANSLATE_TO


def normalize_openai_response_text(content):
    if isinstance(content, str):
        return clean_text(content)
    if isinstance(content, list):
        pieces = []
        for part in content:
            if isinstance(part, dict):
                text_field = part.get("text", "")
                if isinstance(text_field, dict):
                    text_value = clean_text(text_field.get("value", ""))
                else:
                    text_value = clean_text(text_field)
                if text_value:
                    pieces.append(text_value)
                    continue
                content_value = clean_text(part.get("content", ""))
                if content_value:
                    pieces.append(content_value)
                    continue
            else:
                text_value = clean_text(part)
                if text_value:
                    pieces.append(text_value)
        return clean_text("\n".join(pieces))
    return clean_text(content)


def strip_translation_response_prefix(text):
    value = clean_text(text)
    if not value:
        return ""
    return clean_text(re.sub(r"^(?:translation|translated text|中文翻译|翻译|译文)\s*[:：]\s*", "", value, count=1, flags=re.I))


def fetch_local_fast_translation(config, text, limit=1400, initial_delivery=False):
    cleaned = clean_text(text)
    if not cleaned:
        return {"ok": False, "error": "empty_source_text"}
    provider = build_local_fast_translation_provider(config)
    if not provider:
        return {"ok": False, "error": "local_fast_translation_not_configured"}
    circuit_error = local_fast_translation_circuit_open(config, provider, initial_delivery=initial_delivery)
    if circuit_error:
        return {"ok": False, "error": circuit_error}
    url = provider["api_base"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"}
    headers.update(provider.get("headers") or {})
    target_language = clean_text(config.get("translate_to", DEFAULT_TRANSLATE_TO)) or DEFAULT_TRANSLATE_TO
    prompt_language = local_fast_translation_prompt_language(target_language)
    timeout_seconds = local_fast_translation_timeout_seconds(config, initial_delivery=initial_delivery)

    def build_payload(strict=False):
        system_prompt = (
            f"You are a translation engine. Translate the user text into {prompt_language}. "
            f"The final answer must be in {prompt_language}. "
            "Return only the translation. Preserve paragraph breaks. "
            "Keep handles, hashtags, URLs, names, and facts accurate. "
            "Translate all ordinary words in short titles, headlines, and sports/news snippets. "
            "Do not copy the source text as the answer unless it is only a name, handle, URL, or code. "
            "Do not add explanations or quotation marks."
        )
        if strict:
            system_prompt += (
                f" Retry because the previous output was not a usable {prompt_language} translation. "
                f"Output {prompt_language} only. Do not repeat the original wording."
            )
        return {
            "model": provider["model"],
            "temperature": 0.0,
            "max_tokens": local_fast_translation_max_tokens(cleaned),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": cleaned},
            ],
        }

    last_error = ""
    translation = ""
    same_as_source = False
    for strict in (False, True):
        try:
            resp = requests.post(
                url,
                headers=headers,
                json=build_payload(strict=strict),
                timeout=timeout_seconds,
                proxies=provider.get("proxies"),
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.Timeout:
            record_local_fast_translation_failure(
                config, provider, "local_fast_translation_timeout", initial_delivery=initial_delivery
            )
            return {"ok": False, "error": "local_fast_translation_timeout"}
        except Exception as exc:
            error_text = compact_error_text(str(exc), limit=280)
            record_local_fast_translation_failure(config, provider, error_text, initial_delivery=initial_delivery)
            return {"ok": False, "error": error_text}
        choices = data.get("choices") or []
        if not choices:
            last_error = "local_fast_translation_empty_response"
            break
        choice = choices[0] or {}
        content = normalize_openai_response_text(
            (choice.get("message") or {}).get("content", "") or choice.get("text", "")
        )
        translation = strip_translation_response_prefix(content)
        translation = sanitize_translation_text(translation, limit=limit) or compact_error_text(translation, limit=limit)
        if not translation:
            last_error = "local_fast_translation_empty_text"
            break
        if not translation_matches_target_language(target_language, translation):
            last_error = "local_fast_translation_target_language_mismatch"
            continue
        same_as_source = translation_looks_same_as_source(cleaned, translation)
        if same_as_source and text_needs_translation(cleaned):
            last_error = "local_fast_translation_same_as_source"
            continue
        last_error = ""
        break
    if last_error:
        return {"ok": False, "error": last_error}
    clear_local_fast_translation_circuit(provider)
    return {
        "ok": True,
        "translation": compact_error_text(translation, limit=limit),
        "same_as_source": same_as_source,
        "draft_model": provider["model"],
        "draft_provider": "local_fast_translation",
        "draft_ready_at": iso_now(),
    }


def build_editor_draft_provider(config, prefix="editor_draft", label="primary"):
    prefix_value = clean_text(prefix) or "editor_draft"
    api_base = clean_text(config.get(f"{prefix_value}_api_base", ""))
    api_key = clean_text(config.get(f"{prefix_value}_api_key", ""))
    model = clean_text(config.get(f"{prefix_value}_model", ""))
    if not (api_base and api_key and model):
        return None
    return {
        "label": clean_text(label) or prefix_value,
        "prefix": prefix_value,
        "api_base": api_base,
        "api_key": api_key,
        "model": model,
        "headers": parse_custom_headers(config, f"{prefix_value}_custom_headers_json"),
        "proxies": requests_proxies(config, for_editor=True, proxy_key=f"{prefix_value}_proxy"),
    }


def editor_draft_provider_candidates(config):
    candidates = []
    seen = set()
    for prefix, label in (("editor_draft", "primary"), ("editor_draft_fallback", "fallback")):
        provider = build_editor_draft_provider(config, prefix=prefix, label=label)
        if not provider:
            continue
        signature = (provider["api_base"], provider["model"], provider["label"])
        if signature in seen:
            continue
        seen.add(signature)
        candidates.append(provider)
    return candidates


def extract_json_object(text):
    source = str(text or "").strip()
    if not source:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", source, re.S)
    if fenced:
        source = fenced.group(1)
    start = source.find("{")
    end = source.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = source[start : end + 1]
    try:
        payload = json.loads(candidate)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def build_editor_prompt(item):
    source_title = draft_source_title(item, limit=260)
    source_body = draft_source_body(item, limit=1200)
    source_full_text = draft_source_full_text(item, limit=1600)
    if not source_full_text:
        source_full_text = source_title or source_body
    return (
        "\u4f60\u662f X \u76d1\u63a7\u7ffb\u8bd1\u52a9\u624b\u3002\n"
        "\u4efb\u52a1\u4e0d\u662f\u5199\u65b0\u95fb\uff0c\u4e0d\u662f\u62c6\u6210\u6807\u9898/\u5360\u4f4d\u7a3f/PUSH\uff0c\u800c\u662f\u628a\u539f\u5e16\u5168\u90e8\u53ef\u89c1\u6b63\u6587\u6309\u8bed\u5883\u76f4\u63a5\u8bd1\u6210\u4e00\u4efd\u81ea\u7136\u3001\u51c6\u786e\u7684\u4e2d\u6587\u3002\n"
        "\u8bf7\u53ea\u57fa\u4e8e\u539f\u5e16\u539f\u6587\uff08\u539f\u8bed\u8a00\uff09\u751f\u6210\u4e2d\u6587\uff0c\u4e0d\u8981\u81ea\u884c\u8865\u5145\u56fe\u7247\u3001\u5f15\u7528\u5e16\u3001\u5916\u94fe\u5361\u7247\u3001\u89c6\u9891\u91cc\u7684\u5185\u5bb9\u3002\n"
        "\u8fd4\u56de JSON\uff0c\u53ea\u80fd\u5305\u542b\u4e00\u4e2a\u5b57\u6bb5\uff1atranslation\n"
        "\u89c4\u5219\uff1a\n"
        "1. translation \u662f\u539f\u5e16\u5168\u90e8\u53ef\u89c1\u6b63\u6587\u7684\u4e2d\u6587\u7ffb\u8bd1\uff0c\u4e0d\u8981\u6539\u5199\u6210\u65b0\u95fb\u8154\uff0c\u4e0d\u8981\u62c6\u6210\u6807\u9898/\u8981\u70b9\u3002\n"
        "2. \u5982\u679c\u539f\u6587\u6709\u591a\u6bb5\uff0c\u8bf7\u4fdd\u7559\u5927\u81f4\u6bb5\u843d\u7ed3\u6784\uff1b\u5982\u679c\u53ea\u6709\u4e00\u53e5\uff0c\u5c31\u76f4\u63a5\u8bd1\u6210\u4e00\u53e5\u3002\n"
        "3. \u5982\u679c\u539f\u6587\u91cc\u51fa\u73b0\u88ab\u70b9\u540d\u7684 @\u8d26\u53f7\u3001\u4eba\u540d\u6216\u5bf9\u8c61\uff0c\u8bf7\u5728\u8bd1\u6587\u91cc\u4fdd\u7559\u8be5\u5bf9\u8c61\uff0c\u4e0d\u8981\u7701\u7565\u6210\u6cdb\u6cdb\u6982\u62ec\u3002\n"
        "4. \u4e0d\u8981\u8f93\u51fa\u4efb\u4f55\u89e3\u91ca\u3001\u5907\u6ce8\u3001\u201c\u66f4\u591a\u4fe1\u606f\u4ee5\u5b98\u65b9\u4e3a\u51c6\u201d\u4e4b\u7c7b\u7684\u7a7a\u8bdd\uff0c\u4e5f\u4e0d\u8981\u8865\u5199\u63a8\u7406\u5185\u5bb9\u3002\n\n"
        f"\u8d26\u53f7\uff1a@{item.get('handle', '')}\n"
        f"\u53d1\u5e03\u65f6\u95f4\uff1a{item.get('created_at', '')}\n"
        f"\u539f\u5e16\u94fe\u63a5\uff1a{item.get('status_url', '')}\n"
        "\u6807\u9898\u539f\u6587\uff1a\n"
        f"{source_title}\n\n"
        "\u539f\u5e16\u6b63\u6587\u8865\u5145\uff1a\n"
        f"{source_body}\n\n"
        "\u539f\u5e16\u5168\u90e8\u53ef\u89c1\u6b63\u6587\uff08\u6700\u7ec8\u7ffb\u8bd1\u4f9d\u636e\uff09\uff1a\n"
        f"{source_full_text}"
    )


GENERIC_EDITOR_DRAFT_MARKERS = (
    "\u66f4\u591a\u4fe1\u606f\u4ee5\u5b98\u65b9\u540e\u7eed\u6d88\u606f\u4e3a\u51c6",
    "\u5b98\u65b9\u6682\u672a\u62ab\u9732\u66f4\u591a\u7ec6\u8282",
    "\u67e5\u770b\u539f\u5e16",
    "\u7ed3\u5408\u539f\u5e16",
    "\u539f\u5e16\u53ef\u89c1\u6587\u5b57\u8f83\u5c11",
    "\u539f\u5e16\u6b63\u6587\u8865\u5145\u4e0d\u8db3",
)


def looks_generic_editor_draft_text(text):
    value = clean_text(text)
    if not value:
        return True
    return any(marker in value for marker in GENERIC_EDITOR_DRAFT_MARKERS)


def translate_source_text(config, text, limit=320):
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    translated = ""
    local_result = fetch_local_fast_translation(config, cleaned, limit=limit)
    if local_result.get("ok") and not bool(local_result.get("same_as_source", False)):
        translated = clean_text(local_result.get("translation", ""))
    retry_count = max(0, int(DEFAULT_MACHINE_TRANSLATION_RETRY_COUNT))
    retry_delay_seconds = max(0.0, float(DEFAULT_MACHINE_TRANSLATION_RETRY_DELAY_MILLISECONDS) / 1000.0)
    if not translated:
        for attempt in range(retry_count + 1):
            try:
                translated = translate_title(
                    cleaned,
                    clean_text(config.get("translate_to", DEFAULT_TRANSLATE_TO)) or DEFAULT_TRANSLATE_TO,
                    proxy_mapping=requests_proxies(config, for_editor=False),
                )
                if clean_text(translated):
                    break
            except Exception:
                translated = ""
            if attempt < retry_count and retry_delay_seconds > 0:
                time.sleep(retry_delay_seconds)
    translated_value = clean_text(translated)
    if looks_untranslated_machine_translation(cleaned, translated_value):
        line_results = []
        changed = False
        for raw_line in re.split(r"\n+", cleaned):
            line = clean_text(raw_line)
            if not line:
                continue
            line_translation = ""
            for attempt in range(retry_count + 1):
                try:
                    line_translation = translate_title(
                        line,
                        clean_text(config.get("translate_to", DEFAULT_TRANSLATE_TO)) or DEFAULT_TRANSLATE_TO,
                        proxy_mapping=requests_proxies(config, for_editor=False),
                    )
                    if clean_text(line_translation):
                        break
                except Exception:
                    line_translation = ""
                if attempt < retry_count and retry_delay_seconds > 0:
                    time.sleep(retry_delay_seconds)
            normalized_line_translation = clean_text(line_translation) or line
            if text_similarity_ratio(line, normalized_line_translation) < 0.97:
                changed = True
            line_results.append(normalized_line_translation)
        if changed:
            translated_value = clean_text("\n".join(line_results))
    return compact_error_text(translated_value or cleaned, limit=limit)


def first_sentence(text, limit=100):
    value = clean_text(text)
    if not value:
        return ""
    pieces = re.split(r"(?<=[。！？!?])\s*", value)
    for piece in pieces:
        candidate = clean_text(piece)
        if candidate:
            return compact_error_text(candidate, limit=limit)
    return compact_error_text(value, limit=limit)


SOURCE_HANDLE_RE = re.compile(r"@[\w.]{1,32}", re.I)


def extract_source_handles(value):
    handles = []
    seen = set()
    for match in SOURCE_HANDLE_RE.findall(clean_text(value)):
        lowered = match.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        handles.append(match)
    return handles


def text_contains_source_handle(text, handles):
    value = clean_text(text).lower()
    if not value:
        return False
    return any(clean_text(handle).lower() in value for handle in (handles or []))


def combine_source_title_body(source_title, source_body):
    title_text = clean_text(source_title)
    body_text = clean_text(source_body)
    if title_text and body_text:
        return f"{title_text}\n{body_text}"
    return title_text or body_text


def normalize_editor_draft(config, item, draft):
    result = dict(draft or {})
    source_title = draft_source_title(item, limit=260)
    source_body = draft_source_body(item, limit=800)
    source_full_text = draft_source_full_text(item, limit=1600) or combine_source_title_body(source_title, source_body)
    if is_emoji_passthrough_text(source_full_text):
        translation = sanitize_translation_text(source_full_text, limit=1400) or clean_text(source_full_text)
        result["translation"] = compact_error_text(translation, limit=1400)
        result["emoji_passthrough_used"] = True
        return result
    source_handles = extract_source_handles(source_full_text)
    has_meaningful_source_body = bool(normalize_similarity_text(source_body)) and len(normalize_similarity_text(source_body)) >= 24
    translation = clean_text(result.get("translation", ""))
    translated_title = ""
    translated_full_text = ""

    def fallback_title():
        nonlocal translated_title
        if not translated_title:
            translated_title = translate_source_text(config, source_title, limit=200)
        return translated_title

    def fallback_translation():
        nonlocal translated_full_text
        if not translated_full_text:
            translated_full_text = translate_source_text(config, source_full_text or source_title, limit=1400)
        return translated_full_text

    if not translation or looks_generic_editor_draft_text(translation):
        translation = fallback_translation() or translation
    translation = sanitize_translation_text(translation, limit=1400)
    if looks_untranslated_machine_translation(source_full_text, translation):
        translation = sanitize_translation_text(fallback_translation(), limit=1400) or translation
    if source_handles and not text_contains_source_handle(translation, source_handles):
        translation = sanitize_translation_text(fallback_translation(), limit=1400) or translation
    if has_meaningful_source_body and text_similarity_ratio(translation, fallback_title()) >= 0.9:
        translation = sanitize_translation_text(fallback_translation(), limit=1400) or translation
    if not translation:
        translation = sanitize_translation_text(fallback_translation(), limit=1400) or source_full_text or source_title
    result["translation"] = compact_error_text(translation, limit=1400)
    return result


def fetch_editor_draft(config, item, provider=None):
    provider_value = provider or build_editor_draft_provider(config, prefix="editor_draft", label="primary")
    if not provider_value:
        return {"ok": False, "error": "editor_draft_api_not_configured"}
    api_base = provider_value["api_base"]
    api_key = provider_value["api_key"]
    model = provider_value["model"]
    url = api_base.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    headers.update(provider_value.get("headers") or {})
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "\u4f60\u53ea\u8fd4\u56de JSON\u3002"},
            {"role": "user", "content": build_editor_prompt(item)},
        ],
    }
    resp = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=clamp_int(
            config.get("editor_draft_timeout_seconds", DEFAULT_EDITOR_DRAFT_TIMEOUT_SECONDS),
            DEFAULT_EDITOR_DRAFT_TIMEOUT_SECONDS,
            minimum=5,
            maximum=180,
        ),
        proxies=provider_value.get("proxies"),
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return {"ok": False, "error": "empty editor draft response"}
    content = choices[0].get("message", {}).get("content", "")
    parsed = extract_json_object(content)
    if not parsed:
        return {"ok": False, "error": "editor draft did not return valid json"}
    translation = clean_text(parsed.get("translation", ""))
    if not translation:
        headline = clean_text(parsed.get("headline", ""))
        push_copy = clean_text(parsed.get("push_copy", ""))
        placeholder_body = clean_text(parsed.get("placeholder_body", ""))
        pieces = []
        if headline:
            pieces.append(headline)
        if placeholder_body and (not headline or text_similarity_ratio(placeholder_body, headline) < 0.92):
            pieces.append(placeholder_body)
        elif not pieces and placeholder_body:
            pieces.append(placeholder_body)
        if not pieces and push_copy:
            pieces.append(push_copy)
        translation = "\n".join(piece for piece in pieces if piece)
    if not translation:
        return {"ok": False, "error": "editor draft missing translation"}
    return {
        "ok": True,
        "draft": {
            **normalize_editor_draft(
                config,
                item,
                {
                    "translation": translation,
                },
            ),
            "raw_translated_title": compact_error_text(
                clean_text((item or {}).get("raw_translated_title", "")) or build_raw_translated_title(config, item),
                limit=120,
            ),
            "draft_model": model,
            "draft_provider": clean_text(provider_value.get("label", "")),
            "draft_ready_at": iso_now(),
        },
    }


def is_rate_limit_error(exc):
    if isinstance(exc, requests.HTTPError) and exc.response is not None and int(exc.response.status_code or 0) == 429:
        return True
    text = compact_error_text(str(exc), limit=500).lower()
    if not text:
        return False
    markers = ("429", "too many requests", "rate limit", "rate-limited", "too many")
    return any(marker in text for marker in markers)


def retry_after_seconds_from_exception(exc, default_seconds):
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        header_value = clean_text(exc.response.headers.get("Retry-After", ""))
        if header_value.isdigit():
            return clamp_int(header_value, default_seconds, minimum=5, maximum=30 * 60)
    return clamp_int(default_seconds, default_seconds, minimum=5, maximum=30 * 60)


def editor_draft_min_interval_seconds(config):
    return clamp_int(
        config.get("editor_draft_min_interval_seconds", DEFAULT_EDITOR_DRAFT_MIN_INTERVAL_SECONDS),
        DEFAULT_EDITOR_DRAFT_MIN_INTERVAL_SECONDS,
        minimum=0,
        maximum=60,
    )


def editor_draft_rate_limit_cooldown_seconds(config):
    return clamp_int(
        config.get("editor_draft_rate_limit_cooldown_seconds", DEFAULT_EDITOR_DRAFT_RATE_LIMIT_COOLDOWN_SECONDS),
        DEFAULT_EDITOR_DRAFT_RATE_LIMIT_COOLDOWN_SECONDS,
        minimum=15,
        maximum=30 * 60,
    )


def editor_draft_transient_retry_count(config):
    return clamp_int(
        config.get("editor_draft_transient_retry_count", DEFAULT_EDITOR_DRAFT_TRANSIENT_RETRY_COUNT),
        DEFAULT_EDITOR_DRAFT_TRANSIENT_RETRY_COUNT,
        minimum=0,
        maximum=5,
    )


def editor_draft_transient_retry_delay_milliseconds(config):
    return clamp_int(
        config.get(
            "editor_draft_transient_retry_delay_milliseconds",
            DEFAULT_EDITOR_DRAFT_TRANSIENT_RETRY_DELAY_MILLISECONDS,
        ),
        DEFAULT_EDITOR_DRAFT_TRANSIENT_RETRY_DELAY_MILLISECONDS,
        minimum=250,
        maximum=15000,
    )


def update_editor_draft_state(store, **updates):
    def updater(state):
        for key, value in updates.items():
            state[key] = value

    store.update_state(updater)


def clear_editor_draft_error(store):
    update_editor_draft_state(store, editor_draft_last_error="")


def mark_editor_draft_error(store, error_text):
    update_editor_draft_state(store, editor_draft_last_error=compact_error_text(error_text, limit=500))


def wait_for_editor_draft_window(store, config, respect_cooldown=True):
    minimum_spacing = editor_draft_min_interval_seconds(config)
    while True:
        state = store.load_state()
        now_dt = now_utc()
        cooldown_until = parse_iso_datetime(state.get("editor_draft_cooldown_until", ""))
        last_request_at = parse_iso_datetime(state.get("editor_draft_last_request_at", ""))
        wait_seconds = 0.0
        if respect_cooldown and cooldown_until is not None and cooldown_until > now_dt:
            wait_seconds = max(wait_seconds, (cooldown_until - now_dt).total_seconds())
        if minimum_spacing > 0 and last_request_at is not None:
            next_allowed = last_request_at.timestamp() + minimum_spacing
            wait_seconds = max(wait_seconds, next_allowed - now_dt.timestamp())
        if wait_seconds <= 0:
            update_editor_draft_state(
                store,
                editor_draft_last_request_at=iso_now(),
                editor_draft_last_error="",
            )
            return
        time.sleep(min(wait_seconds, 5.0))


def schedule_editor_draft_cooldown(store, seconds, error_text=""):
    seconds_value = clamp_int(seconds, DEFAULT_EDITOR_DRAFT_RATE_LIMIT_COOLDOWN_SECONDS, minimum=5, maximum=30 * 60)
    until_value = datetime.fromtimestamp(now_utc().timestamp() + seconds_value, tz=timezone.utc).isoformat()
    update_editor_draft_state(
        store,
        editor_draft_cooldown_until=until_value,
        editor_draft_last_error=compact_error_text(error_text, limit=500),
    )


def clear_editor_draft_cooldown(store):
    update_editor_draft_state(store, editor_draft_cooldown_until="", editor_draft_last_error="")


def is_editor_draft_transient_error(exc):
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    text = clean_text(str(exc)).lower()
    transient_markers = (
        "timed out",
        "timeout",
        "connection aborted",
        "connection reset",
        "temporarily unavailable",
        "remote end closed connection",
        "remote disconnected",
    )
    return any(marker in text for marker in transient_markers)


def source_text_to_title(value, limit=120):
    lines = source_text_lines(value)
    if lines:
        return compact_error_text(lines[0], limit=limit)
    text = clean_text(value)
    if not text:
        return "\u539f\u5e16\u6807\u9898\u5f85\u8865\u5145"
    text = re.sub(r"\s*\n+\s*", " ", text)
    return compact_error_text(text, limit=limit)


def clean_source_line(value):
    text = clean_text(value)
    if not text:
        return ""
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" \t\r\n|·•-–—")
    text = re.sub(r"^[^\w@\u00C0-\u024F\u0400-\u04FF\u4e00-\u9fff]+", "", text)
    text = strip_source_ui_noise_prefix(text)
    text = strip_source_ui_noise_suffix(text)
    return clean_text(text)


SOURCE_ATTRIBUTION_ONLY_RE = re.compile(r"^(?:@[\w.]{1,32})(?:\s+@[\w.]{1,32})*$", re.I)
SOURCE_PUNCTUATION_ONLY_RE = re.compile(r"^[!?,.;:，。！？；：、…]+$")
SOURCE_INLINE_CONNECTOR_WORDS = {
    "a",
    "an",
    "and",
    "au",
    "aux",
    "con",
    "da",
    "de",
    "del",
    "des",
    "di",
    "do",
    "du",
    "e",
    "el",
    "en",
    "for",
    "im",
    "la",
    "le",
    "na",
    "no",
    "of",
    "para",
    "per",
    "por",
    "the",
    "to",
    "un",
    "una",
    "with",
    "y",
    "zu",
}


def is_source_attribution_line(value):
    text = clean_text(value)
    if not text:
        return False
    normalized = re.sub(r"\s+", " ", text).strip()
    return bool(SOURCE_ATTRIBUTION_ONLY_RE.fullmatch(normalized))


def source_line_ends_with_terminal_punctuation(value):
    text = clean_text(value)
    if not text:
        return False
    return bool(re.search(r"[.!?。！？…]+(?:['\"”’)\]]+)?$", text))


def source_line_starts_with_lowercase_fragment(value):
    text = clean_text(value)
    if not text:
        return False
    first = text[0]
    return first.islower() or first.isdigit()


def source_line_expects_inline_continuation(value):
    text = clean_text(value)
    if not text or source_line_ends_with_terminal_punctuation(text) or SOURCE_PUNCTUATION_ONLY_RE.fullmatch(text):
        return False
    words = re.findall(r"[@#]?[\w\u00C0-\u024F\u0400-\u04FF\u4e00-\u9fff']+", text.lower())
    if not words:
        return False
    last_word = words[-1].lstrip("@#")
    if last_word in SOURCE_INLINE_CONNECTOR_WORDS:
        return True
    return len(words) <= 3


def join_source_fragments(left, right):
    left_text = clean_text(left)
    right_text = clean_text(right)
    if not left_text:
        return right_text
    if not right_text:
        return left_text
    if SOURCE_PUNCTUATION_ONLY_RE.fullmatch(right_text):
        return clean_text(f"{left_text}{right_text}")
    return clean_text(f"{left_text} {right_text}")


def should_inline_merge_attribution_line(previous_line, next_line):
    previous = clean_text(previous_line)
    following = clean_text(next_line)
    if not previous:
        return False
    if source_line_expects_inline_continuation(previous):
        return True
    if not following:
        return False
    if SOURCE_PUNCTUATION_ONLY_RE.fullmatch(following):
        return True
    return source_line_starts_with_lowercase_fragment(following)


def should_merge_source_fragment(previous_line, line):
    previous = clean_text(previous_line)
    current = clean_text(line)
    if not previous or not current:
        return False
    if SOURCE_PUNCTUATION_ONLY_RE.fullmatch(current):
        return True
    if is_source_attribution_line(current):
        return False
    if source_line_starts_with_lowercase_fragment(current) and not source_line_ends_with_terminal_punctuation(previous):
        return True
    return source_line_expects_inline_continuation(previous)


SOURCE_RELATIVE_TIME_RE = re.compile(r"^\d+\s*(?:秒|分钟|小时|天|周|月|年|s|m|h|d)$", re.I)
SOURCE_ENGAGEMENT_COUNTS_RE = re.compile(r"^\d+(?:[.,]\d+)?(?:\s+\d+(?:[.,]\d+)?){0,7}$")
SOURCE_VIEW_COUNT_RE = re.compile(r"\bviews?\b|查看|浏览|次观看", re.I)
SOURCE_HANDLE_HEADER_RE = re.compile(r"^[A-Za-z0-9À-ÿ .'\-]+ @[\w.]{1,32}$", re.I)
SOURCE_HANDLE_TIME_PREFIX_RE = re.compile(
    r"^[A-Za-z0-9À-ÿ .'\-]+ @[\w.]{1,32}(?:\s+\d+\s*(?:秒|分钟|小时|天|周|月|年|s|m|h|d)){1,2}\s+",
    re.I,
)
SOURCE_LINK_CARD_RE = re.compile(r"^(?:来自|from)\s+\S+$", re.I)
SOURCE_LINK_CARD_SUFFIX_RE = re.compile(r"\s+(?:来自|from)\s+\S+(?:\s+\d+(?:[.,]\d+)?){0,8}$", re.I)
SOURCE_PAGER_RE = re.compile(r"^\d+\s+of\s+\d+$", re.I)
SOURCE_PAGER_PREFIX_RE = re.compile(r"^\d+\s+of\s+\d+\s+", re.I)


def strip_source_ui_noise_prefix(value):
    text = clean_text(value)
    if not text:
        return ""
    previous = None
    while text and text != previous:
        previous = text
        text = SOURCE_HANDLE_TIME_PREFIX_RE.sub("", text, count=1)
        text = SOURCE_PAGER_PREFIX_RE.sub("", text, count=1)
        text = re.sub(r"\s+", " ", text).strip(" \t\r\n|·•-–—")
    return clean_text(text)


def strip_source_ui_noise_suffix(value):
    text = clean_text(value)
    if not text:
        return ""
    previous = None
    while text and text != previous:
        previous = text
        text = SOURCE_LINK_CARD_SUFFIX_RE.sub("", text, count=1)
        text = re.sub(r"\s+\d+(?:[.,]\d+)?\s+views?$", "", text, flags=re.I)
        text = re.sub(r"\s+\d+\s+of\s+\d+(?:\s+\d+(?:[.,]\d+)?){1,8}$", "", text, flags=re.I)
        text = re.sub(r"\s+\d+\s+of\s+\d+$", "", text, flags=re.I)
        text = re.sub(r"(?:\s+\d+(?:[.,]\d+)?){2,8}$", "", text)
        text = re.sub(r"\s+\d+\s*(?:秒|分钟|小时|天|周|月|年|s|m|h|d)$", "", text, flags=re.I)
        text = re.sub(r"\s+", " ", text).strip(" \t\r\n|·•-–—")
    return clean_text(text)


def is_source_ui_noise_line(value):
    text = clean_text(value)
    if not text:
        return True
    normalized = re.sub(r"\s+", " ", strip_source_ui_noise_suffix(strip_source_ui_noise_prefix(text)) or text).strip()
    if not normalized:
        return True
    if is_source_attribution_line(normalized):
        return True
    if SOURCE_HANDLE_HEADER_RE.fullmatch(normalized):
        return True
    if SOURCE_LINK_CARD_RE.fullmatch(normalized):
        return True
    if SOURCE_PAGER_RE.fullmatch(normalized):
        return True
    if SOURCE_RELATIVE_TIME_RE.fullmatch(normalized):
        return True
    if SOURCE_ENGAGEMENT_COUNTS_RE.fullmatch(normalized):
        return True
    if SOURCE_VIEW_COUNT_RE.search(normalized):
        return True
    return False


def visible_line_span(raw_lines, visible_lines):
    normalized_raw_lines = [
        normalize_similarity_text(strip_source_ui_noise_suffix(strip_source_ui_noise_prefix(line)))
        for line in (raw_lines or [])
    ]
    normalized_visible_lines = [normalize_similarity_text(line) for line in (visible_lines or []) if normalize_similarity_text(line)]
    if not normalized_raw_lines or not normalized_visible_lines:
        return -1, -1
    first_match_index = -1
    search_start = 0
    for visible_line in normalized_visible_lines:
        match_index = -1
        for index in range(search_start, len(normalized_raw_lines)):
            raw_line = normalized_raw_lines[index]
            if raw_line == visible_line or raw_line.startswith(visible_line) or visible_line.startswith(raw_line):
                match_index = index
                break
        if match_index < 0:
            return -1, -1
        if first_match_index < 0:
            first_match_index = match_index
        search_start = match_index + 1
    return first_match_index, search_start - 1


def source_text_lines(value):
    text = clean_text(value)
    if not text:
        return []
    lines = []
    attribution_only_lines = []
    cleaned_lines = []
    for raw_line in re.split(r"\r?\n+", text):
        cleaned = clean_source_line(raw_line)
        if cleaned:
            cleaned_lines.append(cleaned)
    for index, cleaned in enumerate(cleaned_lines):
        if is_source_attribution_line(cleaned):
            next_line = next((line for line in cleaned_lines[index + 1 :] if line), "")
            if should_inline_merge_attribution_line(lines[-1] if lines else "", next_line):
                if lines:
                    lines[-1] = join_source_fragments(lines[-1], cleaned)
                else:
                    lines.append(cleaned)
                continue
            attribution_only_lines.append(cleaned)
            continue
        if lines and should_merge_source_fragment(lines[-1], cleaned):
            lines[-1] = join_source_fragments(lines[-1], cleaned)
            continue
        lines.append(cleaned)
    if lines:
        return lines
    if attribution_only_lines:
        return attribution_only_lines
    return lines


def filter_source_body_lines(lines, source_title=""):
    filtered_lines = []
    title_text = clean_text(source_title)
    for line in lines or []:
        cleaned_line = clean_text(line)
        if not cleaned_line or is_source_ui_noise_line(cleaned_line):
            continue
        if title_text and text_similarity_ratio(cleaned_line, title_text) >= 0.92:
            continue
        if filtered_lines and text_similarity_ratio(cleaned_line, filtered_lines[-1]) >= 0.97:
            continue
        filtered_lines.append(cleaned_line)
    return filtered_lines


def draft_source_title(item, limit=220):
    item_value = item or {}
    explicit = clean_text(item_value.get("source_title_text", ""))
    if explicit:
        return compact_error_text(explicit, limit=limit)
    lines = source_text_lines(item_value.get("text", ""))
    if lines:
        return compact_error_text(lines[0], limit=limit)
    raw_text = clean_text(item_value.get("raw_text", ""))
    if raw_text:
        return compact_error_text(raw_text, limit=limit)
    return source_text_to_title("", limit=limit)


def draft_source_body(item, limit=1200):
    item_value = item or {}
    explicit = clean_text(item_value.get("source_body_text", ""))
    if explicit:
        return compact_error_text(explicit, limit=limit)
    lines = source_text_lines(item_value.get("text", ""))
    source_title = clean_text(draft_source_title(item_value, limit=260))
    if len(lines) > 1:
        return compact_error_text("\n".join(lines[1:]), limit=limit)
    raw_lines = source_text_lines(item_value.get("raw_text", ""))
    if raw_lines:
        visible_start, visible_end = visible_line_span(raw_lines, lines)
        if visible_end >= 0:
            extra_raw_lines = []
            for line in raw_lines[visible_end + 1 :]:
                cleaned_line = strip_source_ui_noise_suffix(strip_source_ui_noise_prefix(line))
                if not cleaned_line or is_source_ui_noise_line(cleaned_line):
                    continue
                extra_raw_lines.append(cleaned_line)
            extra_raw_lines = filter_source_body_lines(extra_raw_lines, source_title=source_title)
            if extra_raw_lines:
                return compact_error_text("\n".join(extra_raw_lines), limit=limit)
            if lines:
                return ""
        visible_lines = {normalize_similarity_text(line) for line in lines if normalize_similarity_text(line)}
        extra_raw_lines = []
        for line in raw_lines:
            cleaned_line = strip_source_ui_noise_suffix(strip_source_ui_noise_prefix(line))
            normalized = normalize_similarity_text(cleaned_line)
            if not normalized or normalized in visible_lines or is_source_ui_noise_line(cleaned_line):
                continue
            extra_raw_lines.append(cleaned_line)
        extra_raw_lines = filter_source_body_lines(extra_raw_lines, source_title=source_title)
        if extra_raw_lines:
            return compact_error_text("\n".join(extra_raw_lines), limit=limit)
    if bool(item_value.get("has_external_link")):
        return ""
    cleaned_raw_text = "\n".join(
        cleaned_line
        for line in raw_lines
        for cleaned_line in [strip_source_ui_noise_suffix(strip_source_ui_noise_prefix(line))]
        if cleaned_line and not is_source_ui_noise_line(cleaned_line)
    )
    cleaned_tweet_text = "\n".join(lines)
    if cleaned_raw_text and cleaned_raw_text != cleaned_tweet_text:
        return compact_error_text(cleaned_raw_text, limit=limit)
    return ""


def draft_source_full_text(item, limit=1600):
    item_value = item or {}
    explicit = clean_text(item_value.get("source_full_text", ""))
    if explicit:
        return compact_error_text(explicit, limit=limit)
    source_title = clean_text(draft_source_title(item_value, limit=260))
    source_body = clean_text(draft_source_body(item_value, limit=max(260, limit)))
    full_text = combine_source_title_body(source_title, source_body)
    if full_text:
        return compact_error_text(full_text, limit=limit)
    text_value = clean_text(item_value.get("text", ""))
    if text_value:
        return compact_error_text(text_value, limit=limit)
    return compact_error_text(clean_text(item_value.get("raw_text", "")), limit=limit)


def duplicate_probe_text_from_item(item):
    title = clean_text(draft_source_title(item, limit=260))
    body = clean_text(draft_source_body(item, limit=1200))
    pieces = [piece for piece in (title, body) if piece]
    if pieces:
        return "\n".join(pieces)
    raw_lines = source_text_lines((item or {}).get("raw_text", ""))
    if raw_lines:
        return "\n".join(raw_lines)
    return clean_text((item or {}).get("text", ""))


def duplicate_probe_text_from_event(event):
    event_value = event or {}
    title = clean_text(event_value.get("source_title_text", ""))
    body = clean_text(event_value.get("source_body_text", ""))
    if not body:
        lines = source_text_lines(event_value.get("original_text", ""))
        if title and lines and normalize_similarity_text(lines[0]) == normalize_similarity_text(title):
            lines = lines[1:]
        body = "\n".join(lines)
    pieces = [piece for piece in (title, body) if piece]
    if pieces:
        return "\n".join(pieces)
    return clean_text(event_value.get("original_text", ""))


def item_reference_time(item, observed_at=""):
    item_value = item or {}
    return (
        parse_iso_datetime(item_value.get("created_at", ""))
        or parse_iso_datetime(item_value.get("raw_delivery_at", ""))
        or parse_iso_datetime(item_value.get("at", ""))
        or parse_iso_datetime(observed_at)
    )


def append_recent_event_entry(entries, event):
    target_tweet = str((event or {}).get("tweet_id", ""))
    event_target_key = target_key((event or {}).get("target_key", "")) or target_key((event or {}).get("mode", ""))
    merged = [
        entry
        for entry in list(entries or [])
        if not (
            str((entry or {}).get("tweet_id", "")) == target_tweet
            and (target_key((entry or {}).get("target_key", "")) or target_key((entry or {}).get("mode", ""))) == event_target_key
        )
    ]
    merged.append(dict(event or {}))
    return merged[-DEFAULT_RECENT_EVENTS_LIMIT:]


def find_recent_near_duplicate_event(recent_events, target_ref, item, observed_at, config):
    window_seconds = clamp_int(
        (config or {}).get("near_duplicate_window_seconds", DEFAULT_NEAR_DUPLICATE_WINDOW_SECONDS),
        DEFAULT_NEAR_DUPLICATE_WINDOW_SECONDS,
        minimum=0,
        maximum=3600,
    )
    if window_seconds <= 0:
        return None
    similarity_ratio = clamp_float(
        (config or {}).get("near_duplicate_similarity_ratio", DEFAULT_NEAR_DUPLICATE_SIMILARITY_RATIO),
        DEFAULT_NEAR_DUPLICATE_SIMILARITY_RATIO,
        minimum=0.85,
        maximum=1.0,
    )
    minimum_length = clamp_int(
        (config or {}).get("near_duplicate_min_text_length", DEFAULT_NEAR_DUPLICATE_MIN_TEXT_LENGTH),
        DEFAULT_NEAR_DUPLICATE_MIN_TEXT_LENGTH,
        minimum=8,
        maximum=500,
    )
    item_handle = clean_text((item or {}).get("handle", "")).lower()
    if not item_handle:
        return None
    candidate_text = duplicate_probe_text_from_item(item)
    normalized_candidate_text = normalize_similarity_text(candidate_text)
    if len(normalized_candidate_text) < minimum_length:
        return None
    item_target_key = target_key(target_ref)
    item_time = item_reference_time(item, observed_at)
    for event in reversed(list(recent_events or [])):
        if str((event or {}).get("tweet_id", "")) == str((item or {}).get("tweet_id", "")):
            continue
        if clean_text((event or {}).get("handle", "")).lower() != item_handle:
            continue
        event_target_key = target_key((event or {}).get("target_key", "")) or target_key((event or {}).get("mode", ""))
        if item_target_key and event_target_key and event_target_key != item_target_key:
            continue
        event_time = item_reference_time(event)
        if item_time and event_time and abs((item_time - event_time).total_seconds()) > window_seconds:
            continue
        event_text = normalize_similarity_text(duplicate_probe_text_from_event(event))
        if len(event_text) < minimum_length:
            continue
        if normalized_candidate_text == event_text:
            return event
        if SequenceMatcher(None, normalized_candidate_text, event_text).ratio() >= similarity_ratio:
            return event
    return None


def raw_title_for_display(value, limit=120):
    text = clean_text(value)
    if not text:
        return "\u65e0"
    text = re.sub(r"\s*\n+\s*", " ", text)
    return compact_error_text(text, limit=limit)


def x_attachment_labels_from_item(item):
    labels = []
    if bool((item or {}).get("is_repost")) and not item_is_filtered_repost(item):
        labels.append("转帖")
    if bool((item or {}).get("has_image")):
        labels.append("\u56fe\u7247")
    if bool((item or {}).get("has_video")):
        labels.append("\u89c6\u9891")
    if bool((item or {}).get("has_external_link")):
        labels.append("\u5916\u90e8\u94fe\u63a5")
    return labels


def x_banner_line_for_item(item):
    labels = x_attachment_labels_from_item(item)
    if not labels:
        return "\u2501\u2501\u3010X\u76d1\u63a7\u63a8\u9001\u3011\u2501\u2501"
    joined_labels = "\u3001".join(labels)
    return f"\u2501\u2501\u3010X\u76d1\u63a7\u63a8\u9001\u3011\uff08{joined_labels}\uff09\u2501\u2501"


def normalize_textless_draft_display(item, draft, placeholder_body, push_copy):
    source_text = clean_text((item or {}).get("text", ""))
    if source_text:
        return placeholder_body, push_copy
    return "\u65e0", "\u65e0"


AUDIENCE_META_MARKERS = (
    "\u5efa\u8bae\u7f16\u8f91",
    "\u8bf7\u7f16\u8f91",
    "\u7f16\u8f91\u63d0\u793a",
    "\u7f16\u8f91\u53ef",
    "\u5f85\u7a0d\u540e\u8865\u5168",
    "\u5f53\u524d\u5148\u4fdd\u7559\u751f\u8089",
    "\u7ed3\u5408\u539f\u5e16",
    "\u67e5\u770b\u539f\u5e16",
    "\u539f\u5e16\u94fe\u63a5",
    "\u539f\u5e16\u8f7d\u4f53",
    "\u518d\u66ff\u6362\u4e3a\u6b63\u5f0f\u5feb\u8baf",
    "\u66f4\u591a\u7ec6\u8282\u4ecd\u9700",
    "\u4ec5\u4f9d\u636e\u539f\u5e16\u6587\u5b57\u751f\u6210",
    "\u540e\u518d\u8865\u5168",
    "\u5177\u4f53\u5185\u5bb9\u672a\u8be6\u7ec6\u5c55\u5f00",
)


def sanitize_audience_sentence(text):
    value = clean_text(text)
    if not value:
        return ""
    for marker in AUDIENCE_META_MARKERS:
        if marker in value:
            return ""
    return compact_error_text(value, limit=320)


def sanitize_audience_placeholder_body(text):
    value = clean_text(text)
    if not value:
        return ""
    pieces = re.split(r"(?<=[。！？；])\s*", value)
    kept = [sanitize_audience_sentence(piece) for piece in pieces]
    kept = [piece for piece in kept if piece]
    if kept:
        joined = clean_text("".join(kept))
        if joined:
            return compact_error_text(joined, limit=320)
    if "\u5177\u4f53\u5185\u5bb9\u672a\u8be6\u7ec6\u5c55\u5f00" in value:
        trimmed = clean_text(value.replace("\u5177\u4f53\u5185\u5bb9\u672a\u8be6\u7ec6\u5c55\u5f00", ""))
        trimmed = re.sub(r"[，,；;。.!?]+$", "", trimmed)
        if trimmed:
            return compact_error_text(f"{trimmed}\u3002", limit=320)
    return "\u66f4\u591a\u4fe1\u606f\u4ee5\u5b98\u65b9\u540e\u7eed\u6d88\u606f\u4e3a\u51c6\u3002"


def sanitize_audience_push_copy(text, headline=""):
    value = clean_text(text)
    if value and not any(marker in value for marker in AUDIENCE_META_MARKERS):
        return compact_error_text(value, limit=100)
    headline_text = clean_text(headline)
    if headline_text and "\u53d1\u5e03\u65b0\u52a8\u6001" not in headline_text and "\u65b0\u52a8\u6001" not in headline_text:
        return compact_error_text(headline_text, limit=100)
    return "\u66f4\u591a\u4fe1\u606f\u4ee5\u5b98\u65b9\u540e\u7eed\u6d88\u606f\u4e3a\u51c6"


def sanitize_translation_text(text, limit=1400):
    value = clean_text(text)
    if not value:
        return ""
    kept = []
    for raw_line in re.split(r"\n+", value):
        line = clean_text(raw_line)
        if not line:
            continue
        if any(marker in line for marker in AUDIENCE_META_MARKERS):
            continue
        if SOURCE_LINK_CARD_RE.fullmatch(line):
            continue
        if SOURCE_PAGER_RE.fullmatch(line):
            continue
        if SOURCE_ENGAGEMENT_COUNTS_RE.fullmatch(line):
            continue
        if SOURCE_VIEW_COUNT_RE.fullmatch(line):
            continue
        if kept and text_similarity_ratio(line, kept[-1]) >= 0.97:
            continue
        kept.append(line)
    if not kept:
        return ""
    return compact_error_text("\n".join(kept), limit=limit)


def translation_looks_same_as_source(source_text, translated_text):
    source_value = sanitize_translation_text(source_text, limit=1600) or clean_text(source_text)
    translated_value = sanitize_translation_text(translated_text, limit=1600) or clean_text(translated_text)
    if not source_value or not translated_value:
        return False
    return text_similarity_ratio(source_value, translated_value) >= 0.97


def translation_matches_target_language(target_language, translated_text):
    target_value = clean_text(target_language).lower()
    translated_value = sanitize_translation_text(translated_text, limit=1600) or clean_text(translated_text)
    if not translated_value:
        return False
    if target_value.startswith("zh"):
        return bool(re.search(r"[\u4e00-\u9fff]", translated_value))
    return True


def text_needs_translation(text):
    value = clean_text(text)
    if not value:
        return False
    return bool(re.search(r"[A-Za-z\u00C0-\u024F\u0400-\u04FF]", value))


def looks_untranslated_machine_translation(source_text, translated_text):
    source_value = sanitize_translation_text(source_text, limit=1600) or clean_text(source_text)
    translated_value = sanitize_translation_text(translated_text, limit=1600) or clean_text(translated_text)
    if not source_value or not translated_value:
        return False
    if not text_needs_translation(source_value):
        return False
    if re.search(r"[\u4e00-\u9fff]", translated_value) and text_similarity_ratio(source_value, translated_value) < 0.9:
        return False
    return text_similarity_ratio(source_value, translated_value) >= 0.97


def translate_title(text, target_language, proxy_mapping=None):
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": target_language or DEFAULT_TRANSLATE_TO,
        "dt": "t",
        "q": cleaned,
    }
    resp = requests.get(
        "https://translate.googleapis.com/translate_a/single",
        params=params,
        proxies=proxy_mapping if proxy_mapping is not None else {"http": None, "https": None},
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    translated = "".join((part[0] or "") for part in (payload[0] or []) if part and part[0])
    return clean_text(translated) or cleaned


def build_raw_translated_title(config, item):
    source_text = draft_source_title(item, limit=260)
    fallback = raw_title_for_display(source_text)
    if not source_text:
        return fallback
    if is_emoji_passthrough_text(source_text):
        return compact_error_text(source_text, limit=120)
    try:
        translated = translate_title(
            source_text,
            clean_text(config.get("translate_to", DEFAULT_TRANSLATE_TO)) or DEFAULT_TRANSLATE_TO,
            proxy_mapping=requests_proxies(config, for_editor=False),
        )
    except Exception:
        translated = ""
    return compact_error_text(clean_text(translated) or fallback, limit=120)


def render_raw_message(item, observed_at=None):
    observed_value = observed_at or iso_now()
    delay_seconds = elapsed_seconds_between(item.get("created_at", ""), observed_value)
    raw_title = compact_error_text(
        clean_text((item or {}).get("raw_translated_title", "")) or raw_title_for_display(item.get("text", "")),
        limit=120,
    )
    delay_suffix = format_seconds_suffix("\u5ef6\u8fdf", delay_seconds)
    parts = [
        x_banner_line_for_item(item),
        f"\u8d26\u53f7\uff1a@{item.get('handle', '')}",
        "\u3010\u751f\u8089\u3011",
        f"\u6807\u9898\uff1a{raw_title}",
        f"\u751f\u8089\u63a8\u9001\u65f6\u95f4\uff1a{format_local_timestamp(observed_value)}{delay_suffix}",
        "\u3010\u719f\u8089\u3011",
        "\u6807\u9898\uff1a\u751f\u6210\u4e2d...",
        "\u5360\u4f4d\u7a3f\uff1a\u751f\u6210\u4e2d...",
        "PUSH\uff1a\u751f\u6210\u4e2d...",
        "\u719f\u8089\u5b8c\u6210\u65f6\u95f4\uff1a\u751f\u6210\u4e2d...",
        f"\u94fe\u63a5\uff1a{item.get('status_url', '')}",
    ]
    return "\n".join(part for part in parts if clean_text(part))


def render_translated_message(item, draft, delivered_at=None):
    delivered_value = delivered_at or clean_text((item or {}).get("delivered_at", "")) or iso_now()
    delay_seconds = elapsed_seconds_between(item.get("created_at", ""), delivered_value)
    delay_suffix = format_seconds_suffix("\u5ef6\u8fdf", delay_seconds)
    translation = sanitize_translation_text(clean_text((draft or {}).get("translation", "")), limit=1400)
    if not translation:
        translation = draft_source_full_text(item, limit=1400)
    draft_status = clean_text((draft or {}).get("draft_status", "")).lower()
    machine_translation_same_as_source = bool((draft or {}).get("machine_translation_same_as_source", False))
    processed_at = clean_text((draft or {}).get("draft_ready_at", ""))
    if draft_status in {"processed", "ready"}:
        status_text = "\u5df2\u5904\u7406"
    elif machine_translation_same_as_source:
        status_text = "\u5f85\u719f\u8089"
    elif draft_status in {"machine", "fallback", "pending"}:
        status_text = "\u673a\u7ffb"
    else:
        status_text = "\u673a\u7ffb"
    parts = [
        x_banner_line_for_item(item),
        f"\u8d26\u53f7\uff1a@{item.get('handle', '')}",
        "\u6b63\u6587\uff1a",
        translation,
        f"\u72b6\u6001\uff1a{status_text}",
        f"\u63a8\u9001\u65f6\u95f4\uff1a{format_local_timestamp(delivered_value)}{delay_suffix}",
        f"\u5904\u7406\u5b8c\u6210\u65f6\u95f4\uff1a{format_local_timestamp(processed_at)}" if status_text == "\u5df2\u5904\u7406" and processed_at else "",
        f"\u94fe\u63a5\uff1a{item.get('status_url', '')}",
    ]
    return "\n".join(part for part in parts if clean_text(part))


def render_draft_message(item, draft, raw_delivery_at):
    created_at = item.get("created_at", "")
    completed_at = draft.get("draft_ready_at", iso_now())
    raw_delay_seconds = elapsed_seconds_between(created_at, raw_delivery_at)
    draft_elapsed_seconds = elapsed_seconds_between(raw_delivery_at, completed_at)
    raw_delay_suffix = format_seconds_suffix("\u5ef6\u8fdf", raw_delay_seconds)
    draft_elapsed_suffix = format_seconds_suffix("\u8017\u65f6", draft_elapsed_seconds)
    raw_title = compact_error_text(
        clean_text((draft or {}).get("raw_translated_title", "")) or raw_title_for_display(item.get("text", "")),
        limit=120,
    )
    headline = compact_error_text(
        clean_text((draft or {}).get("headline", "")) or draft_source_title(item, limit=64),
        limit=64,
    )
    push_copy = compact_error_text(clean_text((draft or {}).get("push_copy", "")) or headline, limit=100)
    placeholder_body = clean_text((draft or {}).get("placeholder_body", "")) or "\u5b98\u65b9\u6682\u672a\u62ab\u9732\u66f4\u591a\u7ec6\u8282\u3002"
    placeholder_body, push_copy = normalize_textless_draft_display(item, draft, placeholder_body, push_copy)
    placeholder_body = sanitize_audience_placeholder_body(placeholder_body)
    push_copy = sanitize_audience_push_copy(push_copy, headline=headline)
    parts = [
        x_banner_line_for_item(item),
        f"\u8d26\u53f7\uff1a@{item.get('handle', '')}",
        "\u3010\u751f\u8089\u3011",
        f"\u6807\u9898\uff1a{raw_title}",
        f"\u751f\u8089\u63a8\u9001\u65f6\u95f4\uff1a{format_local_timestamp(raw_delivery_at)}{raw_delay_suffix}",
        "\u3010\u719f\u8089\u3011",
        f"\u6807\u9898\uff1a{headline}",
        f"\u5360\u4f4d\u7a3f\uff1a{placeholder_body}",
        f"PUSH\uff1a{push_copy}",
        f"\u719f\u8089\u5b8c\u6210\u65f6\u95f4\uff1a{format_local_timestamp(completed_at)}{draft_elapsed_suffix}",
        f"\u94fe\u63a5\uff1a{item.get('status_url', '')}",
    ]
    return "\n".join(part for part in parts if clean_text(part))


def append_recent_check(store, check):
    def updater(state):
        checks = list(state.get("recent_checks", []))
        checks.append(check)
        state["recent_checks"] = checks[-DEFAULT_RECENT_CHECKS_LIMIT:]
        target_id = target_key(check.get("target_key", "")) or target_key(check.get("mode", ""))
        if target_id:
            target_state = base_target_state()
            target_state.update(dict(state.get("targets", {}).get(target_id, {})))
            target_state["last_successful_check_at"] = check.get("at", "")
            target_state["current_top_tweet_id"] = clean_text(check.get("current_top_tweet_id", "")) or target_state.get("current_top_tweet_id", "")
            target_state["current_top_url"] = clean_text(check.get("current_top_url", "")) or target_state.get("current_top_url", "")
            state["targets"][target_id] = target_state
        state["last_successful_check_at"] = check.get("at", "")
        state["current_top_tweet_id"] = clean_text(check.get("current_top_tweet_id", "")) or state.get("current_top_tweet_id", "")
        state["current_top_url"] = clean_text(check.get("current_top_url", "")) or state.get("current_top_url", "")

    store.update_state(updater)
    try:
        store.append_check_archive(check)
    except Exception as exc:
        log_exception("append_check_archive", exc)


def remember_event(store, event, archive_event_type="delivery"):
    def updater(state):
        target_tweet = str(event.get("tweet_id", ""))
        event_target_key = target_key(event.get("target_key", "")) or target_key(event.get("mode", ""))
        events = [
            entry
            for entry in state.get("recent_events", [])
            if not (
                str(entry.get("tweet_id", "")) == target_tweet
                and (target_key(entry.get("target_key", "")) or target_key(entry.get("mode", ""))) == event_target_key
            )
        ]
        events.append(event)
        state["recent_events"] = events[-DEFAULT_RECENT_EVENTS_LIMIT:]

    store.update_state(updater)
    try:
        store.append_event_archive(event, archive_event_type=archive_event_type)
    except Exception as exc:
        log_exception(f"append_event_archive[{archive_event_type}]", exc)


def update_event(store, tweet_id, updates):
    def updater(state):
        target = str(tweet_id or "")
        events = []
        archived = []
        for entry in state.get("recent_events", []):
            merged = dict(entry)
            if str(merged.get("tweet_id", "")) == target:
                merged.update(updates or {})
                archived.append(dict(merged))
            events.append(merged)
        state["recent_events"] = events[-DEFAULT_RECENT_EVENTS_LIMIT:]
        return archived

    archived_events = store.update_state(updater) or []
    for event in archived_events:
        try:
            store.append_event_archive(event, archive_event_type="update")
        except Exception as exc:
            log_exception("append_event_archive[update]", exc)


def record_error(store, error_text):
    store.update_state(lambda state: state.__setitem__("last_error", compact_error_text(error_text, limit=500)))


def record_target_error(store, target_ref, error_text):
    def updater(state):
        target_id = target_key(target_ref)
        if target_id:
            target_state = base_target_state()
            target_state.update(dict(state.get("targets", {}).get(target_id, {})))
            target_state["last_error"] = compact_error_text(error_text, limit=500)
            state["targets"][target_id] = target_state
        state["last_error"] = compact_error_text(error_text, limit=500)

    store.update_state(updater)


def record_target_navigation_error(store, target_ref, target, observed_at, error_text, phase):
    compact_error = compact_error_text(error_text, limit=500)
    check = build_check_snapshot([], observed_at, target)
    check["error"] = compact_error
    check["navigation_error"] = True
    check["navigation_phase"] = clean_text(phase)
    if is_transient_page_navigation_error(compact_error):
        check["navigation_error_transient"] = True
    append_recent_check(store, check)
    record_target_error(store, target_ref, compact_error)
    return check


def classify_slot_intervention_error(message):
    text = compact_error_text(message, limit=500).lower()
    if not text:
        return ""
    login_required_markers = (
        "x auth is not ready",
        "login in the bot-4000 chrome profile",
        "browser profile cookies were not found",
        "no x/twitter cookies were found",
        "cookies were not found",
        "cookies missing",
        "cookies file missing",
        "auth_token",
        "ct0",
        "csrf",
        "slot config invalid",
        "slot binding config invalid",
        "slot config parse error",
        "login required",
        "not logged in",
        "logged out",
        "please log in",
        "please sign in",
        "sign in to x",
        "authentication required",
        "unauthorized",
        "could not authenticate you",
        "invalid or expired token",
        "profile missing",
    )
    locked_markers = (
        "your account is locked",
        "account is locked",
        "account/access",
        "unlock it",
    )
    verification_markers = (
        "verification",
        "verify",
        "challenge",
        "suspicious activity",
        "confirm your identity",
        "confirm it's you",
        "confirm it is you",
        "confirm your phone",
        "confirm your email",
        "unusual activity",
        "checkpoint",
    )
    if any(marker in text for marker in locked_markers):
        return "locked"
    if any(marker in text for marker in verification_markers):
        return "verification_required"
    if any(marker in text for marker in login_required_markers):
        return "login_required"
    return ""


def classify_runtime_restart_error(message):
    text = compact_error_text(message, limit=500).lower()
    if not text:
        return ""
    browser_closed_markers = (
        "target page, context or browser has been closed",
        "target closed",
        "browser has been closed",
        "context has been closed",
        "page has been closed",
        "connection closed while reading from the driver",
    )
    if any(marker in text for marker in browser_closed_markers):
        return "browser_crashed"
    return ""


def is_transient_page_navigation_error(message):
    text = compact_error_text(message, limit=500).lower()
    if not text:
        return False
    if classify_runtime_restart_error(text):
        return False
    navigation_markers = (
        "page.goto:",
        "page.reload:",
        "navigating to",
    )
    transient_markers = (
        "net::err_connection_closed",
        "net::err_timed_out",
        "timeout",
        "navigation timeout",
    )
    return any(marker in text for marker in navigation_markers) and any(marker in text for marker in transient_markers)


def intervention_kind_label(kind):
    if kind == "login_required":
        return "\u8d26\u53f7\u65e0\u6cd5\u767b\u5f55\u6216\u767b\u5f55\u6001\u5931\u6548"
    if kind == "locked":
        return "\u8d26\u53f7\u88ab\u5c01\u7981\u6216\u9501\u5b9a"
    if kind == "verification_required":
        return "\u8d26\u53f7\u9700\u8981\u9a8c\u8bc1"
    return "\u8d26\u53f7\u9700\u8981\u4eba\u5de5\u5904\u7406"


def runtime_restart_kind_label(kind):
    if kind == "browser_crashed":
        return "\u6d4f\u89c8\u5668\u6216\u9875\u9762\u4e0a\u4e0b\u6587\u5df2\u5173\u95ed"
    if kind == "persistent_empty_page":
        return "\u76ee\u6807\u9875\u9762\u6301\u7eed\u7a7a\u767d\uff0c\u5df2\u89e6\u53d1\u81ea\u6062\u590d\u91cd\u542f"
    if kind == "persistent_partial_page":
        return "\u76ee\u6807\u9875\u9762\u5185\u5bb9\u6b8b\u7f3a\uff0c\u5df2\u89e6\u53d1\u81ea\u6062\u590d\u91cd\u542f"
    return "\u8fd0\u884c\u65f6\u5f02\u5e38"


def slot_operator_action_status(state):
    return {
        "required": bool(state.get("slot_operator_action_required", False)),
        "detected_at": clean_text(state.get("slot_operator_action_required_at", "")),
        "kind": clean_text(state.get("slot_operator_action_required_kind", "")),
        "kind_label": intervention_kind_label(clean_text(state.get("slot_operator_action_required_kind", "")))
        if clean_text(state.get("slot_operator_action_required_kind", ""))
        else "",
        "error": clean_text(state.get("slot_operator_action_required_error", "")),
        "last_alert_at": clean_text(state.get("last_slot_operator_alert_at", "")),
        "last_alert_kind": clean_text(state.get("last_slot_operator_alert_kind", "")),
        "last_cleared_at": clean_text(state.get("last_slot_operator_action_cleared_at", "")),
    }


def auto_restart_status(state):
    return {
        "last_at": clean_text(state.get("last_auto_restart_at", "")),
        "last_kind": clean_text(state.get("last_auto_restart_kind", "")),
        "last_kind_label": runtime_restart_kind_label(clean_text(state.get("last_auto_restart_kind", "")))
        if clean_text(state.get("last_auto_restart_kind", ""))
        else "",
        "last_error": clean_text(state.get("last_auto_restart_error", "")),
        "count": clamp_int(state.get("auto_restart_count", 0), 0, minimum=0, maximum=999999),
        "last_result": clean_text(state.get("last_auto_restart_result", "")),
    }


def mark_slot_intervention_required(store, kind, detected_at, error_message):
    def updater(state):
        state["slot_operator_action_required"] = True
        state["slot_operator_action_required_at"] = str(detected_at or iso_now())
        state["slot_operator_action_required_kind"] = str(kind or "").strip()
        state["slot_operator_action_required_error"] = compact_error_text(error_message, limit=500)

    store.update_state(updater)


def clear_slot_intervention_required(store, cleared_at=None):
    def updater(state):
        if bool(state.get("slot_operator_action_required", False)):
            state["last_slot_operator_action_cleared_at"] = str(cleared_at or iso_now())
        state["slot_operator_action_required"] = False
        state["slot_operator_action_required_at"] = ""
        state["slot_operator_action_required_kind"] = ""
        state["slot_operator_action_required_error"] = ""
        state["last_slot_operator_alert_at"] = ""
        state["last_slot_operator_alert_kind"] = ""
        state["last_slot_operator_alert_error"] = ""

    store.update_state(updater)


def should_send_slot_intervention_alert(store, kind, error_message, current_time, cooldown_seconds):
    if not str(kind or "").strip():
        return False
    state = store.load_state()
    previous_kind = str(state.get("last_slot_operator_alert_kind", "")).strip()
    previous_error = compact_error_text(state.get("last_slot_operator_alert_error", ""), limit=500)
    current_error = compact_error_text(error_message, limit=500)
    if previous_kind != kind or previous_error != current_error:
        return True
    previous_alert_at = parse_iso_datetime(state.get("last_slot_operator_alert_at", ""))
    if previous_alert_at is None:
        return True
    observed_at = current_time or now_utc()
    return (observed_at - previous_alert_at).total_seconds() >= max(0, int(cooldown_seconds))


def mark_slot_intervention_alert_sent(store, kind, sent_at, error_message):
    def updater(state):
        state["last_slot_operator_alert_at"] = str(sent_at or iso_now())
        state["last_slot_operator_alert_kind"] = str(kind or "").strip()
        state["last_slot_operator_alert_error"] = compact_error_text(error_message, limit=500)

    store.update_state(updater)


def should_attempt_auto_restart(store, kind, error_message, current_time, cooldown_seconds):
    if not str(kind or "").strip():
        return False
    state = store.load_state()
    previous_at = parse_iso_datetime(state.get("last_auto_restart_at", ""))
    if previous_at is None:
        return True
    observed_at = current_time or now_utc()
    return (observed_at - previous_at).total_seconds() >= max(0, int(cooldown_seconds))


def mark_auto_restart_attempt(store, kind, attempted_at, error_message, result_text):
    def updater(state):
        previous_count = clamp_int(state.get("auto_restart_count", 0), 0, minimum=0, maximum=999999)
        state["last_auto_restart_at"] = str(attempted_at or iso_now())
        state["last_auto_restart_kind"] = str(kind or "").strip()
        state["last_auto_restart_error"] = compact_error_text(error_message, limit=500)
        state["last_auto_restart_result"] = compact_error_text(result_text, limit=500)
        state["auto_restart_count"] = previous_count + 1

    store.update_state(updater)


def build_browser_crash_alert(config, kind, error_message, mode="", restart_result=None):
    slot = normalize_source_slot(config.get("source_slot", DEFAULT_SOURCE_SLOT))
    lines = [
        "[Xplus\u6d4f\u89c8\u5668\u5f02\u5e38]",
        f"\u69fd\u4f4d\uff1a{source_slot_label(slot)}",
        f"\u95ee\u9898\uff1a{runtime_restart_kind_label(kind)}",
    ]
    normalized_mode = normalize_mode(mode)
    if normalized_mode:
        lines.append(f"\u6a21\u5f0f\uff1a{mode_label(normalized_mode)}")
    error_text = compact_error_text(error_message, limit=280)
    if error_text:
        lines.append(f"\u9519\u8bef\uff1a{error_text}")
    if isinstance(restart_result, dict):
        if restart_result.get("ok"):
            lines.append(f"\u5904\u7406\uff1a\u5df2\u81ea\u52a8\u91cd\u542f Xplus \u670d\u52a1\uff08PID {int(restart_result.get('pid', 0) or 0)}\uff09")
        elif clean_text(restart_result.get("error", "")) == "browser_crash_auto_restart_skipped":
            lines.append("\u5904\u7406\uff1a\u68c0\u6d4b\u5230\u6d4f\u89c8\u5668\u5d29\u6e83\uff0c\u4f46\u5f53\u524d\u5904\u4e8e\u81ea\u52a8\u91cd\u542f\u51b7\u5374\u671f\uff0c\u8bf7\u5c3d\u5feb\u624b\u52a8\u68c0\u67e5")
        else:
            lines.append("\u5904\u7406\uff1a\u81ea\u52a8\u91cd\u542f\u5931\u8d25\uff0c\u8bf7\u5c3d\u5feb\u624b\u52a8\u68c0\u67e5 Xplus \u72b6\u6001")
            restart_error = compact_error_text(
                restart_result.get("error", "") or restart_result.get("stderr", "") or restart_result.get("stdout", ""),
                limit=280,
            )
            if restart_error:
                lines.append(f"\u91cd\u542f\u7ed3\u679c\uff1a{restart_error}")
    else:
        lines.append("\u5904\u7406\uff1a\u68c0\u6d4b\u5230\u5f02\u5e38\uff0c\u6b63\u5728\u51c6\u5907\u81ea\u52a8\u91cd\u542f")
    return "\n".join(lines)


def build_slot_intervention_alert(config, kind, error_message, mode=""):
    slot = normalize_source_slot(config.get("source_slot", DEFAULT_SOURCE_SLOT))
    lines = [
        "[Xplus\u76d1\u63a7\u5f02\u5e38\u63d0\u9192]",
        f"\u69fd\u4f4d\uff1a{source_slot_label(slot)}",
        f"\u95ee\u9898\uff1a{intervention_kind_label(kind)}",
    ]
    normalized_mode = normalize_mode(mode)
    if normalized_mode:
        lines.append(f"\u6a21\u5f0f\uff1a{mode_label(normalized_mode)}")
    lines.append(
        "\u8bf7\u6253\u5f00\u8be5\u69fd\u4f4d\u5bf9\u5e94\u7684 X \u76d1\u63a7 Chrome\uff0c\u5904\u7406\u767b\u5f55\u3001\u9a8c\u8bc1\u6216\u89e3\u9501\u540e\uff0c\u518d\u89c2\u5bdf Xplus \u72b6\u6001\u3002"
    )
    if kind == "login_required":
        lines.append(
            "\u5efa\u8bae\uff1a\u786e\u8ba4\u8be5\u69fd\u4f4d\u7684\u76d1\u63a7\u8d26\u53f7\u4ecd\u7136\u767b\u5f55 X\uff0c\u6216\u91cd\u65b0\u540c\u6b65 cookies\u3002"
        )
    if kind == "verification_required":
        lines.append("\u5efa\u8bae\uff1a\u5c3d\u5feb\u5728 X \u9875\u9762\u5b8c\u6210\u5b89\u5168\u9a8c\u8bc1\u6216 challenge\u3002")
    if kind == "locked":
        lines.append("\u5efa\u8bae\uff1a\u8bbf\u95ee https://x.com/account/access \u67e5\u770b\u662f\u5426\u9700\u8981\u89e3\u9501\u3002")
    error_text = compact_error_text(error_message, limit=280)
    if error_text:
        lines.append(f"\u9519\u8bef\uff1a{error_text}")
    return "\n".join(lines)


def notify_slot_intervention_if_needed(store, config, error_message, observed_at=None, mode=""):
    kind = classify_slot_intervention_error(error_message)
    if not kind:
        return ""
    observed_dt = observed_at or now_utc()
    observed_at_text = observed_dt.isoformat()
    mark_slot_intervention_required(store, kind, observed_at_text, error_message)
    cooldown_seconds = slot_intervention_cooldown_seconds(config)
    if should_send_slot_intervention_alert(store, kind, error_message, observed_dt, cooldown_seconds):
        try:
            discord_send(config, build_slot_intervention_alert(config, kind, error_message, mode=mode))
            mark_slot_intervention_alert_sent(store, kind, observed_at_text, error_message)
        except Exception as exc:
            log_exception("send_slot_intervention_alert", exc)
    return kind


def clear_error(store):
    store.update_state(lambda state: state.__setitem__("last_error", ""))


def clear_target_error(store, target_ref):
    def updater(state):
        target_id = target_key(target_ref)
        if target_id:
            target_state = base_target_state()
            target_state.update(dict(state.get("targets", {}).get(target_id, {})))
            target_state["last_error"] = ""
            state["targets"][target_id] = target_state
        state["last_error"] = ""

    store.update_state(updater)


def update_auth_state(store, target_ref, ready, error_text="", current_top_tweet_id="", current_top_url=""):
    def updater(state):
        target_id = target_key(target_ref)
        if target_id:
            target_state = base_target_state()
            target_state.update(dict(state.get("targets", {}).get(target_id, {})))
            target_state["auth_ready"] = bool(ready)
            target_state["auth_error"] = compact_error_text(error_text, limit=500)
            if current_top_tweet_id:
                target_state["current_top_tweet_id"] = current_top_tweet_id
            if current_top_url:
                target_state["current_top_url"] = current_top_url
            state["targets"][target_id] = target_state
        state["auth_ready"] = bool(ready)
        state["auth_error"] = compact_error_text(error_text, limit=500)
        if current_top_tweet_id:
            state["current_top_tweet_id"] = current_top_tweet_id
        if current_top_url:
            state["current_top_url"] = current_top_url

    store.update_state(updater)


def trim_state_seen_ids(store, config):
    maximum = clamp_int(config.get("max_seen_ids", DEFAULT_MAX_SEEN_IDS), DEFAULT_MAX_SEEN_IDS, minimum=50, maximum=3000)

    def updater(state):
        state["seen_ids"] = trim_seen_ids(dict(state.get("seen_ids", {})), maximum)

    store.update_state(updater)
    if durable_seen_enabled(config):
        payload = load_seen_archive(store)
        items = trim_durable_seen_items(payload.get("items", {}), config)
        atomic_write_text(
            store.seen_archive_path,
            json.dumps({"version": 1, "updated_at": iso_now(), "items": items}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def mark_seen_ids(store, tweet_ids, stamp=None, config=None, target_ref=None):
    at = stamp or iso_now()
    maximum = DEFAULT_MAX_SEEN_IDS
    if config:
        maximum = clamp_int(config.get("max_seen_ids", DEFAULT_MAX_SEEN_IDS), DEFAULT_MAX_SEEN_IDS, minimum=50, maximum=3000)

    def updater(state):
        seen = dict(state.get("seen_ids", {}))
        for tweet_id in tweet_ids:
            value = clean_text(tweet_id)
            if value:
                seen[value] = at
        state["seen_ids"] = trim_seen_ids(seen, maximum)

    store.update_state(updater)
    mark_durable_seen_ids(store, tweet_ids, stamp=at, config=config or {}, target_ref=target_ref)


def profile_target_url(config):
    targets = enabled_targets(config)
    list_target = next((target for target in targets if target_mode(target) == MODE_LIST and clean_text(target.get("url", ""))), None)
    if list_target:
        return list_target["url"]
    home_target = next((target for target in targets if target["mode"] == MODE_HOME and clean_text(target.get("url", ""))), None)
    if home_target:
        return home_target["url"]
    return clean_text(config.get("x_list_url", "")) or clean_text(config.get("x_home_url", "")) or "https://x.com/home"


def find_chrome_executable():
    candidates = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def browser_channel_sequence(config):
    configured_channel = clean_text((config or {}).get("browser_channel", "auto")).lower() or "auto"
    if configured_channel in {"bundled", "playwright", "chromium"}:
        return [""]
    if configured_channel in {"auto", "default"}:
        return ["chrome", ""]
    return [configured_channel]


def browser_channel_label(channel):
    return clean_text(channel) or "playwright-chromium"


def open_profile_with_playwright(config, user_data_dir, target_url):
    if sync_playwright is None:
        return {"ok": False, "error": "playwright_python_package_not_installed"}
    launch_errors = []
    args = browser_launch_args(config)
    playwright = sync_playwright().start()
    context = None
    try:
        for browser_channel in browser_channel_sequence(config):
            try:
                launch_options = {
                    "headless": False,
                    "args": args,
                    "viewport": None,
                }
                if browser_channel:
                    launch_options["channel"] = browser_channel
                context = playwright.chromium.launch_persistent_context(str(user_data_dir), **launch_options)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(target_url, wait_until="domcontentloaded", timeout=DEFAULT_PAGE_TIMEOUT_MS)
                print(
                    f"[{iso_now()}] open_profile: opened {target_url} with {browser_channel_label(browser_channel)}. Close the browser window when login is done.",
                    flush=True,
                )
                while True:
                    time.sleep(1)
                    try:
                        if not context.pages:
                            break
                    except Exception:
                        break
                return {
                    "ok": True,
                    "action": "open_profile",
                    "profile_dir": str(user_data_dir),
                    "url": target_url,
                    "browser_channel": browser_channel_label(browser_channel),
                }
            except Exception as exc:
                launch_errors.append(f"channel={browser_channel_label(browser_channel)}: {exc}")
                try:
                    if context is not None:
                        context.close()
                except Exception:
                    pass
                context = None
        return {"ok": False, "error": "browser_launch_failed", "launch_errors": launch_errors}
    finally:
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        try:
            playwright.stop()
        except Exception:
            pass


def open_profile(store):
    config = runtime_config(store)
    slot_binding = load_x_monitor_slot_binding(config.get("source_slot", DEFAULT_SOURCE_SLOT))
    if not slot_binding_is_valid(slot_binding):
        return invalid_slot_binding_payload("open_profile", slot_binding, running=False)
    user_data_dir = Path(clean_text(config.get("x_browser_profile_dir", "")) or str(DEFAULT_BROWSER_PROFILE_DIR))
    user_data_dir.mkdir(parents=True, exist_ok=True)
    target_url = profile_target_url(config)
    configured_channel = clean_text(config.get("browser_channel", "auto")).lower() or "auto"
    if configured_channel in {"auto", "default", "chrome"}:
        chrome_path = find_chrome_executable()
        if chrome_path is not None:
            subprocess.Popen(
                [
                    str(chrome_path),
                    f"--user-data-dir={user_data_dir}",
                    "--profile-directory=Default",
                    target_url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=WINDOWS_CREATE_NO_WINDOW | WINDOWS_DETACHED_PROCESS | WINDOWS_CREATE_NEW_PROCESS_GROUP,
            )
            return {
                "ok": True,
                "action": "open_profile",
                "profile_dir": str(user_data_dir),
                "url": target_url,
                "browser_channel": "chrome",
            }
        if configured_channel == "chrome":
            return {"ok": False, "error": "chrome_not_found"}
    return open_profile_with_playwright(config, user_data_dir, target_url)


def load_saved_cookie_dict(config):
    path = Path(clean_text(config.get("x_cookies_path", "")) or str(LEGACY_X_MONITOR_COOKIES))
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return {str(key): str(value) for key, value in payload.items() if clean_text(key)}
    return {}


def build_playwright_cookies(config):
    cookie_dict = load_saved_cookie_dict(config)
    cookies = []
    if cookie_dict:
        for domain in (".x.com", ".twitter.com"):
            for name, value in cookie_dict.items():
                cookies.append(
                    {
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": "/",
                        "httpOnly": False,
                        "secure": True,
                        "sameSite": "Lax",
                    }
                )
    return cookies


def safe_locator_count(page, selector):
    try:
        return max(0, int(page.locator(selector).count() or 0))
    except Exception:
        return 0


def safe_body_text(page, timeout=1500):
    try:
        return clean_text(page.locator("body").inner_text(timeout=timeout))
    except Exception:
        return ""


def has_visible_timeline_items(page):
    selectors = (
        'article[data-testid="tweet"]',
        '[data-testid="cellInnerDiv"] article',
        'a[href*="/status/"] time',
    )
    for selector in selectors:
        if safe_locator_count(page, selector) > 0:
            return True
    return False


def has_authenticated_shell(page):
    selectors = (
        '[data-testid="SideNav_NewTweet_Button"]',
        'a[href="/home"]',
        'a[href="/explore"]',
        'a[href="/notifications"]',
        'nav[aria-label]',
    )
    for selector in selectors:
        if safe_locator_count(page, selector) > 0:
            return True
    return False


def detect_auth_issue(page):
    url = clean_text(getattr(page, "url", ""))
    lower_url = url.lower()
    if "login" in lower_url or "i/flow/login" in lower_url:
        return True, "login_required", compact_error_text(url or "x_login_page", limit=280)
    if "account/access" in lower_url:
        return True, "locked", compact_error_text(url or "x_account_access_page", limit=280)
    if has_visible_timeline_items(page):
        return False, "", ""
    if safe_locator_count(page, 'input[autocomplete="username"], input[name="text"]') > 0:
        return True, "login_required", compact_error_text(url or "x_login_form_visible", limit=280)
    verification_text = ""
    verification_selectors = (
        'input[name="challenge_response"]',
        '[data-testid="confirmationSheetConfirm"]',
        'a[href*="account/access"]',
        'form[action*="account/access"]',
    )
    for selector in verification_selectors:
        if safe_locator_count(page, selector) > 0:
            verification_text = safe_body_text(page, timeout=1500) or url or selector
            kind = "locked" if "account/access" in selector else "verification_required"
            return True, kind, compact_error_text(verification_text, limit=280)
    text = safe_body_text(page, timeout=1500)
    lower_text = text.lower()
    login_phrase_groups = (
        ("log in", "sign in"),
        ("\u767b\u5f55", "\u767b\u5165"),
        ("phone, email, or username", "forgot password"),
    )
    verification_phrase_groups = (
        ("confirm your identity", "challenge"),
        ("confirm it's you", "unusual activity"),
        ("confirm your email", "confirm your phone"),
        ("\u9a8c\u8bc1", "\u786e\u8ba4\u662f\u4f60"),
    )
    locked_phrase_groups = (
        ("your account is locked", "unlock it"),
        ("account is locked", "account/access"),
        ("\u89e3\u9501", "\u5e10\u6237\u88ab\u9501\u5b9a"),
    )
    if not has_authenticated_shell(page):
        for markers in locked_phrase_groups:
            if all(marker in lower_text for marker in markers):
                return True, "locked", compact_error_text(text or url, limit=280)
        for markers in verification_phrase_groups:
            if all(marker in lower_text for marker in markers):
                return True, "verification_required", compact_error_text(text or url, limit=280)
        for markers in login_phrase_groups:
            if all(marker in lower_text for marker in markers):
                return True, "login_required", compact_error_text(text or url, limit=280)
    return False, "", ""


def detect_loading_shell(page, body_text=""):
    if has_visible_timeline_items(page) or not has_authenticated_shell(page):
        return False, [], ""
    text = clean_text(body_text) or safe_body_text(page, timeout=DEFAULT_LOADING_SHELL_BODY_TIMEOUT_MILLISECONDS)
    lower_text = text.lower()
    signals = []
    for signal_name, selector in LOADING_SHELL_SIGNAL_SELECTORS:
        if safe_locator_count(page, selector) > 0:
            signals.append(signal_name)
    for marker, signal_name in LOADING_SHELL_TEXT_SIGNALS:
        haystack = lower_text if marker.isascii() else text
        needle = marker.lower() if marker.isascii() else marker
        if needle and needle in haystack:
            signals.append(signal_name)
    normalized_signals = list(dict.fromkeys(signal for signal in signals if clean_text(signal)))
    if normalized_signals:
        return True, normalized_signals, "authenticated_shell_loading_signals_present"
    return False, [], ""


def classify_page_surface_state(page):
    auth_issue, auth_kind, auth_reason = detect_auth_issue(page)
    if auth_issue:
        return {
            "state": "auth_issue",
            "reason": clean_text(auth_kind) or "auth_issue",
            "signals": [],
            "auth_kind": clean_text(auth_kind),
            "auth_reason": clean_text(auth_reason),
        }
    if has_visible_timeline_items(page):
        return {
            "state": "ready",
            "reason": "visible_timeline_items_present",
            "signals": [],
            "auth_kind": "",
            "auth_reason": "",
        }
    body_text = safe_body_text(page, timeout=DEFAULT_LOADING_SHELL_BODY_TIMEOUT_MILLISECONDS)
    is_loading_shell, signals, loading_reason = detect_loading_shell(page, body_text=body_text)
    if is_loading_shell:
        return {
            "state": "loading_shell",
            "reason": loading_reason,
            "signals": signals,
            "auth_kind": "",
            "auth_reason": "",
        }
    return {
        "state": "hard_empty",
        "reason": "no_visible_timeline_items_after_auth_and_loading_checks",
        "signals": [],
        "auth_kind": "",
        "auth_reason": "",
    }


def extract_visible_items_with_meta(page, top_count):
    script = """
() => {
  const origin = location.origin;
  const out = [];
  const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
  const stats = {
    domArticleCount: articles.length,
    inspectedArticleCount: 0,
    missingTweetIdCount: 0,
    duplicateTweetIdCount: 0,
  };
  const canonicalOrigin = 'https://x.com';
  const reservedHandlePaths = new Set([
    'compose',
    'download',
    'explore',
    'hashtag',
    'home',
    'i',
    'intent',
    'jobs',
    'login',
    'messages',
    'notifications',
    'privacy',
    'search',
    'settings',
    'share',
    'signup',
    'tos',
  ]);
  const toAbsolute = (value) => {
    try {
      return new URL(value, origin).href;
    } catch (error) {
      return "";
    }
  };
  const normalizeHost = (value) => value.toLowerCase().replace(/^www\\./, '').replace(/^mobile\\./, '');
  const parseStatusCandidate = (href) => {
    if (!href) {
      return { tweetId: "", handle: "", statusUrl: "" };
    }
    try {
      const url = new URL(href, origin);
      const host = normalizeHost(url.hostname || "");
      if (!['x.com', 'twitter.com'].includes(host)) {
        return { tweetId: "", handle: "", statusUrl: "" };
      }
      const pathname = (url.pathname || "").replace(/\\/+$/, "");
      let match = pathname.match(/^\\/([^\\/?#]+)\\/status\\/(\\d+)(?:\\/[^?#]+)?$/i);
      if (match) {
        return {
          tweetId: match[2],
          handle: match[1],
          statusUrl: `${canonicalOrigin}/${match[1]}/status/${match[2]}`,
        };
      }
      match = pathname.match(/^\\/i\\/web\\/status\\/(\\d+)(?:\\/[^?#]+)?$/i);
      if (match) {
        return {
          tweetId: match[1],
          handle: "",
          statusUrl: `${canonicalOrigin}/i/web/status/${match[1]}`,
        };
      }
    } catch (error) {
    }
    return { tweetId: "", handle: "", statusUrl: "" };
  };
  const parseHandleCandidate = (href) => {
    if (!href) {
      return "";
    }
    try {
      const url = new URL(href, origin);
      const host = normalizeHost(url.hostname || "");
      if (!['x.com', 'twitter.com'].includes(host)) {
        return "";
      }
      const pathname = (url.pathname || "").replace(/\\/+$/, "");
      const match = pathname.match(/^\\/([A-Za-z0-9_]{1,32})$/);
      if (!match) {
        return "";
      }
      const handle = (match[1] || "").trim();
      if (!handle || reservedHandlePaths.has(handle.toLowerCase())) {
        return "";
      }
      return handle;
    } catch (error) {
      return "";
    }
  };
  const unique = new Set();
  for (const article of articles) {
    stats.inspectedArticleCount += 1;
    const links = Array.from(article.querySelectorAll('a[href]')).map((node) => toAbsolute(node.getAttribute('href'))).filter(Boolean);
    const timeStatusHref = toAbsolute(article.querySelector('time')?.closest('a[href]')?.getAttribute('href') || "");
    const statusCandidateLinks = [
      timeStatusHref,
      ...Array.from(article.querySelectorAll('a[href*="/status/"], a[href*="/i/web/status/"]')).map((node) => toAbsolute(node.getAttribute('href'))),
      ...links,
    ].filter(Boolean);
    let statusInfo = { tweetId: "", handle: "", statusUrl: "" };
    for (const href of statusCandidateLinks) {
      statusInfo = parseStatusCandidate(href);
      if (statusInfo.tweetId) {
        break;
      }
    }
    const tweetId = statusInfo.tweetId || "";
    if (!tweetId) {
      stats.missingTweetIdCount += 1;
      continue;
    }
    if (unique.has(tweetId)) {
      stats.duplicateTweetIdCount += 1;
      continue;
    }
    unique.add(tweetId);
    const userNameLinks = Array.from(article.querySelectorAll('[data-testid="User-Name"] a[href]')).map((node) => toAbsolute(node.getAttribute('href'))).filter(Boolean);
    let handle = statusInfo.handle || "";
    if (!handle) {
      for (const href of [...userNameLinks, ...links]) {
        handle = parseHandleCandidate(href);
        if (handle) {
          break;
        }
      }
    }
    const statusUrl = handle ? `${canonicalOrigin}/${handle}/status/${tweetId}` : (statusInfo.statusUrl || "");
    const createdAt = article.querySelector('time')?.getAttribute('datetime') || "";
    const socialContext = (article.querySelector('[data-testid="socialContext"]')?.innerText || "").trim();
    const photoNode = article.querySelector('[data-testid="tweetPhoto"]');
    const photoHasStillImage = !!(photoNode && (
      photoNode.querySelector('img') !== null
      || /background-image\\s*:/i.test(photoNode.innerHTML || '')
      || ((photoNode.getAttribute('aria-label') || '').trim())
      || Array.from(photoNode.querySelectorAll('[aria-label]')).some((node) => ((node.getAttribute('aria-label') || '').trim()))
    ));
    const photoLooksLikeVideo = !!(photoNode && !photoHasStillImage && photoNode.querySelector('[role="progressbar"]') !== null);
    const hasVideo = article.querySelector('[data-testid="videoPlayer"]') !== null
      || article.querySelector('video') !== null
      || links.some((href) => /\\/video\\/\\d+/i.test(href))
      || photoLooksLikeVideo;
    const hasImage = (photoNode !== null || links.some((href) => /\\/photo\\/\\d+/i.test(href))) && !hasVideo;
    const hasCard = article.querySelector('[data-testid="card.wrapper"]') !== null;
    const hasExternalLink = hasCard || links.some((href) => {
      try {
        const host = new URL(href).hostname.toLowerCase().replace(/^www\\./, '');
        return host && !['x.com', 'twitter.com', 'pic.twitter.com', 't.co'].includes(host);
      } catch (error) {
        return false;
      }
    });
    const tweetTextBlocks = Array.from(article.querySelectorAll('[data-testid="tweetText"]'))
      .map((node) => (node.innerText || "").trim())
      .filter(Boolean);
    const tweetText = tweetTextBlocks.join("\\n");
    out.push({
      tweet_id: tweetId,
      handle: handle,
      status_url: statusUrl,
      created_at: createdAt,
      social_context: socialContext,
      has_image: hasImage,
      has_video: hasVideo,
      has_external_link: hasExternalLink,
      text: tweetText,
      text_blocks: tweetTextBlocks.slice(0, 6),
      raw_text: (article.innerText || "").trim().slice(0, 2400),
    });
    if (out.length >= %d) {
      break;
    }
  }
  return { items: out, stats };
}
""" % int(top_count)
    raw_result = page.evaluate(script)
    raw_items = []
    raw_stats = {}
    if isinstance(raw_result, dict):
        raw_items = list(raw_result.get("items", []) or [])
        raw_stats = dict(raw_result.get("stats", {}) or {})
    else:
        raw_items = list(raw_result or [])
    items = []
    for entry in raw_items or []:
        raw_text = clean_text(entry.get("raw_text", ""))
        tweet_text = clean_text(entry.get("text", ""))
        handle = clean_text(entry.get("handle", ""))
        social_context = clean_text(entry.get("social_context", ""))
        repost_context = extract_repost_context(raw_text, tweet_text, handle=handle, social_context=social_context)
        teaser_context = extract_teaser_context(tweet_text, has_external_link=bool(entry.get("has_external_link")))
        item_value = {
            "tweet_id": clean_text(entry.get("tweet_id", "")),
            "handle": handle,
            "status_url": clean_text(entry.get("status_url", "")),
            "created_at": clean_text(entry.get("created_at", "")),
            "social_context": social_context,
            "has_image": bool(entry.get("has_image")),
            "has_video": bool(entry.get("has_video")),
            "has_external_link": bool(entry.get("has_external_link")),
            "text": tweet_text,
            "text_blocks": [clean_text(value) for value in list(entry.get("text_blocks", []) or []) if clean_text(value)],
            "raw_text": raw_text,
            "is_repost": bool(repost_context),
            "repost_context": repost_context,
            "is_teaser": bool(teaser_context),
            "teaser_context": teaser_context,
        }
        repost_filter_reason = classify_repost_filter_reason(item_value)
        item_value["repost_filter_reason"] = repost_filter_reason
        item_value["is_filtered_repost"] = bool(repost_filter_reason)
        items.append(item_value)
    sorted_items = sort_items_by_created_at([item for item in items if item.get("tweet_id")])
    visible_items = visible_items_from_items(sorted_items)
    extract_meta = {
        "extract_dom_article_count": clamp_int(raw_stats.get("domArticleCount", 0), 0, minimum=0, maximum=500),
        "extract_inspected_article_count": clamp_int(raw_stats.get("inspectedArticleCount", 0), 0, minimum=0, maximum=500),
        "extract_id_extracted_count": len(sorted_items),
        "extract_id_missing_count": clamp_int(raw_stats.get("missingTweetIdCount", 0), 0, minimum=0, maximum=500),
        "extract_duplicate_tweet_id_count": clamp_int(raw_stats.get("duplicateTweetIdCount", 0), 0, minimum=0, maximum=500),
        "extract_visible_count": len(visible_items),
    }
    return sorted_items, extract_meta


def extract_visible_items(page, top_count):
    items, _ = extract_visible_items_with_meta(page, top_count)
    return items


def empty_page_retry_settings(config, recovery=False):
    retry_count = clamp_int(
        config.get("empty_page_retry_count", DEFAULT_EMPTY_PAGE_RETRY_COUNT),
        DEFAULT_EMPTY_PAGE_RETRY_COUNT,
        minimum=0,
        maximum=12,
    )
    retry_delay_ms = clamp_int(
        config.get("empty_page_retry_delay_milliseconds", DEFAULT_EMPTY_PAGE_RETRY_DELAY_MILLISECONDS),
        DEFAULT_EMPTY_PAGE_RETRY_DELAY_MILLISECONDS,
        minimum=250,
        maximum=5000,
    )
    if recovery:
        retry_count = min(retry_count, DEFAULT_EMPTY_PAGE_RECOVERY_RETRY_COUNT_CAP)
        retry_delay_ms = min(retry_delay_ms, DEFAULT_EMPTY_PAGE_RECOVERY_RETRY_DELAY_MILLISECONDS_CAP)
    else:
        retry_count = min(retry_count, DEFAULT_EMPTY_PAGE_INITIAL_RETRY_COUNT_CAP)
        retry_delay_ms = min(retry_delay_ms, DEFAULT_EMPTY_PAGE_INITIAL_RETRY_DELAY_MILLISECONDS_CAP)
    return retry_count, retry_delay_ms


def extract_visible_items_with_retry(page, config, stop_event=None, recovery=False):
    top_count = clamp_int(
        config.get("top_scan_count", DEFAULT_TOP_SCAN_COUNT),
        DEFAULT_TOP_SCAN_COUNT,
        minimum=1,
        maximum=20,
    )
    retry_count, retry_delay_ms = empty_page_retry_settings(config, recovery=recovery)
    items, extract_meta = extract_visible_items_with_meta(page, top_count)
    retries_used = 0
    while not items and retries_used < retry_count:
        if stop_event is not None and stop_event.is_set():
            break
        page.wait_for_timeout(retry_delay_ms)
        retries_used += 1
        items, extract_meta = extract_visible_items_with_meta(page, top_count)
    extract_meta = dict(extract_meta or {})
    extract_meta["extract_attempt_count"] = retries_used + 1
    return items, retries_used, extract_meta


def supplement_items_for_candidate_gap(page, config, items, extract_meta, stop_event=None):
    meta = dict(extract_meta or {})
    dom_article_count = clamp_int(meta.get("extract_dom_article_count", 0), 0, minimum=0, maximum=500)
    candidate_count = len(list(items or []))
    id_missing_count = clamp_int(meta.get("extract_id_missing_count", 0), 0, minimum=0, maximum=500)
    minimum_dom_article_count = clamp_int(
        DEFAULT_CANDIDATE_GAP_SUPPLEMENT_MIN_DOM_ARTICLE_COUNT,
        DEFAULT_CANDIDATE_GAP_SUPPLEMENT_MIN_DOM_ARTICLE_COUNT,
        minimum=1,
        maximum=50,
    )
    minimum_gap = clamp_int(
        DEFAULT_CANDIDATE_GAP_SUPPLEMENT_MIN_GAP,
        DEFAULT_CANDIDATE_GAP_SUPPLEMENT_MIN_GAP,
        minimum=1,
        maximum=20,
    )
    current_gap = max(0, dom_article_count - candidate_count)
    if dom_article_count < minimum_dom_article_count or current_gap < minimum_gap or id_missing_count <= 0:
        return list(items or []), {}
    attempts = clamp_int(
        DEFAULT_CANDIDATE_GAP_SUPPLEMENT_ATTEMPTS,
        DEFAULT_CANDIDATE_GAP_SUPPLEMENT_ATTEMPTS,
        minimum=0,
        maximum=3,
    )
    settle_milliseconds = clamp_int(
        DEFAULT_CANDIDATE_GAP_SUPPLEMENT_SETTLE_MILLISECONDS,
        DEFAULT_CANDIDATE_GAP_SUPPLEMENT_SETTLE_MILLISECONDS,
        minimum=150,
        maximum=3000,
    )
    top_count = clamp_int(
        config.get("top_scan_count", DEFAULT_TOP_SCAN_COUNT),
        DEFAULT_TOP_SCAN_COUNT,
        minimum=1,
        maximum=50,
    )
    merged_items = list(items or [])
    latest_meta = dict(meta)
    attempts_used = 0
    for _ in range(attempts):
        if stop_event is not None and stop_event.is_set():
            break
        page.wait_for_timeout(settle_milliseconds)
        attempts_used += 1
        supplement_items, latest_meta = extract_visible_items_with_meta(page, top_count)
        merged_items = merge_items_by_tweet_id(merged_items, supplement_items)
        latest_dom_article_count = clamp_int(latest_meta.get("extract_dom_article_count", 0), 0, minimum=0, maximum=500)
        latest_id_missing_count = clamp_int(latest_meta.get("extract_id_missing_count", 0), 0, minimum=0, maximum=500)
        latest_gap = max(0, latest_dom_article_count - len(merged_items))
        if latest_gap < minimum_gap or latest_id_missing_count <= 0:
            break
    if not attempts_used:
        return merged_items, {}
    return (
        merged_items,
        {
            "candidate_gap_supplement_attempts": attempts_used,
            "candidate_gap_supplement_candidate_count": len(merged_items),
            "candidate_gap_supplement_dom_article_count": clamp_int(latest_meta.get("extract_dom_article_count", 0), 0, minimum=0, maximum=500),
            "candidate_gap_supplement_id_missing_count": clamp_int(latest_meta.get("extract_id_missing_count", 0), 0, minimum=0, maximum=500),
        },
    )


def supplement_items_with_light_scroll(page, target, config, items, stop_event=None):
    if target_mode(target) != MODE_LIST:
        return list(items or []), {}
    minimum_visible_count = partial_page_min_visible_count(config, target)
    if minimum_visible_count <= 0:
        return list(items or []), {}
    visible_count = len(visible_items_from_items(items))
    if visible_count >= minimum_visible_count:
        return list(items or []), {}
    attempts = clamp_int(
        DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_ATTEMPTS,
        DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_ATTEMPTS,
        minimum=0,
        maximum=3,
    )
    settle_milliseconds = clamp_int(
        DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_SETTLE_MILLISECONDS,
        DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_SETTLE_MILLISECONDS,
        minimum=200,
        maximum=5000,
    )
    step_pixels = clamp_int(
        DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_STEP_PIXELS,
        DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_STEP_PIXELS,
        minimum=300,
        maximum=2400,
    )
    top_count = clamp_int(
        config.get("top_scan_count", DEFAULT_TOP_SCAN_COUNT),
        DEFAULT_TOP_SCAN_COUNT,
        minimum=1,
        maximum=50,
    )
    merged_items = list(items or [])
    attempts_used = 0
    for _ in range(attempts):
        if stop_event is not None and stop_event.is_set():
            break
        page.evaluate(
            """
() => {
  const viewport = Math.max(window.innerHeight || 0, 600);
  const top = Math.max(%d, Math.floor(viewport * 0.9));
  window.scrollBy(0, top);
  return window.scrollY || document.documentElement.scrollTop || 0;
}
"""
            % int(step_pixels)
        )
        page.wait_for_timeout(settle_milliseconds)
        attempts_used += 1
        merged_items = merge_items_by_tweet_id(merged_items, extract_visible_items(page, top_count))
        if len(visible_items_from_items(merged_items)) >= minimum_visible_count:
            break
    if attempts_used:
        try:
            page.evaluate(
                """
() => {
  window.scrollTo(0, 0);
  return window.scrollY || document.documentElement.scrollTop || 0;
}
"""
            )
            page.wait_for_timeout(min(300, settle_milliseconds))
        except Exception:
            pass
        return (
            merged_items,
            {
                "light_scroll_supplement_attempts": attempts_used,
                "light_scroll_supplement_visible_count": len(visible_items_from_items(merged_items)),
            },
        )
    return merged_items, {}


def perform_zero_item_light_scroll(page, config, stop_event=None):
    attempts = clamp_int(
        DEFAULT_ZERO_ITEM_SCROLL_RECOVERY_ATTEMPTS,
        DEFAULT_ZERO_ITEM_SCROLL_RECOVERY_ATTEMPTS,
        minimum=0,
        maximum=3,
    )
    settle_milliseconds = clamp_int(
        DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_SETTLE_MILLISECONDS,
        DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_SETTLE_MILLISECONDS,
        minimum=200,
        maximum=5000,
    )
    step_pixels = clamp_int(
        DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_STEP_PIXELS,
        DEFAULT_PARTIAL_PAGE_SCROLL_SUPPLEMENT_STEP_PIXELS,
        minimum=300,
        maximum=2400,
    )
    attempts_used = 0
    for _ in range(attempts):
        if stop_event is not None and stop_event.is_set():
            break
        page.evaluate(
            """
() => {
  const viewport = Math.max(window.innerHeight || 0, 600);
  const top = Math.max(%d, Math.floor(viewport * 0.9));
  window.scrollBy(0, top);
  return window.scrollY || document.documentElement.scrollTop || 0;
}
"""
            % int(step_pixels)
        )
        page.wait_for_timeout(settle_milliseconds)
        attempts_used += 1
        try:
            page.evaluate(
                """
() => {
  window.scrollTo(0, 0);
  return window.scrollY || document.documentElement.scrollTop || 0;
}
"""
            )
            page.wait_for_timeout(min(300, settle_milliseconds))
        except Exception:
            pass
    return {
        "zero_item_scroll_attempts": attempts_used,
        "zero_item_scroll_settle_milliseconds": settle_milliseconds,
    }


def collect_target_items(page, target, config, stop_event=None, recovery=False):
    items, empty_page_retries_used, extract_meta = extract_visible_items_with_retry(
        page,
        config,
        stop_event=stop_event,
        recovery=recovery,
    )
    meta = dict(extract_meta or {})
    if empty_page_retries_used:
        meta["empty_page_retries_used"] = empty_page_retries_used
    if items:
        items, candidate_gap_meta = supplement_items_for_candidate_gap(
            page,
            config,
            items,
            extract_meta,
            stop_event=stop_event,
        )
        meta.update(candidate_gap_meta)
        items, supplement_meta = supplement_items_with_light_scroll(
            page,
            target,
            config,
            items,
            stop_event=stop_event,
        )
        meta.update(supplement_meta)
    return items, meta


def stale_refresh_light_scroll_recheck(page, target, config, items, previous_top_tweet_id="", stop_event=None):
    if not stale_refresh_light_scroll_recheck_enabled(config) or target_mode(target) != MODE_LIST:
        return list(items or []), {}
    settings = stale_refresh_light_scroll_recheck_settings(config)
    attempts = settings["attempts"]
    if attempts <= 0:
        return list(items or []), {}
    current_items = list(items or [])
    current_top = first_visible_tweet_id(current_items)
    previous_top = clean_text(previous_top_tweet_id)
    if current_top and previous_top and current_top != previous_top:
        return current_items, {}
    merged_items = list(current_items)
    attempts_used = 0
    collect_meta = {}
    for _ in range(attempts):
        if stop_event is not None and stop_event.is_set():
            break
        page.evaluate(
            """
() => {
  const viewport = Math.max(window.innerHeight || 0, 600);
  const top = Math.max(%d, Math.floor(viewport * 0.75));
  window.scrollBy(0, top);
  return window.scrollY || document.documentElement.scrollTop || 0;
}
"""
            % int(settings["step_pixels"])
        )
        page.wait_for_timeout(settings["settle_milliseconds"])
        attempts_used += 1
        rechecked_items, meta = collect_target_items(page, target, config, stop_event=stop_event, recovery=True)
        collect_meta = dict(meta or {})
        merged_items = merge_items_by_tweet_id(rechecked_items, merged_items)
        new_top = first_visible_tweet_id(merged_items)
        if new_top and previous_top and new_top != previous_top:
            break
    if attempts_used:
        try:
            page.evaluate(
                """
() => {
  window.scrollTo(0, 0);
  return window.scrollY || document.documentElement.scrollTop || 0;
}
"""
            )
            page.wait_for_timeout(min(300, settings["settle_milliseconds"]))
        except Exception:
            pass
    if not attempts_used:
        return merged_items, {}
    return merged_items, {
        "stale_refresh_light_scroll_recheck_attempts": attempts_used,
        "stale_refresh_light_scroll_recheck_visible_count": len(visible_items_from_items(merged_items)),
        "stale_refresh_light_scroll_recheck_previous_top_tweet_id": previous_top,
        "stale_refresh_light_scroll_recheck_top_tweet_id": first_visible_tweet_id(merged_items),
        "stale_refresh_light_scroll_recheck_collect_meta": collect_meta,
    }


def join_recovery_actions(actions):
    return ",".join(dict.fromkeys(clean_text(action) for action in (actions or []) if clean_text(action)))


def page_settle_milliseconds(config, recovery=False):
    default_value = DEFAULT_EMPTY_PAGE_RECOVERY_SETTLE_MILLISECONDS if recovery else DEFAULT_SETTLE_MILLISECONDS
    key = "empty_page_recovery_settle_milliseconds" if recovery else "page_settle_milliseconds"
    value = clamp_int(
        config.get(key, default_value),
        default_value,
        minimum=300 if recovery else 500,
        maximum=10000,
    )
    if recovery:
        value = min(value, DEFAULT_EMPTY_PAGE_RECOVERY_SETTLE_MILLISECONDS_CAP)
    return value


def empty_page_restart_threshold(config):
    return clamp_int(
        config.get("empty_page_restart_threshold", DEFAULT_EMPTY_PAGE_RESTART_THRESHOLD),
        DEFAULT_EMPTY_PAGE_RESTART_THRESHOLD,
        minimum=1,
        maximum=10,
    )


def multi_target_empty_page_restart_threshold(config, total_targets):
    if clamp_int(total_targets, 0, minimum=0, maximum=50) < 2:
        return 0
    return clamp_int(
        config.get("multi_target_empty_page_restart_threshold", DEFAULT_MULTI_TARGET_EMPTY_PAGE_RESTART_THRESHOLD),
        DEFAULT_MULTI_TARGET_EMPTY_PAGE_RESTART_THRESHOLD,
        minimum=2,
        maximum=10,
    )


def empty_page_wave_recovery_cooldown_seconds(config):
    return clamp_int(
        config.get(
            "empty_page_wave_recovery_cooldown_seconds",
            DEFAULT_EMPTY_PAGE_WAVE_RECOVERY_COOLDOWN_SECONDS,
        ),
        DEFAULT_EMPTY_PAGE_WAVE_RECOVERY_COOLDOWN_SECONDS,
        minimum=0,
        maximum=3600,
    )


def empty_page_wave_canary_enabled(config):
    return config_bool(
        (config or {}).get("empty_page_wave_canary_enabled", DEFAULT_EMPTY_PAGE_WAVE_CANARY_ENABLED),
        DEFAULT_EMPTY_PAGE_WAVE_CANARY_ENABLED,
    )


def empty_page_wave_canary_wait_milliseconds(config):
    return clamp_int(
        (config or {}).get(
            "empty_page_wave_canary_wait_milliseconds",
            DEFAULT_EMPTY_PAGE_WAVE_CANARY_WAIT_MILLISECONDS,
        ),
        DEFAULT_EMPTY_PAGE_WAVE_CANARY_WAIT_MILLISECONDS,
        minimum=300,
        maximum=15000,
    )


def latest_empty_page_wave_recovery_at(state):
    for entry in reversed(list((state or {}).get("recent_events", []))):
        if clean_text(entry.get("event_type", "")) == "empty_page_wave_auto_recover":
            return clean_text(entry.get("at", ""))
    return ""


def empty_page_wave_recovery_cooldown_ready(state, config, observed_at):
    cooldown_seconds = empty_page_wave_recovery_cooldown_seconds(config)
    if cooldown_seconds <= 0:
        return True
    latest_at = latest_empty_page_wave_recovery_at(state)
    if not latest_at:
        return True
    age = elapsed_seconds_between(latest_at, observed_at)
    return age is None or age >= cooldown_seconds


def should_trigger_multi_target_empty_page_restart(failing_targets, total_targets, config, state=None, observed_at=""):
    threshold = multi_target_empty_page_restart_threshold(config, total_targets)
    if threshold <= 0:
        return False
    unique_targets = [clean_text(target) for target in (failing_targets or []) if clean_text(target)]
    unique_targets = list(dict.fromkeys(unique_targets))
    if len(unique_targets) < threshold:
        return False
    if state is not None and clean_text(observed_at):
        return empty_page_wave_recovery_cooldown_ready(state, config, observed_at)
    return True


def empty_page_fast_reopen_restart_threshold(config, total_targets):
    total_value = clamp_int(total_targets, 0, minimum=0, maximum=50)
    if total_value <= 0:
        return 0
    default_value = DEFAULT_EMPTY_PAGE_FAST_REOPEN_RESTART_THRESHOLD
    return clamp_int(
        config.get("empty_page_fast_reopen_restart_threshold", default_value),
        default_value,
        minimum=1,
        maximum=max(1, total_value),
    )


def should_restart_after_fast_reopen_empty(failing_targets, total_targets, config, state=None, observed_at=""):
    threshold = empty_page_fast_reopen_restart_threshold(config, total_targets)
    if threshold <= 0:
        return False
    unique_targets = [clean_text(target) for target in (failing_targets or []) if clean_text(target)]
    unique_targets = list(dict.fromkeys(unique_targets))
    if len(unique_targets) < threshold:
        return False
    if state is not None and clean_text(observed_at):
        return empty_page_wave_recovery_cooldown_ready(state, config, observed_at)
    return True


def empty_page_priority_recheck_settings(config):
    recheck_count = clamp_int(
        config.get("empty_page_priority_recheck_count", DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_COUNT),
        DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_COUNT,
        minimum=0,
        maximum=6,
    )
    recheck_delay_ms = clamp_int(
        config.get(
            "empty_page_priority_recheck_delay_milliseconds",
            DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_DELAY_MILLISECONDS,
        ),
        DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_DELAY_MILLISECONDS,
        minimum=300,
        maximum=15000,
    )
    recheck_count = max(recheck_count, DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_COUNT)
    recheck_delay_ms = min(recheck_delay_ms, DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_DELAY_MILLISECONDS)
    return recheck_count, recheck_delay_ms


def partial_page_min_visible_count(config, target=None):
    default_value = DEFAULT_PARTIAL_PAGE_MIN_VISIBLE_COUNT if target_mode(target) == MODE_LIST else 0
    return clamp_int(
        config.get("partial_page_min_visible_count", default_value),
        default_value,
        minimum=0,
        maximum=20,
    )


def browser_launch_args(config):
    args = ["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"]
    if config_bool(
        config.get("browser_lightweight_mode", DEFAULT_BROWSER_LIGHTWEIGHT_MODE),
        DEFAULT_BROWSER_LIGHTWEIGHT_MODE,
    ):
        args.extend(
            [
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-default-apps",
                "--disable-sync",
                "--mute-audio",
                "--no-default-browser-check",
                "--no-first-run",
                "--disable-features=MediaRouter,OptimizationHints,Translate",
            ]
        )
    if config_bool(
        config.get("browser_disable_images", DEFAULT_BROWSER_DISABLE_IMAGES),
        DEFAULT_BROWSER_DISABLE_IMAGES,
    ):
        args.append("--blink-settings=imagesEnabled=false")
    proxy_value = clean_text(config.get("x_proxy", ""))
    if proxy_value:
        args.append(f"--proxy-server={proxy_value}")
    return list(dict.fromkeys(arg for arg in args if clean_text(arg)))


def navigate_to_target_page(page, target, config, recovery=False):
    page.goto(
        clean_text(target.get("url", "")),
        wait_until="domcontentloaded",
        timeout=clamp_int(config.get("page_timeout_ms", DEFAULT_PAGE_TIMEOUT_MS), DEFAULT_PAGE_TIMEOUT_MS, minimum=5000, maximum=120000),
    )
    page.wait_for_timeout(page_settle_milliseconds(config, recovery=recovery))


def mark_target_reloaded(store, target_ref, reloaded_at):
    def updater(state):
        target_id = target_key(target_ref)
        if not target_id:
            return
        target_state = base_target_state()
        target_state.update(dict(state.get("targets", {}).get(target_id, {})))
        target_state["last_reload_at"] = clean_text(reloaded_at)
        state["targets"][target_id] = target_state
        state["last_reload_at"] = target_state["last_reload_at"]

    store.update_state(updater)


def reload_target_page(page, target, config, store=None, target_ref="", recovery=False):
    page.reload(
        wait_until="domcontentloaded",
        timeout=clamp_int(config.get("page_timeout_ms", DEFAULT_PAGE_TIMEOUT_MS), DEFAULT_PAGE_TIMEOUT_MS, minimum=5000, maximum=120000),
    )
    page.wait_for_timeout(page_settle_milliseconds(config, recovery=recovery))
    reloaded_at = iso_now()
    if store is not None and target_ref:
        mark_target_reloaded(store, target_ref, reloaded_at)
    return page, reloaded_at


def reopen_target_page(context, current_page, target, config, store=None, target_ref=""):
    new_page = context.new_page()
    try:
        navigate_to_target_page(new_page, target, config, recovery=True)
    except Exception:
        try:
            new_page.close()
        except Exception:
            pass
        raise
    try:
        current_page.close()
    except Exception:
        pass
    reloaded_at = iso_now()
    if store is not None and target_ref:
        mark_target_reloaded(store, target_ref, reloaded_at)
    return new_page, reloaded_at


def recover_items_from_loading_shell(page, target, config, store=None, target_ref="", stop_event=None):
    current_page = page
    recovery_steps = []
    recovery_collect_meta = {}
    zero_item_scroll_attempts = 0
    final_surface = {"state": "loading_shell", "reason": "", "signals": []}
    if stop_event is not None and stop_event.is_set():
        return current_page, [], {"steps": recovery_steps, "collect_meta": recovery_collect_meta, "final_surface": final_surface}
    current_page.wait_for_timeout(DEFAULT_LOADING_SHELL_WAIT_MILLISECONDS)
    recovery_steps.append("wait")
    zero_item_scroll_meta = perform_zero_item_light_scroll(current_page, config, stop_event=stop_event)
    zero_item_scroll_attempts = int(zero_item_scroll_meta.get("zero_item_scroll_attempts", 0) or 0)
    if zero_item_scroll_attempts:
        recovery_steps.append("zero_item_scroll")
    items, meta = collect_target_items(current_page, target, config, stop_event=stop_event, recovery=True)
    recovery_collect_meta = dict(meta or {})
    if items or (stop_event is not None and stop_event.is_set()):
        return current_page, items, {
            "steps": recovery_steps,
            "collect_meta": recovery_collect_meta,
            "zero_item_scroll_attempts": zero_item_scroll_attempts,
            "final_surface": {"state": "ready", "reason": "visible_timeline_items_present", "signals": []},
        }
    final_surface = classify_page_surface_state(current_page)
    if clean_text(final_surface.get("state", "")) != "loading_shell":
        return current_page, [], {
            "steps": recovery_steps,
            "collect_meta": recovery_collect_meta,
            "zero_item_scroll_attempts": zero_item_scroll_attempts,
            "final_surface": final_surface,
        }
    current_page, _ = reload_target_page(current_page, target, config, store=store, target_ref=target_ref, recovery=True)
    recovery_steps.append("reload")
    items, meta = collect_target_items(current_page, target, config, stop_event=stop_event, recovery=True)
    recovery_collect_meta = dict(meta or {})
    if items or (stop_event is not None and stop_event.is_set()):
        return current_page, items, {
            "steps": recovery_steps,
            "collect_meta": recovery_collect_meta,
            "zero_item_scroll_attempts": zero_item_scroll_attempts,
            "final_surface": {"state": "ready", "reason": "visible_timeline_items_present", "signals": []},
        }
    final_surface = classify_page_surface_state(current_page)
    return current_page, [], {
        "steps": recovery_steps,
        "collect_meta": recovery_collect_meta,
        "zero_item_scroll_attempts": zero_item_scroll_attempts,
        "final_surface": final_surface,
    }


def recover_items_from_empty_page(context, pages, target_ref, target, page, config, store, stop_event=None):
    current_page = page
    recovery_steps = []
    retries_used = 0
    light_scroll_attempts = 0
    light_scroll_visible_count = 0
    recovery_collect_meta = {}
    priority_rechecks_used = 0
    if stop_event is not None and stop_event.is_set():
        return current_page, [], {"steps": recovery_steps, "retries_used": retries_used}
    current_page, _ = reload_target_page(current_page, target, config, store=store, target_ref=target_ref, recovery=True)
    recovery_steps.append("reload")
    items, meta = collect_target_items(current_page, target, config, stop_event=stop_event, recovery=True)
    recovery_collect_meta = dict(meta or {})
    retries_used += int(meta.get("empty_page_retries_used", 0) or 0)
    light_scroll_attempts += int(meta.get("light_scroll_supplement_attempts", 0) or 0)
    light_scroll_visible_count = max(light_scroll_visible_count, int(meta.get("light_scroll_supplement_visible_count", 0) or 0))
    pages[target_ref] = current_page
    if items or (stop_event is not None and stop_event.is_set()):
        return current_page, items, {"steps": recovery_steps, "retries_used": retries_used, "light_scroll_attempts": light_scroll_attempts, "light_scroll_visible_count": light_scroll_visible_count, "collect_meta": recovery_collect_meta}
    current_page, _ = reopen_target_page(context, current_page, target, config, store=store, target_ref=target_ref)
    recovery_steps.append("reopen")
    items, meta = collect_target_items(current_page, target, config, stop_event=stop_event, recovery=True)
    recovery_collect_meta = dict(meta or {})
    retries_used += int(meta.get("empty_page_retries_used", 0) or 0)
    light_scroll_attempts += int(meta.get("light_scroll_supplement_attempts", 0) or 0)
    light_scroll_visible_count = max(light_scroll_visible_count, int(meta.get("light_scroll_supplement_visible_count", 0) or 0))
    pages[target_ref] = current_page
    if items or (stop_event is not None and stop_event.is_set()):
        return current_page, items, {"steps": recovery_steps, "retries_used": retries_used, "light_scroll_attempts": light_scroll_attempts, "light_scroll_visible_count": light_scroll_visible_count, "collect_meta": recovery_collect_meta, "priority_rechecks_used": priority_rechecks_used}
    priority_recheck_count, priority_recheck_delay_ms = empty_page_priority_recheck_settings(config)
    for _ in range(priority_recheck_count):
        if stop_event is not None and stop_event.is_set():
            break
        current_page.wait_for_timeout(priority_recheck_delay_ms)
        priority_rechecks_used += 1
        if "priority_recheck" not in recovery_steps:
            recovery_steps.append("priority_recheck")
        items, meta = collect_target_items(current_page, target, config, stop_event=stop_event, recovery=True)
        recovery_collect_meta = dict(meta or {})
        retries_used += int(meta.get("empty_page_retries_used", 0) or 0)
        light_scroll_attempts += int(meta.get("light_scroll_supplement_attempts", 0) or 0)
        light_scroll_visible_count = max(light_scroll_visible_count, int(meta.get("light_scroll_supplement_visible_count", 0) or 0))
        pages[target_ref] = current_page
        if items:
            break
    return current_page, items, {"steps": recovery_steps, "retries_used": retries_used, "light_scroll_attempts": light_scroll_attempts, "light_scroll_visible_count": light_scroll_visible_count, "collect_meta": recovery_collect_meta, "priority_rechecks_used": priority_rechecks_used}


def auto_recover_target_page(context, pages, target_ref, target, page, config, store, reason):
    current_page, recovered_at = reopen_target_page(context, page, target, config, store=store, target_ref=target_ref)
    pages[target_ref] = current_page
    event_at = recovered_at or iso_now()
    remember_event(
        store,
        {
            "at": event_at,
            "event_type": "target_page_auto_recover",
            "tweet_id": f"target-page-auto-recover:{target_ref}:{event_at}",
            "target_key": target_ref,
            "mode": target.get("mode", ""),
            "mode_label": target.get("label", ""),
            "target_name": clean_text(target.get("name", "")) or clean_text(target.get("label", "")),
            "list_index": int(target.get("list_index", 0) or 0),
            "target_url": clean_text(target.get("url", "")),
            "recovery_scope": "page",
            "reason": clean_text(reason),
        },
    )
    return current_page, {
        "recovery_scope": "page",
        "reason": clean_text(reason),
        "recovered_at": event_at,
    }


def fast_reopen_and_collect_target_page(context, pages, target_ref, target, page, config, store, reason, stop_event=None):
    current_page, recover_meta = auto_recover_target_page(
        context,
        pages,
        target_ref,
        target,
        page,
        config,
        store,
        reason=reason,
    )
    collect_meta = {}
    if stop_event is not None and stop_event.is_set():
        return current_page, [], {"steps": ["page_auto_recover"], "collect_meta": collect_meta, "auto_recover": recover_meta}
    items, collect_meta = collect_target_items(
        current_page,
        target,
        config,
        stop_event=stop_event,
        recovery=True,
    )
    return current_page, items, {
        "steps": ["page_auto_recover", "post_reopen_collect"],
        "retries_used": int((collect_meta or {}).get("empty_page_retries_used", 0) or 0),
        "light_scroll_attempts": int((collect_meta or {}).get("light_scroll_supplement_attempts", 0) or 0),
        "light_scroll_visible_count": int((collect_meta or {}).get("light_scroll_supplement_visible_count", 0) or 0),
        "collect_meta": dict(collect_meta or {}),
        "auto_recover": recover_meta,
    }


def full_reload_and_collect_target_page(page, target_ref, target, config, store, reason, stop_event=None):
    current_page, reloaded_at = reload_target_page(
        page,
        target,
        config,
        store=store,
        target_ref=target_ref,
        recovery=True,
    )
    event_at = reloaded_at or iso_now()
    remember_event(
        store,
        {
            "at": event_at,
            "event_type": "target_page_auto_recover",
            "tweet_id": f"target-page-auto-recover:{target_ref}:{event_at}",
            "target_key": target_ref,
            "mode": target.get("mode", ""),
            "mode_label": target.get("label", ""),
            "target_name": clean_text(target.get("name", "")) or clean_text(target.get("label", "")),
            "list_index": int(target.get("list_index", 0) or 0),
            "target_url": clean_text(target.get("url", "")),
            "recovery_scope": "page",
            "reason": clean_text(reason),
        },
    )
    collect_meta = {}
    if stop_event is not None and stop_event.is_set():
        return current_page, [], {"steps": ["reload"], "collect_meta": collect_meta, "reloaded_at": event_at}
    items, collect_meta = collect_target_items(
        current_page,
        target,
        config,
        stop_event=stop_event,
        recovery=True,
    )
    return current_page, items, {
        "steps": ["reload", "post_reload_collect"],
        "retries_used": int((collect_meta or {}).get("empty_page_retries_used", 0) or 0),
        "light_scroll_attempts": int((collect_meta or {}).get("light_scroll_supplement_attempts", 0) or 0),
        "light_scroll_visible_count": int((collect_meta or {}).get("light_scroll_supplement_visible_count", 0) or 0),
        "collect_meta": dict(collect_meta or {}),
        "reloaded_at": event_at,
    }


def recover_multi_target_empty_page_wave(
    context,
    pages,
    targets,
    failing_targets,
    config,
    store,
    stop_event=None,
):
    target_map = {target_key(target): target for target in (targets or []) if target_key(target)}
    target_ids = [clean_text(target_id) for target_id in (failing_targets or []) if clean_text(target_id)]
    target_ids = list(dict.fromkeys(target_ids))
    recovered_targets = []
    rebuilt_targets = []
    failed_targets_info = []
    if empty_page_wave_canary_enabled(config) and len(target_ids) >= 2:
        canary_index = stable_jitter_int(
            ":".join(
                [
                    "empty-page-wave-canary",
                    normalize_source_slot((config or {}).get("source_slot", DEFAULT_SOURCE_SLOT)),
                    ",".join(target_ids),
                ]
            ),
            len(target_ids) - 1,
        )
        canary_target_id = target_ids[canary_index]
        canary_target = target_map.get(canary_target_id)
        canary_page = pages.get(canary_target_id)
        canary_wait_ms = empty_page_wave_canary_wait_milliseconds(config)
        canary_items = []
        canary_collect_meta = {}
        canary_error = ""
        if canary_target is not None and canary_page is not None:
            try:
                canary_page.wait_for_timeout(canary_wait_ms)
                canary_items, canary_collect_meta = collect_target_items(
                    canary_page,
                    canary_target,
                    config,
                    stop_event=stop_event,
                    recovery=True,
                )
            except Exception as exc:
                canary_error = compact_error_text(str(exc), limit=280)
        else:
            canary_error = "canary_target_missing"
        if not canary_items:
            event_at = iso_now()
            remember_event(
                store,
                {
                    "at": event_at,
                    "event_type": "empty_page_wave_auto_recover",
                    "tweet_id": f"empty-page-wave-canary-backoff:{event_at}",
                    "target_key": ",".join(target_ids),
                    "mode": MODE_LIST,
                    "mode_label": mode_label(MODE_LIST),
                    "recovery_scope": "wave",
                    "recovery_action": "canary_backoff",
                    "reason": "empty_page_wave_canary_backoff",
                    "canary_target": canary_target_id,
                    "canary_wait_milliseconds": canary_wait_ms,
                    "canary_error": canary_error,
                    "canary_visible_count": len(visible_items_from_items(canary_items)),
                    "canary_collect_meta": dict(canary_collect_meta or {}),
                    "recovered_targets": [],
                    "rebuilt_targets": [],
                    "failed_targets": failed_targets_info,
                },
            )
            return {
                "action": "canary_backoff",
                "recovered_targets": [],
                "rebuilt_targets": [],
                "failed_targets": failed_targets_info,
                "canary_target": canary_target_id,
                "canary_wait_milliseconds": canary_wait_ms,
                "canary_error": canary_error,
                "canary_visible_count": len(visible_items_from_items(canary_items)),
            }
        recovered_targets.append(canary_target_id)
        target_ids = [target_id for target_id in target_ids if target_id != canary_target_id]
    for target_id in target_ids:
        if stop_event is not None and stop_event.is_set():
            break
        target = target_map.get(target_id)
        current_page = pages.get(target_id)
        if target is None or current_page is None:
            continue
        try:
            current_page.wait_for_timeout(DEFAULT_EMPTY_PAGE_WAVE_PROBE_WAIT_MILLISECONDS)
            items, _ = collect_target_items(
                current_page,
                target,
                config,
                stop_event=stop_event,
                recovery=True,
            )
            if items:
                recovered_targets.append(target_id)
                continue
        except Exception as exc:
            failed_targets_info.append(
                {
                    "target_key": target_id,
                    "stage": "probe",
                    "error": compact_error_text(str(exc), limit=280),
                }
            )
            continue
        try:
            current_page, _ = auto_recover_target_page(
                context,
                pages,
                target_id,
                target,
                current_page,
                config,
                store,
                reason="empty_page_wave",
            )
            pages[target_id] = current_page
            rebuilt_targets.append(target_id)
        except Exception as exc:
            failed_targets_info.append(
                {
                    "target_key": target_id,
                    "stage": "rebuild",
                    "error": compact_error_text(str(exc), limit=280),
                }
            )
    recovered_target_ids = list(dict.fromkeys(recovered_targets + rebuilt_targets))
    if recovered_target_ids:
        event_at = iso_now()
        remember_event(
            store,
            {
                "at": event_at,
                "event_type": "empty_page_wave_auto_recover",
                "tweet_id": f"empty-page-wave-auto-recover:{event_at}",
                "target_key": ",".join(recovered_target_ids),
                "mode": MODE_LIST,
                "mode_label": mode_label(MODE_LIST),
                "recovery_scope": "wave",
                "recovery_action": "page_rebuild",
                "reason": "empty_page_wave",
                "recovered_targets": recovered_target_ids,
                "rebuilt_targets": list(dict.fromkeys(rebuilt_targets)),
                "failed_targets": failed_targets_info,
            },
        )
    return {
        "action": "page_rebuild",
        "recovered_targets": recovered_target_ids,
        "rebuilt_targets": list(dict.fromkeys(rebuilt_targets)),
        "failed_targets": failed_targets_info,
    }


def initialize_browser_context(config):
    if sync_playwright is None:
        raise RuntimeError("playwright_python_package_not_installed")
    args = browser_launch_args(config)
    playwright = sync_playwright().start()
    preferred_headless = config_bool(config.get("browser_headless", True), True)
    launch_errors = []
    browser = None
    context = None
    configured_channel = clean_text(config.get("browser_channel", "auto")).lower() or "auto"
    browser_channels = browser_channel_sequence(config)
    for headless_value in ([preferred_headless, False] if preferred_headless else [False]):
        for browser_channel in browser_channels:
            try:
                launch_options = {"headless": headless_value, "args": args}
                if browser_channel:
                    launch_options["channel"] = browser_channel
                browser = playwright.chromium.launch(**launch_options)
                context = browser.new_context()
                cookies = build_playwright_cookies(config)
                if cookies:
                    context.add_cookies(cookies)
                if browser_channel != configured_channel:
                    fallback_label = browser_channel_label(browser_channel)
                    print(f"[{iso_now()}] initialize_browser_context: using browser channel {fallback_label}", flush=True)
                if headless_value != preferred_headless:
                    print(f"[{iso_now()}] initialize_browser_context: headless launch failed, fell back to headful mode", flush=True)
                break
            except Exception as exc:
                channel_label = browser_channel_label(browser_channel)
                launch_errors.append(f"channel={channel_label}, headless={headless_value}: {exc}")
                try:
                    if context is not None:
                        context.close()
                except Exception:
                    pass
                context = None
                try:
                    if browser is not None:
                        browser.close()
                except Exception:
                    pass
                browser = None
        if context is not None:
            break
        if headless_value is False:
            try:
                playwright.stop()
            except Exception:
                pass
            raise RuntimeError(" ; ".join(launch_errors))
    if context is None:
        try:
            playwright.stop()
        except Exception:
            pass
        raise RuntimeError("browser_context_launch_failed")
    context.add_init_script(
        """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
"""
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(clamp_int(config.get("page_timeout_ms", DEFAULT_PAGE_TIMEOUT_MS), DEFAULT_PAGE_TIMEOUT_MS, minimum=5000, maximum=120000))
    return playwright, browser, context, page


def warm_target_page(store, config, executor, target, target_page, observed_at, stop_event=None):
    items, collect_meta = collect_target_items(
        target_page,
        target,
        config,
        stop_event=stop_event,
    )
    if not items:
        return False
    partial_page_meta = detect_partial_page(items, target, config, state=store.load_state(), observed_at=observed_at)
    if partial_page_meta:
        return False
    check = build_check_snapshot(items, observed_at, target)
    attach_initial_collect_meta(check, collect_meta)
    check["baseline_tweet_ids"] = maybe_bootstrap(store, config, target, items, observed_at)
    check["new_tweet_ids"] = handle_new_items(store, config, executor, target, items, observed_at, delivery_context=check)
    annotate_check_with_hot_list_acceleration(check, store, target, config, observed_at)
    update_auth_state(
        store,
        target_key(target),
        True,
        "",
        current_top_tweet_id=check.get("current_top_tweet_id", ""),
        current_top_url=check.get("current_top_url", ""),
    )
    clear_target_error(store, target_key(target))
    clear_error(store)
    append_recent_check(store, check)
    return True


def build_check_snapshot(items, observed_at, target):
    raw_items = list(items or [])
    visible_items = visible_items_from_items(raw_items)
    top_item = visible_items[0] if visible_items else {}
    repost_candidate_count = sum(1 for item in raw_items if bool(item.get("is_repost")))
    repost_filtered_count = sum(1 for item in raw_items if item_is_filtered_repost(item))
    teaser_filtered_count = sum(1 for item in raw_items if bool(item.get("is_teaser")))
    return {
        "at": observed_at,
        "target_key": target_key(target),
        "mode": target.get("mode", ""),
        "mode_label": target.get("label", ""),
        "target_name": clean_text(target.get("name", "")) or clean_text(target.get("label", "")),
        "list_index": int(target.get("list_index", 0) or 0),
        "target_url": clean_text(target.get("url", "")),
        "current_top_tweet_id": clean_text(top_item.get("tweet_id", "")),
        "current_top_url": clean_text(top_item.get("status_url", "")),
        "current_top_handle": clean_text(top_item.get("handle", "")),
        "visible_tweet_ids": [clean_text(item.get("tweet_id", "")) for item in visible_items],
        "candidate_count": len(raw_items),
        "visible_count": len(visible_items),
        "repost_filtered_count": repost_filtered_count,
        "repost_candidate_count": repost_candidate_count,
        "teaser_filtered_count": teaser_filtered_count,
        "filtered_candidate_count": repost_filtered_count + teaser_filtered_count,
        "top_created_at": clean_text(top_item.get("created_at", "")),
        "top_delay_seconds": elapsed_seconds_between(top_item.get("created_at", ""), observed_at),
        "new_tweet_ids": [],
        "error": "",
    }


def attach_extract_observability(check, collect_meta, prefix):
    if not isinstance(check, dict):
        return check
    prefix_value = clean_text(prefix)
    if not prefix_value:
        return check
    meta = dict(collect_meta or {})
    field_names = (
        "attempt_count",
        "dom_article_count",
        "inspected_article_count",
        "id_extracted_count",
        "id_missing_count",
        "duplicate_tweet_id_count",
        "visible_count",
    )
    for field_name in field_names:
        key = f"extract_{field_name}"
        if key not in meta:
            continue
        check[f"{prefix_value}_{field_name}"] = clamp_int(meta.get(key, 0), 0, minimum=0, maximum=500)
    return check


def attach_initial_collect_meta(check, collect_meta):
    if not isinstance(check, dict):
        return check
    meta = dict(collect_meta or {})
    if meta.get("empty_page_retries_used"):
        check["empty_page_retries_used"] = int(meta.get("empty_page_retries_used", 0) or 0)
    if meta.get("candidate_gap_supplement_attempts"):
        check["candidate_gap_supplement_attempts"] = int(meta.get("candidate_gap_supplement_attempts", 0) or 0)
    if meta.get("candidate_gap_supplement_candidate_count"):
        check["candidate_gap_supplement_candidate_count"] = int(meta.get("candidate_gap_supplement_candidate_count", 0) or 0)
    if meta.get("candidate_gap_supplement_dom_article_count"):
        check["candidate_gap_supplement_dom_article_count"] = int(meta.get("candidate_gap_supplement_dom_article_count", 0) or 0)
    if meta.get("candidate_gap_supplement_id_missing_count"):
        check["candidate_gap_supplement_id_missing_count"] = int(meta.get("candidate_gap_supplement_id_missing_count", 0) or 0)
    if meta.get("light_scroll_supplement_attempts"):
        check["light_scroll_supplement_attempts"] = int(meta.get("light_scroll_supplement_attempts", 0) or 0)
    if meta.get("light_scroll_supplement_visible_count"):
        check["light_scroll_supplement_visible_count"] = int(meta.get("light_scroll_supplement_visible_count", 0) or 0)
    if meta.get("stale_refresh_light_scroll_recheck_attempts"):
        check["stale_refresh_light_scroll_recheck"] = "light_scroll"
        check["stale_refresh_light_scroll_recheck_attempts"] = int(meta.get("stale_refresh_light_scroll_recheck_attempts", 0) or 0)
    if meta.get("stale_refresh_light_scroll_recheck_visible_count"):
        check["stale_refresh_light_scroll_recheck_visible_count"] = int(meta.get("stale_refresh_light_scroll_recheck_visible_count", 0) or 0)
    if meta.get("stale_refresh_light_scroll_recheck_previous_top_tweet_id"):
        check["stale_refresh_light_scroll_recheck_previous_top_tweet_id"] = clean_text(meta.get("stale_refresh_light_scroll_recheck_previous_top_tweet_id", ""))
    if meta.get("stale_refresh_light_scroll_recheck_top_tweet_id"):
        check["stale_refresh_light_scroll_recheck_top_tweet_id"] = clean_text(meta.get("stale_refresh_light_scroll_recheck_top_tweet_id", ""))
    attach_extract_observability(check, meta, prefix="initial_extract")
    return check


def attach_page_surface_observability(check, surface):
    if not isinstance(check, dict):
        return check
    surface_value = dict(surface or {})
    state = clean_text(surface_value.get("state", ""))
    reason = clean_text(surface_value.get("reason", ""))
    signals = list(
        dict.fromkeys(
            clean_text(signal)
            for signal in (surface_value.get("signals", []) or [])
            if clean_text(signal)
        )
    )
    if state:
        check["page_surface_state"] = state
    if reason:
        check["page_surface_reason"] = reason
    if signals:
        check["page_surface_signals"] = signals
    return check


def visible_items_from_items(items):
    return [item for item in list(items or []) if not bool(item.get("is_teaser")) and not item_is_filtered_repost(item)]


def first_visible_tweet_id(items):
    visible = visible_items_from_items(items)
    if not visible:
        return ""
    return clean_text(visible[0].get("tweet_id", ""))


def detect_partial_page(items, target, config, state=None, observed_at=""):
    if target_mode(target) != MODE_LIST:
        return {}
    raw_items = list(items or [])
    visible_items = visible_items_from_items(raw_items)
    minimum_visible_count = partial_page_min_visible_count(config, target)
    if minimum_visible_count <= 0 or len(visible_items) >= minimum_visible_count:
        return {}
    raw_item_count = len(raw_items)
    repost_candidate_count = sum(1 for item in raw_items if bool(item.get("is_repost")))
    repost_filtered_count = sum(1 for item in raw_items if item_is_filtered_repost(item))
    teaser_filtered_count = sum(1 for item in raw_items if bool(item.get("is_teaser")))
    filtered_candidate_count = repost_filtered_count + teaser_filtered_count
    visible_deficit = max(0, minimum_visible_count - len(visible_items))
    filter_explains_visible_deficit = raw_item_count >= minimum_visible_count and filtered_candidate_count >= visible_deficit
    if filter_explains_visible_deficit:
        return {}
    current_top_item = visible_items[0] if visible_items else {}
    current_top_time = parse_iso_datetime(current_top_item.get("created_at", ""))
    observed_dt = parse_iso_datetime(observed_at) or now_utc()
    history_cutoff = observed_dt - timedelta(seconds=DEFAULT_PARTIAL_PAGE_HISTORY_WINDOW_SECONDS)
    top_gap_seconds = max(0, int(DEFAULT_PARTIAL_PAGE_NEWER_TOP_GAP_SECONDS))
    target_id = target_key(target)
    state_value = state or {}
    recent_checks = list(state_value.get("recent_checks", []))
    recent_events = list(state_value.get("recent_events", []))
    reasons = []
    reference_visible_count = 0
    reference_top_created_at = ""
    for recent_check in reversed(recent_checks):
        if target_key(recent_check.get("target_key", "")) != target_id:
            continue
        recent_at = parse_iso_datetime(recent_check.get("at", ""))
        if recent_at is None or recent_at < history_cutoff:
            continue
        reference_visible_count = max(reference_visible_count, int(recent_check.get("visible_count", 0) or 0))
        recent_top_time = parse_iso_datetime(recent_check.get("top_created_at", ""))
        if reference_visible_count >= minimum_visible_count and "visible_count_regressed" not in reasons:
            reasons.append("visible_count_regressed")
        if (
            current_top_time is not None
            and recent_top_time is not None
            and (recent_top_time - current_top_time).total_seconds() >= top_gap_seconds
            and "newer_history_hidden" not in reasons
        ):
            reasons.append("newer_history_hidden")
            if not reference_top_created_at:
                reference_top_created_at = clean_text(recent_check.get("top_created_at", ""))
    for recent_event in reversed(recent_events):
        if target_key(recent_event.get("target_key", "")) != target_id:
            continue
        event_time = item_reference_time(recent_event, observed_at)
        if event_time is None or event_time < history_cutoff:
            continue
        if (
            current_top_time is not None
            and (event_time - current_top_time).total_seconds() >= top_gap_seconds
            and "newer_history_hidden" not in reasons
        ):
            reasons.append("newer_history_hidden")
            if not reference_top_created_at:
                reference_top_created_at = clean_text(recent_event.get("created_at", "")) or clean_text(recent_event.get("at", ""))
            break
    if not reasons:
        return {}
    return {
        "reason": ",".join(reasons),
        "visible_count": len(visible_items),
        "minimum_visible_count": minimum_visible_count,
        "raw_item_count": raw_item_count,
        "repost_filtered_count": repost_filtered_count,
        "repost_candidate_count": repost_candidate_count,
        "teaser_filtered_count": teaser_filtered_count,
        "filtered_candidate_count": filtered_candidate_count,
        "reference_visible_count": reference_visible_count,
        "reference_top_created_at": reference_top_created_at,
    }


def item_created_before_service_start(item, service_start_at):
    started_at = parse_iso_datetime(service_start_at)
    if started_at is None:
        return False
    created_at = parse_iso_datetime(item.get("created_at", ""))
    if created_at is None:
        return False
    return created_at < started_at


def restart_gap_replay_seconds(config):
    return clamp_int(
        (config or {}).get("restart_gap_replay_seconds", DEFAULT_RESTART_GAP_REPLAY_SECONDS),
        DEFAULT_RESTART_GAP_REPLAY_SECONDS,
        minimum=0,
        maximum=3600,
    )


def item_should_baseline_on_start(item, service_start_at, config):
    started_at = parse_iso_datetime(service_start_at)
    if started_at is None:
        return False
    created_at = parse_iso_datetime((item or {}).get("created_at", ""))
    if created_at is None:
        return False
    return created_at < started_at


def item_is_restart_gap_replay(item, service_start_at, config):
    return False


def maybe_bootstrap(store, config, target, items, observed_at):
    target_id = target_key(target)
    maximum = clamp_int(config.get("max_seen_ids", DEFAULT_MAX_SEEN_IDS), DEFAULT_MAX_SEEN_IDS, minimum=50, maximum=3000)

    def updater(state):
        target_state = base_target_state()
        target_state.update(dict(state.get("targets", {}).get(target_id, {})))
        if target_state.get("bootstrapped"):
            return []
        service_start_at = clean_text(state.get("last_service_start_at", ""))
        ids = []
        seen = dict(state.get("seen_ids", {}))
        for item in items:
            tweet_id = clean_text(item.get("tweet_id", ""))
            if not tweet_id:
                continue
            if item_should_baseline_on_start(item, service_start_at, config) or not clean_text(item.get("created_at", "")):
                ids.append(tweet_id)
                seen[tweet_id] = observed_at
        visible_items = visible_items_from_items(items)
        top_item = visible_items[0] if visible_items else {}
        target_state["bootstrapped"] = True
        target_state["current_top_tweet_id"] = clean_text(top_item.get("tweet_id", ""))
        target_state["current_top_url"] = clean_text(top_item.get("status_url", ""))
        state["targets"][target_id] = target_state
        state["bootstrapped"] = True
        state["current_top_tweet_id"] = target_state["current_top_tweet_id"]
        state["current_top_url"] = target_state["current_top_url"]
        state["seen_ids"] = trim_seen_ids(seen, maximum)
        return ids

    ids = store.update_state(updater)
    if ids:
        mark_durable_seen_ids(store, ids, stamp=observed_at, config=config, target_ref=target)
    return ids


def fetch_editor_draft_with_backoff(store, config, item):
    providers = editor_draft_provider_candidates(config)
    if not providers:
        return {"ok": False, "error": "editor_draft_api_not_configured"}
    max_attempts = editor_draft_transient_retry_count(config) + 1
    transient_retry_delay_seconds = editor_draft_transient_retry_delay_milliseconds(config) / 1000.0
    last_exc = None
    for provider_index, provider in enumerate(providers):
        respect_cooldown = clean_text(provider.get("label", "")) == "primary"
        has_next_provider = provider_index < len(providers) - 1
        for attempt in range(max_attempts):
            with DRAFT_REQUEST_LOCK:
                wait_for_editor_draft_window(store, config, respect_cooldown=respect_cooldown)
                try:
                    result = fetch_editor_draft(config, item, provider=provider)
                except Exception as exc:
                    last_exc = exc
                    if is_rate_limit_error(exc):
                        if respect_cooldown:
                            cooldown_seconds = retry_after_seconds_from_exception(
                                exc,
                                editor_draft_rate_limit_cooldown_seconds(config),
                            )
                            schedule_editor_draft_cooldown(store, cooldown_seconds, str(exc))
                        if has_next_provider:
                            break
                        if attempt >= max_attempts - 1:
                            raise
                        continue
                    if is_editor_draft_transient_error(exc):
                        if attempt >= max_attempts - 1:
                            if has_next_provider:
                                break
                            mark_editor_draft_error(store, str(exc))
                            raise
                        time.sleep(transient_retry_delay_seconds)
                        continue
                    if has_next_provider:
                        break
                    mark_editor_draft_error(store, str(exc))
                    raise
            if respect_cooldown:
                clear_editor_draft_cooldown(store)
            return result
    if last_exc is not None:
        raise last_exc
    return {"ok": False, "error": "editor_draft_unknown_failure"}


def build_fallback_translation_draft(config, item, error="", status="fallback"):
    source_full_text = draft_source_full_text(item, limit=1600)
    if is_emoji_passthrough_text(source_full_text):
        translation = sanitize_translation_text(source_full_text, limit=1400) or source_full_text
        return {
            "translation": translation,
            "draft_model": "emoji_passthrough",
            "draft_provider": "passthrough",
            "draft_ready_at": iso_now(),
            "draft_status": "processed",
            "draft_error": "",
            "machine_translated_text": translation,
            "machine_translation_same_as_source": False,
            "emoji_passthrough_used": True,
            "skip_async_enrich": True,
        }
    translated = translate_source_text(config, source_full_text, limit=1400) or source_full_text
    translation = sanitize_translation_text(translated, limit=1400) or source_full_text
    return {
        "translation": translation,
        "draft_model": "translate_source_text",
        "draft_provider": "fallback",
        "draft_ready_at": iso_now(),
        "draft_status": status,
        "draft_error": compact_error_text(error, limit=280),
    }


def build_machine_translation_draft(store, config, item):
    source_full_text = draft_source_full_text(item, limit=1600)
    if is_emoji_passthrough_text(source_full_text):
        translation = sanitize_translation_text(source_full_text, limit=1400) or source_full_text
        return {
            "translation": translation,
            "draft_model": "emoji_passthrough",
            "draft_provider": "passthrough",
            "draft_ready_at": iso_now(),
            "draft_status": "processed",
            "draft_error": "",
            "machine_translated_text": translation,
            "machine_translation_same_as_source": False,
            "emoji_passthrough_used": True,
            "skip_async_enrich": True,
        }
    translated = translate_source_text(config, source_full_text, limit=1400) or source_full_text
    translation = sanitize_translation_text(translated, limit=1400) or source_full_text
    machine_translation_same_as_source = looks_untranslated_machine_translation(source_full_text, translation)
    return {
        "translation": translation,
        "draft_model": "translate_source_text",
        "draft_provider": "machine",
        "draft_ready_at": iso_now(),
        "draft_status": "machine",
        "draft_error": "",
        "machine_translated_text": translation,
        "machine_translation_same_as_source": machine_translation_same_as_source,
    }


def build_initial_delivery_draft(config, item):
    source_full_text = draft_source_full_text(item, limit=1600)
    if is_emoji_passthrough_text(source_full_text):
        translation = sanitize_translation_text(source_full_text, limit=1400) or source_full_text
        return {
            "translation": translation,
            "draft_model": "emoji_passthrough",
            "draft_provider": "passthrough",
            "draft_ready_at": iso_now(),
            "draft_status": "processed",
            "draft_error": "",
            "machine_translated_text": translation,
            "machine_translation_same_as_source": False,
            "emoji_passthrough_used": True,
            "skip_async_enrich": True,
            "initial_machine_translation_ready": True,
        }
    local_result = fetch_local_fast_translation(config, source_full_text, limit=1400, initial_delivery=True)
    local_translation = clean_text(local_result.get("translation", "")) if local_result.get("ok") else ""
    local_translation_same_as_source = bool(local_result.get("same_as_source", False))
    editor_enabled = config_bool(config.get("editor_draft_enabled", DEFAULT_EDITOR_DRAFT_ENABLED), DEFAULT_EDITOR_DRAFT_ENABLED)
    if local_translation and not local_translation_same_as_source:
        return {
            "translation": local_translation,
            "draft_model": clean_text(local_result.get("draft_model", "")) or "local_fast_translation",
            "draft_provider": clean_text(local_result.get("draft_provider", "")) or "local_fast_translation",
            "draft_ready_at": clean_text(local_result.get("draft_ready_at", "")) or iso_now(),
            "draft_status": "machine",
            "draft_error": "",
            "machine_translated_text": local_translation,
            "machine_translation_same_as_source": False,
            "emoji_passthrough_used": False,
            "skip_async_enrich": not editor_enabled,
            "initial_machine_translation_ready": True,
        }
    translation = sanitize_translation_text(source_full_text, limit=1400) or compact_error_text(
        draft_source_title(item, limit=260) or raw_title_for_display(item.get("text", "")),
        limit=1400,
    )
    pending_error = clean_text(local_result.get("error", ""))
    if local_result.get("ok") and local_translation_same_as_source:
        pending_error = "local_fast_translation_same_as_source"
    if pending_error == "local_fast_translation_not_configured":
        pending_error = ""
    return {
        "translation": translation,
        "draft_model": "source_text_pending",
        "draft_provider": "deferred",
        "draft_ready_at": "",
        "draft_status": "pending",
        "draft_error": compact_error_text(pending_error, limit=280),
        "machine_translated_text": "",
        "machine_translation_same_as_source": True,
        "emoji_passthrough_used": False,
        "skip_async_enrich": False,
        "initial_machine_translation_ready": False,
    }


def resolve_translation_draft(store, config, item):
    if not config_bool(config.get("editor_draft_enabled", DEFAULT_EDITOR_DRAFT_ENABLED), DEFAULT_EDITOR_DRAFT_ENABLED):
        return build_fallback_translation_draft(config, item, error="editor_draft_disabled", status="fallback")
    try:
        result = fetch_editor_draft_with_backoff(store, config, item)
        if result.get("ok"):
            draft = dict(result.get("draft") or {})
            draft["draft_status"] = "ready"
            draft["draft_error"] = ""
            return draft
        return build_fallback_translation_draft(
            config,
            item,
            error=result.get("error", "editor_draft_unknown_failure"),
            status="fallback",
        )
    except Exception as exc:
        return build_fallback_translation_draft(config, item, error=str(exc), status="fallback")


def draft_translation_for_display(item, draft):
    translation = sanitize_translation_text(clean_text((draft or {}).get("translation", "")), limit=1400)
    if translation:
        return translation
    source_full_text = draft_source_full_text(item, limit=1400)
    if source_full_text:
        return source_full_text
    return compact_error_text(draft_source_title(item, limit=260) or raw_title_for_display(item.get("text", "")), limit=1400)


def should_edit_message_with_draft(item, draft):
    draft_status = clean_text((draft or {}).get("draft_status", "")).lower()
    if draft_status in {"processed", "ready"}:
        return True
    translated_text = draft_translation_for_display(item, draft)
    source_full_text = draft_source_full_text(item, limit=1400)
    return clean_text(translated_text) != clean_text(source_full_text)


def update_event_with_draft(store, tweet_id, item, draft):
    translated_text = clean_text(draft_translation_for_display(item, draft))
    source_full_text = clean_text(item.get("source_full_text", "")) or draft_source_full_text(item, limit=1600)
    draft_status = clean_text((draft or {}).get("draft_status", "")).lower()
    processed = draft_status in {"processed", "ready"}
    update_event(
        store,
        tweet_id,
        {
            "draft_status": draft.get("draft_status", ""),
            "draft_model": draft.get("draft_model", ""),
            "draft_provider": draft.get("draft_provider", ""),
            "draft_ready_at": draft.get("draft_ready_at", ""),
            "draft_error": draft.get("draft_error", ""),
            "translated_text": translated_text,
            "machine_translated_text": clean_text(draft.get("machine_translated_text", "")) or translated_text,
            "machine_translation_same_as_source": bool(draft.get("machine_translation_same_as_source", False)),
            "emoji_passthrough_used": bool(draft.get("emoji_passthrough_used", False)),
            "editor_headline": first_sentence(translated_text, limit=120),
            "editor_push_copy": first_sentence(translated_text, limit=100),
            "editor_placeholder_body": translated_text,
            "processed_at": draft.get("draft_ready_at", "") if processed else "",
            "processed_translated_text": translated_text if processed else "",
            "processed_translation_same_as_source": clean_text(translated_text) == clean_text(source_full_text) if processed else False,
            "pending_recovery_last_error": "",
        },
    )


def event_item_from_recent_event(event):
    event_value = event or {}
    return {
        "tweet_id": clean_text(event_value.get("tweet_id", "")),
        "created_at": clean_text(event_value.get("created_at", "")),
        "status_url": clean_text(event_value.get("url", "")),
        "handle": clean_text(event_value.get("handle", "")),
        "text": clean_text(event_value.get("original_text", "")),
        "source_title_text": clean_text(event_value.get("source_title_text", "")),
        "source_body_text": clean_text(event_value.get("source_body_text", "")),
        "source_full_text": clean_text(event_value.get("source_full_text", "")),
        "raw_translated_title": clean_text(event_value.get("raw_translated_title", "")),
        "has_image": bool(event_value.get("has_image")),
        "has_video": bool(event_value.get("has_video")),
        "has_external_link": bool(event_value.get("has_external_link")),
        "is_repost": bool(event_value.get("is_repost")),
        "repost_context": clean_text(event_value.get("repost_context", "")),
        "is_filtered_repost": bool(event_value.get("is_filtered_repost")),
        "repost_filter_reason": clean_text(event_value.get("repost_filter_reason", "")),
        "delivered_at": clean_text(event_value.get("delivered_at", "")),
    }


def stale_pending_event_age_seconds(event, observed_at):
    observed_value = observed_at or iso_now()
    event_value = event or {}
    pending_since = (
        clean_text(event_value.get("pending_since_at", ""))
        or clean_text(event_value.get("raw_delivery_at", ""))
        or clean_text(event_value.get("delivered_at", ""))
        or clean_text(event_value.get("at", ""))
    )
    return elapsed_seconds_between(pending_since, observed_value)


def can_auto_recover_pending_event(event, observed_at):
    event_value = event or {}
    draft_status = clean_text(event_value.get("draft_status", "")).lower()
    if draft_status != "pending":
        return False
    if clean_text(event_value.get("processed_at", "")):
        return False
    if not clean_text(event_value.get("message_id", "")):
        return False
    age_seconds = stale_pending_event_age_seconds(event_value, observed_at)
    if age_seconds is None or age_seconds < DEFAULT_PENDING_EVENT_RECOVERY_STALE_SECONDS:
        return False
    recovery_count = clamp_int(
        event_value.get("pending_recovery_count", 0),
        0,
        minimum=0,
        maximum=DEFAULT_PENDING_EVENT_RECOVERY_MAX_ATTEMPTS,
    )
    if recovery_count >= DEFAULT_PENDING_EVENT_RECOVERY_MAX_ATTEMPTS:
        return False
    recovery_age_seconds = elapsed_seconds_between(clean_text(event_value.get("pending_recovery_last_at", "")), observed_at)
    if recovery_age_seconds is not None and recovery_age_seconds < DEFAULT_PENDING_EVENT_RECOVERY_COOLDOWN_SECONDS:
        return False
    return True


def maybe_schedule_pending_event_recovery(store, config, executor, observed_at=None):
    observed_value = observed_at or iso_now()
    state = store.load_state()
    candidates = []
    for event in state.get("recent_events", []):
        if not can_auto_recover_pending_event(event, observed_value):
            continue
        age_seconds = stale_pending_event_age_seconds(event, observed_value) or 0
        candidates.append((age_seconds, clean_text(event.get("delivered_at", "")), dict(event)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    event = candidates[0][2]
    tweet_id = clean_text(event.get("tweet_id", ""))
    message_id = clean_text(event.get("message_id", ""))
    if not tweet_id or not message_id:
        return None
    recovery_count = clamp_int(
        event.get("pending_recovery_count", 0),
        0,
        minimum=0,
        maximum=DEFAULT_PENDING_EVENT_RECOVERY_MAX_ATTEMPTS,
    ) + 1
    recovery_at = iso_now()
    updates = {
        "pending_recovery_count": recovery_count,
        "pending_recovery_last_at": recovery_at,
        "pending_recovery_last_error": "",
    }
    item = event_item_from_recent_event(event)
    raw_delivery_at = clean_text(event.get("raw_delivery_at", "")) or clean_text(event.get("delivered_at", "")) or recovery_at
    try:
        executor.submit(enrich_and_edit, store, dict(config or {}), item, message_id, raw_delivery_at)
    except Exception as exc:
        updates["pending_recovery_last_error"] = compact_error_text(str(exc), limit=280)
        update_event(store, tweet_id, updates)
        return None
    update_event(store, tweet_id, updates)
    return {
        "tweet_id": tweet_id,
        "message_id": message_id,
        "age_seconds": candidates[0][0],
        "pending_recovery_count": recovery_count,
    }


def enrich_and_edit(store, config, item, message_id, raw_delivery_at):
    tweet_id = item.get("tweet_id", "")
    try:
        if not bool(item.get("initial_machine_translation_ready", False)):
            machine_draft = build_machine_translation_draft(store, config, item)
            if should_edit_message_with_draft(item, machine_draft):
                discord_edit(config, message_id, render_translated_message(item, machine_draft, delivered_at=raw_delivery_at))
            update_event_with_draft(store, tweet_id, item, machine_draft)
            if bool(machine_draft.get("skip_async_enrich", False)):
                return
        if not config_bool(config.get("editor_draft_enabled", DEFAULT_EDITOR_DRAFT_ENABLED), DEFAULT_EDITOR_DRAFT_ENABLED):
            return
        result = fetch_editor_draft_with_backoff(store, config, item)
        if not result.get("ok"):
            update_event(
                store,
                tweet_id,
                {
                    "draft_status": "skipped" if result.get("error") == "editor_draft_api_not_configured" else "error",
                    "draft_error": compact_error_text(result.get("error", ""), limit=280),
                },
            )
            return
        draft = dict(result.get("draft") or {})
        draft["draft_status"] = "processed"
        draft["draft_error"] = ""
        if should_edit_message_with_draft(item, draft):
            discord_edit(config, message_id, render_translated_message(item, draft, delivered_at=raw_delivery_at))
        update_event_with_draft(store, tweet_id, item, draft)
    except Exception as exc:
        draft_status = "error"
        if is_rate_limit_error(exc):
            draft_status = "rate_limited"
        update_event(store, tweet_id, {"draft_status": draft_status, "draft_error": compact_error_text(str(exc), limit=280)})
        log_exception("enrich_and_edit", exc)


def classify_slow_delivery_cause(item, delivery_context=None):
    context = dict(delivery_context or {})
    if bool((item or {}).get("is_repost")) or clean_text((item or {}).get("repost_context", "")):
        return "repost_old"
    if clean_text(context.get("stale_refresh", "")):
        if clean_text(context.get("stale_refresh_light_scroll_recheck", "")):
            return "stale_recovered_light_scroll"
        return "stale_recovered"
    if clean_text(context.get("page_surface_state", "")) == "loading_shell":
        return "loading_shell"
    if clean_text(context.get("stale_refresh_result", "")) in {"no_items_after_full_reload", "no_items_after_reopen"}:
        return "reload_no_effect"
    return "list_not_exposed"


def slow_delivery_fields(item, delay_seconds, config, delivery_context=None):
    if delay_seconds is None or delay_seconds < slow_attribution_threshold_seconds(config):
        return {}
    context = dict(delivery_context or {})
    return {
        "slow_delivery": True,
        "slow_delivery_cause": classify_slow_delivery_cause(item, context),
        "slow_delivery_threshold_seconds": slow_attribution_threshold_seconds(config),
        "slow_delivery_observed_via": clean_text(context.get("stale_refresh", "")) or clean_text(context.get("soft_recovery_action", "")) or "normal_scan",
    }


def annotate_check_with_hot_list_acceleration(check, store, target, config, observed_at):
    new_ids = set(clean_text(tweet_id) for tweet_id in (check or {}).get("new_tweet_ids", []) if clean_text(tweet_id))
    if not new_ids:
        return
    threshold = hot_list_slow_delivery_threshold_seconds(config)
    max_delay = None
    slow_count = 0
    for event in reversed(store.load_state().get("recent_events", [])):
        if clean_text(event.get("tweet_id", "")) not in new_ids:
            continue
        if target_key(event.get("target_key", "")) != target_key(target):
            continue
        delay = event.get("delay_seconds")
        if isinstance(delay, (int, float)):
            max_delay = int(delay) if max_delay is None else max(max_delay, int(delay))
            if delay >= threshold:
                slow_count += 1
    if slow_count <= 0:
        return
    activation = activate_hot_list_acceleration(
        store,
        target_key(target),
        config,
        observed_at,
        "slow_delivery",
        delay_seconds=max_delay,
    )
    if activation:
        check.update(activation)
        check["hot_list_slow_delivery_count"] = slow_count


def handle_new_items(store, config, executor, target, items, observed_at, delivery_context=None):
    state = store.load_state()
    seen = combined_seen_ids(store, config, state, observed_at=observed_at)
    recent_events = list(state.get("recent_events", []))
    service_start_at = clean_text(state.get("last_service_start_at", ""))
    new_items = [
        item
        for item in items
        if item.get("tweet_id")
        and item["tweet_id"] not in seen
        and not item_is_filtered_repost(item)
        and not bool(item.get("is_teaser"))
        and not item_should_baseline_on_start(item, service_start_at, config)
    ]
    delivered = []
    if not new_items:
        mark_seen_ids(store, [item.get("tweet_id", "") for item in items], stamp=observed_at, config=config, target_ref=target)
        return []
    # Visible timeline items arrive top-down, so delivering in that same order
    # prioritizes the freshest post during burst batches.
    failed_new_tweet_ids = set()
    for item in new_items:
        item_tweet_id = clean_text(item.get("tweet_id", ""))
        item_for_delivery = dict(item)
        try:
            item_for_delivery["source_title_text"] = draft_source_title(item_for_delivery, limit=260)
            item_for_delivery["source_body_text"] = draft_source_body(item_for_delivery, limit=1200)
            item_for_delivery["source_full_text"] = draft_source_full_text(item_for_delivery, limit=1600)
            item_for_delivery["raw_translated_title"] = compact_error_text(
                item_for_delivery.get("source_title_text", "") or raw_title_for_display(item_for_delivery.get("text", "")),
                limit=120,
            )
            backfill_delay_seconds = stale_backfill_delay_seconds(item_for_delivery, observed_at)
            if should_suppress_stale_backfill(item_for_delivery, observed_at, config, target):
                event = {
                    "at": observed_at,
                    "event_type": "stale_backfill_suppressed",
                    "target_key": target_key(target),
                    "mode": target.get("mode", ""),
                    "mode_label": target.get("label", ""),
                    "target_name": clean_text(target.get("name", "")) or clean_text(target.get("label", "")),
                    "list_index": int(target.get("list_index", 0) or 0),
                    "target_url": clean_text(target.get("url", "")),
                    "tweet_id": item_for_delivery.get("tweet_id", ""),
                    "handle": item_for_delivery.get("handle", ""),
                    "url": item_for_delivery.get("status_url", ""),
                    "created_at": item_for_delivery.get("created_at", ""),
                    "original_text": item_for_delivery.get("text", ""),
                    "source_title_text": item_for_delivery.get("source_title_text", ""),
                    "source_body_text": item_for_delivery.get("source_body_text", ""),
                    "source_full_text": item_for_delivery.get("source_full_text", ""),
                    "raw_translated_title": item_for_delivery.get("raw_translated_title", ""),
                    "has_image": bool(item_for_delivery.get("has_image")),
                    "has_video": bool(item_for_delivery.get("has_video")),
                    "has_external_link": bool(item_for_delivery.get("has_external_link")),
                    "is_repost": bool(item_for_delivery.get("is_repost")),
                    "repost_context": clean_text(item_for_delivery.get("repost_context", "")),
                    "is_filtered_repost": bool(item_for_delivery.get("is_filtered_repost")),
                    "repost_filter_reason": clean_text(item_for_delivery.get("repost_filter_reason", "")),
                    "delay_seconds": backfill_delay_seconds,
                    "max_delivery_delay_seconds": max_delivery_delay_seconds(config, target),
                    "suppressed_reason": "stale_backfill_over_max_delivery_delay",
                    "draft_status": "skipped",
                    "draft_error": "stale_backfill_over_max_delivery_delay",
                }
                remember_event(store, event, archive_event_type="suppressed")
                recent_events = append_recent_event_entry(recent_events, event)
                if item_tweet_id:
                    mark_seen_ids(store, [item_tweet_id], stamp=observed_at, config=config, target_ref=target)
                continue
            duplicate_event = find_recent_near_duplicate_event(recent_events, target, item_for_delivery, observed_at, config)
            if duplicate_event:
                continue
            draft = build_initial_delivery_draft(config, item_for_delivery)
            delivered_at = iso_now()
            item_for_delivery["delivered_at"] = delivered_at
            delivery = {}
            if discord_sink_enabled(config):
                delivery = discord_send(config, render_translated_message(item_for_delivery, draft, delivered_at=delivered_at))
            message_id = clean_text((delivery or {}).get("id", ""))
            translated_text = clean_text(draft.get("translation", ""))
            source_full_text = clean_text(item_for_delivery.get("source_full_text", ""))
            machine_translated_text = clean_text(draft.get("machine_translated_text", "")) or translated_text
            machine_translation_same_as_source = bool(draft.get("machine_translation_same_as_source", False))
            initial_editor_fallback_used = bool(draft.get("initial_editor_fallback_used", False))
            emoji_passthrough_used = bool(draft.get("emoji_passthrough_used", False))
            skip_async_enrich = bool(draft.get("skip_async_enrich", False))
            item_for_delivery["machine_translated_text"] = machine_translated_text
            item_for_delivery["machine_translation_same_as_source"] = machine_translation_same_as_source
            item_for_delivery["initial_machine_translation_ready"] = bool(draft.get("initial_machine_translation_ready", False))
            delay_seconds = elapsed_seconds_between(item_for_delivery.get("created_at", ""), delivered_at)
            event = {
                "at": observed_at,
                "target_key": target_key(target),
                "mode": target.get("mode", ""),
                "mode_label": target.get("label", ""),
                "target_name": clean_text(target.get("name", "")) or clean_text(target.get("label", "")),
                "list_index": int(target.get("list_index", 0) or 0),
                "target_url": clean_text(target.get("url", "")),
                "tweet_id": item_for_delivery.get("tweet_id", ""),
                "handle": item_for_delivery.get("handle", ""),
                "url": item_for_delivery.get("status_url", ""),
                "created_at": item_for_delivery.get("created_at", ""),
                "original_text": item_for_delivery.get("text", ""),
                "source_title_text": item_for_delivery.get("source_title_text", ""),
                "source_body_text": item_for_delivery.get("source_body_text", ""),
                "source_full_text": item_for_delivery.get("source_full_text", ""),
                "raw_translated_title": item_for_delivery.get("raw_translated_title", ""),
                "has_image": bool(item_for_delivery.get("has_image")),
                "has_video": bool(item_for_delivery.get("has_video")),
                "has_external_link": bool(item_for_delivery.get("has_external_link")),
                "is_repost": bool(item_for_delivery.get("is_repost")),
                "repost_context": clean_text(item_for_delivery.get("repost_context", "")),
                "is_filtered_repost": bool(item_for_delivery.get("is_filtered_repost")),
                "repost_filter_reason": clean_text(item_for_delivery.get("repost_filter_reason", "")),
                "raw_delivery_at": delivered_at,
                "delivered_at": delivered_at,
                "pending_since_at": delivered_at,
                "message_id": message_id,
                "delay_seconds": delay_seconds,
                "restart_gap_replay": item_is_restart_gap_replay(item_for_delivery, service_start_at, config),
                "draft_status": draft.get("draft_status", "machine"),
                "draft_model": draft.get("draft_model", ""),
                "draft_provider": draft.get("draft_provider", ""),
                "draft_ready_at": draft.get("draft_ready_at", ""),
                "draft_error": draft.get("draft_error", ""),
                "translated_text": translated_text,
                "machine_translated_text": machine_translated_text,
                "machine_translation_same_as_source": machine_translation_same_as_source,
                "emoji_passthrough_used": emoji_passthrough_used,
                "editor_headline": first_sentence(translated_text, limit=120),
                "editor_push_copy": first_sentence(translated_text, limit=100),
                "editor_placeholder_body": translated_text,
                "processed_at": draft.get("draft_ready_at", "") if clean_text(draft.get("draft_status", "")).lower() in {"processed", "ready"} else "",
                "processed_translated_text": translated_text if clean_text(draft.get("draft_status", "")).lower() in {"processed", "ready"} else "",
                "processed_translation_same_as_source": clean_text(translated_text) == clean_text(source_full_text) if clean_text(draft.get("draft_status", "")).lower() in {"processed", "ready"} else False,
                "pending_recovery_count": 0,
                "pending_recovery_last_at": "",
                "pending_recovery_last_error": "",
                "output_sinks": normalize_output_sinks(config),
                "discord_delivered": bool(message_id),
            }
            event.update(slow_delivery_fields(item_for_delivery, delay_seconds, config, delivery_context=delivery_context))
            remember_event(store, event)
            recent_events = append_recent_event_entry(recent_events, event)
            if item_tweet_id:
                mark_seen_ids(store, [item_tweet_id], stamp=observed_at, config=config, target_ref=target)
            if message_id and not initial_editor_fallback_used and not skip_async_enrich:
                executor.submit(enrich_and_edit, store, dict(config), dict(item_for_delivery), message_id, delivered_at)
            delivered.append(item_for_delivery.get("tweet_id", ""))
        except Exception as exc:
            if item_tweet_id:
                failed_new_tweet_ids.add(item_tweet_id)
            record_target_error(store, target, str(exc))
            log_exception(f"handle_new_items[{target_key(target)}:{item_tweet_id}]", exc)
    seen_candidates = [
        item.get("tweet_id", "")
        for item in items
        if item.get("tweet_id", "") and clean_text(item.get("tweet_id", "")) not in failed_new_tweet_ids
    ]
    mark_seen_ids(store, seen_candidates, stamp=observed_at, config=config, target_ref=target)
    return delivered


def wait_with_stop(stop_event, seconds):
    end_at = time.time() + max(0.0, float(seconds))
    while time.time() < end_at:
        if stop_event.is_set():
            return True
        time.sleep(min(0.5, end_at - time.time()))
    return stop_event.is_set()


def stable_jitter_int(seed, maximum):
    max_value = clamp_int(maximum, 0, minimum=0, maximum=600000)
    if max_value <= 0:
        return 0
    digest = hashlib.sha1(clean_text(seed).encode("utf-8", errors="replace")).hexdigest()
    return int(digest[:8], 16) % (max_value + 1)


def target_jitter_seed(config, target, scope):
    return ":".join(
        [
            clean_text(scope),
            normalize_source_slot((config or {}).get("source_slot", DEFAULT_SOURCE_SLOT)),
            clean_text((config or {}).get("port", "")),
            target_key(target),
            clean_text((target or {}).get("url", "")),
        ]
    )


def target_check_jitter_milliseconds(config, target):
    max_jitter_ms = clamp_int(
        (config or {}).get("target_check_jitter_milliseconds", DEFAULT_TARGET_CHECK_JITTER_MILLISECONDS),
        DEFAULT_TARGET_CHECK_JITTER_MILLISECONDS,
        minimum=0,
        maximum=5000,
    )
    return stable_jitter_int(target_jitter_seed(config, target, "target-check"), max_jitter_ms)


def reload_interval_jitter_seconds(config, target):
    max_jitter_seconds = clamp_int(
        (config or {}).get("reload_interval_jitter_seconds", DEFAULT_RELOAD_INTERVAL_JITTER_SECONDS),
        DEFAULT_RELOAD_INTERVAL_JITTER_SECONDS,
        minimum=0,
        maximum=120,
    )
    return stable_jitter_int(target_jitter_seed(config, target, "reload-interval"), max_jitter_seconds)


def target_reload_due_seconds(config, target, base_reload_seconds):
    base_value = clamp_int(
        base_reload_seconds,
        DEFAULT_RELOAD_INTERVAL_SECONDS,
        minimum=5,
        maximum=300,
    )
    return min(300, base_value + reload_interval_jitter_seconds(config, target))


def wait_for_target_check_jitter(stop_event, config, target):
    jitter_ms = target_check_jitter_milliseconds(config, target)
    if jitter_ms <= 0:
        return False
    return wait_with_stop(stop_event, jitter_ms / 1000.0)


def run_service(store):
    config = runtime_config(store)
    parse_error = config_parse_error(config)
    if parse_error:
        record_error(store, f"invalid config: {parse_error}")
        return {"ok": False, "error": "invalid_config", "config_parse_error": parse_error}
    missing = config_missing(config)
    if missing:
        record_error(store, f"missing config: {', '.join(missing)}")
        return {"ok": False, "error": "missing_config", "config_missing": missing}
    slot_binding = load_x_monitor_slot_binding(config.get("source_slot", DEFAULT_SOURCE_SLOT))
    slot_binding_parse_error = slot_binding_config_parse_error(slot_binding)
    if slot_binding_parse_error:
        error_message = f"slot binding config invalid: {slot_binding.get('config_path', '')}: {slot_binding_parse_error}"
        record_error(store, error_message)
        notify_slot_intervention_if_needed(store, config, error_message, observed_at=now_utc())
        return invalid_slot_binding_payload("serve", slot_binding, running=False)
    targets = enabled_targets(config)
    signature = runtime_signature(config)
    stop_event = threading.Event()

    def handle_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    current_pid = os.getpid()
    if not acquire_service_lock(store, pid=current_pid):
        raise RuntimeError("service_instance_already_running")
    write_pid(store, current_pid)
    def initialize_state(state):
        state["last_service_start_at"] = iso_now()
        state["last_service_stop_at"] = ""
        state["last_error"] = ""
        state["service_pid"] = current_pid
        state["service_heartbeat_at"] = state["last_service_start_at"]
        for target in targets:
            target_id = target_key(target)
            if not target_id:
                continue
            target_state = base_target_state()
            target_state.update(dict(state.get("targets", {}).get(target_id, {})))
            target_state["bootstrapped"] = False
            state["targets"][target_id] = target_state
        state["bootstrapped"] = False

    store.update_state(initialize_state)

    executor = ThreadPoolExecutor(max_workers=async_enrich_max_workers(config), thread_name_prefix="xmonitorplus")
    playwright = None
    browser = None
    context = None
    restart_request = None
    page_deficit_streaks = {target_key(target): 0 for target in targets if target_key(target)}
    try:
        slot_binding_problems = []
        if not slot_binding.get("config_exists", False):
            slot_binding_problems.append(f"slot config missing: {slot_binding.get('config_path', '')}")
        if not slot_binding.get("cookies_exists", False):
            slot_binding_problems.append(f"cookies file missing: {slot_binding.get('cookies_path', '')}")
        if not slot_binding.get("profile_exists", False):
            slot_binding_problems.append(f"profile missing: {slot_binding.get('profile_dir', '')}")
        if slot_binding_problems:
            slot_binding_error = "; ".join(slot_binding_problems)
            record_error(store, slot_binding_error)
            notify_slot_intervention_if_needed(store, config, slot_binding_error, observed_at=now_utc())
        playwright, browser, context, page = initialize_browser_context(config)
        pages = {}
        for index, target in enumerate(targets):
            target_id = target_key(target)
            if not target_id:
                continue
            try:
                target_page = page if index == 0 else context.new_page()
            except Exception as exc:
                page_error = f"startup_new_page_failed: {exc}"
                record_target_navigation_error(store, target_id, target, iso_now(), page_error, "startup_new_page")
                runtime_restart_kind = classify_runtime_restart_error(page_error)
                if runtime_restart_kind:
                    restart_request = {
                        "kind": runtime_restart_kind,
                        "error": compact_error_text(page_error, limit=500),
                        "mode": target.get("mode", ""),
                        "target_key": target_id,
                        "detected_at": iso_now(),
                        "attempt_restart": browser_crash_auto_restart_enabled(config)
                        and should_attempt_auto_restart(
                            store,
                            runtime_restart_kind,
                            page_error,
                            now_utc(),
                            browser_crash_auto_restart_cooldown_seconds(config),
                        ),
                    }
                    record_error(store, page_error)
                    log_exception(f"startup_new_page[{target_id}]", exc)
                    stop_event.set()
                    break
                log_exception(f"startup_new_page[{target_id}]", exc)
                continue
            pages[target_id] = target_page
            try:
                navigate_to_target_page(target_page, target, config)
            except PlaywrightTimeoutError as exc:
                navigation_error = f"startup_navigation_timeout: {exc}"
                record_target_navigation_error(store, target_id, target, iso_now(), navigation_error, "startup_navigation")
                log_exception(f"startup_navigation[{target_id}]", exc)
                continue
            except Exception as exc:
                navigation_error = f"startup_navigation_failed: {exc}"
                record_target_navigation_error(store, target_id, target, iso_now(), navigation_error, "startup_navigation")
                runtime_restart_kind = classify_runtime_restart_error(navigation_error)
                if runtime_restart_kind:
                    restart_request = {
                        "kind": runtime_restart_kind,
                        "error": compact_error_text(navigation_error, limit=500),
                        "mode": target.get("mode", ""),
                        "target_key": target_id,
                        "detected_at": iso_now(),
                        "attempt_restart": browser_crash_auto_restart_enabled(config)
                        and should_attempt_auto_restart(
                            store,
                            runtime_restart_kind,
                            navigation_error,
                            now_utc(),
                            browser_crash_auto_restart_cooldown_seconds(config),
                        ),
                    }
                    record_error(store, navigation_error)
                    log_exception(f"startup_navigation[{target_id}]", exc)
                    stop_event.set()
                    break
                log_exception(f"startup_navigation[{target_id}]", exc)
                continue
            mark_target_reloaded(store, target_id, iso_now())
            update_auth_state(store, target_id, True)
        for target in targets:
            if stop_event.is_set():
                break
            target_id = target_key(target)
            target_page = pages.get(target_id)
            if target_page is None:
                continue
            try:
                warm_target_page(
                    store,
                    config,
                    executor,
                    target,
                    target_page,
                    iso_now(),
                    stop_event=stop_event,
                )
            except Exception as exc:
                record_target_error(store, target_id, f"initial_warm_failed: {compact_error_text(str(exc), limit=280)}")
                log_exception(f"initial_warm[{target_id}]", exc)
        watch_seconds = clamp_int(
            config.get("watch_interval_seconds", DEFAULT_WATCH_INTERVAL_SECONDS),
            DEFAULT_WATCH_INTERVAL_SECONDS,
            minimum=2,
            maximum=60,
        )
        while not stop_event.is_set():
            touch_service_runtime(store, pid=current_pid)
            latest_config = runtime_config(store)
            latest_signature = runtime_signature(latest_config)
            latest_targets = enabled_targets(latest_config)
            if not latest_targets:
                record_error(store, "no_enabled_modes_configured")
                break
            if latest_signature != signature:
                record_error(store, "runtime_config_changed_restart_required")
                break
            cycle_has_slot_intervention = False
            cycle_empty_page_failures = []
            for target in targets:
                if stop_event.is_set():
                    break
                target_id = target_key(target)
                if wait_for_target_check_jitter(stop_event, latest_config, target):
                    break
                observed_at = iso_now()
                check = build_check_snapshot([], observed_at, target)
                target_page = pages.get(target_id)
                if target_page is None:
                    try:
                        target_page = context.new_page()
                        pages[target_id] = target_page
                    except Exception as exc:
                        navigation_error = f"new_page_failed: {exc}"
                        record_target_navigation_error(store, target_id, target, observed_at, navigation_error, "new_page")
                        runtime_restart_kind = classify_runtime_restart_error(navigation_error)
                        if runtime_restart_kind:
                            restart_request = {
                                "kind": runtime_restart_kind,
                                "error": compact_error_text(navigation_error, limit=500),
                                "mode": target.get("mode", ""),
                                "target_key": target_id,
                                "detected_at": iso_now(),
                                "attempt_restart": browser_crash_auto_restart_enabled(latest_config)
                                and should_attempt_auto_restart(
                                    store,
                                    runtime_restart_kind,
                                    navigation_error,
                                    now_utc(),
                                    browser_crash_auto_restart_cooldown_seconds(latest_config),
                                ),
                            }
                            record_error(store, navigation_error)
                            log_exception(f"new_page[{target_id}]", exc)
                            stop_event.set()
                            break
                        log_exception(f"new_page[{target_id}]", exc)
                        continue
                reload_seconds = clamp_int(
                    latest_config.get("reload_interval_seconds", DEFAULT_RELOAD_INTERVAL_SECONDS),
                    DEFAULT_RELOAD_INTERVAL_SECONDS,
                    minimum=5,
                    maximum=300,
                )
                reload_due_seconds = target_reload_due_seconds(latest_config, target, reload_seconds)
                state_snapshot = store.load_state()
                target_state = state_snapshot.get("targets", {}).get(target_id, {})
                reload_elapsed = elapsed_seconds_between(target_state.get("last_reload_at", ""), observed_at)
                needs_initial_navigation = reload_elapsed is None
                if (needs_initial_navigation or reload_elapsed >= reload_due_seconds) and not stop_event.is_set():
                    navigation_phase = "initial_navigation" if needs_initial_navigation else "reload"
                    try:
                        if needs_initial_navigation:
                            navigate_to_target_page(target_page, target, latest_config, recovery=True)
                            mark_target_reloaded(store, target_id, iso_now())
                        else:
                            target_page, _ = reload_target_page(
                                target_page,
                                target,
                                latest_config,
                                store=store,
                                target_ref=target_id,
                                recovery=False,
                            )
                        pages[target_id] = target_page
                        observed_at = iso_now()
                        check = build_check_snapshot([], observed_at, target)
                    except PlaywrightTimeoutError as exc:
                        navigation_error = f"{navigation_phase}_timeout: {exc}"
                        record_target_navigation_error(store, target_id, target, observed_at, navigation_error, navigation_phase)
                        runtime_restart_kind = classify_runtime_restart_error(navigation_error)
                        if runtime_restart_kind:
                            restart_request = {
                                "kind": runtime_restart_kind,
                                "error": compact_error_text(navigation_error, limit=500),
                                "mode": target.get("mode", ""),
                                "target_key": target_id,
                                "detected_at": iso_now(),
                                "attempt_restart": browser_crash_auto_restart_enabled(latest_config)
                                and should_attempt_auto_restart(
                                    store,
                                    runtime_restart_kind,
                                    navigation_error,
                                    now_utc(),
                                    browser_crash_auto_restart_cooldown_seconds(latest_config),
                                ),
                            }
                            record_error(store, navigation_error)
                            stop_event.set()
                            break
                        log_exception(f"{navigation_phase}[{target_id}]", exc)
                        continue
                    except Exception as exc:
                        navigation_error = f"{navigation_phase}_failed: {exc}"
                        record_target_navigation_error(store, target_id, target, observed_at, navigation_error, navigation_phase)
                        runtime_restart_kind = classify_runtime_restart_error(navigation_error)
                        if runtime_restart_kind:
                            restart_request = {
                                "kind": runtime_restart_kind,
                                "error": compact_error_text(navigation_error, limit=500),
                                "mode": target.get("mode", ""),
                                "target_key": target_id,
                                "detected_at": iso_now(),
                                "attempt_restart": browser_crash_auto_restart_enabled(latest_config)
                                and should_attempt_auto_restart(
                                    store,
                                    runtime_restart_kind,
                                    navigation_error,
                                    now_utc(),
                                    browser_crash_auto_restart_cooldown_seconds(latest_config),
                                ),
                            }
                            record_error(store, navigation_error)
                            stop_event.set()
                            break
                        log_exception(f"{navigation_phase}[{target_id}]", exc)
                        continue
                try:
                    items, collect_meta = collect_target_items(
                        target_page,
                        target,
                        latest_config,
                        stop_event=stop_event,
                    )
                    recovery_collect_meta = {}
                    page_surface = {
                        "state": "ready",
                        "reason": "visible_timeline_items_present",
                        "signals": [],
                    }
                    soft_recovery_actions = []
                    attach_initial_collect_meta(check, collect_meta)
                    if not items:
                        page_surface = classify_page_surface_state(target_page)
                        attach_page_surface_observability(check, page_surface)
                        page_surface_state = clean_text(page_surface.get("state", ""))
                        if page_surface_state == "auth_issue":
                            auth_kind = clean_text(page_surface.get("auth_kind", "")) or clean_text(page_surface.get("reason", ""))
                            auth_reason = clean_text(page_surface.get("auth_reason", "")) or clean_text(page_surface.get("reason", ""))
                            page_deficit_streaks[target_id] = 0
                            cycle_has_slot_intervention = True
                            update_auth_state(store, target_id, False, auth_reason)
                            record_target_error(store, target_id, auth_reason)
                            notify_slot_intervention_if_needed(
                                store,
                                latest_config,
                                auth_reason or auth_kind,
                                observed_at=now_utc(),
                                mode=target["mode"],
                            )
                            wait_with_stop(stop_event, 10)
                            try:
                                target_page, _ = reload_target_page(
                                    target_page,
                                    target,
                                    latest_config,
                                    store=store,
                                    target_ref=target_id,
                                    recovery=True,
                                )
                                pages[target_id] = target_page
                            except Exception:
                                pass
                            continue
                        if page_surface_state == "loading_shell":
                            page_deficit_streaks[target_id] = 0
                            target_page, recovered_items, loading_meta = recover_items_from_loading_shell(
                                target_page,
                                target,
                                latest_config,
                                store=store,
                                target_ref=target_id,
                                stop_event=stop_event,
                            )
                            pages[target_id] = target_page
                            recovery_collect_meta = dict(loading_meta.get("collect_meta", {}) or {})
                            soft_recovery_actions.extend(list(loading_meta.get("steps", []) or []))
                            if recovered_items:
                                items = recovered_items
                                observed_at = iso_now()
                            else:
                                final_surface = dict(loading_meta.get("final_surface", {}) or {})
                                final_surface_state = clean_text(final_surface.get("state", "")) or "loading_shell"
                                if final_surface_state == "auth_issue":
                                    auth_kind = clean_text(final_surface.get("auth_kind", "")) or clean_text(final_surface.get("reason", ""))
                                    auth_reason = clean_text(final_surface.get("auth_reason", "")) or clean_text(final_surface.get("reason", ""))
                                    cycle_has_slot_intervention = True
                                    update_auth_state(store, target_id, False, auth_reason)
                                    record_target_error(store, target_id, auth_reason)
                                    notify_slot_intervention_if_needed(
                                        store,
                                        latest_config,
                                        auth_reason or auth_kind,
                                        observed_at=now_utc(),
                                        mode=target["mode"],
                                    )
                                    wait_with_stop(stop_event, 10)
                                    try:
                                        target_page, _ = reload_target_page(
                                            target_page,
                                            target,
                                            latest_config,
                                            store=store,
                                            target_ref=target_id,
                                            recovery=True,
                                        )
                                        pages[target_id] = target_page
                                    except Exception:
                                        pass
                                    continue
                                if final_surface_state == "loading_shell":
                                    target_page, shell_reopen_items, shell_reopen_meta = fast_reopen_and_collect_target_page(
                                        context,
                                        pages,
                                        target_id,
                                        target,
                                        target_page,
                                        latest_config,
                                        store,
                                        reason="persistent_loading_shell_fast_reopen",
                                        stop_event=stop_event,
                                    )
                                    pages[target_id] = target_page
                                    shell_reopen_steps = list(shell_reopen_meta.get("steps", []) or [])
                                    soft_recovery_actions.extend(shell_reopen_steps)
                                    check["loading_shell_fast_reopen"] = True
                                    shell_reopen_collect_meta = dict(shell_reopen_meta.get("collect_meta", {}) or {})
                                    if shell_reopen_collect_meta:
                                        recovery_collect_meta = shell_reopen_collect_meta
                                    if shell_reopen_meta.get("retries_used"):
                                        check["loading_shell_fast_reopen_retries_used"] = shell_reopen_meta.get("retries_used")
                                    if shell_reopen_meta.get("light_scroll_attempts"):
                                        check["light_scroll_recovery_attempts"] = (
                                            int(check.get("light_scroll_recovery_attempts", 0) or 0)
                                            + int(shell_reopen_meta.get("light_scroll_attempts", 0) or 0)
                                        )
                                    if shell_reopen_meta.get("light_scroll_visible_count"):
                                        check["light_scroll_recovery_visible_count"] = max(
                                            int(check.get("light_scroll_recovery_visible_count", 0) or 0),
                                            int(shell_reopen_meta.get("light_scroll_visible_count", 0) or 0),
                                        )
                                    if shell_reopen_items:
                                        items = shell_reopen_items
                                        observed_at = iso_now()
                                    else:
                                        check["loading_shell_fast_reopen_result"] = "no_items_after_reopen"
                                        if recovery_collect_meta:
                                            attach_extract_observability(check, recovery_collect_meta, prefix="recovery_extract")
                                        if soft_recovery_actions:
                                            check["soft_recovery_action"] = join_recovery_actions(soft_recovery_actions)
                                        update_auth_state(store, target_id, True, "")
                                        clear_target_error(store, target_id)
                                        append_recent_check(store, check)
                                        continue
                                page_surface = final_surface or {
                                    "state": "hard_empty",
                                    "reason": "no_visible_timeline_items_after_auth_and_loading_checks",
                                    "signals": [],
                                }
                                attach_page_surface_observability(check, page_surface)
                        if not items:
                            page_deficit_streaks[target_id] = clamp_int(
                                page_deficit_streaks.get(target_id, 0) + 1,
                                0,
                                minimum=0,
                                maximum=999999,
                            )
                            check["empty_page_streak"] = page_deficit_streaks[target_id]
                            recovered_items = []
                            recovery_meta = {}
                            recovery_threshold = empty_page_restart_threshold(latest_config)
                            if page_surface_state == "hard_empty" and page_deficit_streaks[target_id] < recovery_threshold:
                                check["empty_page_recovery"] = "observe"
                                check["empty_page_recovery_deferred"] = True
                                update_auth_state(store, target_id, True, "")
                                clear_target_error(store, target_id)
                                append_recent_check(store, check)
                                continue
                            target_page, recovered_items, recovery_meta = recover_items_from_empty_page(
                                context,
                                pages,
                                target_id,
                                target,
                                target_page,
                                latest_config,
                                store,
                                stop_event=stop_event,
                            )
                            pages[target_id] = target_page
                            recovery_steps = recovery_meta.get("steps", [])
                            if recovery_steps:
                                check["empty_page_recovery"] = ",".join(recovery_steps)
                            if recovery_meta.get("retries_used"):
                                check["empty_page_recovery_retries_used"] = recovery_meta.get("retries_used")
                            if recovery_meta.get("light_scroll_attempts"):
                                check["light_scroll_recovery_attempts"] = recovery_meta.get("light_scroll_attempts")
                            if recovery_meta.get("light_scroll_visible_count"):
                                check["light_scroll_recovery_visible_count"] = recovery_meta.get("light_scroll_visible_count")
                            if recovery_meta.get("priority_rechecks_used"):
                                check["empty_page_priority_rechecks_used"] = recovery_meta.get("priority_rechecks_used")
                            recovery_collect_meta = dict(recovery_meta.get("collect_meta", {}) or {})
                            if recovered_items:
                                items = recovered_items
                                observed_at = iso_now()
                            else:
                                check["empty_page_recovery_result"] = "no_items_after_recovery"
                                if page_surface_state == "hard_empty":
                                    cycle_empty_page_failures.append(target_id)
                                    wave_ready = should_trigger_multi_target_empty_page_restart(
                                        cycle_empty_page_failures,
                                        len(targets),
                                        latest_config,
                                        state=store.load_state(),
                                        observed_at=observed_at,
                                    )
                                    if wave_ready:
                                        failing_targets = ",".join(dict.fromkeys(cycle_empty_page_failures))
                                        error_text = f"persistent hard-empty wave after recovery on the configured {failing_targets} pages"
                                        record_error(store, error_text)
                                        wave_recovery = recover_multi_target_empty_page_wave(
                                            context,
                                            pages,
                                            targets,
                                            cycle_empty_page_failures,
                                            latest_config,
                                            store,
                                            stop_event=stop_event,
                                        )
                                        if recovery_collect_meta:
                                            attach_extract_observability(check, recovery_collect_meta, prefix="recovery_extract")
                                        if soft_recovery_actions:
                                            check["soft_recovery_action"] = join_recovery_actions(soft_recovery_actions)
                                        check["empty_page_wave_recovery"] = clean_text(wave_recovery.get("action", "")) or "page_rebuild"
                                        check["empty_page_wave_recovered_targets"] = ",".join(wave_recovery.get("recovered_targets", []))
                                        check["empty_page_wave_rebuilt_targets"] = ",".join(wave_recovery.get("rebuilt_targets", []))
                                        if wave_recovery.get("canary_target"):
                                            check["empty_page_wave_canary_target"] = wave_recovery.get("canary_target")
                                        if wave_recovery.get("canary_wait_milliseconds"):
                                            check["empty_page_wave_canary_wait_milliseconds"] = wave_recovery.get("canary_wait_milliseconds")
                                        if wave_recovery.get("canary_visible_count") is not None:
                                            check["empty_page_wave_canary_visible_count"] = wave_recovery.get("canary_visible_count")
                                        if wave_recovery.get("canary_error"):
                                            check["empty_page_wave_canary_error"] = wave_recovery.get("canary_error")
                                        if wave_recovery.get("failed_targets"):
                                            check["empty_page_wave_failed_count"] = len(wave_recovery.get("failed_targets", []))
                                        update_auth_state(store, target_id, True, "")
                                        clear_target_error(store, target_id)
                                        append_recent_check(store, check)
                                        cycle_empty_page_failures = []
                                        continue
                                    if should_trigger_multi_target_empty_page_restart(
                                        cycle_empty_page_failures,
                                        len(targets),
                                        latest_config,
                                    ):
                                        check["empty_page_wave_recovery"] = "cooldown"
                                if recovery_collect_meta:
                                    attach_extract_observability(check, recovery_collect_meta, prefix="recovery_extract")
                                if soft_recovery_actions:
                                    check["soft_recovery_action"] = join_recovery_actions(soft_recovery_actions)
                                update_auth_state(store, target_id, True, "")
                                clear_target_error(store, target_id)
                                append_recent_check(store, check)
                                continue
                    partial_page_meta = detect_partial_page(items, target, latest_config, state=state_snapshot, observed_at=observed_at)
                    if partial_page_meta:
                        page_surface = {
                            "state": "partial_page",
                            "reason": clean_text(partial_page_meta.get("reason", "")) or "partial_page",
                            "signals": [],
                        }
                        attach_page_surface_observability(check, page_surface)
                        page_deficit_streaks[target_id] = clamp_int(
                            page_deficit_streaks.get(target_id, 0) + 1,
                            0,
                            minimum=0,
                            maximum=999999,
                        )
                        check["partial_page_streak"] = page_deficit_streaks[target_id]
                        check["partial_page_reason"] = clean_text(partial_page_meta.get("reason", ""))
                        check["partial_page_visible_count"] = int(partial_page_meta.get("visible_count", 0) or 0)
                        check["partial_page_min_visible_count"] = int(partial_page_meta.get("minimum_visible_count", 0) or 0)
                        check["partial_page_reference_visible_count"] = int(partial_page_meta.get("reference_visible_count", 0) or 0)
                        check["partial_page_reference_top_created_at"] = clean_text(partial_page_meta.get("reference_top_created_at", ""))
                        target_page, recovered_items, recovery_meta = recover_items_from_empty_page(
                            context,
                            pages,
                            target_id,
                            target,
                            target_page,
                            latest_config,
                            store,
                            stop_event=stop_event,
                        )
                        pages[target_id] = target_page
                        recovery_steps = recovery_meta.get("steps", [])
                        if recovery_steps:
                            check["partial_page_recovery"] = ",".join(recovery_steps)
                        if recovery_meta.get("retries_used"):
                            check["partial_page_recovery_retries_used"] = recovery_meta.get("retries_used")
                        recovery_collect_meta = dict(recovery_meta.get("collect_meta", {}) or {})
                        if recovered_items:
                            items = recovered_items
                            observed_at = iso_now()
                            partial_page_meta = detect_partial_page(items, target, latest_config, state=state_snapshot, observed_at=observed_at)
                        if partial_page_meta:
                            if page_deficit_streaks[target_id] >= empty_page_restart_threshold(latest_config):
                                target_page, _ = auto_recover_target_page(
                                    context,
                                    pages,
                                    target_id,
                                    target,
                                    target_page,
                                    latest_config,
                                    store,
                                    reason="persistent_partial_page",
                                )
                                pages[target_id] = target_page
                                page_deficit_streaks[target_id] = 0
                                soft_recovery_actions.append("page_auto_recover")
                                if recovery_collect_meta:
                                    attach_extract_observability(check, recovery_collect_meta, prefix="recovery_extract")
                                if soft_recovery_actions:
                                    check["soft_recovery_action"] = join_recovery_actions(soft_recovery_actions)
                                update_auth_state(store, target_id, True, "")
                                clear_target_error(store, target_id)
                                append_recent_check(store, check)
                                continue
                            raise RuntimeError(f"insufficient tweets were found on the configured {target['label']} page")
                    late_recovery_candidates = late_unseen_items_for_recovery(
                        state_snapshot,
                        latest_config,
                        target,
                        items,
                        observed_at,
                        store=store,
                    )
                    if late_recovery_candidates:
                        check["late_new_item_recovery_candidates"] = len(late_recovery_candidates)
                        check["late_new_item_recovery_delay_seconds"] = late_new_item_recovery_delay_seconds(latest_config, target)
                        check["late_new_item_recovery_max_delay_seconds"] = max(
                            elapsed_seconds_between(item.get("created_at", ""), observed_at) or 0
                            for item in late_recovery_candidates
                        )
                        try:
                            target_page, late_recovered_items, late_recovery_meta = fast_reopen_and_collect_target_page(
                                context,
                                pages,
                                target_id,
                                target,
                                target_page,
                                latest_config,
                                store,
                                reason="late_new_item_fast_reopen",
                                stop_event=stop_event,
                            )
                            pages[target_id] = target_page
                            soft_recovery_actions.extend(list(late_recovery_meta.get("steps", []) or []))
                            check["late_new_item_recovery"] = "fast_reopen"
                            late_recovery_collect_meta = dict(late_recovery_meta.get("collect_meta", {}) or {})
                            if late_recovery_collect_meta:
                                recovery_collect_meta = late_recovery_collect_meta
                            if late_recovered_items:
                                items = merge_items_by_tweet_id(late_recovered_items, items)
                                observed_at = iso_now()
                                check["late_new_item_recovery_visible_count"] = len(visible_items_from_items(late_recovered_items))
                        except Exception as exc:
                            check["late_new_item_recovery_error"] = compact_error_text(str(exc), limit=280)
                    empty_page_recovery = clean_text(check.get("empty_page_recovery", ""))
                    empty_page_recovery_retries_used = check.get("empty_page_recovery_retries_used", 0)
                    light_scroll_supplement_attempts = int(check.get("light_scroll_supplement_attempts", 0) or 0)
                    light_scroll_supplement_visible_count = int(check.get("light_scroll_supplement_visible_count", 0) or 0)
                    light_scroll_recovery_attempts = int(check.get("light_scroll_recovery_attempts", 0) or 0)
                    light_scroll_recovery_visible_count = int(check.get("light_scroll_recovery_visible_count", 0) or 0)
                    empty_page_streak_value = check.get("empty_page_streak", 0)
                    partial_page_recovery = clean_text(check.get("partial_page_recovery", ""))
                    partial_page_recovery_retries_used = check.get("partial_page_recovery_retries_used", 0)
                    partial_page_streak_value = check.get("partial_page_streak", 0)
                    partial_page_reason = clean_text(check.get("partial_page_reason", ""))
                    partial_page_visible_count = int(check.get("partial_page_visible_count", 0) or 0)
                    partial_page_min_visible_count = int(check.get("partial_page_min_visible_count", 0) or 0)
                    partial_page_reference_visible_count = int(check.get("partial_page_reference_visible_count", 0) or 0)
                    partial_page_reference_top_created_at = clean_text(check.get("partial_page_reference_top_created_at", ""))
                    late_new_item_recovery = clean_text(check.get("late_new_item_recovery", ""))
                    late_new_item_recovery_candidates = int(check.get("late_new_item_recovery_candidates", 0) or 0)
                    late_new_item_recovery_delay_value = int(check.get("late_new_item_recovery_delay_seconds", 0) or 0)
                    late_new_item_recovery_max_delay = int(check.get("late_new_item_recovery_max_delay_seconds", 0) or 0)
                    late_new_item_recovery_visible_count = int(check.get("late_new_item_recovery_visible_count", 0) or 0)
                    late_new_item_recovery_error = clean_text(check.get("late_new_item_recovery_error", ""))
                    soft_recovery_action = clean_text(check.get("soft_recovery_action", ""))
                    initial_collect_meta = dict(collect_meta or {})
                    page_deficit_streaks[target_id] = 0
                    check = build_check_snapshot(items, observed_at, target)
                    attach_initial_collect_meta(check, initial_collect_meta)
                    attach_page_surface_observability(check, page_surface)
                    if light_scroll_supplement_attempts:
                        check["light_scroll_supplement_attempts"] = light_scroll_supplement_attempts
                    if light_scroll_supplement_visible_count:
                        check["light_scroll_supplement_visible_count"] = light_scroll_supplement_visible_count
                    if light_scroll_recovery_attempts:
                        check["light_scroll_recovery_attempts"] = light_scroll_recovery_attempts
                    if light_scroll_recovery_visible_count:
                        check["light_scroll_recovery_visible_count"] = light_scroll_recovery_visible_count
                    if recovery_collect_meta:
                        attach_extract_observability(check, recovery_collect_meta, prefix="recovery_extract")
                    if empty_page_streak_value:
                        check["empty_page_streak"] = empty_page_streak_value
                    if empty_page_recovery:
                        check["empty_page_recovery"] = empty_page_recovery
                    if empty_page_recovery_retries_used:
                        check["empty_page_recovery_retries_used"] = empty_page_recovery_retries_used
                    if partial_page_streak_value:
                        check["partial_page_streak"] = partial_page_streak_value
                    if partial_page_reason:
                        check["partial_page_reason"] = partial_page_reason
                    if partial_page_visible_count:
                        check["partial_page_visible_count"] = partial_page_visible_count
                    if partial_page_min_visible_count:
                        check["partial_page_min_visible_count"] = partial_page_min_visible_count
                    if partial_page_reference_visible_count:
                        check["partial_page_reference_visible_count"] = partial_page_reference_visible_count
                    if partial_page_reference_top_created_at:
                        check["partial_page_reference_top_created_at"] = partial_page_reference_top_created_at
                    if partial_page_recovery:
                        check["partial_page_recovery"] = partial_page_recovery
                    if partial_page_recovery_retries_used:
                        check["partial_page_recovery_retries_used"] = partial_page_recovery_retries_used
                    if late_new_item_recovery:
                        check["late_new_item_recovery"] = late_new_item_recovery
                    if late_new_item_recovery_candidates:
                        check["late_new_item_recovery_candidates"] = late_new_item_recovery_candidates
                    if late_new_item_recovery_delay_value:
                        check["late_new_item_recovery_delay_seconds"] = late_new_item_recovery_delay_value
                    if late_new_item_recovery_max_delay:
                        check["late_new_item_recovery_max_delay_seconds"] = late_new_item_recovery_max_delay
                    if late_new_item_recovery_visible_count:
                        check["late_new_item_recovery_visible_count"] = late_new_item_recovery_visible_count
                    if late_new_item_recovery_error:
                        check["late_new_item_recovery_error"] = late_new_item_recovery_error
                    if soft_recovery_actions and not soft_recovery_action:
                        soft_recovery_action = join_recovery_actions(soft_recovery_actions)
                    if soft_recovery_action:
                        check["soft_recovery_action"] = soft_recovery_action
                    check["baseline_tweet_ids"] = maybe_bootstrap(store, config, target, items, observed_at)
                    check["new_tweet_ids"] = handle_new_items(store, config, executor, target, items, observed_at, delivery_context=check)
                    annotate_check_with_hot_list_acceleration(check, store, target, latest_config, observed_at)
                    if not check.get("new_tweet_ids"):
                        stale_refresh = stale_refresh_state_update(
                            store,
                            target_id,
                            check,
                            latest_config,
                            target,
                            observed_at,
                        )
                        if stale_refresh.get("should_refresh"):
                            stale_refresh_method = clean_text(stale_refresh.get("recovery_method", "")) or "fast_reopen"
                            check["stale_refresh"] = stale_refresh_method
                            check["stale_refresh_top_delay_seconds"] = stale_refresh.get("top_delay_seconds")
                            check["stale_refresh_unchanged_count"] = stale_refresh.get("unchanged_count")
                            check["stale_refresh_cooldown_seconds"] = stale_refresh.get("cooldown_seconds")
                            check["stale_refresh_trigger_count"] = stale_refresh.get("trigger_count")
                            if stale_refresh.get("hot_list_acceleration"):
                                check["hot_list_acceleration"] = True
                                check["hot_list_acceleration_until"] = stale_refresh.get("hot_list_acceleration_until", "")
                                check["hot_list_acceleration_reason"] = stale_refresh.get("hot_list_acceleration_reason", "")
                                check["hot_list_acceleration_delay_seconds"] = stale_refresh.get("hot_list_acceleration_delay_seconds")
                            try:
                                if stale_refresh_method == "full_reload":
                                    target_page, refreshed_items, refresh_meta = full_reload_and_collect_target_page(
                                        target_page,
                                        target_id,
                                        target,
                                        latest_config,
                                        store,
                                        reason="stale_refresh_full_reload",
                                        stop_event=stop_event,
                                    )
                                else:
                                    target_page, refreshed_items, refresh_meta = fast_reopen_and_collect_target_page(
                                        context,
                                        pages,
                                        target_id,
                                        target,
                                        target_page,
                                        latest_config,
                                        store,
                                        reason="stale_refresh",
                                        stop_event=stop_event,
                                    )
                                pages[target_id] = target_page
                                refresh_steps = list(refresh_meta.get("steps", []) or [])
                                refresh_collect_meta = dict(refresh_meta.get("collect_meta", {}) or {})
                                rechecked_items, recheck_meta = stale_refresh_light_scroll_recheck(
                                    target_page,
                                    target,
                                    latest_config,
                                    refreshed_items,
                                    previous_top_tweet_id=check.get("current_top_tweet_id", ""),
                                    stop_event=stop_event,
                                )
                                if recheck_meta:
                                    refreshed_items = rechecked_items
                                    refresh_steps.append("light_scroll_recheck")
                                    refresh_collect_meta.update(recheck_meta)
                                    check["stale_refresh_light_scroll_recheck"] = "light_scroll"
                                    check["stale_refresh_light_scroll_recheck_attempts"] = recheck_meta.get("stale_refresh_light_scroll_recheck_attempts")
                                    check["stale_refresh_light_scroll_recheck_visible_count"] = recheck_meta.get("stale_refresh_light_scroll_recheck_visible_count")
                                if refreshed_items:
                                    items = refreshed_items
                                    observed_at = iso_now()
                                    refreshed_check = build_check_snapshot(items, observed_at, target)
                                    attach_initial_collect_meta(refreshed_check, refresh_collect_meta)
                                    attach_page_surface_observability(
                                        refreshed_check,
                                        {
                                            "state": "ready",
                                            "reason": "visible_timeline_items_present",
                                            "signals": [],
                                        },
                                    )
                                    refreshed_check["stale_refresh"] = stale_refresh_method
                                    refreshed_check["stale_refresh_reason"] = "stale_ready_list"
                                    refreshed_check["stale_refresh_steps"] = join_recovery_actions(refresh_steps)
                                    refreshed_check["stale_refresh_previous_top_tweet_id"] = check.get("current_top_tweet_id", "")
                                    refreshed_check["stale_refresh_previous_top_delay_seconds"] = check.get("top_delay_seconds")
                                    refreshed_check["stale_refresh_unchanged_count"] = stale_refresh.get("unchanged_count")
                                    refreshed_check["stale_refresh_cooldown_seconds"] = stale_refresh.get("cooldown_seconds")
                                    refreshed_check["stale_refresh_trigger_count"] = stale_refresh.get("trigger_count")
                                    if stale_refresh.get("hot_list_acceleration"):
                                        refreshed_check["hot_list_acceleration"] = True
                                        refreshed_check["hot_list_acceleration_until"] = stale_refresh.get("hot_list_acceleration_until", "")
                                        refreshed_check["hot_list_acceleration_reason"] = stale_refresh.get("hot_list_acceleration_reason", "")
                                        refreshed_check["hot_list_acceleration_delay_seconds"] = stale_refresh.get("hot_list_acceleration_delay_seconds")
                                    refreshed_check["baseline_tweet_ids"] = maybe_bootstrap(store, config, target, items, observed_at)
                                    refreshed_check["new_tweet_ids"] = handle_new_items(store, config, executor, target, items, observed_at, delivery_context=refreshed_check)
                                    annotate_check_with_hot_list_acceleration(refreshed_check, store, target, latest_config, observed_at)
                                    check = refreshed_check
                                else:
                                    check["stale_refresh_result"] = (
                                        "no_items_after_full_reload"
                                        if stale_refresh_method == "full_reload"
                                        else "no_items_after_reopen"
                                    )
                                    if refresh_steps:
                                        check["stale_refresh_steps"] = join_recovery_actions(refresh_steps)
                                    if refresh_collect_meta:
                                        attach_extract_observability(check, refresh_collect_meta, prefix="stale_refresh_extract")
                                    activation = activate_hot_list_acceleration(
                                        store,
                                        target_id,
                                        latest_config,
                                        observed_at,
                                        "stale_refresh_no_items",
                                        delay_seconds=check.get("top_delay_seconds"),
                                    )
                                    if activation:
                                        check.update(activation)
                            except Exception as exc:
                                check["stale_refresh_error"] = compact_error_text(str(exc), limit=280)
                    update_auth_state(
                        store,
                        target_id,
                        True,
                        "",
                        current_top_tweet_id=check.get("current_top_tweet_id", ""),
                        current_top_url=check.get("current_top_url", ""),
                    )
                    clear_target_error(store, target_id)
                    clear_error(store)
                    append_recent_check(store, check)
                except Exception as exc:
                    error_text = compact_error_text(str(exc), limit=500)
                    check["error"] = error_text
                    append_recent_check(store, check)
                    record_target_error(store, target_id, error_text)
                    runtime_restart_kind = classify_runtime_restart_error(error_text)
                    if runtime_restart_kind:
                        restart_request = {
                            "kind": runtime_restart_kind,
                            "error": error_text,
                            "mode": target.get("mode", ""),
                            "target_key": target_id,
                            "detected_at": iso_now(),
                            "attempt_restart": browser_crash_auto_restart_enabled(latest_config)
                            and should_attempt_auto_restart(
                                store,
                                runtime_restart_kind,
                                error_text,
                                now_utc(),
                                browser_crash_auto_restart_cooldown_seconds(latest_config),
                            ),
                        }
                        record_error(store, error_text)
                        log_exception(f"monitor_loop[{target_id}]", exc)
                        stop_event.set()
                        break
                    intervention_kind = notify_slot_intervention_if_needed(
                        store,
                        latest_config,
                        error_text,
                        observed_at=now_utc(),
                        mode=target["mode"],
                    )
                    if intervention_kind:
                        cycle_has_slot_intervention = True
                    log_exception(f"monitor_loop[{target_id}]", exc)
            if not stop_event.is_set():
                maybe_schedule_pending_event_recovery(store, latest_config, executor, observed_at=iso_now())
            if not cycle_has_slot_intervention:
                clear_slot_intervention_required(store, cleared_at=iso_now())
            wait_with_stop(stop_event, watch_seconds)
        return {"ok": True}
    finally:
        stop_event.set()
        executor.shutdown(wait=False, cancel_futures=False)
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        try:
            if playwright is not None:
                playwright.stop()
        except Exception:
            pass
        release_service_lock(store)
        mark_service_stopped(store, pid=current_pid, stopped_at=iso_now())
        clear_pid(store)
        if restart_request:
            restart_observed_at = parse_iso_datetime(restart_request.get("detected_at", "")) or now_utc()
            restart_result = {
                "ok": False,
                "error": "browser_crash_auto_restart_skipped",
            }
            if restart_request.get("attempt_restart"):
                try:
                    restart_result = start_service(store)
                except Exception as exc:
                    restart_result = {"ok": False, "error": str(exc)}
                    log_exception("browser_crash_auto_restart", exc)
            remember_event(
                store,
                {
                    "at": restart_request.get("detected_at", iso_now()),
                    "event_type": "service_auto_restart",
                    "tweet_id": f"service-auto-restart:{restart_request.get('detected_at', iso_now())}",
                    "target_key": restart_request.get("target_key", ""),
                    "mode": restart_request.get("mode", ""),
                    "mode_label": mode_label(restart_request.get("mode", "")),
                    "error": restart_request.get("error", ""),
                    "restart_kind": restart_request.get("kind", ""),
                    "restart_kind_label": runtime_restart_kind_label(restart_request.get("kind", "")),
                    "restarted": bool(restart_result.get("ok", False)),
                    "restart_pid": int(restart_result.get("pid", 0) or 0),
                    "restart_result": compact_error_text(
                        restart_result.get("error", "") or restart_result.get("stderr", "") or restart_result.get("stdout", "") or ("ok" if restart_result.get("ok", False) else ""),
                        limit=500,
                    ),
                },
            )
            mark_auto_restart_attempt(
                store,
                restart_request.get("kind", ""),
                restart_observed_at.isoformat(),
                restart_request.get("error", ""),
                restart_result.get("error", "") or restart_result.get("stderr", "") or restart_result.get("stdout", "") or ("ok" if restart_result.get("ok", False) else "skipped"),
            )
            if restart_request.get("kind", "") not in {"persistent_empty_page", "persistent_partial_page"}:
                try:
                    discord_send(
                        config,
                        build_browser_crash_alert(
                            config,
                            restart_request.get("kind", ""),
                            restart_request.get("error", ""),
                            mode=restart_request.get("mode", ""),
                            restart_result=restart_result,
                        ),
                    )
                except Exception as exc:
                    log_exception("send_browser_crash_alert", exc)


def start_service(store):
    config = runtime_config(store)
    parse_error = config_parse_error(config)
    if parse_error:
        record_error(store, f"invalid config: {parse_error}")
        return {
            "ok": False,
            "action": "start",
            "running": False,
            "error": "invalid_config",
            "config_parse_error": parse_error,
        }
    missing = config_missing(config)
    if missing:
        return {"ok": False, "action": "start", "running": False, "error": "missing_config", "config_missing": missing}
    slot_binding = load_x_monitor_slot_binding(config.get("source_slot", DEFAULT_SOURCE_SLOT))
    slot_binding_parse_error = slot_binding_config_parse_error(slot_binding)
    if slot_binding_parse_error:
        error_message = f"slot binding config invalid: {slot_binding.get('config_path', '')}: {slot_binding_parse_error}"
        record_error(store, error_message)
        notify_slot_intervention_if_needed(store, config, error_message, observed_at=now_utc())
        return invalid_slot_binding_payload("start", slot_binding, running=False)
    current_state = store.load_state()
    pid, detected_by = resolve_running_service_pid(store, current_state)
    if pid:
        if read_pid(store) != pid:
            write_pid(store, pid)
        return {
            "ok": True,
            "action": "start",
            "running": True,
            "pid": pid,
            "config_missing": missing,
            "already_running": True,
            "running_detected_by": detected_by,
        }
    clear_pid(store)
    log_handle = open(store.log_path, "a", encoding="utf-8")
    process = subprocess.Popen(
        [preferred_background_python(), str(Path(__file__).resolve()), "--root", str(store.root), "serve"],
        stdout=log_handle,
        stderr=log_handle,
        stdin=subprocess.DEVNULL,
        cwd=str(Path(__file__).resolve().parent),
        creationflags=WINDOWS_CREATE_NO_WINDOW | WINDOWS_DETACHED_PROCESS | WINDOWS_CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    write_pid(store, process.pid)
    running, pid, detected_by = wait_for_service_start(store, candidate_pid=process.pid)
    return {
        "ok": running,
        "action": "start",
        "running": running,
        "pid": pid,
        "running_detected_by": detected_by,
        "config_missing": missing,
        "log_path": str(store.log_path),
    }


def stop_service(store):
    state = store.load_state()
    pid = read_pid(store) or state_service_pid(state)
    if not pid or not is_process_running(pid):
        clear_pid(store)
        mark_service_stopped(store, stopped_at=iso_now())
        return {"ok": True, "action": "stop", "running": False, "stopped": False}
    result = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
        creationflags=WINDOWS_CREATE_NO_WINDOW,
    )
    stopped = wait_for_process_stop(pid)
    if stopped:
        clear_pid(store)
        mark_service_stopped(store, pid=pid, stopped_at=iso_now())
    else:
        write_pid(store, pid)
    return {
        "ok": bool(result.returncode == 0 and stopped),
        "action": "stop",
        "running": not stopped,
        "pid": pid,
        "stdout": clean_text(result.stdout),
        "stderr": clean_text(result.stderr),
    }


def recent_events(store, limit=10, modes=None):
    state = store.load_state()
    items = list(state.get("recent_events", []))
    normalized_modes = {normalize_mode(mode) for mode in (modes or []) if normalize_mode(mode)}
    if normalized_modes:
        items = [item for item in items if normalize_mode(item.get("mode", "")) in normalized_modes]
    return {"ok": True, "action": "recent", "count": min(len(items), limit), "events": items[-limit:][::-1]}


def recent_checks(store, limit=10, modes=None):
    state = store.load_state()
    items = list(state.get("recent_checks", []))
    normalized_modes = {normalize_mode(mode) for mode in (modes or []) if normalize_mode(mode)}
    if normalized_modes:
        items = [item for item in items if normalize_mode(item.get("mode", "")) in normalized_modes]
    return {"ok": True, "action": "checks", "count": min(len(items), limit), "checks": items[-limit:][::-1]}


def status(store):
    config = runtime_config(store)
    parse_error = config_parse_error(config)
    state = store.load_state()
    pid, running_detected_by = resolve_running_service_pid(store, state)
    running = bool(pid)
    slot_binding = load_x_monitor_slot_binding(config.get("source_slot", DEFAULT_SOURCE_SLOT))
    list_configs = normalize_list_configs(config)
    modes_payload = {}

    home_state = base_target_state()
    home_state.update(dict(state.get("targets", {}).get(MODE_HOME, {})))
    modes_payload[MODE_HOME] = {
        "enabled": config_bool(config.get("x_home_enabled", True), True),
        "label": mode_label(MODE_HOME),
        "url": clean_text(config.get("x_home_url", "")),
        "auth_ready": bool(home_state.get("auth_ready", False)),
        "auth_error": clean_text(home_state.get("auth_error", "")),
        "current_top_tweet_id": clean_text(home_state.get("current_top_tweet_id", "")),
        "current_top_url": clean_text(home_state.get("current_top_url", "")),
        "last_successful_check_at": clean_text(home_state.get("last_successful_check_at", "")),
        "last_reload_at": clean_text(home_state.get("last_reload_at", "")),
        "last_error": clean_text(home_state.get("last_error", "")),
        "bootstrapped": bool(home_state.get("bootstrapped", False)),
    }

    list_rows = []
    for index, entry in enumerate(list_configs, start=1):
        target_id = list_target_key(index)
        target_state = base_target_state()
        target_state.update(dict(state.get("targets", {}).get(target_id, {})))
        list_rows.append(
            {
                "id": target_id,
                "index": index,
                "name": clean_text(entry.get("name", "")) or f"列表{index}",
                "enabled": bool(entry.get("enabled", False)),
                "url": clean_text(entry.get("url", "")),
                "configured": bool(clean_text(entry.get("url", ""))),
                "auth_ready": bool(target_state.get("auth_ready", False)),
                "auth_error": clean_text(target_state.get("auth_error", "")),
                "current_top_tweet_id": clean_text(target_state.get("current_top_tweet_id", "")),
                "current_top_url": clean_text(target_state.get("current_top_url", "")),
                "last_successful_check_at": clean_text(target_state.get("last_successful_check_at", "")),
                "last_reload_at": clean_text(target_state.get("last_reload_at", "")),
                "last_error": clean_text(target_state.get("last_error", "")),
                "bootstrapped": bool(target_state.get("bootstrapped", False)),
            }
        )

    enabled_list_rows = [row for row in list_rows if row["enabled"] and row["url"]]
    latest_enabled_list = None
    if enabled_list_rows:
        latest_enabled_list = max(
            enabled_list_rows,
            key=lambda row: parse_iso_datetime(row.get("last_successful_check_at", "")) or datetime.min.replace(tzinfo=timezone.utc),
        )
    modes_payload[MODE_LIST] = {
        "enabled": bool(enabled_list_rows),
        "label": mode_label(MODE_LIST),
        "url": clean_text((latest_enabled_list or {}).get("url", "")) or clean_text(config.get("x_list_url", "")),
        "list_count": len(enabled_list_rows),
        "auth_ready": bool(enabled_list_rows) and all(row.get("auth_ready", False) for row in enabled_list_rows),
        "auth_error": clean_text((latest_enabled_list or {}).get("auth_error", "")),
        "current_top_tweet_id": clean_text((latest_enabled_list or {}).get("current_top_tweet_id", "")),
        "current_top_url": clean_text((latest_enabled_list or {}).get("current_top_url", "")),
        "last_successful_check_at": clean_text((latest_enabled_list or {}).get("last_successful_check_at", "")),
        "last_reload_at": clean_text((latest_enabled_list or {}).get("last_reload_at", "")),
        "last_error": clean_text((latest_enabled_list or {}).get("last_error", "")),
        "bootstrapped": bool(enabled_list_rows) and all(row.get("bootstrapped", False) for row in enabled_list_rows),
    }
    return {
        "ok": True,
        "action": "status",
        "service": SERVICE_NAME,
        "running": running,
        "pid": pid if running else 0,
        "running_detected_by": running_detected_by,
        "config_missing": config_missing(config),
        "config_valid": config_is_valid(config),
        "config_parse_error": parse_error,
        "state_valid": state_is_valid(state),
        "state_parse_error": state_parse_error(state),
        "state_last_recovery_at": clean_text(state.get("state_last_recovery_at", "")),
        "state_last_recovery_error": clean_text(state.get("state_last_recovery_error", "")),
        "state_last_recovery_backup_path": clean_text(state.get("state_last_recovery_backup_path", "")),
        "legacy_x_monitor_defaults": {
            "config_exists": bool(config.get(LEGACY_DEFAULTS_CONFIG_EXISTS_KEY, False)),
            "config_valid": legacy_defaults_are_valid(config),
            "config_parse_error": legacy_defaults_parse_error(config),
            "config_path": clean_text(config.get(LEGACY_DEFAULTS_CONFIG_PATH_KEY, "")),
        },
        "source_slot": normalize_source_slot(config.get("source_slot", DEFAULT_SOURCE_SLOT)),
        "source_slot_label": source_slot_label(config.get("source_slot", DEFAULT_SOURCE_SLOT)),
        "slot_binding": {
            "slot": slot_binding["slot"],
            "label": source_slot_label(slot_binding["slot"]),
            "root": slot_binding["root"],
            "config_path": slot_binding["config_path"],
            "config_exists": slot_binding["config_exists"],
            "config_valid": slot_binding_is_valid(slot_binding),
            "config_parse_error": clean_text(slot_binding.get("config_parse_error", "")),
            "cookies_path": slot_binding["cookies_path"],
            "cookies_exists": slot_binding["cookies_exists"],
            "profile_dir": slot_binding["profile_dir"],
            "profile_exists": slot_binding["profile_exists"],
        },
        "slot_operator_action": slot_operator_action_status(state),
        "auto_restart": auto_restart_status(state),
        "enabled_modes": enabled_mode_names(config),
        "modes": modes_payload,
        "lists": list_rows,
        "x_home_url": clean_text(config.get("x_home_url", "")),
        "x_list_url": clean_text(config.get("x_list_url", "")),
        "x_lists": list_configs,
        "watch_interval_seconds": clamp_int(config.get("watch_interval_seconds", DEFAULT_WATCH_INTERVAL_SECONDS), DEFAULT_WATCH_INTERVAL_SECONDS, minimum=2, maximum=60),
        "reload_interval_seconds": clamp_int(config.get("reload_interval_seconds", DEFAULT_RELOAD_INTERVAL_SECONDS), DEFAULT_RELOAD_INTERVAL_SECONDS, minimum=5, maximum=300),
        "target_check_jitter_milliseconds": clamp_int(config.get("target_check_jitter_milliseconds", DEFAULT_TARGET_CHECK_JITTER_MILLISECONDS), DEFAULT_TARGET_CHECK_JITTER_MILLISECONDS, minimum=0, maximum=5000),
        "reload_interval_jitter_seconds": clamp_int(config.get("reload_interval_jitter_seconds", DEFAULT_RELOAD_INTERVAL_JITTER_SECONDS), DEFAULT_RELOAD_INTERVAL_JITTER_SECONDS, minimum=0, maximum=120),
        "empty_page_wave_canary_enabled": empty_page_wave_canary_enabled(config),
        "empty_page_wave_canary_wait_milliseconds": empty_page_wave_canary_wait_milliseconds(config),
        "partial_page_min_visible_count": partial_page_min_visible_count(config, {"mode": MODE_LIST}),
        "browser_headless": config_bool(config.get("browser_headless", True), True),
        "profile_dir": clean_text(config.get("x_browser_profile_dir", "")),
        "x_cookies_path": clean_text(config.get("x_cookies_path", "")),
        "auth_status": {"ready": bool(state.get("auth_ready", False)), "error": clean_text(state.get("auth_error", ""))},
        "editor_draft": {
            "enabled": config_bool(config.get("editor_draft_enabled", DEFAULT_EDITOR_DRAFT_ENABLED), DEFAULT_EDITOR_DRAFT_ENABLED),
            "api_base": clean_text(config.get("editor_draft_api_base", "")),
            "model": clean_text(config.get("editor_draft_model", "")),
            "fallback_api_base": clean_text(config.get("editor_draft_fallback_api_base", "")),
            "fallback_model": clean_text(config.get("editor_draft_fallback_model", "")),
            "fallback_enabled": bool(clean_text(config.get("editor_draft_fallback_api_base", "")) and clean_text(config.get("editor_draft_fallback_api_key", "")) and clean_text(config.get("editor_draft_fallback_model", ""))),
            "timeout_seconds": clamp_int(config.get("editor_draft_timeout_seconds", DEFAULT_EDITOR_DRAFT_TIMEOUT_SECONDS), DEFAULT_EDITOR_DRAFT_TIMEOUT_SECONDS, minimum=5, maximum=180),
            "min_interval_seconds": editor_draft_min_interval_seconds(config),
            "rate_limit_cooldown_seconds": editor_draft_rate_limit_cooldown_seconds(config),
            "cooldown_until": clean_text(state.get("editor_draft_cooldown_until", "")),
            "last_error": clean_text(state.get("editor_draft_last_error", "")),
        },
        "local_fast_translation": {
            "enabled": config_bool(config.get("local_fast_translation_enabled", DEFAULT_LOCAL_FAST_TRANSLATION_ENABLED), DEFAULT_LOCAL_FAST_TRANSLATION_ENABLED),
            "api_base": clean_text(config.get("local_fast_translation_api_base", "")),
            "model": clean_text(config.get("local_fast_translation_model", "")),
            "timeout_seconds": local_fast_translation_timeout_seconds(config),
            "initial_timeout_seconds": local_fast_translation_timeout_seconds(config, initial_delivery=True),
            "initial_failure_cooldown_seconds": local_fast_translation_initial_failure_cooldown_seconds(config),
        },
        "async_enrich_max_workers": async_enrich_max_workers(config),
        "current_top_tweet_id": clean_text(state.get("current_top_tweet_id", "")),
        "current_top_url": clean_text(state.get("current_top_url", "")),
        "last_service_start_at": clean_text(state.get("last_service_start_at", "")),
        "last_service_stop_at": clean_text(state.get("last_service_stop_at", "")),
        "service_pid": state_service_pid(state),
        "service_heartbeat_at": clean_text(state.get("service_heartbeat_at", "")),
        "last_successful_check_at": clean_text(state.get("last_successful_check_at", "")),
        "last_reload_at": clean_text(state.get("last_reload_at", "")),
        "last_error": clean_text(state.get("last_error", "")),
        "recent_events": list(state.get("recent_events", []))[-5:][::-1],
        "recent_checks": list(state.get("recent_checks", []))[-5:][::-1],
        "log_path": str(store.log_path),
        "config_path": str(store.config_path),
        "root_path": str(store.root),
    }


def configure(store, key, value):
    config, error = load_editable_config_or_error(store, "configure")
    if error:
        return error
    normalized_key = str(key)
    parsed_value = value
    if normalized_key == "x_lists":
        parsed_value_details = parse_json_like_details(value, fallback=[])
        if clean_text(parsed_value_details.get("parse_error", "")):
            return {
                "ok": False,
                "action": "configure",
                "key": normalized_key,
                "error": "invalid_json_value",
                "value_parse_error": clean_text(parsed_value_details.get("parse_error", "")),
            }
        parsed_value = parsed_value_details["value"]
    config[normalized_key] = parsed_value
    store.save_config(config)
    return {"ok": True, "action": "configure", "key": normalized_key, "value": parsed_value}


def extract_limit(text, default=10, minimum=1, maximum=20):
    match = re.search(r"(?<!\d)(\d{1,2})(?!\d)", str(text or ""))
    if not match:
        return default
    return max(minimum, min(maximum, int(match.group(1))))


def preview_mode_flags(config, modes, enabled):
    config = dict(config or {})
    touched = []
    for mode in modes:
        normalized = normalize_mode(mode)
        if not normalized:
            continue
        if normalized == MODE_LIST:
            entries = normalize_list_configs(config)
            changed = False
            for entry in entries:
                desired = bool(enabled) and bool(clean_text(entry.get("url", "")))
                if bool(entry.get("enabled", False)) != desired:
                    entry["enabled"] = desired
                    changed = True
            if changed:
                config["x_lists"] = entries
                config = sync_legacy_list_config_fields(config)
                touched.append(normalized)
            continue
        key = f"x_{normalized}_enabled"
        default_value = normalized == MODE_HOME
        current = config_bool(config.get(key, default_value), default_value)
        if current != bool(enabled):
            config[key] = bool(enabled)
            touched.append(normalized)
    return config, touched


def apply_list_change(store, list_indexes, enabled):
    normalized_indexes = []
    for value in list_indexes or []:
        try:
            index = int(value)
        except Exception:
            continue
        if 1 <= index <= DEFAULT_MAX_LIST_TARGETS and index not in normalized_indexes:
            normalized_indexes.append(index)
    current_runtime = runtime_config(store)
    running_pid, _ = resolve_running_service_pid(store)
    was_running = bool(running_pid)
    config, error = load_editable_config_or_error(store, "configure_lists")
    if error:
        error["running"] = was_running
        error["updated_lists"] = []
        error["enabled_modes"] = enabled_mode_names(current_runtime)
        error["running_before_change"] = was_running
        error["list_change"] = "enable" if enabled else "disable"
        return error
    entries = normalize_list_configs(config)
    touched = []
    for index in normalized_indexes:
        entry = dict(entries[index - 1])
        desired = bool(enabled) and bool(clean_text(entry.get("url", "")))
        if bool(entry.get("enabled", False)) != desired:
            entry["enabled"] = desired
            entries[index - 1] = entry
            touched.append(index)
    if not touched:
        requested_entries = [entries[index - 1] for index in normalized_indexes if 1 <= index <= len(entries)]
        requested_enabled = any(bool(entry.get("enabled", False)) and clean_text(entry.get("url", "")) for entry in requested_entries)
        if enabled and not was_running and requested_enabled and enabled_targets(current_runtime):
            payload = start_service(store)
            payload["updated_lists"] = []
            payload["enabled_modes"] = enabled_mode_names(current_runtime)
            payload["running_before_change"] = was_running
            payload["list_change"] = "enable"
            return payload
        payload = status(store)
        payload["updated_lists"] = []
        payload["running_before_change"] = was_running
        payload["list_change"] = "enable" if enabled else "disable"
        return payload
    config["x_lists"] = entries
    preview_config = runtime_config_with_overrides(store, config)
    preview_missing = config_missing(preview_config)
    if enabled and preview_missing:
        return {
            "ok": False,
            "action": "configure_lists",
            "running": was_running,
            "error": "missing_config",
            "config_missing": preview_missing,
            "updated_lists": [],
            "enabled_modes": enabled_mode_names(current_runtime),
            "running_before_change": was_running,
            "list_change": "enable",
        }
    store.save_config(config)
    latest_runtime = runtime_config(store)
    if was_running:
        stop_service(store)
        time.sleep(1)
    if was_running:
        if enabled_targets(latest_runtime):
            payload = start_service(store)
        else:
            payload = {"ok": True, "action": "stop", "running": False, "stopped": True}
    elif enabled and enabled_targets(latest_runtime):
        payload = start_service(store)
    else:
        payload = status(store)
        payload["action"] = "configure_lists"
        payload["running"] = False
    payload["updated_lists"] = touched
    payload["enabled_modes"] = enabled_mode_names(latest_runtime)
    payload["running_before_change"] = was_running
    payload["list_change"] = "enable" if enabled else "disable"
    return payload


def apply_mode_change(store, modes, enabled):
    current_runtime = runtime_config(store)
    running_pid, _ = resolve_running_service_pid(store)
    was_running = bool(running_pid)
    base_config_payload, error = load_editable_config_or_error(store, "configure_modes")
    if error:
        error["running"] = was_running
        error["updated_modes"] = []
        error["enabled_modes"] = enabled_mode_names(current_runtime)
        error["running_before_change"] = was_running
        error["mode_change"] = "enable" if enabled else "disable"
        return error
    raw_config, touched = preview_mode_flags(base_config_payload, modes, enabled)
    if not touched:
        requested_modes = {normalize_mode(mode) for mode in (modes or []) if normalize_mode(mode)}
        current_modes = set(enabled_mode_names(current_runtime))
        if enabled and not was_running and requested_modes.intersection(current_modes) and enabled_targets(current_runtime):
            payload = start_service(store)
            payload["updated_modes"] = []
            payload["enabled_modes"] = enabled_mode_names(current_runtime)
            payload["running_before_change"] = was_running
            payload["mode_change"] = "enable"
            return payload
        payload = status(store)
        payload["updated_modes"] = []
        payload["enabled_modes"] = enabled_mode_names(current_runtime)
        payload["running_before_change"] = was_running
        payload["mode_change"] = "enable" if enabled else "disable"
        return payload
    preview_config = runtime_config_with_overrides(store, raw_config)
    preview_missing = config_missing(preview_config)
    if enabled and preview_missing:
        return {
            "ok": False,
            "action": "configure_modes",
            "running": was_running,
            "error": "missing_config",
            "config_missing": preview_missing,
            "updated_modes": [],
            "enabled_modes": enabled_mode_names(current_runtime),
            "running_before_change": was_running,
            "mode_change": "enable",
        }
    store.save_config(raw_config)
    config = runtime_config(store)
    if was_running:
        stop_service(store)
        time.sleep(1)
    remaining_modes = enabled_mode_names(config)
    if was_running:
        if enabled_targets(config):
            payload = start_service(store)
        else:
            payload = {"ok": True, "action": "stop", "running": False, "stopped": True}
    elif enabled and enabled_targets(config):
        payload = start_service(store)
    else:
        payload = status(store)
        payload["action"] = "configure_modes"
        payload["running"] = False
    payload["updated_modes"] = touched
    payload["enabled_modes"] = remaining_modes
    payload["running_before_change"] = was_running
    payload["mode_change"] = "enable" if enabled else "disable"
    return payload


def apply_slot_change(store, slot):
    normalized_slot = normalize_source_slot(slot)
    config, error = load_editable_config_or_error(store, "switch_slot")
    if error:
        running_pid, _ = resolve_running_service_pid(store)
        error["running"] = bool(running_pid)
        error["requested_slot"] = normalized_slot
        error["requested_slot_label"] = source_slot_label(normalized_slot)
        return error
    slot_binding = load_x_monitor_slot_binding(normalized_slot)
    if not slot_binding_is_valid(slot_binding):
        running_pid, _ = resolve_running_service_pid(store)
        payload = invalid_slot_binding_payload("switch_slot", slot_binding, running=bool(running_pid))
        payload["requested_slot"] = normalized_slot
        payload["requested_slot_label"] = source_slot_label(normalized_slot)
        return payload
    previous_slot = normalize_source_slot(config.get("source_slot", DEFAULT_SOURCE_SLOT))
    config["source_slot"] = normalized_slot
    config["x_browser_profile_dir"] = slot_binding["profile_dir"]
    config["x_cookies_path"] = slot_binding["cookies_path"]
    store.save_config(config)

    pid_before, _ = resolve_running_service_pid(store)
    was_running = bool(pid_before)
    restart_payload = None
    if was_running:
        stop_service(store)
        time.sleep(1)
        restart_payload = start_service(store)

    store.update_state(lambda state: state.__setitem__("source_slot", normalized_slot))
    current_status = status(store)
    current_status.update(
        {
            "action": "switch_slot",
            "requested_slot": normalized_slot,
            "requested_slot_label": source_slot_label(normalized_slot),
            "previous_slot": previous_slot,
            "previous_slot_label": source_slot_label(previous_slot),
            "running_before_change": was_running,
            "restarted": was_running,
            "restart_result": restart_payload,
        }
    )
    return current_status


def legacy_extract_request_modes_unused(text):
    return extract_request_modes(text)


def extract_request_slot(text):
    raw = str(text or "")
    lower = raw.lower()
    slot_tokens = {
        "1": ("\u0031\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0031", "\u0031\u53f7"),
        "2": ("\u0032\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0032", "\u0032\u53f7"),
        "3": ("\u0033\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0033", "\u0033\u53f7"),
        "4": ("\u0034\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0034", "\u0034\u53f7"),
        "5": ("\u0035\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0035", "\u0035\u53f7"),
        "6": ("\u0036\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0036", "\u0036\u53f7"),
        "7": ("\u0037\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0037", "\u0037\u53f7"),
    }
    for slot_value in ("7", "6", "5", "4", "3", "2", "1"):
        if f"slot {slot_value}" in lower or any(token in raw for token in slot_tokens[slot_value]):
            return slot_value
    match = re.search(
        r"(?:slot|\u69fd\u4f4d|\u5207\u5230|\u5207\u6362(?:\u5230)?|\u6362\u5230|\u6539\u5230)\s*([1-7])",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        return normalize_source_slot(match.group(1))
    return ""



def extract_request_list_indexes(text):
    raw = str(text or "")
    lower = raw.lower()
    indexes = []
    for match in re.finditer(r"(?:第\s*([1-5])\s*列表|list\s*([1-5])|([1-5])\s*列表)", raw, flags=re.IGNORECASE):
        value = next((group for group in match.groups() if group), "")
        if not value:
            continue
        index = int(value)
        if 1 <= index <= DEFAULT_MAX_LIST_TARGETS and index not in indexes:
            indexes.append(index)
    if "列表" in raw or "list" in lower:
        for match in re.finditer(r"(?<!\d)([1-5])(?!\d)", raw):
            index = int(match.group(1))
            if index not in indexes:
                indexes.append(index)
    return indexes


def extract_request_list_indexes_normalized(text):
    return extract_request_list_indexes_clean(text)


def extract_request_list_indexes_clean(text):
    raw = str(text or "")
    lower = raw.lower()
    indexes = []
    pattern = r"(?:\u7b2c\s*([1-5])\s*\u53f7?\s*\u5217\u8868|\u5217\u8868\s*([1-5])|list\s*([1-5])|([1-5])\s*\u53f7?\s*\u5217\u8868)"
    for match in re.finditer(pattern, raw, flags=re.IGNORECASE):
        value = next((group for group in match.groups() if group), "")
        if not value:
            continue
        index = int(value)
        if 1 <= index <= DEFAULT_MAX_LIST_TARGETS and index not in indexes:
            indexes.append(index)
    if "\u5217\u8868" in raw or "list" in lower:
        for match in re.finditer(r"(?<!\d)([1-5])(?!\d)", raw):
            index = int(match.group(1))
            if index not in indexes:
                indexes.append(index)
    return indexes


def legacy_parse_request_unused(text):
    return parse_request(text)


def keyword_positions(text, keywords):
    positions = []
    for keyword in keywords:
        start = 0
        while True:
            index = text.find(keyword, start)
            if index < 0:
                break
            positions.append(index)
            start = index + len(keyword)
    return positions


def has_affirmative_keyword(text, keywords, negations=None, window=10):
    negations = tuple(negations or ())
    for index in keyword_positions(text, keywords):
        prefix = text[max(0, index - window):index]
        if not any(neg in prefix for neg in negations):
            return True
    return False


def is_why_question(text):
    raw = str(text or "")
    lower = raw.lower()
    return any(
        token in raw
        for token in (
            "\u4e3a\u4ec0\u4e48",
            "\u4e3a\u4f55",
            "\u600e\u4e48\u603b\u662f",
            "\u600e\u4e48\u6bcf\u6b21",
            "\u600e\u4e48\u8001\u662f",
            "\u54ea\u91cc\u4e0d\u5bf9",
        )
    ) or any(token in lower for token in ("why", "why does", "why is", "why every"))


def is_explicit_slot_switch(text, requested_slot):
    if not requested_slot:
        return False
    raw = str(text or "")
    lower = raw.lower()
    slot_value = re.escape(str(requested_slot))
    if re.search(rf"(?:switch|change|move|use)\s*(?:xplus\s*)?(?:to\s*)?(?:slot\s*)?{slot_value}\b", lower):
        return True
    if re.search(
        rf"(?:\u5207\u5230|\u5207\u6362(?:\u5230)?|\u6362\u5230|\u6539\u5230|\u7ed1\u5b9a(?:\u5230)?|\u7528)\s*(?:xplus|x\+|x plus|xmonitorplus|\u76d1\u63a7)?\s*(?:\u5230\s*)?(?:{slot_value}\s*\u53f7?\s*\u69fd\u4f4d|\u69fd\u4f4d\s*{slot_value}|{slot_value}\s*\u53f7)",
        raw,
        flags=re.IGNORECASE,
    ):
        return True
    slot_tokens = (
        f"{requested_slot}\u53f7\u69fd\u4f4d",
        f"\u69fd\u4f4d{requested_slot}",
        f"{requested_slot}\u53f7",
    )
    switch_tokens = ("\u5207\u5230", "\u5207\u6362", "\u6362\u5230", "\u6539\u5230", "\u7ed1\u5b9a", "\u7528")
    return (
        "xplus" in lower
        and any(token in raw for token in slot_tokens)
        and any(token in raw for token in switch_tokens)
    )

def extract_request_slot_clean(text):
    raw = str(text or "")
    lower = raw.lower()
    slot_tokens = {
        "1": ("\u0031\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0031", "\u0031\u53f7"),
        "2": ("\u0032\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0032", "\u0032\u53f7"),
        "3": ("\u0033\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0033", "\u0033\u53f7"),
        "4": ("\u0034\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0034", "\u0034\u53f7"),
        "5": ("\u0035\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0035", "\u0035\u53f7"),
        "6": ("\u0036\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0036", "\u0036\u53f7"),
        "7": ("\u0037\u53f7\u69fd\u4f4d", "\u69fd\u4f4d\u0037", "\u0037\u53f7"),
    }
    for slot_value in ("7", "6", "5", "4", "3", "2", "1"):
        if f"slot {slot_value}" in lower or any(token in raw for token in slot_tokens[slot_value]):
            return slot_value
    match = re.search(
        r"(?:slot|\u69fd\u4f4d|\u5207\u5230|\u5207\u6362(?:\u5230)?|\u6362\u5230|\u6539\u5230)\s*([1-7])",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        return normalize_source_slot(match.group(1))
    return ""



def extract_request_modes(text, intent=""):
    raw = str(text or "")
    lower = raw.lower()
    modes = []
    allow_negated_mentions = str(intent or "").lower() == "stop"
    raw_negations = () if allow_negated_mentions else (
        "\u4e0d\u8981",
        "\u522b",
        "\u4e0d\u7528",
        "\u4e0d\u60f3",
        "\u522b\u7528",
        "\u4e0d\u662f",
        "\u5173\u95ed",
        "\u5173\u6389",
        "\u505c\u7528",
    )
    lower_negations = () if allow_negated_mentions else (
        "don't",
        "dont",
        "do not",
        "not ",
        "without",
        "disable",
        "disabled",
        "avoid",
    )
    if has_affirmative_keyword(raw, ("\u63a8\u8350", "\u9996\u9875"), raw_negations) or has_affirmative_keyword(lower, ("home", "recommend", "feed", "timeline"), lower_negations):
        modes.append(MODE_HOME)
    if has_affirmative_keyword(raw, ("\u5217\u8868", "\u6e05\u5355"), raw_negations) or has_affirmative_keyword(lower, ("list", "lists"), lower_negations):
        modes.append(MODE_LIST)
    return list(dict.fromkeys(modes))


def parse_request(text):
    raw = str(text or "")
    lower = raw.lower()
    start_requested = any(token in lower for token in ("start",)) or any(token in raw for token in ("\u542f\u52a8", "\u5f00\u542f"))
    stop_requested = any(token in lower for token in ("stop",)) or any(token in raw for token in ("\u505c\u6b62", "\u5173\u95ed"))
    modes = extract_request_modes(raw, intent="stop" if stop_requested else "start" if start_requested else "")
    requested_slot = extract_request_slot_clean(raw)
    requested_lists = extract_request_list_indexes_clean(raw)
    if any(token in lower for token in ("check", "recent check", "recent checks")) or "\u68c0\u67e5" in raw:
        return {"action": "checks", "limit": extract_limit(raw), "modes": modes, "lists": requested_lists}
    if any(token in lower for token in ("recent", "event", "events")) or any(token in raw for token in ("\u6700\u8fd1", "\u63a8\u9001")):
        return {"action": "recent", "limit": extract_limit(raw), "modes": modes, "lists": requested_lists}
    if is_why_question(raw):
        return {"action": "status", "modes": [], "lists": []}
    if is_explicit_slot_switch(raw, requested_slot):
        return {"action": "switch_slot", "slot": requested_slot, "modes": modes, "lists": requested_lists}
    if start_requested:
        if requested_lists:
            return {"action": "start_lists", "modes": modes, "lists": requested_lists}
        return {"action": "start_modes" if modes else "start", "modes": modes, "lists": requested_lists}
    if stop_requested:
        if requested_lists:
            return {"action": "stop_lists", "modes": modes, "lists": requested_lists}
        return {"action": "stop_modes" if modes else "stop", "modes": modes, "lists": requested_lists}
    return {"action": "status", "modes": modes, "lists": requested_lists}


def handle_request(store, text):
    parsed = parse_request(text)
    action = parsed["action"]
    if action == "start":
        payload = start_service(store)
    elif action == "switch_slot":
        payload = apply_slot_change(store, parsed.get("slot", DEFAULT_SOURCE_SLOT))
    elif action == "start_lists":
        payload = apply_list_change(store, parsed.get("lists", []), True)
    elif action == "start_modes":
        payload = apply_mode_change(store, parsed.get("modes", []), True)
    elif action == "stop":
        payload = stop_service(store)
    elif action == "stop_lists":
        payload = apply_list_change(store, parsed.get("lists", []), False)
    elif action == "stop_modes":
        payload = apply_mode_change(store, parsed.get("modes", []), False)
    elif action == "recent":
        payload = recent_events(store, parsed.get("limit", 10), parsed.get("modes", []))
    elif action == "checks":
        payload = recent_checks(store, parsed.get("limit", 10), parsed.get("modes", []))
    else:
        payload = status(store)
    payload["parsed"] = parsed
    return payload


def build_parser():
    parser = argparse.ArgumentParser(description=SERVICE_NAME)
    parser.add_argument("--root", default="")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("status")
    sub.add_parser("open-profile")
    recent_parser = sub.add_parser("recent")
    recent_parser.add_argument("--limit", type=int, default=10)
    checks_parser = sub.add_parser("checks")
    checks_parser.add_argument("--limit", type=int, default=10)
    request_parser = sub.add_parser("request")
    request_parser.add_argument("--text", required=True)
    configure_parser = sub.add_parser("configure")
    configure_parser.add_argument("--key", required=True)
    configure_parser.add_argument("--value", required=True)
    return parser




def main():
    configure_stdio()
    sanitize_proxy_environment()
    args = build_parser().parse_args()
    store = Store(root=args.root or None)
    try:
        if args.command == "serve":
            payload = run_service(store)
        elif args.command == "start":
            payload = start_service(store)
        elif args.command == "stop":
            payload = stop_service(store)
        elif args.command == "status":
            payload = status(store)
        elif args.command == "open-profile":
            payload = open_profile(store)
        elif args.command == "recent":
            payload = recent_events(store, args.limit)
        elif args.command == "checks":
            payload = recent_checks(store, args.limit)
        elif args.command == "request":
            payload = handle_request(store, args.text)
        else:
            payload = configure(store, args.key, args.value)
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload.get("ok", True) else 1
    except requests.HTTPError as exc:
        body = exc.response.text if exc.response is not None else ""
        print(json.dumps({"ok": False, "error": str(exc), "status_code": exc.response.status_code if exc.response is not None else None, "body": body}, ensure_ascii=False))
        return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
