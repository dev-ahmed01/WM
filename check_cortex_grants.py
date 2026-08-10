from app.core.database import get_snowflake_connection

with get_snowflake_connection() as connection:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT CURRENT_USER(), CURRENT_ROLE()
        """)
        print(cursor.fetchone())

        cursor.execute("""
            SHOW GRANTS TO USER CURRENT_USER()
        """)

        print("\n=== USER GRANTS ===")
        for row in cursor.fetchall():
            print(row)
