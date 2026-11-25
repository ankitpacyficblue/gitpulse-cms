"""Account isolation tests for the CRM store: account A can never read, change or delete account B's rows."""
import unittest
import tests._env  # noqa: F401  (must be first)

import crm_store as cs
import database as db
from database import get_connection


def make_user(name):
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO users (username, password_hash, salt, role, created_at) VALUES (?,?,?,?,?)",
                           (name, "h", "s", "agent", "2026-01-01"))
        conn.commit()
        return cur.lastrowid


class TenancyBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        n = self.id().split(".")[-1]
        self.a = cs.create_account(f"A-{n}")["id"]
        self.b = cs.create_account(f"B-{n}")["id"]


class TestContactsIsolation(TenancyBase):
    def test_same_phone_allowed_in_two_accounts_but_not_twice_in_one(self):
        cs.create_contact(self.a, "Ann", "+1 555 000 1111")
        cs.create_contact(self.b, "Ann B", "+15550001111")
        with self.assertRaisesRegex(ValueError, "duplicate_phone"):
            cs.create_contact(self.a, "Dup", "+1-555-000-1111")

    def test_list_get_update_delete_are_scoped(self):
        cid = cs.create_contact(self.a, "Ann", "+15550002222", tags=["VIP"])
        self.assertEqual(cs.list_contacts(self.b), [])
        self.assertIsNone(cs.get_contact(self.b, cid))
        self.assertFalse(cs.update_contact(self.b, cid, name="Hacked"))
        self.assertFalse(cs.delete_contact(self.b, cid))
        self.assertEqual(cs.get_contact(self.a, cid)["name"], "Ann")
        self.assertEqual(cs.get_contact(self.a, cid)["tags"], ["VIP"])
        self.assertTrue(cs.delete_contact(self.a, cid))

    def test_phone_lookup_is_scoped(self):
        cs.create_contact(self.a, "Ann", "+15550003333")
        self.assertIsNotNone(cs.get_contact_by_phone(self.a, "+1 (555) 000-3333"))
        self.assertIsNone(cs.get_contact_by_phone(self.b, "+15550003333"))

    def test_search_does_not_cross_accounts(self):
        cs.create_contact(self.a, "Zebra Corp", "+15550004444")
        self.assertEqual(cs.list_contacts(self.b, search="Zebra"), [])


class TestConversationsAndMessages(TenancyBase):
    def test_conversation_requires_own_contact(self):
        cid = cs.create_contact(self.a, "Ann", "+15550005555")
        self.assertIsNone(cs.get_or_create_conversation(self.b, cid))
        conv = cs.get_or_create_conversation(self.a, cid)
        self.assertEqual(conv["contact_name"], "Ann")
        self.assertEqual(cs.get_or_create_conversation(self.a, cid)["id"], conv["id"])

    def test_message_cannot_attach_to_other_account(self):
        cid = cs.create_contact(self.a, "Ann", "+15550006666")
        conv = cs.get_or_create_conversation(self.a, cid)
        self.assertIsNone(cs.create_message(self.b, conv["id"], cid, "inbound", "hi"))
        mid = cs.create_message(self.a, conv["id"], cid, "inbound", "hi", wa_message_id="wamid.1")
        self.assertIsNotNone(mid)
        self.assertEqual(cs.list_messages(self.b, conv["id"]), [])
        self.assertEqual(len(cs.list_messages(self.a, conv["id"])), 1)
        self.assertEqual(cs.get_conversation(self.a, conv["id"])["unread_count"], 1)
        self.assertFalse(cs.update_message_status(self.b, "wamid.1", "read"))
        self.assertTrue(cs.update_message_status(self.a, "wamid.1", "read"))
        self.assertFalse(cs.mark_conversation_read(self.b, conv["id"]))
        self.assertTrue(cs.mark_conversation_read(self.a, conv["id"]))

    def test_db_rejects_cross_account_message_row(self):
        """Composite foreign key blocks a conversation/contact pair from different accounts even via raw SQL."""
        ca = cs.create_contact(self.a, "Ann", "+15550007777")
        cb = cs.create_contact(self.b, "Bob", "+15550008888")
        conv_a = cs.get_or_create_conversation(self.a, ca)
        with self.assertRaises(Exception):
            with get_connection() as conn:
                conn.execute("""INSERT INTO messages (account_id, conversation_id, contact_id, direction, body, created_at)
                                VALUES (?,?,?,?,?,?)""", (self.b, conv_a["id"], cb, "inbound", "x", "now"))


