CREATE SCHEMA IF NOT EXISTS legal;

INSERT INTO ref.document_types (code, label, description) VALUES
    (
        'legal_guidance_pipe_renovation',
        'Asiantuntijaopas',
        'Non-binding expert guidance for housing-company pipe renovation planning and decision processes'
    )
ON CONFLICT (code) DO UPDATE
SET label = EXCLUDED.label,
    description = EXCLUDED.description;

INSERT INTO kg.entity_types (code, description) VALUES
    ('guidance_document', 'Non-binding expert guidance document'),
    ('guidance_section', 'Section or chapter in expert guidance'),
    ('guidance_item', 'Rules-first extracted guidance item'),
    ('process_stage', 'Project or decision process stage'),
    ('decision_point', 'Decision point in guidance'),
    ('risk_warning', 'Risk or warning in guidance'),
    ('legal_cross_reference', 'Mentioned legal source requiring verification')
ON CONFLICT (code) DO UPDATE
SET description = EXCLUDED.description;

INSERT INTO kg.relation_types (code, description) VALUES
    ('GUIDES', 'Subject guides object or topic'),
    ('APPLIES_TO_STAGE', 'Guidance applies to a process stage'),
    ('HAS_GUIDANCE_ITEM', 'Guidance document or section has guidance item'),
    ('HAS_DECISION_POINT', 'Guidance document has a decision point'),
    ('HAS_RISK_WARNING', 'Guidance document has a risk warning'),
    ('MENTIONS_LEGAL_SOURCE', 'Guidance item mentions a legal source'),
    ('SUPPORTS_USER_ANSWER', 'Guidance item can support a user-facing answer'),
    ('NEEDS_VERIFICATION_FROM_LAW', 'Mentioned legal source needs verification from binding law')
ON CONFLICT (code) DO UPDATE
SET description = EXCLUDED.description;

CREATE TABLE IF NOT EXISTS legal.guidance_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_code text NOT NULL UNIQUE,
    title text NOT NULL,
    author text,
    publisher text,
    edition text,
    publication_year int,
    source_type text NOT NULL,
    authority_level text NOT NULL,
    binding_status text NOT NULL,
    legal_role text,
    user_facing_role text,
    requires_cross_reference boolean NOT NULL DEFAULT true,
    source_file_id uuid REFERENCES raw.source_files(id) ON DELETE SET NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    CHECK (source_type IN ('expert_guidance')),
    CHECK (authority_level IN ('non_binding_guidance')),
    CHECK (binding_status IN ('not_binding_law'))
);

CREATE TABLE IF NOT EXISTS legal.guidance_sections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    guidance_document_id uuid NOT NULL REFERENCES legal.guidance_documents(id) ON DELETE CASCADE,
    section_number text,
    title text,
    page_start int,
    page_end int,
    parent_section_id uuid NULL REFERENCES legal.guidance_sections(id) ON DELETE CASCADE,
    text_hash text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    UNIQUE (guidance_document_id, section_number, title, page_start)
);

CREATE TABLE IF NOT EXISTS legal.guidance_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    guidance_document_id uuid NOT NULL REFERENCES legal.guidance_documents(id) ON DELETE CASCADE,
    section_id uuid REFERENCES legal.guidance_sections(id) ON DELETE SET NULL,
    item_type text NOT NULL,
    topic_code text,
    process_stage text,
    actor text,
    guidance_summary text NOT NULL,
    legal_relevance text,
    binding_status text NOT NULL,
    confidence numeric(5,4) DEFAULT 1.0,
    page_number int,
    source_file_id uuid REFERENCES raw.source_files(id) ON DELETE SET NULL,
    page_id uuid REFERENCES raw.pages(id) ON DELETE SET NULL,
    section_ref text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    CHECK (item_type IN (
        'principle',
        'planning_step',
        'decision_point',
        'checklist_item',
        'risk_warning',
        'method_condition',
        'project_stage',
        'actor_responsibility',
        'document_requirement',
        'inspection_requirement',
        'warranty_or_handover_note',
        'legal_cross_reference'
    )),
    CHECK (process_stage IS NULL OR process_stage IN (
        'property_strategy',
        'condition_monitoring',
        'needs_assessment',
        'condition_survey',
        'method_selection',
        'project_planning',
        'design',
        'procurement',
        'contracting',
        'construction',
        'supervision',
        'handover',
        'warranty',
        'cost_reporting'
    )),
    CHECK (topic_code IS NULL OR topic_code IN (
        'maintenance_strategy',
        'maintenance_need',
        'pipe_lifetime',
        'water_pipe_condition',
        'sewer_condition',
        'condition_survey',
        'test_milling',
        'repair_options',
        'coating',
        'cipp_lining',
        'hybrid_solution',
        'project_governance',
        'housing_company_decision',
        'shareholder_information',
        'design_procurement',
        'contractor_procurement',
        'contract_negotiation',
        'safety_coordination',
        'moisture_management',
        'supervision',
        'handover',
        'financial_final_account',
        'warranty',
        'cost_statement'
    )),
    CHECK (actor IS NULL OR actor IN (
        'housing_company',
        'board',
        'shareholders',
        'property_manager',
        'designer',
        'supervisor',
        'contractor',
        'safety_coordinator',
        'project_manager',
        'resident',
        'unknown'
    )),
    CHECK (binding_status IN ('not_binding_law')),
    UNIQUE (guidance_document_id, page_number, section_ref, item_type, guidance_summary)
);

CREATE INDEX IF NOT EXISTS idx_guidance_documents_source_file ON legal.guidance_documents(source_file_id);
CREATE INDEX IF NOT EXISTS idx_guidance_sections_document ON legal.guidance_sections(guidance_document_id);
CREATE INDEX IF NOT EXISTS idx_guidance_sections_page ON legal.guidance_sections(page_start, page_end);
CREATE INDEX IF NOT EXISTS idx_guidance_items_document ON legal.guidance_items(guidance_document_id);
CREATE INDEX IF NOT EXISTS idx_guidance_items_section ON legal.guidance_items(section_id);
CREATE INDEX IF NOT EXISTS idx_guidance_items_topic ON legal.guidance_items(topic_code);
CREATE INDEX IF NOT EXISTS idx_guidance_items_stage ON legal.guidance_items(process_stage);
CREATE INDEX IF NOT EXISTS idx_guidance_items_actor ON legal.guidance_items(actor);
CREATE INDEX IF NOT EXISTS idx_guidance_items_page ON legal.guidance_items(page_id);
CREATE INDEX IF NOT EXISTS idx_guidance_items_metadata ON legal.guidance_items USING gin(metadata);
