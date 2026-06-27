# Repositorion rakenne ja toiminta

Tämä tiedosto on tarkoitettu käytännön kartaksi koko repositorioon. README kertoo projektin päätarkoituksen ja käynnistyksen; tämä tiedosto selittää tarkemmin, mitä kukin kansio, tietokantakerros ja kooditiedosto tekee.

Projektin tavoite on rakentaa relaatiotietokanta CIPP-/limisukitusurakoiden asiakirjoista niin, että eri taloyhtiöiden hankkeita voidaan vertailla keskenään. Tietokanta ei ole pelkkä dokumenttiarkisto, vaan siitä rakennetaan analysoitava malli: urakkasopimukset, tarjouspyynnöt, YSE 1998, rakentamisen lait, urakkarajat, JV/SV-linjat, hinnat, maksuerät, laatudokumentit, vastaanotto, takuu, videotarkastukset ja käytännön työmaan tapahtumat.

## 1. Kokonaiskuva

Repo toimii ETL-putkena:

1. Asiakirjat siirretään projektikohtaisesti `data/raw/`-kansioon.
2. Lähdetiedostot inventoidaan `raw.source_files`-tauluun.
3. PDF-sivut puretaan tekstiksi `raw.pages`-tauluun ja `data/extracted/`-kansioon.
4. Sivuteksteistä tehdään redaktoituja markdown-asiakirjoja.
5. Markdownista ja tietokannasta rakennetaan kanoninen JSON-malli.
6. JSON validoidaan.
7. JSON ladataan PostgreSQL-tietokantaan relaatiotauluiksi.
8. Asiakirjat linkitetään sopimuksiin ja niiden sisältö pilkotaan haku- ja analyysikäyttöön.
9. Tarjouspyynnöistä ja operatiivisista asiakirjoista rikastetaan projektifaktoja.
10. Hintalogiikka vertaa käyttäjän taloyhtiötä lähimpään omaan referenssihankkeeseen.

Karkeasti:

```text
data/raw
  -> raw.source_files
  -> raw.pages
  -> data/extracted/.../markdown
  -> data/normalized/...canonical.json
  -> core / doc / domain / finance / quality / rag / audit
  -> analyysi, vertailu, hinta-arviot ja kysymys-vastauslogiikka
```

## 2. Nykytila 2026-06-26

Tässä vaiheessa repo ei ole enää pelkkä suunnitelma, vaan toimiva paikallinen ETL- ja analyysipohja. Tietokannassa on kuusi referenssiprojektia, yhteiset sopimusehdot ja rakentamisen lakiaineiston ylätaso.

Nykyinen käsittelytilanne:

```text
referenssiprojektit: 6
lähdetiedostot tietokannassa: 413
raw.pages-tekstitietueet: 952
Office-tekstipurku: käytössä
LibreOffice-muunnos: käytössä
visuaalinen OCR: käytössä
DWG -> PDF -muunnos: käytössä
```

Projektikohtainen tekstikerros:

| Referenssi | Lähdetiedostot | Tekstitietueet |
|---|---:|---:|
| Referenssikohde A | 123 | 232 |
| Referenssikohde B | 62 | 256 |
| Referenssikohde C | 63 | 146 |
| Referenssikohde D | 16 | 41 |
| Referenssikohde E | 82 | 160 |
| Referenssikohde F | 67 | 117 |

Tärkeät viimeisimmät edistysaskeleet:

- kuvat ja skannit on ajettu visuaalisen OCR:n läpi
- DWG-piirustukset muunnetaan Autodesk DWG TrueView 2027:llä PDF-muotoon
- DWG:stä syntyvät PDF:t rekisteröidään johdannaisiksi lähdetiedostoiksi `raw.source_files`-tauluun
- DWG-PDF:t voidaan OCR-käsitellä rajatusti `--pdf-only`- ja `--notes-contains`-lipuilla
- raw-kerroksessa on nyt tarpeeksi tekstisisältöä seuraavaan normalisointi- ja vertailuvaiheeseen

Audit-huomio: `raw.extraction_runs` säilyttää myös epäonnistuneet testi- ja kokeiluajot. Niitä ei pidä tulkita suoraan nykyiseksi virhetilaksi. Laaturaportin pitää erottaa viimeisin onnistunut käsittely historiassa olevista aiemmista epäonnistumisista.

## 3. Seuraava etenemissuunnitelma

Seuraavat kehitysaskeleet tehdään tässä järjestyksessä:

1. **Käsittelyn laaturaportti.** Komento `cipp-report-processing-quality` näyttää projektikohtaisesti tiedostomäärät, tekstisivut, uusimmat onnistuneet purut, epäonnistuneet ajot, OCR-tarpeet ja puuttuvat tekstit.
2. **Markdown- ja section-kerroksen päivitys.** `cipp-build-markdown` kokoaa kaikki saman dokumenttityypin raw-tekstit yhteen markdowniin ja `cipp-load-markdown-sections --ensure-raw-documents --prune-missing-markdown` vie ne `doc.sections`- ja `doc.clauses`-kerrokseen.
3. **Projektifaktojen rikastus.** Poimitaan jokaisesta hankkeesta samat vertailukentät: asuntojen määrä, JV/SV-laajuus, pystylinjat, pohjaviemärit, tonttilinjat, hinnat, lisätyöt, vastaanotto, puutteet, takuu ja videotarkastukset.
4. **Vertailukelpoisuusmatriisi.** Komento `cipp-report-reference-facts` rakentaa raportin, jossa jokainen referenssi näkyy samoilla sarakkeilla ja puuttuvat tiedot erottuvat.
5. **PostgreSQL-native knowledge graph.** `cipp-build-knowledge-graph` kokoaa rakenteisista tietokantatauluista todistettavan suhdeverkon `kg`-skeemaan ilman Neo4j:tä tai LLM-arvauksia.
6. **User-case retrieval packet.** `cipp-build-retrieval-packet` hakee käyttäjän CIPP-kysymykseen liittyvät entityt, suhteet, evidencen ja tekstikatkelmat ilman LLM-agenttia.
7. **Source-grounded answer composer.** `cipp-compose-answer` muodostaa retrieval-paketista lyhyen, kontrolloidun lähdevastauksen ilman LLM:ää.
8. **Ensimmäinen kysely-MVP.** Käyttäjä antaa taloyhtiön tiedot, järjestelmä valitsee lähimmän referenssikohteen ja antaa alustavan hinta-/riskikommentin lähdeaineiston perusteella.

Tämän suunnitelman nykyinen konkreettinen toteutettava osa on source-grounded answer composer -kerros.

Tärkeä rajaus: `kg` ja retrieval ovat käytössä vastausaineiston rakentamiseen, mutta vapaata GraphRAG-/LLM-vastausta ei aloiteta vielä. Tavoite on välttää tilanne, jossa vastaus näyttäisi täsmälliseltä mutta perustuisi puuttuviin tai heikosti jäljitettäviin faktoihin.

## 4. Repojuuren tiedostot

### `README.md`

Projektin aloitusopas. Sisältää Docker/PostgreSQL-käynnistyksen, perusrakenteen, ensimmäisen pilotin, YSE/lakien aseman, JV/SV-jaon, videotarkastuksen ja hintasäännön.

### `REPO_RAKENNE_JA_TOIMINTA.md`

Tämä tiedosto. Tavoite on selittää koko repo niin, että näet mitä jokainen osa tekee ja mihin kohtaan projektin kokonaisuutta se liittyy.

### `SOTA_PostgreSQL_CIPP_urakkasopimus_template.md`

Alkuperäinen suunnitelma / arkkitehtuuridokumentti. Se on suunnittelutason dokumentti, josta repo on lähtenyt liikkeelle. Toteutus on kasvanut siitä eteenpäin käytännön projektidatan mukana.

### `docker-compose.yml`

Käynnistää PostgreSQL + pgvector -tietokannan Dockerissa.

Tärkeää:

- käyttää imagea `pgvector/pgvector:pg16`
- julkaisee portin `${POSTGRES_PORT:-55432}:5432`
- lukee käyttäjän, salasanan ja tietokannan nimen `.env`-tiedostosta
- ajaa `db/migrations/`-kansion SQL-tiedostot ensimmäisellä tietokannan alustuksella
- säilyttää datan Docker-volumessa `postgres_data`

### `.env`

Paikalliset salaisuudet ja asetukset. Tätä ei pidä commitoida. Sisältää esimerkiksi PostgreSQL-salasanan ja `DATABASE_URL`-yhteysmerkkijonon.

### `.gitignore`

Määrittää mitä ei tallenneta versionhallintaan. Tyypillisesti esimerkiksi `.env`, virtuaaliympäristöt, välimuistit ja paikalliset raskaat datahakemistot pidetään poissa gitistä.

### `pyproject.toml`

Python-projektin määritykset:

- paketin nimi on `cipp-contracts`
- Python-versio vähintään 3.10
- ajonaikaiset riippuvuudet: `pypdf`, `psycopg[binary]`
- kehitysriippuvuudet: `pytest`, `ruff`
- järjestelmäriippuvuudet: Docker Desktop, Docker Compose, LibreOffice, Autodesk DWG TrueView 2027 ja paikallinen `kuvien-parsinta` OCR-pipeline
- komentorivityökalut määritellään `[project.scripts]`-osiossa

Tämä on tiedosto, joka kertoo Pythonille miten projekti asennetaan kehitystilaan ja mitä komentoja repo tarjoaa.

### Riippuvuudet käytännössä

Python-riippuvuudet löytyvät myös tiedostoista:

- `requirements.txt`: ajonaikaiset kirjastot
- `requirements-dev.txt`: ajonaikaiset kirjastot sekä testaus- ja lint-työkalut

Järjestelmätason riippuvuudet eivät ole Python-paketteja:

- Docker Desktop ajaa PostgreSQL/pgvector-tietokannan.
- Docker Compose käynnistää `docker-compose.yml`-palvelut.
- LibreOffice muuntaa vanhat binääriset Office-tiedostot, erityisesti `.doc` ja `.xls`, moderniin OOXML-muotoon tekstipurkua varten.
- Autodesk DWG TrueView 2027 muuntaa DWG-piirustukset PDF-muotoon Core Consolen kautta.
- `kuvien-parsinta` ajaa visuaalisen OCR:n kuville ja skannatuille piirustuksille erillisen OCR-repositorion valmiilla PaddleOCR-VL/PP-StructureV3-putkella.

