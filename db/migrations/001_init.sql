CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS doc;
CREATE SCHEMA IF NOT EXISTS domain;
CREATE SCHEMA IF NOT EXISTS finance;
CREATE SCHEMA IF NOT EXISTS quality;
CREATE SCHEMA IF NOT EXISTS rag;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS ref;

CREATE TABLE IF NOT EXISTS ref.document_types (
    code text PRIMARY KEY,
    label text NOT NULL,
    description text
);

INSERT INTO ref.document_types (code, label, description) VALUES
    ('main_contract', 'Urakkasopimus', 'Sopimuksen ydinfaktat, osapuolet, aikataulu, vakuudet ja liiteluettelo'),
    ('negotiation_minutes', 'Urakkaneuvottelupöytäkirja', 'Urakan tarkennukset, hinnan muutokset ja sovitut täsmennykset'),
    ('contract_terms', 'Sopimusehdot', 'Tekniset ja kaupalliset ehdot, laatukriteerit ja lisätyöehdot'),
    ('rfq', 'Tarjouspyyntö', 'Tilaajan alkuperäinen urakkalaajuus ja tarjousvaatimukset'),
    ('rfq_clarification', 'Tarjouspyynnön tarkennus', 'Katselmuksessa sovitut tarkennukset ja urakkarajojen muutokset'),
    ('contractor_offer', 'Urakoitsijan tarjous', 'Urakoitsijan hinta, menetelmä, laajuus, ehdot ja poissulut'),
    ('unit_prices', 'Yksikköhintaluettelo', 'Lisätöiden ja optioiden yksikköhinnat'),
    ('payment_schedule', 'Maksuerätaulukko', 'Maksuerien summat ja maksukelpoisuusehdot'),
    ('drawing_index', 'Piirustusluettelo', 'Piirustusasiakirjat ja tekninen viitepaketti'),
    ('quality_manual', 'Laatukäsikirja', 'Laadunhallinta, tiedotus, tarkastus, työturvallisuus ja loppudokumentaatio'),
    ('security_document', 'Vakuusasiakirja', 'Vakuuden tyyppi, määrä, voimassaolo ja kattavuus')
ON CONFLICT (code) DO UPDATE
SET label = EXCLUDED.label,
    description = EXCLUDED.description;

CREATE TABLE IF NOT EXISTS ref.chunk_types (
    code text PRIMARY KEY,
    label text NOT NULL
);

INSERT INTO ref.chunk_types (code, label) VALUES
    ('contract_fact_summary', 'Sopimuksen ydinfaktat'),
    ('contract_clause', 'Sopimuskohta'),
    ('technical_requirement', 'Tekninen vaatimus'),
    ('payment_condition', 'Maksuehto'),
    ('unit_price', 'Yksikköhinta'),
    ('responsibility', 'Vastuunjakokohta'),
    ('quality_requirement', 'Laatuvaatimus'),
    ('deliverable', 'Luovutusasiakirjavaatimus'),
    ('document_precedence', 'Asiakirjojen pätevyysjärjestys')
ON CONFLICT (code) DO UPDATE SET label = EXCLUDED.label;

CREATE TABLE IF NOT EXISTS raw.source_files (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code text NOT NULL,
    original_filename text NOT NULL,
    stored_path text NOT NULL,
    document_type text NOT NULL REFERENCES ref.document_types(code),
    file_ext text NOT NULL,
    sha256 text NOT NULL UNIQUE,
    page_count integer,
    byte_size bigint,
    has_text_layer boolean,
    needs_ocr boolean,
    created_at timestamptz NOT NULL DEFAULT now(),
    notes text
);

CREATE TABLE IF NOT EXISTS raw.extraction_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_id uuid NOT NULL REFERENCES raw.source_files(id) ON DELETE CASCADE,
    extractor_name text NOT NULL,
    extractor_version text,
    extraction_started_at timestamptz NOT NULL DEFAULT now(),
    extraction_finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('created','running','completed','failed')),
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text
);

CREATE TABLE IF NOT EXISTS raw.pages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_id uuid NOT NULL REFERENCES raw.source_files(id) ON DELETE CASCADE,
    extraction_run_id uuid REFERENCES raw.extraction_runs(id) ON DELETE SET NULL,
    page_no integer NOT NULL CHECK (page_no > 0),
    raw_text text,
    raw_text_hash text,
    text_quality_score numeric(5,2),
    image_path text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_file_id, page_no)
);

