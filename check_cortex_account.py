from app.core.database import get_snowflake_connection

with get_snowflake_connection() as connection:
    with connection.cursor() as cursor:
        print("=== ACCOUNT ===")
        cursor.execute("SELECT CURRENT_ACCOUNT(), CURRENT_REGION(), CURRENT_USER(), CURRENT_ROLE()")
        print(cursor.fetchone())

        print("\n=== CORTEX DATABASE ROLE ===")
        try:
            cursor.execute("SHOW DATABASE ROLES IN DATABASE SNOWFLAKE")
            rows = cursor.fetchall()
            for row in rows:
                if "CORTEX" in str(row).upper():
                    print(row)
        except Exception as e:
            print("Could not inspect Cortex database roles:", e)

        print("\n=== CORTEX SEARCH SERVICES ===")
        cursor.execute("SHOW CORTEX SEARCH SERVICES")
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                print(row)
        else:
            print("NONE")
