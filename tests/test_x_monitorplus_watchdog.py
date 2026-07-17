import importlib.util
import os
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "x_monitorplus_watchdog.py"
MODULE_SPEC = importlib.util.spec_from_file_location("x_monitorplus_watchdog", MODULE_PATH)
watchdog = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(watchdog)


class XMonitorPlusWatchdogTests(unittest.TestCase):
    def test_is_process_running_detects_current_process(self):
        self.assertTrue(watchdog.is_process_running(os.getpid()))

    def test_is_process_running_rejects_invalid_process_ids(self):
        self.assertFalse(watchdog.is_process_running(0))
        self.assertFalse(watchdog.is_process_running(-1))


if __name__ == "__main__":
    unittest.main()