class TestDealsBroadcastsAutomations(TenancyBase):
    def test_deals_scoped_and_contact_checked(self):
        ca = cs.create_contact(self.a, "Ann", "+15550009999")
        with self.assertRaisesRegex(ValueError, "contact_not_found"):
            cs.create_deal(self.b, "Steal", 10, contact_id=ca)
        did = cs.create_deal(self.a, "Big", 500, contact_id=ca)
        self.assertEqual(cs.list_deals(self.b), [])
        self.assertFalse(cs.update_deal_stage(self.b, did, "won"))
        self.assertFalse(cs.delete_deal(self.b, did))
        self.assertTrue(cs.update_deal_stage(self.a, did, "Won"))
        self.assertEqual(cs.list_deals(self.a)[0]["stage"], "won")

    def test_broadcasts_scoped(self):
        bid = cs.create_broadcast(self.a, "Promo", "Hello")
        self.assertIsNone(cs.get_broadcast(self.b, bid))
        self.assertEqual(cs.list_broadcasts(self.b), [])
        self.assertFalse(cs.update_broadcast_stats(self.b, bid, total=9))
        self.assertTrue(cs.update_broadcast_stats(self.a, bid, total=9, sent=9))

    def test_automations_scoped(self):
        aid = cs.create_automation(self.a, "Hi", "keyword", "Hello", trigger_keyword="HELLO")
        self.assertEqual(cs.list_automations(self.b), [])
        self.assertFalse(cs.toggle_automation(self.b, aid, False))
        self.assertFalse(cs.delete_automation(self.b, aid))
        self.assertFalse(cs.increment_automation_execution(self.b, aid))
        self.assertTrue(cs.increment_automation_execution(self.a, aid))


class TestAccountsAndMembership(TenancyBase):
    def test_membership_and_listing(self):
        u = make_user("u-" + self.id().split(".")[-1])
        cs.add_membership(self.a, u, "owner")
        cs.add_membership(self.b, u, "viewer")
        roles = {x["id"]: x["role"] for x in cs.list_accounts_for_user(u)}
        self.assertEqual(roles, {self.a: "owner", self.b: "viewer"})
        self.assertEqual(cs.get_membership_role(self.a, u), "owner")
        self.assertIsNone(cs.get_membership_role("nope", u))
        self.assertEqual(cs.count_owners(self.a), 1)

    def test_invalid_role_rejected(self):
        u = make_user("u2-" + self.id().split(".")[-1])
        with self.assertRaises(ValueError):
            cs.add_membership(self.a, u, "superuser")

    def test_soft_delete_keeps_rows_scoped_and_removes_access(self):
        u = make_user("u3-" + self.id().split(".")[-1])
        cs.add_membership(self.a, u, "owner")
        cs.create_contact(self.a, "Ann", "+15550001010")
        self.assertTrue(cs.soft_delete_account(self.a))
        self.assertIsNone(cs.get_account(self.a))
        self.assertIsNone(cs.get_membership_role(self.a, u))
        self.assertEqual(cs.list_accounts_for_user(u), [])
        with get_connection() as conn:
            n = conn.execute("SELECT COUNT(*) FROM contacts WHERE account_id = ?", (self.a,)).fetchone()[0]
            orphan = conn.execute("SELECT COUNT(*) FROM contacts WHERE account_id IS NULL").fetchone()[0]
        self.assertEqual((n, orphan), (1, 0))

    def test_hard_delete_blocked_by_restrict(self):
        cs.create_contact(self.a, "Ann", "+15550001212")
        with self.assertRaises(Exception):      # outside the block, so the connection rolls back
            with get_connection() as conn:
                conn.execute("DELETE FROM accounts WHERE id = ?", (self.a,))


