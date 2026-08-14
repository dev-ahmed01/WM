"""OWD Database Migration Deployment & Verification Script.

Executes ordered schema migrations against Snowflake database WORKMATE_AI,
seeds initial SECURITY departments and roles, and runs INFORMATION_SCHEMA verification checks.
Deployment fails closed when live Snowflake credentials are unavailable.
"""

import sys
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Ensure backend app imports work
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.database import get_snowflake_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("owd_deployer")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "analytics" / "migrations"
MIGRATION_FILES = [
    "01_schemas.sql",
    "02_security.sql",
    "03_knowledge_studio.sql",
    "04_workmate_copilot.sql",
    "05_intelligence_hub.sql",
    "06_shared.sql",
    "08_seed_data.sql",
    "09_owd_v1_1_tables.sql",
    "10_enterprise_document_layer.sql",
    "12_runtime_alignment.sql",
    "13_runtime_prerequisites.sql",
    "14_runtime_integrity.sql",
    "15_active_workflow_versions.sql",
    "16_flexible_owd_authoring_metadata.sql",
    "17_multilingual_voice.sql",
    "18_query_resolution_memory.sql",
]

_ADD_COLUMN_IF_MISSING_RE = re.compile(
    r'^\s*ALTER\s+TABLE\s+([A-Z0-9_$."]+)\s+'
    r'ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+([A-Z0-9_$"]+)',
    re.IGNORECASE | re.DOTALL,
)


def ordered_migrations() -> List[str]:
    """Return the deterministic database-only migration order."""
    return list(MIGRATION_FILES)


def has_placeholder_credentials() -> bool:
    """Reject the shipped template values before opening a Snowflake connection."""
    values = (
        getattr(settings, "SNOWFLAKE_ACCOUNT", ""),
        getattr(settings, "SNOWFLAKE_USER", ""),
        getattr(settings, "SNOWFLAKE_PASSWORD", ""),
    )
    markers = ("your_", "replace_with_", "placeholder")
    return any(not value or any(marker in value.lower() for marker in markers) for value in values)


def split_sql_statements(sql_text: str) -> List[str]:
    """Splits SQL script text into individual executable SQL statements, ignoring comments."""
    lines = sql_text.splitlines()
    statements = []
    current_stmt = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current_stmt.append(line)
        if stripped.endswith(";"):
            stmt_text = "\n".join(current_stmt).strip()
            if stmt_text.endswith(";"):
                stmt_text = stmt_text[:-1].strip()
            if stmt_text:
                statements.append(stmt_text)
            current_stmt = []

    if current_stmt:
        stmt_text = "\n".join(current_stmt).strip()
        if stmt_text.endswith(";"):
            stmt_text = stmt_text[:-1].strip()
        if stmt_text:
            statements.append(stmt_text)

    return statements


def add_column_if_missing_target(statement: str) -> Optional[Tuple[str, str]]:
    """Return the table/column guarded by an ADD COLUMN IF NOT EXISTS statement."""
    match = _ADD_COLUMN_IF_MISSING_RE.match(statement)
    if not match:
        return None
    return match.group(1), match.group(2)


def column_exists(cur: Any, table_identifier: str, column_identifier: str) -> bool:
    """Check column metadata before Snowflake evaluates an idempotent ADD COLUMN."""
    parts = [part.strip('"').upper() for part in table_identifier.split(".")]
    column_name = column_identifier.strip('"').upper()
    if len(parts) == 2:
        metadata_view = "INFORMATION_SCHEMA.COLUMNS"
        schema_name, table_name = parts
    elif len(parts) == 3:
        database_name, schema_name, table_name = parts
        metadata_view = f"{database_name}.INFORMATION_SCHEMA.COLUMNS"
    else:
        raise ValueError(f"Unsupported table identifier: {table_identifier}")

    cur.execute(
        f"SELECT 1 FROM {metadata_view} "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s LIMIT 1",
        (schema_name, table_name, column_name),
    )
    return cur.fetchone() is not None