Windowsissa oletettu LibreOffice-polku on:

```text
C:\Program Files\LibreOffice\program\soffice.exe
```

Jos LibreOffice ei ole PATHissa, komennolle `cipp-extract-remaining-text` annetaan polku parametrilla `--soffice-path`.

Windowsissa oletettu Autodesk Core Console -polku on:

```text
C:\Program Files\Autodesk\DWG TrueView 2027 - English\accoreconsole.exe
```

Jos TrueView ei ole PATHissa, komennolle `cipp-extract-dwg-trueview` annetaan polku parametrilla `--accoreconsole-path`.

Visuaalinen OCR käyttää ensisijaisesti tätä paikallista komentoa:

```text
F:\-DEV-\95.Kuvien-parsinta-SOTA\.venv\Scripts\kuvien-parsinta.exe
```

Tähän repoon ei kopioida raskaita OCR-mallipainoja tai vanhan OCR-repon ympäristöä. Sen sijaan tähän repoon on lisätty adapteri, joka käyttää valmista pipelinea ja tallentaa tuloksen tämän projektin tietokantamalliin.

## 5. Kansiorakenne

### `data/`

Projektin aineistokerros.

```text
data/
  raw/         alkuperäiset asiakirjat projektikohtaisesti
  extracted/   PDF:stä puretut sivut ja markdownit
  normalized/  kanoniset JSON-mallit
  reports/     inventointi-, validointi- ja käsittelyraportit
```

`data/raw/` on lähdearkisto. Sinne kuuluvat projektien alkuperäiset asiakirjat omissa kansioissaan. YSE 1998 ja rakentamisen lait ovat yhteisiä ylätason lähteitä, eivät yksittäisen projektin omia asiakirjoja.

`data/extracted/` sisältää koneellisesti tuotettuja välituloksia. Sieltä löytyvät esimerkiksi PDF-sivujen JSONit ja markdown-tiedostot kuten `rfq.md`, `main_contract.md` ja `quality_plan.md`.

`data/normalized/` sisältää projektikohtaiset canonical JSON -tiedostot. Ne ovat välimalli dokumenttimaailman ja relaatiotietokannan välillä.

`data/reports/` sisältää käsittelyn raportteja: mitä tiedostoja löydettiin, mitä validoitiin, missä oli puutteita.

### `db/`

Tietokannan rakenne ja hyötykyselyt.

```text
db/
  migrations/  tietokannan skeeman luonti ja sanastojen siemendata
  queries/     valmiita analyysi- ja tarkistuskyselyjä
```

### `src/cipp_contracts/`

Varsinainen Python-koodi. Tämä on repositorion ohjelmallinen ydin.

```text
src/cipp_contracts/
  extract/     lähdetiedostojen inventointi ja tekstin purku
  normalize/   asiakirjatekstin muuntaminen kanoniseksi malliksi
  load/        kanonisen mallin lataus PostgreSQL-tietokantaan
  kg/          PostgreSQL-native knowledge graph -rakentaja
  retrieve/    user-case retrieval packet -rakentaja
  answer/      deterministic source-grounded answer composer
  api/         paikallinen FastAPI-kehitysrajapinta playgroundille
  price/       JV-urakan hinta-arviolaskenta
  validate/    canonical JSON -validointi
  embed/       varattu embedding-/vektorointikerrokselle
  search/      varattu hakutoiminnoille
```

### `tests/`

Automaattitestit tärkeimmälle logiikalle. Testit ovat pieni mutta tärkeä turvaverkko: ne varmistavat, että tarjouspyyntöjen faktaparseri, canonical-validointi ja JV-hintalogiikka eivät hajoa huomaamatta.

## 6. Tietokannan pääajatus

Tietokanta on jaettu skeemoihin, jotta eri tietotyypit eivät mene sekaisin.

### `ref`

Viitesanastot. Tärkein taulu on `ref.document_types`, joka määrittää asiakirjatyypit kuten:

- `main_contract`
- `rfq`
- `contract_terms`
- `payment_schedule`
- `unit_prices`
- `quality_manual`
- `yse_1998`
- `law_rakentamislaki_751_2023`
- `law_alueidenkayttolaki_132_1999`
- `video_inspection_report`

Asiakirjatyypit ovat erittäin tärkeitä, koska niiden avulla eri projektien erilaiset kansiorakenteet muutetaan vertailukelpoisiksi.

### `raw`

Raaka lähdekerros.

- `raw.source_files`: jokainen alkuperäinen lähdetiedosto
- `raw.source_file_document_types`: yhden lähdetiedoston asiakirjatyyppi tai tyypit
- `raw.extraction_runs`: tekstinpurkuajot
- `raw.pages`: PDF-sivujen teksti sivutasolla

Tämä kerros vastaa kysymykseen: mistä tieto tuli?

### `core`

Projektin ja sopimuksen ydintiedot.

- `core.projects`: hankkeet, esimerkiksi Referenssikohde A, Referenssikohde B, Referenssikohde C
- `core.properties`: taloyhtiön / kiinteistön tekniset perustiedot
- `core.contracts`: urakkasopimukset
- `core.parties`: sopijaosapuolet, tilaaja, urakoitsija, valvoja jne.
- `core.contract_documents`: sopimusasiakirjat ja niiden pätevyysjärjestys
- `core.canonical_versions`: ladatut canonical JSON -versiot

Tämä kerros vastaa kysymykseen: mikä hanke, mikä sopimus ja mitkä asiakirjat siihen kuuluvat?

### `doc`

Asiakirjasisällön analyysikerros.

- `doc.sections`: markdownista muodostetut asiakirjaosiot
- `doc.clauses`: pykälä-/ehtotason tekstikatkelmat
- `doc.obligations`: velvoitteet, esimerkiksi urakoitsijan tehtävät

Tämä kerros vastaa kysymykseen: mitä asiakirjoissa sanotaan?

### `domain`

Rakentamisen ja CIPP-urakan toimialamalli.

- `domain.scope_items`: urakan sisältö
- `domain.boundaries`: urakkarajat
- `domain.sewer_segments`: JV/SV-linjat ja niiden osat
- `domain.technical_requirements`: tekniset vaatimukset
- `domain.deliverables`: luovutusaineisto ja toimitettavat dokumentit
- `domain.responsibilities`: vastuut
- `domain.schedule_milestones`: aikataulun virstanpylväät

Tämä on repositorion tärkeimpiä kerroksia, koska tässä dokumenttiteksti muuttuu vertailtavaksi urakkatiedoksi.

### `finance`

Rahaan liittyvä tieto.

- `finance.contract_prices`: sopimushinnat
- `finance.payment_schedule_items`: maksuerät
- `finance.unit_prices`: lisä- ja yksikköhinnat
- `finance.securities`: vakuudet
- `finance.insurances`: vakuutukset
- `finance.price_estimates`: järjestelmän laskemat hinta-arviot

Tämä kerros vastaa kysymykseen: mitä urakka maksaa, mistä hinta muodostuu ja miten maksut etenevät?

### `quality`

Laadunvarmistus ja tarkastukset.

- `quality.requirements`: laatuvaatimukset, kuten videotarkastus
- `quality.inspections`: tarkastukset
- `quality.defects`: virheet ja puutteet

Videotarkastus kuuluu tähän ajatteluun: urakoitsija kuvaa valmiit JV/SV-linjat, valvoja kommentoi kuvaukset, ja näitä käytetään myöhemmin takuuajan tarkastuksessa.

### `rag`

Hakua ja tulevaa RAG-käyttöä varten.

- `rag.chunks`: tekstikatkelmat, joihin voidaan tehdä full text -hakua
- `rag.embeddings`: vektorihakua varten varattu embedding-taulu

Tämä kerros on tarkoitettu kysymys-vastauslogiikan pohjaksi.

### `kg`

PostgreSQL-native knowledge graph -kerros.

- `kg.entity_types`: sallittu entity-sanasto
- `kg.relation_types`: sallittu relaatiosanasto
- `kg.entities`: projektit, sopimukset, asiakirjat, osiot, ehdot, osapuolet, laajuudet, vaatimukset, maksuerät, tarkastukset, puutteet, vastaanotot ja tapahtumat graph-solmuina
- `kg.relations`: todistettavat suhteet, kuten `HAS_CONTRACT`, `HAS_DOCUMENT`, `HAS_SECTION`, `REQUIRES`, `AFFECTS` ja `SUPPORTED_BY`
- `kg.evidence`: linkit siihen, mistä entity tai relaatio syntyi

Tämä kerros ei ole Neo4j, GraphDB eikä uusi palvelu. Se on relaatiotietokannan sisäinen suhdekerros, joka rakennetaan olemassa olevasta `core`, `doc`, `domain`, `finance`, `quality`, `ops` ja `raw` -datasta. `rag` hakee tekstikatkelmia; `kg` kertoo, miten sopimus, asiakirja, vaatimus, viemärisegmentti, maksuerä tai vastaanoton havainto liittyy toisiin tietoihin.

### `audit`

Jäljitettävyys, virheet ja tietosuojahavainnot.

- `audit.validation_issues`: validoinnin löydökset
- `audit.pii_findings`: henkilötieto-/salassapitohavainnot
- `audit.processing_events`: käsittelyn tapahtumaloki

Tämä kerros vastaa kysymykseen: mitä käsittelyssä tapahtui ja mitä pitää tarkistaa?

### `ops`

Operatiivinen projektitieto.

Työn aikana Referenssikohde Bn, Referenssikohde An ja Referenssikohde Cn lisäaineistoista on alettu mallintaa oikean työmaan etenemistä: kokoukset, vastaanotto, lisätyöt, käytännön ongelmat, valvojan havainnot ja ratkaisut.

Tähän kokonaisuuteen kuuluvat käsitteellisesti esimerkiksi:

- projektitapahtumat
- kokous- ja vastaanottokirjaukset
- operatiiviset havainnot
- ongelmat ja ratkaisut
- maksujen hyväksynnät
- luovutus- ja vastaanottotiedot

