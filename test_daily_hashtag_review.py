"""No-network tests for scheduled read-only 5-hashtag, 20-creators/tag review."""
import unittest
from scripts.daily_hashtag_review import (
    HASHTAGS, PER_HASHTAG, build_report, markdown, select_distinct_authors
)


def row(username, age, code=None):
    return {
        "username": username,
        "age": float(age),
        "code": code or "P" + username.replace(".", "_"),
    }


class DailyHashtagTests(unittest.TestCase):
    def test_exact_five_original_hashtags_and_goal(self):
        self.assertEqual(
            HASHTAGS,
            ("followforfollow", "likeforlike", "likeforfollow", "follow4follow", "like4like"),
        )
        self.assertEqual(PER_HASHTAG, 20)

    def test_keep_older_posts_and_sort_newest_first(self):
        records = [
            row("older", 300),
            row("newer", 2),
            row("middle", 46),
            row("newer", 250, "SECOND"),
            row("invalid user!", 1),
            row("future", -1),
        ]
        found = select_distinct_authors(records, per_tag=20)
        self.assertEqual([r["username"] for r in found], ["newer", "middle", "older"])
        self.assertEqual([r["age_hours"] for r in found], [2, 46, 300])

    def test_twenty_per_hashtag_and_global_uniqueness(self):
        def fetch(tag):
            position = HASHTAGS.index(tag)
            rows = [row("shared", 1, "UNIQUE" + str(position))]
            rows += [row(f"user{position}_{i}", i + 2) for i in range(30)]
            return rows, [{"http": "200", "raw": len(rows)}]
        report = build_report(fetch)
        self.assertEqual(len(report["results"]), 5)
        self.assertEqual(report["total_unique_accounts"], 100)
        self.assertEqual([r["unique_accounts"] for r in report["results"]], [20] * 5)
        names = [c["username"].lower() for r in report["results"] for c in r["candidates"]]
        self.assertEqual(len(names), len(set(names)))

    def test_shortfall_not_padded(self):
        def fetch(tag):
            return [row(tag + "user", 100)], [{"http": "200", "raw": 1}]
        report = build_report(fetch)
        self.assertEqual(report["total_unique_accounts"], 5)
        self.assertEqual([r["unique_accounts"] for r in report["results"]], [1] * 5)
        self.assertIn("No likes or follows were performed", markdown(report))

    def test_stop_on_rate_limit_no_second_query(self):
        calls = []
        def fetch(tag):
            calls.append(tag)
            return [], [{"http": "429", "raw": 0}]
        report = build_report(fetch)
        self.assertEqual(calls, [HASHTAGS[0]])
        self.assertEqual(len(report["errors"]), 1)
        self.assertEqual(report["total_unique_accounts"], 0)

    def test_does_not_include_bad_values(self):
        candidates = select_distinct_authors([
            row("john.smith", 5, "ABC123"),
            row("bad username", 0.5),
            row("nottrusted", float("nan")),
            {"username": "also_invalid", "code": "../../../../", "age": 0.5},
        ])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["post_url"], "https://www.instagram.com/p/ABC123/")


if __name__ == "__main__":
    unittest.main()
