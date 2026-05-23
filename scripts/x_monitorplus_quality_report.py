import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


SERVICE_NAME = "x-monitor-plus-quality-report"
DEFAULT_STORAGE_BASE = Path(os.environ.get("X_MONITORPLUS_STORAGE_BASE", "")) if os.environ.get("X_MONITORPLUS_STORAGE_BASE", "").strip() else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "XMonitorPlus"
DEFAULT_SLOT_ROOTS = (
    DEFAULT_STORAGE_BASE / "x-monitor-plus",
    DEFAULT_STORAGE_BASE / "x-monitor-plus-2",
)
DEFAULT_WATCHDOG_ROOT = DEFAULT_STORAGE_BASE / "x-monitor-plus-watchdog"
EVENT_ARCHIVE_FILENAME = "event_archive.jsonl"
CHECK_ARCHIVE_FILENAME = "check_archive.jsonl"
SEEN_ARCHIVE_FILENAME = "seen_archive.json"


def now_utc():
    return datetime.now(timezone.utc)


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


def compact_text(value, limit=220):
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        return default if default is not None else {}


def read_jsonl_since(path, since, time_fields):
    rows = []
    target = Path(path)
    if not target.exists():
        return rows
    with target.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            observed = None
            for field in time_fields:
                observed = parse_iso_datetime(row.get(field, ""))
                if observed is not None:
                    break
            if observed is None or observed < since:
                continue
            row["_observed_dt"] = observed
            rows.append(row)
    return rows


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * (float(pct) / 100.0)))
    index = max(0, min(len(ordered) - 1, index))
    return ordered[index]


def latency_summary(values):
    values = [int(value) for value in values if value is not None]
    if not values:
        return {"count": 0, "p50": None, "p90": None, "p95": None, "p99": None, "max": None, "over60": 0, "over300": 0}
    return {
        "count": len(values),
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
        "over60": sum(1 for value in values if value >= 60),
        "over300": sum(1 for value in values if value >= 300),
    }


def is_text_repost(value):
    text = " ".join(str(value or "").strip().lower().split())
    return text.startswith("rt @") or text.startswith("\u8f6c\u53d1 @") or text.startswith("\u8f6c\u53d1@")


def is_repost_delivery(row):
    if bool(row.get("is_repost")) or bool(row.get("is_filtered_repost")):
        return True
    if str(row.get("repost_context", "") or "").strip():
        return True
    return is_text_repost(row.get("original_text") or row.get("source_full_text") or row.get("text", ""))


def slot_label(root, index):
    name = Path(root).name
    if name.endswith("-2"):
        return "slot3"
    if name.endswith("-3"):
        return "slot4"
    if name.endswith("-4"):
        return "slot5"
    if name.endswith("-5"):
        return "slot6"
    return f"slot{index + 2}"


