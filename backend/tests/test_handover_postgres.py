"""Disposable Postgres acceptance for shift handover tenant RLS and audit review."""
from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from app.core.config import settings
from app.repositories.handover_repository import HandoverRepository


@pytest.mark.live_integration
def test_handover_is_owner_scoped_and_review_is_atomic():
    suffix = uuid4().hex[:10]
    dep_a, dep_b = "hov_a_" + suffix, "hov_b_" + suffix
    worker, manager, outsider = ("hw_" + suffix, "hm_" + suffix, "ho_" + suffix)
    conversation = "conv_h_" + suffix
    other_conversation = "conv_o_" + suffix
    users = [worker, manager, outsider]
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            for dep in (dep_a, dep_b):
                cur.execute("INSERT INTO security.departments(id,code,name) VALUES(%s,%s,%s)",
                            (dep,dep.upper(),dep))
            for user, dep in ((worker, dep_a), (manager, dep_a), (outsider, dep_b)):
                cur.execute("""INSERT INTO security.users(id,email,hashed_password,department_id)
                               VALUES(%s,%s,'synthetic',%s)""",
                            (user,user + "@example.test",dep))
            for conv, person, dep in ((conversation, worker, dep_a),
                                      (other_conversation, outsider, dep_b)):
                cur.execute("""INSERT INTO workmate_copilot.conversations
                               (id,user_id,department_id) VALUES(%s,%s,%s)""",
                            (conv,person,dep))
    try:
        assert HandoverRepository.submit(dep_a, worker, other_conversation, "Night lead",
                "blocked_supervisor","damage","high","Quarantine carton for review.","") is None
        submitted = HandoverRepository.submit(
            dep_a, worker, conversation, "Night shift lead", "blocked_supervisor",
            "damage", "high", "Quarantine carton for review.", "Damaged seal")
        assert submitted and submitted["status"] == "submitted"
        assert submitted["snapshot_state"]["workflow_status"] is None
        assert HandoverRepository.list(dep_b, outsider, True) == []
        assert len(HandoverRepository.list(dep_a, worker, False)) == 1
        assert len(HandoverRepository.list(dep_a, manager, True)) == 1
        assert HandoverRepository.review(dep_a, worker, submitted["id"],
                 "acknowledged","Self-review must be rejected.") is None
        assert HandoverRepository.review(dep_b, outsider, submitted["id"],
                 "acknowledged","Wrong department must be rejected.") is None
        assert HandoverRepository.claim(dep_a, worker, submitted["id"]) is None
        assert HandoverRepository.claim(dep_b, outsider, submitted["id"]) is None
        claimed = HandoverRepository.claim(dep_a, manager, submitted["id"])
        assert claimed and claimed["assigned_to_user_id"] == manager
        assert HandoverRepository.claim(dep_a, manager, submitted["id"]) is None
        accepted = HandoverRepository.review(dep_a, manager, submitted["id"],
                 "follow_up_requested","Keep shipment segregated until a supervisor decides.")
        assert accepted and accepted["status"] == "follow_up_requested"
        assert accepted["reviewed_by"] == manager
        assert HandoverRepository.review(dep_a, manager, submitted["id"],
                 "acknowledged","Double review must fail.") is None
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT action,actor_user_id FROM workmate_copilot.shift_handover_events
                               WHERE handover_id=%s ORDER BY created_at""", (submitted["id"],))
                assert cur.fetchall() == [("submitted",worker),("claimed",manager),("follow_up_requested",manager)]
                cur.execute("BEGIN")
                cur.execute("SET LOCAL ROLE workmate_scoped_reader")
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.shift_handovers WHERE id=%s", (submitted["id"],))
                assert cur.fetchone() == (0,), "Non-owner role must not see unscoped record"
                cur.execute("SELECT set_config('workmate.department_id',%s,true)", (dep_b,))
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.shift_handovers WHERE id=%s", (submitted["id"],))
                assert cur.fetchone() == (0,), "Different tenant must not see record"
                cur.execute("SELECT set_config('workmate.department_id',%s,true)", (dep_a,))
                cur.execute("SELECT COUNT(*) FROM workmate_copilot.shift_handovers WHERE id=%s", (submitted["id"],))
                assert cur.fetchone() == (1,)
                cur.execute("ROLLBACK")
    finally:
        with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM workmate_copilot.shift_handover_events WHERE department_id=%s", (dep_a,))
                cur.execute("DELETE FROM workmate_copilot.shift_handovers WHERE department_id=%s", (dep_a,))
                cur.execute("DELETE FROM workmate_copilot.conversations WHERE id=ANY(%s)",
                            ([conversation,other_conversation],))
                cur.execute("DELETE FROM security.users WHERE id=ANY(%s)", (users,))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)", ([dep_a,dep_b],))
