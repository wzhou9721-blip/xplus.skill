import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


SERVICE_NAME = "x-monitor-plus-watchdog"
XPLUS_SERVICE_NAME = "x-monitor-plus"
DEFAULT_STORAGE_BASE = Path(os.environ.get("X_MONITORPLUS_STORAGE_BASE", "")) if os.environ.get("X_MONITORPLUS_STORAGE_BASE", "").strip() else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "XMonitorPlus"
DEFAULT_ROOT = DEFAULT_STORAGE_BASE / SERVICE_NAME
DEFAULT_SLOT_ROOTS = (
    DEFAULT_STORAGE_BASE / "x-monitor-plus",
    DEFAULT_STORAGE_BASE / "x-monitor-plus-2",
)
DEFAULT_POLL_SECONDS = 60
DEFAULT_HEARTBEAT_STALE_SECONDS = 180
DEFAULT_CHECK_ARCHIVE_STALE_SECONDS = 180
DEFAULT_READY_STALE_SECONDS = 600
DEFAULT_RESTART_COOLDOWN_SECONDS = 900
DEFAULT_START_GRACE_SECONDS = 120
DEFAULT_SEMANTIC_WINDOW_SECONDS = 15 * 60
DEFAULT_READY_STALE_RESTART_ENABLED = False
DEFAULT_SEMANTIC_RESTART_ENABLED = False
DEFAULT_SEMANTIC_LATE_RECOVERY_RESTART_COUNT = 2
DEFAULT_SEMANTIC_LATE_RECOVERY_MAX_DELAY_SECONDS = 300
DEFAULT_SEMANTIC_STATIC_TOP_DELAY_SECONDS = 60 * 60
DEFAULT_SEMANTIC_STATIC_CHECK_COUNT = 8
DEFAULT_SEMANTIC_HARD_EMPTY_RESTART_COUNT = 24
DEFAULT_SEMANTIC_HARD_EMPTY_RESTART_SECONDS = 120
DEFAULT_TAIL_BYTES = 256 * 1024
CHECK_ARCHIVE_FILENAME = "check_archive.jsonl"
EVENT_ARCHIVE_FILENAME = "event_archive.jsonl"
WINDOWS_DETACHED_PROCESS = 0x00000008
WINDOWS_CREATE_NEW_PROCESS_GROUP = 0x00000200
WINDOWS_CREATE_NO_WINDOW = 0x08000000

DRIVER_ERROR_MARKERS = (
    "connection closed while reading from the driver",
    "target page, context or browser has been closed",
    "target closed",
    "browser has been closed",
    "context has been closed",
    "page has been closed",
)


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


def parse_iso_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def compact_text(value, limit=500):
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        return default if default is not None else {}


