"""Measured operational metrics, computed only from persisted events, plus a separate ROI *estimator*.

Rules this module enforces:
- Every number carries its definition. A metric the data cannot support is returned as `null` with a reason,
  never as an invented value (for example response latency is not persisted today).
- "Answered" is never reported as "resolved". Resolution needs a human signal (a closed case, a published SOP).
- Estimated savings are computed only from caller-supplied assumptions and are returned under a different key
  from measured values; the two are never added together.
"""
from __future__ import annotations

from typing import Any, Dict, List

import statistics

from app.core.database import get_postgres_connection, get_transaction

DEFINITIONS = {
    "active_employees": "Distinct employees who sent at least one message in the period.",
    "questions_received": "Messages sent by employees in the period (any kind: questions, confirmations, commands).",
    "matched_an_approved_sop": "Employee messages routed to an approved SOP or workflow step. This means a procedure was found, not that the problem was solved.",
    "knowledge_gaps_raised": "Employee messages for which no approved SOP matched (a case was opened or an existing gap was counted).",
    "safety_stops": "Employee messages that triggered the stop-work safety response.",
    "live_data_declined": "Questions about stock levels, bin locations or shipment status that WorkMate declined because it has no live data.",
    "actions_confirmed": "Discrepancy reports the employee confirmed and WorkMate recorded.",
    "gap_rate_pct": "knowledge_gaps_raised / questions_received.",
    "workflows_started": "Guided workflow sessions started in the period.",
    "workflows_completed": "Sessions that reached the completed state (explicit attestations and decisions recorded).",
    "workflow_completion_rate_pct": "workflows_completed / workflows_started. Sessions still in progress count as not completed.",
    "escalations_opened": "Support escalations created in the period.",
    "escalations_resolved": "Of those created in the period, how many a human has resolved.",
    "median_escalation_resolution_hours": "Median of (resolved - created) over escalations created in the period that are resolved.",
    "exception_cases_opened": "Blocked-work cases raised by employees in the period.",
    "exception_cases_closed": "Of those opened in the period, closed after corrective work, evidence review and independent site acceptance.",
    "median_exception_closure_hours": "Median of (closed - opened) over cases opened in the period and closed.",
    "gaps_closed_by_published_sop": "Knowledge gaps resolved because an approved SOP was published for them.",
    "handovers_submitted": "Shift handovers or discrepancy reports submitted in the period.",
    "conversations_total": "Conversations in which an employee sent at least one message in the period.",
    "conversations_confirmed_resolved": "Conversations where the employee marked an answer helpful and did not ask for a person or flag an answer.",
    "self_service_resolution_pct": "conversations_confirmed_resolved / conversations_total. Only employee-confirmed outcomes count; an answer nobody rated is not counted as resolved.",
    "answers_rated_helpful": "Answers employees marked helpful.",
    "answers_rated_not_helpful": "Answers employees marked not helpful.",
    "cases_opened": "Requests for a person, unanswered questions and flagged answers opened in the period.",
    "cases_resolved": "Of those opened in the period, how many staff resolved or closed.",
    "median_case_resolution_hours": "Median of (resolved - opened) over cases opened in the period that staff resolved.",
    "messages_in_devanagari": "Employee messages written in Hindi (Devanagari script). Hindi written in English letters cannot be told apart from English and counts below.",
    "messages_in_latin_script": "Employee messages written in English letters (English or Hinglish).",
}
UNAVAILABLE = {
    "response_latency_ms": "Not persisted: per-response latency is not stored, so no number is reported.",
    "answer_helpfulness": "Not collected: employees are not yet asked 'did this help?' outside pilot departments.",
}


def _pct(part: int, whole: int):
    return round(100.0 * part / whole, 1) if whole else None


