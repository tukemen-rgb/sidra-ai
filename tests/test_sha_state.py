from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.ingestion.sha_state import (  # noqa: E402
    ConcurrentStateUpdate,
    InvalidCommitSha,
    InvalidRepository,
    ShaStateStore,
)


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


class ShaStateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ShaStateStore(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_first_sync_is_marked_changed(self) -> None:
        decision = self.store.decide("tukemen-rgb/site", SHA_A)
        self.assertIsNone(decision.previous_sha)
        self.assertTrue(decision.changed)

    def test_same_sha_skips_incremental_ingestion(self) -> None:
        self.store.advance(
            "tukemen-rgb/site", SHA_A, expected_previous_sha=None
        )
        decision = self.store.decide("tukemen-rgb/site", SHA_A)
        self.assertEqual(decision.previous_sha, SHA_A)
        self.assertFalse(decision.changed)

    def test_changed_sha_returns_previous_and_head(self) -> None:
        self.store.advance(
            "tukemen-rgb/site", SHA_A, expected_previous_sha=None
        )
        decision = self.store.decide("tukemen-rgb/site", SHA_B)
        self.assertEqual(decision.previous_sha, SHA_A)
        self.assertEqual(decision.head_sha, SHA_B)
        self.assertTrue(decision.changed)

    def test_compare_and_set_blocks_stale_worker(self) -> None:
        self.store.advance(
            "tukemen-rgb/site", SHA_A, expected_previous_sha=None
        )
        self.store.advance(
            "tukemen-rgb/site", SHA_B, expected_previous_sha=SHA_A
        )
        with self.assertRaises(ConcurrentStateUpdate):
            self.store.advance(
                "tukemen-rgb/site", SHA_C, expected_previous_sha=SHA_A
            )
        self.assertEqual(
            self.store.get("tukemen-rgb/site").last_commit_sha, SHA_B
        )

    def test_persisted_state_contains_no_content_or_credentials(self) -> None:
        self.store.advance(
            "tukemen-rgb/site", SHA_A, expected_previous_sha=None
        )
        state_text = next(Path(self.tmp.name).glob("*.json")).read_text(
            encoding="utf-8"
        )
        self.assertIn("last_commit_sha", state_text)
        self.assertNotIn("token", state_text.lower())
        self.assertNotIn("content", state_text.lower())
        self.assertNotIn("password", state_text.lower())

    def test_repository_and_sha_validation(self) -> None:
        with self.assertRaises(InvalidRepository):
            self.store.decide("../not-a-repo", SHA_A)
        with self.assertRaises(InvalidCommitSha):
            self.store.decide("tukemen-rgb/site", "short-sha")


if __name__ == "__main__":
    unittest.main()