def deploy_migrations() -> Dict[str, Any]:
    """Run ordered SQL migrations against live Snowflake, failing closed."""
    if has_placeholder_credentials():
        return {
            "schemas_created": [], "tables_created": [], "views_created": [],
            "seed_data_inserted": [], "warnings": [],
            "failed_statements": [{"error": "Live Snowflake credentials are required; placeholder credentials are configured."}],
            "status": "FAILED",
        }

    report = {
        "schemas_created": [],
        "tables_created": [],
        "views_created": [],
        "seed_data_inserted": [],
        "warnings": [],
        "failed_statements": [],
        "status": "FAILED",
    }

    logger.info("Connecting to Snowflake database WORKMATE_AI...")

    try:
        with get_snowflake_connection() as conn:
            with conn.cursor() as cur:
                for mig_file in ordered_migrations():
                    file_path = MIGRATIONS_DIR / mig_file
                    if not file_path.exists():
                        msg = f"Migration file not found: {file_path}"
                        logger.error(msg)
                        report["failed_statements"].append({"file": mig_file, "error": msg})
                        return report

                    logger.info(f"Executing migration: {mig_file}")
                    sql_text = file_path.read_text(encoding="utf-8")
                    statements = split_sql_statements(sql_text)

                    for idx, stmt in enumerate(statements, 1):
                        try:
                            add_column_target = add_column_if_missing_target(stmt)
                            if add_column_target and column_exists(cur, *add_column_target):
                                logger.info(
                                    "  [SKIP] Column %s already exists on %s",
                                    add_column_target[1],
                                    add_column_target[0],
                                )
                                continue
                            cur.execute(stmt)
                            logger.info(f"  [OK] Statement {idx}/{len(statements)} in {mig_file}")
                        except Exception as exc:
                            error_msg = f"SQL error executing statement {idx} in {mig_file}: {str(exc)}"
                            logger.error(error_msg)
                            report["failed_statements"].append({"file": mig_file, "statement": stmt, "error": str(exc)})
                            report["status"] = "FAILED"
                            return report

                # ----------------------------------------------------------------
                # Verification Queries via INFORMATION_SCHEMA
                # ----------------------------------------------------------------
                logger.info("Executing INFORMATION_SCHEMA verification queries...")

                # 1. Check Schemas
                cur.execute("""
                    SELECT SCHEMA_NAME 
                    FROM INFORMATION_SCHEMA.SCHEMATA 
                    WHERE CATALOG_NAME = CURRENT_DATABASE()
                """)
                schemas = [row[0].upper() for row in cur.fetchall()]
                report["schemas_created"] = sorted(schemas)

                # 2. Check Tables
                cur.execute("""
                    SELECT TABLE_SCHEMA, TABLE_NAME 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_TYPE = 'BASE TABLE'
                    ORDER BY TABLE_SCHEMA, TABLE_NAME
                """)
                tables = [f"{row[0]}.{row[1]}".upper() for row in cur.fetchall()]
                report["tables_created"] = tables

                # 3. Check Views
                cur.execute("""
                    SELECT TABLE_SCHEMA, TABLE_NAME 
                    FROM INFORMATION_SCHEMA.VIEWS 
                    ORDER BY TABLE_SCHEMA, TABLE_NAME
                """)
                views = [f"{row[0]}.{row[1]}".upper() for row in cur.fetchall()]
                report["views_created"] = views

                # 4. Verify Seed Data in SECURITY
                cur.execute("SELECT COUNT(*) FROM SECURITY.departments")
                dept_row = cur.fetchone()
                dept_count = int(dept_row[0]) if dept_row else 0

                cur.execute("SELECT COUNT(*) FROM SECURITY.roles")
                role_row = cur.fetchone()
                role_count = int(role_row[0]) if role_row else 0

                report["seed_data_inserted"] = [
                    f"SECURITY.departments ({dept_count} rows: Operations, Warehouse, Logistics, Quality, Inventory)",
                    f"SECURITY.roles ({role_count} rows: Admin, Supervisor, Employee)",
                ]

                report["status"] = "SUCCESS"
                logger.info("OWD Database Architecture Migration Deployment Completed Successfully!")

    except Exception as exc:
        logger.error("Live Snowflake deployment failed: %s", exc)
        report["failed_statements"].append({"error": str(exc)})
        report["status"] = "FAILED"

    return report


if __name__ == "__main__":
    result = deploy_migrations()
    print("\n" + "=" * 80)
    print("OWD SNOWFLAKE DATABASE DEPLOYMENT REPORT")
    print("=" * 80)
    print(f"Status: {result['status']}")
    print(f"Schemas Found ({len(result['schemas_created'])}): {result['schemas_created']}")
    print(f"Tables Created ({len(result['tables_created'])}):")
    for t in result['tables_created']:
        print(f"  - {t}")
    print(f"Views Created ({len(result['views_created'])}):")
    for v in result['views_created']:
        print(f"  - {v}")
    print("Seed Data:")
    for s in result['seed_data_inserted']:
        print(f"  - {s}")
    if result['warnings']:
        print("Warnings:")
        for w in result['warnings']:
            print(f"  - {w}")
    if result['failed_statements']:
        print("FAILED STATEMENTS:")
        for f in result['failed_statements']:
            print(f"  - {f}")
    print("=" * 80)
    if result["status"] != "SUCCESS":
        sys.exit(1)
