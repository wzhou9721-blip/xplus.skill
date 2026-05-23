import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


SERVICE_NAME = "x-monitor-plus-stability"
DEFAULT_STORAGE_BASE = Path.home() / "AppData" / "Local" / "XMonitorPlus"
if os.environ.get("X_MONITORPLUS_STORAGE_BASE", "").strip():
    DEFAULT_STORAGE_BASE = Path(os.environ["X_MONITORPLUS_STORAGE_BASE"])
elif "LOCALAPPDATA" in os.environ:
    DEFAULT_STORAGE_BASE = Path(os.environ["LOCALAPPDATA"]) / "XMonitorPlus"

DEFAULT_ACTIVE_ROOTS = (
    DEFAULT_STORAGE_BASE / "x-monitor-plus",
    DEFAULT_STORAGE_BASE / "x-monitor-plus-2",
)
DEFAULT_STANDBY_ROOTS = (
    DEFAULT_STORAGE_BASE / "x-monitor-plus-3",
    DEFAULT_STORAGE_BASE / "x-monitor-plus-4",
    DEFAULT_STORAGE_BASE / "x-monitor-plus-5",
)
DEFAULT_WATCHDOG_ROOT = DEFAULT_STORAGE_BASE / "x-monitor-plus-watchdog"
DEFAULT_READY_WAIT_SECONDS = 60
DEFAULT_POLL_SECONDS = 5


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def script_dir():
    return Path(__file__).resolve().parent


def service_script():
    return script_dir() / "x_monitorplus_service.py"


def watchdog_script():
    return script_dir() / "x_monitorplus_watchdog.py"


