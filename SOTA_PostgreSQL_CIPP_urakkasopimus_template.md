# SOTA PostgreSQL -tietokantatemplate: Korjausrakentamisen urakkasopimukset, CIPP-sukitusurakat

Versio: 0.1
Tila: tekninen toteutusohje ja tietokantapohja
Domain: korjausrakentamisen urakkasopimus, erityisesti viemärisaneerauksen CIPP-sukitusurakat
Pilottiaineisto: yksi anonymisoitu taloyhtiön sukitusurakkakokonaisuus, johon kuuluu pääsopimus, neuvottelupöytäkirja, sopimusehdot, tarjouspyyntö, tarjouspyynnön tarkennus, urakoitsijan tarjous, yksikköhinnat, maksuerätaulukko, piirustusluettelo, laatukäsikirja ja vakuusasiakirja.

Huomio: tässä dokumentissa henkilöiden, taloyhtiöiden ja yritysten nimet korvataan rooleilla ja tunnisteilla. Tuotantotietokannassa AI:n näkyviin hakukerroksiin ei viedä oikeita henkilö- tai organisaationimiä.

---

## 1. Tavoite

Tavoite on rakentaa PostgreSQL-tietokanta, joka ei ole vain dokumenttivarasto, vaan CIPP-sukitusurakoiden analyysi-, haku-, vertailu- ja sopimusgenerointialusta.

Tietokannan pitää kyetä vastaamaan esimerkiksi seuraaviin kysymyksiin:

- Mikä on urakan kohde ja tekninen laajuus?
- Mihin urakkarajat on määritetty JV- ja SV-linjoissa?
- Mitkä asiakirjat kuuluvat sopimuskokonaisuuteen ja missä pätevyysjärjestyksessä?
- Miten vastuut jakautuvat tilaajan, urakoitsijan, valvojan ja suunnittelijan kesken?
- Mitkä asiat kuuluvat urakkahintaan ja mitkä ovat lisätyötä?
- Milla ehdolla maksuerät tulevat maksukelpoisiksi?
- Mitä laatukriteereitä, tarkastuksia ja loppudokumentteja urakassa vaaditaan?
- Miten vakuudet, vakuutukset, viivästyssakot ja takuut määräytyvät?
- Miten uusi sopimusluonnos voidaan generoida vanhojen sopimuspakettien perusteella ilman, että PII vuotaa ulos?

---

## 2. Periaate: ei leveää CSV-taulua

Alkuperäinen CSV-purku on hyödyllinen ensimmäinen inventaario, mutta sitä ei pidetä lopullisena tietomallina.

Oikea malli:

```text
PDF-aineisto
-> raakateksti ja sivukohtainen data
-> canonical JSON
-> normalisoitu PostgreSQL
-> clause/chunk/embedding -kerros
-> validointi ja haku
-> analyysi ja sopimusluonnos
```

Sopimus ei ole yksi rivi. Sopimus on kokonaisuus:

```text
projekti
  -> rakennuskohde
  -> sopimukset
  -> sopimusasiakirjat
  -> osapuolet ja roolit
  -> urakkalaajuus
  -> tekniset vaatimukset
  -> vastuumatriisi
  -> maksuerät
  -> vakuudet
  -> vakuutukset
  -> laatu- ja tarkastusvaatimukset
  -> liitteet
  -> sopimuslausekkeet
  -> RAG-chunkit ja embeddingit
```

---

## 3. SOTA-määritelmä tässä projektissa

Tässä projektissa SOTA-taso ei tarkoita monimutkaisinta mahdollista tietokantaa. Se tarkoittaa seuraavaa:

1. Jäljitettävyys: jokainen fakta voidaan palauttaa alkuperäiseen dokumenttiin, sivuun ja kohtaan.
2. Normalisointi: rahat, päivämäärät, roolit, maksuerät ja vastuut ovat omissa tauluissaan.
3. Clause layer: pitkiä sopimuskohtia ei pakoteta relaatiokenttiin, vaan ne tallennetaan sopimuskohtina.
4. Hybridihaku: PostgreSQL full-text search + pgvector semantic search + metadatafiltterit.
5. PII-erotus: oikeat nimet ja yhteystiedot erotetaan AI:n käyttämästä anonymisoidusta datasta.
6. Validointi: summat, ALV, maksuerät, vakuudet, päivämäärät ja liiteluettelo tarkistetaan automaattisesti.
7. Versiointi: jokainen dokumentti, ekstraktio ja sopimusluonnos saa oman version.
8. Domain-ontologia: tietokanta ymmärtää CIPP-sukitusurakan käsitteet, ei vain tekstiä.
9. Hallittu RAG: chunkit muodostetaan sopimusrakenteen mukaan, ei satunnaisilla merkkimääräikkunoilla.
10. Toistettava ETL: sama prosessi voidaan ajaa jokaiselle uudelle urakkapaketille.

---

## 4. Lähdemateriaalin dokumenttityypit

Pilottiaineistosta tunnistetaan nämä dokumenttityypit. Käytä naita tyyppikoodeja tietokannassa.