Tärkeä nykytilahuomio: osa tästä operatiivisesta kerroksesta on syntynyt projektin aikana tietokantaan suoraan. Se kannattaa seuraavaksi vakioida omaksi migraatioksi ja Python-importeriksi, jotta sama prosessi voidaan ajaa kaikille uusille hankkeille samalla tavalla.

## 7. Migraatiot

Migraatiot ovat `db/migrations/`-kansiossa. Docker ajaa ne aakkos-/numerojärjestyksessä, kun tietokantavolyymi luodaan ensimmäisen kerran.

### `001_init.sql`

Perustaa koko tietokantarungon:

- ottaa käyttöön `pgcrypto`, `pg_trgm`, `unaccent`, `vector`
- luo skeemat `raw`, `core`, `doc`, `domain`, `finance`, `quality`, `rag`, `audit`, `ref`
- luo tärkeimmät taulut kaikille ydinkerroksille
- lisää alkuperäiset asiakirjatyypit
- luo indeksejä hakua, liittymiä ja full text -hakua varten

Tämä on tietokannan peruskivi.

### `002_source_file_document_types.sql`

Lisää `raw.source_file_document_types`-taulun. Sen avulla yksi lähdetiedosto voidaan merkitä yhdeksi tai useammaksi asiakirjatyypiksi.

Tämä on tärkeää, koska todellisissa projektikansioissa tiedostojen nimet ja sisällöt eivät aina ole täydellisen siistejä.

### `003_yse_1998_document_type.sql`

Lisää asiakirjatyypin `yse_1998`. YSE 1998 on yleinen sopimusehto, joka koskee kaikkia hankkeita ylemmän tason sopimusaineistona.

### `004_construction_law_document_types.sql`

Lisää rakentamisen lakiasiakirjat:

- `law_rakentamislaki_751_2023`
- `law_alueidenkayttolaki_132_1999`

Nämä ovat YSE:n kanssa yhteistä ylätason aineistoa, eivät yksittäisen projektin sisäisiä liitteitä.

### `005_optional_project_document_types.sql`

Lisää projektikohtaisia lisäasiakirjatyyppejä:

- liiteluettelo
- urakkaneuvottelun liite
- työturvallisuus-/työsuojelusuunnitelma
- aikataulu
- urakoitsijan liitteet
- toteutus- ja laadunhallintasuunnitelma
- projektihuomio

Tämä syntyi tarpeesta käsitellä projekteja, joissa asiakirjakokonaisuus vaihtelee.

### `006_sewer_segments.sql`

Luo `domain.sewer_segments`-taulun JV/SV-linjojen vertailtavalle mallille.

JV-järjestelmä kuvataan virtaussuunnassa:

1. asuntohajotukset
2. pystylinjat
3. pohjaviemäri
4. tonttilinja

SV-järjestelmä kuvataan vastaavasti:

1. pihakaivot ja maan alla kulkevat SV-tonttilinjat
2. mahdolliset kattokaivot
3. mahdolliset SV-pystylinjat
4. mahdollinen SV-pohjaviemäri

Tauluun tallennetaan myös kuuluuko segmentti urakkaan, miten varma tulkinta on, mikä on urakkaraja ja mikä on hinnallinen vaikutus.

## 8. Python-koodin yhteiset perustiedostot

### `src/cipp_contracts/config.py`

Lukee `.env`-tiedoston ja palauttaa tietokantayhteyden.

Päätehtävä:

- `load_env_file()` lukee avain-arvoparit `.env`:stä
- `get_database_url()` palauttaa `DATABASE_URL`-arvon ympäristöstä tai `.env`:stä

Kaikki tietokantaan kirjoittavat komennot nojaavat tähän.

### `src/cipp_contracts/jsonio.py`

Pieni apumoduuli JSON-tiedostojen lukemiseen ja kirjoittamiseen.

Päätehtävä:

- `read_json_object(path)` lukee JSON-objektin
- `write_json_object(path, data)` kirjoittaa JSON-objektin siististi UTF-8-muodossa

Tätä käytetään canonical JSON -tiedostojen kanssa.

### `src/cipp_contracts/model.py`

Yhteiset mallimääritykset ja validointiapurit.

Sisältää esimerkiksi:

- pakolliset asiakirjatyypit
- canonical JSON -juuritason avaimet
- `ValidationIssue`-rakenteen
- `decimal_or_none()`-apurin rahalukujen käsittelyyn

Tämä vähentää sitä, että samat merkkijonot ja validointisäännöt kopioituisivat moneen paikkaan.

## 9. Extract: lähteistä tekstiksi

### `src/cipp_contracts/extract/inventory_source_files.py`

Inventoi projektikansion lähdetiedostot.

Mitä se tekee:

- käy läpi annetun `data/raw/...`-kansion
- laskee tiedoston koon ja SHA-256-tiivisteen
- arvaa asiakirjatyypin tiedostonimen perusteella
- kirjoittaa tiedoston `raw.source_files`-tauluun
- kirjoittaa asiakirjatyypit `raw.source_file_document_types`-tauluun
- tuottaa inventointiraportin

Tämä on yleensä ensimmäinen komento, kun uusi projektikansio lisätään järjestelmään.

### `src/cipp_contracts/extract/extract_pdf_pages.py`

Purkaa PDF-tiedostojen sivut tekstiksi.

Mitä se tekee:

- lukee PDF:t `raw.source_files`-taulusta
- käyttää `pypdf`-kirjastoa tekstin purkamiseen
- luo ajon `raw.extraction_runs`-tauluun
- tallentaa sivut `raw.pages`-tauluun
- kirjoittaa sivukohtaisia JSON-tiedostoja `data/extracted/.../pages/`-kansioon

Tämä säilyttää sivutason lähdeviittauksen. Se on tärkeää myöhempää todistettavuutta varten.

### `src/cipp_contracts/extract/extract_office_text.py`

Purkaa modernien Office-tiedostojen tekstisisällön.

Mitä se tekee:

- lukee `.docx`- ja `.xlsx`-tiedostoja `raw.source_files`-taulusta
- purkaa kappaletekstit, taulukkotekstit ja taulukkolaskennan solut
- kirjoittaa tekstin `raw.pages`-tauluun
- tuottaa ajolokin `raw.extraction_runs`-tauluun

Tämä on tärkeä erityisesti työmaapöytäkirjoille, lisätyöasiakirjoille ja taulukoille.

### `src/cipp_contracts/extract/extract_remaining_text.py`

Käsittelee ne tiedostot, joita PDF- ja Office-peruspurku eivät kata.

Mitä se tekee:

- käyttää LibreOfficea vanhojen `.doc`- ja `.xls`-tiedostojen muuntamiseen
- lukee tekstipohjaiset tiedostot kuten `.txt`, `.xml`, `.odt` ja `.gdoc`
- kirjaa kuvat, DWG:t ja muut erikoistiedostot seurantamerkinnöiksi
- tallentaa onnistuneet tekstipurkutulokset `raw.pages`-tauluun

Tämä pitää inventaarion eheänä: tiedetään mitä on käsitelty, mitä voidaan lukea suoraan ja mikä tarvitsee erikoisputken.

### `src/cipp_contracts/extract/extract_visual_ocr.py`

Ajaa visuaalisen OCR:n kuville ja skannatuille dokumenteille.

Mitä se tekee:

- hakee `.jpg`, `.jpeg` ja `.png`-tiedostot `raw.source_files`-taulusta
- kutsuu ulkoista `kuvien-parsinta parse` -komentoa
- käyttää OCR-repositorion valmista rakenne-OCR-putkea, esimerkiksi `structurev3`-moottoria
- lukee tuotetun markdownin ja tallentaa sen `raw.pages`-tauluun
- kirjoittaa OCR-ajon lokin `data/extracted/visual_ocr/`-kansioon
- osaa `--pdf-only`- ja `--notes-contains`-lipuilla rajata OCR:n esimerkiksi vain DWG:stä syntyneisiin OCR-tarpeisiin PDF-välituloksiin

Tämä on silta kuva-/skannausmaailmasta samaan relaatiotietokantaan kuin PDF- ja Office-asiakirjat.

### `src/cipp_contracts/extract/extract_dwg_trueview.py`

Muuntaa DWG-piirustukset PDF-muotoon Autodesk DWG TrueView 2027:n avulla.

Mitä se tekee:

- hakee `.dwg`-tiedostot `raw.source_files`-taulusta
- ajaa `accoreconsole.exe`-ohjelman projektikohtaisella plottausskriptillä
- tuottaa PDF-välituloksen `data/extracted/dwg_trueview/`-kansioon
- rekisteröi syntyneen PDF:n johdannaiseksi lähdetiedostoksi `raw.source_files`-tauluun
- tallentaa `raw.pages`-tauluun jäljitettävän merkinnän siitä, mihin PDF muunnettiin
- säilyttää TrueViewin stdout/stderr-lokin myöhempää virheiden analyysia varten

DWG-adapteri ei vielä tulkitse piirustusten sisältöä itse. Sen tehtävä on ensin saada DWG:t luettavaan PDF-välimuotoon, jonka jälkeen PDF- ja OCR-putket voivat käsitellä niitä samalla periaatteella kuin muut lähteet.

### `src/cipp_contracts/extract/build_markdown.py`

Rakentaa PDF-sivuista markdown-asiakirjat.

Mitä se tekee:

- lukee sivutekstit `raw.pages`-taulusta
- ryhmittelee ne asiakirjatyypin mukaan, myös OCR-, DWG-PDF-, Office- ja LibreOffice-/remaining-putken tekstit
- redaktoi tunnistettavia henkilötietoja ja yhteystietoja
- kirjoittaa markdownit `data/extracted/<project>/markdown/`-kansioon
- siivoaa vanhat markdownit ennen uutta ajoa, jotta stale-tiedostot eivät päädy hakuindeksiin
- lisää sivukohtaiset lähde- ja extractor-metatiedot markdowniin
- kirjaa tietosuojahavainnot `audit.pii_findings`-tauluun

Tämä on kohta, jossa raakateksti muuttuu ihmiselle ja parserille helpommin luettavaksi muodoksi.

