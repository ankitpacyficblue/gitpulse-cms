"""Auth sessions and account/user management rules."""
import time
import unittest
import tests._env  # noqa: F401

import crm_store as cs
import database as db
from engine import auth
from engine import accounts_service as svc
from engine.accounts_service import ServiceError


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        n = str(time.time_ns())
        cls.pa = auth.get_user_by_id(auth.create_user("pa" + n, "Passw0rd!x", is_platform_admin=True))
        cls.plain = auth.get_user_by_id(auth.create_user("plain" + n, "Passw0rd!x"))

    def new_account(self):
        out = svc.create_account_with_owner(self.pa, "Acme " + str(time.time_ns()))
        return out["id"]


class TestSessions(Base):
    def test_login_and_validate(self):
        ok, token, user, err = auth.authenticate_user(self.plain["username"], "Passw0rd!x", "1.2.3.4")
        self.assertTrue(ok, err)
        self.assertNotIn("role", user)
        v = auth.validate_session(token)
        self.assertEqual(v["id"], self.plain["id"])
        self.assertFalse(v["is_platform_admin"])

    def test_wrong_password_and_unknown_user_same_message(self):
        _, _, _, e1 = auth.authenticate_user(self.plain["username"], "nope", "9.9.9.9")
        _, _, _, e2 = auth.authenticate_user("ghost-user", "nope", "9.9.9.8")
        self.assertEqual(e1, e2)

    def test_tampered_token_rejected(self):
        token = auth.create_session(self.plain["id"])
        self.assertIsNone(auth.validate_session(token[:-4] + "AAAA"))
        self.assertIsNone(auth.validate_session(""))
        self.assertIsNone(auth.validate_session("garbage"))

    def test_logout_revokes(self):
        token = auth.create_session(self.plain["id"])
        self.assertIsNotNone(auth.validate_session(token))
        auth.revoke_session(token)
        self.assertIsNone(auth.validate_session(token))

    def test_inactive_user_loses_access_immediately_and_cannot_login(self):
        uid = auth.create_user("temp" + str(time.time_ns()), "Passw0rd!x")
        token = auth.create_session(uid)
        auth.set_user_active(uid, False)
        self.assertIsNone(auth.validate_session(token))
        ok, *_ = auth.authenticate_user(auth.get_user_by_id(uid)["username"], "Passw0rd!x", "5.5.5.5")
        self.assertFalse(ok)

    def test_no_default_admin_and_short_password_rejected(self):
        self.assertFalse(hasattr(auth, "init_default_admin"))
        with self.assertRaises(ValueError):
            auth.create_user("shortpw", "abc")

    def test_secret_required_on_serverless(self):
        import os
        old_s, old_v = os.environ.pop("SESSION_SECRET"), os.environ.get("VERCEL")
        os.environ["VERCEL"] = "1"
        try:
            with self.assertRaises(RuntimeError):
                auth.get_auth_secret_key()
        finally:
            os.environ["SESSION_SECRET"] = old_s
            os.environ.pop("VERCEL") if old_v is None else os.environ.__setitem__("VERCEL", old_v)


class TestBootstrap(Base):
    def test_bootstrap_from_env_only_with_strong_password_and_is_idempotent(self):
        import os
        name = "boot" + str(time.time_ns())
        os.environ["BOOTSTRAP_ADMIN_USERNAME"] = name
        try:
            os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "short"
            self.assertIsNone(auth.bootstrap_platform_admin_from_env())
            os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "a-long-bootstrap-password"
            uid = auth.bootstrap_platform_admin_from_env()
            self.assertTrue(auth.get_user_by_id(uid)["is_platform_admin"])
            self.assertIsNone(auth.bootstrap_platform_admin_from_env())
            ok, *_ = auth.authenticate_user(name, "a-long-bootstrap-password", "7.7.7.7")
            self.assertTrue(ok)
        finally:
            os.environ.pop("BOOTSTRAP_ADMIN_USERNAME", None)
            os.environ.pop("BOOTSTRAP_ADMIN_PASSWORD", None)

    def test_nothing_without_env(self):
        self.assertIsNone(auth.bootstrap_platform_admin_from_env())