CREATE TABLE IF NOT EXISTS raw.extracted_tables (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_id uuid NOT NULL REFERENCES raw.source_files(id) ON DELETE CASCADE,
    extraction_run_id uuid REFERENCES raw.extraction_runs(id) ON DELETE SET NULL,
    page_no integer,
    table_no integer,
    table_type text,
    raw_table_json jsonb NOT NULL,
    extraction_quality text,
    notes text
);

CREATE TABLE IF NOT EXISTS core.projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code text NOT NULL UNIQUE,
    project_name_redacted text NOT NULL,
    project_type text NOT NULL DEFAULT 'cipp_sukitusurakka',
    lifecycle_status text NOT NULL DEFAULT 'imported',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.properties (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES core.projects(id) ON DELETE CASCADE,
    property_code text NOT NULL,
    city_redacted text,
    building_year integer,
    building_count integer,
    stairwell_count integer,
    apartment_count integer,
    floor_area_m2 numeric(12,2),
    floor_count integer,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (project_id, property_code)
);

CREATE TABLE IF NOT EXISTS core.parties (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    party_code text NOT NULL UNIQUE,
    party_type text NOT NULL CHECK (party_type IN ('housing_company','contractor','consultant','property_manager','authority','insurer','other')),
    display_name_redacted text NOT NULL,
    original_name_hash text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS core.contacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    party_id uuid REFERENCES core.parties(id) ON DELETE CASCADE,
    role_title text,
    person_name_redacted text,
    person_name_hash text,
    email_hash text,
    phone_hash text,
    visible_to_ai boolean NOT NULL DEFAULT false,
    notes text
);

CREATE TABLE IF NOT EXISTS core.contracts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES core.projects(id) ON DELETE CASCADE,
    contract_code text NOT NULL,
    contract_type text NOT NULL DEFAULT 'construction_contract',
    contract_date date,
    revision text,
    subject text,
    standard_terms text,
    currency_code char(3) NOT NULL DEFAULT 'EUR',
    status text NOT NULL DEFAULT 'imported',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (project_id, contract_code)
);

CREATE TABLE IF NOT EXISTS core.contract_parties (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    party_id uuid NOT NULL REFERENCES core.parties(id),
    role text NOT NULL CHECK (role IN ('client','contractor','designer','supervisor','property_manager','chairperson','insurer','other')),
    valid_from date,
    valid_to date,
    UNIQUE (contract_id, party_id, role)
);

CREATE TABLE IF NOT EXISTS core.contract_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    source_file_id uuid REFERENCES raw.source_files(id),
    document_type text NOT NULL REFERENCES ref.document_types(code),
    document_title_redacted text NOT NULL,
    attachment_no text,
    document_date date,
    revision text,
    page_count integer,
    precedence_rank integer,
    is_contract_document boolean NOT NULL DEFAULT true,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS core.document_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_document_id uuid NOT NULL REFERENCES core.contract_documents(id) ON DELETE CASCADE,
    source_file_id uuid REFERENCES raw.source_files(id),
    version_label text NOT NULL,
    version_no integer NOT NULL,
    content_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (contract_document_id, version_no)
);

CREATE TABLE IF NOT EXISTS doc.sections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_document_id uuid NOT NULL REFERENCES core.contract_documents(id) ON DELETE CASCADE,
    parent_section_id uuid REFERENCES doc.sections(id) ON DELETE CASCADE,
    section_order integer NOT NULL,
    section_key text NOT NULL,
    title text,
    body_text text NOT NULL,
    page_start integer,
    page_end integer,
    source_confidence numeric(5,2),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (contract_document_id, section_order)
);

CREATE TABLE IF NOT EXISTS doc.clauses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id uuid NOT NULL REFERENCES doc.sections(id) ON DELETE CASCADE,
    clause_key text,
    clause_type text NOT NULL,
    title text,
    clause_text text NOT NULL,
    normalized_summary text,
    legal_effect text,
    source_page integer,
    source_quote_hash text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS doc.obligations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    obligated_role text NOT NULL,
    beneficiary_role text,
    obligation_type text NOT NULL,
    obligation_text text NOT NULL,
    trigger_condition text,
    deadline_text text,
    evidence_required text,
    consequence_text text,
    confidence numeric(5,2),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS doc.cross_references (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_clause_id uuid REFERENCES doc.clauses(id) ON DELETE CASCADE,
    to_document_id uuid REFERENCES core.contract_documents(id) ON DELETE CASCADE,
    to_section_key text,
    reference_text text NOT NULL,
    reference_type text
);

