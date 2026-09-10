CREATE TABLE IF NOT EXISTS cleanup_rules (
    id SERIAL PRIMARY KEY,
    scope VARCHAR(10) NOT NULL,
    domain VARCHAR(255),
    match_type VARCHAR(20) NOT NULL,
    pattern TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    note TEXT,
    source_removed_line_id INTEGER REFERENCES document_removed_lines(id) ON DELETE SET NULL,
    created_by VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    hit_count INTEGER NOT NULL DEFAULT 0,
    last_hit_at TIMESTAMP,
    CONSTRAINT ck_cleanup_rules_scope CHECK (scope IN ('global', 'domain')),
    CONSTRAINT ck_cleanup_rules_match_type CHECK (match_type IN ('literal_line', 'contains', 'regex'))
);
CREATE INDEX IF NOT EXISTS ix_cleanup_rules_active_scope ON cleanup_rules (active, scope);
CREATE INDEX IF NOT EXISTS ix_cleanup_rules_domain ON cleanup_rules (domain);
