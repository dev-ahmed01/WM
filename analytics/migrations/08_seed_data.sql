-- 08_seed_data.sql: Minimal initial seed data for SECURITY schema

-- Seed Departments
MERGE INTO SECURITY.departments AS target
USING (
    SELECT 'dept_ops' AS id, 'OPS' AS code, 'Operations' AS name UNION ALL
    SELECT 'dept_wh' AS id, 'WH' AS code, 'Warehouse' AS name UNION ALL
    SELECT 'dept_log' AS id, 'LOG' AS code, 'Logistics' AS name UNION ALL
    SELECT 'dept_qa' AS id, 'QA' AS code, 'Quality' AS name UNION ALL
    SELECT 'dept_inv' AS id, 'INV' AS code, 'Inventory' AS name
) AS src
ON target.id = src.id
WHEN MATCHED THEN UPDATE SET code = src.code, name = src.name
WHEN NOT MATCHED THEN INSERT (id, code, name, created_at) VALUES (src.id, src.code, src.name, CURRENT_TIMESTAMP());

-- Seed Roles
MERGE INTO SECURITY.roles AS target
USING (
    SELECT 'role_admin' AS id, 'admin' AS name, PARSE_JSON('{"all": true}') AS permission_set UNION ALL
    SELECT 'role_manager' AS id, 'manager' AS name, PARSE_JSON('{"view_analytics": true, "manage_sops": true}') AS permission_set UNION ALL
    SELECT 'role_employee' AS id, 'employee' AS name, PARSE_JSON('{"use_copilot": true}') AS permission_set
) AS src
ON target.id = src.id
WHEN MATCHED THEN UPDATE SET name = src.name, permission_set = src.permission_set
WHEN NOT MATCHED THEN INSERT (id, name, permission_set, created_at) VALUES (src.id, name, permission_set, CURRENT_TIMESTAMP());