CREATE TABLE IF NOT EXISTS domain.scope_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    item_code text NOT NULL,
    system_type text NOT NULL CHECK (system_type IN ('JV','SV','KPA','floor_drain','wc','other')),
    item_name text NOT NULL,
    included_in_contract boolean NOT NULL,
    is_option boolean NOT NULL DEFAULT false,
    is_extra_work boolean NOT NULL DEFAULT false,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    notes text,
    UNIQUE (contract_id, item_code)
);

CREATE TABLE IF NOT EXISTS domain.contract_boundaries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    system_type text NOT NULL CHECK (system_type IN ('JV','SV','KPA','other')),
    upstream_boundary text,
    downstream_boundary text,
    inspected boolean,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS domain.technical_requirements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    requirement_code text NOT NULL,
    requirement_type text NOT NULL,
    requirement_text text NOT NULL,
    numeric_limit numeric(12,4),
    unit text,
    standard_ref text,
    applies_to text,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    UNIQUE (contract_id, requirement_code)
);

CREATE TABLE IF NOT EXISTS domain.responsibility_matrix (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    responsibility_key text NOT NULL,
    responsibility_area text NOT NULL,
    responsible_role text NOT NULL,
    details text,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    UNIQUE (contract_id, responsibility_key)
);

CREATE TABLE IF NOT EXISTS domain.schedule_milestones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    milestone_key text NOT NULL,
    milestone_name text NOT NULL,
    planned_date date,
    planned_start date,
    planned_finish date,
    qualifier text,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    UNIQUE (contract_id, milestone_key)
);

CREATE TABLE IF NOT EXISTS domain.inspections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    inspection_type text NOT NULL,
    required_by_role text,
    performed_by_role text,
    inspection_text text NOT NULL,
    evidence_required text,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS finance.contract_prices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    price_type text NOT NULL CHECK (price_type IN ('fixed_contract_price','option','extra_work','unit_price_total')),
    amount_net numeric(14,2),
    vat_rate numeric(5,2),
    vat_amount numeric(14,2),
    amount_gross numeric(14,2),
    currency_code char(3) NOT NULL DEFAULT 'EUR',
    price_text text,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    CHECK (amount_net IS NULL OR amount_net >= 0),
    CHECK (amount_gross IS NULL OR amount_gross >= 0)
);

CREATE TABLE IF NOT EXISTS finance.payment_schedule_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    item_no integer NOT NULL,
    amount_net numeric(14,2) NOT NULL,
    vat_rate numeric(5,2),
    vat_amount numeric(14,2),
    amount_gross numeric(14,2),
    payment_condition text NOT NULL,
    source_document_id uuid REFERENCES core.contract_documents(id) ON DELETE SET NULL,
    source_table_id uuid REFERENCES raw.extracted_tables(id) ON DELETE SET NULL,
    UNIQUE (contract_id, item_no)
);

CREATE TABLE IF NOT EXISTS finance.unit_prices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    unit_price_code text NOT NULL,
    item_name text NOT NULL,
    unit text,
    amount_gross numeric(14,2),
    amount_net numeric(14,2),
    vat_rate numeric(5,2),
    condition_text text,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    UNIQUE (contract_id, unit_price_code)
);

CREATE TABLE IF NOT EXISTS finance.securities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    security_type text NOT NULL CHECK (security_type IN ('construction_period','warranty_period','other')),
    amount numeric(14,2),
    amount_percent numeric(5,2),
    basis text,
    validity_text text,
    issuer_role text,
    beneficiary_role text,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS finance.insurances (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    insurance_type text NOT NULL,
    required_by_role text,
    coverage_amount numeric(14,2),
    coverage_text text,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS finance.penalties (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    penalty_type text NOT NULL,
    percent_per_workday numeric(8,4),
    max_workdays integer,
    basis text,
    calculation_text text,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS quality.requirements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    requirement_key text NOT NULL,
    requirement_category text NOT NULL,
    requirement_text text NOT NULL,
    acceptance_criteria text,
    evidence_required text,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    UNIQUE (contract_id, requirement_key)
);

CREATE TABLE IF NOT EXISTS quality.deliverables (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    deliverable_key text NOT NULL,
    deliverable_name text NOT NULL,
    required_at text,
    required_by_role text,
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    UNIQUE (contract_id, deliverable_key)
);

CREATE TABLE IF NOT EXISTS quality.nonconformities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    finding_text text NOT NULL,
    severity text CHECK (severity IN ('low','medium','high','critical')),
    status text NOT NULL DEFAULT 'open',
    source_document_id uuid REFERENCES core.contract_documents(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag.embedding_models (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name text NOT NULL UNIQUE,
    provider text NOT NULL,
    dimension integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag.chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    contract_document_id uuid REFERENCES core.contract_documents(id) ON DELETE CASCADE,
    section_id uuid REFERENCES doc.sections(id) ON DELETE SET NULL,
    clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    chunk_order integer NOT NULL,
    chunk_type text NOT NULL REFERENCES ref.chunk_types(code),
    content_redacted text NOT NULL,
    content_hash text NOT NULL,
    token_count integer,
    page_start integer,
    page_end integer,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    search_vector_fi tsvector GENERATED ALWAYS AS (to_tsvector('finnish', coalesce(content_redacted,''))) STORED,
    search_vector_simple tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content_redacted,''))) STORED,
    UNIQUE (contract_id, content_hash)
);