def atomic_write_text(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(str(tmp), str(target))


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


def read_pid(path):
    try:
        return int(Path(path).read_text(encoding="utf-8").strip() or "0")
    except Exception:
        return 0


def write_pid(path, pid):
    atomic_write_text(path, str(int(pid)))


def clear_pid(path):
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


def detect_wrapper_python():
    candidates = [
        Path(__file__).resolve().parents[1] / "service_start.cmd",
        Path(__file__).resolve().parents[1] / "watchdog_start.cmd",
    ]
    for candidate in candidates:
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in text.splitlines():
            if "PYTHON_EXE=" not in line:
                continue
            value = line.split("PYTHON_EXE=", 1)[1].strip().strip('"')
            if value and Path(value).exists():
                return value
    return ""


def preferred_background_python():
    wrapper_python = detect_wrapper_python()
    current = Path(wrapper_python or sys.executable)
    if os.name == "nt":
        pythonw = current.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(current)


def service_python():
    return detect_wrapper_python() or sys.executable


def slot_key(root):
    name = Path(root).name
    if name.endswith("-2"):
        return "slot3"
    if name.endswith("-3"):
        return "slot4"
    if name.endswith("-4"):
        return "slot5"
    if name.endswith("-5"):
        return "slot6"
    return "slot2"


def read_slot_pid(root):
    root = Path(root)
    state = read_json(root / "state.json", {})
    for candidate in (
        read_pid(root / "service.pid"),
        int(state.get("service_pid", 0) or 0) if str(state.get("service_pid", "")).strip() else 0,
        read_pid(root / "service.lock"),
    ):
        if candidate:
            return int(candidate)
    return 0


def enabled_targets(config):
    targets = []
    if bool(config.get("x_home_enabled", False)):
        targets.append("home")
    if bool(config.get("x_list_enabled", True)):
        lists = config.get("x_lists")
        if isinstance(lists, list):
            for item in lists:
                if isinstance(item, dict) and bool(item.get("enabled", False)) and str(item.get("url", "")).strip():
                    targets.append(str(item.get("id", "") or item.get("name", "") or "list"))
        elif str(config.get("x_list_url", "")).strip():
            targets.append("list")
    return targets


def slot_should_run(root):
    config = read_json(Path(root) / "config.json", {})
    return bool(enabled_targets(config))


def file_mtime_dt(path):
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime, timezone.utc)
    except Exception:
        return None


def file_size(path):
    try:
        return Path(path).stat().st_size
    except Exception:
        return 0


def read_tail_lines(path, max_bytes=DEFAULT_TAIL_BYTES):
    target = Path(path)
    try:
        size = target.stat().st_size
        with target.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
                handle.readline()
            data = handle.read()
    except Exception:
        return []
    text = data.decode("utf-8", errors="replace")
    return [line for line in text.splitlines() if line.strip()]


def recent_checks(root, limit=200):
    rows = []
    for line in read_tail_lines(Path(root) / CHECK_ARCHIVE_FILENAME):
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows[-limit:]


def latest_check_time(rows, predicate=None):
    for row in reversed(rows):
        if predicate and not predicate(row):
            continue
        observed = parse_iso_datetime(row.get("archived_at") or row.get("at"))
        if observed:
            return observed
    return None


def check_has_driver_error(rows):
    for row in reversed(rows[-50:]):
        text = compact_text(row.get("error", ""), limit=1000).lower()
        if any(marker in text for marker in DRIVER_ERROR_MARKERS):
            return text
    return ""


def seconds_since(value, current_time):
    if not value:
        return None
    return max(0.0, (current_time - value).total_seconds())


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def safe_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return bool(default)


def check_observed_time(row):
    return parse_iso_datetime((row or {}).get("archived_at") or (row or {}).get("at"))


def check_target_key(row):
    return compact_text((row or {}).get("target_key", "") or (row or {}).get("mode", ""), limit=80)


def visible_signature(row):
    values = (row or {}).get("visible_tweet_ids", [])
    if not isinstance(values, list):
        return ()
    return tuple(str(item or "").strip() for item in values if str(item or "").strip())


def semantic_rows(rows, current_time, config, service_start_at=None):
    window_seconds = max(60, safe_int(config.get("semantic_window_seconds", DEFAULT_SEMANTIC_WINDOW_SECONDS), DEFAULT_SEMANTIC_WINDOW_SECONDS))
    cutoff = current_time.timestamp() - window_seconds
    service_start = parse_iso_datetime(service_start_at) if service_start_at else None
    selected = []
    for row in list(rows or []):
        observed = check_observed_time(row)
        if observed is None:
            continue
        if observed.timestamp() < cutoff:
            continue
        if service_start is not None and observed < service_start:
            continue
        selected.append(row)
    return selected