Nykyinen huomio: redaktoinnissa on vielä projektikohtaisia kovakoodattuja poistoja erityisesti Referenssikohde An aineistolle. Se kannattaa myöhemmin yleistää.

### `src/cipp_contracts/extract/import_finlex_legal_xml.py`

Tuo rakentamisen lakiaineistoa Finlexin XML-muodosta.

Mitä se tekee:

- lukee Finlex Open Data -XML-tiedostoja
- tunnistaa lakien osiot ja pykälät
- rekisteröi lähdetiedostot `raw.source_files`-tauluun
- luo lakiteksteistä markdown-tyyppiset osiot tietokantaan

Tämä on tärkeää siksi, että lait käsitellään samassa järjestelmässä kuin sopimukset, mutta yhteisenä ylätason aineistona.

## 10. Normalize: tekstistä kanoniseksi malliksi

### `src/cipp_contracts/normalize/build_canonical_contract.py`

Luo tyhjän canonical JSON -pohjan projektin aloitukseen.

Mitä se tekee:

- rakentaa validin perusrakenteen
- lisää pakolliset pääavaimet
- lisää oletusasiakirjat
- antaa projektikohtaisen tunnisteen

Tätä käytetään, kun halutaan aloittaa uusi hanke hallitulla rakenteella ennen kuin kaikki tiedot on rikastettu.

### `src/cipp_contracts/normalize/build_project_canonical.py`

Rakentaa projektin canonical JSON -mallin tietokannassa olevasta markdown-/asiakirjatiedosta.

Mitä se tekee:

- hakee projektin dokumentit tietokannasta
- lukee markdown-sisältöjä
- etsii sopimuspäivän, hinnat, kiinteistötiedot ja tarjouspyynnön faktat
- tunnistaa urakan sisältöä, urakkarajoja, JV/SV-segmenttejä, vakuuksia ja viivästyssakkoja
- muodostaa yhtenäisen JSON-rakenteen

Tämä on nykyisen tuotantoputken tärkein normalisointikoodi uusille projekteille.

### `src/cipp_contracts/normalize/enrich_canonical_from_markdown.py`

Rikastaa canonical JSON -mallia markdownista.

Tämä on vanhempi ja osittain Referenssikohde A-painotteinen rikastaja. Se sisältää paljon käsityönä rakennettua tulkintaa, kuten:

- asuntojen määrä
- urakkasopimuksen tiedot
- osapuolet
- asiakirjojen pätevyysjärjestys
- JV-urakkarajat
- maksuerät
- yksikköhinnat
- laatuvaatimukset
- luovutusaineisto
- aikataulu

Se on arvokas esimerkki siitä, miten asiakirjasisältö tulkitaan, mutta pitkällä aikavälillä yleisempi `build_project_canonical.py` on parempi pohja useiden hankkeiden käsittelylle.

### `src/cipp_contracts/normalize/rfq_facts.py`

Parsee tarjouspyyntöasiakirjasta teknisiä perustietoja.

Tämä on erittäin tärkeä moduuli, koska tarjouspyyntö on monessa projektissa paras lähde kiinteistön ja urakan laajuuden perustiedoille.

Se tunnistaa esimerkiksi:

- rakennusvuoden
- rakennusten määrän
- porrashuoneiden määrän
- asuntojen määrän
- kerrosalan
- kerrosmäärän
- liike-/palvelutilojen määrän
- JV-pystylinjojen määrän
- SV-pystylinjojen määrän

Se sisältää myös erikoislogiikkaa esimerkiksi Referenssikohde Cn kaltaisille kohteille, joissa rakennuksia on useita ja pystylinjojen määrä voidaan ilmaista vaihteluvälinä.

### `src/cipp_contracts/normalize/sync_rfq_facts.py`

Synkronoi tarjouspyyntöfaktat tietokantaan.

Mitä se tekee:

- lukee projektin `rfq.md`-tiedoston
- käyttää `rfq_facts.py`-parseria
- päivittää `core.properties`-taulua
- päivittää JV-pystylinjojen laajuustietoa

Tätä käytetään, kun halutaan tehdä projektien perusfaktoista vertailukelpoisia.

### `src/cipp_contracts/normalize/report_reference_facts.py`

Rakentaa kuuden referenssiprojektin vertailufaktamatriisin nykyisestä PostgreSQL-tietokannasta.

Mitä se tekee:

- lukee faktat `core`, `finance`, `domain`, `quality`, `ops`, `doc` ja `raw`-kerroksista
- laskee esimerkiksi hinta/asunto-luvun ja maksuerätaulukon summan
- merkitsee puuttuvat kentät `missing_fields`-sarakkeeseen
- merkitsee heikosti todistetut kentät `weak_evidence_fields`-sarakkeeseen
- kirjoittaa faktakohtaisen lähdejäljen kevyenä `evidence_json`-rakenteena
- antaa jokaiselle projektille `kg_readiness_status`-arvon: `ready`, `needs_review` tai `not_ready`

Tämä on hyväksymisportti ennen GraphRAG-/LLM-vastauskäyttöä. Jos faktat eivät ole vielä selkeästi vertailukelpoisia ja jäljitettäviä, graafia ei pidä käyttää vastausten perustana.

## 11. Load: kanonisesta mallista tietokantaan

### `src/cipp_contracts/load/load_contract_package.py`

Lataa canonical JSON -sopimuspaketin PostgreSQL-tietokantaan.

Mitä se tekee:

- lisää tai päivittää projektin `core.projects`-tauluun
- lisää kiinteistön `core.properties`-tauluun
- lisää sopimuksen `core.contracts`-tauluun
- lisää osapuolet `core.parties`-tauluun
- lisää sopimusasiakirjat `core.contract_documents`-tauluun
- lisää hinnat, maksuerät, yksikköhinnat, vakuudet ja vakuutukset `finance`-skeemaan
- lisää urakan sisällön, urakkarajat, tekniset vaatimukset, vastuut, luovutusaineistot ja aikataulut `domain`-skeemaan
- lisää laatuvaatimukset `quality`-skeemaan
- tallentaa canonical-version `core.canonical_versions`-tauluun

Tämä on pääasiallinen silta JSON-mallista relaatiotietokantaan.

### `src/cipp_contracts/load/link_contract_documents.py`

Linkittää sopimuksen asiakirjat alkuperäisiin lähdetiedostoihin.

Mitä se tekee:

- etsii projektin sopimuksen
- etsii sopimusasiakirjojen dokumenttityypit
- yhdistää ne `raw.source_files`-taulun lähdetiedostoihin
- huomioi myös yhteiset asiakirjat kuten YSE 1998 ja lait

Tämä vastaa kysymykseen: mikä tietokantaan ladattu sopimusasiakirja perustuu mihinkin alkuperäiseen tiedostoon?

### `src/cipp_contracts/load/load_markdown_sections.py`

Lataa markdown-asiakirjojen sisällön tietokannan dokumenttikerrokseen.

Mitä se tekee:

- lukee `data/extracted/<project>/markdown/`-kansion markdownit
- pilkkoo ne osioihin, myös lähdekohtaiset `Source N / Page N` -otsikot
- voi luoda puuttuvat `core.contract_documents`-rivit raw-lähteiden dokumenttityypeistä lipulla `--ensure-raw-documents`
- voi poistaa projektin vanhat sectionit ennen uutta latausta lipulla `--prune-missing-markdown`
- tallentaa lähdetiedoston, lähdetiedoston id:n, extractor-nimen ja extractor-statuksen `doc.sections.metadata`-kenttään silloin kun tiedot ovat saatavilla
- tallentaa osiot `doc.sections`-tauluun
- tallentaa hakukelpoisia katkelmia `doc.clauses`-tauluun
- käyttää fallback-logiikkaa, jos esimerkiksi yksikköhinnat löytyvät urakoitsijan tarjouksesta eivätkä omasta `unit_prices.md`-tiedostosta

Tämä mahdollistaa dokumenttisisällön kysymisen, haun ja analysoinnin.

## 12. KG: PostgreSQL-native knowledge graph

### `src/cipp_contracts/kg/build_knowledge_graph.py`

Rakentaa PostgreSQL:n sisäisen tietograafin olemassa olevista relaatiotauluista.

Mitä se tekee:

- varmistaa `kg`-skeeman olemassaolon migraatiosta `db/migrations/008_knowledge_graph.sql`
- varmistaa myös non-binding guidance -taulut migraatiosta `db/migrations/009_legal_guidance_documents.sql`
- lukee projektit, sopimukset, osapuolet, asiakirjat, dokumenttiosiot, ehdot, urakkasisällöt, viemärisegmentit, vaatimukset, maksuerät, vakuudet, vakuutukset, operatiiviset tapahtumat, vastaanotot ja havainnot
- lukee lisäksi `legal.guidance_documents`-, `legal.guidance_sections`- ja `legal.guidance_items`-rivit
- lukee myös valinnaiset `quality.inspections`- ja `quality.defects`-taulut, jos ne ovat kannassa olemassa
- muodostaa niistä `kg.entities`- ja `kg.relations`-rivit
- tallentaa jokaiselle entitylle tai relaatiolle lähdejäljen `kg.evidence`-tauluun
- toimii idempotentisti, eli sama ajo päivittää olemassa olevat solmut ja suhteet eikä monista niitä

Tämä builder ei käytä LLM:ää eikä arvaa puuttuvia suhteita. Jos suhteelle ei löydy rakenteista riviä tai lähdejälkeä, sitä ei rakenneta.

### `src/cipp_contracts/legal/import_guidance_pdf.py`

Tuo lakiosan alla käsiteltävän, mutta ei-sitovan asiantuntijaoppaan tietokantaan.

Nykyinen käyttötapa on Jari Virran `Taloyhtiön putkiremonttiopas`, joka luokitellaan näin:

- `source_type = expert_guidance`
- `authority_level = non_binding_guidance`
- `binding_status = not_binding_law`
- `legal_role = planning_and_decision_guidance`

Mitä se tekee:

- rekisteröi PDF:n `raw.source_files`-tauluun dokumenttityypillä `legal_guidance_pipe_renovation`
- purkaa sivut `raw.pages`-tauluun ja säilyttää sivunumerot
- tunnistaa päälukurakenteen `legal.guidance_sections`-tauluun
- poimii sääntöpohjaisesti `legal.guidance_items`-rivejä signaaleista kuten `kannattaa`, `pitää`, `on syytä`, `edellyttää`, `riski`, `soveltuu` ja `ei sovellu`
- luokittelee itemit process stage-, topic-, actor- ja item type -kenttiin
- tallentaa lakimaininnat `legal_cross_reference`-itemeiksi statuksella `mentioned_not_verified`

Tämä importer ei käytä LLM:ää eikä tee sitovia oikeudellisia väitteitä. Oppaan tarkoitus on antaa amatööritoimijalle prosessi- ja tarkistuslistaohjausta ennen kuin järjestelmä viittaa varsinaisiin lakeihin, YSE-ehtoihin, urakkasopimukseen tai tarjouspyyntöön.

## 13. Retrieve: käyttäjäkysymyksen aineistopaketti

### `src/cipp_contracts/retrieve/build_retrieval_packet.py`

Rakentaa lähdeperustaisen retrieval-paketin käyttäjän CIPP-aiheisesta kysymyksestä.

Tärkeä tuoterajaus:

- järjestelmä ei ole referenssiprojektien kyselybotti
- referenssiprojektit ovat sisäinen, anonymisoitu tietopohja
- käyttäjä kysyy omaa taloyhtiötään tai yleistä CIPP-sukitusurakkaa koskevan kysymyksen
- moduuli ei muodosta vielä lopullista agenttivastausta eikä kutsu LLM:ää

Mitä se tekee:

- tunnistaa kysymyksestä aiheen deterministisesti, esimerkiksi maksuerät, urakkarajat, JV/SV-segmentit, videotarkastuksen, vastaanoton, takuun tai lisätyöt
- tunnistaa myös expert guidance -kysymykset, kuten hankesuunnittelu, yhtiökokous, hallitus, osakkaat, kuntotutkimus, koejyrsintä, pinnoitus, sukitusvaihtoehdot, turvallisuuskoordinaattori ja kosteudenhallinta
- tallentaa käyttäjän taloyhtiön vihjeet `user_case`-osioon, esimerkiksi asuntojen määrän, pystylinjojen määrän ja pohjaviemärin mukanaolon
- hakee aiheen mukaiset `kg.entities`-solmut ja 1-hop `kg.relations`-suhteet
- hakee `kg.evidence`-rivit
- hakee evidencen perusteella `doc.sections`-, `doc.clauses`- ja `raw.pages`-tekstikatkelmat
- painottaa JV/SV-, urakkaraja- ja scope-kyselyissä domain-entityjä kuten `sewer_segment`, `scope_item`, `boundary`, `technical_requirement`, `quality_requirement` ja `responsibility`
- käyttää tekstikontekstin fallback-ketjua: clause -> section -> raw.page -> source_file pages -> entity source -> topic fallback
- kertoo coverage-tilan kentällä `evidence_coverage_status`: `ok`, `partial`, `weak` tai `no_text_context`
- merkitsee entity-, relation- ja evidence-riveille `text_context_status`-arvon, kuten `direct_clause`, `direct_section`, `direct_page`, `source_file_page`, `entity_source_fallback`, `topic_text_fallback` tai `missing`
- anonymisoi referenssien käytön `reference_001`-tyyppisiksi sisäisiksi lähteiksi
- palauttaa guidance-lähteet asiantuntijaohjeina, ei lakilähteinä
- palauttaa JSON- ja Markdown-muotoisen retrieval-paketin

Tämä on v0.5.0-kehityslinjan retrieval-vaihe. Se ei ole vielä agenttivastaus: myöhempi hybrid RAG / GraphRAG -vastauslogiikka käyttää tätä pakettia vastauksen aineistona.

### `src/cipp_contracts/retrieve/report_retrieval_smoke_matrix.py`

Rakentaa retrieval smoke matrix -raportin ennen mahdollista `v0.5.0`-releaseä.

Mitä se tekee:

- ajaa 10 vakioitua CIPP-aihetta nykyisen `build_retrieval_packet.py`-logiikan läpi
- aiheet ovat maksuerät, JV, SV, urakkarajat, videotarkastus, vastaanotto, takuu, vakuudet/vakuutukset, lisätyöt/yksikköhinnat ja puutteet/reklamaatiot
- optiona `--include-guidance-topics` lisää 10 putkiremonttioppaan prosessiohjauksen smoke-kysymystä
- mittaa per aihe `retrieval_status`-, `evidence_coverage_status`-, tekstikonteksti-, evidence- ja reference usage -luvut
- antaa jokaiselle aiheelle `topic_status`-arvon: `pass`, `partial` tai `fail`
- laskee matrix-tason `release_candidate`-arvon
- tekee pattern-pohjaisen anonymisoinnin smoke checkin Markdown-outputille

`partial` voi olla hyväksyttävä esimerkiksi videotarkastus-, vastaanotto- tai takuuaiheessa, jos aihe ei kaadu, evidence löytyy osittain ja raportti kertoo syyn. `fail` estää release candidate -tilan.

## 14. Answer: lähdeperustainen vastausrunko

### `src/cipp_contracts/answer/compose_answer.py`

Muodostaa retrieval-paketista lyhyen, kontrolloidun lähdeperustaisen vastauksen.

Mitä se tekee:

- lukee valmiin retrieval-paketin tai rakentaa sen kysymyksestä
- valitsee tärkeimmät lähdekatkelmat prioriteetilla: `direct_clause`, `direct_section`, `direct_page`, `source_file_page`, `entity_source_fallback`, `topic_text_fallback`
- muodostaa JSON- ja Markdown-vastauksen ilman LLM-kutsua
- käyttää topic-kohtaisia kevyitä runkoja esimerkiksi maksuerille, JV/SV-laajuudelle, urakkarajoille, videotarkastukselle, vastaanotolle, takuulle, vakuuksille, lisätöille ja reklamaatioille
- näyttää `missing_user_case_fields`-kentän käyttäjälle näkyvinä puuttuvina tietoina
- näyttää epävarmuudet, jos retrieval tai evidence coverage ei ole täysin kunnossa
- näyttää lähteet vain anonymisoituina `reference_001`-tyyppisinä viitteinä
- merkitsee expert guidance -lähteet lähdeluokalla `expert_guidance`
- käyttää retrievalin sanitointisääntöjä ja redaktoi myös varomattomat rahamäärät vastauksista

`answer_status` voi olla:

- `answered`: retrieval ja evidence coverage ovat kunnossa, ja lähdekatkelmia löytyi
- `partial`: lähteitä löytyi, mutta retrieval tai coverage jäi osittaiseksi
- `insufficient_evidence`: lähdekatkelmia ei ole riittävästi turvalliseen vastaukseen

Tämä moduuli ei ole täysi agentti. Se ei keskustele, suunnittele uutta tiedonhakua eikä muodosta vapaata LLM-vastausta. `generation_mode` on `deterministic_source_grounded` ja `llm_used` on aina `false`.

Kun vastaus perustuu asiantuntijaoppaaseen, composer käyttää muotoa “Asiantuntijaohjeen perusteella” eikä “laki määrää”. Se lisää epävarmuuden siitä, että sitova oikeudellinen tulkinta pitää varmistaa varsinaisesta lakitekstistä, yhtiöjärjestyksestä, sopimuksesta tai asiantuntijalta.

### `src/cipp_contracts/answer/report_answer_smoke_matrix.py`

Rakentaa answer composer smoke matrix -raportin ennen mahdollista `v0.6.0`-releaseä.

Mitä se tekee:

- ajaa 20 vakioitua kysymystä `cipp-compose-answer`-logiikan läpi
- 10 aihetta ovat core CIPP -aiheita: maksuerät, JV, SV, urakkarajat, videotarkastus, vastaanotto, takuu, vakuudet/vakuutukset, lisätyöt/yksikköhinnat ja puutteet/reklamaatiot
- 10 aihetta ovat legal guidance -aiheita: hankesuunnittelu, hallituksen valmistelu, osakkaiden kysymykset, kuntotutkimus, pinnoituksen riskit, sukituksen soveltuvuus, yhtiökokouspäätökset, vastaanotto/takuu, viranomaisvelvoitteet ja amatööritoimijan tarjouspyyntövalmistelu
- tarkistaa, että `llm_used` on aina `false`
- tarkistaa Markdown-outputin anonymisointi- ja polkuturvallisuuden
- tarkistaa, että expert guidance -aineistoa ei esitetä sitovana lakina
- ajaa kevyen hallucination guardin euroille, prosenteille, pitkille opaskatkelmille ja raakadataviitteille
- laskee per aihe `pass`, `partial` tai `fail` -tilan sekä matrix-tason `release_candidate`-arvon

Tämä eroaa retrieval smoke matrixista: retrieval-portti testaa löydetäänkö aineisto; answer-portti testaa syntyykö siitä turvallinen käyttäjälle näytettävä lähdevastaus. Tämäkään moduuli ei käytä LLM:ää.

## 15. Validate: laadunvarmistus

### `src/cipp_contracts/validate/validate_canonical_contract.py`

Validoi canonical JSON -tiedoston ennen tietokantaan lataamista.

Se tarkistaa esimerkiksi:

- puuttuuko pakollisia pääavaimia
- puuttuuko pakollisia asiakirjatyyppejä
- onko asiakirjoilla päällekkäisiä pätevyysjärjestyksiä
- löytyykö osapuolilta tarvittavat nimet ja roolit
- täsmäävätkö maksuerät sopimushintaan
- löytyykö tekstistä sähköposteja tai puhelinnumeroita, joita ei pitäisi jäädä näkyviin

Validointi ei ratkaise kaikkea, mutta se estää pahimmat rakenteelliset virheet ennen latausta.

## 16. Price: JV-hinta-arvio

### `src/cipp_contracts/price/estimate_jv_price.py`

Laskee käyttäjän antaman taloyhtiön JV-urakan hinta-arvion.

Tärkeä vastausperiaate:

1. Ensin haetaan tietokannasta kaikki saatavilla olevat referenssiprojektit.
2. Järjestelmä valitsee lähimmän oman referenssikohteen.
3. Jos sopivaa referenssiä ei löydy, käytetään Referenssikohde Aa oletuksena.
4. Hinta-arvio muodostetaan käyttäjän kohteen ja referenssin suhteesta.

Nykyinen nyrkkisääntö:

- asuntojen määrä selittää 70 prosenttia hinnasta
- pystylinjojen määrä 10 prosenttia
- pohjaviemärin koko ja pituus 10 prosenttia
- tonttiviemärin koko ja pituus 10 prosenttia

Lisäksi käytetään kokemusperäistä haarukkaa:

- kokonais-JV-urakka parhailla materiaaleilla on usein noin 5000-8000 euroa per asunto
- pieni kohde liikkuu lähemmäs 8000 euroa per asunto
- Referenssikohde A on default-referenssi hyvin onnistuneesta limisukitusurakasta

Moduuli voi myös tallentaa arvion `finance.price_estimates`-tauluun.

## 17. Embed ja search

### `src/cipp_contracts/embed/`

Tämä kansio on varattu embedding- ja vektorointilogiikalle. Tietokannassa on jo `rag.embeddings` ja pgvector käytössä, mutta varsinainen embedding-putki on vielä kehitettävä.

Tuleva rooli:

- ottaa `rag.chunks` tai `doc.clauses` -tekstit
- muodostaa embeddingit
- tallentaa ne `rag.embeddings`-tauluun
- mahdollistaa semanttinen haku

### `src/cipp_contracts/search/`

Tämä kansio on varattu hakukerrokselle. SQL-puolella on jo full text -hakukysely `db/queries/search_full_text.sql`.

Tuleva rooli:

- yhdistää full text -haku ja vektorihaku
- hakea vastaukselle lähdekatkelmat
- tukea CIPP-kysymys-vastauslogiikkaa

## 18. SQL-kyselyt

### `db/queries/search_full_text.sql`

Tekee suomenkielisen ja yksinkertaisen full text -haun `rag.chunks`-taulusta.

Käyttö: kun halutaan löytää dokumenttikatkelmia käyttäjän kysymykseen ilman embedding-hakua.

### `db/queries/payment_schedule_total.sql`

Laskee sopimuksen maksuerien summat.

Käyttö: tarkistaa täsmäävätkö maksuerät sopimuksen kokonaishintaan.

### `db/queries/document_precedence.sql`

Listaa sopimuksen asiakirjat pätevyysjärjestyksessä.

Käyttö: kun pitää ratkaista, mikä asiakirja menee toisen edelle ristiriitatilanteessa.

### `db/queries/contractor_obligations.sql`

Listaa urakoitsijan velvoitteet.

Käyttö: kun halutaan vastata kysymyksiin tyyliin "mitä urakoitsijan pitää tehdä" tai "mikä näyttö vaaditaan".

### `db/queries/compare_sewer_segments.sql`

Listaa projektien JV/SV-segmentit vertailtavassa järjestyksessä.

Käyttö: kun vertaillaan projektien laajuutta yläjuoksulta alajuoksulle.

### `db/queries/kg_project_graph.sql`

Näyttää yhden projektin KG-suhteet luettavana edge-listana.

### `db/queries/kg_entity_neighborhood.sql`

Näyttää yhden entityn lähisuhteet kumpaankin suuntaan.

### `db/queries/kg_relation_evidence.sql`

Näyttää relaation ja siihen liittyvän evidencen.

### `db/queries/kg_project_readiness_summary.sql`

Tiivistää projektikohtaisesti KG-solmut, suhteet ja evidence-kattavuuden.

### `db/queries/retrieval_entity_search.sql`

Hakee kysymyksen aiheeseen sopivia KG-entityjä entity-tyyppien ja avainsanojen avulla.

### `db/queries/retrieval_kg_neighborhood.sql`

Hakee valittujen entityjen 1-hop KG-naapuruston.

### `db/queries/retrieval_evidence_context.sql`

Hakee valittujen entityjen ja relaatioiden evidence-rivit.

### `db/queries/retrieval_user_case_candidates.sql`

Auttaa myöhemmin etsimään käyttäjän taloyhtiön tietoihin lähimpiä sisäisiä vertailukohteita.

## 19. Komentorivityökalut

`pyproject.toml` määrittää nämä komennot, kun paketti on asennettu kehitystilaan.

### `cipp-inventory-source-files`

Inventoi lähdetiedostot tietokantaan.

Tyypillinen käyttö:

```powershell
cipp-inventory-source-files --project-code reference_001 --source-dir data/raw/reference_001
```

### `cipp-extract-pdf-pages`

Purkaa PDF-sivut tekstiksi.

```powershell
cipp-extract-pdf-pages --project-code reference_001 --output-dir data/extracted/reference_001/pages
```

### `cipp-build-markdown`

Muodostaa markdown-asiakirjat PDF-sivuista.

```powershell
cipp-build-markdown --project-code reference_001 --output-dir data/extracted/reference_001/markdown
```

### `cipp-build-canonical`

Luo tyhjän canonical JSON -pohjan.

```powershell
cipp-build-canonical --project-code reference_001 --output data/normalized/reference_001/canonical.json
```

### `cipp-build-project-canonical`

Rakentaa canonical JSON -mallin projektin markdown-/tietokantasisällöstä.

```powershell
cipp-build-project-canonical --project-code reference_001 --output data/normalized/reference_001/canonical.json
```

### `cipp-enrich-canonical`

Rikastaa canonical JSON -mallia markdownista. Tämä on hyödyllinen erityisesti vanhemman Referenssikohde A-putken kanssa.

```powershell
cipp-enrich-canonical --input data/normalized/reference_001/canonical.json --markdown-dir data/extracted/reference_001/markdown --output data/normalized/reference_001/canonical.enriched.json
```

### `cipp-validate-canonical`

Validoi canonical JSON -tiedoston.

```powershell
cipp-validate-canonical --input data/normalized/reference_001/canonical.json --report data/reports/reference_001.validation.json
```

### `cipp-load-contract`

Lataa canonical JSON -sopimuspaketin tietokantaan.

```powershell
cipp-load-contract --input data/normalized/reference_001/canonical.json
```

### `cipp-link-contract-documents`

Linkittää sopimusasiakirjat alkuperäisiin lähdetiedostoihin.

```powershell
cipp-link-contract-documents --project-code reference_001
```

### `cipp-load-markdown-sections`

Lataa markdown-osiot ja tekstikatkelmat tietokantaan.

```powershell
cipp-load-markdown-sections --project reference_001 --input data/extracted/reference_001/markdown --ensure-raw-documents --prune-missing-markdown
```

### `cipp-import-finlex-legal-xml`

Tuo lakiaineiston Finlex XML -lähteestä.

```powershell
cipp-import-finlex-legal-xml --source-dir data/raw/Rakentamisen_Lait
```

### `cipp-report-processing-quality`

Kirjoittaa käsittelyn laaturaportin. Raportti erottaa viimeisimmän onnistuneen tai epäonnistuneen ajon historiallisista audit-merkinnöistä.

```powershell
cipp-report-processing-quality --output data/reports/processing_quality_report.md
```

### `cipp-report-reference-facts`

Kirjoittaa referenssiprojektien vertailufaktamatriisin Markdown- ja CSV-muotoon.

```powershell
cipp-report-reference-facts --output-md data/reports/reference_facts_matrix.md --output-csv data/reports/reference_facts_matrix.csv
```

Raportin `kg_readiness_status` tarkoittaa:

- `ready`: tekstikerros ja keskeiset faktat ovat kunnossa ja evidence on riittävän vahvaa.
- `needs_review`: osa tiedoista puuttuu, evidence on heikkoa tai hinta-/maksuerävertailu vaatii tarkistusta.
- `not_ready`: tekstikerros tai keskeinen faktapohja puuttuu niin, ettei graafikerrosta saa vielä aloittaa.

`needs_review` muuttuu `ready`-tilaksi, kun `blocking_missing_fields` ja `blocking_weak_evidence_fields` tyhjenevät. Blokkaavia kenttiä ovat esimerkiksi `apartments_count`, `jv_verticals_count`, `jv_scope_summary`, `bottom_drain_scope`, `yard_line_scope`, `contract_price`, `quality_requirements_available`, `video_inspection_available`, `handover_or_reception_available` ja `warranty_notes_available`. Raportti näyttää myös `kg_readiness_reasons`-kentässä, miksi projekti on `ready`, `needs_review` tai `not_ready`.

Maksuerät ovat oma tarkistuskerroksensa, koska maksuerätaulukko voi löytyä eri projekteissa eri dokumenttityypistä. `cipp-report-reference-facts` käyttää `payment_schedule_facts`-moduulia, joka etsii maksueriä ensin `finance.payment_schedule_items`-taulusta ja sen jälkeen `core.contract_documents`-, `doc.sections`-, `doc.clauses`- ja `raw.pages`-kerroksista. Discovery huomioi esimerkiksi maksuerätaulukot, urakkasopimukset, tarjoukset, sopimusehdot, liitteet, taloudelliset loppuselvitykset ja projektinhallintataulukot.

Kun rivit löytyvät luotettavasti, ne tallennetaan idempotentisti `finance.payment_schedule_items`-tauluun ja niiden summa hyväksytään, jos se vastaa sopimushintaa enintään yhden euron pyöristystoleranssilla. Kaikissa projekteissa ei ole yhtä maksuerätaulukkoa: erillinen lasku- ja hyväksyntäkansio käsitellään invoice-based payment schedule -mallina, jossa erilliset laskut ja hyväksyntädokumentit voidaan koostaa samoiksi maksueräriveiksi.

Raportti näyttää erotuksen kentissä `payment_schedule_difference` ja `payment_schedule_difference_pct`. `payment_schedule_evidence_status` kertoo tilan: `structured_and_matches`, `structured_but_mismatch`, `invoice_documents_structured`, `invoice_documents_found_unstructured`, `found_unstructured` tai `not_found`. `found_unstructured` ja `invoice_documents_found_unstructured` jäävät `needs_review`-tilaan, koska taulukko, laskut tai maksuerämaininnat löytyvät mutta rivejä ei vielä voida poimia luotettavasti. `not_found` tarkoittaa ennen kaikkea discovery-logiikan puutetta. `next_blocker` näyttää ensimmäisen seuraavaksi korjattavan portin.