def summarize_slot(root, label, since, now):
    root = Path(root)
    events = read_jsonl_since(root / EVENT_ARCHIVE_FILENAME, since, ("archived_at", "delivered_at", "at"))
    checks = read_jsonl_since(root / CHECK_ARCHIVE_FILENAME, since, ("archived_at", "at"))
    state = read_json(root / "state.json", {})
    seen_archive = read_json(root / SEEN_ARCHIVE_FILENAME, {})
    deliveries = [row for row in events if row.get("archive_event_type") == "delivery"]
    updates = [row for row in events if row.get("archive_event_type") == "update"]
    suppressed = [row for row in events if row.get("archive_event_type") == "suppressed"]
    original_deliveries = [row for row in deliveries if not is_repost_delivery(row)]
    repost_deliveries = [row for row in deliveries if is_repost_delivery(row)]
    delay_values = [row.get("delay_seconds") for row in deliveries if isinstance(row.get("delay_seconds"), (int, float))]
    original_delay_values = [
        row.get("delay_seconds") for row in original_deliveries if isinstance(row.get("delay_seconds"), (int, float))
    ]
    repost_delay_values = [
        row.get("delay_seconds") for row in repost_deliveries if isinstance(row.get("delay_seconds"), (int, float))
    ]

    def collect_latency_details(rows):
        delay_by_target = defaultdict(list)
        slow_deliveries = []
        slow_cause_counts = Counter()
        for row in rows:
            target = str(row.get("target_key", "") or row.get("mode", "") or "unknown")
            delay = row.get("delay_seconds")
            if isinstance(delay, (int, float)):
                delay_by_target[target].append(delay)
                if delay >= 60:
                    cause = str(row.get("slow_delivery_cause", "") or "unknown")
                    slow_cause_counts[cause] += 1
                    slow_deliveries.append(
                        {
                            "at": row.get("delivered_at") or row.get("at") or row.get("archived_at"),
                            "target_key": target,
                            "delay_seconds": int(delay),
                            "handle": row.get("handle", ""),
                            "tweet_id": row.get("tweet_id", ""),
                            "url": row.get("url", ""),
                            "slow_delivery_cause": cause,
                            "is_repost": is_repost_delivery(row),
                            "repost_context": compact_text(row.get("repost_context", ""), limit=120),
                        }
                    )
        slow_deliveries.sort(key=lambda item: (item.get("delay_seconds", 0), item.get("at", "")), reverse=True)
        target_summaries = {target: latency_summary(values) for target, values in sorted(delay_by_target.items())}
        return target_summaries, slow_deliveries, dict(slow_cause_counts)

    delay_by_target, slow_deliveries, slow_cause_counts = collect_latency_details(deliveries)
    original_delay_by_target, slow_original_deliveries, slow_original_cause_counts = collect_latency_details(original_deliveries)
    repost_delay_by_target, slow_repost_deliveries, slow_repost_cause_counts = collect_latency_details(repost_deliveries)
    original_latency = latency_summary(original_delay_values)
    repost_latency = latency_summary(repost_delay_values)
    repost_reason_counts = Counter()
    for row in repost_deliveries:
        if bool(row.get("is_repost")) or str(row.get("repost_context", "") or "").strip():
            repost_reason_counts["structured_repost"] += 1
        elif bool(row.get("is_filtered_repost")):
            repost_reason_counts["filtered_repost"] += 1
        elif is_text_repost(row.get("original_text") or row.get("source_full_text") or row.get("text", "")):
            repost_reason_counts["text_rt"] += 1
        else:
            repost_reason_counts["unknown_repost"] += 1

    surface_counts = Counter(str(row.get("page_surface_state", "") or "unknown") for row in checks)
    reason_counts = Counter(str(row.get("page_surface_reason", "") or "unknown") for row in checks)
    soft_recovery_counts = Counter()
    for row in checks:
        for field in (
            "soft_recovery_action",
            "empty_page_recovery",
            "partial_page_recovery",
            "late_new_item_recovery",
            "empty_page_wave_recovery",
        ):
            value = str(row.get(field, "") or "").strip()
            if value:
                soft_recovery_counts[value] += 1
    late_recovery_checks = [
        row
        for row in checks
        if row.get("late_new_item_recovery") or int(row.get("late_new_item_recovery_candidates", 0) or 0) > 0
    ]
    restart_gap_replay_count = sum(1 for row in deliveries if bool(row.get("restart_gap_replay")))
    baseline_count = 0
    new_tweet_count = 0
    for row in checks:
        baseline_ids = row.get("baseline_tweet_ids", [])
        new_ids = row.get("new_tweet_ids", [])
        if isinstance(baseline_ids, list):
            baseline_count += len(baseline_ids)
        if isinstance(new_ids, list):
            new_tweet_count += len(new_ids)
    latest_check = max((row["_observed_dt"] for row in checks), default=None)
    heartbeat = parse_iso_datetime(state.get("service_heartbeat_at", ""))
    seen_items = seen_archive.get("items", {}) if isinstance(seen_archive.get("items", {}), dict) else {}
    return {
        "label": label,
        "root": str(root),
        "running_pid": int(state.get("service_pid", 0) or 0),
        "heartbeat_at": heartbeat.isoformat() if heartbeat else "",
        "heartbeat_age_seconds": max(0, int((now - heartbeat).total_seconds())) if heartbeat else None,
        "latest_check_at": latest_check.isoformat() if latest_check else "",
        "latest_check_age_seconds": max(0, int((now - latest_check).total_seconds())) if latest_check else None,
        "last_error": compact_text(state.get("last_error", ""), limit=500),
        "delivery_latency": latency_summary(delay_values),
        "delivery_latency_original": original_latency,
        "delivery_latency_repost": repost_latency,
        "delivery_latency_by_target": delay_by_target,
        "delivery_latency_original_by_target": original_delay_by_target,
        "delivery_latency_repost_by_target": repost_delay_by_target,
        "slow_delivery_cause_counts": slow_cause_counts,
        "slow_original_cause_counts": slow_original_cause_counts,
        "slow_repost_cause_counts": slow_repost_cause_counts,
        "event_counts": {
            "delivery": len(deliveries),
            "delivery_original": original_latency["count"],
            "delivery_repost": repost_latency["count"],
            "update": len(updates),
            "suppressed": len(suppressed),
        },
        "repost_delivery_count": repost_latency["count"],
        "repost_reason_counts": dict(repost_reason_counts),
        "check_count": len(checks),
        "surface_counts": dict(surface_counts),
        "surface_reason_top": dict(reason_counts.most_common(8)),
        "recovery_counts": dict(soft_recovery_counts.most_common(12)),
        "late_recovery_count": len(late_recovery_checks),
        "late_recovery_max_delay_seconds": max(
            [int(row.get("late_new_item_recovery_max_delay_seconds", 0) or 0) for row in late_recovery_checks] or [0]
        ),
        "baseline_tweet_count": baseline_count,
        "new_tweet_count": new_tweet_count,
        "restart_gap_replay_count": restart_gap_replay_count,
        "seen_archive_items": len(seen_items),
        "seen_archive_updated_at": str(seen_archive.get("updated_at", "")),
        "slow_deliveries": slow_deliveries[:10],
        "slow_original_deliveries": slow_original_deliveries[:10],
        "slow_repost_deliveries": slow_repost_deliveries[:10],
    }


