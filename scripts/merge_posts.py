"""Give every older `posts` row its `blog_plan` row, so there is one set of posts.

    python -m scripts.merge_posts            # dry run: counts per account and state, reads only
    python -m scripts.merge_posts --apply    # add the rows

Reads DATABASE_URL like the app. Adds nothing twice and changes no `posts` row.
Undo: DELETE FROM blog_plan WHERE origin = 'legacy'."""
import sys
from collections import Counter
from typing import List, Tuple

import database as db
from engine import blog_plan


def plan() -> List[Tuple[int, str, str]]:
    """(post id, account name, state) for each post still to be added. Works before the schema change."""
    with db.get_connection() as conn:
        rows = conn.execute("""
            SELECT p.id, a.name, p.status FROM posts p
            JOIN projects j ON j.id = p.project_id JOIN accounts a ON a.id = j.account_id
            WHERE a.status != 'deleted' AND p.status != 'deleted'
              AND NOT EXISTS (SELECT 1 FROM blog_plan b WHERE b.post_id = p.id)
            ORDER BY p.id""").fetchall()
    return [(r["id"], r["name"], blog_plan.merged_status(r["status"])) for r in rows]


def run(apply: bool = False) -> int:
    todo = plan()
    for (account, state), n in sorted(Counter((a, s) for _, a, s in todo).items()):
        print(f"{account}: {state} = {n}")
    print(f"{len(todo)} post(s) to add." if not apply else f"Adding {len(todo)} post(s).")
    if apply:
        added = sum(blog_plan.mirror(post_id, "legacy") is not None for post_id, _, _ in todo)
        print(f"Added {added}.")
    return len(todo)


if __name__ == "__main__":
    run(apply="--apply" in sys.argv[1:])
