"""Regression suite for externally reachable managed DB and private staging UI."""
from copy import deepcopy

import yaml

from scripts.check_staging_topology import DEFAULT_COMPOSE, check, examine


def _config():
    return yaml.safe_load(DEFAULT_COMPOSE.read_text(encoding="utf-8"))


def test_verified_staging_topology_is_private_and_can_egress_to_managed_database():
    result=check()
    assert result["decision"]=="STATIC_TOPOLOGY_PASS_NOT_DEPLOYED"
    actual=_config()
    assert examine(actual)==[]
    services=actual["services"]
    assert services["frontend"]["networks"]==["internal"]
    assert services["backend"]["networks"]==["internal","database_egress"]
    assert services["migrate"]["networks"]==["database_egress"]
    assert services["backup"]["networks"]==["database_egress"]
    assert "ports" not in services["backend"]
    assert services["backend"]["environment"]["WORKMATE_OUTBOUND_ENABLED"]=="false"


def test_topology_audit_catches_trapped_db_and_public_api():
    config=_config()
    broken=deepcopy(config)
    broken["services"]["backend"]["networks"]=["internal"]
    broken["services"]["migrate"]["networks"]=["internal"]
    broken["services"]["backup"]["networks"]=["internal"]
    errors=examine(broken)
    assert any("backend must attach exactly" in e for e in errors)
    assert any("migrate must attach exactly" in e for e in errors)
    assert any("backup must attach exactly" in e for e in errors)

    broken=deepcopy(config)
    broken["services"]["backend"]["ports"]=["8000:8000"]
    broken["services"]["frontend"]["networks"]=["internal","public"]
    broken["networks"]["internal"]["internal"]=False
    errors=examine(broken)
    assert any("may not publish host ports" in e for e in errors)
    assert any("frontend must attach exactly" in e for e in errors)
    assert any("App communication network must block" in e for e in errors)


def test_staging_does_not_auto_enable_vendor_outbound_or_skip_role_preflight():
    config=_config()
    invalid=deepcopy(config)
    invalid["services"]["backend"]["environment"]["WORKMATE_OUTBOUND_ENABLED"]="true"
    invalid["services"]["backend"]["environment"]["WORKMATE_OUTBOUND_ALLOWED_HOSTS"]="all.example.net"
    invalid["services"]["backend"]["command"]=["uvicorn","app.main:app"]
    invalid["services"]["migrate"]["command"]=["true"]
    errors=examine(invalid)
    assert any("explicitly disable outbound ERP" in e for e in errors)
    assert any("may not allowlist external ERP" in e for e in errors)
    assert any("Runtime database privilege/RLS preflight" in e for e in errors)
    assert any("Migration and non-owner grants" in e for e in errors)