def run_json_command(args, timeout=60):
    result = subprocess.run(
        [str(item) for item in args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )
    stdout = (result.stdout or "").strip()
    payload = {}
    if stdout:
        last_line = stdout.splitlines()[-1]
        try:
            payload = json.loads(last_line)
        except Exception:
            payload = {"ok": False, "parse_error": "command did not return JSON", "stdout": stdout[-1000:]}
    if not payload:
        payload = {"ok": result.returncode == 0}
    payload.setdefault("returncode", result.returncode)
    if result.stderr:
        payload.setdefault("stderr", result.stderr.strip()[-1000:])
    return payload


def slot_label(root):
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


def enabled_targets_from_status(status):
    targets = []
    for item in status.get("lists", []) if isinstance(status.get("lists", []), list) else []:
        if item.get("enabled"):
            targets.append(
                {
                    "id": item.get("id", ""),
                    "index": item.get("index"),
                    "name": item.get("name", ""),
                    "url": item.get("url", ""),
                    "configured": bool(item.get("configured")),
                    "auth_ready": bool(item.get("auth_ready")),
                    "auth_error": item.get("auth_error", ""),
                    "last_successful_check_at": item.get("last_successful_check_at", ""),
                    "last_error": item.get("last_error", ""),
                }
            )
    modes = status.get("modes", {}) if isinstance(status.get("modes", {}), dict) else {}
    home = modes.get("home", {}) if isinstance(modes.get("home", {}), dict) else {}
    if home.get("enabled"):
        targets.append(
            {
                "id": "home",
                "index": 0,
                "name": home.get("label", "home"),
                "url": home.get("url", ""),
                "configured": bool(home.get("url")),
                "auth_ready": bool(home.get("auth_ready")),
                "auth_error": home.get("auth_error", ""),
                "last_successful_check_at": home.get("last_successful_check_at", ""),
                "last_error": home.get("last_error", ""),
            }
        )
    return targets


def profile_lock_markers(profile_dir):
    root = Path(profile_dir or "")
    if not profile_dir or not root.exists():
        return []
    names = ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile")
    return [str(root / name) for name in names if (root / name).exists()]


def summarize_slot(root, python_exe):
    status = run_json_command([python_exe, service_script(), "--root", root, "status"], timeout=60)
    binding = status.get("slot_binding", {}) if isinstance(status.get("slot_binding", {}), dict) else {}
    profile_dir = status.get("profile_dir") or binding.get("profile_dir", "")
    targets = enabled_targets_from_status(status)
    issues = []
    warnings = []

    if not status.get("ok", False):
        issues.append("status_command_failed")
    if status.get("config_parse_error"):
        issues.append("config_parse_error")
    if status.get("state_parse_error"):
        warnings.append("state_parse_error")
    if status.get("config_missing"):
        issues.append("config_missing:" + ",".join(str(item) for item in status.get("config_missing", [])))
    if not status.get("config_valid", True):
        issues.append("config_invalid")
    if not targets:
        issues.append("no_enabled_targets")
    for target in targets:
        if not target.get("url"):
            issues.append(f"target_missing_url:{target.get('id')}")
        if not target.get("configured", True):
            issues.append(f"target_not_configured:{target.get('id')}")
        if not target.get("auth_ready", False):
            issues.append(f"target_auth_not_ready:{target.get('id')}")
    if not status.get("auth_status", {}).get("ready", False):
        issues.append("auth_not_ready")
    if not binding.get("config_exists", True):
        issues.append("slot_binding_config_missing")
    if not binding.get("cookies_exists", True):
        issues.append("slot_binding_cookies_missing")
    if not binding.get("profile_exists", True):
        issues.append("slot_binding_profile_missing")
    markers = profile_lock_markers(profile_dir)
    if markers:
        warnings.append("profile_lock_marker_present")
    if status.get("slot_operator_action", {}).get("required"):
        issues.append("slot_operator_action_required:" + str(status.get("slot_operator_action", {}).get("kind", "")))

    return {
        "label": slot_label(root),
        "root": str(Path(root)),
        "running": bool(status.get("running")),
        "pid": int(status.get("pid", 0) or 0),
        "source_slot": status.get("source_slot", ""),
        "source_slot_label": status.get("source_slot_label", ""),
        "enabled_targets": targets,
        "enabled_target_count": len(targets),
        "profile_dir": profile_dir,
        "profile_lock_markers": markers,
        "last_service_start_at": status.get("last_service_start_at", ""),
        "last_service_stop_at": status.get("last_service_stop_at", ""),
        "service_heartbeat_at": status.get("service_heartbeat_at", ""),
        "last_successful_check_at": status.get("last_successful_check_at", ""),
        "last_error": status.get("last_error", ""),
        "issues": issues,
        "warnings": warnings,
    }


def summarize_watchdog(watchdog_root, slot_roots, python_exe):
    status = run_json_command(
        [python_exe, watchdog_script(), "--root", watchdog_root]
        + [arg for root in slot_roots for arg in ("--slot-root", str(root))]
        + ["status"],
        timeout=60,
    )
    state = status.get("state", {}) if isinstance(status.get("state", {}), dict) else {}
    config = state.get("config", {}) if isinstance(state.get("config", {}), dict) else {}
    issues = []
    warnings = []
    if not status.get("ok", False):
        issues.append("watchdog_status_command_failed")
    if config.get("semantic_restart_enabled"):
        issues.append("semantic_restart_enabled")
    if config.get("ready_stale_restart_enabled"):
        issues.append("ready_stale_restart_enabled")
    if status.get("running") and not state.get("slots"):
        warnings.append("watchdog_running_without_slot_state")
    return {
        "root": str(Path(watchdog_root)),
        "running": bool(status.get("running")),
        "pid": int(status.get("pid", 0) or 0),
        "heartbeat_at": state.get("heartbeat_at", ""),
        "semantic_restart_enabled": bool(config.get("semantic_restart_enabled", False)),
        "ready_stale_restart_enabled": bool(config.get("ready_stale_restart_enabled", False)),
        "restart_cooldown_seconds": config.get("restart_cooldown_seconds"),
        "slot_roots": config.get("slot_roots", []),
        "issues": issues,
        "warnings": warnings,
    }


def build_snapshot(slot_roots, watchdog_root, python_exe):
    slots = [summarize_slot(str(root), python_exe) for root in slot_roots]
    watchdog = summarize_watchdog(str(watchdog_root), slot_roots, python_exe)
    issues = []
    warnings = []
    for slot in slots:
        for issue in slot["issues"]:
            issues.append(f"{slot['label']}:{issue}")
        for warning in slot["warnings"]:
            warnings.append(f"{slot['label']}:{warning}")
    for issue in watchdog["issues"]:
        issues.append(f"watchdog:{issue}")
    for warning in watchdog["warnings"]:
        warnings.append(f"watchdog:{warning}")

    stopped_enabled = [slot["label"] for slot in slots if slot["enabled_target_count"] and not slot["running"]]
    if watchdog["running"] and stopped_enabled:
        issues.append("watchdog_running_will_restart_stopped_enabled_slots:" + ",".join(stopped_enabled))
    if not watchdog["running"] and all(not slot["running"] for slot in slots):
        warnings.append("all_slots_and_watchdog_stopped")

    return {
        "ok": not issues,
        "service": SERVICE_NAME,
        "generated_at": now_iso(),
        "slot_count": len(slots),
        "running_slot_count": sum(1 for slot in slots if slot["running"]),
        "enabled_target_count": sum(slot["enabled_target_count"] for slot in slots),
        "issues": issues,
        "warnings": warnings,
        "slots": slots,
        "watchdog": watchdog,
    }


def preflight(slot_roots, watchdog_root, python_exe):
    snapshot = build_snapshot(slot_roots, watchdog_root, python_exe)
    snapshot["action"] = "preflight"
    snapshot["ready_to_start"] = not any(
        issue
        for issue in snapshot["issues"]
        if not issue.startswith("watchdog_running_will_restart_stopped_enabled_slots")
    )
    return snapshot


def status(slot_roots, watchdog_root, python_exe):
    snapshot = build_snapshot(slot_roots, watchdog_root, python_exe)
    snapshot["action"] = "status"
    return snapshot


def safe_stop(slot_roots, watchdog_root, python_exe):
    actions = []
    actions.append(
        {
            "step": "stop_watchdog",
            "result": run_json_command([python_exe, watchdog_script(), "--root", watchdog_root, "stop"], timeout=60),
        }
    )
    for root in slot_roots:
        actions.append(
            {
                "step": "stop_slot",
                "slot": slot_label(root),
                "root": str(root),
                "result": run_json_command([python_exe, service_script(), "--root", root, "stop"], timeout=60),
            }
        )
    final_status = status(slot_roots, watchdog_root, python_exe)
    return {
        "ok": not final_status["watchdog"]["running"] and all(not slot["running"] for slot in final_status["slots"]),
        "service": SERVICE_NAME,
        "action": "safe-stop",
        "generated_at": now_iso(),
        "actions": actions,
        "final_status": final_status,
    }


def wait_for_slots_running(slot_roots, watchdog_root, python_exe, wait_seconds, poll_seconds):
    deadline = time.time() + max(0, wait_seconds)
    latest = status(slot_roots, watchdog_root, python_exe)
    while time.time() < deadline:
        if all(slot["running"] for slot in latest["slots"] if slot["enabled_target_count"]):
            return latest
        time.sleep(max(1, poll_seconds))
        latest = status(slot_roots, watchdog_root, python_exe)
    return latest


def safe_start(slot_roots, watchdog_root, python_exe, wait_seconds, poll_seconds, start_watchdog=True):
    before = preflight(slot_roots, watchdog_root, python_exe)
    blocking = [
        issue
        for issue in before["issues"]
        if not issue.startswith("watchdog_running_will_restart_stopped_enabled_slots")
    ]
    actions = []
    if blocking:
        return {
            "ok": False,
            "service": SERVICE_NAME,
            "action": "safe-start",
            "generated_at": now_iso(),
            "blocked": True,
            "blocking_issues": blocking,
            "preflight": before,
            "actions": actions,
        }
    if before["watchdog"]["running"]:
        actions.append(
            {
                "step": "stop_watchdog_before_start",
                "result": run_json_command([python_exe, watchdog_script(), "--root", watchdog_root, "stop"], timeout=60),
            }
        )
    for root in slot_roots:
        actions.append(
            {
                "step": "start_slot",
                "slot": slot_label(root),
                "root": str(root),
                "result": run_json_command([python_exe, service_script(), "--root", root, "start"], timeout=60),
            }
        )
    after_slots = wait_for_slots_running(slot_roots, watchdog_root, python_exe, wait_seconds, poll_seconds)
    if start_watchdog and all(slot["running"] for slot in after_slots["slots"] if slot["enabled_target_count"]):
        actions.append(
            {
                "step": "start_watchdog_after_slots",
                "result": run_json_command(
                    [python_exe, watchdog_script(), "--root", watchdog_root]
                    + [arg for root in slot_roots for arg in ("--slot-root", str(root))]
                    + ["start"],
                    timeout=60,
                ),
            }
        )
    final_status = status(slot_roots, watchdog_root, python_exe)
    return {
        "ok": start_watchdog == final_status["watchdog"]["running"] and all(
            slot["running"] for slot in final_status["slots"] if slot["enabled_target_count"]
        ),
        "service": SERVICE_NAME,
        "action": "safe-start",
        "generated_at": now_iso(),
        "preflight": before,
        "actions": actions,
        "final_status": final_status,
    }


def build_parser():
    parser = argparse.ArgumentParser(description=SERVICE_NAME)
    parser.add_argument("--slot-root", action="append", default=[])
    parser.add_argument("--include-standby", action="store_true")
    parser.add_argument("--watchdog-root", default=str(DEFAULT_WATCHDOG_ROOT))
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--wait-seconds", type=int, default=DEFAULT_READY_WAIT_SECONDS)
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--no-watchdog", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("preflight")
    sub.add_parser("safe-stop")
    sub.add_parser("safe-start")
    return parser


def selected_slot_roots(args):
    roots = [Path(item) for item in args.slot_root] if args.slot_root else list(DEFAULT_ACTIVE_ROOTS)
    if args.include_standby:
        roots.extend(DEFAULT_STANDBY_ROOTS)
    return roots


def main():
    args = build_parser().parse_args()
    slot_roots = selected_slot_roots(args)
    if args.command == "status":
        payload = status(slot_roots, Path(args.watchdog_root), args.python_exe)
    elif args.command == "preflight":
        payload = preflight(slot_roots, Path(args.watchdog_root), args.python_exe)
    elif args.command == "safe-stop":
        payload = safe_stop(slot_roots, Path(args.watchdog_root), args.python_exe)
    else:
        payload = safe_start(
            slot_roots,
            Path(args.watchdog_root),
            args.python_exe,
            args.wait_seconds,
            args.poll_seconds,
            start_watchdog=not args.no_watchdog,
        )
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
