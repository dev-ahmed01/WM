"""Organization-scoped employee administration.

Every method takes the acting administrator's organization (resolved from the
database, never from request input) and refuses to read or write users whose
department belongs to another organization. A missing organization fails
closed.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import psycopg

from app.core.database import get_postgres_connection
from app.core.security import hash_password

LANGUAGES = {"en", "hi", "hinglish"}
INVITE_TTL = timedelta(days=7)
RECOVERY_TTL = timedelta(hours=1)


class OrgScopeError(Exception):
    """Target is outside the acting administrator's organization (reported as not found)."""


class OrgValidationError(Exception):
    pass


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def organization_of_user(cur, user_id: str) -> Optional[str]:
    cur.execute(
        "SELECT d.organization_id FROM security.users u JOIN security.departments d "
        "ON d.id = u.department_id WHERE u.id = %s",
        (user_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _role_id(cur, role: str) -> str:
    cur.execute("SELECT id FROM security.roles WHERE LOWER(name)=%s ORDER BY (id = %s) DESC LIMIT 1",
                (role, f"role_{role}"))
    row = cur.fetchone()
    if not row:
        raise OrgValidationError(f"role '{role}' is not configured")
    return row[0]


def _require_org(cur, actor_id: str) -> str:
    org = organization_of_user(cur, actor_id)
    if not org:
        raise OrgScopeError("organization not configured")
    return org


_EMP_COLS = """u.id, u.email, u.full_name, u.status, u.department_id, u.warehouse_id,
  u.supervisor_id, u.preferred_language, jp.code, COALESCE(r.name,'employee'), u.is_demo"""
_EMP_FROM = """FROM security.users u
  JOIN security.departments d ON d.id = u.department_id
  LEFT JOIN security.job_profiles jp ON jp.id = u.job_profile_id
  LEFT JOIN security.user_roles ur ON ur.user_id = u.id
  LEFT JOIN security.roles r ON r.id = ur.role_id"""


def _row(r) -> Dict[str, Any]:
    return {
        "id": r[0], "email": r[1], "full_name": r[2], "status": r[3],
        "department_id": r[4], "warehouse_id": r[5], "supervisor_id": r[6],
        "preferred_language": r[7], "job_profile": r[8], "role": r[9], "is_demo": r[10],
    }


class OrgRepository:
    @staticmethod
    def overview(actor_id: str) -> Dict[str, Any]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            org = _require_org(cur, actor_id)
            cur.execute("SELECT id, code, name, is_demo FROM security.organizations WHERE id=%s", (org,))
            o = cur.fetchone()
            cur.execute("SELECT id, code, name FROM security.warehouses WHERE organization_id=%s ORDER BY code", (org,))
            wh = [{"id": a, "code": b, "name": c} for a, b, c in cur.fetchall()]
            cur.execute("SELECT id, code, name, warehouse_id FROM security.departments WHERE organization_id=%s ORDER BY code", (org,))
            dp = [{"id": a, "code": b, "name": c, "warehouse_id": w} for a, b, c, w in cur.fetchall()]
            cur.execute("SELECT code, name_en, name_hi FROM security.job_profiles ORDER BY code")
            jp = [{"code": a, "name_en": b, "name_hi": c} for a, b, c in cur.fetchall()]
        return {"organization": {"id": o[0], "code": o[1], "name": o[2], "is_demo": o[3]},
                "warehouses": wh, "departments": dp, "job_profiles": jp}

    @staticmethod
    def list_employees(actor_id: str, q: str = "", limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            org = _require_org(cur, actor_id)
            like = f"%{q.strip().lower()}%"
            cur.execute(
                f"SELECT {_EMP_COLS} {_EMP_FROM} WHERE d.organization_id=%s "
                "AND (%s = '%%' OR LOWER(u.email) LIKE %s OR LOWER(COALESCE(u.full_name,'')) LIKE %s) "
                "ORDER BY u.email LIMIT %s OFFSET %s",
                (org, like, like, like, limit, offset),
            )
            return [_row(r) for r in cur.fetchall()]

    @staticmethod
    def _get_in_org(cur, org: str, user_id: str):
        cur.execute(f"SELECT {_EMP_COLS} {_EMP_FROM} WHERE u.id=%s AND d.organization_id=%s", (user_id, org))
        r = cur.fetchone()
        if not r:
            raise OrgScopeError("employee not found")
        return r

    @staticmethod
    def get_employee(actor_id: str, user_id: str) -> Dict[str, Any]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            org = _require_org(cur, actor_id)
            return _row(OrgRepository._get_in_org(cur, org, user_id))

    @staticmethod
    def _resolve_refs(cur, org: str, data: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if data.get("department_id") is not None:
            cur.execute("SELECT 1 FROM security.departments WHERE id=%s AND organization_id=%s",
                        (data["department_id"], org))
            if not cur.fetchone():
                raise OrgScopeError("department not found")
            out["department_id"] = data["department_id"]
        if data.get("warehouse_id") is not None:
            cur.execute("SELECT 1 FROM security.warehouses WHERE id=%s AND organization_id=%s",
                        (data["warehouse_id"], org))
            if not cur.fetchone():
                raise OrgScopeError("warehouse not found")
            out["warehouse_id"] = data["warehouse_id"]
        if data.get("supervisor_id") is not None:
            cur.execute("SELECT 1 FROM security.users u JOIN security.departments d ON d.id=u.department_id "
                        "WHERE u.id=%s AND d.organization_id=%s", (data["supervisor_id"], org))
            if not cur.fetchone():
                raise OrgScopeError("supervisor not found")
            out["supervisor_id"] = data["supervisor_id"]
        if data.get("job_profile") is not None:
            cur.execute("SELECT id FROM security.job_profiles WHERE code=%s", (data["job_profile"],))
            r = cur.fetchone()
            if not r:
                raise OrgValidationError("unknown job profile")
            out["job_profile_id"] = r[0]
        if data.get("preferred_language") is not None:
            if data["preferred_language"] not in LANGUAGES:
                raise OrgValidationError("unsupported language")
            out["preferred_language"] = data["preferred_language"]
        if data.get("full_name") is not None:
            out["full_name"] = data["full_name"].strip()[:255]
        return out

    @staticmethod
    def create_invited(actor_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create an employee in 'invited' state with an unusable password; returns a one-time token."""
        role = data.get("role", "employee")
        if role not in ("employee", "manager"):
            raise OrgValidationError("administrators cannot be created through this endpoint")
        user_id = f"usr_{uuid.uuid4().hex[:16]}"
        token = secrets.token_urlsafe(32)
        try:
            with get_postgres_connection() as conn, conn.cursor() as cur:
                org = _require_org(cur, actor_id)
                refs = OrgRepository._resolve_refs(cur, org, data)
                if "department_id" not in refs:
                    raise OrgValidationError("department is required")
                cur.execute(
                    "INSERT INTO security.users (id,email,hashed_password,department_id,full_name,status,"
                    "job_profile_id,warehouse_id,supervisor_id,preferred_language) "
                    "VALUES (%s,%s,%s,%s,%s,'invited',%s,%s,%s,%s)",
                    (user_id, data["email"].strip().lower(), hash_password(secrets.token_urlsafe(32)),
                     refs["department_id"], refs.get("full_name"), refs.get("job_profile_id"),
                     refs.get("warehouse_id"), refs.get("supervisor_id"),
                     refs.get("preferred_language", "en")),
                )
                cur.execute("INSERT INTO security.user_roles (user_id, role_id) VALUES (%s,%s)",
                            (user_id, _role_id(cur, role)))
                OrgRepository._issue_token(cur, user_id, "invite", token, INVITE_TTL, actor_id)
                emp = _row(OrgRepository._get_in_org(cur, org, user_id))
        except psycopg.errors.UniqueViolation as exc:
            raise OrgValidationError("email already registered") from exc
        except psycopg.errors.CheckViolation as exc:
            raise OrgScopeError("cross-organization reference rejected") from exc
        return {"employee": emp, "one_time_token": token, "expires_in_hours": int(INVITE_TTL.total_seconds() // 3600)}

    @staticmethod
    def _issue_token(cur, user_id: str, purpose: str, token: str, ttl: timedelta, created_by: Optional[str]) -> None:
        cur.execute("UPDATE security.account_tokens SET used_at = now() "
                    "WHERE user_id=%s AND purpose=%s AND used_at IS NULL", (user_id, purpose))
        cur.execute(
            "INSERT INTO security.account_tokens (id,user_id,purpose,token_hash,expires_at,created_by) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (uuid.uuid4().hex, user_id, purpose, _digest(token),
             datetime.now(timezone.utc) + ttl, created_by),
        )

    @staticmethod
    def update_employee(actor_id: str, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with get_postgres_connection() as conn, conn.cursor() as cur:
                org = _require_org(cur, actor_id)
                OrgRepository._get_in_org(cur, org, user_id)
                refs = OrgRepository._resolve_refs(cur, org, data)
                if refs:
                    sets = ", ".join(f"{k}=%s" for k in refs)
                    cur.execute(f"UPDATE security.users SET {sets} WHERE id=%s", (*refs.values(), user_id))
                role = data.get("role")
                if role is not None:
                    if role not in ("employee", "manager"):
                        raise OrgValidationError("invalid role")
                    cur.execute("SELECT 1 FROM security.user_roles ur JOIN security.roles r ON r.id=ur.role_id "
                                "WHERE ur.user_id=%s AND LOWER(r.name)='admin'", (user_id,))
                    if cur.fetchone():
                        raise OrgValidationError("administrator roles are not editable here")
                    cur.execute("DELETE FROM security.user_roles WHERE user_id=%s", (user_id,))
                    cur.execute("INSERT INTO security.user_roles (user_id, role_id) VALUES (%s,%s)",
                                (user_id, _role_id(cur, role)))
                return _row(OrgRepository._get_in_org(cur, org, user_id))
        except psycopg.errors.CheckViolation as exc:
            raise OrgScopeError("cross-organization reference rejected") from exc

    @staticmethod
    def set_active(actor_id: str, user_id: str, active: bool) -> Dict[str, Any]:
        with get_postgres_connection() as conn, conn.cursor() as cur:
            org = _require_org(cur, actor_id)
            cur.execute("SELECT status FROM security.users WHERE id=%s", (user_id,))
            OrgRepository._get_in_org(cur, org, user_id)
            if user_id == actor_id and not active:
                raise OrgValidationError("administrators cannot deactivate themselves")
            cur.execute("UPDATE security.users SET status=%s WHERE id=%s",
                        ("active" if active else "inactive", user_id))
            if not active:
                # Deactivation must end every live session immediately.
                cur.execute("UPDATE security.refresh_sessions SET revoked_at = now() "
                            "WHERE user_id=%s AND revoked_at IS NULL", (user_id,))
            return _row(OrgRepository._get_in_org(cur, org, user_id))

    @staticmethod
    def issue_recovery(actor_id: str, user_id: str) -> Dict[str, Any]:
        token = secrets.token_urlsafe(32)
        with get_postgres_connection() as conn, conn.cursor() as cur:
            org = _require_org(cur, actor_id)
            OrgRepository._get_in_org(cur, org, user_id)
            OrgRepository._issue_token(cur, user_id, "recovery", token, RECOVERY_TTL, actor_id)
        return {"one_time_token": token, "expires_in_hours": 1}

    @staticmethod
    def redeem_token(token: str, new_password: str) -> bool:
        """Set a password from an unused, unexpired token and activate the account."""
        with get_postgres_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE security.account_tokens SET used_at = now() "
                "WHERE token_hash=%s AND used_at IS NULL AND expires_at > now() "
                "RETURNING user_id, purpose", (_digest(token),))
            r = cur.fetchone()
            if not r:
                return False
            user_id, purpose = r
            cur.execute("SELECT status FROM security.users WHERE id=%s FOR UPDATE", (user_id,))
            status = cur.fetchone()[0]
            if status == "inactive":
                raise OrgValidationError("account is deactivated")
            cur.execute("UPDATE security.users SET hashed_password=%s, status='active' WHERE id=%s",
                        (hash_password(new_password), user_id))
            cur.execute("UPDATE security.refresh_sessions SET revoked_at = now() "
                        "WHERE user_id=%s AND revoked_at IS NULL", (user_id,))
            return True
