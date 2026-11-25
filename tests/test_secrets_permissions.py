"""Tests for credential encryption and role permissions."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import secrets_box as sb
from engine.permissions import permissions_for, has_permission, can_assign_role, ROLES


class TestSecretsBox(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("CREDENTIAL_ENC_KEY")
        os.environ["CREDENTIAL_ENC_KEY"] = sb.generate_key()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("CREDENTIAL_ENC_KEY", None)
        else:
            os.environ["CREDENTIAL_ENC_KEY"] = self._old

    def test_round_trip_and_not_plaintext(self):
        ct = sb.encrypt("EAAB-secret-token-1234", "acct-a")
        self.assertNotIn("secret", ct)
        self.assertEqual(sb.decrypt(ct, "acct-a"), "EAAB-secret-token-1234")

    def test_ciphertext_bound_to_account(self):
        ct = sb.encrypt("tok", "acct-a")
        with self.assertRaises(sb.SecretsBoxError):
            sb.decrypt(ct, "acct-b")

    def test_nonce_is_random(self):
        self.assertNotEqual(sb.encrypt("tok", "a"), sb.encrypt("tok", "a"))

    def test_missing_key_fails_without_leaking(self):
        os.environ.pop("CREDENTIAL_ENC_KEY")
        with self.assertRaises(sb.SecretsBoxError) as cm:
            sb.encrypt("tok", "a")
        self.assertNotIn("tok", str(cm.exception))

    def test_bad_key_length(self):
        os.environ["CREDENTIAL_ENC_KEY"] = "c2hvcnQ="
        with self.assertRaises(sb.SecretsBoxError):
            sb.encrypt("tok", "a")

    def test_mask_shows_only_last_four(self):
        self.assertEqual(sb.mask("EAABxxxxxxxxab12"), "…ab12")
        self.assertEqual(sb.mask("short"), "…")
        self.assertEqual(sb.mask(""), "")

    def test_empty_values(self):
        self.assertEqual(sb.encrypt("", "a"), "")
        self.assertEqual(sb.decrypt("", "a"), "")


class TestPermissions(unittest.TestCase):
    def test_role_ladder(self):
        for lower, higher in zip(ROLES[::-1], ROLES[::-1][1:]):
            self.assertTrue(permissions_for(lower) < permissions_for(higher), (lower, higher))

    def test_viewer_cannot_write(self):
        self.assertTrue(has_permission("viewer", "crm.read"))
        self.assertFalse(has_permission("viewer", "crm.write"))

    def test_agent_cannot_delete_or_configure(self):
        self.assertTrue(has_permission("agent", "crm.write"))
        self.assertFalse(has_permission("agent", "crm.delete"))
        self.assertFalse(has_permission("agent", "wa.config"))

    def test_only_owner_manages_account(self):
        self.assertFalse(has_permission("admin", "account.manage"))
        self.assertTrue(has_permission("owner", "account.manage"))

    def test_unknown_role_has_nothing(self):
        self.assertEqual(permissions_for("root"), frozenset())
        self.assertEqual(permissions_for(None), frozenset())

    def test_assign_role_rules(self):
        self.assertTrue(can_assign_role("admin", "agent"))
        self.assertFalse(can_assign_role("admin", "owner"))
        self.assertTrue(can_assign_role("owner", "owner"))
        self.assertFalse(can_assign_role("agent", "viewer"))
        self.assertFalse(can_assign_role("owner", "superuser"))


if __name__ == "__main__":
    unittest.main()