class TestWhatsAppAccounts(TenancyBase):
    def test_credentials_encrypted_masked_and_scoped(self):
        verify = cs.save_whatsapp_account(self.a, phone_number_id="PN-A", waba_id="W", business_name="A Co",
                                          access_token="EAAB-secret-token-ab12", app_secret="appsecret")
        self.assertTrue(verify)
        with get_connection() as conn:
            row = dict(conn.execute("SELECT * FROM whatsapp_accounts WHERE account_id = ?", (self.a,)).fetchone())
        self.assertNotIn("secret-token", row["access_token_enc"])
        self.assertNotIn(verify, row["verify_token_hash"])
        pub = cs.get_whatsapp_public(self.a)
        self.assertTrue(pub["has_token"])
        self.assertEqual(pub["token_masked"], "…ab12")
        self.assertNotIn("access_token", pub)
        self.assertNotIn("EAAB", str(pub))
        self.assertEqual(cs.get_whatsapp_credentials(self.a)["access_token"], "EAAB-secret-token-ab12")
        self.assertFalse(cs.get_whatsapp_public(self.b)["configured"])
        self.assertEqual(cs.get_whatsapp_credentials(self.b)["access_token"], "")

    def test_empty_token_keeps_old_one_and_update_returns_no_new_verify(self):
        cs.save_whatsapp_account(self.a, phone_number_id="PN-A2", access_token="tok-1111")
        again = cs.save_whatsapp_account(self.a, phone_number_id="PN-A2", business_name="Renamed", access_token="")
        self.assertIsNone(again)
        self.assertEqual(cs.get_whatsapp_credentials(self.a)["access_token"], "tok-1111")
        self.assertEqual(cs.get_whatsapp_public(self.a)["business_name"], "Renamed")

    def test_routing_by_phone_number_id_and_unique(self):
        cs.save_whatsapp_account(self.a, phone_number_id=f"PN-{self.a[:6]}", access_token="t")
        self.assertEqual(cs.find_account_by_phone_number_id(f"PN-{self.a[:6]}"), self.a)
        self.assertIsNone(cs.find_account_by_phone_number_id("unknown"))
        with self.assertRaises(Exception):
            cs.save_whatsapp_account(self.b, phone_number_id=f"PN-{self.a[:6]}", access_token="t")

    def test_verify_token_per_account(self):
        v = cs.save_whatsapp_account(self.a, phone_number_id=f"PV-{self.a[:6]}", access_token="t")
        self.assertTrue(cs.verify_token_matches_any(v))
        self.assertFalse(cs.verify_token_matches_any("gitpulse_webhook_verify"))
        self.assertFalse(cs.verify_token_matches_any(""))
        new = cs.rotate_verify_token(self.a)
        self.assertFalse(cs.verify_token_matches_any(v))
        self.assertTrue(cs.verify_token_matches_any(new))

    def test_ciphertext_not_usable_from_other_account(self):
        cs.save_whatsapp_account(self.a, phone_number_id=f"PX-{self.a[:6]}", access_token="tok-a")
        with get_connection() as conn:
            enc = conn.execute("SELECT access_token_enc FROM whatsapp_accounts WHERE account_id = ?", (self.a,)).fetchone()[0]
        from engine import secrets_box
        with self.assertRaises(secrets_box.SecretsBoxError):
            secrets_box.decrypt(enc, self.b)

    def test_deleted_account_stops_receiving(self):
        cs.save_whatsapp_account(self.a, phone_number_id=f"PD-{self.a[:6]}", access_token="t")
        cs.soft_delete_account(self.a)
        self.assertIsNone(cs.find_account_by_phone_number_id(f"PD-{self.a[:6]}"))


if __name__ == "__main__":
    unittest.main()
