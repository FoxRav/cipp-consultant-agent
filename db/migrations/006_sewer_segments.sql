CREATE TABLE IF NOT EXISTS domain.sewer_segments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id) ON DELETE CASCADE,
    system_type text NOT NULL CHECK (system_type IN ('JV','SV')),
    segment_type text NOT NULL CHECK (
        segment_type IN (
            'apartment_branches',
            'vertical_stacks',
            'base_drain',
            'plot_line',
            'yard_drains',
            'roof_drains'
        )
    ),
    flow_order integer NOT NULL,
    segment_name text NOT NULL,
    included_in_contract boolean,
    inclusion_confidence numeric(5,2),
    boundary_text text,
    pricing_impact text,
    source_document_type text REFERENCES ref.document_types(code),
    source_clause_id uuid REFERENCES doc.clauses(id) ON DELETE SET NULL,
    notes text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (contract_id, system_type, segment_type)
);

CREATE INDEX IF NOT EXISTS idx_sewer_segments_contract_system
ON domain.sewer_segments(contract_id, system_type, flow_order);

