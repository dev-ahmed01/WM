"""Source-backed, revisioned procedure drafts. No generated content is trusted.

This is a controlled deterministic extraction and human-editable draft, not an AI
certification of SOP completeness. Publishing remains a separate guarded action.
"""
from __future__ import annotations
import hashlib
import json
import re
from uuid import uuid4

from app.core.database import get_postgres_connection

COLUMNS = ("id,department_id,created_by,source_sha256,source_filename,"
           "source_type,title,source_excerpt,steps,warnings,status,revision,"
           "reviewed_by,reviewed_at,created_at,updated_at")
LINE_ITEM = re.compile(r"^\s*(?:(?:step|stage)\s*\d+\s*[:.)-]\s*|\d{1,3}[.)]\s+|[-*]\s+)(.{8,700})$",re.I)


class DraftNotFound(Exception):
    pass


class DraftConflict(Exception):
    pass


def _start(cur, department):
    cur.execute("BEGIN")
    cur.execute("SELECT set_config('workmate.department_id',%s,true)",(department,))


def _dict(cur):
    value=cur.fetchone()
    if value is None:
        return None
    result=dict(zip([c.name.lower() for c in cur.description],value))
    for k in ("reviewed_at","created_at","updated_at"):
        if result.get(k) is not None:
            result[k]=result[k].isoformat()
    return result


def _event(cur, draft,dept,actor,action,revision):
    cur.execute("""INSERT INTO knowledge_studio.procedure_draft_events
      (draft_id,department_id,actor_id,action,revision) VALUES(%s,%s,%s,%s,%s)
    """,(draft,dept,actor,action,revision))


def propose_steps(source_text: str) -> list[dict]:
    """Conservative ordered-line candidate collection; never invent an SOP step."""
    seen=set()
    proposed=[]
    for line_no,line in enumerate(source_text.splitlines(),1):
        match=LINE_ITEM.match(line.strip())
        if not match:
            continue
        text=match.group(1).strip().strip("-").strip()
        key=text.casefold()
        if key in seen or not text:
            continue
        seen.add(key)
        proposed.append({
            "id":"step_"+uuid4().hex[:16],
            "instruction":text[:700],
            "source_line":line_no,
            "reviewed":False,
        })
        if len(proposed)>=50:
            break
    return proposed


