"""Temporary passwords: forced change (B2) and admin reset (B3)."""
import unittest
import tests._env  # noqa: F401
from tests.apihelpers import Caller, new_user, new_account, join, setup_db
from engine import auth
import database as db


def login(username, password):
    ok, token, _, err = auth.authenticate_user(username, password, "127.0.0.1", "t")
    return ok, token, err


class TestTempPasswords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        setup_db()
        cls.acct = new_account()
        cls.owner = new_user("owner"); join(cls.acct, cls.owner, "owner")
        cls.admin = new_user("admin"); join(cls.acct, cls.admin, "admin")
        cls.agent = new_user("agent"); join(cls.acct, cls.agent, "agent")
        cls.owner_c, cls.admin_c = Caller(cls.owner, cls.acct), Caller(cls.admin, cls.acct)

    def _add(self, name):
        code, out = self.owner_c("POST", f"/api/accounts/{self.acct}/users", {"username": name, "role": "agent"})
        self.assertEqual(code, 201)
        return out

    def test_new_user_must_change_password_before_anything_else(self):
        out = self._add("fresh1")
        ok, token, _ = login("fresh1", out["temporary_password"])
        self.assertTrue(ok)
        user = auth.validate_session(token)
        self.assertTrue(user["must_change_password"])
        c = Caller(user, self.acct)
        code, body = c("GET", "/api/whatsapp/contacts")
        self.assertEqual((code, body["code"]), (403, "password_change_required"))
        self.assertEqual(c("GET", "/api/auth/me")[0], 200)
        self.assertEqual(c("POST", "/api/auth/change-password",
                           {"current_password": out["temporary_password"], "new_password": "BrandNewPass1"})[0], 200)
        ok, token, _ = login("fresh1", "BrandNewPass1")
        self.assertFalse(auth.validate_session(token)["must_change_password"])
        self.assertEqual(Caller(auth.validate_session(token), self.acct)("GET", "/api/whatsapp/contacts")[0], 200)

    def test_expired_temp_password_is_refused(self):
        out = self._add("fresh2")
        with db.get_connection() as conn:
            conn.execute("UPDATE users SET temp_password_expires = '2000-01-01T00:00:00' WHERE username = 'fresh2'")
            conn.commit()
        ok, _, err = login("fresh2", out["temporary_password"])
        self.assertFalse(ok)
        self.assertIn("expired", err)

    def test_admin_reset_revokes_sessions_and_forces_change(self):
        out = self._add("fresh3")
        uid = out["user_id"]
        auth.update_user_password(uid, "ChosenPass123")           # user already changed it
        ok, old_token, _ = login("fresh3", "ChosenPass123")
        code, body = self.admin_c("POST", f"/api/accounts/{self.acct}/users/{uid}/reset-password")
        self.assertEqual(code, 200)
        self.assertTrue(body["must_change_password"])
        ok, token, _ = login("fresh3", body["temporary_password"])
        self.assertTrue(ok)
        self.assertTrue(auth.validate_session(token)["must_change_password"])
        self.assertFalse(login("fresh3", "ChosenPass123")[0])

    def test_admin_cannot_reset_owner_or_self_or_shared_login(self):
        self.assertEqual(self.admin_c("POST", f"/api/accounts/{self.acct}/users/{self.owner['id']}/reset-password")[0], 403)
        self.assertEqual(self.admin_c("POST", f"/api/accounts/{self.acct}/users/{self.admin['id']}/reset-password")[0], 400)
        other = new_account()
        join(other, self.agent, "agent")                           # agent now belongs to two accounts
        code, body = self.admin_c("POST", f"/api/accounts/{self.acct}/users/{self.agent['id']}/reset-password")
        self.assertEqual((code, body["error"]), (403, "shared_login"))

    def test_agent_cannot_reset(self):
        c = Caller(self.agent, self.acct)
        self.assertEqual(c("POST", f"/api/accounts/{self.acct}/users/{self.admin['id']}/reset-password")[0], 403)


if __name__ == "__main__":
    unittest.main()
