from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch

from runner import Ledger, StopRun, main, run, save_session, write_action


class FakeClient:
    user_id = "999"

    def __init__(self):
        self.follows = []
        self.likes = []
        self.fail_like = False
        self.existing = set()

    def dump_settings(self, path):
        Path(path).write_text('{"fake":true}')

    def hashtag_medias_recent(self, tag, amount):
        return [NS(user=NS(pk=i, username=f"user{i}")) for i in [1, 1, 2, 3, 999]]

    hashtag_medias_top = hashtag_medias_recent

    def user_friendship_v1(self, uid):
        return NS(following=uid in self.existing, outgoing_request=False)

    def user_follow(self, uid):
        self.follows.append(uid)
        return True

    def user_medias_v1(self, uid, amount):
        return [NS(id=f"{uid}_{i}") for i in range(amount)]

    def media_like(self, mid):
        self.likes.append(mid)
        if self.fail_like:
            raise TimeoutError("secret-session-token")
        return True


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = Ledger(self.root / "actions.sqlite3")
        self.addCleanup(self.ledger.db.close)
        self.session = self.root / "session.json"
        self.client = FakeClient()
        self.args = NS(hashtags=["tag1", "tag2", "tag1"], execute=True, source="recent",
                       fetch=10, per_tag=5, max_follows=2, max_likes=3, likes=3, pause=1)
        self.sleeper = patch("runner.time.sleep")
        self.sleeper.start()
        self.addCleanup(self.sleeper.stop)

    def test_global_budgets_and_duplicate_users(self):
        run(self.client, self.ledger, self.session, self.args)
        self.assertEqual(self.client.follows, ["1", "2"])
        self.assertEqual(len(self.client.likes), 3)

    def test_follow_saved_even_if_like_fails(self):
        self.client.fail_like = True
        with self.assertRaises(StopRun):
            run(self.client, self.ledger, self.session, self.args)
        self.assertEqual(self.ledger.count("follow"), 1)
        self.assertEqual(self.ledger.count("like"), 1)
        self.assertIn("TimeoutError", self.ledger.get("blocked"))
        self.assertNotIn("secret-session-token", self.ledger.get("blocked"))

    def test_unknown_write_never_retried(self):
        self.ledger.reserve("follow", "1", 10)
        run(self.client, self.ledger, self.session, self.args)
        self.assertEqual(self.client.follows, ["2"])

    def test_preview_makes_no_writes_or_action_reservations(self):
        self.args.execute = False
        run(self.client, self.ledger, self.session, self.args)
        self.assertEqual(self.client.follows, [])
        self.assertEqual(self.client.likes, [])
        self.assertEqual(self.ledger.count("follow"), 0)

    def test_persistence_across_restarts(self):
        self.ledger.reserve("follow", "1", 10)
        second = Ledger(self.root / "actions.sqlite3")
        self.addCleanup(second.db.close)
        self.assertTrue(second.seen("follow", "1"))
        self.assertEqual(second.count("follow"), 1)

    def test_rolling_window_and_lifetime_deduplication(self):
        self.ledger.reserve("follow", "1", 10)
        self.ledger.db.execute("UPDATE actions SET at=0")
        self.ledger.db.commit()
        self.assertEqual(self.ledger.count("follow"), 0)
        self.assertTrue(self.ledger.seen("follow", "1"))

    def test_challenge_stops_before_later_actions(self):
        ChallengeRequired = type("ChallengeRequired", (Exception,), {})
        with patch.object(self.client, "user_follow", side_effect=ChallengeRequired("secret")):
            with self.assertRaisesRegex(StopRun, "ChallengeRequired"):
                run(self.client, self.ledger, self.session, self.args)
        self.assertEqual(self.ledger.count("follow"), 1)
        self.assertEqual(self.client.likes, [])

    def test_existing_follow_skipped(self):
        self.client.existing.add("1")
        run(self.client, self.ledger, self.session, self.args)
        self.assertEqual(self.client.follows, ["2", "3"])

    def test_false_result_remains_pending(self):
        with self.assertRaises(StopRun):
            write_action(self.client, self.ledger, self.session, "follow", "1", 10,
                         lambda uid: False, 1)
        self.assertTrue(self.ledger.seen("follow", "1"))
        self.assertTrue(self.ledger.get("blocked"))

    def test_session_saved_privately(self):
        save_session(self.client, self.session)
        self.assertEqual(self.session.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.session.with_suffix(".tmp").exists())

    def test_installed_library_contract(self):
        import inspect
        from instagrapi import Client
        from instagrapi.types import Relationship
        for method, count in [("hashtag_medias_recent", 2), ("hashtag_medias_top", 2),
                              ("user_friendship_v1", 1), ("user_medias_v1", 2),
                              ("user_follow", 1), ("media_like", 1)]:
            inspect.signature(getattr(Client, method)).bind(None, *(["1"] * count))
        self.assertIn("outgoing_request", Relationship.model_fields)
        self.assertIn("following", Relationship.model_fields)

    def test_real_client_write_timeout_is_not_replayed(self):
        from client import NoReplayClient, configure
        from instagrapi.exceptions import ClientRequestTimeout
        client = NoReplayClient(with_challenge_flow=False)
        configure(client)
        client.delay_range = None
        with patch.object(client, "_send_private_request", side_effect=ClientRequestTimeout()) as send:
            with self.assertRaises(ClientRequestTimeout):
                client.private_request("friendships/create/1/", data={"user_id": "1"})
        self.assertEqual(send.call_count, 1)
        self.assertFalse(client.with_challenge_flow)
        self.assertEqual(client.session_retry_total, 0)

    def test_paused_scheduled_run_stops_before_client_creation(self):
        args = NS(username="testuser", state_dir=self.root, command="run")
        directory = self.root / "testuser"
        directory.mkdir()
        ledger = Ledger(directory / "actions.sqlite3")
        ledger.set("blocked", "challenge")
        ledger.db.close()
        with patch("runner.parse_args", return_value=args), patch("client.NoReplayClient") as factory:
            with self.assertRaisesRegex(StopRun, "Account paused"):
                main()
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
