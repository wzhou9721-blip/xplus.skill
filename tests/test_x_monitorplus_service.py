import contextlib
import importlib.util
import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "x_monitorplus_service.py"
MODULE_SPEC = importlib.util.spec_from_file_location("x_monitorplus_service", MODULE_PATH)
svc = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(svc)

WATCHDOG_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "x_monitorplus_watchdog.py"
WATCHDOG_MODULE_SPEC = importlib.util.spec_from_file_location("x_monitorplus_watchdog", WATCHDOG_MODULE_PATH)
watchdog = importlib.util.module_from_spec(WATCHDOG_MODULE_SPEC)
WATCHDOG_MODULE_SPEC.loader.exec_module(watchdog)


@contextlib.contextmanager
def temporary_test_dir():
    root = MODULE_PATH.parents[1] / ".tmp-tests"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"case-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


class FakeLocator:
    def __init__(self, count=0, text=""):
        self._count = count
        self._text = text

    def count(self):
        return self._count

    def inner_text(self, timeout=None):
        return self._text


class FakePage:
    def __init__(self, url="", counts=None, body_text="", goto_error=None, reload_error=None):
        self.url = url
        self.counts = dict(counts or {})
        self.body_text = body_text
        self.goto_error = goto_error
        self.reload_error = reload_error
        self.waits = []
        self.goto_calls = []
        self.reload_calls = []
        self.evaluations = []
        self.closed = False

    def locator(self, selector):
        count = self.counts.get(selector, 0)
        text = self.body_text if selector == "body" else ""
        return FakeLocator(count=count, text=text)

    def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append({"url": url, "wait_until": wait_until, "timeout": timeout})
        if self.goto_error is not None:
            raise self.goto_error
        self.url = url

    def reload(self, **kwargs):
        self.reload_calls.append(dict(kwargs))
        if self.reload_error is not None:
            raise self.reload_error

    def evaluate(self, script):
        self.evaluations.append(script)
        return 0

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, page):
        self.page = page
        self.new_page_calls = 0

    def new_page(self):
        self.new_page_calls += 1
        return self.page


class FakeExecutor:
    def __init__(self):
        self.submissions = []

    def submit(self, *args, **kwargs):
        self.submissions.append((args, kwargs))


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise svc.requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return dict(self._payload)