CREATE TABLE IF NOT EXISTS rag.chunk_embeddings_1536 (
    chunk_id uuid PRIMARY KEY REFERENCES rag.chunks(id) ON DELETE CASCADE,
    embedding_model_id uuid NOT NULL REFERENCES rag.embedding_models(id),
    embedding vector(1536) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag.eval_questions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    question_code text NOT NULL UNIQUE,
    project_code text,
    question text NOT NULL,
    expected_source_document_type text REFERENCES ref.document_types(code),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.canonical_contract_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid REFERENCES core.projects(id) ON DELETE CASCADE,
    contract_id uuid REFERENCES core.contracts(id) ON DELETE CASCADE,
    version_no integer NOT NULL,
    canonical_json jsonb NOT NULL,
    canonical_hash text NOT NULL,
    validation_status text NOT NULL DEFAULT 'created' CHECK (validation_status IN ('created','valid','valid_with_warnings','invalid')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (contract_id, version_no)
);

CREATE TABLE IF NOT EXISTS core.contract_drafts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_code text NOT NULL UNIQUE,
    based_on_project_ids uuid[] NOT NULL DEFAULT '{}',
    draft_json jsonb NOT NULL,
    validation_status text NOT NULL DEFAULT 'created' CHECK (validation_status IN ('created','valid','valid_with_warnings','invalid')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit.validation_issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid REFERENCES core.projects(id) ON DELETE CASCADE,
    contract_id uuid REFERENCES core.contracts(id) ON DELETE CASCADE,
    issue_type text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('info','warning','error','critical')),
    message text NOT NULL,
    source_table text,
    source_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE TABLE IF NOT EXISTS audit.pii_findings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_id uuid REFERENCES raw.source_files(id) ON DELETE CASCADE,
    location_text text,
    pii_type text NOT NULL,
    raw_value_hash text NOT NULL,
    replacement_value text,
    visibility_decision text NOT NULL CHECK (visibility_decision IN ('redact','hash','allow_internal','manual_review')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_source_files_project ON raw.source_files(project_code);
CREATE INDEX IF NOT EXISTS idx_source_files_document_type ON raw.source_files(document_type);
CREATE INDEX IF NOT EXISTS idx_contract_documents_contract ON core.contract_documents(contract_id);
CREATE INDEX IF NOT EXISTS idx_contract_documents_type ON core.contract_documents(document_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contract_documents_unique_doc
ON core.contract_documents(contract_id, document_type, coalesce(attachment_no, ''));
CREATE INDEX IF NOT EXISTS idx_sections_document_order ON doc.sections(contract_document_id, section_order);
CREATE INDEX IF NOT EXISTS idx_clauses_type ON doc.clauses(clause_type);
CREATE INDEX IF NOT EXISTS idx_clauses_key_trgm ON doc.clauses USING GIN ((coalesce(clause_key, '')) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_obligations_contract_role ON doc.obligations(contract_id, obligated_role);
CREATE INDEX IF NOT EXISTS idx_scope_contract_system ON domain.scope_items(contract_id, system_type);
CREATE INDEX IF NOT EXISTS idx_payment_contract_item ON finance.payment_schedule_items(contract_id, item_no);
CREATE INDEX IF NOT EXISTS idx_chunks_contract_type ON rag.chunks(contract_id, chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_search_vector_fi ON rag.chunks USING GIN(search_vector_fi);
CREATE INDEX IF NOT EXISTS idx_chunks_search_vector_simple ON rag.chunks USING GIN(search_vector_simple);
CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON rag.chunks USING GIN(metadata);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_1536_hnsw
ON rag.chunk_embeddings_1536
USING hnsw (embedding vector_cosine_ops);
