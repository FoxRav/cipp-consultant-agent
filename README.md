# CIPP Contract Database

PostgreSQL + pgvector -pohjainen CIPP-tietopohja sopimuspakettien inventointiin, normalisointiin, validointiin, knowledge graph -suhdekerrokseen ja lähdeperustaiseen retrievaliin.

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
- `httpx`

Paikallisen kehitys-API:n riippuvuudet:

- `fastapi`
- `uvicorn`

Frontend-playgroundin riippuvuudet:

- Node.js 20+
- Vite
- React
- TypeScript

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
src/cipp_contracts   Python-työkalut importtiin, validointiin, KG:hen ja hakuun
data/raw             Alkuperäinen aineisto, ei versionhallintaan
data/extracted       PDF-purku, taulukot ja canonical JSON
data/reports         Validointi-, PII- ja ekstraktioraportit
apps/web             Paikallinen React/Vite-playground kyselyiden testaamiseen
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

## Hyväksymisportit ennen GraphRAG-käyttöä

PostgreSQL-native KG voidaan rakentaa rakenteisista tietokantariveistä. GraphRAG-/LLM-vastauskäyttöön sitä ei kuitenkaan oteta ennen kuin kaksi porttia on kunnossa:

1. `cipp-report-processing-quality` varmistaa vakaan tekstikerroksen: lähdetiedostot, `raw.pages`, markdownit, `doc.sections`, `doc.clauses` ja viimeisimmät extractor-statukset.
2. `cipp-report-reference-facts` tuottaa vertailufaktamatriisin ja `kg_readiness_status`-arvon jokaiselle referenssille.

`kg_readiness_status` voi olla `ready`, `needs_review` tai `not_ready`. Se kertoo, voidaanko projektin faktat viedä myöhemmin graafikerrokseen ilman että puuttuvat tiedot, heikko evidence tai tekstikerroksen virheet piiloutuvat.

`needs_review` muuttuu `ready`-tilaksi vasta, kun blokkaavat faktat löytyvät ja niillä on riittävä evidence. Blokkaavia kenttiä ovat erityisesti asuntojen määrä, JV-pystylinjat, JV-laajuus, pohja-/tonttiviemärin rajaus, sopimushinta sekä laatu-, videotarkastus-, vastaanotto- ja takuutieto. Ei-blokkaavat puutteet, kuten kerrosala tai liiketilojen määrä, voivat jäädä näkyviin `missing_fields`-kenttään ilman että ne yksin estävät KG-valmiutta.

Maksueriä käsitellään erikseen, koska maksuerätaulukko voi löytyä eri projekteissa eri asiakirjasta. Discovery-logiikka etsii maksueriä `finance.payment_schedule_items`-riveistä, sopimusasiakirjoista, `doc.sections`- ja `doc.clauses`-teksteistä sekä `raw.pages`-kerroksesta. Jos luotettavat rivit löytyvät, raportti tallentaa ne idempotentisti `finance.payment_schedule_items`-tauluun, laskee `payment_schedule_total`-summan, vertaa sitä sopimushintaan yhden euron pyöristystoleranssilla ja näyttää erotuksen kentissä `payment_schedule_difference` ja `payment_schedule_difference_pct`.

Kaikissa projekteissa maksuerät eivät ole yhtenä maksuerätaulukkona. Erillinen lasku- ja hyväksyntäkansio käsitellään invoice-based payment schedule -mallina: erilliset laskut ja hyväksyntädokumentit voidaan koostaa samaksi `finance.payment_schedule_items`-kerrokseksi, jos eränumero, summa ja evidence saadaan luotettavasti ulos.

`payment_schedule_evidence_status` kertoo maksuerien tilan: `structured_and_matches`, `structured_but_mismatch`, `invoice_documents_structured`, `invoice_documents_found_unstructured`, `found_unstructured` tai `not_found`. `found_unstructured` tarkoittaa, että maksuerätaulukko tai maksuerämaininta löytyy tekstistä, mutta rivejä ei vielä voida poimia luotettavasti. `not_found` tarkoittaa nykyisen discovery-logiikan puutetta eikä todista, ettei aineistossa olisi taulukkoa. PostgreSQL-native KG voidaan rakentaa olemassa olevista rakenteisista riveistä, mutta GraphRAG-/LLM-käyttöön sitä ei pidä käyttää ennen kuin maksuerätaulukot ja niihin liittyvä evidence ovat kunnossa kaikille referensseille tai poikkeama on dokumentoitu.