class XMonitorPlusServiceTests(unittest.TestCase):
    def test_watchdog_keeps_supported_slot_roots_distinct(self):
        roots = [
            "x-monitor-plus",
            "x-monitor-plus-2",
            "x-monitor-plus-3",
            "x-monitor-plus-4",
            "x-monitor-plus-5",
        ]

        self.assertEqual(
            [watchdog.slot_key(root) for root in roots],
            ["slot2", "slot3", "slot4", "slot5", "slot6"],
        )

    def test_default_browser_channel_auto_falls_back_to_bundled_chromium(self):
        self.assertEqual(svc.base_config()["browser_channel"], "auto")
        self.assertEqual(svc.browser_channel_sequence({"browser_channel": "auto"}), ["chrome", ""])
        self.assertEqual(svc.browser_channel_sequence({"browser_channel": "chromium"}), [""])
        self.assertEqual(svc.browser_channel_label(""), "playwright-chromium")

    def test_normalize_list_configs_preserves_stale_refresh_options(self):
        config = {
            "x_lists": [
                {
                    "id": "list1",
                    "name": "list-core",
                    "url": "https://x.com/i/lists/1",
                    "enabled": True,
                    "stale_refresh_enabled": True,
                    "stale_refresh_top_delay_seconds": 45,
                    "stale_refresh_unchanged_count": 2,
                    "stale_refresh_cooldown_seconds": 30,
                }
            ]
        }

        entries = svc.normalize_list_configs(config)

        self.assertTrue(entries[0]["stale_refresh_enabled"])
        self.assertEqual(entries[0]["stale_refresh_top_delay_seconds"], 45)
        self.assertEqual(entries[0]["stale_refresh_unchanged_count"], 2)
        self.assertEqual(entries[0]["stale_refresh_cooldown_seconds"], 30)

    def test_stale_refresh_triggers_after_old_unchanged_top_and_cooldown(self):
        with temporary_test_dir() as root:
            store = svc.Store(root)
            config = svc.base_config()
            target = {
                "key": "list1",
                "mode": svc.MODE_LIST,
                "label": "list-core",
                "name": "list-core",
                "url": "https://x.com/i/lists/1",
                "stale_refresh_top_delay_seconds": 45,
                "stale_refresh_unchanged_count": 2,
                "stale_refresh_cooldown_seconds": 30,
            }
            check = {
                "target_key": "list1",
                "current_top_tweet_id": "tweet-1",
                "top_delay_seconds": 60,
            }

            first = svc.stale_refresh_state_update(
                store,
                "list1",
                check,
                config,
                target,
                "2026-05-02T05:00:00+00:00",
            )
            second = svc.stale_refresh_state_update(
                store,
                "list1",
                check,
                config,
                target,
                "2026-05-02T05:00:03+00:00",
            )
            cooldown = svc.stale_refresh_state_update(
                store,
                "list1",
                check,
                config,
                target,
                "2026-05-02T05:00:20+00:00",
            )
            escalated = svc.stale_refresh_state_update(
                store,
                "list1",
                check,
                config,
                target,
                "2026-05-02T05:00:35+00:00",
            )

            self.assertFalse(first["should_refresh"])
            self.assertTrue(second["should_refresh"])
            self.assertEqual(second["recovery_method"], "fast_reopen")
            self.assertEqual(second["trigger_count"], 1)
            self.assertFalse(cooldown["should_refresh"])
            self.assertEqual(cooldown["unchanged_count"], 3)
            self.assertTrue(escalated["should_refresh"])
            self.assertEqual(escalated["recovery_method"], "full_reload")
            self.assertEqual(escalated["trigger_count"], 2)

    def test_hot_list_acceleration_temporarily_lowers_stale_thresholds(self):
        with temporary_test_dir() as root:
            store = svc.Store(root)
            config = svc.base_config()
            config["hot_list_acceleration_enabled"] = True
            config["hot_list_stale_top_delay_seconds"] = 45
            config["hot_list_stale_unchanged_count"] = 2
            config["hot_list_stale_cooldown_seconds"] = 30
            target = {
                "key": "list1",
                "mode": svc.MODE_LIST,
                "label": "list-core",
                "name": "list-core",
                "url": "https://x.com/i/lists/1",
            }
            activation = svc.activate_hot_list_acceleration(
                store,
                "list1",
                config,
                "2026-05-02T05:00:00+00:00",
                "slow_delivery",
                delay_seconds=56,
            )
            self.assertTrue(activation["hot_list_acceleration"])

            result = {}
            for index in range(2):
                result = svc.stale_refresh_state_update(
                    store,
                    "list1",
                    {
                        "target_key": "list1",
                        "current_top_tweet_id": "tweet-1",
                        "top_delay_seconds": 50,
                    },
                    config,
                    target,
                    f"2026-05-02T05:00:0{index}+00:00",
                )

            self.assertTrue(result["should_refresh"])
            self.assertTrue(result["hot_list_acceleration"])
            self.assertEqual(result["top_delay_threshold_seconds"], 45)
            self.assertEqual(result["unchanged_threshold"], 2)

    def test_hot_list_acceleration_disabled_ignores_existing_hot_state(self):
        with temporary_test_dir() as root:
            store = svc.Store(root)
            config = svc.base_config()
            config["hot_list_acceleration_enabled"] = False
            config["stale_refresh_top_delay_seconds"] = 180
            config["stale_refresh_unchanged_count"] = 12
            config["stale_refresh_cooldown_seconds"] = 180
            target = {
                "key": "list1",
                "mode": svc.MODE_LIST,
                "name": "list-core",
                "url": "https://x.com/i/lists/1",
            }

            def seed_state(state):
                target_state = svc.base_target_state()
                target_state["stale_refresh_top_tweet_id"] = "old-top"
                target_state["stale_refresh_unchanged_count"] = 11
                target_state["stale_refresh_trigger_count"] = 7
                target_state["stale_refresh_last_at"] = "2026-05-02T05:00:00+00:00"
                target_state["hot_list_acceleration_until"] = "2026-05-02T05:30:00+00:00"
                target_state["hot_list_acceleration_reason"] = "stale_refresh_no_items"
                target_state["hot_list_acceleration_delay_seconds"] = 320
                state.setdefault("targets", {})["list1"] = target_state
                return state

            store.update_state(seed_state)

            result = svc.stale_refresh_state_update(
                store,
                "list1",
                {
                    "target_key": "list1",
                    "current_top_tweet_id": "old-top",
                    "top_delay_seconds": 200,
                },
                config,
                target,
                "2026-05-02T05:05:00+00:00",
            )
            state = store.load_state()

            self.assertFalse(result.get("hot_list_acceleration", False))
            self.assertEqual(result["cooldown_seconds"], 180)
            self.assertEqual(result["unchanged_threshold"], 12)
            self.assertEqual(state["targets"]["list1"]["hot_list_acceleration_until"], "")

    def test_stale_refresh_light_scroll_recheck_runs_when_top_stays_old(self):
        original_collect_target_items = svc.collect_target_items
        try:
            page = FakePage(url="https://x.com/i/lists/current")
            target = {
                "key": "list2",
                "mode": svc.MODE_LIST,
                "label": "Balanced 2",
                "name": "Balanced 2",
                "url": "https://x.com/i/lists/2045766641817162232",
                "list_index": 2,
            }
            calls = []

            def fake_collect_target_items(*args, **kwargs):
                calls.append(kwargs)
                return [{"tweet_id": "fresh-after-scroll", "created_at": "2026-05-02T05:01:00+00:00"}], {}

            svc.collect_target_items = fake_collect_target_items

            items, meta = svc.stale_refresh_light_scroll_recheck(
                page,
                target,
                svc.base_config(),
                [{"tweet_id": "old-top", "created_at": "2026-05-02T05:00:00+00:00"}],
                previous_top_tweet_id="old-top",
            )

            self.assertEqual(first := items[0]["tweet_id"], "fresh-after-scroll")
            self.assertEqual(first, meta["stale_refresh_light_scroll_recheck_top_tweet_id"])
            self.assertEqual(meta["stale_refresh_light_scroll_recheck_attempts"], 1)
            self.assertEqual(len(calls), 1)
            self.assertTrue(page.evaluations)
        finally:
            svc.collect_target_items = original_collect_target_items

    def test_slow_delivery_fields_classify_stale_recovered_original(self):
        config = svc.base_config()
        fields = svc.slow_delivery_fields(
            {"tweet_id": "tweet-1", "is_repost": False, "repost_context": ""},
            56,
            config,
            delivery_context={"stale_refresh": "full_reload"},
        )

        self.assertTrue(fields["slow_delivery"])
        self.assertEqual(fields["slow_delivery_cause"], "stale_recovered")
        self.assertEqual(fields["slow_delivery_threshold_seconds"], svc.DEFAULT_SLOW_ATTRIBUTION_THRESHOLD_SECONDS)

    def test_discord_send_retries_timeout_with_stable_nonce(self):
        original_post = svc.requests.post
        original_sleep = svc.time.sleep
        try:
            calls = []

            def flaky_post(url, headers=None, json=None, timeout=None):
                calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
                if len(calls) == 1:
                    raise svc.requests.Timeout("discord read timed out")
                return FakeResponse(payload={"id": "msg-1"})

            svc.requests.post = flaky_post
            svc.time.sleep = lambda seconds: None

            config = svc.base_config()
            config["discord_channel_id"] = "channel-1"
            config["discord_bot_token"] = "Bot token"
            config["discord_transient_retry_count"] = 1

            result = svc.discord_send(config, "hello https://x.com/test/status/1")

            self.assertEqual(result["id"], "msg-1")
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["json"]["nonce"], calls[1]["json"]["nonce"])
            self.assertTrue(calls[0]["json"]["enforce_nonce"])
            self.assertIn("<https://x.com/test/status/1>", calls[0]["json"]["content"])
        finally:
            svc.requests.post = original_post
            svc.time.sleep = original_sleep

    def test_discord_edit_retries_transient_server_error(self):
        original_patch = svc.requests.patch
        original_sleep = svc.time.sleep
        try:
            calls = []

            def flaky_patch(url, headers=None, json=None, timeout=None):
                calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
                if len(calls) == 1:
                    return FakeResponse(status_code=502, payload={"message": "bad gateway"})
                return FakeResponse(payload={"id": "msg-1"})

            svc.requests.patch = flaky_patch
            svc.time.sleep = lambda seconds: None

            config = svc.base_config()
            config["discord_channel_id"] = "channel-1"
            config["discord_bot_token"] = "Bot token"
            config["discord_transient_retry_count"] = 1

            result = svc.discord_edit(config, "msg-1", "updated")

            self.assertEqual(result["id"], "msg-1")
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["json"], {"content": "updated"})
        finally:
            svc.requests.patch = original_patch
            svc.time.sleep = original_sleep

    def test_jsonl_only_sink_does_not_require_discord_config(self):
        config = svc.base_config()
        config["output_sinks"] = ["jsonl"]
        config["discord_enabled"] = False

        self.assertNotIn("discord_channel_id", svc.config_missing(config))
        self.assertNotIn("discord_bot_token", svc.config_missing(config))

    def test_jsonl_only_sink_archives_new_items_without_discord_send(self):
        original_discord_send = svc.discord_send
        original_find_recent_near_duplicate_event = svc.find_recent_near_duplicate_event
        original_iso_now = svc.iso_now
        try:
            svc.discord_send = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("discord should not be called"))
            svc.find_recent_near_duplicate_event = lambda recent_events, target_ref, item, observed_at, config: None
            svc.iso_now = lambda: "2026-05-02T05:00:05+00:00"

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                state = svc.base_state()
                state["last_service_start_at"] = "2026-05-02T04:59:00+00:00"
                store.save_state(state)
                config = svc.base_config()
                config["output_sinks"] = ["jsonl"]
                config["discord_enabled"] = False
                target = {
                    "key": "list1",
                    "mode": svc.MODE_LIST,
                    "label": "list-core",
                    "name": "list-core",
                    "url": "https://x.com/i/lists/1",
                    "list_index": 1,
                }
                items = [
                    {
                        "tweet_id": "tweet-jsonl",
                        "created_at": "2026-05-02T05:00:00+00:00",
                        "status_url": "https://x.com/test/status/tweet-jsonl",
                        "handle": "agenttest",
                        "text": "Agent-first local event",
                        "is_repost": False,
                        "repost_context": "",
                        "is_filtered_repost": False,
                        "repost_filter_reason": "",
                        "is_teaser": False,
                        "has_image": False,
                        "has_video": False,
                        "has_external_link": False,
                    }
                ]

                delivered = svc.handle_new_items(store, config, FakeExecutor(), target, items, "2026-05-02T05:00:04+00:00")
                archive_lines = (Path(tmpdir) / svc.EVENT_ARCHIVE_FILENAME).read_text(encoding="utf-8").splitlines()
                event = json.loads(archive_lines[-1])

            self.assertEqual(delivered, ["tweet-jsonl"])
            self.assertEqual(event["tweet_id"], "tweet-jsonl")
            self.assertEqual(event["output_sinks"], ["jsonl"])
            self.assertFalse(event["discord_delivered"])
            self.assertEqual(event["message_id"], "")
        finally:
            svc.discord_send = original_discord_send
            svc.find_recent_near_duplicate_event = original_find_recent_near_duplicate_event
            svc.iso_now = original_iso_now

    def test_watchdog_keeps_disabled_slot_stopped(self):
        config = {
            "heartbeat_stale_seconds": 180,
            "check_archive_stale_seconds": 180,
            "ready_stale_seconds": 600,
        }
        health = {
            "should_run": False,
            "running": False,
            "heartbeat_age_seconds": None,
            "check_archive_age_seconds": None,
            "latest_ready_age_seconds": None,
            "driver_error": "",
        }
        self.assertEqual(watchdog.stale_reason(health, config, {}, watchdog.now_utc()), "")

    def test_watchdog_detects_stale_heartbeat(self):
        config = {
            "heartbeat_stale_seconds": 180,
            "check_archive_stale_seconds": 180,
            "ready_stale_seconds": 600,
        }
        health = {
            "should_run": True,
            "running": True,
            "heartbeat_age_seconds": 181,
            "check_archive_age_seconds": 1,
            "latest_ready_age_seconds": 1,
            "driver_error": "",
        }
        self.assertEqual(
            watchdog.stale_reason(health, config, {}, watchdog.now_utc()),
            "heartbeat_stale:181s",
        )

    def test_watchdog_accepts_recent_checks_while_heartbeat_is_bootstrapping(self):
        config = {
            "heartbeat_stale_seconds": 180,
            "check_archive_stale_seconds": 180,
            "ready_stale_seconds": 600,
        }
        health = {
            "should_run": True,
            "running": True,
            "heartbeat_age_seconds": None,
            "check_archive_age_seconds": 15,
            "latest_ready_age_seconds": 15,
            "driver_error": "",
        }
        self.assertEqual(watchdog.stale_reason(health, config, {}, watchdog.now_utc()), "")

    def test_watchdog_detects_new_driver_error_once(self):
        config = {
            "heartbeat_stale_seconds": 180,
            "check_archive_stale_seconds": 180,
            "ready_stale_seconds": 600,
        }
        error = "connection closed while reading from the driver"
        health = {
            "should_run": True,
            "running": True,
            "heartbeat_age_seconds": 1,
            "check_archive_age_seconds": 1,
            "latest_ready_age_seconds": 1,
            "driver_error": error,
        }
        self.assertTrue(watchdog.stale_reason(health, config, {}, watchdog.now_utc()).startswith("driver_error:"))
        self.assertEqual(
            watchdog.stale_reason(health, config, {"last_driver_error": error}, watchdog.now_utc()),
            "",
        )

    def test_watchdog_ready_stale_is_observation_only_by_default(self):
        config = {
            "heartbeat_stale_seconds": 180,
            "check_archive_stale_seconds": 180,
            "ready_stale_seconds": 600,
        }
        health = {
            "should_run": True,
            "running": True,
            "heartbeat_age_seconds": 1,
            "check_archive_age_seconds": 1,
            "latest_ready_age_seconds": 601,
            "driver_error": "",
        }
        self.assertEqual(watchdog.stale_reason(health, config, {}, watchdog.now_utc()), "")

        config["ready_stale_restart_enabled"] = True
        self.assertEqual(
            watchdog.stale_reason(health, config, {}, watchdog.now_utc()),
            "ready_check_stale:601s",
        )

    def test_watchdog_semantic_health_restarts_after_late_recovery_signal(self):
        config = {
            "semantic_window_seconds": 900,
            "semantic_restart_enabled": True,
            "semantic_late_recovery_restart_count": 2,
            "semantic_late_recovery_max_delay_seconds": 300,
            "semantic_static_top_delay_seconds": 3600,
            "semantic_static_check_count": 8,
        }
        current_time = watchdog.parse_iso_datetime("2026-04-29T10:20:00+00:00")
        rows = [
            {
                "at": "2026-04-29T10:18:00+00:00",
                "target_key": "list2",
                "page_surface_state": "ready",
                "late_new_item_recovery": "fast_reopen",
                "late_new_item_recovery_candidates": 1,
                "late_new_item_recovery_max_delay_seconds": 240,
            },
            {
                "at": "2026-04-29T10:19:00+00:00",
                "target_key": "list2",
                "page_surface_state": "ready",
                "late_new_item_recovery": "fast_reopen",
                "late_new_item_recovery_candidates": 1,
                "late_new_item_recovery_max_delay_seconds": 260,
            },
        ]

        semantic = watchdog.build_semantic_health(
            rows,
            current_time,
            config,
            service_start_at="2026-04-29T10:00:00+00:00",
        )

        self.assertEqual(semantic["restart_reason"], "semantic_late_recovery:list2:count=2:max_delay=260s")

    def test_watchdog_semantic_health_observes_late_recovery_without_restart_by_default(self):
        config = {
            "semantic_window_seconds": 900,
            "semantic_late_recovery_restart_count": 2,
            "semantic_late_recovery_max_delay_seconds": 300,
            "semantic_static_top_delay_seconds": 3600,
            "semantic_static_check_count": 8,
        }
        current_time = watchdog.parse_iso_datetime("2026-04-29T10:20:00+00:00")
        rows = [
            {
                "at": "2026-04-29T10:18:00+00:00",
                "target_key": "list2",
                "page_surface_state": "ready",
                "late_new_item_recovery": "fast_reopen",
                "late_new_item_recovery_candidates": 1,
                "late_new_item_recovery_max_delay_seconds": 240,
            },
            {
                "at": "2026-04-29T10:19:00+00:00",
                "target_key": "list2",
                "page_surface_state": "ready",
                "late_new_item_recovery": "fast_reopen",
                "late_new_item_recovery_candidates": 1,
                "late_new_item_recovery_max_delay_seconds": 260,
            },
        ]

        semantic = watchdog.build_semantic_health(
            rows,
            current_time,
            config,
            service_start_at="2026-04-29T10:00:00+00:00",
        )

        self.assertEqual(semantic["restart_reason"], "")
        self.assertEqual(semantic["late_recovery_targets"]["list2"]["count"], 2)

    def test_watchdog_semantic_health_ignores_previous_service_signals(self):
        config = {
            "semantic_window_seconds": 900,
            "semantic_restart_enabled": True,
            "semantic_late_recovery_restart_count": 1,
            "semantic_late_recovery_max_delay_seconds": 120,
            "semantic_static_top_delay_seconds": 3600,
            "semantic_static_check_count": 8,
        }
        current_time = watchdog.parse_iso_datetime("2026-04-29T10:20:00+00:00")
        rows = [
            {
                "at": "2026-04-29T10:18:00+00:00",
                "target_key": "list2",
                "page_surface_state": "ready",
                "late_new_item_recovery": "fast_reopen",
                "late_new_item_recovery_candidates": 1,
                "late_new_item_recovery_max_delay_seconds": 260,
            }
        ]

        semantic = watchdog.build_semantic_health(
            rows,
            current_time,
            config,
            service_start_at="2026-04-29T10:19:00+00:00",
        )

        self.assertEqual(semantic["restart_reason"], "")
        self.assertEqual(semantic["late_recovery_targets"], {})

    def test_watchdog_semantic_health_reports_static_old_ready_timeline(self):
        config = {
            "semantic_window_seconds": 900,
            "semantic_late_recovery_restart_count": 2,
            "semantic_late_recovery_max_delay_seconds": 300,
            "semantic_static_top_delay_seconds": 3600,
            "semantic_static_check_count": 3,
        }
        current_time = watchdog.parse_iso_datetime("2026-04-29T10:20:00+00:00")
        rows = [
            {
                "at": f"2026-04-29T10:1{minute}:00+00:00",
                "target_key": "list3",
                "page_surface_state": "ready",
                "visible_tweet_ids": ["old-1", "old-2", "old-3"],
                "top_delay_seconds": 3700 + minute,
            }
            for minute in range(3)
        ]

        semantic = watchdog.build_semantic_health(
            rows,
            current_time,
            config,
            service_start_at="2026-04-29T10:00:00+00:00",
        )

        self.assertEqual(semantic["restart_reason"], "")
        self.assertEqual(semantic["static_stale_targets"][0]["target_key"], "list3")
        self.assertEqual(semantic["static_stale_targets"][0]["unchanged_ready_count"], 3)

    def test_watchdog_enabled_targets_require_active_monitoring(self):
        self.assertEqual(watchdog.enabled_targets({"x_home_enabled": False, "x_list_enabled": False}), [])
        self.assertEqual(
            watchdog.enabled_targets(
                {
                    "x_home_enabled": False,
                    "x_list_enabled": True,
                    "x_lists": [
                        {"id": "list1", "url": "https://x.com/i/lists/1", "enabled": True},
                        {"id": "list2", "url": "https://x.com/i/lists/2", "enabled": False},
                    ],
                }
            ),
            ["list1"],
        )

    def test_handle_new_items_defers_machine_translation_to_async(self):
        original_discord_send = svc.discord_send
        original_build_machine_translation_draft = svc.build_machine_translation_draft
        original_find_recent_near_duplicate_event = svc.find_recent_near_duplicate_event
        try:
            sent_payloads = []
            svc.discord_send = lambda config, content: sent_payloads.append(content) or {"id": "msg-1"}

            def fail_if_called(*args, **kwargs):
                raise AssertionError("machine translation should be deferred to the async worker")

            svc.build_machine_translation_draft = fail_if_called
            svc.find_recent_near_duplicate_event = lambda recent_events, target_ref, item, observed_at, config: None

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                state = svc.base_state()
                state["last_service_start_at"] = "2026-04-19T08:00:00+00:00"
                store.save_state(state)
                executor = FakeExecutor()
                target = {
                    "key": "list1",
                    "mode": svc.MODE_LIST,
                    "label": "Balanced 1",
                    "name": "Balanced 1",
                    "url": "https://x.com/i/lists/2045764486196592926",
                    "list_index": 1,
                }
                items = [
                    {
                        "tweet_id": "tweet-1",
                        "created_at": "2026-04-19T08:10:00+00:00",
                        "status_url": "https://x.com/test/status/tweet-1",
                        "handle": "testhandle",
                        "text": "Original source text for async translation",
                        "is_repost": False,
                        "repost_context": "",
                        "is_filtered_repost": False,
                        "repost_filter_reason": "",
                        "is_teaser": False,
                        "has_image": False,
                        "has_video": False,
                        "has_external_link": False,
                    }
                ]

                delivered = svc.handle_new_items(
                    store,
                    svc.base_config(),
                    executor,
                    target,
                    items,
                    "2026-04-19T08:11:00+00:00",
                )
                latest_state = store.load_state()

            self.assertEqual(delivered, ["tweet-1"])
            self.assertEqual(len(sent_payloads), 1)
            self.assertIn("状态：待熟肉", sent_payloads[0])
            self.assertIn("Original source text for async translation", sent_payloads[0])
            self.assertEqual(len(executor.submissions), 1)
            self.assertEqual(latest_state["recent_events"][-1]["draft_status"], "pending")
            self.assertIn("is_repost", latest_state["recent_events"][-1])
            self.assertFalse(latest_state["recent_events"][-1]["is_repost"])
        finally:
            svc.discord_send = original_discord_send
            svc.build_machine_translation_draft = original_build_machine_translation_draft
            svc.find_recent_near_duplicate_event = original_find_recent_near_duplicate_event

    def test_handle_new_items_suppresses_stale_backfill(self):
        original_discord_send = svc.discord_send
        original_find_recent_near_duplicate_event = svc.find_recent_near_duplicate_event
        try:
            sent_payloads = []
            svc.discord_send = lambda config, content: sent_payloads.append(content) or {"id": "msg-1"}
            svc.find_recent_near_duplicate_event = lambda recent_events, target_ref, item, observed_at, config: None

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                state = svc.base_state()
                state["last_service_start_at"] = "2026-04-19T08:00:00+00:00"
                store.save_state(state)
                executor = FakeExecutor()
                config = svc.base_config()
                config["max_delivery_delay_seconds"] = 300
                target = {
                    "key": "list1",
                    "mode": svc.MODE_LIST,
                    "label": "Balanced 1",
                    "name": "Balanced 1",
                    "url": "https://x.com/i/lists/2045764486196592926",
                    "list_index": 1,
                }
                items = [
                    {
                        "tweet_id": "tweet-stale",
                        "created_at": "2026-04-19T08:04:00+00:00",
                        "status_url": "https://x.com/test/status/tweet-stale",
                        "handle": "testhandle",
                        "text": "Older item surfaced by the list later",
                        "is_repost": False,
                        "repost_context": "",
                        "is_filtered_repost": False,
                        "repost_filter_reason": "",
                        "is_teaser": False,
                        "has_image": False,
                        "has_video": False,
                        "has_external_link": False,
                    }
                ]

                delivered = svc.handle_new_items(
                    store,
                    config,
                    executor,
                    target,
                    items,
                    "2026-04-19T08:11:00+00:00",
                )
                latest_state = store.load_state()
                archive_records = [
                    json.loads(line)
                    for line in (Path(tmpdir) / svc.EVENT_ARCHIVE_FILENAME).read_text(encoding="utf-8").splitlines()
                ]

            self.assertEqual(delivered, [])
            self.assertEqual(sent_payloads, [])
            self.assertEqual(executor.submissions, [])
            self.assertIn("tweet-stale", latest_state["seen_ids"])
            self.assertEqual(latest_state["recent_events"][-1]["event_type"], "stale_backfill_suppressed")
            self.assertEqual(latest_state["recent_events"][-1]["delay_seconds"], 420)
            self.assertEqual(archive_records[-1]["archive_event_type"], "suppressed")
        finally:
            svc.discord_send = original_discord_send
            svc.find_recent_near_duplicate_event = original_find_recent_near_duplicate_event

    def test_handle_new_items_delivers_late_backfill_by_default(self):
        original_discord_send = svc.discord_send
        original_find_recent_near_duplicate_event = svc.find_recent_near_duplicate_event
        original_iso_now = svc.iso_now
        try:
            sent_payloads = []
            svc.discord_send = lambda config, content: sent_payloads.append(content) or {"id": "msg-1"}
            svc.find_recent_near_duplicate_event = lambda recent_events, target_ref, item, observed_at, config: None
            svc.iso_now = lambda: "2026-04-19T08:11:00+00:00"

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                state = svc.base_state()
                state["last_service_start_at"] = "2026-04-19T08:00:00+00:00"
                store.save_state(state)
                executor = FakeExecutor()
                target = {
                    "key": "list1",
                    "mode": svc.MODE_LIST,
                    "label": "Balanced 1",
                    "name": "Balanced 1",
                    "url": "https://x.com/i/lists/2045764486196592926",
                    "list_index": 1,
                }
                items = [
                    {
                        "tweet_id": "tweet-late",
                        "created_at": "2026-04-19T08:04:00+00:00",
                        "status_url": "https://x.com/test/status/tweet-late",
                        "handle": "testhandle",
                        "text": "Late but still must be delivered",
                        "is_repost": False,
                        "repost_context": "",
                        "is_filtered_repost": False,
                        "repost_filter_reason": "",
                        "is_teaser": False,
                        "has_image": False,
                        "has_video": False,
                        "has_external_link": False,
                    }
                ]

                delivered = svc.handle_new_items(
                    store,
                    svc.base_config(),
                    executor,
                    target,
                    items,
                    "2026-04-19T08:11:00+00:00",
                )
                latest_state = store.load_state()

            self.assertEqual(delivered, ["tweet-late"])
            self.assertEqual(len(sent_payloads), 1)
            self.assertEqual(latest_state["recent_events"][-1]["tweet_id"], "tweet-late")
            self.assertEqual(latest_state["recent_events"][-1]["delay_seconds"], 420)
        finally:
            svc.discord_send = original_discord_send
            svc.find_recent_near_duplicate_event = original_find_recent_near_duplicate_event
            svc.iso_now = original_iso_now

    def test_service_start_baselines_all_prestart_items(self):
        original_discord_send = svc.discord_send
        original_find_recent_near_duplicate_event = svc.find_recent_near_duplicate_event
        original_iso_now = svc.iso_now
        try:
            sent_payloads = []
            svc.discord_send = lambda config, content: sent_payloads.append(content) or {"id": f"msg-{len(sent_payloads)}"}
            svc.find_recent_near_duplicate_event = lambda recent_events, target_ref, item, observed_at, config: None
            svc.iso_now = lambda: "2026-04-19T09:01:00+00:00"

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                state = svc.base_state()
                state["last_service_start_at"] = "2026-04-19T09:00:00+00:00"
                store.save_state(state)
                executor = FakeExecutor()
                config = svc.base_config()
                config["restart_gap_replay_seconds"] = 300
                target = {
                    "key": "list1",
                    "mode": svc.MODE_LIST,
                    "label": "Balanced 1",
                    "name": "Balanced 1",
                    "url": "https://x.com/i/lists/2045764486196592926",
                    "list_index": 1,
                }
                items = [
                    {
                        "tweet_id": "recent-prestart",
                        "created_at": "2026-04-19T08:58:30+00:00",
                        "status_url": "https://x.com/test/status/recent-prestart",
                        "handle": "testhandle",
                        "text": "Recent pre-start item should baseline",
                        "is_repost": False,
                        "repost_context": "",
                        "is_filtered_repost": False,
                        "repost_filter_reason": "",
                        "is_teaser": False,
                        "has_image": False,
                        "has_video": False,
                        "has_external_link": False,
                    },
                    {
                        "tweet_id": "old-prestart",
                        "created_at": "2026-04-19T08:40:00+00:00",
                        "status_url": "https://x.com/test/status/old-prestart",
                        "handle": "testhandle",
                        "text": "Old pre-start item should baseline",
                        "is_repost": False,
                        "repost_context": "",
                        "is_filtered_repost": False,
                        "repost_filter_reason": "",
                        "is_teaser": False,
                        "has_image": False,
                        "has_video": False,
                        "has_external_link": False,
                    },
                ]

                baseline_ids = svc.maybe_bootstrap(
                    store,
                    config,
                    target,
                    items,
                    "2026-04-19T09:01:00+00:00",
                )
                delivered = svc.handle_new_items(
                    store,
                    config,
                    executor,
                    target,
                    items,
                    "2026-04-19T09:01:00+00:00",
                )
                latest_state = store.load_state()

            self.assertEqual(baseline_ids, ["recent-prestart", "old-prestart"])
            self.assertEqual(delivered, [])
            self.assertIn("old-prestart", latest_state["seen_ids"])
            self.assertIn("recent-prestart", latest_state["seen_ids"])
            self.assertEqual(latest_state["recent_events"], [])
            self.assertEqual(len(sent_payloads), 0)
        finally:
            svc.discord_send = original_discord_send
            svc.find_recent_near_duplicate_event = original_find_recent_near_duplicate_event
            svc.iso_now = original_iso_now

    def test_durable_seen_archive_prevents_duplicate_after_state_trim(self):
        original_discord_send = svc.discord_send
        original_find_recent_near_duplicate_event = svc.find_recent_near_duplicate_event
        try:
            sent_payloads = []
            svc.discord_send = lambda config, content: sent_payloads.append(content) or {"id": "msg-1"}
            svc.find_recent_near_duplicate_event = lambda recent_events, target_ref, item, observed_at, config: None

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                state = svc.base_state()
                state["last_service_start_at"] = "2026-04-19T08:00:00+00:00"
                store.save_state(state)
                config = svc.base_config()
                config["durable_seen_retention_seconds"] = 72 * 3600
                target = {
                    "key": "list1",
                    "mode": svc.MODE_LIST,
                    "label": "Balanced 1",
                    "name": "Balanced 1",
                    "url": "https://x.com/i/lists/2045764486196592926",
                    "list_index": 1,
                }
                svc.mark_seen_ids(
                    store,
                    ["tweet-durable"],
                    stamp="2026-04-19T08:10:00+00:00",
                    config=config,
                    target_ref=target,
                )
                trimmed_state = store.load_state()
                trimmed_state["seen_ids"] = {}
                store.save_state(trimmed_state)
                items = [
                    {
                        "tweet_id": "tweet-durable",
                        "created_at": "2026-04-19T08:10:00+00:00",
                        "status_url": "https://x.com/test/status/tweet-durable",
                        "handle": "testhandle",
                        "text": "This should not duplicate",
                        "is_repost": False,
                        "repost_context": "",
                        "is_filtered_repost": False,
                        "repost_filter_reason": "",
                        "is_teaser": False,
                        "has_image": False,
                        "has_video": False,
                        "has_external_link": False,
                    }
                ]

                delivered = svc.handle_new_items(
                    store,
                    config,
                    FakeExecutor(),
                    target,
                    items,
                    "2026-04-19T08:20:00+00:00",
                )
                archive = json.loads((Path(tmpdir) / svc.SEEN_ARCHIVE_FILENAME).read_text(encoding="utf-8"))

            self.assertEqual(delivered, [])
            self.assertEqual(sent_payloads, [])
            self.assertIn("tweet-durable", archive["items"])
            self.assertEqual(archive["items"]["tweet-durable"]["target_key"], "list1")
        finally:
            svc.discord_send = original_discord_send
            svc.find_recent_near_duplicate_event = original_find_recent_near_duplicate_event

    def test_durable_seen_archive_trims_by_retention(self):
        with temporary_test_dir() as tmpdir:
            store = svc.Store(root=tmpdir)
            config = svc.base_config()
            config["durable_seen_retention_seconds"] = 3600
            svc.mark_seen_ids(
                store,
                ["old-seen"],
                stamp="2026-04-19T08:00:00+00:00",
                config=config,
                target_ref={"key": "list1"},
            )
            svc.mark_seen_ids(
                store,
                ["fresh-seen"],
                stamp="2026-04-19T09:30:00+00:00",
                config=config,
                target_ref={"key": "list1"},
            )

            seen = svc.durable_seen_ids(store, config, observed_at="2026-04-19T10:00:00+00:00")

        self.assertNotIn("old-seen", seen)
        self.assertIn("fresh-seen", seen)

    def test_late_unseen_items_for_recovery_flags_late_unseen_without_suppressing(self):
        state = svc.base_state()
        state["last_service_start_at"] = "2026-04-19T08:00:00+00:00"
        state["seen_ids"] = {"already-seen": "2026-04-19T08:10:00+00:00"}
        config = svc.base_config()
        target = {"key": "list1", "mode": svc.MODE_LIST}
        items = [
            {
                "tweet_id": "late-unseen",
                "created_at": "2026-04-19T08:08:00+00:00",
                "is_filtered_repost": False,
                "is_teaser": False,
            },
            {
                "tweet_id": "fresh-unseen",
                "created_at": "2026-04-19T08:10:10+00:00",
                "is_filtered_repost": False,
                "is_teaser": False,
            },
            {
                "tweet_id": "already-seen",
                "created_at": "2026-04-19T08:07:00+00:00",
                "is_filtered_repost": False,
                "is_teaser": False,
            },
        ]

        late_items = svc.late_unseen_items_for_recovery(
            state,
            config,
            target,
            items,
            "2026-04-19T08:11:00+00:00",
        )

        self.assertEqual([item["tweet_id"] for item in late_items], ["late-unseen"])

    def test_handle_new_items_marks_each_success_before_later_send_failure(self):
        original_discord_send = svc.discord_send
        original_find_recent_near_duplicate_event = svc.find_recent_near_duplicate_event
        original_log_exception = svc.log_exception
        try:
            send_attempts = []

            def flaky_send(config, content):
                send_attempts.append(content)
                if len(send_attempts) == 2:
                    raise RuntimeError("discord send timeout")
                return {"id": f"msg-{len(send_attempts)}"}

            svc.discord_send = flaky_send
            svc.find_recent_near_duplicate_event = lambda recent_events, target_ref, item, observed_at, config: None
            svc.log_exception = lambda *args, **kwargs: None

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                state = svc.base_state()
                state["last_service_start_at"] = "2026-04-19T08:00:00+00:00"
                store.save_state(state)
                executor = FakeExecutor()
                target = {
                    "key": "list1",
                    "mode": svc.MODE_LIST,
                    "label": "Balanced 1",
                    "name": "Balanced 1",
                    "url": "https://x.com/i/lists/2045764486196592926",
                    "list_index": 1,
                }
                items = [
                    {
                        "tweet_id": "tweet-ok",
                        "created_at": "2026-04-19T08:10:00+00:00",
                        "status_url": "https://x.com/test/status/tweet-ok",
                        "handle": "testhandle",
                        "text": "First item should not duplicate",
                        "is_repost": False,
                        "repost_context": "",
                        "is_filtered_repost": False,
                        "repost_filter_reason": "",
                        "is_teaser": False,
                        "has_image": False,
                        "has_video": False,
                        "has_external_link": False,
                    },
                    {
                        "tweet_id": "tweet-fail",
                        "created_at": "2026-04-19T08:10:01+00:00",
                        "status_url": "https://x.com/test/status/tweet-fail",
                        "handle": "testhandle",
                        "text": "Second item should retry later",
                        "is_repost": False,
                        "repost_context": "",
                        "is_filtered_repost": False,
                        "repost_filter_reason": "",
                        "is_teaser": False,
                        "has_image": False,
                        "has_video": False,
                        "has_external_link": False,
                    },
                ]

                delivered = svc.handle_new_items(
                    store,
                    svc.base_config(),
                    executor,
                    target,
                    items,
                    "2026-04-19T08:11:00+00:00",
                )
                state_after_failure = store.load_state()

                delivered_retry = svc.handle_new_items(
                    store,
                    svc.base_config(),
                    executor,
                    target,
                    items,
                    "2026-04-19T08:11:30+00:00",
                )
                state_after_retry = store.load_state()

            self.assertEqual(delivered, ["tweet-ok"])
            self.assertIn("tweet-ok", state_after_failure["seen_ids"])
            self.assertNotIn("tweet-fail", state_after_failure["seen_ids"])
            self.assertEqual(delivered_retry, ["tweet-fail"])
            self.assertEqual([entry["tweet_id"] for entry in state_after_retry["recent_events"]], ["tweet-ok", "tweet-fail"])
        finally:
            svc.discord_send = original_discord_send
            svc.find_recent_near_duplicate_event = original_find_recent_near_duplicate_event
            svc.log_exception = original_log_exception

    def test_build_initial_delivery_draft_uses_local_fast_translation_when_available(self):
        original_fetch_local_fast_translation = svc.fetch_local_fast_translation
        try:
            svc.fetch_local_fast_translation = lambda config, text, limit=1400, initial_delivery=False: {
                "ok": True,
                "translation": "这是首发机翻",
                "same_as_source": False,
                "draft_model": "local-mt-test-model",
                "draft_provider": "local_fast_translation",
                "draft_ready_at": "2026-04-19T16:00:01+00:00",
            }
            config = svc.base_config()
            config["local_fast_translation_enabled"] = True
            item = {
                "text": "Original source text for immediate machine translation",
                "source_full_text": "Original source text for immediate machine translation",
            }

            draft = svc.build_initial_delivery_draft(config, item)

            self.assertEqual(draft["draft_status"], "machine")
            self.assertEqual(draft["translation"], "这是首发机翻")
            self.assertEqual(draft["draft_provider"], "local_fast_translation")
            self.assertFalse(draft["skip_async_enrich"])
            self.assertTrue(draft["initial_machine_translation_ready"])
        finally:
            svc.fetch_local_fast_translation = original_fetch_local_fast_translation

    def test_build_initial_delivery_draft_falls_back_to_pending_when_local_fast_translation_fails(self):
        original_fetch_local_fast_translation = svc.fetch_local_fast_translation
        try:
            svc.fetch_local_fast_translation = lambda config, text, limit=1400, initial_delivery=False: {
                "ok": False,
                "error": "local_fast_translation_timeout",
            }
            config = svc.base_config()
            config["local_fast_translation_enabled"] = True
            item = {
                "text": "Original source text for pending fallback",
                "source_full_text": "Original source text for pending fallback",
            }

            draft = svc.build_initial_delivery_draft(config, item)

            self.assertEqual(draft["draft_status"], "pending")
            self.assertIn("Original source text for pending fallback", draft["translation"])
            self.assertEqual(draft["draft_error"], "local_fast_translation_timeout")
            self.assertFalse(draft["initial_machine_translation_ready"])
        finally:
            svc.fetch_local_fast_translation = original_fetch_local_fast_translation

    def test_translate_source_text_prefers_local_fast_translation_before_google(self):
        original_fetch_local_fast_translation = svc.fetch_local_fast_translation
        original_translate_title = svc.translate_title
        try:
            svc.fetch_local_fast_translation = lambda config, text, limit=320, initial_delivery=False: {
                "ok": True,
                "translation": "本地快翻结果",
                "same_as_source": False,
            }
            svc.translate_title = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("google translation should not run when local fast translation succeeds")
            )

            translated = svc.translate_source_text(svc.base_config(), "Original source text")

            self.assertEqual(translated, "本地快翻结果")
        finally:
            svc.fetch_local_fast_translation = original_fetch_local_fast_translation
            svc.translate_title = original_translate_title

    def test_fetch_local_fast_translation_prompts_with_readable_chinese_language(self):
        original_requests_post = svc.requests.post
        captured = {}
        try:
            class FakeResponse:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": "这是一条中文机翻结果。"
                                }
                            }
                        ]
                    }

            def fake_post(*args, **kwargs):
                captured["payload"] = kwargs.get("json")
                return FakeResponse()

            svc.requests.post = fake_post
            config = svc.base_config()
            config["local_fast_translation_enabled"] = True
            config["local_fast_translation_api_base"] = "http://127.0.0.1:9/v1"
            config["local_fast_translation_api_key"] = "local"
            config["local_fast_translation_model"] = "local-mt-test-model"
            config["translate_to"] = "zh-CN"

            result = svc.fetch_local_fast_translation(config, "Original source text", limit=1400)

            self.assertTrue(result["ok"])
            system_prompt = captured["payload"]["messages"][0]["content"]
            self.assertIn("Simplified Chinese", system_prompt)
            self.assertNotIn("zh-CN", system_prompt)
        finally:
            svc.requests.post = original_requests_post

    def test_fetch_local_fast_translation_uses_short_initial_timeout_and_circuit_breaker(self):
        original_requests_post = svc.requests.post
        try:
            captured = {}

            def timeout_post(*args, **kwargs):
                captured["timeout"] = kwargs.get("timeout")
                raise svc.requests.exceptions.Timeout()

            svc.requests.post = timeout_post
            config = svc.base_config()
            config["local_fast_translation_enabled"] = True
            config["local_fast_translation_api_base"] = "http://127.0.0.1:9/v1"
            config["local_fast_translation_api_key"] = "local"
            config["local_fast_translation_model"] = "local-mt-test-model"
            config["local_fast_translation_timeout_seconds"] = 8
            config["local_fast_translation_initial_timeout_seconds"] = 0.5
            config["local_fast_translation_initial_failure_cooldown_seconds"] = 30

            result = svc.fetch_local_fast_translation(config, "Original source text", initial_delivery=True)
            second_result = svc.fetch_local_fast_translation(config, "Another source text", initial_delivery=True)

            self.assertEqual(result["error"], "local_fast_translation_timeout")
            self.assertEqual(captured["timeout"], 0.5)
            self.assertTrue(second_result["error"].startswith("local_fast_translation_circuit_open:"))
        finally:
            svc.requests.post = original_requests_post
            svc.LOCAL_FAST_TRANSLATION_CIRCUIT.update({"key": "", "blocked_until": 0.0, "last_error": ""})

    def test_local_fast_translation_prompt_language_maps_chinese_codes(self):
        self.assertEqual(svc.local_fast_translation_prompt_language("zh-CN"), "Simplified Chinese")
        self.assertEqual(svc.local_fast_translation_prompt_language("zh_TW"), "Traditional Chinese")

    def test_fetch_local_fast_translation_rejects_wrong_target_language_output(self):
        original_requests_post = svc.requests.post
        try:
            class FakeResponse:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": "El texto sigue en español y no fue traducido al chino."
                                }
                            }
                        ]
                    }

            svc.requests.post = lambda *args, **kwargs: FakeResponse()
            config = svc.base_config()
            config["local_fast_translation_enabled"] = True
            config["local_fast_translation_api_base"] = "http://127.0.0.1:9/v1"
            config["local_fast_translation_api_key"] = "local"
            config["local_fast_translation_model"] = "local-mt-test-model"

            result = svc.fetch_local_fast_translation(config, "Texto original en español", limit=1400)

            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "local_fast_translation_target_language_mismatch")
        finally:
            svc.requests.post = original_requests_post

    def test_empty_page_retry_settings_cap_initial_empty_page_cost(self):
        config = svc.base_config()
        config["empty_page_retry_count"] = 10
        config["empty_page_retry_delay_milliseconds"] = 900

        retry_count, retry_delay_ms = svc.empty_page_retry_settings(config, recovery=False)

        self.assertEqual(retry_count, svc.DEFAULT_EMPTY_PAGE_INITIAL_RETRY_COUNT_CAP)
        self.assertEqual(retry_delay_ms, svc.DEFAULT_EMPTY_PAGE_INITIAL_RETRY_DELAY_MILLISECONDS_CAP)

    def test_empty_page_retry_settings_cap_recovery_more_aggressively(self):
        config = svc.base_config()
        config["empty_page_retry_count"] = 10
        config["empty_page_retry_delay_milliseconds"] = 900

        retry_count, retry_delay_ms = svc.empty_page_retry_settings(config, recovery=True)

        self.assertEqual(retry_count, svc.DEFAULT_EMPTY_PAGE_RECOVERY_RETRY_COUNT_CAP)
        self.assertEqual(retry_delay_ms, svc.DEFAULT_EMPTY_PAGE_RECOVERY_RETRY_DELAY_MILLISECONDS_CAP)

    def test_page_settle_milliseconds_caps_recovery_wait(self):
        config = svc.base_config()
        config["empty_page_recovery_settle_milliseconds"] = 2500

        settle_ms = svc.page_settle_milliseconds(config, recovery=True)

        self.assertEqual(settle_ms, svc.DEFAULT_EMPTY_PAGE_RECOVERY_SETTLE_MILLISECONDS_CAP)

    def test_empty_page_priority_recheck_settings_enforce_fast_follow_up(self):
        config = svc.base_config()
        config["empty_page_priority_recheck_count"] = 1
        config["empty_page_priority_recheck_delay_milliseconds"] = 3000

        recheck_count, recheck_delay_ms = svc.empty_page_priority_recheck_settings(config)

        self.assertEqual(recheck_count, svc.DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_COUNT)
        self.assertEqual(recheck_delay_ms, svc.DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_DELAY_MILLISECONDS)

    def test_should_trigger_multi_target_empty_page_restart_for_wave(self):
        config = svc.base_config()

        self.assertTrue(
            svc.should_trigger_multi_target_empty_page_restart(
                ["list1", "list2", "list3"],
                total_targets=3,
                config=config,
            )
        )
        self.assertFalse(
            svc.should_trigger_multi_target_empty_page_restart(
                ["list1", "list2"],
                total_targets=3,
                config=config,
            )
        )
        self.assertFalse(
            svc.should_trigger_multi_target_empty_page_restart(
                ["list1", "list2"],
                total_targets=1,
                config=config,
            )
        )

    def test_should_trigger_multi_target_empty_page_restart_can_be_overridden_lower(self):
        config = svc.base_config()
        config["multi_target_empty_page_restart_threshold"] = 2

        self.assertTrue(
            svc.should_trigger_multi_target_empty_page_restart(
                ["list1", "list2"],
                total_targets=3,
                config=config,
            )
        )

    def test_should_trigger_multi_target_empty_page_restart_respects_cooldown(self):
        config = svc.base_config()
        config["empty_page_wave_recovery_cooldown_seconds"] = 180
        state = {
            "recent_events": [
                {
                    "event_type": "empty_page_wave_auto_recover",
                    "at": "2026-05-03T07:00:00+00:00",
                }
            ]
        }

        self.assertFalse(
            svc.should_trigger_multi_target_empty_page_restart(
                ["list1", "list2", "list3"],
                total_targets=3,
                config=config,
                state=state,
                observed_at="2026-05-03T07:01:00+00:00",
            )
        )
        self.assertTrue(
            svc.should_trigger_multi_target_empty_page_restart(
                ["list1", "list2", "list3"],
                total_targets=3,
                config=config,
                state=state,
                observed_at="2026-05-03T07:03:01+00:00",
            )
        )

    def test_should_restart_after_fast_reopen_empty_rebuilds_after_all_configured_targets_fail(self):
        config = svc.base_config()

        self.assertFalse(
            svc.should_restart_after_fast_reopen_empty(
                ["list1"],
                total_targets=3,
                config=config,
            )
        )
        self.assertFalse(
            svc.should_restart_after_fast_reopen_empty(
                ["list1", "list2"],
                total_targets=3,
                config=config,
            )
        )
        self.assertTrue(
            svc.should_restart_after_fast_reopen_empty(
                ["list1", "list2", "list3"],
                total_targets=3,
                config=config,
            )
        )

    def test_classify_runtime_restart_error_ignores_empty_page_wave(self):
        self.assertEqual(
            svc.classify_runtime_restart_error("persistent empty page wave on the configured list1,list2 pages"),
            "",
        )

    def test_classify_page_surface_loading_shell(self):
        page = FakePage(
            url="https://x.com/i/lists/123",
            counts={
                'a[href="/home"]': 1,
                '[role="progressbar"]': 1,
            },
            body_text="Loading timeline...",
        )

        surface = svc.classify_page_surface_state(page)

        self.assertEqual(surface["state"], "loading_shell")
        self.assertEqual(surface["reason"], "authenticated_shell_loading_signals_present")
        self.assertIn("progressbar", surface["signals"])

    def test_classify_page_surface_hard_empty(self):
        page = FakePage(
            url="https://x.com/i/lists/123",
            counts={'a[href="/home"]': 1},
            body_text="Nothing useful here",
        )

        surface = svc.classify_page_surface_state(page)

        self.assertEqual(surface["state"], "hard_empty")
        self.assertEqual(surface["reason"], "no_visible_timeline_items_after_auth_and_loading_checks")

    def test_classify_page_surface_auth_issue(self):
        page = FakePage(url="https://x.com/i/flow/login")

        surface = svc.classify_page_surface_state(page)

        self.assertEqual(surface["state"], "auth_issue")
        self.assertEqual(surface["reason"], "login_required")

    def test_detect_partial_page_regression(self):
        items = [
            {
                "tweet_id": "1",
                "created_at": "2026-04-18T05:00:00+00:00",
                "status_url": "https://x.com/test/status/1",
                "handle": "test",
                "is_repost": False,
                "is_teaser": False,
            }
        ]
        target = {"key": "list2", "mode": svc.MODE_LIST, "label": "权威信息源"}
        state = {
            "recent_checks": [
                {
                    "target_key": "list2",
                    "at": "2026-04-18T05:05:00+00:00",
                    "visible_count": 4,
                    "top_created_at": "2026-04-18T05:05:00+00:00",
                }
            ],
            "recent_events": [],
        }

        partial = svc.detect_partial_page(items, target, svc.base_config(), state=state, observed_at="2026-04-18T05:10:00+00:00")

        self.assertIn("visible_count_regressed", partial["reason"])
        self.assertEqual(partial["visible_count"], 1)

    def test_visible_items_from_items_keeps_high_signal_reposts(self):
        items = [
            {"tweet_id": "repost-1", "is_repost": True, "is_teaser": False, "has_video": True},
            {"tweet_id": "normal-1", "is_repost": False, "is_teaser": False},
            {"tweet_id": "teaser-1", "is_repost": False, "is_teaser": True},
        ]
        target = {
            "key": "list3",
            "mode": svc.MODE_LIST,
            "label": "官方组织",
            "name": "官方组织",
            "url": "https://x.com/i/lists/2045059136174653812",
            "list_index": 3,
        }

        visible = svc.visible_items_from_items(items)
        snapshot = svc.build_check_snapshot(items, "2026-04-18T05:10:00+00:00", target)

        self.assertEqual([item["tweet_id"] for item in visible], ["repost-1", "normal-1"])
        self.assertEqual(snapshot["visible_count"], 2)
        self.assertEqual(snapshot["repost_filtered_count"], 0)
        self.assertEqual(snapshot["repost_candidate_count"], 1)
        self.assertEqual(snapshot["filtered_candidate_count"], 1)
        self.assertEqual(svc.x_banner_line_for_item(items[0]), "━━【X监控推送】（转帖、视频）━━")

    def test_visible_items_from_items_filters_low_signal_reposts(self):
        items = [
            {"tweet_id": "repost-1", "is_repost": True, "is_teaser": False, "text": "Nice."},
            {"tweet_id": "normal-1", "is_repost": False, "is_teaser": False, "text": "Normal post"},
        ]
        target = {
            "key": "list3",
            "mode": svc.MODE_LIST,
            "label": "官方组织",
            "name": "官方组织",
            "url": "https://x.com/i/lists/2045059136174653812",
            "list_index": 3,
        }

        visible = svc.visible_items_from_items(items)
        snapshot = svc.build_check_snapshot(items, "2026-04-18T05:10:00+00:00", target)

        self.assertEqual([item["tweet_id"] for item in visible], ["normal-1"])
        self.assertEqual(snapshot["repost_filtered_count"], 1)
        self.assertEqual(snapshot["repost_candidate_count"], 1)
        self.assertEqual(snapshot["filtered_candidate_count"], 1)

    def test_handle_new_items_allows_high_signal_reposts(self):
        original_discord_send = svc.discord_send
        original_find_recent_near_duplicate_event = svc.find_recent_near_duplicate_event
        try:
            svc.discord_send = lambda config, content: {"id": "msg-1"}
            svc.find_recent_near_duplicate_event = lambda recent_events, target_ref, item, observed_at, config: None

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                state = svc.base_state()
                state["last_service_start_at"] = "2026-04-18T05:00:00+00:00"
                store.save_state(state)
                executor = FakeExecutor()
                target = {
                    "key": "list3",
                    "mode": svc.MODE_LIST,
                    "label": "官方组织",
                    "name": "官方组织",
                    "url": "https://x.com/i/lists/2045059136174653812",
                    "list_index": 3,
                }
                items = [
                    {
                        "tweet_id": "repost-1",
                        "created_at": "2026-04-18T05:10:00+00:00",
                        "status_url": "https://x.com/test/status/repost-1",
                        "handle": "testhandle",
                        "text": "Interesting repost",
                        "is_repost": True,
                        "repost_filter_reason": "",
                        "is_filtered_repost": False,
                        "is_teaser": False,
                        "has_image": False,
                        "has_video": True,
                        "has_external_link": False,
                    }
                ]

                delivered = svc.handle_new_items(
                    store,
                    svc.base_config(),
                    executor,
                    target,
                    items,
                    "2026-04-18T05:11:00+00:00",
                )
                latest_state = store.load_state()

            self.assertEqual(delivered, ["repost-1"])
            self.assertEqual(latest_state["recent_events"][-1]["tweet_id"], "repost-1")
            self.assertEqual(latest_state["recent_events"][-1]["target_name"], "官方组织")
            self.assertEqual(latest_state["recent_events"][-1]["draft_status"], "pending")
            self.assertEqual(len(executor.submissions), 1)
        finally:
            svc.discord_send = original_discord_send
            svc.find_recent_near_duplicate_event = original_find_recent_near_duplicate_event

    def test_handle_new_items_filters_low_signal_reposts(self):
        original_discord_send = svc.discord_send
        try:
            sent_payloads = []
            svc.discord_send = lambda config, content: sent_payloads.append(content) or {"id": "msg-1"}

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                state = svc.base_state()
                state["last_service_start_at"] = "2026-04-18T05:00:00+00:00"
                store.save_state(state)
                executor = FakeExecutor()
                target = {
                    "key": "list3",
                    "mode": svc.MODE_LIST,
                    "label": "官方组织",
                    "name": "官方组织",
                    "url": "https://x.com/i/lists/2045059136174653812",
                    "list_index": 3,
                }
                items = [
                    {
                        "tweet_id": "repost-1",
                        "created_at": "2026-04-18T05:10:00+00:00",
                        "status_url": "https://x.com/test/status/repost-1",
                        "handle": "testhandle",
                        "text": "Nice.",
                        "is_repost": True,
                        "repost_filter_reason": "low_signal_repost_without_media_or_meaningful_text",
                        "is_filtered_repost": True,
                        "is_teaser": False,
                        "has_image": False,
                        "has_video": False,
                        "has_external_link": False,
                    }
                ]

                delivered = svc.handle_new_items(
                    store,
                    svc.base_config(),
                    executor,
                    target,
                    items,
                    "2026-04-18T05:11:00+00:00",
                )

            self.assertEqual(delivered, [])
            self.assertEqual(sent_payloads, [])
        finally:
            svc.discord_send = original_discord_send

    def test_classify_runtime_restart_error_recognizes_restartable_conditions(self):
        self.assertEqual(
            svc.classify_runtime_restart_error("Target page, context or browser has been closed"),
            "browser_crashed",
        )
        self.assertEqual(
            svc.classify_runtime_restart_error("Page.evaluate: Connection closed while reading from the driver"),
            "browser_crashed",
        )
        self.assertEqual(
            svc.classify_runtime_restart_error("BrowserContext.new_page: Connection closed while reading from the driver"),
            "browser_crashed",
        )
        self.assertEqual(
            svc.classify_runtime_restart_error("persistent empty page on the configured 权威信息源 page"),
            "",
        )
        self.assertEqual(
            svc.classify_runtime_restart_error("persistent partial page on the configured 权威信息源 page"),
            "",
        )

    def test_classify_runtime_restart_error_ignores_transient_navigation_failures(self):
        transient_messages = [
            "Page.goto: net::ERR_CONNECTION_CLOSED at https://x.com/i/lists/123",
            "Page.goto: Timeout 30000ms exceeded. Call log: navigating to \"https://x.com/i/lists/123\"",
            "Page.reload: net::ERR_CONNECTION_CLOSED",
        ]

        for message in transient_messages:
            with self.subTest(message=message):
                self.assertEqual(svc.classify_runtime_restart_error(message), "")
                self.assertTrue(svc.is_transient_page_navigation_error(message))

    def test_record_target_navigation_error_appends_target_check_without_bootstrap(self):
        target = {
            "key": "list2",
            "mode": svc.MODE_LIST,
            "label": "权威信息源",
            "name": "权威信息源",
            "url": "https://x.com/i/lists/2043934078009999426",
            "list_index": 2,
        }

        with temporary_test_dir() as tmpdir:
            store = svc.Store(root=tmpdir)
            state = svc.base_state()
            store.save_state(state)
            svc.record_target_navigation_error(
                store,
                "list2",
                target,
                "2026-05-03T07:40:00+00:00",
                "startup_navigation_failed: Page.goto: net::ERR_CONNECTION_CLOSED",
                "startup_navigation",
            )
            latest_state = store.load_state()

        self.assertEqual(latest_state["targets"]["list2"]["last_error"], "startup_navigation_failed: Page.goto: net::ERR_CONNECTION_CLOSED")
        self.assertEqual(latest_state["last_error"], "startup_navigation_failed: Page.goto: net::ERR_CONNECTION_CLOSED")
        self.assertEqual(latest_state["recent_checks"][-1]["target_key"], "list2")
        self.assertEqual(latest_state["recent_checks"][-1]["navigation_phase"], "startup_navigation")
        self.assertTrue(latest_state["recent_checks"][-1]["navigation_error"])
        self.assertTrue(latest_state["recent_checks"][-1]["navigation_error_transient"])
        self.assertEqual(latest_state["recent_checks"][-1]["visible_count"], 0)

    def test_auto_recover_target_page_reopens_only_target_page(self):
        current_page = FakePage(url="https://x.com/i/lists/old")
        new_page = FakePage(url="https://x.com/i/lists/new")
        context = FakeContext(new_page)
        target = {
            "key": "list2",
            "mode": svc.MODE_LIST,
            "label": "权威信息源",
            "name": "权威信息源",
            "url": "https://x.com/i/lists/2043934078009999426",
            "list_index": 2,
        }
        pages = {"list2": current_page}
        config = svc.base_config()

        with temporary_test_dir() as tmpdir:
            store = svc.Store(root=tmpdir)
            recovered_page, meta = svc.auto_recover_target_page(
                context,
                pages,
                "list2",
                target,
                current_page,
                config,
                store,
                reason="persistent_empty_page",
            )
            state = store.load_state()

        self.assertIs(recovered_page, new_page)
        self.assertIs(pages["list2"], new_page)
        self.assertTrue(current_page.closed)
        self.assertEqual(meta["recovery_scope"], "page")
        self.assertEqual(state["recent_events"][-1]["event_type"], "target_page_auto_recover")
        self.assertEqual(state["recent_events"][-1]["recovery_scope"], "page")

    def test_recover_multi_target_empty_page_wave_rebuilds_pages_without_service_restart(self):
        original_collect_target_items = svc.collect_target_items
        try:
            svc.collect_target_items = lambda *args, **kwargs: ([], {})
            list1_old = FakePage(url="https://x.com/i/lists/list1-old")
            list2_old = FakePage(url="https://x.com/i/lists/list2-old")
            list1_new = FakePage(url="https://x.com/i/lists/list1-new")
            list2_new = FakePage(url="https://x.com/i/lists/list2-new")

            class WaveContext:
                def __init__(self, pages):
                    self.pages = list(pages)
                    self.calls = 0

                def new_page(self):
                    page = self.pages[self.calls]
                    self.calls += 1
                    return page

            context = WaveContext([list1_new, list2_new])
            pages = {"list1": list1_old, "list2": list2_old}
            targets = [
                {
                    "key": "list1",
                    "mode": svc.MODE_LIST,
                    "label": "监控均衡1",
                    "name": "监控均衡1",
                    "url": "https://x.com/i/lists/list1",
                    "list_index": 1,
                },
                {
                    "key": "list2",
                    "mode": svc.MODE_LIST,
                    "label": "监控均衡2",
                    "name": "监控均衡2",
                    "url": "https://x.com/i/lists/list2",
                    "list_index": 2,
                },
            ]
            config = svc.base_config()
            config["empty_page_wave_canary_enabled"] = False

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                result = svc.recover_multi_target_empty_page_wave(
                    context,
                    pages,
                    targets,
                    ["list1", "list2"],
                    config,
                    store,
                )
                state = store.load_state()

            self.assertEqual(result["recovered_targets"], ["list1", "list2"])
            self.assertEqual(result["rebuilt_targets"], ["list1", "list2"])
            self.assertEqual(result["failed_targets"], [])
            self.assertIs(pages["list1"], list1_new)
            self.assertIs(pages["list2"], list2_new)
            self.assertTrue(list1_old.closed)
            self.assertTrue(list2_old.closed)
            self.assertIn(svc.DEFAULT_EMPTY_PAGE_WAVE_PROBE_WAIT_MILLISECONDS, list1_old.waits)
            self.assertIn(svc.DEFAULT_EMPTY_PAGE_WAVE_PROBE_WAIT_MILLISECONDS, list2_old.waits)
            self.assertEqual(state["recent_events"][-1]["event_type"], "empty_page_wave_auto_recover")
            self.assertEqual(state["recent_events"][-1]["recovery_scope"], "wave")
            self.assertEqual(state["recent_events"][-1]["recovery_action"], "page_rebuild")
        finally:
            svc.collect_target_items = original_collect_target_items

    def test_recover_multi_target_empty_page_wave_canary_backoff_avoids_rebuild(self):
        original_collect_target_items = svc.collect_target_items
        try:
            svc.collect_target_items = lambda *args, **kwargs: ([], {})
            list1_old = FakePage(url="https://x.com/i/lists/list1-old")
            list2_old = FakePage(url="https://x.com/i/lists/list2-old")
            list1_new = FakePage(url="https://x.com/i/lists/list1-new")

            context = FakeContext(list1_new)
            pages = {"list1": list1_old, "list2": list2_old}
            targets = [
                {
                    "key": "list1",
                    "mode": svc.MODE_LIST,
                    "label": "Monitor 1",
                    "name": "Monitor 1",
                    "url": "https://x.com/i/lists/list1",
                    "list_index": 1,
                },
                {
                    "key": "list2",
                    "mode": svc.MODE_LIST,
                    "label": "Monitor 2",
                    "name": "Monitor 2",
                    "url": "https://x.com/i/lists/list2",
                    "list_index": 2,
                },
            ]
            config = svc.base_config()
            config["empty_page_wave_canary_enabled"] = True
            config["empty_page_wave_canary_wait_milliseconds"] = 1200

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                result = svc.recover_multi_target_empty_page_wave(
                    context,
                    pages,
                    targets,
                    ["list1", "list2"],
                    config,
                    store,
                )
                state = store.load_state()

            self.assertEqual(result["action"], "canary_backoff")
            self.assertEqual(result["recovered_targets"], [])
            self.assertEqual(result["rebuilt_targets"], [])
            self.assertEqual(context.new_page_calls, 0)
            self.assertIs(pages["list1"], list1_old)
            self.assertIs(pages["list2"], list2_old)
            self.assertFalse(list1_old.closed)
            self.assertFalse(list2_old.closed)
            self.assertEqual(state["recent_events"][-1]["event_type"], "empty_page_wave_auto_recover")
            self.assertEqual(state["recent_events"][-1]["recovery_action"], "canary_backoff")
            self.assertEqual(state["recent_events"][-1]["canary_wait_milliseconds"], 1200)
        finally:
            svc.collect_target_items = original_collect_target_items

    def test_reload_interval_jitter_is_stable_per_slot_and_target(self):
        config = svc.base_config()
        config["source_slot"] = "2"
        config["port"] = 8798
        config["reload_interval_jitter_seconds"] = 20
        target = {"key": "list1", "url": "https://x.com/i/lists/list1"}

        first = svc.reload_interval_jitter_seconds(config, target)
        second = svc.reload_interval_jitter_seconds(config, target)
        self.assertEqual(first, second)
        self.assertGreaterEqual(first, 0)
        self.assertLessEqual(first, 20)
        self.assertEqual(svc.target_reload_due_seconds(config, target, 45), 45 + first)

    def test_fast_reopen_and_collect_target_page_rechecks_new_page_immediately(self):
        original_collect_target_items = svc.collect_target_items
        try:
            old_page = FakePage(url="https://x.com/i/lists/old")
            new_page = FakePage(url="https://x.com/i/lists/new")
            context = FakeContext(new_page)
            pages = {"list2": old_page}
            target = {
                "key": "list2",
                "mode": svc.MODE_LIST,
                "label": "Balanced 2",
                "name": "Balanced 2",
                "url": "https://x.com/i/lists/2045766641817162232",
                "list_index": 2,
            }
            calls = []

            def fake_collect_target_items(page, *args, **kwargs):
                calls.append(page)
                return [{"tweet_id": "fresh-after-reopen"}], {"empty_page_retries_used": 0}

            svc.collect_target_items = fake_collect_target_items

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                recovered_page, items, meta = svc.fast_reopen_and_collect_target_page(
                    context,
                    pages,
                    "list2",
                    target,
                    old_page,
                    svc.base_config(),
                    store,
                    reason="empty_page_fast_reopen",
                )
                state = store.load_state()

            self.assertIs(recovered_page, new_page)
            self.assertIs(pages["list2"], new_page)
            self.assertTrue(old_page.closed)
            self.assertEqual([item["tweet_id"] for item in items], ["fresh-after-reopen"])
            self.assertEqual(calls, [new_page])
            self.assertEqual(meta["steps"], ["page_auto_recover", "post_reopen_collect"])
            self.assertEqual(state["recent_events"][-1]["event_type"], "target_page_auto_recover")
            self.assertEqual(state["recent_events"][-1]["reason"], "empty_page_fast_reopen")
        finally:
            svc.collect_target_items = original_collect_target_items

    def test_full_reload_and_collect_target_page_rechecks_same_page_immediately(self):
        original_collect_target_items = svc.collect_target_items
        try:
            page = FakePage(url="https://x.com/i/lists/current")
            target = {
                "key": "list2",
                "mode": svc.MODE_LIST,
                "label": "Balanced 2",
                "name": "Balanced 2",
                "url": "https://x.com/i/lists/2045766641817162232",
                "list_index": 2,
            }
            calls = []

            def fake_collect_target_items(reloaded_page, *args, **kwargs):
                calls.append(reloaded_page)
                return [{"tweet_id": "fresh-after-reload"}], {"empty_page_retries_used": 0}

            svc.collect_target_items = fake_collect_target_items

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                recovered_page, items, meta = svc.full_reload_and_collect_target_page(
                    page,
                    "list2",
                    target,
                    svc.base_config(),
                    store,
                    reason="stale_refresh_full_reload",
                )
                state = store.load_state()

            self.assertIs(recovered_page, page)
            self.assertEqual(len(page.reload_calls), 1)
            self.assertEqual([item["tweet_id"] for item in items], ["fresh-after-reload"])
            self.assertEqual(calls, [page])
            self.assertEqual(meta["steps"], ["reload", "post_reload_collect"])
            self.assertEqual(state["recent_events"][-1]["event_type"], "target_page_auto_recover")
            self.assertEqual(state["recent_events"][-1]["reason"], "stale_refresh_full_reload")
        finally:
            svc.collect_target_items = original_collect_target_items

    def test_empty_page_recovery_priority_rechecks_same_target_before_giving_up(self):
        original_reload_target_page = svc.reload_target_page
        original_reopen_target_page = svc.reopen_target_page
        original_collect_target_items = svc.collect_target_items
        try:
            page = FakePage(url="https://x.com/i/lists/old")
            context = FakeContext(page)
            target = {
                "key": "list2",
                "mode": svc.MODE_LIST,
                "label": "Balanced 2",
                "name": "Balanced 2",
                "url": "https://x.com/i/lists/2045766641817162232",
                "list_index": 2,
            }
            collect_calls = {"count": 0}

            svc.reload_target_page = lambda current_page, *args, **kwargs: (current_page, "2026-04-23T00:00:00+00:00")
            svc.reopen_target_page = lambda current_context, current_page, *args, **kwargs: (current_page, "2026-04-23T00:00:01+00:00")

            def fake_collect_target_items(*args, **kwargs):
                collect_calls["count"] += 1
                if collect_calls["count"] < 3:
                    return [], {}
                return [{"tweet_id": "late-visible"}], {}

            svc.collect_target_items = fake_collect_target_items

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                recovered_page, items, meta = svc.recover_items_from_empty_page(
                    context,
                    {"list2": page},
                    "list2",
                    target,
                    page,
                    svc.base_config(),
                    store,
                )

            self.assertIs(recovered_page, page)
            self.assertEqual([item["tweet_id"] for item in items], ["late-visible"])
            self.assertIn("priority_recheck", meta["steps"])
            self.assertEqual(meta["priority_rechecks_used"], 1)
            self.assertIn(svc.DEFAULT_EMPTY_PAGE_PRIORITY_RECHECK_DELAY_MILLISECONDS, page.waits)
        finally:
            svc.reload_target_page = original_reload_target_page
            svc.reopen_target_page = original_reopen_target_page
            svc.collect_target_items = original_collect_target_items

    def test_enrich_and_edit_applies_async_machine_translation_when_editor_disabled(self):
        original_build_machine_translation_draft = svc.build_machine_translation_draft
        original_discord_edit = svc.discord_edit
        try:
            edited_payloads = []
            svc.build_machine_translation_draft = lambda store, config, item: {
                "translation": "translated asynchronously",
                "machine_translated_text": "translated asynchronously",
                "draft_status": "machine",
                "draft_model": "test-machine",
                "draft_provider": "test-provider",
                "draft_ready_at": "2026-04-19T08:11:05+00:00",
                "draft_error": "",
                "machine_translation_same_as_source": False,
                "skip_async_enrich": False,
            }
            svc.discord_edit = lambda config, message_id, content: edited_payloads.append(content) or {"id": message_id}

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                state = svc.base_state()
                state["recent_events"] = [
                    {
                        "tweet_id": "tweet-1",
                        "target_key": "list1",
                        "translated_text": "Original source text",
                        "draft_status": "pending",
                    }
                ]
                store.save_state(state)
                config = svc.base_config()
                config["editor_draft_enabled"] = False
                item = {
                    "tweet_id": "tweet-1",
                    "created_at": "2026-04-19T08:10:00+00:00",
                    "status_url": "https://x.com/test/status/tweet-1",
                    "handle": "testhandle",
                    "text": "Original source text",
                    "source_full_text": "Original source text",
                }

                svc.enrich_and_edit(store, config, item, "msg-1", "2026-04-19T08:11:00+00:00")
                latest_state = store.load_state()

            self.assertEqual(len(edited_payloads), 1)
            self.assertIn("translated asynchronously", edited_payloads[0])
            self.assertIn("状态：机翻", edited_payloads[0])
            self.assertEqual(latest_state["recent_events"][-1]["draft_status"], "machine")
            self.assertEqual(latest_state["recent_events"][-1]["translated_text"], "translated asynchronously")
        finally:
            svc.build_machine_translation_draft = original_build_machine_translation_draft
            svc.discord_edit = original_discord_edit

    def test_enrich_and_edit_skips_rebuilding_machine_translation_when_initial_machine_translation_is_ready(self):
        original_build_machine_translation_draft = svc.build_machine_translation_draft
        original_fetch_editor_draft_with_backoff = svc.fetch_editor_draft_with_backoff
        original_discord_edit = svc.discord_edit
        try:
            edited_payloads = []

            def fail_if_called(*args, **kwargs):
                raise AssertionError("machine translation should not be rebuilt after initial local fast translation")

            svc.build_machine_translation_draft = fail_if_called
            svc.fetch_editor_draft_with_backoff = lambda store, config, item: {
                "ok": True,
                "draft": {
                    "translation": "最终熟肉",
                    "draft_model": "editor-model",
                    "draft_provider": "primary",
                    "draft_ready_at": "2026-04-19T08:11:06+00:00",
                    "draft_error": "",
                },
            }
            svc.discord_edit = lambda config, message_id, content: edited_payloads.append(content) or {"id": message_id}

            with temporary_test_dir() as tmpdir:
                store = svc.Store(root=tmpdir)
                state = svc.base_state()
                state["recent_events"] = [
                    {
                        "tweet_id": "tweet-1",
                        "target_key": "list1",
                        "translated_text": "首发机翻",
                        "draft_status": "machine",
                    }
                ]
                store.save_state(state)
                config = svc.base_config()
                item = {
                    "tweet_id": "tweet-1",
                    "created_at": "2026-04-19T08:10:00+00:00",
                    "status_url": "https://x.com/test/status/tweet-1",
                    "handle": "testhandle",
                    "text": "Original source text",
                    "source_full_text": "Original source text",
                    "initial_machine_translation_ready": True,
                    "machine_translated_text": "首发机翻",
                }

                svc.enrich_and_edit(store, config, item, "msg-1", "2026-04-19T08:11:00+00:00")
                latest_state = store.load_state()

            self.assertEqual(len(edited_payloads), 1)
            self.assertIn("最终熟肉", edited_payloads[0])
            self.assertEqual(latest_state["recent_events"][-1]["draft_status"], "processed")
            self.assertEqual(latest_state["recent_events"][-1]["translated_text"], "最终熟肉")
        finally:
            svc.build_machine_translation_draft = original_build_machine_translation_draft
            svc.fetch_editor_draft_with_backoff = original_fetch_editor_draft_with_backoff
            svc.discord_edit = original_discord_edit

    def test_maybe_schedule_pending_event_recovery_submits_stale_pending_event(self):
        with temporary_test_dir() as tmpdir:
            store = svc.Store(root=tmpdir)
            state = svc.base_state()
            state["recent_events"] = [
                {
                    "tweet_id": "tweet-1",
                    "message_id": "msg-1",
                    "url": "https://x.com/test/status/tweet-1",
                    "handle": "testhandle",
                    "created_at": "2026-04-19T08:10:00+00:00",
                    "original_text": "Original source text",
                    "source_title_text": "Original source text",
                    "source_body_text": "",
                    "source_full_text": "Original source text",
                    "raw_delivery_at": "2026-04-19T08:11:00+00:00",
                    "delivered_at": "2026-04-19T08:11:00+00:00",
                    "pending_since_at": "2026-04-19T08:11:00+00:00",
                    "draft_status": "pending",
                    "processed_at": "",
                    "pending_recovery_count": 0,
                    "pending_recovery_last_at": "",
                }
            ]
            store.save_state(state)
            executor = FakeExecutor()

            result = svc.maybe_schedule_pending_event_recovery(
                store,
                svc.base_config(),
                executor,
                observed_at="2026-04-19T08:13:00+00:00",
            )
            latest_state = store.load_state()

        self.assertIsNotNone(result)
        self.assertEqual(result["tweet_id"], "tweet-1")
        self.assertEqual(len(executor.submissions), 1)
        args, kwargs = executor.submissions[0]
        self.assertEqual(args[0], svc.enrich_and_edit)
        self.assertEqual(args[3]["status_url"], "https://x.com/test/status/tweet-1")
        self.assertEqual(args[4], "msg-1")
        self.assertEqual(latest_state["recent_events"][-1]["pending_recovery_count"], 1)
        self.assertTrue(latest_state["recent_events"][-1]["pending_recovery_last_at"])

    def test_maybe_schedule_pending_event_recovery_skips_fresh_pending_event(self):
        with temporary_test_dir() as tmpdir:
            store = svc.Store(root=tmpdir)
            state = svc.base_state()
            state["recent_events"] = [
                {
                    "tweet_id": "tweet-1",
                    "message_id": "msg-1",
                    "url": "https://x.com/test/status/tweet-1",
                    "handle": "testhandle",
                    "created_at": "2026-04-19T08:10:00+00:00",
                    "original_text": "Original source text",
                    "source_title_text": "Original source text",
                    "source_body_text": "",
                    "source_full_text": "Original source text",
                    "raw_delivery_at": "2026-04-19T08:11:30+00:00",
                    "delivered_at": "2026-04-19T08:11:30+00:00",
                    "pending_since_at": "2026-04-19T08:11:30+00:00",
                    "draft_status": "pending",
                    "processed_at": "",
                    "pending_recovery_count": 0,
                    "pending_recovery_last_at": "",
                }
            ]
            store.save_state(state)
            executor = FakeExecutor()

            result = svc.maybe_schedule_pending_event_recovery(
                store,
                svc.base_config(),
                executor,
                observed_at="2026-04-19T08:12:00+00:00",
            )

        self.assertIsNone(result)
        self.assertEqual(len(executor.submissions), 0)

    def test_event_archive_records_delivery_and_update(self):
        with temporary_test_dir() as tmpdir:
            store = svc.Store(root=tmpdir)
            event = {
                "tweet_id": "tweet-archive-1",
                "target_key": "list1",
                "message_id": "msg-archive-1",
                "delay_seconds": 93,
                "draft_status": "pending",
            }

            svc.remember_event(store, event)
            svc.update_event(store, "tweet-archive-1", {"draft_status": "processed"})

            archive_path = Path(tmpdir) / svc.EVENT_ARCHIVE_FILENAME
            records = [
                json.loads(line)
                for line in archive_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual([record["archive_event_type"] for record in records], ["delivery", "update"])
        self.assertEqual(records[0]["delay_seconds"], 93)
        self.assertEqual(records[0]["draft_status"], "pending")
        self.assertEqual(records[1]["draft_status"], "processed")
        self.assertTrue(records[1]["archived_at"])

    def test_check_archive_records_recent_check(self):
        with temporary_test_dir() as tmpdir:
            store = svc.Store(root=tmpdir)
            check = {
                "at": "2026-04-20T22:21:31+00:00",
                "target_key": "list1",
                "target_name": "xplus2-match-1",
                "current_top_tweet_id": "tweet-check-1",
                "top_delay_seconds": 40,
                "page_surface_state": "loading_shell",
                "page_surface_reason": "authenticated_shell_loading_signals_present",
                "soft_recovery_action": "wait,zero_item_scroll,reload",
            }

            svc.append_recent_check(store, check)

            archive_path = Path(tmpdir) / svc.CHECK_ARCHIVE_FILENAME
            records = [
                json.loads(line)
                for line in archive_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            latest_state = store.load_state()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["archive_record_type"], "check")
        self.assertEqual(records[0]["page_surface_state"], "loading_shell")
        self.assertEqual(records[0]["soft_recovery_action"], "wait,zero_item_scroll,reload")
        self.assertEqual(latest_state["recent_checks"][-1]["current_top_tweet_id"], "tweet-check-1")

    def test_atomic_write_text_retries_transient_permission_error(self):
        original_replace = svc.os.replace
        replace_attempts = {"count": 0}

        def flaky_replace(src, dst):
            replace_attempts["count"] += 1
            if replace_attempts["count"] == 1:
                raise PermissionError("temporary lock")
            return original_replace(src, dst)

        try:
            svc.os.replace = flaky_replace
            with temporary_test_dir() as tmpdir:
                target = Path(tmpdir) / "state.json"
                svc.atomic_write_text(target, '{"ok": true}')
                self.assertEqual(target.read_text(encoding="utf-8"), '{"ok": true}')
            self.assertEqual(replace_attempts["count"], 2)
        finally:
            svc.os.replace = original_replace


if __name__ == "__main__":
    unittest.main()
