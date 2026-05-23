import importlib.util
import os
import py_compile
import tempfile
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("x_monitorplus_service.py")


def load_service_module(name, localappdata=None):
    previous_localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata is not None:
        os.environ["LOCALAPPDATA"] = localappdata
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        if spec.loader is None:
            raise RuntimeError("module_loader_missing")
        spec.loader.exec_module(module)
        return module
    finally:
        if localappdata is not None:
            if previous_localappdata is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous_localappdata


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def test_py_compile():
    py_compile.compile(str(SCRIPT_PATH), doraise=True)


def test_invalid_config_write_guards():
    module = load_service_module("xplus_smoke_invalid_config")
    with tempfile.TemporaryDirectory() as root_dir:
        root = Path(root_dir)
        store = module.Store(root)
        broken_text = "{ broken json"
        store.config_path.write_text(broken_text, encoding="utf-8")

        results = {
            "configure": module.configure(store, "x_home_enabled", True),
            "configure_modes": module.apply_mode_change(store, [module.MODE_HOME], True),
            "configure_lists": module.apply_list_change(store, [1], True),
            "switch_slot": module.apply_slot_change(store, "2"),
        }

        for action, payload in results.items():
            assert_true(payload.get("error") == "invalid_config", f"{action} should refuse invalid config")
        assert_true(store.config_path.read_text(encoding="utf-8") == broken_text, "invalid config should remain unchanged")


def test_invalid_x_lists_value_guard():
    module = load_service_module("xplus_smoke_invalid_x_lists")
    with tempfile.TemporaryDirectory() as root_dir:
        root = Path(root_dir)
        store = module.Store(root)
        before = store.config_path.read_text(encoding="utf-8")
        payload = module.configure(store, "x_lists", "{ broken json")
        after = store.config_path.read_text(encoding="utf-8")
        assert_true(payload.get("error") == "invalid_json_value", "invalid x_lists JSON should be rejected")
        assert_true(before == after, "invalid x_lists JSON should not rewrite config")


def test_invalid_state_auto_recovery():
    module = load_service_module("xplus_smoke_invalid_state")
    with tempfile.TemporaryDirectory() as root_dir:
        root = Path(root_dir)
        store = module.Store(root)
        broken_text = "{ broken json"
        store.state_path.write_text(broken_text, encoding="utf-8")

        payload = module.status(store)
        assert_true(payload.get("state_valid") is True, "state should be repaired into a valid shape")
        assert_true(payload.get("state_parse_error", "") == "", "state parse error should not stay active after repair")
        assert_true(bool(payload.get("state_last_recovery_error", "")), "state repair should be visible in status")
        backup_path = payload.get("state_last_recovery_backup_path", "")
        assert_true(bool(backup_path), "state repair should preserve a backup path")
        assert_true(Path(backup_path).exists(), "state repair backup should exist")
        assert_true(Path(backup_path).read_text(encoding="utf-8") == broken_text, "state repair backup should preserve the invalid source")


def test_slot_binding_parse_error_visibility():
    with tempfile.TemporaryDirectory() as localappdata_dir, tempfile.TemporaryDirectory() as root_dir:
        module = load_service_module("xplus_smoke_slot_binding", localappdata=localappdata_dir)
        slot_root = Path(localappdata_dir) / "XMonitorPlus" / "x-monitor-2"
        slot_root.mkdir(parents=True, exist_ok=True)
        (slot_root / "config.json").write_text("{ broken json", encoding="utf-8")

        store = module.Store(root_dir)
        config = store.load_config()
        config["source_slot"] = "2"
        config["x_home_enabled"] = False
        config["x_lists"] = [{"id": "list1", "name": "list1", "url": "https://x.com/i/lists/1", "enabled": True}]
        config["discord_channel_id"] = "1"
        config["discord_bot_token"] = "2"
        store.save_config(config)

        payload = module.status(store)
        assert_true(payload.get("config_valid") is True, "main config should stay valid in slot-binding smoke test")
        assert_true(bool(payload.get("slot_binding", {}).get("config_parse_error", "")), "slot binding parse error should be exposed in status")


def test_legacy_defaults_parse_error_visibility():
    with tempfile.TemporaryDirectory() as localappdata_dir, tempfile.TemporaryDirectory() as root_dir:
        module = load_service_module("xplus_smoke_legacy_defaults", localappdata=localappdata_dir)
        legacy_root = Path(localappdata_dir) / "XMonitorPlus" / "x-monitor"
        legacy_root.mkdir(parents=True, exist_ok=True)
        (legacy_root / "config.json").write_text("{ broken json", encoding="utf-8")

        store = module.Store(root_dir)
        payload = module.status(store)
        legacy_payload = payload.get("legacy_x_monitor_defaults", {})
        assert_true(legacy_payload.get("config_exists") is True, "legacy defaults config should be detected")
        assert_true(legacy_payload.get("config_valid") is False, "legacy defaults config should be marked invalid")
        assert_true(bool(legacy_payload.get("config_parse_error", "")), "legacy defaults parse error should be exposed")


