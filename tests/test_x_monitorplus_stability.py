import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "x_monitorplus_stability.py"
MODULE_SPEC = importlib.util.spec_from_file_location("x_monitorplus_stability", MODULE_PATH)
stability = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(stability)


def service_status(running=False, auth_ready=True, target_auth_ready=True):
    return {
        "ok": True,
        "running": running,
        "pid": 123 if running else 0,
        "config_valid": True,
        "config_missing": [],
        "auth_status": {"ready": auth_ready, "error": ""},
        "source_slot": "2",
        "source_slot_label": "2号槽位",
        "slot_binding": {
            "config_exists": True,
            "cookies_exists": True,
            "profile_exists": True,
            "profile_dir": "C:/tmp/profile",
        },
        "profile_dir": "C:/tmp/profile",
        "lists": [
            {
                "id": "list1",
                "index": 1,
                "name": "list1",
                "enabled": True,
                "url": "https://x.com/i/lists/1",
                "configured": True,
                "auth_ready": target_auth_ready,
                "auth_error": "",
            }
        ],
    }


def watchdog_status(running=False, semantic_restart_enabled=False):
    return {
        "ok": True,
        "running": running,
        "pid": 456 if running else 0,
        "state": {
            "heartbeat_at": "2026-05-06T00:00:00+00:00",
            "config": {
                "slot_roots": ["C:/tmp/slot2"],
                "semantic_restart_enabled": semantic_restart_enabled,
                "ready_stale_restart_enabled": False,
                "restart_cooldown_seconds": 900,
            },
            "slots": {"slot2": {"last_health": {"running": running}}},
        },
    }


class XMonitorPlusStabilityTests(unittest.TestCase):
    def setUp(self):
        self.original_run_json_command = stability.run_json_command

    def tearDown(self):
        stability.run_json_command = self.original_run_json_command

    def test_status_flags_watchdog_that_would_restart_stopped_enabled_slot(self):
        def fake_run(args, timeout=60):
            if "x_monitorplus_watchdog.py" in str(args[1]):
                return watchdog_status(running=True)
            return service_status(running=False)

        stability.run_json_command = fake_run

        payload = stability.status([Path("C:/tmp/slot2")], Path("C:/tmp/watchdog"), "python")

        self.assertFalse(payload["ok"])
        self.assertIn("watchdog_running_will_restart_stopped_enabled_slots:slot2", payload["issues"])

    def test_preflight_blocks_semantic_watchdog_restart_policy(self):
        def fake_run(args, timeout=60):
            if "x_monitorplus_watchdog.py" in str(args[1]):
                return watchdog_status(running=False, semantic_restart_enabled=True)
            return service_status(running=False)

        stability.run_json_command = fake_run

        payload = stability.preflight([Path("C:/tmp/slot2")], Path("C:/tmp/watchdog"), "python")

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["ready_to_start"])
        self.assertIn("watchdog:semantic_restart_enabled", payload["issues"])

    def test_safe_start_blocks_when_auth_is_not_ready(self):
        calls = []

        def fake_run(args, timeout=60):
            calls.append(list(args))
            if "x_monitorplus_watchdog.py" in str(args[1]):
                return watchdog_status(running=False)
            return service_status(running=False, auth_ready=False, target_auth_ready=False)

        stability.run_json_command = fake_run

        payload = stability.safe_start(
            [Path("C:/tmp/slot2")],
            Path("C:/tmp/watchdog"),
            "python",
            wait_seconds=0,
            poll_seconds=1,
        )

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["blocked"])
        self.assertIn("slot2:auth_not_ready", payload["blocking_issues"])
        flattened = " ".join(" ".join(str(part) for part in call) for call in calls)
        self.assertNotIn(" start", flattened)


if __name__ == "__main__":
    unittest.main()
