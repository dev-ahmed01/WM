-- Align existing SECURITY departments with the runtime validation contract.

ALTER TABLE SECURITY.departments
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

UPDATE SECURITY.departments
SET is_active = TRUE
WHERE is_active IS NULL;

MERGE INTO SECURITY.departments AS target
USING (
    SELECT 'dept_admin' AS id, 'ADMIN' AS code, 'Executive Administration' AS name UNION ALL
    SELECT 'dept_inbound', 'INBOUND', 'Inbound Operations' UNION ALL
    SELECT 'dept_outbound', 'OUTBOUND', 'Outbound Operations' UNION ALL
    SELECT 'dept_ops', 'OPS', 'Operations & Logistics' UNION ALL
    SELECT 'dept_quality', 'QUALITY', 'Quality' UNION ALL
    SELECT 'dept_inventory', 'INVENTORY', 'Inventory' UNION ALL
    SELECT 'dept_safety', 'SAFETY', 'Safety & Compliance' UNION ALL
    SELECT 'dept_returns', 'RETURNS', 'Returns' UNION ALL
    SELECT 'dept_maintenance', 'MAINTENANCE', 'Maintenance' UNION ALL
    SELECT 'dept_eng', 'ENG', 'Engineering & Technology'
) AS src
ON target.id = src.id
WHEN MATCHED THEN UPDATE SET code = src.code, name = src.name, is_active = TRUE
WHEN NOT MATCHED THEN INSERT (id, code, name, is_active, created_at)
    VALUES (src.id, src.code, src.name, TRUE, CURRENT_TIMESTAMP());
