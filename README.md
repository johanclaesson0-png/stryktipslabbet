# Stryktipslabbet 12.0

**Stryktipslabbet** är en svensk mobilanpassad analysapp för Stryktipset, anpassad till ett tipslag med 10 deltagare och ett budgettak på **1 800 kr per omgång**. Den lämnar aldrig in spel.

## Webbadresser när GitHub Pages har aktiverats

- App: https://johanclaesson0-png.github.io/stryktipslabbet/
- Datastatus: https://johanclaesson0-png.github.io/stryktipslabbet/status.html
- Automatiska systemförslag: https://johanclaesson0-png.github.io/stryktipslabbet/veckans-analys.html
- Spikvakten: https://johanclaesson0-png.github.io/stryktipslabbet/spikvakt.html
- **Femårsarkiv och lagstatistik:** https://johanclaesson0-png.github.io/stryktipslabbet/datadjup.html

Om webbadressen inte fungerar än: öppna repositoryts **Settings → Pages → Build and deployment → Source** och välj **GitHub Actions**. Kontrollera under **Settings → Actions → General** att Actions får köras och att GitHub-tokenen har skrivbehörighet för arkivlagring. Kör därefter arbetsflödet manuellt via **Actions → Stryktipslabbet – samla och publicera → Run workflow**.

## Vad som finns i repositoryt

- index.html: Stryktipslabbet med beslutsstudio och historik.
- veckans-analys.html: automatiska systemförslag och historik för varje observerad omgång.
- status.html: visar senast publicerad observation och spelstopp.
- scripts/collect.py: tidsstämplad, läsande insamling av framtida Stryktipsomgångar och officiellt facit.
- scripts/analyze.py: räknar fram sannolikheter från observerade odds, optimerar tre matematiska system under budgettaket, arkiverar varianter före spelstopp och rättar mot officiellt facit.
- scripts/publish.py: bygger enbart validerad publik webbinformation och de senast arkiverade omgångarna.
- tests/test_pipeline.py, tests/test_analysis.py, tests/test_solo.py och tests/test_spikvakt.py: 39 automatiserade testfall.
- .github/workflows/stryktipslabbet.yml: bygg-, insamlings- och publiceringsflöde.
- data/2024-2026-datatackning.csv och data/2024-2026-simulerade-system.csv: äldre experimentella backtests.

Schemat försöker köras två gånger i timmen (minut 17 och 47 UTC) och dämpar API-frågor när spelstopp är långt bort. GitHub Actions kan försenas eller utebli. Svenska Spels offentliga API är odokumenterat och åtkomst kan inte garanteras. Liveinsamling får inte antas fungera innan verkliga GitHub-körningar bekräftats.

## Testa lokalt

1. Kör: python -m unittest discover -s tests -v
2. Valfritt, om Svenska Spels API är nåbart: python scripts/collect.py --outdir data
3. Kör analysen: python -m scripts.analyze --outdir data
4. Kör eget läge: python -m scripts.solo --outdir data
5. Frys Spikvakt före spelstopp: python -m scripts.spikvakt --outdir data
6. Bygg publik webbplats: python -m scripts.publish
7. Starta lokal webbserver: python -m http.server -d .site 8000

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

## Spikvakten – nytt beslutsstöd i version 11

Sida: https://johanclaesson0-png.github.io/stryktipslabbet/spikvakt.html

**Syfte:** att hjälpa en ovan tippare att se *var* en spik är osäker, vad en extra gardering kostar och när oavgjort kan vara värt att studera.

- **Spik-risk:** från den tidsstämplade, marginalnormaliserade 1X2-sannolikheten beräknas risken att spiken missar som 1−P(tecken). Spikar under 55 % sannolikhet markeras. Ett andratecken föreslås utifrån näst högsta modellchans och den nya systemkostnaden visas; andra garderingar kan behöva flyttas.
- **Kryssvakt:** flaggar om ett system saknar X i en match där modellens P(X) är minst 27 %. P(X) och folkets X-streck visas separat; skillnaden är inte bevis på spelvärde.
- **Kostnadsneutrala testförslag:** scripts/spikvakt.py optimerar två experimentella varianter: mindre riskfyllda spikar och mer fokus på X. Varje variant har exakt samma antal rader och kostnad som den balanserade grundmodellen – både i 100-kronorsläget och lagets 1 800-kronorsläge.
- **Förhandsfrysning:** scriptet skapar inga nya experiment efter spelstopp, även om gamla förhandsodds finns kvar. Källtid, modellversion och fryst skapandetid lagras. Äldre rapportversioner sparas i data/spikvakt_history/.
- **Rättning:** efter officiellt facit räknas 10/11/12/13-rättsrader, täckta matcher och hypotetiskt netto per förslag i data/spikvakt_settlements/. Publiceringen validerar tidsstämplade källvärden och förhandsversion.
- **Testplan:** gränser och vikter är registrerade i källkoden under version spikvakt-fixed-2026-11-13-v1. Inga omgångar före införandet får räknas som framåttester. Jämför nya framtida omgångar mot den orörda grundmodellen.