| Tyyppikoodi | Dokumentti | Tarkoitus tietokannassa |
|---|---|---|
| `main_contract` | Urakkasopimus | sopimuksen ydinfaktat, osapuolet, aikataulu, vakuudet, viivästyssakko, liiteluettelo |
| `negotiation_minutes` | Urakkaneuvottelupöytäkirja | urakan tarkennukset, hinnan muutokset, yksikköhintojen sovinnat, lisähuomiot |
| `contract_terms` | Sopimusehtoja | tekniset ja kaupalliset ehdot, laatukriteerit, lisätyöehdot, maksukelpoisuusehdot |
| `rfq` | Tarjouspyynto | tilaajan alkuperäinen urakkalaajuus ja tarjousvaatimukset |
| `rfq_clarification` | Tarjouspyynnon tarkennus | katselmuksessa sovitut tarkennukset ja urakkarajojen muutokset |
| `contractor_offer` | Urakoitsijan tarjous | urakoitsijan hinta, menetelmä, laajuus, ehdot ja poissulut |
| `unit_prices` | Yksikköhintaluettelo | lisätöiden ja optioiden yksikköhinnat |
| `payment_schedule` | Maksuerätaulukko | maksuerien summat ja maksukelpoisuusehdot |
| `drawing_index` | Piirustusluettelo | piirustusasiakirjat ja tekninen viitepaketti |
| `quality_manual` | Laatukasikirja | laadunhallinta, tiedotus, tarkastus, työturvallisuus, loppudokumentaatio |
| `security_document` | Vakuusasiakirja | vakuuden tyyppi, määrä, voimassaolo ja kattavuus |

Tärkeää: dokumenttityyppi ja asiakirjan pätevyysjärjestys ovat eri asioita. Pätevyysjärjestys tulee tallentaa erikseen.

---

## 5. Projektikansion rakenne

Luo Kone1:lle projekti esimerkiksi näin:

```text
F:\dev\cipp-contract-db\
  data\
    raw\
      pilot_001\
        pdf\
        csv\
        images\
    extracted\
      pilot_001\
        pages_json\
        tables_json\
        markdown\
        canonical_json\
    normalized\
      pilot_001\
        contracts.jsonl
        contract_sections.jsonl
        obligations.jsonl
        payment_schedule.jsonl
        unit_prices.jsonl
        quality_requirements.jsonl
    reports\
      pilot_001\
        extraction_report.md
        validation_report.md
        pii_report.md
  db\
    migrations\
    seeds\
    queries\
  src\
    extract\
    normalize\
    validate\
    load\
    embed\
    search\
  tests\
    fixtures\
    eval_questions\
```

---

## 6. PostgreSQL-skeemat

Käytä useaa PostgreSQL-schemaa, ei kaikkea `public`-schemaan.

```sql
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS doc;
CREATE SCHEMA IF NOT EXISTS domain;
CREATE SCHEMA IF NOT EXISTS finance;
CREATE SCHEMA IF NOT EXISTS quality;
CREATE SCHEMA IF NOT EXISTS rag;
CREATE SCHEMA IF NOT EXISTS audit;
```

Merkitys:

| Schema | Sisältö |
|---|---|
| `raw` | alkuperäiset tiedostot, raakateksti, sivut, taulukot, ekstraktioajot |
| `core` | projekti, kohde, sopimus, osapuolet, roolit, asiakirjat |
| `doc` | sopimusosiot, lausekkeet, velvoitteet, viittaukset |
| `domain` | CIPP-domain: urakkarajat, viemärilinjat, menetelmät, vastuut, tarkastukset |
| `finance` | urakkahinta, maksuerät, vakuudet, vakuutukset, yksikköhinnat |
| `quality` | laatukriteerit, tarkastukset, luovutusmateriaali, poikkeamat |
| `rag` | chunkit, embeddingit, hakufunktiot, eval-kysymykset |
| `audit` | validointivirheet, PII-havainnot, import-lokit |

---

## 7. PostgreSQL:n tekninen käynnistys

### 7.1 Luo tietokanta

```sql
CREATE DATABASE cipp_contracts;
```

Yhdistä tietokantaan ja aja:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS vector;
```

`pgcrypto` antaa `gen_random_uuid()`-funktion. `pg_trgm` auttaa sumeassa tekstihaussa. `vector` tarvitaan pgvector-embeddingeille. `unaccent` auttaa hakujen normalisoinnissa.

---

## 8. Taulujen ydinsuunnittelu

### 8.1 Raw layer

Tämä kerros säilyttää alkuperäin. Raakakerrosta ei ylikirjoiteta.

```sql
CREATE TABLE raw.source_files (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code text NOT NULL,
    original_filename text NOT NULL,
    stored_path text NOT NULL,
    document_type text NOT NULL,
    file_ext text NOT NULL,
    sha256 text NOT NULL UNIQUE,
    page_count integer,
    byte_size bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    notes text
);

CREATE TABLE raw.extraction_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_id uuid NOT NULL REFERENCES raw.source_files(id),
    extractor_name text NOT NULL,
    extractor_version text,
    extraction_started_at timestamptz NOT NULL DEFAULT now(),
    extraction_finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('created','running','completed','failed')),
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text
);

CREATE TABLE raw.pages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_id uuid NOT NULL REFERENCES raw.source_files(id),
    page_no integer NOT NULL,
    raw_text text,
    text_quality_score numeric(5,2),
    image_path text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_file_id, page_no)
);