def build_semantic_health(rows, current_time, config, service_start_at=None):
    selected = semantic_rows(rows, current_time, config, service_start_at=service_start_at)
    semantic_restart_enabled = safe_bool(
        config.get("semantic_restart_enabled", DEFAULT_SEMANTIC_RESTART_ENABLED),
        DEFAULT_SEMANTIC_RESTART_ENABLED,
    )
    late_by_target = {}
    ready_by_target = {}
    for row in selected:
        target = check_target_key(row)
        if not target:
            continue
        if row.get("late_new_item_recovery") or safe_int(row.get("late_new_item_recovery_candidates", 0), 0) > 0:
            entry = late_by_target.setdefault(target, {"count": 0, "max_delay_seconds": 0})
            entry["count"] += 1
            entry["max_delay_seconds"] = max(
                entry["max_delay_seconds"],
                safe_int(row.get("late_new_item_recovery_max_delay_seconds", row.get("top_delay_seconds", 0)), 0),
            )
        if str(row.get("page_surface_state", "")).strip() == "ready":
            ready_by_target.setdefault(target, []).append(row)

    restart_count = max(
        1,
        safe_int(
            config.get("semantic_late_recovery_restart_count", DEFAULT_SEMANTIC_LATE_RECOVERY_RESTART_COUNT),
            DEFAULT_SEMANTIC_LATE_RECOVERY_RESTART_COUNT,
        ),
    )
    max_delay_threshold = max(
        60,
        safe_int(
            config.get("semantic_late_recovery_max_delay_seconds", DEFAULT_SEMANTIC_LATE_RECOVERY_MAX_DELAY_SECONDS),
            DEFAULT_SEMANTIC_LATE_RECOVERY_MAX_DELAY_SECONDS,
        ),
    )
    restart_reason = ""
    if semantic_restart_enabled:
        for target, entry in sorted(late_by_target.items()):
            if entry["count"] >= restart_count or entry["max_delay_seconds"] >= max_delay_threshold:
                restart_reason = (
                    f"semantic_late_recovery:{target}:"
                    f"count={entry['count']}:max_delay={entry['max_delay_seconds']}s"
                )
                break

    hard_empty_count_threshold = max(
        3,
        safe_int(
            config.get("semantic_hard_empty_restart_count", DEFAULT_SEMANTIC_HARD_EMPTY_RESTART_COUNT),
            DEFAULT_SEMANTIC_HARD_EMPTY_RESTART_COUNT,
        ),
    )
    hard_empty_seconds_threshold = max(
        30,
        safe_int(
            config.get("semantic_hard_empty_restart_seconds", DEFAULT_SEMANTIC_HARD_EMPTY_RESTART_SECONDS),
            DEFAULT_SEMANTIC_HARD_EMPTY_RESTART_SECONDS,
        ),
    )
    hard_empty_streak = []
    for row in reversed(selected):
        if str(row.get("page_surface_state", "")).strip() != "hard_empty":
            break
        hard_empty_streak.append(row)
    hard_empty_summary = {}
    if hard_empty_streak:
        first_seen = check_observed_time(hard_empty_streak[-1])
        last_seen = check_observed_time(hard_empty_streak[0])
        duration_seconds = 0
        if first_seen and last_seen:
            duration_seconds = max(0, int((last_seen - first_seen).total_seconds()))
        targets = sorted({check_target_key(row) for row in hard_empty_streak if check_target_key(row)})
        hard_empty_summary = {
            "count": len(hard_empty_streak),
            "duration_seconds": duration_seconds,
            "targets": targets,
        }
        if (
            semantic_restart_enabled
            and not restart_reason
            and len(hard_empty_streak) >= hard_empty_count_threshold
            and duration_seconds >= hard_empty_seconds_threshold
        ):
            restart_reason = (
                "semantic_hard_empty:"
                f"count={len(hard_empty_streak)}:"
                f"duration={duration_seconds}s:"
                f"targets={','.join(targets)}"
            )

    static_top_delay_threshold = max(
        300,
        safe_int(
            config.get("semantic_static_top_delay_seconds", DEFAULT_SEMANTIC_STATIC_TOP_DELAY_SECONDS),
            DEFAULT_SEMANTIC_STATIC_TOP_DELAY_SECONDS,
        ),
    )
    static_check_count = max(
        2,
        safe_int(
            config.get("semantic_static_check_count", DEFAULT_SEMANTIC_STATIC_CHECK_COUNT),
            DEFAULT_SEMANTIC_STATIC_CHECK_COUNT,
        ),
    )
    static_targets = []
    for target, target_rows in sorted(ready_by_target.items()):
        latest_rows = target_rows[-static_check_count:]
        if len(latest_rows) < static_check_count:
            continue
        signatures = [visible_signature(row) for row in latest_rows]
        if not signatures[-1] or any(signature != signatures[-1] for signature in signatures):
            continue
        top_delay = safe_int(latest_rows[-1].get("top_delay_seconds", 0), 0)
        if top_delay >= static_top_delay_threshold:
            static_targets.append(
                {
                    "target_key": target,
                    "unchanged_ready_count": len(latest_rows),
                    "top_delay_seconds": top_delay,
                    "visible_count": len(signatures[-1]),
                }
            )

    return {
        "restart_reason": restart_reason,
        "late_recovery_targets": late_by_target,
        "hard_empty": hard_empty_summary,
        "static_stale_targets": static_targets,
        "semantic_restart_enabled": semantic_restart_enabled,
        "semantic_window_seconds": max(60, safe_int(config.get("semantic_window_seconds", DEFAULT_SEMANTIC_WINDOW_SECONDS), DEFAULT_SEMANTIC_WINDOW_SECONDS)),
    }


