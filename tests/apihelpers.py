"""Shared fixtures: build accounts, users and API callers without any seed data."""
import secrets
import tests._env  # noqa: F401

import crm_store as cs
import database as db
from engine import auth
from server.routes_api import handle_api_request


def new_user(prefix="u", platform_admin=False):
    name = f"{prefix}_{secrets.token_hex(4)}"
    uid = auth.create_user(name, "Passw0rd!xyz", is_platform_admin=platform_admin)
    return dict(auth.get_user_by_id(uid))


def new_account(name=None):
    return cs.create_account(name or f"Acct {secrets.token_hex(3)}")["id"]


def join(account_id, user, role):
    cs.add_membership(account_id, user["id"], role)


class Caller:
    """Calls the API as one user, optionally pinned to an account via X-Account-Id."""
    def __init__(self, user, account_id=None):
        self.user, self.account_id = user, account_id

    def __call__(self, method, path, body=None, query=None, account_id="default", user="default"):
        acct = self.account_id if account_id == "default" else account_id
        hdrs = {"X-Account-Id": acct} if acct else {}
        usr = self.user if user == "default" else user
        return handle_api_request(method, path, query or {}, body or {}, current_user=usr, headers=hdrs)


def setup_db():
    db.init_db()
