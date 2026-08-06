"""Role and Department Access Control Middleware Factories.

Enforces role-based access control (RBAC) and department-scoped data access rules,
raising ApiErrorPayload HTTP 403 exceptions on permission failures.
"""

# Assumption: Admins bypass department-scope checks in require_own_department, while non-admins must match the target department_id.

from typing import Dict, Any, Union, List
from fastapi import Depends, Request, HTTPException, status

from app.middleware.auth_middleware import get_current_user
from app.core.security import normalize_role


def require_role(*roles: Union[str, List[str], tuple]):
    """Dependency factory enforcing role-based access control against claims in current_user.

    Usage:
        @app.get("/admin", dependencies=[Depends(require_role("admin"))])
        @app.get("/hub", dependencies=[Depends(require_role("admin", "manager"))])
    """
    allowed_roles = set()
    for r in roles:
        if isinstance(r, (list, tuple, set)):
            allowed_roles.update(normalize_role(item) for item in r)
        else:
            allowed_roles.add(normalize_role(r))

    async def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = normalize_role(current_user.get("role", ""))
        if not user_role or user_role not in allowed_roles:
            allowed_str = ", ".join(sorted(allowed_roles))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": "AUTH_FORBIDDEN",
                    "message": f"User with role '{user_role}' is not authorized for this resource. Required role(s): {allowed_str}.",
                    "details": {"required_roles": list(allowed_roles), "user_role": user_role},
                },
            )
        return current_user

    return role_checker


def require_own_department(department_id_param: str = "department_id"):
    """Dependency factory checking if requested department scope matches the user's department_id claim.

    Admins automatically bypass department restrictions. Non-admin users whose department_id
    does not match the target department_id parameter will receive HTTP 403 AUTH_FORBIDDEN.

    Usage:
        @app.get("/departments/{department_id}/sops", dependencies=[Depends(require_own_department("department_id"))])
    """

    async def department_checker(
        request: Request,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        user_role = normalize_role(current_user.get("role", ""))
        user_dept = current_user.get("department_id")

        # Admins bypass department-level restrictions
        if user_role == "admin":
            return current_user

        # Resolve target department ID from request path or query params, or direct argument
        target_dept = (
            request.path_params.get(department_id_param)
            or request.query_params.get(department_id_param)
            or department_id_param
        )

        if not user_dept or user_dept != target_dept:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": "AUTH_FORBIDDEN",
                    "message": f"User department '{user_dept}' cannot access department scope '{target_dept}'.",
                    "details": {"user_department": user_dept, "requested_department": target_dept},
                },
            )

        return current_user

    return department_checker