def summarize_watchdog(root, since, now):
    state = read_json(Path(root) / "watchdog_state.json", {})
    recent_actions = state.get("recent_actions", [])
    if not isinstance(recent_actions, list):
        recent_actions = []
    actions = []
    for action in recent_actions:
        checked_at = parse_iso_datetime(action.get("checked_at", ""))
        if checked_at is None or checked_at < since:
            continue
        actions.append(action)
    result_counts = Counter(str(action.get("result", "") or "unknown") for action in actions)
    restart_reasons = Counter(str(action.get("reason", "") or "unknown") for action in actions if action.get("result") == "restarted")
    slots = state.get("slots", {}) if isinstance(state.get("slots", {}), dict) else {}
    health = {}
    for key, value in slots.items():
        slot_health = dict((value or {}).get("last_health", {}) or {})
        health[key] = {
            "pid": slot_health.get("pid"),
            "running": slot_health.get("running"),
            "heartbeat_age_seconds": slot_health.get("heartbeat_age_seconds"),
            "latest_check_age_seconds": slot_health.get("latest_check_age_seconds"),
            "semantic_restart_reason": slot_health.get("semantic_restart_reason", ""),
            "semantic_static_stale_targets": slot_health.get("semantic_static_stale_targets", []),
        }
    heartbeat = parse_iso_datetime(state.get("heartbeat_at", ""))
    return {
        "root": str(root),
        "running_pid": int(state.get("watchdog_pid", 0) or 0),
        "heartbeat_at": heartbeat.isoformat() if heartbeat else "",
        "heartbeat_age_seconds": max(0, int((now - heartbeat).total_seconds())) if heartbeat else None,
        "result_counts": dict(result_counts),
        "restart_reasons": dict(restart_reasons),
        "recent_restart_actions": [
            {
                "slot": action.get("slot", ""),
                "checked_at": action.get("checked_at", ""),
                "reason": action.get("reason", ""),
                "ok": bool(action.get("ok")),
                "pid": ((action.get("restart") or {}).get("pid")),
            }
            for action in actions
            if action.get("result") == "restarted"
        ][-10:],
        "slot_health": health,
    }


def build_report(slot_roots, watchdog_root, hours):
    now = now_utc()
    since = now - timedelta(hours=float(hours))
    slots = [summarize_slot(root, slot_label(root, index), since, now) for index, root in enumerate(slot_roots)]
    watchdog = summarize_watchdog(watchdog_root, since, now)
    aggregate_delays = []
    for slot in slots:
        for row in slot.get("slow_deliveries", []):
            pass
        summary = slot.get("delivery_latency", {})
        # Recompute aggregate from per-target summaries is approximate, so keep aggregate simple.
    return {
        "service": SERVICE_NAME,
        "generated_at": now.isoformat(),
        "since": since.isoformat(),
        "hours": float(hours),
        "slots": slots,
        "watchdog": watchdog,
    }


def fmt_seconds(value):
    if value is None:
        return "-"
    return f"{int(value)}s"