def run_service_command(root, command, timeout=45):
    script = Path(__file__).resolve().with_name("x_monitorplus_service.py")
    args = [service_python(), str(script), "--root", str(Path(root)), command]
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        creationflags=WINDOWS_CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    stdout = result.stdout or ""
    payload = {}
    try:
        payload = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else {}
    except Exception:
        payload = {}
    return {
        "returncode": result.returncode,
        "stdout": compact_text(stdout, limit=1000),
        "stderr": compact_text(result.stderr or "", limit=1000),
        "payload": payload,
    }


def restart_slot(root, reason):
    stop_result = run_service_command(root, "stop", timeout=45)
    time.sleep(2)
    start_result = run_service_command(root, "start", timeout=60)
    payload = start_result.get("payload") or {}
    return {
        "root": str(root),
        "reason": reason,
        "ok": bool(payload.get("running") or payload.get("ok")),
        "pid": int(payload.get("pid", 0) or 0),
        "stop": stop_result,
        "start": start_result,
    }


class WatchdogStore:
    def __init__(self, root=None):
        self.root = Path(root or DEFAULT_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)
        self.pid_path = self.root / "watchdog.pid"
        self.state_path = self.root / "watchdog_state.json"
        self.log_path = self.root / "watchdog.log"

    def load_state(self):
        payload = {
            "started_at": "",
            "heartbeat_at": "",
            "watchdog_pid": 0,
            "slots": {},
            "recent_actions": [],
        }
        payload.update(read_json(self.state_path, {}))
        if not isinstance(payload.get("slots"), dict):
            payload["slots"] = {}
        if not isinstance(payload.get("recent_actions"), list):
            payload["recent_actions"] = []
        return payload

    def save_state(self, payload):
        atomic_write_text(self.state_path, json.dumps(payload, ensure_ascii=False, indent=2))

    def update_state(self, updater):
        state = self.load_state()
        updater(state)
        self.save_state(state)
        return state

    def log(self, message):
        line = f"[{iso_now()}] {message}\n"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)


