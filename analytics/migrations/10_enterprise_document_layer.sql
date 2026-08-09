-- ============================================================================
-- WorkMate AI - Enterprise Knowledge Document Layer Schema Migration (v2.0)
-- 
-- Target Schema: WORKMATE_AI.KNOWLEDGE_STUDIO
-- 
-- Explicitly creates all 5 enterprise document tables with fully-qualified names:
-- 1. WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS
-- 2. WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_CONTENTS
-- 3. WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_AI_METADATA
-- 4. WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_CHUNKS
-- 5. WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_LINEAGE
-- ============================================================================

USE DATABASE WORKMATE_AI;
USE SCHEMA KNOWLEDGE_STUDIO;

-- Cleanup stray view or table in PUBLIC schema if created by legacy schema context drift
DROP VIEW IF EXISTS PUBLIC.KNOWLEDGE_DOCUMENTS;
DROP TABLE IF EXISTS PUBLIC.KNOWLEDGE_DOCUMENTS;

-- 1. Knowledge Document Entity Table
CREATE TABLE IF NOT EXISTS WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS (
    id VARCHAR(64) PRIMARY KEY,
    workflow_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.WORKFLOWS(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS(id),
    document_name VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    stage_uri VARCHAR(512) NOT NULL,
    relative_path VARCHAR(512) NULL,
    directory VARCHAR(255) NULL,
    extension VARCHAR(32) NOT NULL DEFAULT 'md',
    mime_type VARCHAR(64) NOT NULL DEFAULT 'text/markdown',
    uploaded_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    stage_last_modified TIMESTAMP_NTZ NULL,
    file_size_bytes INT NOT NULL DEFAULT 0,
    compression VARCHAR(32) NOT NULL DEFAULT 'none',
    encoding VARCHAR(32) NOT NULL DEFAULT 'utf-8',
    md5_hash VARCHAR(64) NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    compiler_version VARCHAR(32) NOT NULL DEFAULT '1.1.0',
    parser_version VARCHAR(32) NOT NULL DEFAULT '1.1.0',
    source_type VARCHAR(64) NOT NULL DEFAULT 'OWD_MARKDOWN',
    language_code VARCHAR(16) NOT NULL DEFAULT 'en-US',
    author VARCHAR(128) NULL,
    reviewer VARCHAR(128) NULL,
    approval_status VARCHAR(32) NOT NULL DEFAULT 'APPROVED',
    tags VARIANT NULL,
    labels VARIANT NULL,
    description TEXT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- 2. Knowledge Document Contents Preservation Table
CREATE TABLE IF NOT EXISTS WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_CONTENTS (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS(id),
    raw_markdown TEXT NOT NULL,
    normalized_markdown TEXT NOT NULL,
    frontmatter_yaml TEXT NULL,
    frontmatter_json VARIANT NULL,
    body_markdown TEXT NOT NULL,
    sections_json VARIANT NULL,
    tables_json VARIANT NULL,
    code_blocks_json VARIANT NULL,
    images_json VARIANT NULL,
    links_json VARIANT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- 3. Knowledge Document AI Metadata Table
CREATE TABLE IF NOT EXISTS WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_AI_METADATA (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS(id),
    reading_time_minutes INT NOT NULL DEFAULT 1,
    word_count INT NOT NULL DEFAULT 0,
    sentence_count INT NOT NULL DEFAULT 0,
    paragraph_count INT NOT NULL DEFAULT 0,
    complexity_score FLOAT NOT NULL DEFAULT 0.5,
    risk_score FLOAT NOT NULL DEFAULT 0.1,
    summary TEXT NULL,
    keywords VARIANT NULL,
    entities VARIANT NULL,
    language_detected VARCHAR(16) NOT NULL DEFAULT 'en-US',
    embedding_model VARCHAR(128) NOT NULL DEFAULT 'none',
    embedding_version VARCHAR(32) NOT NULL DEFAULT 'none',
    chunk_count INT NOT NULL DEFAULT 0,
    average_chunk_size INT NOT NULL DEFAULT 0,
    last_embedding_time TIMESTAMP_NTZ NULL,
    embedding_status VARCHAR(32) NOT NULL DEFAULT 'NOT_REQUIRED',
    evaluation_score FLOAT NULL DEFAULT NULL,
    confidence_score FLOAT NULL DEFAULT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- 4. Knowledge Document Chunks Table (First-Class Chunk Objects)
CREATE TABLE IF NOT EXISTS WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_CHUNKS (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS(id),
    state_id VARCHAR(64) NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.WORKFLOW_STATES(id),
    step_id VARCHAR(64) NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.WORKFLOW_STEPS(id),
    chunk_order INT NOT NULL DEFAULT 0,
    character_count INT NOT NULL DEFAULT 0,
    token_count INT NOT NULL DEFAULT 0,
    chunk_content TEXT NOT NULL,
    embedding_ref VARCHAR(128) NOT NULL DEFAULT 'none',
    vector_status VARCHAR(32) NOT NULL DEFAULT 'NOT_REQUIRED',
    chunk_hash VARCHAR(64) NOT NULL,
    chunk_type VARCHAR(64) NOT NULL DEFAULT 'STATE_STEP',
    section_name VARCHAR(255) NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- 5. Knowledge Document Lineage Audit Table
CREATE TABLE IF NOT EXISTS WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENT_LINEAGE (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS(id),
    workflow_version_id VARCHAR(64) NOT NULL REFERENCES WORKMATE_AI.KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS(id),
    stage_file_uri VARCHAR(512) NOT NULL,
    source_markdown_hash VARCHAR(64) NOT NULL,
    parser_name VARCHAR(64) NOT NULL DEFAULT 'OWDParser',
    ast_hash VARCHAR(64) NOT NULL,
    compiler_name VARCHAR(64) NOT NULL DEFAULT 'OWDCompiler',
    loader_name VARCHAR(64) NOT NULL DEFAULT 'OWDLoader',
    status VARCHAR(32) NOT NULL DEFAULT 'PUBLISHED',
    executed_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    execution_notes TEXT NULL,
    created_at TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================================================
-- Backfill Query for Pre-Existing Workflows
-- ============================================================================
INSERT INTO WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS (
    id, workflow_id, workflow_version_id, document_name, original_filename,
    stage_uri, relative_path, directory, extension, mime_type, file_size_bytes,
    sha256_hash, compiler_version, parser_version, source_type, language_code,
    author, reviewer, approval_status, tags, labels, description
)
SELECT 
    'doc_' || wv.id AS id,
    w.id AS workflow_id,
    wv.id AS workflow_version_id,
    w.title AS document_name,
    w.workflow_code || '.md' AS original_filename,
    wv.stage_file_uri AS stage_uri,
    'inbound/' || w.workflow_code || '.md' AS relative_path,
    'inbound' AS directory,
    'md' AS extension,
    'text/markdown' AS mime_type,
    LENGTH(COALESCE(w.description, w.title)) * 10 AS file_size_bytes,
    SHA2(COALESCE(wv.ast_hash, wv.id), 256) AS sha256_hash,
    '1.1.0' AS compiler_version,
    '1.1.0' AS parser_version,
    'OWD_MARKDOWN' AS source_type,
    'en-US' AS language_code,
    w.owner AS author,
    'System Supervisor' AS reviewer,
    'APPROVED' AS approval_status,
    ARRAY_CONSTRUCT(w.category, w.department_id) AS tags,
    OBJECT_CONSTRUCT('priority', w.priority, 'difficulty', w.difficulty) AS labels,
    w.description AS description
FROM WORKMATE_AI.KNOWLEDGE_STUDIO.WORKFLOWS w
JOIN WORKMATE_AI.KNOWLEDGE_STUDIO.WORKFLOW_VERSIONS wv ON wv.workflow_id = w.id
WHERE NOT EXISTS (
    SELECT 1 FROM WORKMATE_AI.KNOWLEDGE_STUDIO.KNOWLEDGE_DOCUMENTS kd WHERE kd.workflow_version_id = wv.id
);
