-- Governed reference knowledge is deliberately separate from executable OWD workflows.
-- No plain PDF/Word document may be promoted into a state machine by this migration.
CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.reference_documents (
    id VARCHAR(64) PRIMARY KEY,
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    title VARCHAR(512) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_extension VARCHAR(16) NOT NULL,
    mime_type VARCHAR(128) NOT NULL,
    stage_uri VARCHAR(1024) NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    file_size_bytes NUMBER(38,0) NOT NULL,
    extracted_characters NUMBER(38,0) NOT NULL,
    extraction_warnings VARCHAR(8192),
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'APPROVED', 'ARCHIVED')),
    created_by VARCHAR(128) NOT NULL,
    reviewed_by VARCHAR(128),
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    reviewed_at TIMESTAMP_NTZ,
    updated_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS KNOWLEDGE_STUDIO.reference_chunks (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES KNOWLEDGE_STUDIO.reference_documents(id),
    department_id VARCHAR(64) NOT NULL REFERENCES SECURITY.departments(id),
    ordinal_index NUMBER(38,0) NOT NULL,
    start_offset NUMBER(38,0) NOT NULL,
    end_offset NUMBER(38,0) NOT NULL,
    content TEXT NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

ALTER TABLE KNOWLEDGE_STUDIO.reference_documents CLUSTER BY (department_id, status);
ALTER TABLE KNOWLEDGE_STUDIO.reference_chunks CLUSTER BY (department_id, document_id);
