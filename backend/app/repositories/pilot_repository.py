"""Pilot review repository: bounded, tenant-scoped, structured signals only."""
from __future__ import annotations

from uuid import uuid4
from app.core.database import get_postgres_connection


class PilotFeedbackRepository:
    @staticmethod
    def save(department_id: str, reporter_id: str, surface: str, verdict: str,
             issue: str, daily_limit: int) -> str | None:
        identifier = uuid4().hex
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute(
                        "SELECT set_config('workmate.department_id', %s, true)",
                        (department_id,),
                    )
                    # Serialize this user's attempts across API replicas; avoid
                    # a concurrent submit bypassing the daily cohort limit.
                    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (reporter_id,))
                    cur.execute(
                        """INSERT INTO shared.pilot_feedback
                           (id,department_id,reporter_user_id,surface,verdict,issue)
                           SELECT %s,%s,%s,%s,%s,%s
                           WHERE (SELECT count(*) FROM shared.pilot_feedback
                                  WHERE reporter_user_id=%s
                                  AND created_at >= CURRENT_DATE) < %s
                           RETURNING id""",
                        (identifier, department_id, reporter_id, surface, verdict,
                         issue, reporter_id, daily_limit),
                    )
                    item = cur.fetchone()
                    cur.execute("COMMIT")
                    return str(item[0]) if item else None
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def summary(department_id: str, days: int = 14) -> dict:
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute(
                        "SELECT set_config('workmate.department_id', %s, true)",
                        (department_id,),
                    )
                    cur.execute(
                    """SELECT surface,verdict,issue,count(*)
                       FROM shared.pilot_feedback
                       WHERE department_id=%s
                         AND created_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                       GROUP BY surface,verdict,issue
                       ORDER BY surface,verdict,issue""",
                    (department_id, days),
                )
                    counts = [
                        {"surface": str(row[0]), "verdict": str(row[1]),
                         "issue": str(row[2]), "count": int(row[3])}
                        for row in cur.fetchall()
                    ]
                    cur.execute("COMMIT")
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
        total = sum(item["count"] for item in counts)
        needs_review = sum(item["count"] for item in counts if item["verdict"] == "needs_review")
        return {
            "window_days": days, "total": total, "needs_review": needs_review,
            "helpful": total - needs_review, "counts": counts,
            "privacy": "Department aggregates only. No reporters, questions or transcripts.",
        }
