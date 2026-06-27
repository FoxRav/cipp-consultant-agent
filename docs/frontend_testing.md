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
http://127.0.0.1:5173
```

4. Testaa kysymykset:

```text
Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?
Mitä pitää huomioida taloyhtiön JV-pystylinjojen ja pohjaviemärin sukituksessa?
Mitä urakkarajoissa pitää huomioida?
Mitä videotarkastuksesta ja loppukuvauksesta pitää vaatia?
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
- videotarkastus kyllä/ei
- yksikköhinnat kyllä/ei

Oletuksena `SV-pystyviemäreitä = 4` ja `Kattokaivot = 4`. Kattokaivojen oletusarvo johdetaan SV-pystyviemäreiden oletusarvosta, koska kattokaivot liittyvät sadevesipuolen pystylinjoihin. Käyttäjä voi muuttaa kattokaivojen määrää erikseen, jos kohteen todellinen tilanne poikkeaa oletuksesta.

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

## Mock API -testi

Mock-tila ei tarvitse tietokantaa tai backendia.

```powershell
cd apps/web
npm run dev
```

Avaa:

```text
http://127.0.0.1:5173/?mock=1
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

Smoke käyttää mock API -tilaa URL-parametrilla `?mock=1`. Testi varmistaa, että yläpalkin kentät näkyvät, arvoja voi muuttaa, kysymyksen voi lähettää, vastaus ja lähteet ilmestyvät, debug-näkymä avautuu ja UI:ssa ei näy Windows-polkuja tai luottamuksellisia dokumenttipäätteitä.
