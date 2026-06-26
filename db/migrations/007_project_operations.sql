INSERT INTO ref.document_types (code, label, description) VALUES
    ('change_order_offer', 'Lisatyotarjous', 'Urakan aikainen lisa- tai muutostyotarjous'),
    ('contract_program', 'Urakkaohjelma', 'Urakkaohjelma tai vastaava toteutusta ohjaava asiakirja'),
    ('drawing', 'Piirustus', 'Projektin piirustus tai kuva-aineisto'),
    ('drawing_index', 'Piirustusluettelo', 'Piirustusluettelo'),
    ('financial_final_report', 'Taloudellinen loppuselvitys', 'Vastaanottoon tai lopputilitykseen liittyva rahaliikenneasiakirja'),
    ('financial_tracking', 'Rahaliikenteen seuranta', 'Projektin rahaliikenteen seuranta- tai taulukkoaineisto'),
    ('handover_attachment', 'Vastaanoton liite', 'Vastaanottoon liittyva liiteaineisto'),
    ('handover_minutes', 'Vastaanottopoytakirja', 'Vastaanotto- tai taloudellisen loppuselvityksen poytakirja'),
    ('kickoff_meeting', 'Aloituskokous', 'Tyomaan aloituskokouksen asiakirja'),
    ('kvv_correction_photo', 'KVV-korjauskuva', 'KVV-tarkastukseen tai korjaukseen liittyva kuva'),
    ('kvv_inspection', 'KVV-tarkastus', 'KVV- tai katselmusasiakirja'),
    ('moisture_measurement_photo', 'Kosteusmittauskuva', 'Kosteusmittaukseen liittyva kuva'),
    ('payment_approval', 'Maksueran hyvaksynta', 'Hyvaksytty maksueran tai laskun asiakirja'),
    ('photo_documentation', 'Kuvadokumentaatio', 'Projektin kuva-aineisto'),
    ('project_correspondence', 'Projektikirjeenvaihto', 'Projektin kirjeenvaihto tai tiedoksianto'),
    ('project_management_table', 'Projektinhallintataulukko', 'Projektinhallinnan taulukkoaineisto'),
    ('resident_feedback', 'Asukaspalaute', 'Asukkaan palaute tai reklamaatio'),
    ('resident_notice', 'Asukastiedote', 'Asukkaille tai käyttäjille jaettu tiedote'),
    ('site_diary', 'Tyomaapaivakirja', 'Tyomaan paivakirja tai paivittainen seuranta'),
    ('site_meeting', 'Tyomaakokous', 'Tyomaakokouksen poytakirja tai liite'),
    ('supervisor_comment_file', 'Valvojan kommenttitiedosto', 'Valvojan kommentti- tai tarkastusaineisto'),
    ('technical_work_description', 'Tekninen tyoselostus', 'Tekninen tyoselostus tai menetelmakuvaus'),
    ('video_inspection_report', 'Videotarkastusraportti', 'Valvojan videotarkastusraportti tai kommenttiaineisto'),
    ('warranty_security', 'Takuuajan vakuus', 'Takuuajan vakuutta koskeva asiakirja'),
    ('work_plan', 'Tyosuunnitelma', 'Urakoitsijan tyosuunnitelma')
ON CONFLICT (code) DO UPDATE
SET label = EXCLUDED.label,
    description = EXCLUDED.description;

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.project_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code text NOT NULL REFERENCES core.projects(project_code) ON DELETE CASCADE,
    event_type text NOT NULL,
    event_date date,
    title text NOT NULL,
    source_file_id uuid REFERENCES raw.source_files(id) ON DELETE SET NULL,
    source_document_type text REFERENCES ref.document_types(code),
    summary text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_project_events_project_date
ON ops.project_events(project_code, event_date, event_type);

CREATE TABLE IF NOT EXISTS ops.project_observations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_event_id uuid REFERENCES ops.project_events(id) ON DELETE CASCADE,
    project_code text NOT NULL REFERENCES core.projects(project_code) ON DELETE CASCADE,
    observation_type text NOT NULL,
    severity text,
    system_type text,
    location_text text,
    issue_text text NOT NULL,
    decision_text text,
    action_text text,
    responsible_role text,
    status text,
    source_file_id uuid REFERENCES raw.source_files(id) ON DELETE SET NULL,
    source_page integer,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_project_observations_project_type
ON ops.project_observations(project_code, observation_type);

CREATE TABLE IF NOT EXISTS ops.handover_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code text NOT NULL REFERENCES core.projects(project_code) ON DELETE CASCADE,
    handover_date date,
    source_file_id uuid REFERENCES raw.source_files(id) ON DELETE SET NULL,
    accepted boolean,
    accepted_with_remarks boolean,
    handover_summary text,
    open_items_text text,
    financial_settlement_text text,
    warranty_text text,
    attachments jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.payment_approvals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code text NOT NULL REFERENCES core.projects(project_code) ON DELETE CASCADE,
    source_file_id uuid REFERENCES raw.source_files(id) ON DELETE SET NULL,
    approval_date date,
    invoice_or_payment_ref text,
    payment_item_text text,
    amount_gross numeric(12,2),
    approval_status text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
