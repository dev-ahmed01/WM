from app.core.database import get_snowflake_connection

search_sql = """
SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
    'WORKMATE_AI.KNOWLEDGE_STUDIO.WORKMATE_KNOWLEDGE_SEARCH',
    '{
      "query": "receive shipment",
      "columns": [
        "chunk_id",
        "document_id",
        "document_title",
        "version_number",
        "state_id",
        "step_number",
        "step_title",
        "search_content",
        "department_id",
        "status"
      ],
      "filter": {
        "@and": [
          {"@eq": {"department_id": "dept_ops"}},
          {"@eq": {"status": "published"}}
        ]
      },
      "limit": 5
    }'
) AS response
"""

with get_snowflake_connection() as connection:
    with connection.cursor() as cursor:
        cursor.execute(search_sql)

        row = cursor.fetchone()

        print("\n=== CORTEX SEARCH RESULT ===")
        print(row[0])