## PostgreSQL-native knowledge graph

`kg`-kerros mallintaa todistettavia suhteita projektien, sopimusten, asiakirjojen, osapuolten, laajuuksien, viemärisegmenttien, vaatimusten, maksuerien ja vastaanoton välillä. Se käyttää nykyistä PostgreSQL-kantaa eikä lisää Neo4j:tä, GraphDB:tä tai muuta infraa.

RAG ja KG ovat eri asioita: `rag` hakee tekstikatkelmia, kun taas `kg` mallintaa suhteita kuten `project HAS_CONTRACT contract`, `document HAS_SECTION section` ja `payment_item SUPPORTED_BY document`. KG-builder käyttää vain olemassa olevaa rakenteista dataa ja source/evidence-kerrosta. Se ei tee LLM-arvauksia.

```powershell
cipp-build-knowledge-graph --all --dry-run
cipp-build-knowledge-graph --all
cipp-build-knowledge-graph --project-code reference_001 --prune
```

Jokaiselle entitylle tai relaatiolle pyritään tallentamaan evidence `kg.evidence`-tauluun esimerkiksi `source_table/source_id`-, `source_file_id`-, `section_id`- tai `clause_id`-viitteellä. Tätä PostgreSQL-native KG:tä käytetään myöhemmin GraphRAG-/hybrid retrieval -vaiheessa rajaamaan ja perustelemaan hakuja, mutta graafiin ei tallenneta suhteita ilman jäljitettävää alkuperää.

## Legal guidance documents

Repo tukee myös lakiosan alla käsiteltäviä asiantuntijaoppaita, jotka eivät ole lakeja, asetuksia, YSE-ehtoja tai sopimuksia. Tällainen aineisto tuodaan luokalla `source_type=expert_guidance`, `authority_level=non_binding_guidance` ja `binding_status=not_binding_law`.

Tätä aineistoa käytetään taloyhtiön hallituksen, osakkaan ja muun amatööritoimijan prosessiohjaukseen: lähtötiedot, kuntotutkimukset, hankesuunnittelu, päätöspisteet, tarjouspyynnöt, vastaanotto ja takuu. Se ei syrjäytä varsinaista lakia, asetusta, YSE-ehtoa, urakkasopimusta tai tarjouspyyntöä. Jos oppaassa mainitaan laki tai asetus, maininta tallennetaan `legal_cross_reference`-tyyppisenä ja statuksella `mentioned_not_verified`, kunnes varsinainen normilähde linkitetään.

```powershell
cipp-import-legal-guidance-pdf --file data/raw/legal_guidance/<asiantuntijaopas>.pdf --document-code expert_guidance_001 --title "Asiantuntijaopas" --publication-year 2020
```

Importer purkaa sivuviitteet `raw.pages`-kerrokseen, tunnistaa päälukurakenteen ja tallentaa sääntöpohjaiset `legal.guidance_items`-rivit. Raportit ja PDF pysyvät `data/`-kansiossa eivätkä kuulu git-committeihin.

## User-case retrieval packet

Järjestelmä ei ole referenssiprojektien kyselybotti. Käyttäjä kysyy omaa taloyhtiötään tai yleistä CIPP-sukitusurakkaa koskevan kysymyksen. Referenssiprojektit ovat sisäinen, anonymisoitu grounding-aineisto.

`cipp-build-retrieval-packet` rakentaa vastausaineiston, mutta ei vielä muodosta lopullista agenttivastausta eikä kutsu LLM:ää. Se tunnistaa kysymyksestä aiheen deterministisesti, hakee relevantit `kg.entities`- ja `kg.relations`-rivit, liittää `kg.evidence`-todisteet ja hakee tarvittaessa tekstikatkelmat `doc.sections`-, `doc.clauses`- ja `raw.pages`-kerroksista.

