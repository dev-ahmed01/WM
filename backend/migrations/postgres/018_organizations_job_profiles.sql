-- Phase 3: multi-company structure. Organizations own warehouses; departments
-- belong to one organization (and optionally one warehouse). Existing
-- department-scoped RLS keeps working unchanged: a department can never span
-- organizations, so department isolation implies organization isolation.
-- Idempotent.

CREATE TABLE IF NOT EXISTS security.organizations (
    id VARCHAR(64) PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS security.warehouses (
    id VARCHAR(64) PRIMARY KEY,
    organization_id VARCHAR(64) NOT NULL REFERENCES security.organizations(id),
    code VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, code),
    UNIQUE (id, organization_id)
);

-- Job profiles are a platform catalogue (same for every tenant); they are not
-- permissions. System role + department/warehouse scope decide access.
CREATE TABLE IF NOT EXISTS security.job_profiles (
    id VARCHAR(64) PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name_en VARCHAR(128) NOT NULL,
    name_hi VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO security.job_profiles (id, code, name_en, name_hi) VALUES
  ('jp_receiving','RECEIVING_ASSOCIATE','Receiving associate','रिसीविंग सहयोगी'),
  ('jp_picker','PICKER','Picker','पिकर'),
  ('jp_packer','PACKER','Packer','पैकर'),
  ('jp_dispatch','DISPATCH_ASSOCIATE','Dispatch associate','डिस्पैच सहयोगी'),
  ('jp_inventory','INVENTORY_ASSOCIATE','Inventory associate','इन्वेंटरी सहयोगी'),
  ('jp_quality','QUALITY_INSPECTOR','Quality inspector','गुणवत्ता निरीक्षक'),
  ('jp_mhe','MATERIAL_HANDLING','Material handling worker','मटेरियल हैंडलिंग कर्मचारी'),
  ('jp_returns','RETURNS_ASSOCIATE','Returns associate','रिटर्न्स सहयोगी'),
  ('jp_maintenance','MAINTENANCE_ASSOCIATE','Maintenance associate','मेंटेनेंस सहयोगी'),
  ('jp_general','GENERAL_EMPLOYEE','General warehouse employee','सामान्य वेयरहाउस कर्मचारी')
ON CONFLICT (id) DO NOTHING;

ALTER TABLE security.departments
    ADD COLUMN IF NOT EXISTS organization_id VARCHAR(64) REFERENCES security.organizations(id),
    ADD COLUMN IF NOT EXISTS warehouse_id VARCHAR(64);
DO $$ BEGIN
    ALTER TABLE security.departments
        ADD CONSTRAINT departments_warehouse_org_fk
        FOREIGN KEY (warehouse_id, organization_id)
        REFERENCES security.warehouses (id, organization_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE security.users
    ADD COLUMN IF NOT EXISTS job_profile_id VARCHAR(64) REFERENCES security.job_profiles(id),
    ADD COLUMN IF NOT EXISTS warehouse_id VARCHAR(64) REFERENCES security.warehouses(id),
    ADD COLUMN IF NOT EXISTS supervisor_id VARCHAR(64) REFERENCES security.users(id),
    ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(8) NOT NULL DEFAULT 'en',
    ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE;
DO $$ BEGIN
    ALTER TABLE security.users ADD CONSTRAINT users_language_chk
        CHECK (preferred_language IN ('en','hi','hinglish'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Legacy departments (pre-018) are placed into one explicit legacy organization
-- so every department has an owner. Fresh databases create nothing here.
INSERT INTO security.organizations (id, code, name)
SELECT 'org_legacy', 'LEGACY', 'Legacy single-tenant organization'
WHERE EXISTS (SELECT 1 FROM security.departments WHERE organization_id IS NULL)
ON CONFLICT (id) DO NOTHING;
UPDATE security.departments SET organization_id = 'org_legacy'
WHERE organization_id IS NULL AND EXISTS (SELECT 1 FROM security.organizations WHERE id='org_legacy');

-- A user's department, warehouse and supervisor must all be in one organization.
CREATE OR REPLACE FUNCTION security.enforce_user_org_consistency() RETURNS trigger AS $$
DECLARE dept_org VARCHAR(64); wh_org VARCHAR(64); sup_org VARCHAR(64);
BEGIN
    SELECT organization_id INTO dept_org FROM security.departments WHERE id = NEW.department_id;
    IF NEW.warehouse_id IS NOT NULL THEN
        SELECT organization_id INTO wh_org FROM security.warehouses WHERE id = NEW.warehouse_id;
        IF wh_org IS DISTINCT FROM dept_org THEN
            RAISE EXCEPTION 'user warehouse must belong to the department organization' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF NEW.supervisor_id IS NOT NULL THEN
        SELECT d.organization_id INTO sup_org FROM security.users u
          JOIN security.departments d ON d.id = u.department_id WHERE u.id = NEW.supervisor_id;
        IF sup_org IS DISTINCT FROM dept_org THEN
            RAISE EXCEPTION 'supervisor must belong to the same organization' USING ERRCODE = '23514';
        END IF;
        IF NEW.supervisor_id = NEW.id THEN
            RAISE EXCEPTION 'user cannot supervise themselves' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_org_consistency ON security.users;
CREATE TRIGGER trg_users_org_consistency
    BEFORE INSERT OR UPDATE OF department_id, warehouse_id, supervisor_id ON security.users
    FOR EACH ROW EXECUTE FUNCTION security.enforce_user_org_consistency();

-- Managers may be scoped to specific warehouses/departments inside one organization.
CREATE TABLE IF NOT EXISTS security.manager_scopes (
    user_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
    warehouse_id VARCHAR(64) NOT NULL REFERENCES security.warehouses(id),
    department_id VARCHAR(64) NOT NULL DEFAULT '' ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, warehouse_id, department_id)
);

-- One-time invitation / recovery tokens. Only a SHA-256 digest is stored.
CREATE TABLE IF NOT EXISTS security.account_tokens (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES security.users(id),
    purpose VARCHAR(16) NOT NULL CHECK (purpose IN ('invite','recovery')),
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ NULL,
    created_by VARCHAR(64) NULL REFERENCES security.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_account_tokens_user ON security.account_tokens(user_id, purpose);

CREATE INDEX IF NOT EXISTS idx_departments_org ON security.departments(organization_id);
CREATE INDEX IF NOT EXISTS idx_users_dept ON security.users(department_id);

-- Canonical system roles (admin/manager/employee). Seeders that already
-- created a role with the same name are left untouched.
INSERT INTO security.roles (id, name, permission_set)
SELECT v.id, v.name, v.perms::jsonb FROM (VALUES
  ('role_admin','admin','{"manage_users":true,"manage_knowledge":true,"manage_conversations":true}'),
  ('role_manager','manager','{"view_operations":true,"resolve_exceptions":true,"view_analytics":true}'),
  ('role_employee','employee','{"use_copilot":true}')
) AS v(id,name,perms)
WHERE NOT EXISTS (SELECT 1 FROM security.roles r WHERE LOWER(r.name)=v.name)
ON CONFLICT (id) DO NOTHING;
