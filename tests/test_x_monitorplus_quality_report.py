import importlib.util
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "x_monitorplus_quality_report.py"
MODULE_SPEC = importlib.util.spec_from_file_location("x_monitorplus_quality_report", MODULE_PATH)
quality = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(quality)


class XMonitorPlusQualityReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="xplus-quality-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_jsonl(self, name, rows):
        with (self.tmp / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_summarize_slot_splits_original_and_repost_latency(self):
        self.write_jsonl(
            "event_archive.jsonl",
            [
                {
                    "archive_event_type": "delivery",
                    "archived_at": "2026-04-30T00:00:20+00:00",
                    "delivered_at": "2026-04-30T00:00:20+00:00",
                    "target_key": "list1",
                    "delay_seconds": 20,
                    "handle": "original",
                    "tweet_id": "1",
                    "original_text": "plain original",
                    "is_repost": False,
                    "repost_context": "",
                },
                {
                    "archive_event_type": "delivery",
                    "archived_at": "2026-04-30T00:08:20+00:00",
                    "delivered_at": "2026-04-30T00:08:20+00:00",
                    "target_key": "list2",
                    "delay_seconds": 500,
                    "handle": "structured",
                    "tweet_id": "2",
                    "original_text": "structured repost",
                    "is_repost": True,
                    "repost_context": "Source reposted",
                    "slow_delivery_cause": "repost_old",
                },
                {
                    "archive_event_type": "delivery",
                    "archived_at": "2026-04-30T00:13:20+00:00",
                    "delivered_at": "2026-04-30T00:13:20+00:00",
                    "target_key": "list3",
                    "delay_seconds": 800,
                    "handle": "textual",
                    "tweet_id": "3",
                    "original_text": "RT \n@club: text repost",
                    "is_repost": False,
                    "repost_context": "",
                    "slow_delivery_cause": "list_not_exposed",
                },
            ],
        )
        self.write_jsonl("check_archive.jsonl", [])
        (self.tmp / "state.json").write_text(
            json.dumps({"service_pid": 123, "service_heartbeat_at": "2026-04-30T00:14:00+00:00"}),
            encoding="utf-8",
        )

        report = quality.summarize_slot(
            self.tmp,
            "slot-test",
            datetime(2026, 4, 30, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 30, 0, 15, tzinfo=timezone.utc),
        )

        self.assertEqual(report["delivery_latency"]["count"], 3)
        self.assertEqual(report["delivery_latency_original"]["count"], 1)
        self.assertEqual(report["delivery_latency_original"]["max"], 20)
        self.assertEqual(report["delivery_latency_repost"]["count"], 2)
        self.assertEqual(report["delivery_latency_repost"]["max"], 800)
        self.assertEqual(report["repost_reason_counts"], {"structured_repost": 1, "text_rt": 1})
        self.assertEqual(report["event_counts"]["delivery_original"], 1)
        self.assertEqual(report["event_counts"]["delivery_repost"], 2)
        self.assertEqual(report["delivery_latency_original_by_target"]["list1"]["count"], 1)
        self.assertEqual(report["delivery_latency_repost_by_target"]["list2"]["count"], 1)
        self.assertEqual(report["delivery_latency_repost_by_target"]["list3"]["count"], 1)
        self.assertEqual(report["slow_delivery_cause_counts"], {"repost_old": 1, "list_not_exposed": 1})
        self.assertEqual(report["slow_repost_cause_counts"], {"repost_old": 1, "list_not_exposed": 1})
        self.assertEqual(report["slow_repost_deliveries"][0]["slow_delivery_cause"], "list_not_exposed")


if __name__ == "__main__":
    unittest.main()