class ProcedureDraftRepository:
    @staticmethod
    def create(department,actor,extracted,raw:bytes,title:str):
        file_name=extracted.filename
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,255}",file_name):
            raise DraftConflict("Rename the source document to use letters, numbers, '-' or '_'.")
        if not (5 <= len(title.strip()) <= 180):
            raise DraftConflict("A procedure title between 5 and 180 characters is required.")
        steps=propose_steps(extracted.content)
        warnings=list(extracted.warnings)
        if not steps:
            warnings.append("No numbered or bulleted steps were found. Add and review all steps manually.")
        if len(steps)==50:
            warnings.append("Only the first 50 potential steps were proposed. Review the original for omissions.")
        warnings.append("Every extracted step is an untrusted suggestion until reviewed by an administrator.")
        draft="drft_"+uuid4().hex[:24]
        object_id=uuid4().hex
        digest=hashlib.sha256(raw).hexdigest()
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    cur.execute("""SELECT 1 FROM security.users u
                       JOIN security.departments d ON d.id=u.department_id
                       WHERE u.id=%s AND u.department_id=%s AND u.status='active'
                         AND d.is_active=TRUE""",(actor,department))
                    if not cur.fetchone():
                        raise DraftConflict("Active administrator department is required.")
                    cur.execute("""INSERT INTO shared.source_objects
                        (id,department_id,filename,sha256_hash,content)
                        VALUES(%s,%s,%s,%s,%s)""",
                        (object_id,department,file_name,digest,raw))
                    cur.execute("""INSERT INTO knowledge_studio.procedure_drafts
                       (id,department_id,created_by,source_object_id,source_sha256,
                        source_filename,source_type,title,source_excerpt,steps,warnings)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                       RETURNING """+COLUMNS,
                        (draft,department,actor,object_id,digest,file_name,
                         extracted.file_type,title.strip(),extracted.content[:8000],
                         json.dumps(steps),json.dumps(warnings[:30])))
                    value=_dict(cur)
                    _event(cur,draft,department,actor,"imported",1)
                    cur.execute("COMMIT")
                    return value
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def list(department,limit=50):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    cur.execute("""SELECT id,title,source_filename,status,revision,
                        updated_at,jsonb_array_length(steps) AS step_count
                        FROM knowledge_studio.procedure_drafts
                        WHERE department_id=%s ORDER BY updated_at DESC LIMIT %s""",
                        (department,limit))
                    names=[x.name.lower() for x in cur.description]
                    result=[dict(zip(names,row)) for row in cur.fetchall()]
                    for item in result:
                        item["updated_at"]=item["updated_at"].isoformat()
                    cur.execute("COMMIT")
                    return result
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def get(department,draft_id):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    cur.execute("SELECT "+COLUMNS+"""
                        FROM knowledge_studio.procedure_drafts
                        WHERE id=%s AND department_id=%s""",(draft_id,department))
                    result=_dict(cur)
                    cur.execute("COMMIT")
                    if not result:
                        raise DraftNotFound()
                    return result
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def update(department,actor,draft_id,revision,title,steps):
        if not (5<=len(title.strip())<=180) or len(steps)>50:
            raise DraftConflict("Title or step limit exceeded.")
        if any(not isinstance(s,dict) or not (10<=len(str(s.get("instruction","")).strip())<=700)
               for s in steps):
            raise DraftConflict("Each step needs an instruction between 10 and 700 characters.")
        seen={s["id"] for s in steps}
        if len(seen)!=len(steps):
            raise DraftConflict("Each workflow step needs a distinct identifier.")
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    cur.execute("""SELECT revision FROM knowledge_studio.procedure_drafts
                        WHERE id=%s AND department_id=%s FOR UPDATE""",(draft_id,department))
                    row=cur.fetchone()
                    if not row:
                        raise DraftNotFound()
                    if row[0]!=revision:
                        raise DraftConflict("This draft changed since you opened it. Refresh before saving.")
                    cur.execute("""UPDATE knowledge_studio.procedure_drafts
                        SET title=%s,steps=%s::jsonb,status='draft',revision=revision+1,
                            reviewed_by=NULL,reviewed_at=NULL,updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s AND department_id=%s
                        RETURNING """+COLUMNS,(title.strip(),json.dumps(steps),draft_id,department))
                    result=_dict(cur)
                    _event(cur,draft_id,department,actor,"edited",result["revision"])
                    cur.execute("COMMIT")
                    return result
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def review(department,actor,draft_id,revision):
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    cur.execute("""SELECT steps,revision,status
                        FROM knowledge_studio.procedure_drafts
                        WHERE id=%s AND department_id=%s FOR UPDATE""",(draft_id,department))
                    row=cur.fetchone()
                    if not row:
                        raise DraftNotFound()
                    steps,current,status=row
                    if current!=revision or status!="draft":
                        raise DraftConflict("The draft version changed or was already reviewed.")
                    if not steps or any(s.get("reviewed") is not True for s in steps):
                        raise DraftConflict("Review each source-backed step before approving this draft.")
                    cur.execute("""UPDATE knowledge_studio.procedure_drafts
                        SET status='reviewed',revision=revision+1,reviewed_by=%s,
                            reviewed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s AND department_id=%s
                        RETURNING """+COLUMNS,(actor,draft_id,department))
                    result=_dict(cur)
                    _event(cur,draft_id,department,actor,"reviewed",result["revision"])
                    cur.execute("COMMIT")
                    return result
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    @staticmethod
    def source(department,draft_id):
        """Return the original document, never from an unscoped object identifier."""
        with get_postgres_connection() as conn:
            with conn.cursor() as cur:
                _start(cur,department)
                try:
                    cur.execute("""
                      SELECT d.source_filename,o.content
                      FROM knowledge_studio.procedure_drafts d
                      JOIN shared.source_objects o ON o.id=d.source_object_id
                      WHERE d.id=%s AND d.department_id=%s AND o.department_id=%s
                    """,(draft_id,department,department))
                    found=cur.fetchone()
                    cur.execute("COMMIT")
                    if not found:
                        raise DraftNotFound()
                    return found[0],bytes(found[1])
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