def build_slot_health(root, current_time, config=None):
    root = Path(root)
    config_value = dict(config or {})
    state = read_json(root / "state.json", {})
    pid = read_slot_pid(root)
    running = bool(pid and is_process_running(pid))
    heartbeat_at = parse_iso_datetime(state.get("service_heartbeat_at", ""))
    check_mtime = file_mtime_dt(root / CHECK_ARCHIVE_FILENAME)
    event_mtime = file_mtime_dt(root / EVENT_ARCHIVE_FILENAME)
    checks = recent_checks(root)
    service_start_at = state.get("last_service_start_at", "")
    latest_check = latest_check_time(checks)
    latest_ready = latest_check_time(checks, lambda row: str(row.get("page_surface_state", "")).strip() == "ready")
    driver_error = check_has_driver_error(checks) or compact_text(state.get("last_error", ""), limit=1000).lower()
    if not any(marker in driver_error for marker in DRIVER_ERROR_MARKERS):
        driver_error = ""
    semantic = build_semantic_health(checks, current_time, config_value, service_start_at=service_start_at)
    return {
        "root": str(root),
        "slot": slot_key(root),
        "should_run": slot_should_run(root),
        "pid": pid,
        "running": running,
        "heartbeat_at": heartbeat_at.isoformat() if heartbeat_at else "",
        "heartbeat_age_seconds": seconds_since(heartbeat_at, current_time),
        "check_archive_mtime": check_mtime.isoformat() if check_mtime else "",
        "check_archive_age_seconds": seconds_since(check_mtime, current_time),
        "check_archive_size": file_size(root / CHECK_ARCHIVE_FILENAME),
        "event_archive_mtime": event_mtime.isoformat() if event_mtime else "",
        "event_archive_size": file_size(root / EVENT_ARCHIVE_FILENAME),
        "latest_check_at": latest_check.isoformat() if latest_check else "",
        "latest_check_age_seconds": seconds_since(latest_check, current_time),
        "latest_ready_at": latest_ready.isoformat() if latest_ready else "",
        "latest_ready_age_seconds": seconds_since(latest_ready, current_time),
        "driver_error": driver_error,
        "semantic_restart_reason": semantic.get("restart_reason", ""),
        "semantic_late_recovery_targets": semantic.get("late_recovery_targets", {}),
        "semantic_hard_empty": semantic.get("hard_empty", {}),
        "semantic_static_stale_targets": semantic.get("static_stale_targets", []),
        "semantic_restart_enabled": semantic.get("semantic_restart_enabled", DEFAULT_SEMANTIC_RESTART_ENABLED),
        "semantic_window_seconds": semantic.get("semantic_window_seconds", DEFAULT_SEMANTIC_WINDOW_SECONDS),
    }


def stale_reason(health, config, previous_slot_state, current_time):
    if not health.get("should_run"):
        return ""
    if not health.get("running"):
        return "process_not_running"
    heartbeat_age = health.get("heartbeat_age_seconds")
    check_age = health.get("check_archive_age_seconds")
    ready_age = health.get("latest_ready_age_seconds")
    if heartbeat_age is None:
        if not (
            (check_age is not None and check_age <= int(config["check_archive_stale_seconds"]))
            or (ready_age is not None and ready_age <= int(config["ready_stale_seconds"]))
        ):
            return "heartbeat_stale:-1s"
    elif heartbeat_age > int(config["heartbeat_stale_seconds"]):
        return f"heartbeat_stale:{int(heartbeat_age)}s"
    if check_age is None or check_age > int(config["check_archive_stale_seconds"]):
        return f"check_archive_stale:{int(check_age or -1)}s"
    if (
        safe_bool(config.get("ready_stale_restart_enabled", DEFAULT_READY_STALE_RESTART_ENABLED), DEFAULT_READY_STALE_RESTART_ENABLED)
        and (ready_age is None or ready_age > int(config["ready_stale_seconds"]))
    ):
        return f"ready_check_stale:{int(ready_age or -1)}s"
    if health.get("driver_error"):
        last_error_seen = str(previous_slot_state.get("last_driver_error", ""))
        if health["driver_error"] != last_error_seen:
            return "driver_error:" + compact_text(health["driver_error"], limit=160)
    if health.get("semantic_restart_reason"):
        return compact_text(health["semantic_restart_reason"], limit=180)
    return ""