JV/SV-, urakkaraja- ja scope-kyselyissä haku painottaa domain-entityjä: `sewer_segment`, `scope_item`, `boundary`, `technical_requirement`, `quality_requirement` ja `responsibility`. Tekstikontekstin fallback-ketju on:

```text
clause -> section -> raw.page -> source_file pages -> entity source -> topic fallback
```

Packet kertoo coverage-tilan kentällä `evidence_coverage_status`: `ok`, `partial`, `weak` tai `no_text_context`. Lisäksi entity-, relation- ja evidence-riveillä on `text_context_status`, esimerkiksi `direct_clause`, `direct_section`, `direct_page`, `source_file_page`, `entity_source_fallback`, `topic_text_fallback` tai `missing`.

```powershell
cipp-build-retrieval-packet --question "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?" --output data/reports/retrieval_packet.json --output-md data/reports/retrieval_packet.md
cipp-build-retrieval-packet --question "Mitä pitää huomioida taloyhtiön JV-pystylinjojen ja pohjaviemärin sukituksessa?" --apartments-count 30 --jv-verticals-count 8 --includes-bottom-drain true --output data/reports/retrieval_packet_jv.json --output-md data/reports/retrieval_packet_jv.md
```

Packetin `answer_scope` on `general_cipp_user_case`. `reference_usage.mode` on `internal_anonymized_grounding`, ja Markdown-raportissa referenssit näkyvät vain `reference_001`-tyyppisinä sisäisinä lähteinä. `--debug-reference-project-code` on vain kehittäjän tarkistukseen, ei normaali käyttäjäkyselyn käyttötapa.

## Retrieval smoke matrix

`cipp-report-retrieval-smoke-matrix` on hyväksymisportti ennen mahdollista `v0.5.0`-releaseä. Se ajaa 10 vakioitua CIPP-aihetta nykyisen retrieval-packet-builderin läpi: maksuerät, JV, SV, urakkarajat, videotarkastus, vastaanotto, takuu, vakuudet/vakuutukset, lisätyöt/yksikköhinnat sekä puutteet/reklamaatiot.

```powershell
cipp-report-retrieval-smoke-matrix --output data/reports/retrieval_smoke_matrix.json --output-md data/reports/retrieval_smoke_matrix.md
cipp-report-retrieval-smoke-matrix --include-guidance-topics --output data/reports/retrieval_smoke_matrix_guidance.json --output-md data/reports/retrieval_smoke_matrix_guidance.md
```

Raportti laskee jokaiselle aiheelle `pass`, `partial` tai `fail` -tilan sekä matrix-tason `release_candidate`-arvon. `partial` voi olla hyväksyttävä esimerkiksi vastaanotto-, takuu- tai videotarkastusaiheessa, jos raportti kertoo selkeän syyn eikä anonymisointitarkistus löydä vuotoja. Tämä ei ole agenttivastaus, vaan retrieval-valmiuden testi.

## Answer composer smoke matrix

`cipp-report-answer-smoke-matrix` on hyväksymisportti ennen mahdollista `v0.6.0`-releaseä. Se ajaa 20 kysymystä composerin läpi: samat 10 core CIPP -aihetta kuin retrieval smoke matrix sekä 10 legal guidance -aihetta putkiremontin hankesuunnittelusta, hallituksen valmistelusta, osakaskysymyksistä, kuntotutkimuksesta, menetelmävalinnasta, vastaanotosta, takuusta ja viranomaisvelvoitteista.

```powershell
cipp-report-answer-smoke-matrix --output data/reports/answer_smoke_matrix.json --output-md data/reports/answer_smoke_matrix.md
```

Retrieval smoke matrix testaa, löytyykö aineisto. Answer smoke matrix testaa, muodostuuko aineistosta turvallinen lähdevastaus: `llm_used=false`, lähteet mukana, Markdown ei vuoda raakadataa, expert guidance ei muutu lakiväitteeksi ja hallucination guard ei löydä keksittyjä euroja, prosentteja, määräaikoja tai pitkiä opaskatkelmia. `v0.6.0` on release candidate vasta, kun matriisissä ei ole `fail`-aiheita.