CREATE TABLE raw.extracted_tables (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_id uuid NOT NULL REFERENCES raw.source_files(id),
    page_no integer,
    table_no integer,
    table_type text,
    raw_table_json jsonb NOT NULL,
    extraction_quality text,
    notes text
);
```

### 8.2 Core layer

```sql
CREATE TABLE core.projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code text NOT NULL UNIQUE,
    project_name_redacted text NOT NULL,
    project_type text NOT NULL DEFAULT 'cipp_sukitusurakka',
    lifecycle_status text NOT NULL DEFAULT 'imported',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.properties (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES core.projects(id),
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

CREATE TABLE core.parties (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    party_code text NOT NULL UNIQUE,
    party_type text NOT NULL CHECK (party_type IN ('housing_company','contractor','consultant','property_manager','authority','insurer','other')),
    display_name_redacted text NOT NULL,
    original_name_hash text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE core.contacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    party_id uuid REFERENCES core.parties(id),
    role_title text,
    person_name_redacted text,
    person_name_hash text,
    email_hash text,
    phone_hash text,
    visible_to_ai boolean NOT NULL DEFAULT false,
    notes text
);

CREATE TABLE core.contracts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES core.projects(id),
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

CREATE TABLE core.contract_parties (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    party_id uuid NOT NULL REFERENCES core.parties(id),
    role text NOT NULL CHECK (role IN ('client','contractor','designer','supervisor','property_manager','chairperson','insurer','other')),
    valid_from date,
    valid_to date,
    UNIQUE (contract_id, party_id, role)
);

CREATE TABLE core.contract_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    source_file_id uuid REFERENCES raw.source_files(id),
    document_type text NOT NULL,
    document_title_redacted text NOT NULL,
    attachment_no text,
    document_date date,
    revision text,
    page_count integer,
    precedence_rank integer,
    is_contract_document boolean NOT NULL DEFAULT true,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
```

### 8.3 Document and clause layer

```sql
CREATE TABLE doc.sections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_document_id uuid NOT NULL REFERENCES core.contract_documents(id),
    parent_section_id uuid REFERENCES doc.sections(id),
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

CREATE TABLE doc.clauses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id uuid NOT NULL REFERENCES doc.sections(id),
    clause_key text,
    clause_type text NOT NULL,
    title text,
    clause_text text NOT NULL,
    normalized_summary text,
    legal_effect text,
    source_page integer,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE doc.obligations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clause_id uuid REFERENCES doc.clauses(id),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
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

CREATE TABLE doc.cross_references (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_clause_id uuid REFERENCES doc.clauses(id),
    to_document_id uuid REFERENCES core.contract_documents(id),
    to_section_key text,
    reference_text text NOT NULL,
    reference_type text
);
```

### 8.4 Domain layer: CIPP-sukitusurakka

```sql
CREATE TABLE domain.scope_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    item_code text NOT NULL,
    system_type text NOT NULL CHECK (system_type IN ('JV','SV','KPA','floor_drain','wc','other')),
    item_name text NOT NULL,
    included_in_contract boolean NOT NULL,
    is_option boolean NOT NULL DEFAULT false,
    is_extra_work boolean NOT NULL DEFAULT false,
    source_clause_id uuid REFERENCES doc.clauses(id),
    notes text,
    UNIQUE (contract_id, item_code)
);

CREATE TABLE domain.contract_boundaries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    system_type text NOT NULL CHECK (system_type IN ('JV','SV','KPA','other')),
    upstream_boundary text,
    downstream_boundary text,
    inspected boolean,
    source_clause_id uuid REFERENCES doc.clauses(id),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE domain.technical_requirements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    requirement_code text NOT NULL,
    requirement_type text NOT NULL,
    requirement_text text NOT NULL,
    numeric_limit numeric(12,4),
    unit text,
    standard_ref text,
    applies_to text,
    source_clause_id uuid REFERENCES doc.clauses(id),
    UNIQUE (contract_id, requirement_code)
);

CREATE TABLE domain.responsibility_matrix (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    responsibility_key text NOT NULL,
    responsibility_area text NOT NULL,
    responsible_role text NOT NULL,
    details text,
    source_clause_id uuid REFERENCES doc.clauses(id),
    UNIQUE (contract_id, responsibility_key)
);

CREATE TABLE domain.schedule_milestones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    milestone_key text NOT NULL,
    milestone_name text NOT NULL,
    planned_date date,
    planned_start date,
    planned_finish date,
    qualifier text,
    source_clause_id uuid REFERENCES doc.clauses(id),
    UNIQUE (contract_id, milestone_key)
);

CREATE TABLE domain.inspections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    inspection_type text NOT NULL,
    required_by_role text,
    performed_by_role text,
    inspection_text text NOT NULL,
    evidence_required text,
    source_clause_id uuid REFERENCES doc.clauses(id),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
```

### 8.5 Finance layer

```sql
CREATE TABLE finance.contract_prices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    price_type text NOT NULL CHECK (price_type IN ('fixed_contract_price','option','extra_work','unit_price_total')),
    amount_net numeric(14,2),
    vat_rate numeric(5,2),
    vat_amount numeric(14,2),
    amount_gross numeric(14,2),
    currency_code char(3) NOT NULL DEFAULT 'EUR',
    price_text text,
    source_clause_id uuid REFERENCES doc.clauses(id),
    CHECK (amount_net IS NULL OR amount_net >= 0),
    CHECK (amount_gross IS NULL OR amount_gross >= 0)
);

CREATE TABLE finance.payment_schedule_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    item_no integer NOT NULL,
    amount_net numeric(14,2) NOT NULL,
    vat_rate numeric(5,2),
    amount_gross numeric(14,2),
    payment_condition text NOT NULL,
    source_document_id uuid REFERENCES core.contract_documents(id),
    source_table_id uuid REFERENCES raw.extracted_tables(id),
    UNIQUE (contract_id, item_no)
);

CREATE TABLE finance.unit_prices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    unit_price_code text NOT NULL,
    item_name text NOT NULL,
    unit text,
    amount_gross numeric(14,2),
    amount_net numeric(14,2),
    vat_rate numeric(5,2),
    condition_text text,
    source_clause_id uuid REFERENCES doc.clauses(id),
    UNIQUE (contract_id, unit_price_code)
);

CREATE TABLE finance.securities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    security_type text NOT NULL CHECK (security_type IN ('construction_period','warranty_period','other')),
    amount numeric(14,2),
    amount_percent numeric(5,2),
    basis text,
    validity_text text,
    issuer_role text,
    beneficiary_role text,
    source_clause_id uuid REFERENCES doc.clauses(id)
);

CREATE TABLE finance.insurances (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    insurance_type text NOT NULL,
    required_by_role text,
    coverage_amount numeric(14,2),
    coverage_text text,
    source_clause_id uuid REFERENCES doc.clauses(id)
);