def test_slot_binding_guard_paths():
    with tempfile.TemporaryDirectory() as localappdata_dir, tempfile.TemporaryDirectory() as root_dir:
        module = load_service_module("xplus_smoke_slot_binding_guard", localappdata=localappdata_dir)
        module.discord_send = lambda *args, **kwargs: {"id": "smoke-alert"}
        slot_root = Path(localappdata_dir) / "XMonitorPlus" / "x-monitor-2"
        slot_root.mkdir(parents=True, exist_ok=True)
        (slot_root / "config.json").write_text("{ broken json", encoding="utf-8")

        store = module.Store(root_dir)
        config = store.load_config()
        config["source_slot"] = "2"
        config["x_home_enabled"] = False
        config["x_lists"] = [{"id": "list1", "name": "list1", "url": "https://x.com/i/lists/1", "enabled": True}]
        config["discord_channel_id"] = "1"
        config["discord_bot_token"] = "2"
        store.save_config(config)

        start_payload = module.start_service(store)
        open_profile_payload = module.open_profile(store)
        switch_slot_payload = module.apply_slot_change(store, "2")

        for action, payload in {
            "start": start_payload,
            "open_profile": open_profile_payload,
            "switch_slot": switch_slot_payload,
        }.items():
            assert_true(payload.get("error") == "invalid_slot_binding_config", f"{action} should refuse invalid slot binding config")


def test_request_parser_common_paths():
    module = load_service_module("xplus_smoke_request_parser")
    cases = [
        ("switch to slot 2", {"action": "switch_slot", "slot": "2"}),
        ("switch to slot 3", {"action": "switch_slot", "slot": "3"}),
        ("switch xplus to slot 7", {"action": "switch_slot", "slot": "7"}),
        ("start list monitoring", {"action": "start_modes", "modes": [module.MODE_LIST]}),
        ("stop list 1 and 2", {"action": "stop_lists", "lists": [1, 2]}),
        ("recent 5 events", {"action": "recent", "limit": 5}),
    ]
    for text, expected in cases:
        payload = module.parse_request(text)
        for key, value in expected.items():
            assert_true(payload.get(key) == value, f"request parser mismatch for {text}: expected {key}={value}, got {payload.get(key)}")


def test_new_item_delivery_prioritizes_newest():
    module = load_service_module("xplus_smoke_delivery_order")
    with tempfile.TemporaryDirectory() as root_dir:
        store = module.Store(root_dir)
        sent = []

        def fake_render(item, draft, delivered_at=None):
            return item.get("tweet_id", "")

        def fake_send(config, content):
            sent.append(content)
            return {"id": content}

        def fake_draft(config_obj, item):
            tweet_id = item.get("tweet_id", "")
            return {
                "translation": tweet_id,
                "machine_translated_text": tweet_id,
                "draft_status": "machine",
                "draft_model": "",
                "draft_provider": "",
                "draft_ready_at": "",
                "draft_error": "",
                "machine_translation_same_as_source": False,
                "initial_editor_fallback_used": False,
                "emoji_passthrough_used": False,
                "skip_async_enrich": True,
            }

        class RecordingExecutor:
            def submit(self, *args, **kwargs):
                raise AssertionError("async enrich should be skipped in delivery-order smoke test")

        module.render_translated_message = fake_render
        module.discord_send = fake_send
        module.build_initial_delivery_draft = fake_draft

        target = {"mode": "list", "label": "list1", "name": "list1", "list_index": 1, "url": "https://x.com/i/lists/1"}
        items = [
            {"tweet_id": "300", "handle": "acct", "status_url": "https://x.com/acct/status/300", "created_at": "2026-04-19T11:01:02.000Z", "text": "newest"},
            {"tweet_id": "200", "handle": "acct", "status_url": "https://x.com/acct/status/200", "created_at": "2026-04-19T11:01:01.000Z", "text": "middle"},
            {"tweet_id": "100", "handle": "acct", "status_url": "https://x.com/acct/status/100", "created_at": "2026-04-19T11:01:00.000Z", "text": "oldest"},
        ]

        delivered = module.handle_new_items(store, store.load_config(), RecordingExecutor(), target, items, "2026-04-19T11:01:24.000000+00:00")
        assert_true(sent == ["300", "200", "100"], f"new items should send newest-first, got {sent}")
        assert_true(delivered == ["300", "200", "100"], f"delivered order should stay newest-first, got {delivered}")


def test_recovery_retry_budget_is_capped():
    module = load_service_module("xplus_smoke_recovery_retry_budget")
    config = {
        "empty_page_retry_count": 10,
        "empty_page_retry_delay_milliseconds": 500,
    }
    normal_retry_count, normal_retry_delay = module.empty_page_retry_settings(config, recovery=False)
    recovery_retry_count, recovery_retry_delay = module.empty_page_retry_settings(config, recovery=True)
    assert_true((normal_retry_count, normal_retry_delay) == (2, 250), f"normal retry budget changed unexpectedly: {(normal_retry_count, normal_retry_delay)}")
    assert_true((recovery_retry_count, recovery_retry_delay) == (1, 250), f"recovery retry budget should be capped, got {(recovery_retry_count, recovery_retry_delay)}")


def main():
    tests = [
        ("py_compile", test_py_compile),
        ("invalid_config_write_guards", test_invalid_config_write_guards),
        ("invalid_x_lists_value_guard", test_invalid_x_lists_value_guard),
        ("invalid_state_auto_recovery", test_invalid_state_auto_recovery),
        ("slot_binding_parse_error_visibility", test_slot_binding_parse_error_visibility),
        ("legacy_defaults_parse_error_visibility", test_legacy_defaults_parse_error_visibility),
        ("slot_binding_guard_paths", test_slot_binding_guard_paths),
        ("request_parser_common_paths", test_request_parser_common_paths),
        ("new_item_delivery_prioritizes_newest", test_new_item_delivery_prioritizes_newest),
        ("recovery_retry_budget_is_capped", test_recovery_retry_budget_is_capped),
    ]
    for name, test in tests:
        test()
        print(f"[ok] {name}")


if __name__ == "__main__":
    main()