class TestAccountCreation(Base):
    def test_only_platform_admin_creates_accounts(self):
        with self.assertRaises(ServiceError) as cm:
            svc.create_account_with_owner(self.plain, "Nope")
        self.assertEqual(cm.exception.status, 403)

    def test_creates_empty_account_with_new_owner_and_temp_password(self):
        out = svc.create_account_with_owner(self.pa, "Beta " + str(time.time_ns()), owner_username="Owner" + str(time.time_ns()))
        self.assertIn("owner_temporary_password", out)
        self.assertEqual(cs.get_membership_role(out["id"], out["owner_user_id"]), "owner")
        self.assertEqual(cs.list_contacts(out["id"]), [])
        self.assertEqual(cs.list_deals(out["id"]), [])
        self.assertEqual(cs.list_automations(out["id"]), [])

    def test_existing_user_becomes_owner_without_password(self):
        out = svc.create_account_with_owner(self.pa, "Gamma " + str(time.time_ns()), owner_username=self.plain["username"])
        self.assertNotIn("owner_temporary_password", out)
        self.assertEqual(out["owner_user_id"], self.plain["id"])


class TestUserManagement(Base):
    def test_admin_adds_agent_new_user_gets_temp_password(self):
        acct = self.new_account()
        out = svc.add_user(acct, "admin", "agent" + str(time.time_ns()), "agent")
        self.assertIn("temporary_password", out)
        self.assertEqual(cs.get_membership_role(acct, out["user_id"]), "agent")

    def test_existing_user_added_without_new_password_and_duplicate_409(self):
        acct = self.new_account()
        out = svc.add_user(acct, "owner", self.plain["username"], "viewer")
        self.assertNotIn("temporary_password", out)
        with self.assertRaises(ServiceError) as cm:
            svc.add_user(acct, "owner", self.plain["username"], "viewer")
        self.assertEqual(cm.exception.status, 409)

    def test_agent_and_viewer_cannot_manage_users(self):
        acct = self.new_account()
        for role in ("agent", "viewer"):
            with self.assertRaises(ServiceError) as cm:
                svc.add_user(acct, role, "x" + str(time.time_ns()), "viewer")
            self.assertEqual(cm.exception.status, 403)

    def test_admin_cannot_grant_owner_but_owner_can(self):
        acct = self.new_account()
        with self.assertRaises(ServiceError):
            svc.add_user(acct, "admin", "own" + str(time.time_ns()), "owner")
        svc.add_user(acct, "owner", "own" + str(time.time_ns()), "owner")

    def test_invalid_role_400(self):
        acct = self.new_account()
        with self.assertRaises(ServiceError) as cm:
            svc.add_user(acct, "owner", "z" + str(time.time_ns()), "root")
        self.assertEqual(cm.exception.status, 400)

    def test_last_owner_protected(self):
        acct = self.new_account()  # platform admin is sole owner
        with self.assertRaises(ServiceError) as cm:
            svc.change_role(acct, "owner", self.pa["id"], "admin")
        self.assertEqual(cm.exception.code, "last_owner")
        with self.assertRaises(ServiceError) as cm:
            svc.remove_member(acct, "owner", self.pa["id"])
        self.assertEqual(cm.exception.code, "last_owner")

    def test_admin_cannot_demote_or_remove_owner(self):
        acct = self.new_account()
        svc.add_user(acct, "owner", self.plain["username"], "owner")  # two owners now
        with self.assertRaises(ServiceError):
            svc.change_role(acct, "admin", self.plain["id"], "viewer")
        with self.assertRaises(ServiceError):
            svc.remove_member(acct, "admin", self.plain["id"])
        svc.change_role(acct, "owner", self.plain["id"], "viewer")
        self.assertEqual(cs.get_membership_role(acct, self.plain["id"]), "viewer")

    def test_cannot_touch_member_of_other_account(self):
        a1, a2 = self.new_account(), self.new_account()
        out = svc.add_user(a2, "owner", "only-in-a2" + str(time.time_ns()), "agent")
        with self.assertRaises(ServiceError) as cm:
            svc.change_role(a1, "owner", out["user_id"], "admin")
        self.assertEqual(cm.exception.status, 404)
        with self.assertRaises(ServiceError):
            svc.remove_member(a1, "owner", out["user_id"])
        self.assertEqual(cs.get_membership_role(a2, out["user_id"]), "agent")


class TestDeleteAccount(Base):
    def test_requires_owner_and_matching_name(self):
        acct = self.new_account()
        name = cs.get_account(acct)["name"]
        with self.assertRaises(ServiceError):
            svc.delete_account(acct, "admin", name)
        with self.assertRaises(ServiceError) as cm:
            svc.delete_account(acct, "owner", "wrong")
        self.assertEqual(cm.exception.code, "confirm_name_mismatch")
        svc.delete_account(acct, "owner", name)
        self.assertIsNone(cs.get_account(acct))


if __name__ == "__main__":
    unittest.main()
