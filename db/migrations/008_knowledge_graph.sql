CREATE SCHEMA IF NOT EXISTS kg;

CREATE TABLE IF NOT EXISTS kg.entity_types (
    code text PRIMARY KEY,
    description text,
    created_at timestamptz DEFAULT now()
);

INSERT INTO kg.entity_types (code, description) VALUES
    ('project', 'Reference or customer project'),
    ('contract', 'Contract under a project'),
    ('document', 'Contract or source document'),
    ('section', 'Document section'),
    ('clause', 'Document clause'),
    ('party', 'Contract party or stakeholder'),
    ('property', 'Property or housing company fact set'),
    ('scope_item', 'Contract scope item'),
    ('boundary', 'Contract boundary or limit'),
    ('sewer_segment', 'JV/SV sewer segment'),
    ('responsibility', 'Responsibility assignment'),
    ('technical_requirement', 'Technical requirement'),
    ('quality_requirement', 'Quality requirement'),
    ('payment_item', 'Payment schedule item'),
    ('unit_price', 'Unit price item'),
    ('security', 'Security or guarantee'),
    ('insurance', 'Insurance requirement or record'),
    ('inspection', 'Inspection or review'),
    ('defect', 'Defect, open item, or quality issue'),
    ('handover', 'Handover or reception record'),
    ('warranty_issue', 'Warranty issue or warranty-related note'),
    ('event', 'Operational project event')
ON CONFLICT (code) DO UPDATE
SET description = EXCLUDED.description;

CREATE TABLE IF NOT EXISTS kg.relation_types (
    code text PRIMARY KEY,
    description text,
    created_at timestamptz DEFAULT now()
);

INSERT INTO kg.relation_types (code, description) VALUES
    ('CONTAINS', 'Subject contains object'),
    ('PART_OF', 'Subject is part of object'),
    ('MENTIONS', 'Subject mentions object'),
    ('HAS_CONTRACT', 'Project has contract'),
    ('HAS_DOCUMENT', 'Project has document'),
    ('HAS_PARTY', 'Contract has party'),
    ('HAS_SECTION', 'Document has section'),
    ('HAS_CLAUSE', 'Section has clause'),
    ('DEFINES', 'Subject defines object'),
    ('REQUIRES', 'Subject requires object'),
    ('RESPONSIBLE_FOR', 'Party is responsible for object'),
    ('AFFECTS', 'Subject affects object'),
    ('DEPENDS_ON', 'Subject depends on object'),
    ('PAID_BY', 'Subject is paid by object'),
    ('DOCUMENTED_IN', 'Subject is documented in object'),
    ('SUPPORTED_BY', 'Subject is supported by object evidence'),
    ('OBSERVED_IN', 'Subject was observed in object'),
    ('RESOLVED_BY', 'Subject was resolved by object'),
    ('PRECEDES', 'Subject precedes object'),
    ('RELATED_TO', 'Subject is related to object'),
    ('CONFLICTS_WITH', 'Subject conflicts with object')
ON CONFLICT (code) DO UPDATE
SET description = EXCLUDED.description;

CREATE TABLE IF NOT EXISTS kg.entities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type text NOT NULL REFERENCES kg.entity_types(code),
    canonical_key text NOT NULL,
    canonical_name text NOT NULL,
    display_name text,
    project_id uuid NULL,
    document_id uuid NULL,
    source_table text NULL,
    source_id uuid NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    UNIQUE (entity_type, canonical_key)
);

CREATE TABLE IF NOT EXISTS kg.relations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_entity_id uuid NOT NULL REFERENCES kg.entities(id) ON DELETE CASCADE,
    relation_type text NOT NULL REFERENCES kg.relation_types(code),
    object_entity_id uuid NOT NULL REFERENCES kg.entities(id) ON DELETE CASCADE,
    project_id uuid NULL,
    confidence numeric(5,4) NOT NULL DEFAULT 1.0,
    extraction_method text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    UNIQUE (subject_entity_id, relation_type, object_entity_id)
);

CREATE TABLE IF NOT EXISTS kg.evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id uuid NULL REFERENCES kg.entities(id) ON DELETE CASCADE,
    relation_id uuid NULL REFERENCES kg.relations(id) ON DELETE CASCADE,
    source_file_id uuid NULL,
    page_id uuid NULL,
    section_id uuid NULL,
    clause_id uuid NULL,
    extraction_run_id uuid NULL,
    source_table text NULL,
    source_id uuid NULL,
    quote_text text NULL,
    evidence_note text NULL,
    confidence numeric(5,4) NOT NULL DEFAULT 1.0,
    created_at timestamptz DEFAULT now(),
    CHECK (entity_id IS NOT NULL OR relation_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_kg_entities_type ON kg.entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_kg_entities_project ON kg.entities(project_id);
CREATE INDEX IF NOT EXISTS idx_kg_entities_document ON kg.entities(document_id);
CREATE INDEX IF NOT EXISTS idx_kg_entities_source ON kg.entities(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_kg_entities_metadata ON kg.entities USING gin(metadata);
CREATE INDEX IF NOT EXISTS idx_kg_relations_subject ON kg.relations(subject_entity_id);
CREATE INDEX IF NOT EXISTS idx_kg_relations_object ON kg.relations(object_entity_id);
CREATE INDEX IF NOT EXISTS idx_kg_relations_type ON kg.relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_kg_relations_project ON kg.relations(project_id);
CREATE INDEX IF NOT EXISTS idx_kg_relations_metadata ON kg.relations USING gin(metadata);
CREATE INDEX IF NOT EXISTS idx_kg_evidence_entity ON kg.evidence(entity_id);
CREATE INDEX IF NOT EXISTS idx_kg_evidence_relation ON kg.evidence(relation_id);
CREATE INDEX IF NOT EXISTS idx_kg_evidence_source_file ON kg.evidence(source_file_id);
CREATE INDEX IF NOT EXISTS idx_kg_evidence_page ON kg.evidence(page_id);
CREATE INDEX IF NOT EXISTS idx_kg_evidence_section ON kg.evidence(section_id);
CREATE INDEX IF NOT EXISTS idx_kg_evidence_clause ON kg.evidence(clause_id);
CREATE INDEX IF NOT EXISTS idx_kg_evidence_source ON kg.evidence(source_table, source_id);
