"""Fail-closed static staging network separation audit.

This does NOT prove real hosted connectivity, TLS, DNS pinning or egress
firewall enforcement. Those require external deployment acceptance.
"""
from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_COMPOSE = Path(__file__).resolve().parents[1] / "deploy/staging/compose.yml"


def examine(compose: dict) -> list[str]:
    problems: list[str] = []
    services = compose.get("services") if isinstance(compose, dict) else None
    networks = compose.get("networks") if isinstance(compose, dict) else None
    if not isinstance(services, dict) or not isinstance(networks, dict):
        return ["Staging Compose must define services and networks."]
    if networks.get("internal", {}).get("internal") is not True:
        problems.append("App communication network must block public egress.")
    db_bridge = networks.get("database_egress")
    if not isinstance(db_bridge, dict) or db_bridge.get("internal") is True:
        problems.append("Managed PostgreSQL requires outbound-capable database_egress.")
    expected = {
        "migrate": {"database_egress"},
        "backend": {"internal", "database_egress"},
        "frontend": {"internal"},
        "ingress": {"internal", "public"},
        "backup": {"database_egress"},
    }
    for name, wanted in expected.items():
        service = services.get(name)
        if not isinstance(service, dict):
            problems.append(f"Required staging service {name} is missing.")
            continue
        assigned = service.get("networks")
        actual = set(assigned) if isinstance(assigned, list) else set()
        if actual != wanted:
            problems.append(
                f"{name} must attach exactly {sorted(wanted)}, got {sorted(actual)}."
            )
        if name != "ingress" and service.get("ports"):
            problems.append(f"{name} may not publish host ports.")
    backend = services.get("backend") or {}
    env = backend.get("environment") or {}
    if not isinstance(env, dict) or str(env.get("WORKMATE_OUTBOUND_ENABLED", "")).lower() != "false":
        problems.append("Staging must explicitly disable outbound ERP delivery.")
    if isinstance(env, dict) and env.get("WORKMATE_OUTBOUND_ALLOWED_HOSTS", None) != "":
        problems.append("Staging may not allowlist external ERP targets.")
    backend_command = " ".join(str(x) for x in backend.get("command", []))
    if "verify_runtime_database.py" not in backend_command:
        problems.append("Runtime database privilege/RLS preflight is required.")
    migrate = services.get("migrate") or {}
    migrate_command = " ".join(str(x) for x in migrate.get("command", []))
    if "migrate_postgres.py" not in migrate_command or "grant_pg_runtime.py" not in migrate_command:
        problems.append("Migration and non-owner grants must precede backend startup.")
    return problems


def check(path: Path = DEFAULT_COMPOSE) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    problems = examine(data)
    if problems:
        raise RuntimeError("Staging topology rejected: " + "; ".join(problems))
    return {
        "decision": "STATIC_TOPOLOGY_PASS_NOT_DEPLOYED",
        "checks": "external managed DB bridge; private frontend; no public API ports; ERP outbound disabled; non-owner runtime checks",
    }


if __name__ == "__main__":
    print(check())
