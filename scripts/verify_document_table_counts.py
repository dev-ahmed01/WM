import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import get_snowflake_connection

def verify_counts():
    tables = [
        "WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS",
        "WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_CONTENTS",
        "WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_AI_METADATA",
        "WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_CHUNKS",
        "WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_LINEAGE",
    ]
    with get_snowflake_connection() as conn:
        with conn.cursor() as cur:
            for t in tables:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                cnt = cur.fetchone()[0]
                print(f"{t}: {cnt} row(s)")

if __name__ == "__main__":
    verify_counts()