def summary(department_ids: List[str], days: int) -> Dict[str, Any]:
    days = max(1, min(int(days), 365))
    if not department_ids:
        return {"period_days": days, "metrics": {}, "definitions": DEFINITIONS, "unavailable": UNAVAILABLE}
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT
                 COUNT(DISTINCT c.user_id) FILTER (WHERE m.sender='employee'),
                 COUNT(*) FILTER (WHERE m.sender='employee'),
                 COUNT(*) FILTER (WHERE m.sender='employee' AND (m.intent LIKE 'WORKFLOW\\_%%' OR m.intent IN ('SOP_CATALOG_LOOKUP','WORKFLOW_SUGGESTIONS'))),
                 COUNT(*) FILTER (WHERE m.sender='employee' AND m.intent='KNOWLEDGE_GAP'),
                 COUNT(*) FILTER (WHERE m.sender='employee' AND m.intent='SAFETY_STOP'),
                 COUNT(*) FILTER (WHERE m.sender='employee' AND m.intent='LIVE_DATA_UNAVAILABLE'),
                 COUNT(*) FILTER (WHERE m.sender='employee' AND m.intent='ACTION_CONFIRMED')
               FROM workmate_copilot.conversation_messages m
               JOIN workmate_copilot.conversations c ON c.id=m.conversation_id
               WHERE c.department_id = ANY(%s) AND m.created_at >= now() - make_interval(days => %s)""",
            (department_ids, days))
        active, questions, matched, gaps, safety, live, actions = cur.fetchone()

        cur.execute(
            """SELECT COUNT(DISTINCT c.id),
                      COUNT(DISTINCT c.id) FILTER (WHERE EXISTS (SELECT 1 FROM workmate_copilot.message_feedback f
                           JOIN workmate_copilot.conversation_messages fm ON fm.id=f.message_id
                           WHERE fm.conversation_id=c.id AND f.rating='helpful')
                         AND NOT EXISTS (SELECT 1 FROM workmate_copilot.message_feedback f2
                           JOIN workmate_copilot.conversation_messages fm2 ON fm2.id=f2.message_id
                           WHERE fm2.conversation_id=c.id AND f2.rating='not_helpful')
                         AND NOT EXISTS (SELECT 1 FROM knowledge_studio.knowledge_gaps g
                           WHERE g.conversation_id=c.id AND g.kind IN ('human_request','incorrect_answer')))
               FROM workmate_copilot.conversations c
               WHERE c.department_id = ANY(%s) AND EXISTS (SELECT 1 FROM workmate_copilot.conversation_messages m
                     WHERE m.conversation_id=c.id AND m.sender='employee' AND m.created_at >= now() - make_interval(days => %s))""",
            (department_ids, days))
        convs, convs_ok = cur.fetchone()

        cur.execute(
            """SELECT COUNT(*) FILTER (WHERE f.rating='helpful'), COUNT(*) FILTER (WHERE f.rating='not_helpful')
               FROM workmate_copilot.message_feedback f
               WHERE f.department_id = ANY(%s) AND f.created_at >= now() - make_interval(days => %s)""",
            (department_ids, days))
        rated_up, rated_down = cur.fetchone()

        cur.execute(
            """SELECT COUNT(*), COUNT(*) FILTER (WHERE status IN ('resolved','closed','dismissed')),
                      percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (resolved_at - created_at))/3600.0)
                        FILTER (WHERE resolved_at IS NOT NULL)
               FROM knowledge_studio.knowledge_gaps
               WHERE department_id = ANY(%s) AND created_at >= now() - make_interval(days => %s)""",
            (department_ids, days))
        support_opened, support_resolved, support_median = cur.fetchone()

        cur.execute(
            """SELECT COUNT(*) FILTER (WHERE m.message_text ~ '[\u0900-\u097F]'),
                      COUNT(*) FILTER (WHERE m.message_text !~ '[\u0900-\u097F]')
               FROM workmate_copilot.conversation_messages m JOIN workmate_copilot.conversations c ON c.id=m.conversation_id
               WHERE m.sender='employee' AND c.department_id = ANY(%s) AND m.created_at >= now() - make_interval(days => %s)""",
            (department_ids, days))
        msgs_hi, msgs_latin = cur.fetchone()

        # What people actually ask, in their own words (aggregated by wording; confirmations like "yes" are not questions).
        cur.execute(
            """SELECT lower(btrim(m.message_text)) AS q, COUNT(*) AS n, COUNT(DISTINCT c.user_id) AS people
               FROM workmate_copilot.conversation_messages m JOIN workmate_copilot.conversations c ON c.id=m.conversation_id
               WHERE m.sender='employee' AND c.department_id = ANY(%s) AND m.created_at >= now() - make_interval(days => %s)
                 AND length(btrim(m.message_text)) >= 8
                 AND lower(btrim(m.message_text)) NOT IN ('yes','no','done','yes.','no.','ok','okay','thanks','thank you')
               GROUP BY 1 ORDER BY n DESC, q LIMIT 8""",
            (department_ids, days))
        top_questions = [{"question": q[:140], "count": n, "people": people} for q, n, people in cur.fetchall()]

        cur.execute(
            """SELECT COUNT(*), COUNT(*) FILTER (WHERE s.status='completed')
               FROM workmate_copilot.workflow_sessions s
               JOIN workmate_copilot.conversations c ON c.id=s.conversation_id
               WHERE c.department_id = ANY(%s) AND s.started_at >= now() - make_interval(days => %s)""",
            (department_ids, days))
        started, completed = cur.fetchone()

        cur.execute(
            """SELECT COUNT(*), COUNT(*) FILTER (WHERE e.status='resolved'),
                      percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (e.resolved_at - e.created_at))/3600.0)
                        FILTER (WHERE e.status='resolved' AND e.resolved_at IS NOT NULL)
               FROM workmate_copilot.escalation_records e
               LEFT JOIN workmate_copilot.conversation_messages m ON m.id=e.conversation_message_id
               LEFT JOIN workmate_copilot.workflow_sessions ws ON ws.id=e.session_id
               JOIN workmate_copilot.conversations c ON c.id=COALESCE(m.conversation_id, ws.conversation_id)
               WHERE c.department_id = ANY(%s) AND e.created_at >= now() - make_interval(days => %s)""",
            (department_ids, days))
        esc_opened, esc_resolved, esc_median = cur.fetchone()

        cur.execute(
            """SELECT COUNT(*) FILTER (WHERE status='resolved')
               FROM knowledge_studio.knowledge_gaps
               WHERE department_id = ANY(%s) AND updated_at >= now() - make_interval(days => %s)""",
            (department_ids, days))
        gaps_closed = cur.fetchone()[0]


    # work_exceptions and shift_handovers are protected by row-level security keyed on one department at a time.
    # Querying them without that context returns zero rows for the restricted runtime login, which would silently
    # under-report. So: one tenant-scoped transaction per department, combined here.
    cases_opened = cases_closed = handovers = 0
    closure_hours: List[float] = []
    for dept in department_ids:
        with get_transaction(dept) as cur:
            cur.execute(
                """SELECT status, EXTRACT(EPOCH FROM (closed_at - created_at))/3600.0
                   FROM workmate_copilot.work_exceptions
                   WHERE department_id=%s AND created_at >= now() - make_interval(days => %s)""", (dept, days))
            for status, hours in cur.fetchall():
                cases_opened += 1
                if status == "closed":
                    cases_closed += 1
                    if hours is not None:
                        closure_hours.append(float(hours))
            cur.execute(
                """SELECT COUNT(*) FROM workmate_copilot.shift_handovers
                   WHERE department_id=%s AND created_at >= now() - make_interval(days => %s)""", (dept, days))
            handovers += cur.fetchone()[0]
    cases_median = statistics.median(closure_hours) if closure_hours else None

    rnd = lambda v: round(float(v), 1) if v is not None else None
    metrics = {
        "active_employees": active, "questions_received": questions, "matched_an_approved_sop": matched,
        "knowledge_gaps_raised": gaps, "gap_rate_pct": _pct(gaps, questions), "safety_stops": safety,
        "live_data_declined": live, "actions_confirmed": actions,
        "workflows_started": started, "workflows_completed": completed,
        "workflow_completion_rate_pct": _pct(completed, started),
        "escalations_opened": esc_opened, "escalations_resolved": esc_resolved,
        "median_escalation_resolution_hours": rnd(esc_median),
        "exception_cases_opened": cases_opened, "exception_cases_closed": cases_closed,
        "median_exception_closure_hours": rnd(cases_median),
        "gaps_closed_by_published_sop": gaps_closed, "handovers_submitted": handovers,
        "conversations_total": convs, "conversations_confirmed_resolved": convs_ok,
        "self_service_resolution_pct": _pct(convs_ok, convs),
        "answers_rated_helpful": rated_up, "answers_rated_not_helpful": rated_down,
        "cases_opened": support_opened, "cases_resolved": support_resolved, "median_case_resolution_hours": rnd(support_median),
        "messages_in_devanagari": msgs_hi, "messages_in_latin_script": msgs_latin,
    }
    return {"period_days": days, "departments": department_ids, "metrics": metrics, "top_questions": top_questions,
            "definitions": {k: DEFINITIONS[k] for k in metrics}, "unavailable": UNAVAILABLE}


def roi_estimate(*, employees: int, questions_per_employee_per_week: float, minutes_per_supervisor_interruption: float,
                 share_answered_without_supervisor_pct: float, loaded_hourly_cost: float, weeks: int = 52) -> Dict[str, Any]:
    """Pure arithmetic over the caller's assumptions. Nothing here is measured; every input is echoed back."""
    for name, value in (("employees", employees), ("questions_per_employee_per_week", questions_per_employee_per_week),
                        ("minutes_per_supervisor_interruption", minutes_per_supervisor_interruption),
                        ("loaded_hourly_cost", loaded_hourly_cost)):
        if value < 0:
            raise ValueError(f"{name} cannot be negative")
    if not 0 <= share_answered_without_supervisor_pct <= 100:
        raise ValueError("share_answered_without_supervisor_pct must be between 0 and 100")
    questions_year = employees * questions_per_employee_per_week * weeks
    avoided = questions_year * share_answered_without_supervisor_pct / 100.0
    hours = avoided * minutes_per_supervisor_interruption / 60.0
    return {
        "kind": "ESTIMATE_FROM_ASSUMPTIONS",
        "assumptions": {"employees": employees, "questions_per_employee_per_week": questions_per_employee_per_week,
                        "minutes_per_supervisor_interruption": minutes_per_supervisor_interruption,
                        "share_answered_without_supervisor_pct": share_answered_without_supervisor_pct,
                        "loaded_hourly_cost": loaded_hourly_cost, "weeks": weeks},
        "estimated_questions_per_year": round(questions_year),
        "estimated_supervisor_interruptions_avoided": round(avoided),
        "estimated_supervisor_hours_saved": round(hours, 1),
        "estimated_cost_saved": round(hours * loaded_hourly_cost, 2),
        "caveat": "These figures follow only from the assumptions above. They are not measured outcomes and not a guarantee; "
                  "measure the real answer-without-supervisor share in a pilot before relying on them.",
    }
