from app.core.database import get_snowflake_connection

with get_snowflake_connection() as connection:
    with connection.cursor() as cursor:

        print("\n=== CURRENT SECURITY CONTEXT ===")
        cursor.execute("""
            SELECT
                CURRENT_USER(),
                CURRENT_ROLE(),
                CURRENT_DATABASE(),
                CURRENT_SCHEMA(),
                CURRENT_WAREHOUSE()
        """)

        print(cursor.fetchone())

        print("\n=== CORTEX SEARCH SERVICES ===")
        cursor.execute("""
            SHOW CORTEX SEARCH SERVICES
            IN SCHEMA WORKMATE_AI.KNOWLEDGE_STUDIO
        """)

        rows = cursor.fetchall()

        if not rows:
            print("NO CORTEX SEARCH SERVICES FOUND")
        else:
            for row in rows:
                print(row)