def cooldown_active(previous_slot_state, current_time, cooldown_seconds):
    previous_at = parse_iso_datetime(previous_slot_state.get("last_restart_at", ""))
    if previous_at is None:
        return False
    return (current_time - previous_at).total_seconds() < max(0, int(cooldown_seconds))


def default_config(args):
    return {
        "slot_roots": [str(Path(item)) for item in (args.slot_root or DEFAULT_SLOT_ROOTS)],
        "poll_seconds": max(10, int(args.poll_seconds)),
        "heartbeat_stale_seconds": max(30, int(args.heartbeat_stale_seconds)),
        "check_archive_stale_seconds": max(30, int(args.check_archive_stale_seconds)),
        "ready_stale_seconds": max(60, int(args.ready_stale_seconds)),
        "restart_cooldown_seconds": max(30, int(args.restart_cooldown_seconds)),
        "semantic_window_seconds": max(60, int(args.semantic_window_seconds)),
        "ready_stale_restart_enabled": bool(args.ready_stale_restart_enabled),
        "semantic_restart_enabled": bool(args.semantic_restart_enabled),
        "semantic_late_recovery_restart_count": max(1, int(args.semantic_late_recovery_restart_count)),
        "semantic_late_recovery_max_delay_seconds": max(60, int(args.semantic_late_recovery_max_delay_seconds)),
        "semantic_static_top_delay_seconds": max(300, int(args.semantic_static_top_delay_seconds)),
        "semantic_static_check_count": max(2, int(args.semantic_static_check_count)),
        "semantic_hard_empty_restart_count": max(3, int(args.semantic_hard_empty_restart_count)),
        "semantic_hard_empty_restart_seconds": max(30, int(args.semantic_hard_empty_restart_seconds)),
    }


def check_once(store, config):
    current_time = now_utc()
    actions = []

    def updater(state):
        state["heartbeat_at"] = current_time.isoformat()
        state["watchdog_pid"] = os.getpid()
        state.setdefault("slots", {})
        state.setdefault("recent_actions", [])

    state = store.update_state(updater)
    for root_text in config["slot_roots"]:
        root = Path(root_text)
        key = slot_key(root)
        previous_slot_state = dict(state.get("slots", {}).get(key, {}))
        health = build_slot_health(root, current_time, config=config)
        reason = stale_reason(health, config, previous_slot_state, current_time)
        action = {"slot": key, "root": str(root), "checked_at": current_time.isoformat(), "health": health, "reason": reason}
        if reason and cooldown_active(previous_slot_state, current_time, config["restart_cooldown_seconds"]):
            action["result"] = "restart_cooldown"
            action["ok"] = False
            store.log(f"{key} unhealthy but restart cooldown is active: {reason}")
        elif reason:
            store.log(f"{key} unhealthy, restarting: {reason}")
            restart_result = restart_slot(root, reason)
            action["result"] = "restarted" if restart_result.get("ok") else "restart_failed"
            action["ok"] = bool(restart_result.get("ok"))
            action["restart"] = restart_result
            previous_slot_state["last_restart_at"] = current_time.isoformat()
            previous_slot_state["last_restart_reason"] = reason
            previous_slot_state["last_restart_ok"] = bool(restart_result.get("ok"))
            previous_slot_state["last_restart_pid"] = int(restart_result.get("pid", 0) or 0)
            store.log(f"{key} restart result: {action['result']} pid={previous_slot_state['last_restart_pid']}")
        else:
            action["result"] = "healthy" if health.get("should_run") else "disabled"
            action["ok"] = True
        previous_slot_state["last_check_at"] = current_time.isoformat()
        previous_slot_state["last_health"] = health
        if health.get("driver_error"):
            previous_slot_state["last_driver_error"] = health.get("driver_error")
        actions.append(action)

        def slot_updater(next_state, slot_key_value=key, slot_state_value=previous_slot_state, action_value=action):
            next_state.setdefault("slots", {})[slot_key_value] = slot_state_value
            recent = list(next_state.get("recent_actions", []))
            if action_value.get("result") != "healthy":
                recent.append(action_value)
            next_state["recent_actions"] = recent[-80:]

        state = store.update_state(slot_updater)
    return {"ok": True, "checked_at": current_time.isoformat(), "actions": actions}


