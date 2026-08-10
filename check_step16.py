from app.core.database import get_snowflake_connection

WORKFLOW_ID = "1d0ceb46-6c55-591a-b9e4-f54ece0b5d68"
VERSION_ID = "b2f336d4-d2a7-53ad-83ac-dfd880650cdb"

with get_snowflake_connection() as connection:
    with connection.cursor() as cursor:

        print("\n=== WORKFLOW ===")
        cursor.execute("""
            SELECT *
            FROM WORKMATE_AI.KNOWLEDGE_STUDIO.workflows
            WHERE id = %s
        """, (WORKFLOW_ID,))

        for row in cursor.fetchall():
            print(row)

        print("\n=== VERSION ===")
        cursor.execute("""
            SELECT
                id,
                workflow_id,
                version_number,
                status,
                stage_file_uri,
                created_at,
                published_at
            FROM WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_versions
            WHERE id = %s
        """, (VERSION_ID,))

        for row in cursor.fetchall():
            print(row)

        print("\n=== STATES ===")
        cursor.execute("""
            SELECT
                id,
                state_key,
                state_type,
                title,
                ordinal_index,
                is_initial,
                is_terminal
            FROM WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_states
            WHERE workflow_version_id = %s
            ORDER BY ordinal_index
        """, (VERSION_ID,))

        states = cursor.fetchall()

        for row in states:
            print(row)

        print("\nSTATE COUNT:", len(states))

        print("\n=== SEARCH METADATA ===")
        cursor.execute("""
            SELECT
                id,
                workflow_version_id,
                state_id,
                department_id,
                status,
                LEFT(search_content, 200)
            FROM WORKMATE_AI.KNOWLEDGE_STUDIO.workflow_search_metadata
            WHERE workflow_version_id = %s
            ORDER BY state_id
        """, (VERSION_ID,))

        metadata = cursor.fetchall()

        for row in metadata:
            print(row)

        print("\nSEARCH METADATA COUNT:", len(metadata))
