"""Public staging HTTPS probes never send authenticated or mutating requests."""
import pytest
from scripts.check_staging_https import validate_target, assess


def test_public_origin_must_be_bare_https():
    assert validate_target("https://STAGING.example.org") == "https://staging.example.org"
    for value in ("http://stage.example.org", "https://user:pass@stage.example.org",
                  "https://stage.example.org/login", "https://stage.example.org?secret=1"):
        with pytest.raises(ValueError, match="bare public HTTPS"):
            validate_target(value)


def test_probe_requires_security_headers_and_uncached_unauthorized_session():
    common = {"Strict-Transport-Security": "max-age=31536000",
              "X-Content-Type-Options": "nosniff"}
    assert assess(200, dict(common, **{"Content-Type":"text/html"}), login=True) == []
    assert assess(401, dict(common, **{"Cache-Control":"no-store"}), login=False) == []
    assert assess(200, {}, login=True)
    assert assess(200, common, login=False)