def serve(store, config):
    current_pid = os.getpid()
    write_pid(store.pid_path, current_pid)
    started_at = iso_now()
    store.update_state(
        lambda state: (
            state.__setitem__("started_at", started_at),
            state.__setitem__("watchdog_pid", current_pid),
            state.__setitem__("config", config),
        )
    )
    store.log(f"watchdog started pid={current_pid}")
    while True:
        try:
            check_once(store, config)
        except Exception as exc:
            store.log(f"watchdog loop error: {type(exc).__name__}: {exc}")
            traceback.print_exc(file=sys.stderr)
        time.sleep(max(10, int(config["poll_seconds"])))


def start_watchdog(store, config):
    pid = read_pid(store.pid_path)
    if pid and is_process_running(pid):
        return {"ok": True, "action": "start", "running": True, "already_running": True, "pid": pid}
    clear_pid(store.pid_path)
    log_handle = open(store.log_path, "a", encoding="utf-8")
    process = subprocess.Popen(
        [preferred_background_python(), str(Path(__file__).resolve()), "--root", str(store.root)]
        + build_config_cli_args(config)
        + ["serve"],
        stdout=log_handle,
        stderr=log_handle,
        stdin=subprocess.DEVNULL,
        cwd=str(Path(__file__).resolve().parent),
        creationflags=(
            WINDOWS_CREATE_NO_WINDOW | WINDOWS_DETACHED_PROCESS | WINDOWS_CREATE_NEW_PROCESS_GROUP
            if os.name == "nt"
            else 0
        ),
        close_fds=True,
    )
    write_pid(store.pid_path, process.pid)
    time.sleep(1)
    running = is_process_running(process.pid)
    return {"ok": running, "action": "start", "running": running, "pid": process.pid, "root": str(store.root)}


def stop_watchdog(store):
    pid = read_pid(store.pid_path)
    if not pid or not is_process_running(pid):
        clear_pid(store.pid_path)
        return {"ok": True, "action": "stop", "running": False, "stopped": False}
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
            creationflags=WINDOWS_CREATE_NO_WINDOW,
        )
    else:
        os.kill(pid, 15)
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    time.sleep(1)
    stopped = not is_process_running(pid)
    if stopped:
        clear_pid(store.pid_path)
    return {
        "ok": stopped,
        "action": "stop",
        "running": not stopped,
        "pid": pid,
        "stdout": compact_text(getattr(result, "stdout", ""), limit=500),
        "stderr": compact_text(getattr(result, "stderr", ""), limit=500),
    }


def status(store):
    state = store.load_state()
    pid = read_pid(store.pid_path)
    running = bool(pid and is_process_running(pid))
    return {
        "ok": True,
        "action": "status",
        "running": running,
        "pid": pid if running else 0,
        "root": str(store.root),
        "state": state,
        "log_path": str(store.log_path),
    }


