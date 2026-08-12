-- Accept descriptive metadata from JSON/table-authored OWD documents without truncation.
ALTER TABLE KNOWLEDGE_STUDIO.workflows ALTER COLUMN estimated_duration SET DATA TYPE VARCHAR(512);
ALTER TABLE KNOWLEDGE_STUDIO.workflows ALTER COLUMN review_cycle SET DATA TYPE VARCHAR(512);