CREATE TABLE finance.penalties (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    penalty_type text NOT NULL,
    percent_per_workday numeric(8,4),
    max_workdays integer,
    basis text,
    calculation_text text,
    source_clause_id uuid REFERENCES doc.clauses(id)
);
```

### 8.6 Quality layer

```sql
CREATE TABLE quality.requirements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    requirement_key text NOT NULL,
    requirement_category text NOT NULL,
    requirement_text text NOT NULL,
    acceptance_criteria text,
    evidence_required text,
    source_clause_id uuid REFERENCES doc.clauses(id),
    UNIQUE (contract_id, requirement_key)
);

CREATE TABLE quality.deliverables (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    deliverable_key text NOT NULL,
    deliverable_name text NOT NULL,
    required_at text,
    required_by_role text,
    source_clause_id uuid REFERENCES doc.clauses(id),
    UNIQUE (contract_id, deliverable_key)
);

CREATE TABLE quality.nonconformities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    finding_text text NOT NULL,
    severity text CHECK (severity IN ('low','medium','high','critical')),
    status text NOT NULL DEFAULT 'open',
    source_document_id uuid REFERENCES core.contract_documents(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

### 8.7 RAG layer

```sql
CREATE TABLE rag.embedding_models (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name text NOT NULL UNIQUE,
    provider text NOT NULL,
    dimension integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rag.chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES core.contracts(id),
    contract_document_id uuid REFERENCES core.contract_documents(id),
    section_id uuid REFERENCES doc.sections(id),
    clause_id uuid REFERENCES doc.clauses(id),
    chunk_order integer NOT NULL,
    chunk_type text NOT NULL,
    content_redacted text NOT NULL,
    content_hash text NOT NULL,
    token_count integer,
    page_start integer,
    page_end integer,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('finnish', coalesce(content_redacted,''))) STORED,
    UNIQUE (contract_id, content_hash)
);

-- Jos käytät 1536-dimension embedding-mallia:
CREATE TABLE rag.chunk_embeddings_1536 (
    chunk_id uuid PRIMARY KEY REFERENCES rag.chunks(id) ON DELETE CASCADE,
    embedding_model_id uuid NOT NULL REFERENCES rag.embedding_models(id),
    embedding vector(1536) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Jos käytät muuta embedding-mallia, luo vastaava taulu oikealla dimensiolla, esimerkiksi `rag.chunk_embeddings_1024` tai `rag.chunk_embeddings_768`.

### 8.8 Audit layer

```sql
CREATE TABLE audit.validation_issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid REFERENCES core.projects(id),
    contract_id uuid REFERENCES core.contracts(id),
    issue_type text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('info','warning','error','critical')),
    message text NOT NULL,
    source_table text,
    source_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE TABLE audit.pii_findings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_id uuid REFERENCES raw.source_files(id),
    location_text text,
    pii_type text NOT NULL,
    raw_value_hash text NOT NULL,
    replacement_value text,
    visibility_decision text NOT NULL CHECK (visibility_decision IN ('redact','hash','allow_internal','manual_review')),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

---

## 9. Indeksit

```sql
CREATE INDEX idx_source_files_project ON raw.source_files(project_code);
CREATE INDEX idx_contract_documents_contract ON core.contract_documents(contract_id);
CREATE INDEX idx_sections_document_order ON doc.sections(contract_document_id, section_order);
CREATE INDEX idx_clauses_type ON doc.clauses(clause_type);
CREATE INDEX idx_obligations_contract_role ON doc.obligations(contract_id, obligated_role);
CREATE INDEX idx_scope_contract_system ON domain.scope_items(contract_id, system_type);
CREATE INDEX idx_payment_contract_item ON finance.payment_schedule_items(contract_id, item_no);
CREATE INDEX idx_chunks_contract_type ON rag.chunks(contract_id, chunk_type);
CREATE INDEX idx_chunks_search_vector ON rag.chunks USING GIN(search_vector);
CREATE INDEX idx_chunks_metadata ON rag.chunks USING GIN(metadata);

-- HNSW-indeksi semantic searchiin. Käytä vasta kun dataa on ladattu.
CREATE INDEX idx_chunk_embeddings_1536_hnsw
ON rag.chunk_embeddings_1536
USING hnsw (embedding vector_cosine_ops);
```

Periaate:

- B-tree indeksi: id:t, foreign keyt, päivämäärät, dokumenttityypit.
- GIN indeksi: full-text search, JSONB metadata.
- HNSW: semanttinen embedding-haku.
- pg_trgm: käytä nimien, otsikoiden ja tiedostonimien sumeaan hakuun tarvittaessa.

---

## 10. Canonical JSON -template

Ennen PostgreSQL-latausta jokaisesta urakkapaketista tehdään canonical JSON. Tämä on tärkein välivaihe.