def render_text_report(report):
    lines = []
    lines.append(f"Xplus quality report: last {report['hours']:g}h")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("")
    for slot in report["slots"]:
        latency = slot["delivery_latency"]
        original_latency = slot.get("delivery_latency_original", {})
        repost_latency = slot.get("delivery_latency_repost", {})
        lines.append(
            f"{slot['label']}: pid={slot['running_pid']} "
            f"heartbeat_age={fmt_seconds(slot['heartbeat_age_seconds'])} "
            f"check_age={fmt_seconds(slot['latest_check_age_seconds'])} "
            f"deliveries={latency['count']} p50={fmt_seconds(latency['p50'])} "
            f"p90={fmt_seconds(latency['p90'])} p95={fmt_seconds(latency['p95'])} "
            f"max={fmt_seconds(latency['max'])} over60={latency['over60']} over300={latency['over300']}"
        )
        lines.append(
            f"  original: deliveries={original_latency.get('count', 0)} "
            f"p50={fmt_seconds(original_latency.get('p50'))} "
            f"p90={fmt_seconds(original_latency.get('p90'))} "
            f"p95={fmt_seconds(original_latency.get('p95'))} "
            f"p99={fmt_seconds(original_latency.get('p99'))} "
            f"max={fmt_seconds(original_latency.get('max'))} "
            f"over60={original_latency.get('over60', 0)} over300={original_latency.get('over300', 0)}"
        )
        lines.append(
            f"  repost: deliveries={repost_latency.get('count', 0)} "
            f"p50={fmt_seconds(repost_latency.get('p50'))} "
            f"p90={fmt_seconds(repost_latency.get('p90'))} "
            f"p95={fmt_seconds(repost_latency.get('p95'))} "
            f"p99={fmt_seconds(repost_latency.get('p99'))} "
            f"max={fmt_seconds(repost_latency.get('max'))} "
            f"over60={repost_latency.get('over60', 0)} over300={repost_latency.get('over300', 0)} "
            f"reasons={slot.get('repost_reason_counts', {})}"
        )
        if slot.get("last_error"):
            lines.append(f"  last_error: {slot['last_error']}")
        lines.append(
            f"  checks={slot['check_count']} surfaces={slot['surface_counts']} "
            f"recoveries={slot['recovery_counts']}"
        )
        lines.append(
            f"  late_recovery={slot['late_recovery_count']} "
            f"late_recovery_max={fmt_seconds(slot['late_recovery_max_delay_seconds'])} "
            f"baseline_ids={slot['baseline_tweet_count']} new_ids={slot['new_tweet_count']} "
            f"seen_archive_items={slot['seen_archive_items']}"
        )
        if slot.get("slow_delivery_cause_counts"):
            lines.append(f"  slow causes={slot.get('slow_delivery_cause_counts', {})}")
        if slot["slow_deliveries"]:
            lines.append("  slow deliveries:")
            for row in slot["slow_deliveries"][:5]:
                handle = f"@{row['handle']}" if row.get("handle") else ""
                lines.append(
                    f"    {row.get('at','')} {row.get('target_key','')} "
                    f"{fmt_seconds(row.get('delay_seconds'))} {handle} {row.get('tweet_id','')} "
                    f"cause={row.get('slow_delivery_cause', 'unknown')}"
                )
        if slot.get("slow_original_deliveries"):
            lines.append("  slow original deliveries:")
            for row in slot["slow_original_deliveries"][:5]:
                handle = f"@{row['handle']}" if row.get("handle") else ""
                lines.append(
                    f"    {row.get('at','')} {row.get('target_key','')} "
                    f"{fmt_seconds(row.get('delay_seconds'))} {handle} {row.get('tweet_id','')}"
                )
        if slot.get("slow_repost_deliveries"):
            lines.append("  slow repost deliveries:")
            for row in slot["slow_repost_deliveries"][:5]:
                handle = f"@{row['handle']}" if row.get("handle") else ""
                context = f" {row.get('repost_context')}" if row.get("repost_context") else ""
                lines.append(
                    f"    {row.get('at','')} {row.get('target_key','')} "
                    f"{fmt_seconds(row.get('delay_seconds'))} {handle} {row.get('tweet_id','')}{context}"
                )
        lines.append("")
    watchdog = report["watchdog"]
    lines.append(
        f"watchdog: pid={watchdog['running_pid']} heartbeat_age={fmt_seconds(watchdog['heartbeat_age_seconds'])} "
        f"results={watchdog['result_counts']} restarts={watchdog['restart_reasons']}"
    )
    for slot, health in sorted(watchdog.get("slot_health", {}).items()):
        lines.append(
            f"  {slot}: pid={health.get('pid')} running={health.get('running')} "
            f"heartbeat_age={fmt_seconds(health.get('heartbeat_age_seconds'))} "
            f"check_age={fmt_seconds(health.get('latest_check_age_seconds'))} "
            f"semantic={health.get('semantic_restart_reason') or '-'} "
            f"static_stale={health.get('semantic_static_stale_targets') or []}"
        )
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(description=SERVICE_NAME)
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--slot-root", action="append", default=[])
    parser.add_argument("--watchdog-root", default=str(DEFAULT_WATCHDOG_ROOT))
    parser.add_argument("--json", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    slot_roots = [Path(item) for item in args.slot_root] if args.slot_root else list(DEFAULT_SLOT_ROOTS)
    report = build_report(slot_roots, Path(args.watchdog_root), args.hours)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