## Source-grounded answer composer

`cipp-compose-answer` on ensimmäinen kontrolloitu vastauskerros retrieval-paketin päälle. Se ei ole täysi agentti, ei kutsu LLM:ää eikä keksi tietoa retrieval-paketin ulkopuolelta. Se valitsee tärkeimmät anonymisoidut lähdekatkelmat, muodostaa lyhyen lähdeperustaisen vastauksen ja näyttää puuttuvat käyttäjätiedot sekä epävarmuudet.

```powershell
cipp-compose-answer --question "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?" --output data/reports/answer_payment.json --output-md data/reports/answer_payment.md
cipp-compose-answer --retrieval-packet data/reports/retrieval_packet.json --output data/reports/answer.json --output-md data/reports/answer.md
```

`answer_status` kertoo vastauksen käyttökelpoisuuden:

- `answered`: retrieval ja evidence coverage ovat kunnossa, ja lähdekatkelmia löytyi
- `partial`: aineistoa löytyi, mutta coverage tai retrieval jäi osittaiseksi
- `insufficient_evidence`: lähdekatkelmia ei ole riittävästi turvalliseen vastaukseen

Lähteet näytetään `reference_001`-tyyppisinä anonymisoituina viitteinä. Composer käyttää samoja sanitointisääntöjä kuin retrieval-paketti ja redaktoi esimerkiksi raakadatapolkuja, dokumenttinimiä, henkilötietoja ja varomattomia rahamääriä. `llm_used` on tässä vaiheessa aina `false`.

Jos vastaus perustuu expert guidance -aineistoon, composer näyttää lähdeluokan `expert_guidance` ja lisää epävarmuuden: sitova oikeudellinen tulkinta pitää varmistaa varsinaisesta lakitekstistä, yhtiöjärjestyksestä, sopimuksesta tai asiantuntijalta. Käyttäjälle sopiva muoto on “Oppaan mukaan” tai “Asiantuntijaohjeen perusteella”, ei “laki määrää”.

## Local dev API ja frontend playground

`cipp-run-dev-api` käynnistää paikallisen FastAPI-kehityspalvelun nykyisen retrieval + composer -putken päälle. API ei lisää vapaata LLM-vastausta eikä duplikoi business-logiikkaa. `llm_enabled=false` ja vastaukset perustuvat `cipp-build-retrieval-packet` + `cipp-compose-answer` -kerrokseen.

```powershell
cipp-run-dev-api --host 127.0.0.1 --port 8000
```

Endpointit:

- `GET /api/health`
- `GET /api/app-config`
- `GET /api/suggested-questions`
- `POST /api/answer`

Frontend näyttää API health -tilan badgeissa: `api: ok`, `api: offline` tai `api: error`. Jos `/api/answer` ei vastaa, käyttöliittymä näyttää käytetyn API base URLin, endpointin ja backendin käynnistysohjeen pelkän geneerisen `Failed to fetch` -tekstin sijaan.

Frontend löytyy kansiosta `apps/web`. Se on suomenkielinen paikallinen testauskäyttöliittymä, jossa käyttäjä voi säätää taloyhtiön perustietoja, kysyä sukitusurakasta ja nähdä lähdeperustaisen vastauksen.

Frontendin perusnäkymä on yksipalstainen. Erilliset oikean reunan `Lähteet`- ja `Epävarmuudet`-sivupaneelit on poistettu, eikä tyhjiä placeholder-kortteja renderöidä. Lähde-, epävarmuus-, puuttuva tieto- ja varoitusdata säilyy edelleen API-vastauksen JSONissa sekä debug-näkymässä kehittäjän tarkistusta varten.

```powershell
cd apps/web
npm install
npm run dev
```

