CREATE TABLE IF NOT EXISTS raw.source_file_document_types (
    source_file_id uuid NOT NULL REFERENCES raw.source_files(id) ON DELETE CASCADE,
    document_type text NOT NULL REFERENCES ref.document_types(code),
    is_primary boolean NOT NULL DEFAULT false,
    notes text,
    PRIMARY KEY (source_file_id, document_type)
);

CREATE INDEX IF NOT EXISTS idx_source_file_document_types_type
ON raw.source_file_document_types(document_type);

