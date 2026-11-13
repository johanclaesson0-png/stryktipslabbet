# Stryktipslabbet 10.0

**Stryktipslabbet** är en svensk mobilanpassad analysapp för Stryktipset, anpassad till ett tipslag med 10 deltagare och ett budgettak på **1 800 kr per omgång**. Den lämnar aldrig in spel.

## Webbadresser när GitHub Pages har aktiverats

- App: https://johanclaesson0-png.github.io/stryktipslabbet/
- Datastatus: https://johanclaesson0-png.github.io/stryktipslabbet/status.html
- Automatiska systemförslag: https://johanclaesson0-png.github.io/stryktipslabbet/veckans-analys.html

Om webbadressen inte fungerar än: öppna repositoryts **Settings → Pages → Build and deployment → Source** och välj **GitHub Actions**. Kontrollera under **Settings → Actions → General** att Actions får köras och att GitHub-tokenen har skrivbehörighet för arkivlagring. Kör därefter arbetsflödet manuellt via **Actions → Stryktipslabbet – samla och publicera → Run workflow**.

## Vad som finns i repositoryt

- index.html: Stryktipslabbet med beslutsstudio och historik.
- veckans-analys.html: automatiska systemförslag och historik för varje observerad omgång.
- status.html: visar senast publicerad observation och spelstopp.
- scripts/collect.py: tidsstämplad, läsande insamling av framtida Stryktipsomgångar och officiellt facit.
- scripts/analyze.py: räknar fram sannolikheter från observerade odds, optimerar tre matematiska system under budgettaket, arkiverar varianter före spelstopp och rättar mot officiellt facit.
- scripts/publish.py: bygger enbart validerad publik webbinformation och de senast arkiverade omgångarna.
- tests/test_pipeline.py och tests/test_analysis.py: 17 automatiserade testfall.
- .github/workflows/stryktipslabbet.yml: bygg-, insamlings- och publiceringsflöde.
- data/2024-2026-datatackning.csv och data/2024-2026-simulerade-system.csv: äldre experimentella backtests.

Schemat försöker köras två gånger i timmen (minut 17 och 47 UTC) och dämpar API-frågor när spelstopp är långt bort. GitHub Actions kan försenas eller utebli. Svenska Spels offentliga API är odokumenterat och åtkomst kan inte garanteras. Liveinsamling får inte antas fungera innan verkliga GitHub-körningar bekräftats.

## Testa lokalt

1. Kör: python -m unittest discover -s tests -v
2. Valfritt, om Svenska Spels API är nåbart: python scripts/collect.py --outdir data
3. Kör analysen: python -m scripts.analyze --outdir data
4. Bygg publik webbplats: python scripts/publish.py
5. Starta lokal webbserver: python -m http.server -d .site 8000

## Källstatus och integritet

Offentliga GitHub-repositories är synliga för alla. Lägg inte upp personuppgifter, spelkonton, privata andelslag eller nycklar. Bygget publicerar bara webbapp, statussida och godkända dataposter som Pages-artifakt. Tidsstämplade råa publika API-svar i repositoryt är fortsatt offentligt åtkomliga.

De två historiska teståren omfattar 105 omgångar, men äldre historiska förhandsodds och folkstreck är inte komplett verifierade. Simulerade systemutfall är därför **inte bevis på faktisk ekonomisk överavkastning**. Efterhandsinhämtad data är aldrig giltig som samtida förhandsdata.

18+ · Spela ansvarsfullt · https://stodlinjen.se/

## Automatisk analys och historisk uppföljning

Varje ny kvalificerad **förhandsobservation** från Svenska Spel (13 matcher, odds och folkstreck med giltig observationstid före spelstopp) omvandlas till tre alternativa matematiska system: balanserad, streckvärde-experiment och skrällexperiment. Det är ett **budgettak på 1 800 kr**, inte ett krav att varje system måste kosta exakt 1 800 kr.

Sannolikheterna beräknas som 1/odds och normaliseras för bookmaker-marginalen. De är *inte* en separat tränad fotbollsmodell. För värde- och skrällprofilerna styr folkstrecken ett heuristiskt urval, vilket inte ger vetenskapligt belägg för positivt väntevärde. Varje observation och dess system förblir frysta i data/analysis_history/. Den senaste giltiga prognosen före spelstopp sparas i data/analysis/<omgång>.json.

När komplett officiellt facit och alla fyra utdelningsnivåerna finns beräknas hypotetiska vinster och netto i data/settlements/ och visas i Veckans analys. Inga insatser skickas in eller läggs automatiskt. Arkiveringen fortsätter varje vecka oavsett vem i laget som faktiskt tippar.

## Feedback och förbättringar från historiska kuponger

Vi har analyserat **39 tidigare kuponger** och dokumenterat aggregerade fynd (felspikar, täckning av oavgjorda, garderingar och fallgropar i efterhandstest). Ingen privat lagkupong har lagts i det offentliga repositoryt.

- [Läs analysen och prioriteringarna](docs/feedback-historiska-kuponger-2026.md)
- [Följ utvecklingen i GitHub Issue #1](https://github.com/johanclaesson0-png/stryktipslabbet/issues/1)

Resultaten är hypoteser att testa, **inte** bevis att en ändrad modell kommer att vinna oftare.

## Eget spel (högst 100 kr)

Webbadress: https://johanclaesson0-png.github.io/stryktipslabbet/spela-sjalv.html

Den nya personliga 100-kronorsvyn bygger automatiskt tre system från den **samma frysta förhandsobservationen** som lagets 1 800-kronorsförslag, men kostar högst 100 kr per matematiskt system (normalt 96 kr). De sparas i `data/personal/` och rättas separat efter officiellt resultat i `data/personal_settlements/`. Inga riktiga spel läggs.

Jämförelsen med **105 äldre omgångar** från `data/2024-2026-elo-100kr-jamforelse.csv` bygger på en förenklad historisk Elo-modell, INTE på den nya oddsmodellen. Historiken är därför en illustration av risk, systemstorlek och träffsäkerhet – inte bevis för framtida överavkastning. Andra spel (Topptipset och Europatipset) länkas som möjliga alternativ, men har **ännu ingen separat automatisk datainhämtning** i Stryktipslabbet. Slutliga beslut och insatser görs på Svenska Spels webbplats.
