# Frontend Playground Testing

Tämä checklist on paikallisen kehitys-UI:n testaamiseen. Frontend ei ole tuotantopalvelu, eikä se käytä LLM:ää.

## Live API -testi

1. Käynnistä backend:

```powershell
cipp-run-dev-api --host 127.0.0.1 --port 8000
```

2. Käynnistä frontend:

```powershell
cd apps/web
npm run dev
```

3. Avaa selain:

```text
http://127.0.0.1:5173/?resetCase=1
```

`?resetCase=1` tyhjentää vanhan `cipp_user_case`-localStorage-tilan ja pakottaa oikean oletuscasen. Käytä sitä aina, jos selaimessa näkyy vanhoja nolla-arvoja tai poistettuja kenttiä.

4. Testaa kysymykset:

```text
Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?
Mitä pitää huomioida taloyhtiön JV-pystylinjojen ja pohjaviemärin sukituksessa?
Mitä urakkarajoissa pitää huomioida?
Paljonko yllä kuvatun taloyhtiön urakka maksaa?
Kuinka paljon yllä asetettu taloyhtiön sukitusurakka maksaa?
Mitä amatööritoimijan pitää ymmärtää ennen kuin taloyhtiö pyytää urakkatarjouksia?
```

5. Muuta yläpalkista:

- asuntojen määrä
- rakennusten määrä
- JV-pystyviemärit
- SV-pystyviemärit
- kattokaivot
- pohjaviemärin pituus
- tonttilinjan pituus
- sadevesilinjojen pituus

Oletuksena `SV-pystyviemäreitä = 4` ja `Kattokaivot = 4`. Kattokaivojen oletusarvo johdetaan SV-pystyviemäreiden oletusarvosta, koska kattokaivot liittyvät sadevesipuolen pystylinjoihin. Käyttäjä voi muuttaa kattokaivojen määrää erikseen, jos kohteen todellinen tilanne poikkeaa oletuksesta.

Koko oletuscase on: `Asuntoja=30`, `Rakennuksia=1`, `Porrashuoneita=3`, `JV-pystyviemäreitä=15`, `SV-pystyviemäreitä=4`, `Kattokaivot=4`, `Pohjaviemäri m=50`, `Tonttilinja m=30` ja `Sadevesilinjat m=30`.

Perusnäkymässä ei näytetä `Videotarkastus`- eikä `Yksikköhinnat / lisätyöt` -kenttiä. Pikakysymysnapeissa ei näytetä `Videotarkastus`- eikä `Lisätyöt`-aiheita.

6. Tarkista jokaisessa vastauksessa:

- vastaus näkyy
- lähteet näkyvät
- epävarmuudet näkyvät
- puuttuvat tiedot näkyvät
- `llm_used=false`
- reference-lähteet ovat anonymisoituja
- ei Windows-polkuja
- ei oikeita projektinimiä
- debug toggle toimii
- erillistä oikean reunan lähde-/epävarmuuspaneelia ei näy
- tyhjät placeholderit kuten `Ei vielä lähteitä.` ja `Ei merkintöjä.` eivät näy

Hintakysymyksessä tarkista lisäksi:

- oletuskysymys on `Kuinka paljon yllä asetettu taloyhtiön sukitusurakka maksaa?`
- kysymys `Paljonko yllä kuvatun taloyhtiön urakka maksaa?` tunnistuu kustannusarvioksi
- vastauskortissa näkyy `Arviossa käytetty case`
- case-yhteenveto vastaa yläpalkin arvoja
- jos luotettava lähdeperustainen hintadata ei riitä, vastaus sanoo tämän selvästi eikä keksi euromäärää
- puuttuvat tiedot ja kustannusajurit näkyvät
- vastaus ei muutu yleiseksi asiantuntijaohjeeksi eikä mainitse sisäisen oppaan nimeä

## Mock API -testi

Mock-tila ei tarvitse tietokantaa tai backendia.

```powershell
cd apps/web
npm run dev
```

Avaa:

```text
http://127.0.0.1:5173/?mock=1&resetCase=1
```

Vaihtoehtoisesti aseta paikalliseen frontend-env-tiedostoon:

```env
VITE_USE_MOCK_API=true
```

Älä committaa oikeaa `.env`-tiedostoa.

## Automaattinen smoke-testi

Ensimmäisellä kerralla Playwright voi tarvita selaimen:

```powershell
cd apps/web
npx playwright install chromium
```

Aja smoke:

```powershell
npm run test:smoke
```

Smoke käyttää mock API -tilaa URL-parametrilla `?mock=1&resetCase=1`. Testi varmistaa, että yläpalkin case-parametrit näkyvät, poistetut perusnäkymän kentät ja topic-chipit eivät näy, arvoja voi muuttaa, reset palauttaa keskitetyn default-casen, hintakysymyksen voi lähettää, vastaus ilmestyy, case-yhteenveto näkyy, debug-näkymä avautuu, erilliset lähde-/epävarmuuspaneelit eivät näy ja UI:ssa ei näy Windows-polkuja tai luottamuksellisia dokumenttipäätteitä.

Perusnäkymä on yksipalstainen. Erilliset `Lähteet`- ja `Epävarmuudet`-sivupaneelit sekä niiden tyhjät placeholder-tekstit on poistettu. API-vastauksen lähde-, epävarmuus-, puuttuva tieto- ja varoitusdata säilyy JSONissa ja debug-näkymässä.

Smoke sisältää myös vanhan localStorage-tilan regression: jos selaimessa on vanha `cipp_user_case`, jossa SV-pystyviemärit, kattokaivot tai sadevesilinjat ovat nollia, schema-version mismatch poistaa vanhan tilan ja palauttaa arvot `4`, `4` ja `30`.

## Failed to fetch -vianetsintä

Jos frontend näyttää API-yhteysvirheen, erota ensin onko kyse backendistä, URL-asetuksesta, CORSista vai endpointin runtime-virheestä.

1. Tarkista että backend on käynnissä:

```powershell
cipp-run-dev-api --host 127.0.0.1 --port 8000
```

2. Tarkista health selaimessa:

```text
http://127.0.0.1:8000/api/health
```

3. Tarkista että frontend on käynnissä:

```powershell
cd apps/web
npm run dev
```

4. Tarkista API base URL:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Jos `VITE_API_BASE_URL` jätetään tyhjäksi, frontend käyttää suhteellista `/api/...`-polkua ja Vite proxy ohjaa kutsun backendille.

5. Testaa mock-tila ilman backendia:

```text
http://127.0.0.1:5173/?mock=1
```

Jos mock toimii mutta live ei, ongelma on backend/API/CORS/proxy-yhteydessä, ei UI-komponenteissa.

6. Testaa suora API POST PowerShellillä:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/answer" `
  -ContentType "application/json" `
  -Body '{
    "question":"Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
    "user_case":{
      "apartments_count":30,
      "buildings_count":1,
      "staircases_count":3,
      "jv_verticals_count":15,
      "sv_verticals_count":4,
      "roof_drains_count":4,
      "bottom_drain_length_m":50,
      "yard_line_length_m":30,
      "stormwater_line_length_m":30
    },
    "options":{
      "max_sources":8,
      "include_debug":false
    }
  }'
```

Tulkinta:

- backend ei vastaa: käynnistä `cipp-run-dev-api`
- direct POST toimii mutta frontend ei: tarkista `VITE_API_BASE_URL`, Vite proxy ja CORS
- direct POST palauttaa JSON-virheen `answer_composer_failed`: katso backend-loki
- mock toimii mutta live ei: UI on kunnossa, live API -polku pitää korjata
