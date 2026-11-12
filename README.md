# Stryktipslabbet 8.0

**Stryktipslabbet** är en svensk mobilanpassad analysapp för Stryktipset, anpassad till ett tipslag med 10 deltagare och ett budgettak på **1 800 kr per omgång**. Den lämnar aldrig in spel.

## Webbadresser när GitHub Pages har aktiverats

- App: https://johanclaesson0-png.github.io/stryktipslabbet/
- Datastatus: https://johanclaesson0-png.github.io/stryktipslabbet/status.html

Om webbadressen inte fungerar än: öppna repositoryts **Settings → Pages → Build and deployment → Source** och välj **GitHub Actions**. Kontrollera under **Settings → Actions → General** att Actions får köras och att GitHub-tokenen har skrivbehörighet för arkivlagring. Kör därefter arbetsflödet manuellt via **Actions → Stryktipslabbet – samla och publicera → Run workflow**.

## Vad som finns i repositoryt

- index.html: Stryktipslabbet med beslutsstudio och historik.
- status.html: visar senast publicerad observation och spelstopp.
- scripts/collect.py: tidsstämplad, läsande insamling av framtida Stryktipsomgångar och officiellt facit.
- scripts/publish.py: bygger enbart validerad publik webbinformation.
- tests/test_pipeline.py: nio automatiserade testfall.
- .github/workflows/stryktipslabbet.yml: bygg-, insamlings- och publiceringsflöde.
- data/2024-2026-datatackning.csv och data/2024-2026-simulerade-system.csv: äldre experimentella backtests.

Schemat försöker köras två gånger i timmen (minut 17 och 47 UTC) och dämpar API-frågor när spelstopp är långt bort. GitHub Actions kan försenas eller utebli. Svenska Spels offentliga API är odokumenterat och åtkomst kan inte garanteras. Liveinsamling får inte antas fungera innan verkliga GitHub-körningar bekräftats.

## Testa lokalt

1. Kör: python -m unittest discover -s tests -v
2. Valfritt, om Svenska Spels API är nåbart: python scripts/collect.py --outdir data
3. Bygg publik webbplats: python scripts/publish.py
4. Starta lokal webbserver: python -m http.server -d .site 8000

## Källstatus och integritet

Offentliga GitHub-repositories är synliga för alla. Lägg inte upp personuppgifter, spelkonton, privata andelslag eller nycklar. Bygget publicerar bara webbapp, statussida och godkända dataposter som Pages-artifakt. Tidsstämplade råa publika API-svar i repositoryt är fortsatt offentligt åtkomliga.

De två historiska teståren omfattar 105 omgångar, men äldre historiska förhandsodds och folkstreck är inte komplett verifierade. Simulerade systemutfall är därför **inte bevis på faktisk ekonomisk överavkastning**. Efterhandsinhämtad data är aldrig giltig som samtida förhandsdata.

18+ · Spela ansvarsfullt · https://stodlinjen.se/