PostgreSQL-native KG voidaan rakentaa olemassa olevista rakenteisista riveistä, mutta GraphRAG-/LLM-vastauskäyttöä ei aloiteta ennen tätä porttia, koska muuten vastaus voisi näyttää valmiilta mutta sisältää puuttuvia tai heikosti todistettuja urakkafaktoja.

### `cipp-build-knowledge-graph`

Rakentaa PostgreSQL-native KG-kerroksen.

```powershell
cipp-build-knowledge-graph --all --dry-run
cipp-build-knowledge-graph --all
cipp-build-knowledge-graph --project-code reference_001 --prune
```

`--dry-run` tarkistaa rakentamisen ilman kirjoituksia. `--prune` poistaa valitun projektin vanhat KG-solmut ennen uudelleenrakennusta. `--all` rakentaa kaikki kannassa olevat referenssiprojektit.

### `cipp-import-legal-guidance-pdf`

Tuo ei-sitovan asiantuntijaoppaan legal guidance -kerrokseen.

```powershell
cipp-import-legal-guidance-pdf --file data/raw/legal_guidance/virta_putkiremonttiopas_2020/Putkiremonttiopas_4p_lores.pdf --document-code putkiremonttiopas_virta_2020 --title "Taloyhtiön putkiremonttiopas" --author "Jari Virta" --publisher "Kiinteistöalan Kustannus Oy" --publication-year 2020 --edition "4. painos"
```

Komento kirjoittaa `raw.source_files`, `raw.pages`, `legal.guidance_documents`, `legal.guidance_sections` ja `legal.guidance_items` -kerroksiin. `--dry-run` purkaa ja luokittelee aineiston mutta rollbackaa tietokantamuutokset. Raportteihin ei kirjoiteta pitkiä tekijänoikeudellisia katkelmia.

### `cipp-build-retrieval-packet`

Rakentaa käyttäjän CIPP-kysymykselle JSON- ja Markdown-muotoisen retrieval-paketin.

```powershell
cipp-build-retrieval-packet --question "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?" --output data/reports/retrieval_packet.json --output-md data/reports/retrieval_packet.md
cipp-build-retrieval-packet --question "Mitä pitää huomioida taloyhtiön JV-pystylinjojen ja pohjaviemärin sukituksessa?" --apartments-count 30 --jv-verticals-count 8 --includes-bottom-drain true --output data/reports/retrieval_packet_jv.json --output-md data/reports/retrieval_packet_jv.md
```

Komento ei vastaa käyttäjän puolesta, vaan palauttaa aineiston. Se ei käytä referenssiprojektikoodia normaalina hakukohteena. `--debug-reference-project-code` on vain kehittäjän tarkistusta varten.

### `cipp-report-retrieval-smoke-matrix`

Kirjoittaa retrieval smoke matrix -raportin.

```powershell
cipp-report-retrieval-smoke-matrix --output data/reports/retrieval_smoke_matrix.json --output-md data/reports/retrieval_smoke_matrix.md
cipp-report-retrieval-smoke-matrix --include-guidance-topics --output data/reports/retrieval_smoke_matrix_guidance.json --output-md data/reports/retrieval_smoke_matrix_guidance.md
```

Tämä on v0.5.0-ehdokkuuden portti. Raportti ei muodosta agenttivastausta, vaan kertoo ovatko ydinkysymysten retrieval-polut riittävän valmiita.

### `cipp-compose-answer`

Muodostaa retrieval-paketista kontrolloidun lähdeperustaisen vastauksen.

```powershell
cipp-compose-answer --question "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?" --output data/reports/answer_payment.json --output-md data/reports/answer_payment.md
cipp-compose-answer --retrieval-packet data/reports/retrieval_packet.json --output data/reports/answer.json --output-md data/reports/answer.md
```

Komento voi joko lukea valmiin retrieval-paketin tai rakentaa sen ensin kysymyksestä. Se ei kutsu LLM:ää eikä muodosta väitteitä ilman retrieval-paketin lähdekatkelmia. Outputin `answer_status` on `answered`, `partial` tai `insufficient_evidence`.

### `cipp-report-answer-smoke-matrix`

Kirjoittaa answer composer smoke matrix -raportin.

```powershell
cipp-report-answer-smoke-matrix --output data/reports/answer_smoke_matrix.json --output-md data/reports/answer_smoke_matrix.md
```

Tämä on `v0.6.0`-ehdokkuuden portti. Raportti ei ole agenttivastaus, vaan se tarkistaa että 20 core/guidance-aiheen vastaukset ovat lähdeperustaisia, anonymisoituja, LLM-vapaita ja expert guidance -aineiston osalta ei-sitovasti muotoiltuja.

### `cipp-run-dev-api`

Käynnistää paikallisen FastAPI-kehityspalvelun selain-playgroundia varten.

```powershell
cipp-run-dev-api --host 127.0.0.1 --port 8000
```

API:n endpointit ovat:

- `GET /api/health`: palvelun tila, `llm_enabled=false`
- `GET /api/app-config`: frontendin kentät, oletusarvot, topicit ja UI-labelit
- `GET /api/suggested-questions`: valmiit testikysymykset core- ja guidance-aiheille
- `POST /api/answer`: rakentaa retrieval-paketin ja ajaa sen `compose_answer`-funktion läpi

API ei sisällä omaa rinnakkaista CIPP-päättelyä. Se käyttää nykyisiä `retrieve`- ja `answer`-kerroksia ja lisää vain paikallisen HTTP-rajapinnan, request id:n, keston ja viimeisen sanitointivahdin. `include_debug=true` voi palauttaa lyhyen debug-paketin, mutta raakadataa, tiedostopolkuja, oikeita projektinimiä tai henkilötietoja ei pidä palauttaa.

## 19.1 Paikallinen frontend playground

`apps/web` on Vite + React + TypeScript -käyttöliittymä paikalliseen testaukseen. Se ei ole SaaS-tuote eikä sisällä kirjautumista, maksamista, käyttäjähallintaa tai multi-tenant-arkkitehtuuria.

Käynnistys:

```powershell
cd apps/web
npm install
npm run dev
```

Oletus-API:

```text
http://127.0.0.1:8000
```

Frontendin pääosat:

- `apps/web/src/App.tsx`: kokoaa playgroundin tilan, kyselyn ja vastauksen.
- `apps/web/src/api/client.ts`: kutsuu `/api/app-config`, `/api/suggested-questions` ja `/api/answer`.
- `apps/web/src/components/TopCaseBar.tsx`: taloyhtiön perustiedot ja toggle-parametrit.
- `apps/web/src/components/QuestionPanel.tsx`: keskustelumainen kysymyskenttä ja debug-toggle.
- `apps/web/src/components/AnswerCard.tsx`: lyhyt vastaus, key points, lähteisiin perustuvat huomiot ja jatkokysymykset.
- `apps/web/src/components/SourcesPanel.tsx`: anonymisoidut lähteet ja sanitisoidut katkelmat.
- `apps/web/src/components/UncertaintyPanel.tsx`: puuttuvat käyttäjätiedot, epävarmuudet ja varoitukset.
- `apps/web/src/components/StatusBadges.tsx`: `answered/partial/insufficient_evidence`, `llm_used=false`, `source_grounded` ja `expert_guidance`.
- `apps/web/src/styles.css`: hillitty moderni käyttöliittymätyyli.
- `apps/web/playwright.config.ts`: käynnistää Viten ja ajaa frontend smoke-testin mock API -tilassa.
- `apps/web/tests/frontend-smoke.spec.ts`: varmistaa selaimessa, että yläpalkki, kysymys, vastaus, lähteet, epävarmuudet, debug ja sanitointi toimivat.
- `docs/frontend_testing.md`: manuaalinen live API- ja mock API -testauslista.
- `scripts/run_frontend_dev.ps1`: tulostaa paikallisen backend/frontend-käynnistysohjeen.

Yläpalkin parametrit lähetetään aina API:iin `user_case`-osiossa. Tällä testataan nopeasti, miten esimerkiksi asuntojen määrä, JV-pystylinjat, pohjaviemäri, tonttilinja, sadevesilinjat, kattokaivot, videotarkastus ja yksikköhinnat vaikuttavat puuttuviin tietoihin, epävarmuuksiin ja retrievalin painotukseen.

Tärkeä rajaus: frontend näyttää vastauksen, jonka source-grounded composer muodostaa. Se ei kutsu LLM:ää eikä saa näyttää referenssiprojektien oikeita nimiä tai raakaa tiedostopolkuja.

Mock API -tila käynnistyy joko URL-parametrilla `?mock=1` tai frontendin paikallisella `VITE_USE_MOCK_API=true` -asetuksella. Mock-vastaus on tarkoitettu vain UI:n nopeaan testaukseen; live-testissä käytetään `cipp-run-dev-api`-palvelua ja oikeaa PostgreSQL-tietopohjaa.

## 20. Tyypillinen uuden projektin käsittely

Kun uusi hanke lisätään, tavoite on saada se samaan vertailukelpoiseen muotoon kuin aiemmat hankkeet.

Tyypillinen eteneminen:

1. Siirrä alkuperäiset asiakirjat `data/raw/<project_code>/`-kansioon.
2. Aja lähdetiedostojen inventointi.
3. Pura PDF-sivut.
4. Rakenna markdownit.
5. Rakenna canonical JSON.
6. Validoi canonical JSON.
7. Lataa canonical JSON tietokantaan.
8. Linkitä sopimusasiakirjat lähdetiedostoihin.
9. Lataa markdown-osiot ja tekstikatkelmat.
10. Synkronoi tarjouspyyntöfaktat.
11. Tuo mahdolliset kokous-, vastaanotto-, lisätyö-, maksu- ja takuutiedot operatiiviseen kerrokseen.
12. Tarkista projektin vertailukelpoisuus SQL-kyselyillä.

