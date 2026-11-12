# Stryktipslabbet 8.0 – redo för GitHub Pages

Forskningsverktyg för ett tipslag med tio deltagare. Budget **högst 1 800 kr** per kupong. Ingen kuponginlämning sker. **18+ · Spela ansvarsfullt**.

## Publicera

1. Skapa ett **nytt och publikt** repository som heter `stryktipslabbet` på https://github.com/new. Observera att repository och Pages blir publika. Lägg aldrig upp privata andelslagsuppgifter eller spelkonton.
2. Ladda upp hela **innehållet** i denna projektmapp till `main`. Kontrollera att även `.github/workflows/stryktipsobservation.yml` finns med (dold mapp). Om du använder GitHub Desktop kan du klona det tomma repositoryt och kopiera in dessa filer.
3. I **Settings → Pages → Build and deployment → Source**, välj **GitHub Actions**. I **Settings → Actions → General → Workflow permissions** tillåt att `GITHUB_TOKEN` får skriva till repositoryt (read/write) för att spara insamlingens observationer.
4. Öppna **Actions** → workflow **Stryktipslabbet – insamling och säker publicering** → **Run workflow**. Kontroller att tester, insamling, bygg och publicering visas. Om extern API-hämtning misslyckas visas fortfarande webbappen men utan levande data.
5. Webbplatsen bör finnas under `https://DITT-GITHUB-NAMN.github.io/stryktipslabbet/`. Kontrollera den faktiska länken på **Settings → Pages**. På själva sidan finns länken **Kontrollera datastatus**.

Publicerade filer begränsas till `index.html`, `status.html`, `data/status.json`, en kvalificerad `data/latest.json` och upp till 30 validerade resultatfiler. Råarkiv, tester och datainsamlarkod publiceras **inte** som webbsidor. I ett *publikt repository* är de dock fortfarande synliga som kod/data, eftersom repositoryt i sig är publikt.

## Hur ofta körs det?

Workflow kör schemalagt två gånger per timme (UTC minut 17 och 47). Insamlaren dämpar antalet anrop när spelstopp är långt bort: cirka 6h (>48 h till stopp), 2h (24–48 h), 1h (6–24 h) och 30min sista 6h. GitHub garanterar inte exakta körtider och kan pausa scheman. Resultat hämtas efter spelstopp och skrivs till separat facit. Data med obs-tid **efter** spelstopp används aldrig som pre-close.

Allt detta förutsätter att GitHub Actions är aktiverat och Svenska Spels odokumenterade publika API går att nå. Inga löften om realtidsleverans. Se `LAS_MIG.md` för matematisk metod och historiska begränsningar.

## Testa lokalt

```bash
python -m unittest discover -s tests -v
python verktyg/bygg_publikt_v8.py --root . --output .site
python -m http.server -d .site 8000
```

Öppna http://localhost:8000/status.html eller http://localhost:8000/. Automatiserad insamling kan testas separat från GitHub.

## Dataetik och integritet

- Historiska systemresultat i demoarkivet är experiment, inte verifierad avkastning.
- 105 omgångar har resultatfacit, men äldre förhandsodds och streck är ofullständiga.
- Alla observationer kommer från offentligt API (när det fungerar); ingen kontoinloggning och inget spelkonto.
- Spara eventuella privata kuponger/laguppgifter lokalt och **inte** i offentligt repository.
