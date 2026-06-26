INSERT INTO ref.document_types (code, label, description) VALUES
    ('yse_1998', 'YSE 1998', 'Rakennusurakan yleiset sopimusehdot YSE 1998')
ON CONFLICT (code) DO UPDATE
SET label = EXCLUDED.label,
    description = EXCLUDED.description;

