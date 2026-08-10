from app.core.database import get_snowflake_connection

with get_snowflake_connection() as connection:
    with connection.cursor() as cursor:
        cursor.execute(
            "LIST @WORKMATE_AI.KNOWLEDGE_STUDIO.RAW_OWD_STAGE"
        )

        for row in cursor.fetchall():
            print(row)