Tärkeä periaate: kaikissa projekteissa ei ole samaa asiakirjakokonaisuutta, mutta samat olennaiset tiedot pyritään löytämään eri lähteistä. Tarjouspyyntö on yleensä paras lähde teknisille perustiedoille.

## 21. Projektien vertailukelpoisuus

Vertailukelpoisuus syntyy kolmesta asiasta:

1. Asiakirjat luokitellaan samoilla `document_type`-koodeilla.
2. Urakan sisältö normalisoidaan samoihin domain-tauluihin.
3. Kiinteistö- ja laajuustiedot puretaan samoihin kenttiin.

Esimerkki:

- Referenssikohde Assa urakkasopimus voi antaa hinnan ja maksuerät.
- Toisessa projektissa tarjouspyyntö voi antaa asuntojen määrän ja pystylinjat.
- Kolmannessa projektissa kokouspöytäkirjat voivat kertoa lisätöistä ja toteutuneista ongelmista.

Järjestelmän tehtävä on saada nämä eri lähteistä tulevat tiedot samaan rakenteeseen, jotta kysymykset voidaan vastata vertaamalla projekteja eikä vain lukemalla yksittäistä PDF:ää.

## 22. Tärkeimmät CIPP-käsitteet repossa

### JV-linjat

Jätevesiviemärit mallinnetaan virtaussuunnassa:

1. asuntohajotukset
2. pystylinjat
3. pohjaviemäri
4. tonttilinja

Tällä on suora hinnallinen merkitys.

### SV-linjat

Sadevesilinjat jakautuvat kahteen päätilanteeseen:

1. sadevesi kerätään pihakaivoista maan alla oleviin SV-tonttilinjoihin
2. sadevesi kerätään myös katolta, jolloin mukana voi olla kattokaivoja, SV-pystylinjoja ja SV-pohjaviemäri

Katolta kerättävä sadevesi kasvattaa työtä ja hintaa selvästi.

### Videotarkastus

Videotarkastus tarkoittaa valmiin sukitetun JV- tai SV-linjan kuvausta ja valvojan tekemää tarkastusta.

Sen merkitys:

- osoittaa työn laadun valmistumishetkellä
- tuottaa havaintoja vastaanottoon
- toimii lähtötietona 2-vuotistakuutarkastuksessa
- auttaa päättämään, pitääkö jotain korjata takuumielessä

### Vastaanotto

Vastaanotto on hetki, jossa urakoitsija luovuttaa työmaan takaisin taloyhtiön vastuulle. Tämä on operatiivisesti erittäin tärkeä vaihe, koska siinä kirjataan:

- hyväksytäänkö työ
- mitä puutteita jää
- mitä dokumentteja luovutetaan
- mitä maksueriä voidaan hyväksyä
- mitä takuuajan asioita seurataan

## 23. Testit

### `tests/test_validate_canonical_contract.py`

Varmistaa, että uusi canonical-pohja on riittävän validi ja että päällekkäinen asiakirjojen pätevyysjärjestys havaitaan virheeksi.

### `tests/test_rfq_facts.py`

Varmistaa, että tarjouspyyntöparseri löytää eri hankkeistä oikeita perustietoja.

Testatut hankkeet:

- Referenssikohde D
- Referenssikohde C
- Referenssikohde E
- Referenssikohde F

### `tests/test_estimate_jv_price.py`

Varmistaa JV-hinta-arvion peruslogiikan:

- Referenssikohde A toimii oletusreferenssinä
- pieni taloyhtiö liikkuu lähemmäs korkeaa euroa/asunto-hintaa
- lähin sisäinen referenssi valitaan ennen oletusreferenssiä

### `tests/eval_questions/reference_001.jsonl`

Sisältää ensimmäiset arviointikysymykset Referenssikohde An aineistolle. Näiden avulla voidaan myöhemmin testata, osaako hakukerros löytää oikean lähdeasiakirjan.

## 24. Mitä tiedostoja yleensä muokataan?

Kun lisätään uusi hanke:

- lisätään aineisto `data/raw/<project_code>/`
- ajetaan extract/normalize/load-komennot
- tarvittaessa parannetaan parseria `src/cipp_contracts/normalize/`
- tarvittaessa lisätään uusi document type migraatioon
- lisätään testejä, jos parseriin tulee uutta logiikkaa

Kun lisätään uusi tietokantakäsite:

- lisätään migraatio `db/migrations/00x_....sql`
- päivitetään latauskoodi `src/cipp_contracts/load/`
- päivitetään normalisointi `src/cipp_contracts/normalize/`
- lisätään kysely tai testi, jos käsitteellä tehdään analytiikkaa

Kun parannetaan käyttäjän kysymyksiin vastaamista:

- parannetaan dokumenttien pilkkomista `load_markdown_sections.py`
- rakennetaan embedding-putkea `embed/`
- rakennetaan hakukerrosta `search/`
- lisätään eval-kysymyksiä `tests/eval_questions/`

## 25. Mitä ei yleensä muokata käsin?

Näitä ei yleensä kannata muokata käsin:

- `.venv/`
- `.pytest_cache/`
- `.ruff_cache/`
- `__pycache__/`
- Dockerin tietokantavolyymi
- koneellisesti tuotetut sivu-JSONit, ellei korjata kokeellista välitulosta

Canonical JSONia voi tarkistaa käsin, mutta pitkällä aikavälillä tavoitteena on, että se syntyy mahdollisimman paljon parserien ja importerien kautta.

## 26. Nykyiset tunnetut kehityskohdat

### Operatiivinen importer pitää vakioida

Referenssikohde Bn, Referenssikohde An ja Referenssikohde Cn lisäaineistot osoittivat, että työmaan kokoukset, vastaanotto, lisätyöt, maksut ja käytännön ongelmat ovat erittäin arvokkaita.

Seuraava hyvä tekninen askel on tehdä virallinen importer esimerkiksi:

```text
src/cipp_contracts/extract/import_project_operations.py
```

ja sille oma migraatio:

```text
db/migrations/007_project_operations.sql
```

Silloin operatiivinen data ei jää käsin luoduksi tietokantarakenteeksi.

### Redaktointi pitää yleistää

`build_markdown.py` tekee jo henkilötietojen poistoa, mutta siinä on vielä projektikohtaista logiikkaa. Parempi ratkaisu on yleinen redaktiokerros, joka toimii kaikille hankkeille samalla tavalla.

### Vanha ja uusi canonical-rikastus pitää yhdistää

`enrich_canonical_from_markdown.py` sisältää paljon arvokasta Referenssikohde A-tulkintaa, mutta `build_project_canonical.py` on yleisempi usean projektin malli.

Pitkällä aikavälillä paras ratkaisu on siirtää arvokkaat tulkintasäännöt yleiseen rakentajaan ja vähentää projektikohtaista koodia.

### Embedding- ja hakukerros puuttuu vielä

Tietokanta tukee jo pgvectoria, mutta varsinainen embedding-generointi ja semanttinen haku pitää vielä toteuttaa.

### `.doc`-, `.docx`-, `.xls`- ja muut toimistotiedostot

PDF-putki on selkein. Jos projektien lisäaineistoissa on Word- tai Excel-tiedostoja, niille tarvitaan oma luotettava tekstin- ja taulukonpurku, jotta kokous-, vastaanotto- ja maksutiedot saadaan sisään yhtä hyvin kuin PDF:stä.

## 27. Miten repo toimii käyttäjän kysymyksen kannalta?

Kun käyttäjä kysyy esimerkiksi:

```text
Paljonko meidän taloyhtiön kaikkien JV-linjojen CIPP-urakka maksaisi?
```

Järjestelmän pitäisi edetä näin:

1. Käyttäjän kohteen tiedot tallennetaan `user_case`-vihjeiksi.
2. Kysymyksestä tunnistetaan CIPP-aihe, esimerkiksi hinta, maksuerät, JV/SV-segmentit, urakkarajat tai laatu.
3. `retrieve` hakee KG:stä aiheen kannalta relevantit entityt ja suhteet.
4. `kg.evidence` linkittää löydökset `doc.sections`-, `doc.clauses`- ja `raw.pages`-teksteihin.
5. Retrieval-paketti kertoo mitä tietoja puuttuu tarkempaa arviota varten.
6. `answer` muodostaa lyhyen deterministic source-grounded -vastauksen vain retrieval-paketin aineistosta.

Kun käyttäjä kysyy esimerkiksi:

```text
Linjassa on jyijyä, mitä pitää tehdä?
```

Retrieval-paketin pitäisi hakea:

1. operatiiviset havainnot aiemmista projekteista
2. kokouspöytäkirjat ja vastaanottodokumentit
3. laatuvaatimukset ja videotarkastuskommentit
4. sopimus- ja YSE-tason vastuut
5. vastaavat ratkaisut aiemmista hankkeista

Tavoite ei ole kysyä yksittäistä referenssiprojektia, vaan käyttää referenssejä sisäisenä, anonymisoituna tietopohjana: mitä vastaavissa tilanteissa on dokumentoitu, kuka vastasi, millä perusteella ja miten asia vietiin evidenceen.

## 28. Ytimeen tiivistettynä

Repo rakentaa CIPP-urakoista vertailukelpoisen tietokannan.

Tärkein ajatus on tämä:

- `data/raw` säilyttää alkuperäiset asiakirjat
- `raw` todistaa mistä tieto tuli
- `core` kertoo mikä hanke ja sopimus on kyseessä
- `doc` säilyttää asiakirjatekstin analysoitavassa muodossa
- `domain` muuttaa urakan sisällön CIPP-käsitteiksi
- `finance` mallintaa hinnat ja maksut
- `quality` mallintaa laadun, tarkastukset ja takuun
- `ops` mallintaa oikean työmaan tapahtumat
- `kg` mallintaa faktat ja suhteet todistettavana verkostona
- `retrieve` kokoaa käyttäjäkysymyksen aineistopaketin
- `rag` mahdollistaa hakemisen ja myöhemmin kysymys-vastausjärjestelmän

Kun nämä kerrokset ovat kunnossa, uusi taloyhtiö voidaan käsitellä lähdeperustaisesti aiempien todellisten hankkeiden pohjalta ilman että käyttäjälle avataan luottamuksellisia referenssiprojekteja.