**Status:** funktionerna är byggda och testerna passerar. Det är ännu INTE visat att Spikvakten förbättrar träffsäkerhet eller utdelning. På vissa kuponger blir testförslagen identiska med grundmodellen. Förväntad avkastning kan inte beräknas utan tillförlitliga pott- och utdelningsdata. Lottade/inställda matcher bör framöver skiljas från spelade matcher i prognoskvalitetsmått.

18+ – Spela ansvarsfullt och använd en fast förlustgräns.


## Version 12 – fem års historik och utökad förhandsinformation

**Femårshistorik:** data/history/stryktipset-five-years.csv innehåller 262 kuponger och 3 406 matcher från 13 november 2021 till 7 november 2026. Källan är ett publikt resultatarkiv som speglar Svenska Spels publicerade omgångsfacit: https://github.com/andreyhgl/stryktipset-results. Källan och begränsningarna dokumenteras i data/history/source.json.

**Kronologiskt modelltest:** scripts/history5.py går igenom omgångarna i tidsordning. Den använder en historisk, förenklad Elo-baslinje som bara känner till äldre kupongresultat. 2021/22 används som uppvärmning; 210 omgångar efter 13 november 2022 utvärderas med Brier score och matematiska 96/1800-system. Det är INTE ett test av dagens oddsmodell. Eftersom vi saknar säkra historiska förhandsodds/-streck får de inte rekonstrueras med efterhandsinformation. Resultatmått och per-år-statistik finns i data/history/summary.json.

**Officiella utdelningar:** scripts/historical_payouts.py försöker stegvis kontrollera gamla utbetalningar mot Svenska Spels officiella resultat-API, högst åtta äldre omgångar per schemalagd körning. Endast bekräftade resultat och belopp lagras; enbart facit innebär inte automatiskt verifierat vinstbelopp. Matchresultat som verkar administrativt bestämda markeras separat i historikens prognoskvalitetsmätning.

**Ligahistorik för aktuell form:** scripts/league_history.py hämtar matchresultat från OpenFootball / football.json, licens CC0-1.0: https://github.com/openfootball/football.json. Säsonger 2021/22–2026/27 och de stora engelska/europeiska ligor som finns i katalogen läses gradvis in. Dessutom ingår **landskamper för herrlandslag 2020–2026**, från martj42/international_results (CC0 1.0), https://github.com/martj42/international_results. Neutral-plan-matcher ingår i lagens totala form men räknas inte som hemma-/bortamatcher. Aktuell säsong kan uppdateras högst dagligen; källmaterialet är ibland ofullständigt eller försenat och måste bedömas per lag.

**Förhandsrapporter:** varje ny omgång kan visa:
- Fem och tio senast tillgängliga ligamatcher (vinst, kryss, förlust).
- Mål för och emot samt poäng per match.
- Separat hemma-/bortaform.
- Datum för senaste tillgängliga match och antal historiska matcher.
- Tidigare möten i täckta ligor.
- Sannolikheter från observerade odds och folkets streck.
- Täckningsstatus per match (bra/delvis/saknas) och källor.

Skriptet beräknar endast statistik på matcher vars datum är **strikt före kupongens förhandsobservation**. Rapporter skapas bara före spelstopp, är knutna till den exakta förhandsobservationen och visas via datadjup.html. Om en liga eller ett lag saknas visas detta tydligt. Vi lovar aldrig att vi har korrekta startelvor/skador utan en verifierad separat källa.

**Källvillkor:** football-data.co.uk har publicerade användningsbegränsningar för automatiserad inhämtning/AI. Ingen sådan källa hämtas automatiskt här; OpenFootball används för öppna licensierade resultat. Vi hämtar inte historiska förhandsodds från slutresultat.

**Driftsättning:** GitHub Actions tar högst 14 nya ligafiler och åtta resultatutdelningar per körning. Den fulla ligahistoriken och kontrollen av gamla utdelningar fylls därför successivt på; datadjup.html visar hur mycket som verkligen är tillgängligt. Nya automatiska CI-tester säkerställer att dagens och framtida matchresultat inte får ingå i föregående dagars formtal. Svenska namn på landslag normaliseras mot den internationella datakällan. Förslagets 1X2-sannolikheter bygger fortfarande på normaliserade bookmakerodds; formdatan är tills vidare **beslutsstöd, inte automatiskt en del av sannolikhetsmodellen**, tills den kan valideras på framtida omgångar.