```json
{
  "project_code": "pilot_001",
  "project_type": "cipp_sukitusurakka",
  "property": {
    "property_code": "property_001",
    "city_redacted": "Kaupunki1",
    "building_year": 1968,
    "building_count": 2,
    "stairwell_count": 5,
    "apartment_count": 49,
    "floor_area_m2": 3139
  },
  "contract": {
    "contract_code": "contract_001",
    "contract_type": "construction_contract",
    "contract_date": "YYYY-MM-DD",
    "revision": "REVx",
    "subject": "Viemärijärjestelmien CIPP-sukitusurakka",
    "standard_terms": "YSE 1998",
    "currency_code": "EUR"
  },
  "parties": [
    {"party_code": "client_001", "role": "client", "display_name_redacted": "Tilaaja1"},
    {"party_code": "contractor_001", "role": "contractor", "display_name_redacted": "Urakoitsija1"},
    {"party_code": "supervisor_001", "role": "supervisor", "display_name_redacted": "Valvoja1"},
    {"party_code": "designer_001", "role": "designer", "display_name_redacted": "Suunnittelija1"}
  ],
  "documents": [
    {"document_type": "main_contract", "attachment_no": null, "precedence_rank": 2},
    {"document_type": "rfq", "attachment_no": "LIITE3", "precedence_rank": 3},
    {"document_type": "contractor_offer", "attachment_no": "LIITE5", "precedence_rank": 4},
    {"document_type": "negotiation_minutes", "attachment_no": "LIITE1", "precedence_rank": 5},
    {"document_type": "unit_prices", "attachment_no": "LIITE6", "precedence_rank": 6},
    {"document_type": "payment_schedule", "attachment_no": "LIITE7", "precedence_rank": 7},
    {"document_type": "drawing_index", "attachment_no": "LIITE8", "precedence_rank": 8},
    {"document_type": "contract_terms", "attachment_no": "LIITE2", "precedence_rank": 9},
    {"document_type": "rfq_clarification", "attachment_no": "LIITE4", "precedence_rank": 10},
    {"document_type": "quality_manual", "attachment_no": "LIITE9", "precedence_rank": 11}
  ],
  "scope_items": [],
  "boundaries": [],
  "technical_requirements": [],
  "responsibilities": [],
  "prices": [],
  "payment_schedule": [],
  "unit_prices": [],
  "securities": [],
  "insurances": [],
  "penalties": [],
  "quality_requirements": [],
  "deliverables": [],
  "clauses": [],
  "obligations": []
}
```

---

## 11. Ekstraktioprosessi

### 11.1 Vaihe 1: tiedostoinventaario

Tee jokaisesta tiedostosta inventaario:

```text
- alkuperäinen tiedostonimi
- dokumenttityyppi
- sivumäärä
- tiedostokoko
- sha256
- onko tekstikerros olemassa
- tarvitseeko OCR:aa
- onko taulukoita
- onko kuvia tai piirustusluetteloita
```

Tulos tallennetaan `raw.source_files`-tauluun.

### 11.2 Vaihe 2: PDF -> sivukohtainen teksti

Jokainen PDF puretaan sivuittain.

Tallenna:

```text
source_file_id
page_no
raw_text
text_quality_score
image_path
```

Jos tekstista puuttuu paljon merkkejä tai rivijako on rikki, renderöi sivu kuvaksi ja arvioi tarvitaanko OCR. OCR:ää ei pidä ajaa sokeasti kaikkiin sivuihin, koska se voi tuoda virheitä hyvään tekstikerrokseen.

### 11.3 Vaihe 3: taulukot erikseen

Tunnista ainakin nämä taulukkotyypit:

```text
payment_schedule
unit_prices
document_precedence
drawing_index
security_details
```

Taulukkoa ei saa tallentaa vain tekstikappaleeksi, jos siinä on rahasummia, rivejä tai maksukelpoisuusehtoja.

### 11.4 Vaihe 4: canonical JSON

Kirjoita normalisointiskripti, joka muuttaa raakatekstin canonical JSONiksi.

Suositeltu tiedosto:

```text
src\normalize\build_canonical_contract.py
```

Ajo:

```powershell
python .\src\normalize\build_canonical_contract.py --project pilot_001 --input .\data\extracted\pilot_001 --output .\data\extracted\pilot_001\canonical_json\contract.json
```

### 11.5 Vaihe 5: validointi ennen latausta

Canonical JSON validoidaan ennen PostgreSQL-latausta.

```powershell
python .\src\validate\validate_canonical_contract.py --input .\data\extracted\pilot_001\canonical_json\contract.json --report .\data\reports\pilot_001\validation_report.md
```

### 11.6 Vaihe 6: lataus PostgreSQL:aan

```powershell
python .\src\load\load_contract_package.py --input .\data\extracted\pilot_001\canonical_json\contract.json --db postgresql://USER:PASSWORD@localhost:5432/cipp_contracts
```

### 11.7 Vaihe 7: chunkkaus ja embeddingit

```powershell
python .\src\embed\build_chunks.py --project pilot_001
python .\src\embed\embed_chunks.py --project pilot_001 --model MODEL_NAME
```

---

## 12. Chunkkaussäännöt

Sopimusdataa ei chunkata mekaanisesti merkkimäärällä. Chunkkaus tehdään sopimusrakenteen perusteella.

### 12.1 Chunkkityypit

| Chunk type | Sisältö |
|---|---|
| `contract_fact_summary` | sopimuksen ydinfaktat |
| `contract_clause` | yksi sopimuskohta tai alakohta |
| `technical_requirement` | yksittäinen tekninen vaatimus |
| `payment_condition` | yksi maksuerärivi ehtoineen |
| `unit_price` | yksi yksikköhintarivi |
| `responsibility` | yksi vastuunjakokohta |
| `quality_requirement` | yksi laatukriteeri tai tarkastusvaatimus |
| `deliverable` | yksi luovutusasiakirjavaatimus |
| `document_precedence` | asiakirjaluettelon yksi rivi tai kooste |

### 12.2 Chunkin maksimikoko

Suositus:

```text
sopimuslauseke: 300-900 tokenia
tekninen vaatimus: 100-500 tokenia
maksuerärivi: yksi rivi per chunk
vastuunjakorivi: yksi vastuu per chunk
laatukäsikirjan pitkä osio: otsikkokohtainen chunk, tarvittaessa alakohtiin
```

Älä koskaan halkaise näitä:

```text
- maksuerän summa + maksukelpoisuusehto
- vakuuden määrä + voimassaoloehto
- viivästyssakkoprosentti + enimmäispäivien määrä
- urakkarajan ylä- ja alajuoksun määrittely
- laatukriteerin numeric limit, esimerkiksi 2 mm tai 4 mm
- yksikköhinnan tuote + hinta + ehto
```

### 12.3 Chunkin metadata

Jokaiseen chunkiin lisätään:

```json
{
  "project_code": "pilot_001",
  "contract_code": "contract_001",
  "document_type": "contract_terms",
  "section_key": "technical_requirements",
  "role_scope": ["contractor", "supervisor"],
  "system_type": ["JV", "SV"],
  "money_related": false,
  "date_related": false,
  "quality_related": true,
  "source_page_start": 1,
  "source_page_end": 1,
  "pii_redacted": true
}
```

---

## 13. PII- ja anonymisointisäännöt

Tässä projektissa PII erotetaan tietokannan sisällä.

### 13.1 AI:lle sallittu

```text
Tilaaja1
Urakoitsija1
Valvoja1
Suunnittelija1
Isännöitsijä1
Kohde1
Kaupunki1
Kiinteistö1
Henkilö1
Henkilö2
```

### 13.2 AI:lle ei sallita oletuksena

```text
oikea henkilönimi
puhelinnumero
sähköposti
kotiosoite
organisaation oikea nimi
henkilötunnus
syntymapäivä
allekirjoituskuva
pankkitilin numero
```

### 13.3 Tietokantaperiaate

- `core.parties.display_name_redacted` saa näkyä AI:lle.
- `core.parties.original_name_hash` ei paljasta nimeä.
- `core.contacts.*_hash` ei paljasta yhteystietoa.
- Raakadata saa sisältää alkuperäisen tiedon vain hallitussa `raw`-kerroksessa.
- RAG-chunkit käyttävät aina redaktoitua tekstiä.

---

## 14. Domain-ekstraktion kenttämälli

### 14.1 Pääurakan faktat

Poimi pääsopimuksesta ja liitteistä:

```text
contract_date
revision
project_type
subject
building_target
system_type
standard_terms
currency
contract_price_net
vat_rate
vat_amount
contract_price_gross
start_right_date
latest_start_date
completion_date
completion_qualifier
delay_penalty_percent_per_workday
delay_penalty_max_workdays
warranty_months
construction_security_amount
warranty_security_amount
```

### 14.2 CIPP-tekniset faktat

Poimi ainakin:

```text
JV pystyviemärien määrä
SV-linjat
pohjaviemärit
pihaviemärit
KPA-linjat
lattiakaivot
WC-istuimet
puhdistusluukut
ohipumppaus
limisukitus
haarayhdevaatimukset
vesianalyysi
kuvausvaatimukset
KVV-tarkastus
luovutusvideot
punakynäkuvat
loppudokumentaatio
```

### 14.3 Vastuut

Tee jokaisesta vastuujaosta yksi rivi:

```text
vastuualue
vastuurooli
tarkennus
lähdedokumentti
lähdesivu
```

Esimerkkejä vastuualueista:

```text
telineet ja rakennelmat
kulkutiet
alueen osoittaminen
vartiointi
suojaus
jätehuolto
sosiaalitilat
vesi ja sähkö
avaimet
alihankkijoiden hyväksyminen
tiedotus
työmaapäiväkirja
KVV-tarkastus
loppudokumentaatio
```

---

## 15. Validointiportit

### 15.1 Tiedostopaketti

Tarkista:

```text
- löytyykö pääsopimus
- löytyvätkö kaikki liitteet
- onko jokaisella tiedostolla sha256
- onko sivumäärä tallennettu
- onko dokumenttityyppi tunnistettu
- onko liitenumero tunnistettu
- onko pätevyysjärjestys tunnistettu
```

### 15.2 Raha ja ALV

Tarkista:

```text
amount_net + vat_amount = amount_gross
amount_net * vat_rate = vat_amount
maksuerien summa = urakkahinta
maksuerien ALV0 summa = urakkahinta ALV0
maksuerien ALV24 summa = urakkahinta ALV24
vakuuden prosentti vastaa sopimusehtoa tai poikkeama kirjataan
viivästyssakon päiväkohtainen määrä on laskettavissa
```

Jos lasku ei täsmää, tee rivi `audit.validation_issues`-tauluun.

### 15.3 Päivämäärät

Tarkista:

```text
contract_date <= start_right_date
start_right_date <= latest_start_date
latest_start_date <= completion_date
warranty_end_date = reception_date + warranty_months, jos vastaanottopäivä on tiedossa
security_validity_end_date >= required_validity_end_date, jos voimassaolo on tiedossa
```

### 15.4 Sopimuspaketin sisäinen ristiriita

Etsi ristiriitoja:

```text
- tarjoushinta vs lopullinen urakkahinta
- tarjouspyynnön urakkaraja vs sopimuksen urakkaraja
- liitteen ehto vs pääsopimuksen ehto
- maksuehto vs maksuerätaulukko
- tarjouspyynnön optio vs sopimukseen sisältyvä laajuus
```

Ristiriita ei tarkoita automaattisesti virhettä. Se voi johtua pätevyysjärjestyksestä tai neuvottelussa sovitusta muutoksesta.

### 15.5 PII

Tarkista ennen RAG-chunkkien luontia:

```text
- ei sähköposteja rag.chunks.content_redacted -kentässä
- ei puhelinnumeroita rag.chunks.content_redacted -kentässä
- ei oikeita henkilönimiä rag.chunks.content_redacted -kentässä
- ei oikeita organisaationimiä rag.chunks.content_redacted -kentässä
```

---

## 16. Hakukerros

### 16.1 Full-text search

Peruskysely:

```sql
SELECT c.id, c.content_redacted, ts_rank(c.search_vector, plainto_tsquery('finnish', :query)) AS rank
FROM rag.chunks c
WHERE c.search_vector @@ plainto_tsquery('finnish', :query)
ORDER BY rank DESC
LIMIT 20;
```