Frontend käyttää oletuksena API:a osoitteessa `http://127.0.0.1:8000`. Asetus löytyy tiedostosta `apps/web/.env.example`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Yläpalkin parametrit lähetetään jokaisen kysymyksen mukana `user_case`-osiossa: asuntojen määrä, rakennukset, porrashuoneet, JV/SV-pystyviemärit, kattokaivot, pohjaviemärin pituus, tonttilinjan pituus ja sadevesilinjojen pituus. `Videotarkastus` ja `Yksikköhinnat / lisätyöt` on poistettu perusnäkymästä ja pikakysymysnapeista, vaikka niitä voidaan käsitellä backendissä myöhemmin tarkemmissa työvaiheissa.

Frontendin oletuscase on: `apartments_count=30`, `buildings_count=1`, `staircases_count=3`, `jv_verticals_count=15`, `sv_verticals_count=4`, `roof_drains_count=4`, `bottom_drain_length_m=50`, `yard_line_length_m=30` ja `stormwater_line_length_m=30`. Kattokaivojen oletusarvo johdetaan SV-pystyviemäreiden oletusarvosta, eli oletuksena molemmat ovat 4. Käyttäjä voi silti muuttaa `roof_drains_count`-arvoa erikseen, jos kohteessa kattokaivojen määrä poikkeaa SV-pystyviemäreiden määrästä.

Frontendin default-case on keskitetty tiedostoon `apps/web/src/config/defaultCase.ts`. Selain tallentaa case-arvot versionoidusti localStorageen avaimilla `cipp_user_case` ja `cipp_user_case_schema_version`. Jos selaimessa näkyy vanhoja nolla-arvoja tai poistettuja kenttiä, avaa testinäkymä reset-parametrilla:

```text
http://127.0.0.1:5173/?resetCase=1
```

Mock-testissä sama onnistuu osoitteella `http://127.0.0.1:5173/?mock=1&resetCase=1`.

Hintakysymykset kuten `Kuinka paljon yllä asetettu taloyhtiön sukitusurakka maksaa?` tunnistetaan `cost_estimate`-intentiksi ennen yleisiä ohjeaiheita. Composer käyttää silloin yläpalkin nykyisiä `user_case`-arvoja, näyttää vastauskortissa `Arviossa käytetty case` -osion ja listaa kustannusajurit. Euromääräinen haarukka annetaan vain, jos rakenteisesta ja anonymisoidusta referenssidatasta löytyy riittävä hintapohja; muuten vastaus sanoo selvästi, ettei euromääräistä arviota voi muodostaa, ja listaa puuttuvat tiedot.

Referenssiprojektit pysyvät sisäisenä anonymisoituna grounding-aineistona. UI näyttää lähteet `reference_001`-tyyppisinä viitteinä eikä näytä raakadatahakemistoja, luottamuksellisia tiedostonimiä tai oikeita projektinimiä. Debug-paketti on oletuksena pois päältä ja sekin kulkee API:n sanitoinnin läpi.

Frontendissä on myös mock API -tila nopeaan UI-testaukseen ilman tietokantaa:

```text
http://127.0.0.1:5173/?mock=1
```

Automaattinen smoke-testi ajaa saman mock-polun Playwrightilla:

```powershell
cd apps/web
npm run test:smoke
```

Ensimmäisellä konekohtaisella ajolla Playwright voi tarvita Chromiumin:

```powershell
npx playwright install chromium
```

Manuaalinen testauslista on tiedostossa [frontend_testing.md](F:/-DEV-/97.cipp-contract-db/docs/frontend_testing.md).

## Supabase auth planning

Supabasea suunnitellaan vain auth- ja session-kerrokseksi. CIPP:n raskas dokumenttidata, KG, legal guidance, retrieval ja composer pysyvät omassa PostgreSQL/FastAPI-putkessa.

Nykyisessä frontendissä on auth-adapterirajapinta ja mock login/register/logout -prototyyppi. Oletusprovider on `mock`, eikä oikeaa Supabase-clienttiä tai tuotanto-SaaS-käyttäjähallintaa ole vielä kytketty.

```env
VITE_AUTH_PROVIDER=mock
# VITE_SUPABASE_URL=
# VITE_SUPABASE_ANON_KEY=
```

Suunnitelma ja rajaukset ovat tiedostossa [supabase_auth_plan.md](F:/-DEV-/97.cipp-contract-db/docs/supabase_auth_plan.md).