def build_config_cli_args(config):
    args = [
        "--poll-seconds",
        str(config["poll_seconds"]),
        "--heartbeat-stale-seconds",
        str(config["heartbeat_stale_seconds"]),
        "--check-archive-stale-seconds",
        str(config["check_archive_stale_seconds"]),
        "--ready-stale-seconds",
        str(config["ready_stale_seconds"]),
        "--restart-cooldown-seconds",
        str(config["restart_cooldown_seconds"]),
        "--semantic-window-seconds",
        str(config["semantic_window_seconds"]),
        "--ready-stale-restart-enabled" if config.get("ready_stale_restart_enabled") else "--no-ready-stale-restart-enabled",
        "--semantic-restart-enabled" if config.get("semantic_restart_enabled") else "--no-semantic-restart-enabled",
        "--semantic-late-recovery-restart-count",
        str(config["semantic_late_recovery_restart_count"]),
        "--semantic-late-recovery-max-delay-seconds",
        str(config["semantic_late_recovery_max_delay_seconds"]),
        "--semantic-static-top-delay-seconds",
        str(config["semantic_static_top_delay_seconds"]),
        "--semantic-static-check-count",
        str(config["semantic_static_check_count"]),
        "--semantic-hard-empty-restart-count",
        str(config["semantic_hard_empty_restart_count"]),
        "--semantic-hard-empty-restart-seconds",
        str(config["semantic_hard_empty_restart_seconds"]),
    ]
    for root in config["slot_roots"]:
        args.extend(["--slot-root", str(root)])
    return args


def build_parser():
    parser = argparse.ArgumentParser(description=SERVICE_NAME)
    parser.add_argument("--root", default="")
    parser.add_argument("--slot-root", action="append", default=[])
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--heartbeat-stale-seconds", type=int, default=DEFAULT_HEARTBEAT_STALE_SECONDS)
    parser.add_argument("--check-archive-stale-seconds", type=int, default=DEFAULT_CHECK_ARCHIVE_STALE_SECONDS)
    parser.add_argument("--ready-stale-seconds", type=int, default=DEFAULT_READY_STALE_SECONDS)
    parser.add_argument("--restart-cooldown-seconds", type=int, default=DEFAULT_RESTART_COOLDOWN_SECONDS)
    parser.add_argument("--semantic-window-seconds", type=int, default=DEFAULT_SEMANTIC_WINDOW_SECONDS)
    parser.add_argument("--ready-stale-restart-enabled", action=argparse.BooleanOptionalAction, default=DEFAULT_READY_STALE_RESTART_ENABLED)
    parser.add_argument("--semantic-restart-enabled", action=argparse.BooleanOptionalAction, default=DEFAULT_SEMANTIC_RESTART_ENABLED)
    parser.add_argument("--semantic-late-recovery-restart-count", type=int, default=DEFAULT_SEMANTIC_LATE_RECOVERY_RESTART_COUNT)
    parser.add_argument("--semantic-late-recovery-max-delay-seconds", type=int, default=DEFAULT_SEMANTIC_LATE_RECOVERY_MAX_DELAY_SECONDS)
    parser.add_argument("--semantic-static-top-delay-seconds", type=int, default=DEFAULT_SEMANTIC_STATIC_TOP_DELAY_SECONDS)
    parser.add_argument("--semantic-static-check-count", type=int, default=DEFAULT_SEMANTIC_STATIC_CHECK_COUNT)
    parser.add_argument("--semantic-hard-empty-restart-count", type=int, default=DEFAULT_SEMANTIC_HARD_EMPTY_RESTART_COUNT)
    parser.add_argument("--semantic-hard-empty-restart-seconds", type=int, default=DEFAULT_SEMANTIC_HARD_EMPTY_RESTART_SECONDS)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("status")
    sub.add_parser("check-once")
    return parser


def main():
    configure_stdio()
    args = build_parser().parse_args()
    store = WatchdogStore(root=args.root or None)
    config = default_config(args)
    try:
        if args.command == "serve":
            serve(store, config)
            return 0
        if args.command == "start":
            payload = start_watchdog(store, config)
        elif args.command == "stop":
            payload = stop_watchdog(store)
        elif args.command == "status":
            payload = status(store)
        else:
            payload = check_once(store, config)
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload.get("ok", True) else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
