"""Phase 6B: HMAC-signed intake from preconfigured connector IDs.

Ingested work is *pending* and still needs independent approval. No vendor
network adapter or web-facing auto-execution is enabled.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import re
import time
from uuid import uuid4
from app.core.config import settings
from app.core.database import get_postgres_connection
from app.repositories.work_integration_intake_repository import (
    stage_in_transaction,IntegrationConflict,IntegrationNotFound,_scope,_record,
)

ID_PATTERN=re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{5,63}$")
NONCE_PATTERN=re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{15,79}$")
SIGNATURE_PATTERN=re.compile(r"^v1=[a-f0-9]{64}$")
MAX_BODY=16384


def configured_secret(source_id):
    """Fail closed on missing, short or malformed environment secret mapping."""
    try:
        mapping=json.loads(settings.WORKMATE_CONNECTOR_SECRETS_JSON)
    except (TypeError,ValueError):
        return None
    if not isinstance(mapping,dict):
        return None
    value=mapping.get(source_id)
    if not isinstance(value,str) or len(value)<32 or len(value)>512:
        return None
    return value.encode("utf-8")


def is_signature_valid(secret,stamp,nonce,raw,signature,now=None):
    """HMAC over exact signed bytes; timestamp window is a hard upper bound."""
    if not secret or len(raw)>MAX_BODY or not raw:
        return False
    if not NONCE_PATTERN.fullmatch(nonce or "") or not SIGNATURE_PATTERN.fullmatch(signature or ""):
        return False
    if not stamp or not stamp.isascii() or not re.fullmatch(r"[0-9]{10}",stamp):
        return False
    measured=int(time.time()) if now is None else int(now)
    if abs(measured-int(stamp))>settings.WORKMATE_WEBHOOK_CLOCK_SKEW_SECONDS:
        return False
    signed=b"v1\n"+stamp.encode("ascii")+b"\n"+nonce.encode("ascii")+b"\n"+raw
    expected="v1="+hmac.new(secret,signed,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,signature)


def _admin(cur,dept,actor):
    cur.execute("""
      SELECT 1 FROM security.users u
      JOIN security.user_roles ur ON ur.user_id=u.id
      JOIN security.roles role ON role.id=ur.role_id
      WHERE u.id=%s AND u.department_id=%s AND u.status='active'
        AND lower(role.name)='admin'
    """,(actor,dept))
    return cur.fetchone() is not None


def _public(source):
    if source is None:
        return None
    for key in ("created_at","updated_at"):
        if source.get(key) is not None:
            source[key]=source[key].isoformat()
    return source


class ConnectorRepository:
    @staticmethod
    def register(dept,admin,source_id,source_system):
        if not ID_PATTERN.fullmatch(source_id):
            raise IntegrationConflict("Connector ID must use 6–64 URL-safe characters.")
        if source_system not in ("sap","oracle","odoo","custom_wms"):
            raise IntegrationConflict("Unsupported warehouse source schema.")
        if not configured_secret(source_id):
            raise IntegrationConflict("A sufficiently strong secret must be provisioned before connector registration.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _scope(cur,dept)
                try:
                    if not _admin(cur,dept,admin):
                        raise IntegrationNotFound()
                    cur.execute("""
                      INSERT INTO workmate_copilot.work_integration_sources
                        (id,department_id,source_system,created_by)
                      VALUES(%s,%s,%s,%s)
                      ON CONFLICT DO NOTHING
                      RETURNING id,department_id,source_system,created_by,status,created_at,updated_at
                    """,(source_id,dept,source_system,admin))
                    result=_record(cur)
                    if not result:
                        raise IntegrationConflict("Connector ID is already registered.")
                    cur.execute("COMMIT")
                    return _public(result)
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def set_enabled(dept,admin,source_id,enabled):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _scope(cur,dept)
                try:
                    if not _admin(cur,dept,admin):
                        raise IntegrationNotFound()
                    cur.execute("""
                      UPDATE workmate_copilot.work_integration_sources
                      SET status=%s,updated_at=CURRENT_TIMESTAMP
                      WHERE id=%s AND department_id=%s
                      RETURNING id,department_id,source_system,created_by,status,created_at,updated_at
                    """,("active" if enabled else "disabled",source_id,dept))
                    row=_record(cur)
                    if not row:
                        raise IntegrationNotFound()
                    if enabled and not configured_secret(source_id):
                        raise IntegrationConflict("Cannot enable connector without configured signing secret.")
                    cur.execute("COMMIT")
                    return _public(row)
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def list(dept,actor):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _scope(cur,dept)
                if not _admin(cur,dept,actor):
                    raise IntegrationNotFound()
                cur.execute("""
                  SELECT s.id,s.department_id,s.source_system,s.created_by,s.status,
                         s.created_at,s.updated_at,
                         (SELECT COUNT(*) FROM workmate_copilot.work_integration_deliveries d
                          WHERE d.source_id=s.id AND d.department_id=s.department_id) AS deliveries,
                         (SELECT COUNT(*) FROM workmate_copilot.work_integration_deliveries d
                          WHERE d.source_id=s.id AND d.department_id=s.department_id
                            AND d.status IN ('conflict','invalid')) AS failures,
                         (SELECT MAX(received_at) FROM workmate_copilot.work_integration_deliveries d
                          WHERE d.source_id=s.id AND d.department_id=s.department_id) AS last_delivery_at
                  FROM workmate_copilot.work_integration_sources s
                  WHERE s.department_id=%s ORDER BY s.created_at DESC LIMIT 100
                """,(dept,))
                names=[col.name.lower() for col in cur.description]
                results=[dict(zip(names,row)) for row in cur.fetchall()]
                for item in results:
                    for key in ("created_at","updated_at","last_delivery_at"):
                        if item.get(key) is not None:
                            item[key]=item[key].isoformat()
                cur.execute("COMMIT")
                return results

    @staticmethod
    def deliveries(dept,actor,source_id,limit=40):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _scope(cur,dept)
                if not _admin(cur,dept,actor):
                    raise IntegrationNotFound()
                cur.execute("""
                  SELECT 1 FROM workmate_copilot.work_integration_sources
                  WHERE id=%s AND department_id=%s
                """,(source_id,dept))
                if not cur.fetchone():
                    raise IntegrationNotFound()
                cur.execute("""
                  SELECT id,source_id,status,reason_code,content_sha256,
                         received_at,intake_id FROM workmate_copilot.work_integration_deliveries
                  WHERE department_id=%s AND source_id=%s
                  ORDER BY received_at DESC,id LIMIT %s
                """,(dept,source_id,limit))
                names=[col.name.lower() for col in cur.description]
                data=[dict(zip(names,row)) for row in cur.fetchall()]
                for row in data:
                    row["received_at"]=row["received_at"].isoformat()
                cur.execute("COMMIT")
                return data

    @staticmethod
    def lookup_active(source_id):
        # Backend owner can resolve the department without trusting an
        # attacker-provided department. Invalid ID/disabled source is opaque.
        if not ID_PATTERN.fullmatch(source_id):
            return None
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                  SELECT id,department_id,source_system,created_by
                  FROM workmate_copilot.work_integration_sources
                  WHERE id=%s AND status='active'
                """,(source_id,))
                return _record(cur)

    @staticmethod
    def deliver(source,nonce,stamp,raw,payload,error_code=None):
        """Atomic durable nonce + staged idempotent work; audit invalid payloads.

        Conflicting business IDs are retained as safe, non-payload dead-letter
        metadata. Never create queue items or execute SOPs here.
        """
        dept=source["department_id"]
        content_hash=hashlib.sha256(raw).hexdigest()
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _scope(cur,dept)
                try:
                    cur.execute("""
                      SELECT status FROM workmate_copilot.work_integration_sources
                      WHERE id=%s AND department_id=%s FOR SHARE
                    """,(source["id"],dept))
                    current=cur.fetchone()
                    if not current or current[0]!="active" or not _admin(cur,dept,source["created_by"]):
                        raise IntegrationNotFound()
                    delivery_id="del_"+uuid4().hex[:24]
                    cur.execute("""
                      INSERT INTO workmate_copilot.work_integration_deliveries
                        (id,department_id,source_id,request_nonce,signed_timestamp,
                         content_sha256,status,reason_code)
                      VALUES(%s,%s,%s,%s,%s,%s,'invalid','unprocessed')
                      ON CONFLICT DO NOTHING RETURNING id
                    """,(delivery_id,dept,source["id"],nonce,int(stamp),content_hash))
                    if cur.fetchone() is None:
                        raise IntegrationConflict("Delivery nonce has already been used.")
                    result=None
                    status="invalid" if error_code else "staged"
                    reason=error_code or "none"
                    if not error_code:
                        if payload["source_system"]!=source["source_system"]:
                            status="invalid"
                            reason="source_mismatch"
                        else:
                            cur.execute("SAVEPOINT stage_source")
                            try:
                                result=stage_in_transaction(cur,dept,source["created_by"],payload)
                                status="replayed" if result["replayed"] else "staged"
                                cur.execute("RELEASE SAVEPOINT stage_source")
                            except IntegrationConflict:
                                cur.execute("ROLLBACK TO SAVEPOINT stage_source")
                                cur.execute("RELEASE SAVEPOINT stage_source")
                                status="conflict"
                                reason="source_collision"
                    cur.execute("""
                      UPDATE workmate_copilot.work_integration_deliveries
                      SET status=%s,reason_code=%s,intake_id=%s WHERE id=%s
                    """,(status,reason,result["id"] if result else None,delivery_id))
                    cur.execute("COMMIT")
                    return {"delivery_id":delivery_id,"status":status,"reason_code":reason,
                            "intake_id":result["id"] if result else None,
                            "replayed":result["replayed"] if result else False}
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
