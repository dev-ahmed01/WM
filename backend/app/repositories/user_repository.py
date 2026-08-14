"""Repository executing user, role, and department lookup queries against Snowflake."""

# Assumption: Roles default to 'employee' if a user record has no mapped entry in user_roles.

import logging
from typing import Optional, Dict, Any
from app.core.database import get_snowflake_connection
from app.exceptions import WorkMateException
from app.core.security import normalize_role

logger = logging.getLogger("workmate.repository")


class UserRepository:
    """Manages database lookups for users, roles, and department associations in Snowflake."""

    @staticmethod
    def _row_to_user(row: Any) -> Dict[str, Any]:
        return {
            "id": row[0],
            "email": row[1],
            "hashed_password": row[2],
            "department_id": row[3],
            "role": normalize_role(row[4]),
        }

    @staticmethod
    def get_user_by_email(email_or_username: str) -> Optional[Dict[str, Any]]:
        """Fetches a user record by email address or username along with role and department information."""
        key = email_or_username.lower().strip()

        query = """
            SELECT 
                u.id, 
                u.email, 
                u.hashed_password, 
                u.department_id, 
                COALESCE(r.name, 'employee') AS role
            FROM SECURITY.users u
            LEFT JOIN SECURITY.user_roles ur ON u.id = ur.user_id
            LEFT JOIN SECURITY.roles r ON ur.role_id = r.id
            WHERE (LOWER(u.email) = LOWER(%s) OR LOWER(u.id) = LOWER(%s))
              AND LOWER(COALESCE(u.status, 'active')) = 'active'
            ORDER BY CASE LOWER(COALESCE(r.name, 'employee'))
                WHEN 'admin' THEN 1
                WHEN 'administrator' THEN 1
                WHEN 'manager' THEN 2
                WHEN 'supervisor' THEN 2
                ELSE 3
            END
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (key, key))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return UserRepository._row_to_user(row)
        except Exception as exc:
            raise WorkMateException(message=f"Database query failed while fetching user by email: {str(exc)}") from exc

    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
        """Fetches a user record by user ID along with role and department information."""
        query = """
            SELECT 
                u.id, 
                u.email, 
                u.hashed_password, 
                u.department_id, 
                COALESCE(r.name, 'employee') AS role
            FROM SECURITY.users u
            LEFT JOIN SECURITY.user_roles ur ON u.id = ur.user_id
            LEFT JOIN SECURITY.roles r ON ur.role_id = r.id
            WHERE u.id = %s
              AND LOWER(COALESCE(u.status, 'active')) = 'active'
            ORDER BY CASE LOWER(COALESCE(r.name, 'employee'))
                WHEN 'admin' THEN 1
                WHEN 'administrator' THEN 1
                WHEN 'manager' THEN 2
                WHEN 'supervisor' THEN 2
                ELSE 3
            END
            LIMIT 1
        """
        try:
            with get_snowflake_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (user_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return UserRepository._row_to_user(row)
        except Exception as exc:
            raise WorkMateException(message=f"Database query failed while fetching user by ID: {str(exc)}") from exc