Jos suomalaiset domain-termit, lyhenteet tai taivutusmuodot toimivat huonosti `finnish`-konfiguraatiolla, tee rinnalle `simple`-konfiguraatio. CIPP-domainissa lyhenteet kuten JV(jätevesi), SV(sadevesi), KPA(käsienpesuallas), KVV((kiinteistön vesi- ja viemärilaitteistot) ja YSE(yleiset sopimusehdot) voivat toimia paremmin ilman aggressiivista kielistemminkiä.

### 16.2 Vector search

```sql
SELECT c.id,
       c.content_redacted,
       e.embedding <=> :query_embedding AS distance
FROM rag.chunk_embeddings_1536 e
JOIN rag.chunks c ON c.id = e.chunk_id
WHERE c.contract_id = :contract_id
ORDER BY e.embedding <=> :query_embedding
LIMIT 20;
```

### 16.3 Hybridihaku

Tuotantokäytössä käytä yhdistelmää:

```text
metadatafiltteri + full-text search + vector search + rerank
```

Esimerkki:

```text
query: "milloin maksuerä on maksukelpoinen"
filters:
  document_type = payment_schedule OR section_key = payment_terms
  money_related = true
```

---

## 17. Testikysymykset ensimmäiseen evaluointiin

Tee `tests/eval_questions/pilot_001.jsonl`.

```jsonl
{"id":"q001","question":"Mikä on urakan kohde?","expected_source":"main_contract"}
{"id":"q002","question":"Mikä on JV-linjojen urakkaraja yla- ja alajuoksulla?","expected_source":"main_contract"}
{"id":"q003","question":"Kuka vastaa telineista ja kulkuteista?","expected_source":"main_contract"}
{"id":"q004","question":"Mitä asiakirjoja sopimukseen kuuluu ja missä järjestyksessä?","expected_source":"main_contract"}
{"id":"q005","question":"Mitkä asiat ovat lisatyota viemareiden huuhtelussa tai rassauksessa?","expected_source":"contract_terms"}
{"id":"q006","question":"Mitä ISO-standardia sukitustyossa noudatetaan?","expected_source":"contract_terms"}
{"id":"q007","question":"Miten maksuerät tulevat maksukelpoisiksi?","expected_source":"payment_schedule"}
{"id":"q008","question":"Mitä yksikkohintoja lisatoille on annettu?","expected_source":"unit_prices"}
{"id":"q009","question":"Mitä loppudokumentaatioon tulee sisältyä?","expected_source":"quality_manual"}
{"id":"q010","question":"Mitä vakuuksia urakoitsijalta vaaditaan?","expected_source":"main_contract"}
```

Hyväksyttävä vastaus vaatii:

```text
- vastaus löytyy oikeasta dokumenttityypistä
- vastaus sisältää lähdeviitteen
- vastaus ei sisällä PII:tä
- vastaus ei sekoita tarjousta ja lopullista sopimusta
- vastaus kertoo, jos aineistossa on ristiriita tai tarkennus
```

---

## 18. Latausjärjestys PostgreSQL:ään

Aja lataus aina tässä järjestyksessä:

```text
1. raw.source_files
2. raw.pages
3. raw.extracted_tables
4. core.projects
5. core.properties
6. core.parties
7. core.contacts
8. core.contracts
9. core.contract_parties
10. core.contract_documents
11. doc.sections
12. doc.clauses
13. doc.obligations
14. doc.cross_references
15. domain.scope_items
16. domain.contract_boundaries
17. domain.technical_requirements
18. domain.responsibility_matrix
19. domain.schedule_milestones
20. domain.inspections
21. finance.contract_prices
22. finance.payment_schedule_items
23. finance.unit_prices
24. finance.securities
25. finance.insurances
26. finance.penalties
27. quality.requirements
28. quality.deliverables
29. rag.chunks
30. rag.chunk_embeddings_1536
31. audit.validation_issues
32. audit.pii_findings
```

---

## 19. Esimerkkikyselyt tietokannasta

### 19.1 Listaa sopimusasiakirjat pätevyysjärjestyksessä

```sql
SELECT document_type, attachment_no, document_title_redacted, precedence_rank, document_date
FROM core.contract_documents
WHERE contract_id = :contract_id
ORDER BY precedence_rank NULLS LAST;
```

### 19.2 Laske maksuerien summa

```sql
SELECT
    SUM(amount_net) AS total_net,
    SUM(amount_gross) AS total_gross
FROM finance.payment_schedule_items
WHERE contract_id = :contract_id;
```

### 19.3 Hae kaikki urakoitsijan velvoitteet

```sql
SELECT obligation_type, obligation_text, trigger_condition, evidence_required
FROM doc.obligations
WHERE contract_id = :contract_id
  AND obligated_role = 'contractor'
ORDER BY obligation_type;
```

### 19.4 Hae tekniset laatukriteerit

```sql
SELECT requirement_code, requirement_type, requirement_text, numeric_limit, unit, standard_ref
FROM domain.technical_requirements
WHERE contract_id = :contract_id
ORDER BY requirement_code;
```

### 19.5 Hae kaikki maksukelpoisuusehdot

```sql
SELECT item_no, amount_net, amount_gross, payment_condition
FROM finance.payment_schedule_items
WHERE contract_id = :contract_id
ORDER BY item_no;
```

---

## 20. Sopimusgeneroinnin pohja

Kun tietokantaan on ladattu useampi urakkapaketti, uusi sopimusluonnos generoidaan näin:

```text
1. Käyttäjä syöttää uuden kohteen perustiedot.
2. Järjestelmä hakee lähimmät vertailu-urakat.
3. Järjestelmä hakee pääsopimuksen rakenteen.
4. Järjestelmä hakee CIPP-domainin pakolliset kohdat.
5. Järjestelmä hakee maksuerätaulukon mallin.
6. Järjestelmä hakee sopimusehdot ja laatukriteerit.
7. Järjestelmä muodostaa canonical contract draft JSONin.
8. Järjestelmä validoi luonnoksen.
9. Järjestelmä tulostaa sopimusluonnoksen ja liitepuutelistauksen.
```

Sopimusluonnos ei saa syntyä suoraan vapaasta LLM-vastauksesta. Sen pitää syntyä canonical JSONista.

---

## 21. Sopimusluonnoksen output-malli

```json
{
  "draft_id": "draft_001",
  "based_on_projects": ["pilot_001"],
  "contract": {
    "subject": "Viemärijärjestelmien CIPP-sukitusurakka",
    "standard_terms": "YSE 1998",
    "currency_code": "EUR"
  },
  "sections": [
    {"section_key":"project", "title":"Hanke", "body":"..."},
    {"section_key":"parties", "title":"Sopijapuolet", "body":"..."},
    {"section_key":"scope", "title":"Urakan laajuus", "body":"..."},
    {"section_key":"responsibilities", "title":"Vastuut", "body":"..."},
    {"section_key":"contract_documents", "title":"Sopimusasiakirjat", "body":"..."},
    {"section_key":"schedule", "title":"Urakka-aika", "body":"..."},
    {"section_key":"penalties", "title":"Viivästyssakko", "body":"..."},
    {"section_key":"warranty", "title":"Takuu", "body":"..."},
    {"section_key":"securities", "title":"Vakuudet", "body":"..."},
    {"section_key":"insurances", "title":"Vakuutukset", "body":"..."},
    {"section_key":"price", "title":"Urakkahinta", "body":"..."},
    {"section_key":"payment", "title":"Urakkahinnan maksaminen", "body":"..."},
    {"section_key":"disputes", "title":"Riitaisuuksien ratkaiseminen", "body":"..."}
  ],
  "missing_inputs": [],
  "validation_issues": []
}
```

---

## 22. Ensimmäinen toteutusjärjestys

### Paiva 1: tietokanta ja migraatiot

1. Luo projekti- ja kansiorakenne.
2. Luo PostgreSQL-tietokanta.
3. Aja extensionit.
4. Aja skeemat.
5. Aja taulut ja indeksit.
6. Tee `db/migrations/001_init.sql`.

### Paiva 2: raw-import

1. Laske jokaiselle tiedostolle sha256.
2. Tunnista dokumenttityyppi.
3. Tallenna `raw.source_files`.
4. Pura PDF:t sivutekstiksi.
5. Tallenna `raw.pages`.
6. Tallenna maksuerätaulukko ja yksikköhinnat `raw.extracted_tables`-tauluun.

### Paiva 3: canonical JSON

1. Tee manuaalisesti tarkistettu `contract.json`.
2. Pura osapuolet anonymisoituina.
3. Pura sopimusasiakirjat ja pätevyysjärjestys.
4. Pura laajuus, urakkarajat, aikataulu ja rahat.
5. Pura vastuut, vakuudet, vakuutukset ja laatuvaatimukset.

### Paiva 4: validointi

1. Tarkista ALV ja summat.
2. Tarkista maksuerien summat.
3. Tarkista vakuudet suhteessa ALV0-hintaan.
4. Tarkista päivämääräjärjestys.
5. Tarkista PII.
6. Tuota `validation_report.md`.

### Paiva 5: haku ja RAG

1. Luo chunkit.
2. Luo full-text search.
3. Luo embeddingit.
4. Aja eval-kysymykset.
5. Korjaa chunkkaus ja metadata, jos vastaukset hakevat väärästä dokumentista.

---

## 23. Minimal viable database ennen laajennusta

Jos haluat nopeimman toimivan version, tee ensin vain nämä taulut:

```text
raw.source_files
raw.pages
core.projects
core.contracts
core.contract_documents
core.parties
core.contract_parties
doc.sections
doc.clauses
finance.contract_prices
finance.payment_schedule_items
finance.unit_prices
finance.securities
domain.scope_items
domain.contract_boundaries
domain.responsibility_matrix
quality.requirements
quality.deliverables
rag.chunks
rag.chunk_embeddings_1536
audit.validation_issues
audit.pii_findings
```

Vasta kun tämä toimii, lisää tarkemmat inspection-, nonconformity-, change_order- ja deliverable-workflowt.

---

## 24. Yleiset virheet, joita vältä

1. Älä tee 40 sarakkeen `contracts`-taulua.
2. Älä embeddingoi koko PDF:aa yhtena chunkkina.
3. Älä sekoita tarjousta ja lopullista sopimusta ilman pätevyysjärjestysta.
4. Älä tallenna oikeita henkilönimiä RAG-chunkeihin.
5. Älä hukkaa sivuviitteitä.
6. Älä käsittele maksuerätaulukkoa pelkkänä tekstina.
7. Älä käsittele laatukäsikirjaa vain liitteenä. Siina on prosessivaatimuksia.
8. Älä anna LLM:n kirjoittaa sopimusta ilman canonical JSON -välivaihetta.
9. Älä luota automaattiseen PDF-purkuun ilman validointiraporttia.
10. Älä tee tietokannasta pelkkää dokumenttihakua. Domain-faktat pitää normalisoida.

---

## 25. Lopputavoite

Kun ensimmäinen pilottipaketti on ajettu sisään oikein, seuraava urakkapaketti ei ole uusi projekti vaan uusi datapaketti samaan putkeen.

Tavoiteltu lopputulos:

```text
1. Uusi CIPP-urakkapaketti sisään.
2. Järjestelmä tunnistaa dokumentit.
3. Järjestelmä purkaa faktat ja lausekkeet.
4. Järjestelmä validoi rahat, päivämäärät, liitteet ja vastuut.
5. Järjestelmä anonymisoi AI-kerroksen.
6. Järjestelmä rakentaa hybridihakukelpoiset chunkit.
7. Järjestelmä osaa vertailla urakoita.
8. Järjestelmä osaa tuottaa uuden sopimusluonnoksen canonical JSONin kautta.
```

Tämä on se pohja, jonka päälle CIPP-urakkasopimus-SaaS kannattaa rakentaa.
