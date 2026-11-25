"""Login lockout is per username+IP; security headers are defined."""
import time
import unittest

import tests._env  # noqa: F401
from engine import auth
from server.security import SECURITY_HEADERS


def fail(ip, user, n):
    for _ in range(n):
        auth.record_login_attempt(ip, user, success=False)


class LockoutTests(unittest.TestCase):
    def setUp(self):
        self.u = f"lk{time.time_ns()}"
        self.ip = f"10.0.{time.time_ns() % 250}.{time.time_ns() % 199 + 1}"

    def test_pair_locks_after_five(self):
        fail(self.ip, self.u, 5)
        self.assertTrue(auth.check_login_lockout(self.ip, self.u)[0])

    def test_other_ip_same_user_not_locked(self):
        fail(self.ip, self.u, 5)
        self.assertFalse(auth.check_login_lockout("203.0.113.9", self.u)[0])

    def test_unknown_usernames_do_not_lock_a_real_user_on_same_ip(self):
        for i in range(10):
            fail(self.ip, f"ghost{i}{time.time_ns()}", 1)
        fail(self.ip, "x" + self.u, 10)
        self.assertFalse(auth.check_login_lockout(self.ip, self.u)[0])

    def test_username_wide_cap_across_ips(self):
        for i in range(auth.MAX_FAILED_PER_USERNAME):
            fail(f"198.51.100.{i + 1}", self.u, 1)
        self.assertTrue(auth.check_login_lockout("192.0.2.1", self.u)[0])

    def test_success_clears_only_that_pair(self):
        fail(self.ip, self.u, 4)
        fail("203.0.113.7", self.u, 4)
        auth.record_login_attempt(self.ip, self.u, success=True)
        fail(self.ip, self.u, 1)
        self.assertFalse(auth.check_login_lockout(self.ip, self.u)[0])
        fail("203.0.113.7", self.u, 1)
        self.assertTrue(auth.check_login_lockout("203.0.113.7", self.u)[0])


class HeaderTests(unittest.TestCase):
    def test_headers(self):
        h = dict(SECURITY_HEADERS)
        self.assertEqual(h["X-Frame-Options"], "DENY")
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
        self.assertIn("Referrer-Policy", h)

    def test_wsgi_app_sets_headers_without_wildcard_cors(self):
        import api.index as m
        out = {}
        m.app({"PATH_INFO": "/login", "REQUEST_METHOD": "GET", "QUERY_STRING": ""},
              lambda status, hdrs: out.update(h=dict(hdrs)))
        self.assertEqual(out["h"]["X-Frame-Options"], "DENY")
        self.assertNotIn("Access-Control-Allow-Origin", out["h"])


if __name__ == "__main__":
    unittest.main()
