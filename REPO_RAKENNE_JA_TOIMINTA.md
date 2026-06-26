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

## 2. Repojuuren tiedostot

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
- järjestelmäriippuvuudet: Docker Desktop, Docker Compose ja LibreOffice
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

Windowsissa oletettu LibreOffice-polku on:

```text
C:\Program Files\LibreOffice\program\soffice.exe
```

Jos LibreOffice ei ole PATHissa, komennolle `cipp-extract-remaining-text` annetaan polku parametrilla `--soffice-path`.

## 3. Kansiorakenne

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
  price/       JV-urakan hinta-arviolaskenta
  validate/    canonical JSON -validointi
  embed/       varattu embedding-/vektorointikerrokselle
  search/      varattu hakutoiminnoille
```

### `tests/`

Automaattitestit tärkeimmälle logiikalle. Testit ovat pieni mutta tärkeä turvaverkko: ne varmistavat, että tarjouspyyntöjen faktaparseri, canonical-validointi ja JV-hintalogiikka eivät hajoa huomaamatta.

## 4. Tietokannan pääajatus

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

## 5. Migraatiot

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

## 6. Python-koodin yhteiset perustiedostot

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

## 7. Extract: lähteistä tekstiksi

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

### `src/cipp_contracts/extract/build_markdown.py`

Rakentaa PDF-sivuista markdown-asiakirjat.

Mitä se tekee:

- lukee sivutekstit `raw.pages`-taulusta
- ryhmittelee ne asiakirjatyypin mukaan
- redaktoi tunnistettavia henkilötietoja ja yhteystietoja
- kirjoittaa markdownit `data/extracted/<project>/markdown/`-kansioon
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

## 8. Normalize: tekstistä kanoniseksi malliksi

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

## 9. Load: kanonisesta mallista tietokantaan

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
- pilkkoo ne osioihin
- tallentaa osiot `doc.sections`-tauluun
- tallentaa hakukelpoisia katkelmia `doc.clauses`-tauluun
- käyttää fallback-logiikkaa, jos esimerkiksi yksikköhinnat löytyvät urakoitsijan tarjouksesta eivätkä omasta `unit_prices.md`-tiedostosta

Tämä mahdollistaa dokumenttisisällön kysymisen, haun ja analysoinnin.

## 10. Validate: laadunvarmistus

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

## 11. Price: JV-hinta-arvio

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

## 12. Embed ja search

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

## 13. SQL-kyselyt

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

## 14. Komentorivityökalut

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
cipp-load-markdown-sections --project-code reference_001 --markdown-dir data/extracted/reference_001/markdown
```

### `cipp-import-finlex-legal-xml`

Tuo lakiaineiston Finlex XML -lähteestä.

```powershell
cipp-import-finlex-legal-xml --source-dir data/raw/Rakentamisen_Lait
```

## 15. Tyypillinen uuden projektin käsittely

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

## 16. Projektien vertailukelpoisuus

Vertailukelpoisuus syntyy kolmesta asiasta:

1. Asiakirjat luokitellaan samoilla `document_type`-koodeilla.
2. Urakan sisältö normalisoidaan samoihin domain-tauluihin.
3. Kiinteistö- ja laajuustiedot puretaan samoihin kenttiin.

Esimerkki:

- Referenssikohde Assa urakkasopimus voi antaa hinnan ja maksuerät.
- Toisessa projektissa tarjouspyyntö voi antaa asuntojen määrän ja pystylinjat.
- Kolmannessa projektissa kokouspöytäkirjat voivat kertoa lisätöistä ja toteutuneista ongelmista.

Järjestelmän tehtävä on saada nämä eri lähteistä tulevat tiedot samaan rakenteeseen, jotta kysymykset voidaan vastata vertaamalla projekteja eikä vain lukemalla yksittäistä PDF:ää.

## 17. Tärkeimmät CIPP-käsitteet repossa

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

## 18. Testit

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

## 19. Mitä tiedostoja yleensä muokataan?

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

## 20. Mitä ei yleensä muokata käsin?

Näitä ei yleensä kannata muokata käsin:

- `.venv/`
- `.pytest_cache/`
- `.ruff_cache/`
- `__pycache__/`
- Dockerin tietokantavolyymi
- koneellisesti tuotetut sivu-JSONit, ellei korjata kokeellista välitulosta

Canonical JSONia voi tarkistaa käsin, mutta pitkällä aikavälillä tavoitteena on, että se syntyy mahdollisimman paljon parserien ja importerien kautta.

## 21. Nykyiset tunnetut kehityskohdat

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

## 22. Miten repo toimii käyttäjän kysymyksen kannalta?

Kun käyttäjä kysyy esimerkiksi:

```text
Paljonko meidän taloyhtiön kaikkien JV-linjojen CIPP-urakka maksaisi?
```

Järjestelmän pitäisi edetä näin:

1. Käyttäjän kohteen tiedot normalisoidaan samoihin kenttiin kuin referenssihankkeet.
2. Tietokannasta haetaan kaikki omat referenssihankkeet.
3. Lähin referenssi valitaan asuntojen määrän, pystylinjojen, pohjaviemärin ja tonttiviemärin perusteella.
4. Jos dataa puuttuu, Referenssikohde A toimii oletusreferenssinä.
5. Hinta-arvio lasketaan ja perustellaan lähdedatalla.
6. Vastaus kertoo myös epävarmuudet, esimerkiksi jos pohjaviemärin tai tonttilinjan pituus puuttuu.

Kun käyttäjä kysyy esimerkiksi:

```text
Linjassa on jyijyä, mitä pitää tehdä?
```

Järjestelmän pitäisi hakea:

1. operatiiviset havainnot aiemmista projekteista
2. kokouspöytäkirjat ja vastaanottodokumentit
3. laatuvaatimukset ja videotarkastuskommentit
4. sopimus- ja YSE-tason vastuut
5. vastaavat ratkaisut aiemmista hankkeista

Tavoite ei ole antaa pelkkää yleisvastausta, vaan vastata projektikokemuksen perusteella: mitä vastaavassa tilanteessa tehtiin, kuka vastasi, millä perusteella ja miten asia dokumentoitiin.

## 23. Ytimeen tiivistettynä

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
- `rag` mahdollistaa hakemisen ja myöhemmin kysymys-vastausjärjestelmän

Kun nämä kerrokset ovat kunnossa, uusi taloyhtiö voidaan verrata aiempiin todellisiin hankkeisiin eikä pelkkään yleiseen nyrkkisääntöön.

