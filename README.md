# CIPP Contract Database

PostgreSQL + pgvector -pohjainen tietokantapohja CIPP-sukitusurakoiden sopimuspakettien inventointiin, normalisointiin, validointiin, hakuun ja myöhempään sopimusluonnosten generointiin.

## Riippuvuudet

Järjestelmätason riippuvuudet:

- Python 3.10+
- Docker Desktop
- Docker Compose
- LibreOffice, suositeltu polku Windowsissa: `C:\Program Files\LibreOffice\program\soffice.exe`
- Autodesk DWG TrueView 2027, suositeltu Core Console -polku Windowsissa: `C:\Program Files\Autodesk\DWG TrueView 2027 - English\accoreconsole.exe`
- paikallinen visuaalisen OCR:n pipeline `kuvien-parsinta`, suositeltu polku: `F:\-DEV-\95.Kuvien-parsinta-SOTA\.venv\Scripts\kuvien-parsinta.exe`

Docker-palvelut:

- PostgreSQL 16
- pgvector

Python-ajonaikaiset riippuvuudet:

- `pypdf`
- `psycopg[binary]`

Kehitysriippuvuudet:

- `pytest`
- `ruff`

LibreOffice tarvitaan vanhojen Office-tiedostojen muuntamiseen, erityisesti `.doc -> .docx` ja `.xls -> .xlsx`. Ilman LibreOfficea modernit `.docx/.xlsx`-tiedostot voidaan silti purkaa, mutta vanhoista binäärisistä Office-tiedostoista saadaan vain rajallinen best-effort-teksti tai jatkokäsittelymerkintä.

Autodesk DWG TrueView tarvitaan DWG-piirustusten erämuuntoon PDF-muotoon ennen jatkokäsittelyä. Visuaalinen OCR käyttää erillisen OCR-repositorion valmista `kuvien-parsinta`-CLI:tä, joka ajaa kuvien ja skannattujen dokumenttien rakenne-OCR:n ja tallentaa tekstin tämän repon `raw.pages`-tauluun.

## Käynnistys

```powershell
Copy-Item .env.example .env
python -m pip install -r requirements-dev.txt
docker compose up -d
docker compose ps
```

Tietokanta kuuntelee oletuksena osoitteessa:

```text
postgresql://cipp:<POSTGRES_PASSWORD>@localhost:55432/cipp_contracts
```

## Rakenne

```text
db/migrations        PostgreSQL-migraatiot
db/queries           Manuaaliset tarkistus- ja hakukyselyt
src/cipp_contracts   Python-työkalut importtiin, validointiin ja hakuun
data/raw             Alkuperäinen aineisto, ei versionhallintaan
data/extracted       PDF-purku, taulukot ja canonical JSON
data/reports         Validointi-, PII- ja ekstraktioraportit
tests                Testit ja eval-kysymykset
```

## Ensimmäinen tavoite

1. Aja PostgreSQL + pgvector Dockerilla.
2. Lataa `db/migrations/001_init.sql`.
3. Tuo pilottipaketin tiedostot `data/raw/reference_001/`-kansion alle.
4. Muodosta canonical JSON.
5. Validoi canonical JSON ennen tietokantalatausta.
6. Luo chunkit ja full-text-haku ennen embeddingejä.

YSE 1998 käsitellään omana sopimusasiakirjana dokumenttityypillä `yse_1998`, koska se on pääsopimuksen asiakirjaluettelossa pätevyysjärjestyksen ensimmäinen asiakirja.
Rakentamisen lakikokonaisuus käsitellään vielä ylempänä normikerroksena dokumenttityypeillä `law_rakentamislaki_751_2023` ja `law_alueidenkayttolaki_132_1999`. Niiden `precedence_rank` on `0`.

## JV/SV segmenttimalli

Vertailua varten viemärijärjestelmät puretaan segmentteihin tauluun `domain.sewer_segments`.

JV-segmentit yläjuoksulta alajuoksulle:

```text
asuntohajotukset -> pystylinjat -> pohjaviemäri -> tonttilinja
```

SV-segmentit riippuvat kohteesta:

```text
pihamaan sadevesikaivot -> SV-tonttilinja
```

Jos sadevesi kerätään myös katolta, lisätään kalliimpi kattokeräysketju:

```text
katon kerääjäkaivot -> SV-pystylinjat -> SV-pohjaviemäri
```

## Videotarkastus ja takuu

Videotarkastus tarkoittaa valmiin sukitetun JV- tai SV-linjan laadunvarmistusketjua:

1. urakoitsija kuvaa valmiin sukitetun linjan
2. hankkeen valvoja tarkastaa videokuvaukset
3. valvoja antaa omissa asiakirjoissaan kommentit työn laadusta, puutteista, hyväksynnästä, urakoitsijan vastineista ja mahdollisista seurantakohdista
4. videotarkastusasiakirjoja käytetään 2-vuotistakuuajan tarkastuksessa
5. takuutarkastuksessa kerätään tieto viemärien käytössä takuuajan aikana esiintyneistä ongelmista
6. takuutarkastuksessa päätetään, tarvitseeko työtä korjata takuuvelvoitteena

Tietomallissa `video_inspection_report` ei ole pelkkä videoaineisto, vaan valvojan laadunvarmistus- ja takuuseuranta-asiakirja. Sen havainnot tulee tulkita ketjuna:

```text
valmis JV/SV-linja -> urakoitsijan kuvaus -> valvojan kommentti -> hyväksyntä / korjaus / takuuajan seuranta -> 2-vuotistakuutarkastus
```

Vertailuraportti syntyy kyselystä [compare_sewer_segments.sql](F:/-DEV-/97.cipp-contract-db/db/queries/compare_sewer_segments.sql), ja viimeisin CSV on [sewer_segments_comparison.csv](F:/-DEV-/97.cipp-contract-db/data/reports/sewer_segments_comparison.csv).

## JV-hinnan nyrkkisääntö

Kun käyttäjä kysyy oman taloyhtiön kerrostalon kokonaisesta JV-sukitusurakasta, oletussääntö on:

- parhailla materiaaleilla kokonaisurakka on yleensä 5000-8000 euroa/asunto
- mitä pienempi asuntomäärä, sitä lähempänä hinta on 8000 euroa/asunto
- asuntojen määrä selittää oletuksena 70 % hinnasta
- pystylinjojen määrä selittää 10 % hinnasta
- pohjaviemärin koko ja pituus selittää 10 % hinnasta
- tonttiviemärin koko ja pituus selittää 10 % hinnasta

Vastausperiaate käyttäjän taloyhtiön hintakysymyksiin:

1. hae kaikki omat vertailukelpoiset referenssiprojektit PostgreSQL:stä
2. pisteytä ne käyttäjän antamiin tietoihin nähden: asunnot 70 %, pystylinjat 10 %, pohjaviemäri 10 %, tonttiviemäri 10 %
3. valitse lähin oma referenssikohde
4. laske hinta-arvio valitun referenssin ja nyrkkisäännön pohjalta
5. tallenna annettu arvio `finance.price_estimates`-tauluun, jos ajo tehdään `--save`-lipulla

Referenssikohde A (`reference_001`) toimii oletusreferenssinä silloin, kun parempaa vertailukelpoista omaa referenssikohdetta ei vielä löydy. Laskuria voi ajaa moduulina:

```powershell
.\.venv\Scripts\python -m cipp_contracts.price.estimate_jv_price --apartments 49
.\.venv\Scripts\python -m cipp_contracts.price.estimate_jv_price --apartments 49 --vertical-stacks 15 --save --customer-label "oma_taloyhtio"
```

## Pilottipaketin raw-vaihe

```powershell
cipp-inventory-source-files --project reference_001 --input data\raw\reference_001\pdf --report data\reports\reference_001\extraction_report.md
cipp-extract-pdf-pages --project reference_001 --output data\extracted\reference_001\pages_json
cipp-extract-office-text --project reference_001 --output data\extracted\reference_001\office_text
cipp-extract-remaining-text --project reference_001 --output data\extracted\remaining_text --soffice-path "C:\Program Files\LibreOffice\program\soffice.exe"
cipp-extract-visual-ocr --project reference_001 --output data\extracted\visual_ocr --engine structurev3 --quality standard
cipp-extract-dwg-trueview --project reference_001 --output data\extracted\dwg_trueview --accoreconsole-path "C:\Program Files\Autodesk\DWG TrueView 2027 - English\accoreconsole.exe"
cipp-extract-visual-ocr --project reference_001 --output data\extracted\visual_ocr_dwg_pdf --engine structurev3 --quality standard --pdf-only --notes-contains "Derived PDF converted from DWG"
cipp-report-processing-quality --output data\reports\processing_quality_report.md
cipp-report-reference-facts --output-md data\reports\reference_facts_matrix.md --output-csv data\reports\reference_facts_matrix.csv
cipp-build-markdown --project reference_001 --output data\extracted\reference_001\markdown
cipp-link-contract-documents --project reference_001
cipp-load-markdown-sections --project reference_001 --input data\extracted\reference_001\markdown --ensure-raw-documents --prune-missing-markdown
```

## Hyväksymisportit ennen knowledge graphia

Knowledge graph -kerrosta ei rakenneta ennen kuin kaksi porttia on kunnossa:

1. `cipp-report-processing-quality` varmistaa vakaan tekstikerroksen: lähdetiedostot, `raw.pages`, markdownit, `doc.sections`, `doc.clauses` ja viimeisimmät extractor-statukset.
2. `cipp-report-reference-facts` tuottaa vertailufaktamatriisin ja `kg_readiness_status`-arvon jokaiselle referenssille.

`kg_readiness_status` voi olla `ready`, `needs_review` tai `not_ready`. Se kertoo, voidaanko projektin faktat viedä myöhemmin graafikerrokseen ilman että puuttuvat tiedot, heikko evidence tai tekstikerroksen virheet piiloutuvat.

`needs_review` muuttuu `ready`-tilaksi vasta, kun blokkaavat faktat löytyvät ja niillä on riittävä evidence. Blokkaavia kenttiä ovat erityisesti asuntojen määrä, JV-pystylinjat, JV-laajuus, pohja-/tonttiviemärin rajaus, sopimushinta, maksueräsumma sekä laatu-, videotarkastus-, vastaanotto- ja takuutieto. Ei-blokkaavat puutteet, kuten kerrosala tai liiketilojen määrä, voivat jäädä näkyviin `missing_fields`-kenttään ilman että ne yksin estävät KG-valmiutta.


