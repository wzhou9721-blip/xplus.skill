import contextlib
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "x_monitorplus_hermes_tweet.py"
MODULE_SPEC = importlib.util.spec_from_file_location("x_monitorplus_hermes_tweet", MODULE_PATH)
hermes = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(hermes)


@contextlib.contextmanager
def temporary_test_dir():
    path = Path(tempfile.mkdtemp(prefix="xplus-hermes-tweet-"))
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise hermes.requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return self._payload


class HermesTweetFetcherTests(unittest.TestCase):
    def test_disabled_duplicate_does_not_suppress_enabled_query(self):
        queries = hermes.normalize_query_configs(
            {
                "hermes_tweet_queries": [
                    {"query": "openclaw skill", "enabled": False},
                    {"query": "openclaw skill", "enabled": True, "limit": 5},
                ]
            }
        )

        self.assertEqual(
            queries,
            [{"query": "openclaw skill", "name": "openclaw skill", "limit": 5}],
        )

    def test_disabled_fetch_skips_without_api_key(self):
        with temporary_test_dir() as root:
            store = hermes.svc.Store(root=root)
            store.save_config({"hermes_tweet_enabled": False})

            result = hermes.fetch_once(store)

        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "hermes_tweet_disabled")

    def test_missing_api_key_reports_env_names_only(self):
        with temporary_test_dir() as root:
            store = hermes.svc.Store(root=root)
            store.save_config({"hermes_tweet_enabled": True, "hermes_tweet_queries": ["openclaw skill"]})

            old_values = {name: os.environ.pop(name, None) for name in hermes.DEFAULT_API_KEY_ENVS}
            try:
                result = hermes.fetch_once(store)
            finally:
                for name, value in old_values.items():
                    if value is not None:
                        os.environ[name] = value

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "missing_api_key")
        self.assertIn("XQUIK_API_KEY", result["api_key_envs"])

    def test_http_error_payload_excludes_response_and_request_details(self):
        response = FakeResponse({"debug": "private response detail"}, status_code=403)
        error = hermes.requests.HTTPError(
            "403 error for https://xquik.com/search?q=private-query",
            response=response,
        )

        result = hermes.http_error_payload(error)

        self.assertEqual(
            result,
            {
                "ok": False,
                "action": "hermes_tweet_fetch",
                "error": "http_error",
                "status_code": 403,
            },
        )

    def test_fetch_writes_normalized_events_and_dedupes_seen_ids(self):
        original_get = hermes.requests.get
        original_iso_now = hermes.svc.iso_now
        try:
            calls = []

            def fake_get(url, headers=None, params=None, timeout=None):
                calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
                return FakeResponse(
                    {
                        "data": {
                            "tweets": [
                                {
                                    "id": "100",
                                    "text": "Hermes Agent X monitoring update",
                                    "author": {"username": "alice"},
                                    "created_at": "2026-05-23T12:00:00+00:00",
                                },
                                {
                                    "id": "100",
                                    "text": "duplicate",
                                    "author": {"username": "alice"},
                                },
                            ]
                        }
                    }
                )

            hermes.requests.get = fake_get
            hermes.svc.iso_now = lambda: "2026-05-23T12:01:00+00:00"
            with temporary_test_dir() as root:
                store = hermes.svc.Store(root=root)
                store.save_config(
                    {
                        "hermes_tweet_enabled": True,
                        "hermes_tweet_queries": [{"name": "OpenClaw", "query": "openclaw skill", "limit": 5}],
                        "hermes_tweet_api_key_env": "XQUIK_TEST_KEY",
                        "output_sinks": ["jsonl"],
                    }
                )
                os.environ["XQUIK_TEST_KEY"] = "xq_test"

                result = hermes.fetch_once(store)
                second_result = hermes.fetch_once(store)
                archive_lines = (Path(root) / hermes.svc.EVENT_ARCHIVE_FILENAME).read_text(encoding="utf-8").splitlines()
                event = json.loads(archive_lines[-1])

            self.assertTrue(result["ok"])
            self.assertEqual(result["written"], 1)
            self.assertEqual(result["queries"][0]["fetched"], 2)
            self.assertEqual(result["queries"][0]["written"], 1)
            self.assertEqual(second_result["written"], 0)
            self.assertEqual(second_result["skipped_seen"], 2)
            self.assertEqual(event["tweet_id"], "100")
            self.assertEqual(event["handle"], "alice")
            self.assertEqual(event["url"], "https://x.com/alice/status/100")
            self.assertEqual(event["source"], "hermes_tweet")
            self.assertEqual(calls[0]["headers"]["X-API-Key"], "xq_test")
            self.assertEqual(calls[0]["params"], {"q": "openclaw skill", "limit": 5})
        finally:
            hermes.requests.get = original_get
            hermes.svc.iso_now = original_iso_now
            os.environ.pop("XQUIK_TEST_KEY", None)


if __name__ == "__main__":
    unittest.main()
