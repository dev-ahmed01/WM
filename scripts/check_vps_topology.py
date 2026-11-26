"""Static audit of deploy/vps/compose.yml (single-host deployment).

This proves the *file* keeps the data plane private; it does NOT prove a running host is configured correctly
(firewall, DNS, TLS issuance). Use the acceptance checklist in deploy/vps/README.md on the real server.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

DEFAULT_COMPOSE = Path(__file__).resolve().parents[1] / "deploy/vps/compose.yml"
PRIVATE_ONLY = {"postgres", "ollama", "migrate", "backend", "frontend", "backup"}


def examine(compose: dict) -> list[str]:
    problems: list[str] = []
    services = compose.get("services") or {}
    networks = compose.get("networks") or {}
    if networks.get("internal", {}).get("internal") is not True:
        problems.append("The 'internal' network must be internal:true (no internet route).")
    for name, svc in services.items():
        if name != "ingress" and svc.get("ports"):
            problems.append(f"Service '{name}' publishes host ports; only 'ingress' may.")
    ingress_ports = {str(p).split(":")[0] for p in services.get("ingress", {}).get("ports", [])}
    if not ingress_ports <= {"80", "443"}:
        problems.append("Ingress may publish only 80/443.")
    for name in PRIVATE_ONLY & set(services):
        nets = set(services[name].get("networks") or [])
        if nets != {"internal"}:
            problems.append(f"Service '{name}' must be attached to the internal network only (found {sorted(nets)}).")
    models_nets = set(services.get("models", {}).get("networks") or [])
    if "egress" not in models_nets:
        problems.append("The one-shot model puller needs the egress network to download models.")
    if "egress" in {n for s, v in services.items() if s != "models" for n in (v.get("networks") or [])}:
        problems.append("Only the model puller may use the egress network.")
    backend = services.get("backend", {})
    env = backend.get("environment") or {}
    if env.get("APP_ENV") != "production":
        problems.append("Backend must run with APP_ENV=production.")
    if str(env.get("PUBLISH_REQUIRES_APPROVAL")).lower() != "true":
        problems.append("Backend must keep PUBLISH_REQUIRES_APPROVAL=true.")
    if str(env.get("POSTGRES_RLS_REFERENCES")).lower() != "true":
        problems.append("Backend must enable row-level-security context (POSTGRES_RLS_REFERENCES=true).")
    if "ollama:11434" not in str(env.get("LOCAL_AI_BASE_URL", "")):
        problems.append("Backend must reach the private Ollama container, not an external provider.")
    if not backend.get("read_only"):
        problems.append("Backend root filesystem should be read-only.")
    runtime_user = re.search(r"//\$\{(\w+)\}", str(env.get("DATABASE_URL", "")))
    owner_user = re.search(r"//\$\{(\w+)\}", str((services.get("migrate", {}).get("environment") or {}).get("MIGRATION_DATABASE_URL", "")))
    if not runtime_user or not owner_user or runtime_user.group(1) == owner_user.group(1):
        problems.append("The API must connect as a different, non-owner database login than the migration owner.")
    # Every credential-like environment value must be injected from the operator's .env, never written in the file.
    for name, svc in services.items():
        for key, value in (svc.get("environment") or {}).items():
            text = str(value)
            literal_credentials = re.search(r"://[^/${}@:]+:[^/${}@]+@", text)  # user:password@host with no ${...}
            if (re.search(r"(?i)password|secret", key) and "${" not in text) or literal_credentials:
                problems.append(f"Service '{name}' hard-codes a credential in {key}; it must come from an environment variable.")
    return problems


def main() -> int:
    problems = examine(yaml.safe_load(DEFAULT_COMPOSE.read_text(encoding="utf-8")))
    for p in problems:
        print("FAIL:", p)
    if not problems:
        print("VPS topology OK (static check only).")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
