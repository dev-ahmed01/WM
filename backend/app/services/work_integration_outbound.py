"""Phase 6C: explicit, signed outbound HTTPS event delivery (opt-in worker).

The durable outbox is Postgres-backed, and HTTP never runs under a database
transaction. A destination's acknowledgement means ONLY it received an event,
not that any SOP/work/evidence or site condition changed.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import time
from urllib.parse import urlsplit
import httpx

from app.core.config import settings
from app.repositories.work_integration_outbox_repository import OutboxRepository

RECEIPT=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{3,99}$")
HOST=re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$")


def configured_target(source_id):
    """Static operator allowlist; source payloads never influence the URL.

    Deployment must also enforce DNS/egress firewall policies to prevent
    DNS-rebinding/private-address routing. Redirects and proxies are disabled.
    """
    try:
        config=json.loads(settings.WORKMATE_OUTBOUND_TARGETS_JSON)
    except (TypeError,ValueError):
        return None
    if not isinstance(config,dict):
        return None
    entry=config.get(source_id)
    if not isinstance(entry,dict) or set(entry)!={"url","secret"}:
        return None
    url,secret=entry.get("url"),entry.get("secret")
    if not isinstance(url,str) or not isinstance(secret,str) or not 32<=len(secret)<=512:
        return None
    if len(url)>500:
        return None
    try:
        parts=urlsplit(url)
        hostname=parts.hostname
        allowed={h.strip().lower() for h in settings.WORKMATE_OUTBOUND_ALLOWED_HOSTS.split(",") if h.strip()}
        if (parts.scheme!="https" or not hostname or not HOST.fullmatch(hostname)
            or hostname not in allowed or hostname.endswith((".localhost",".local",".internal"))
            or parts.username or parts.password or parts.fragment or parts.port not in (None,443)
            or not parts.path.startswith("/") or "\\" in url or any(ch.isspace() for ch in url)
            or "%" in (parts.netloc or "")):
            return None
        try:
            ipaddress.ip_address(hostname)
            return None
        except ValueError:
            pass
    except ValueError:
        return None
    return {"url":url,"secret":secret.encode("utf-8")}


def delivery_headers(secret,event_id,raw,now=None):
    stamp=str(int(time.time()) if now is None else now)
    message=b"v1\n"+stamp.encode()+b"\n"+event_id.encode()+b"\n"+raw
    digest=hmac.new(secret,message,hashlib.sha256).hexdigest()
    return {"Content-Type":"application/json","X-WM-Outbox-Id":event_id,
            "X-WM-Timestamp":stamp,"X-WM-Signature":"v1="+digest}


def dispatch_claim(job,client_factory=None):
    """Return successful settlement boolean. Never log response bodies/secrets."""
    target=configured_target(job["source_id"])
    if not target:
        return OutboxRepository.settle(
            job["id"],job["lease_token"],False,reason="not_configured")
    raw=json.dumps(job["payload"],sort_keys=True,
                   ensure_ascii=False,separators=(",",":")).encode("utf-8")
    headers=delivery_headers(target["secret"],job["id"],raw)
    code="transport_error"
    receipt=None
    ok=False
    try:
        # Strict config-only HTTPS target, secure TLS, no proxy/env/redirects.
        # The caller may inject a fully local mock httpx.Client for CI.
        factory=client_factory or (lambda: httpx.Client(
            timeout=settings.WORKMATE_OUTBOUND_TIMEOUT_SECONDS,
            follow_redirects=False,trust_env=False))
        with factory() as client:
            with client.stream("POST",target["url"],content=raw,headers=headers) as response:
                if response.status_code<200 or response.status_code>=300:
                    code="http_status"
                elif "application/json" not in response.headers.get("content-type","").lower():
                    code="invalid_ack"
                else:
                    chunks=bytearray()
                    for chunk in response.iter_bytes():
                        chunks.extend(chunk)
                        if len(chunks)>4096:
                            break
                    if len(chunks)>4096:
                        code="invalid_ack"
                    else:
                        try:
                            ack=json.loads(chunks)
                        except (TypeError,ValueError):
                            ack=None
                        if (isinstance(ack,dict)
                            and ack.get("event_id")==job["id"]
                            and ack.get("status")=="accepted"
                            and isinstance(ack.get("receipt_id"),str)
                            and RECEIPT.fullmatch(ack["receipt_id"])):
                            receipt=ack["receipt_id"]
                            ok=True
                            code="none"
                        else:
                            code="invalid_ack"
    except (httpx.HTTPError,OSError,ValueError):
        code="transport_error"
    return OutboxRepository.settle(job["id"],job["lease_token"],
                                   ok,receipt=receipt,reason=code)


def dispatch_batch(limit=10,client_factory=None):
    if not settings.WORKMATE_OUTBOUND_ENABLED:
        return {"enabled":False,"claimed":0,"settled":0}
    jobs=OutboxRepository.claim(limit)
    settled=0
    for job in jobs:
        if dispatch_claim(job,client_factory):
            settled+=1
    return {"enabled":True,"claimed":len(jobs),"settled":settled}
