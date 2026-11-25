import io
import json
import unittest
from unittest import mock

from engine.github_client import GitHubClient


class CommitAuthorTests(unittest.TestCase):
    def test_commit_does_not_override_committer_or_author(self):
        sent = []

        def fake_urlopen(req, timeout=0):
            if req.get_method() == "PUT":
                sent.append(json.loads(req.data))
            return io.BytesIO(json.dumps({"sha": "old", "commit": {"sha": "new"}}).encode())

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            ok, sha, _ = GitHubClient("token").commit_file("o/r", "main", "a.md", "x", "msg")
        self.assertEqual((ok, sha), (True, "new"))
        self.assertNotIn("committer", sent[0])
        self.assertNotIn("author", sent[0])


if __name__ == "__main__":
    unittest.main()
