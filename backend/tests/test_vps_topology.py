"""The single-VPS compose file must keep the data plane private (static audit)."""
import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_vps_topology as audit  # noqa: E402

COMPOSE = yaml.safe_load((ROOT / "deploy/vps/compose.yml").read_text(encoding="utf-8"))


def test_shipped_vps_compose_is_private_by_design():
    assert audit.examine(COMPOSE) == []


def test_audit_catches_a_published_database_port():
    broken = copy.deepcopy(COMPOSE)
    broken["services"]["postgres"]["ports"] = ["5432:5432"]
    assert any("postgres" in p and "publishes" in p for p in audit.examine(broken))


def test_audit_catches_an_api_with_internet_access_and_a_shared_owner_login():
    broken = copy.deepcopy(COMPOSE)
    broken["services"]["backend"]["networks"] = ["internal", "egress"]
    broken["services"]["backend"]["environment"]["DATABASE_URL"] = broken["services"]["migrate"]["environment"]["MIGRATION_DATABASE_URL"]
    problems = audit.examine(broken)
    assert any("backend" in p and "internal network only" in p for p in problems)
    assert any("non-owner" in p for p in problems)


def test_audit_catches_disabled_publish_approval_and_external_ai():
    broken = copy.deepcopy(COMPOSE)
    broken["services"]["backend"]["environment"]["PUBLISH_REQUIRES_APPROVAL"] = "false"
    broken["services"]["backend"]["environment"]["LOCAL_AI_BASE_URL"] = "https://api.example-llm.com"
    problems = audit.examine(broken)
    assert any("PUBLISH_REQUIRES_APPROVAL" in p for p in problems)
    assert any("private Ollama" in p for p in problems)


def test_init_script_creates_a_non_bypassrls_application_login():
    sql = (ROOT / "deploy/vps/initdb/10-roles.sh").read_text(encoding="utf-8")
    assert "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE" in sql and "workmate_scoped_reader" in sql


def test_env_template_contains_no_real_secrets():
    text = (ROOT / "deploy/vps/.env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith(("OWNER_DB_PASSWORD", "APP_DB_PASSWORD", "JWT_SECRET", "INTERNAL_WEBHOOK_SECRET")):
            assert line.split("=", 1)[1].strip() == "", line


def test_bootstrap_service_is_private_opt_in_and_takes_credentials_from_the_operator_shell():
    svc = COMPOSE["services"]["bootstrap"]
    assert svc["profiles"] == ["bootstrap"] and set(svc["networks"]) == {"internal"} and not svc.get("ports")
    for key in ("BOOTSTRAP_ADMIN_EMAIL", "BOOTSTRAP_ADMIN_PASSWORD"):
        # Injected from the shell, never literal. Not ':?' (required): Compose validates profile-gated services too,
        # and a plain `docker compose up` must not demand bootstrap credentials.
        assert svc["environment"][key].startswith("${") and ":-" in svc["environment"][key]


def test_plain_up_needs_no_bootstrap_or_backup_inputs():
    import subprocess, shutil
    if not shutil.which("docker"):
        return
    import os
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BOOTSTRAP_", "BACKUP_"))}
    env.update({"WORKMATE_DOMAIN": "x.example.com", "OWNER_DB_USER": "o", "OWNER_DB_PASSWORD": "p1", "APP_DB_USER": "a",
                "APP_DB_PASSWORD": "p2", "JWT_SECRET": "j" * 40, "INTERNAL_WEBHOOK_SECRET": "w" * 40})
    r = subprocess.run(["docker", "compose", "-f", str(ROOT / "deploy/vps/compose.yml"), "config", "-q"], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
