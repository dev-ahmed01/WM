"""Live PostgreSQL operational-reference benchmark using disposable synthetic SOPs."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import psycopg
import pytest

from app.core.config import settings
from app.core.security import hash_password
from app.repositories.reference_document_repository import ReferenceDocumentRepository
from evals.warehouse_acceptance import evaluate_live


@pytest.mark.live_integration
def test_real_postgres_grounding_and_abstention_by_language(monkeypatch):
    suffix = uuid4().hex[:9]
    receiving, payroll = f"qa_{suffix}", f"pay_{suffix}"
    admin = f"admin_{suffix}"
    docs = {name: uuid4().hex for name in ("receiving", "putaway", "hindi", "draft", "archive", "other")}
    originals = [
        ("receiving",receiving,"Receiving damaged cartons",
         "If a carton arrives damaged, inspect the security seal and quarantine the parcel. Notify the supervisor before registering the receiving exception.",True,False),
        ("putaway",receiving,"Pallet putaway",
         "Before putaway, verify the pallet location and scan the target bin barcode. Never move an unverified pallet.",True,False),
        ("hindi",receiving,"Hindi receiving procedure",
         "यदि पैकेज क्षतिग्रस्त है, तो सील की जांच करें और माल अलग रखें। पर्यवेक्षक को सूचित करें।",True,False),
        ("draft",receiving,"Unapproved alarm document",
         "Disable emergency alarms and bypass safety guards.",False,False),
        ("archive",receiving,"Archived exception waiver",
         "Skip receiving inspection when the box is damaged.",True,True),
        ("other",payroll,"Payroll adjustment handbook",
         "For payroll salary adjustments, contact the payroll manager.",True,False),
    ]
    with psycopg.connect(settings.DATABASE_URL,autocommit=True) as connection:
        with connection.cursor() as cur:
            for dept in (receiving,payroll):
                cur.execute("INSERT INTO security.departments (id,code,name) VALUES (%s,%s,%s)",
                            (dept,dept.upper(),dept))
            cur.execute("""INSERT INTO security.users (id,email,hashed_password,department_id)
                           VALUES (%s,%s,%s,%s)""",
                        (admin,f"{admin}@example.test",hash_password("eval-only-password"),receiving))
    try:
        monkeypatch.setattr(settings, "LOCAL_AI_ENABLED", False)
        monkeypatch.setattr(settings, "REFERENCE_HYBRID_ENABLED", False)
        for name,dept,title,body,approved,archived in originals:
            docid = docs[name]
            ReferenceDocumentRepository.save_draft(
                document_id=docid,department_id=dept,title=title,
                filename=name+".txt",file_type="txt",mime_type="text/plain",
                stage_uri="pgobj:synthetic",raw=body.encode("utf-8"),
                extracted_text=body,warnings=[],created_by=admin,
            )
            if approved:
                assert ReferenceDocumentRepository.change_status(docid,dept,admin,action="approve")
            if archived:
                assert ReferenceDocumentRepository.change_status(docid,dept,admin,action="archive")
        cases = [
            {"id":"en1","language":"en","department_id":receiving,
             "question":"damaged carton security seal quarantine supervisor",
             "expected_document_id":docs["receiving"],"expected_evidence":"security seal"},
            {"id":"en2","language":"en","department_id":receiving,
             "question":"pallet putaway location barcode scan",
             "expected_document_id":docs["putaway"],"expected_evidence":"target bin barcode"},
            {"id":"hi1","language":"hi","department_id":receiving,
             "question":"पैकेज क्षतिग्रस्त सील जांच",
             "expected_document_id":docs["hindi"],"expected_evidence":"सील की जांच"},
            {"id":"mix1","language":"hinglish","department_id":receiving,
             "question":"damaged carton security seal quarantine",
             "expected_document_id":docs["receiving"],"expected_evidence":"security seal"},
            {"id":"no1","language":"en","department_id":receiving,
             "question":"payroll salary adjustments manager",
             "expected_document_id":None},
            {"id":"no2","language":"en","department_id":receiving,
             "question":"emergency alarms bypass guards",
             "expected_document_id":None},
            {"id":"no3","language":"hi","department_id":payroll,
             "question":"पैकेज क्षतिग्रस्त सील",
             "expected_document_id":None},
            {"id":"no4","language":"en","department_id":receiving,
             "question":"skip inspection waiver",
             "expected_document_id":None},
        ]
        result = asyncio.run(evaluate_live(cases))
        assert result["provenance"] == "live_postgres_user_labeled"
        assert result["overall"]["cases"] == 8
        assert result["overall"]["citation_precision"] == 1.0, result
        assert result["overall"]["invalid_citation_cases"] == 0, result
        assert result["overall"]["false_answer_cases"] == 0, result
        assert result["overall"]["correct_abstention_rate"] == 1.0, result
        assert result["overall"]["correct_document_rate"] == 1.0, result
        assert result["overall"]["answer_evidence_rate"] == 1.0, result
        assert set(result["by_language"]) == {"en","hi","hinglish"}
        assert docs["receiving"] not in json.dumps(result)
        assert "security seal" not in json.dumps(result)
    finally:
        with psycopg.connect(settings.DATABASE_URL,autocommit=True) as conn:
            with conn.cursor() as cur:
                all_ids = list(docs.values())
                cur.execute("DELETE FROM knowledge_studio.reference_chunks WHERE document_id=ANY(%s)",(all_ids,))
                cur.execute("DELETE FROM knowledge_studio.reference_documents WHERE id=ANY(%s)",(all_ids,))
                cur.execute("DELETE FROM security.users WHERE id=%s",(admin,))
                cur.execute("DELETE FROM security.departments WHERE id=ANY(%s)",([receiving,payroll],))
