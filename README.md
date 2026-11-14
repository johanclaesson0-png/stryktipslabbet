# Stryktipslabbet 16.1

**Stryktipslabbet** är en svensk mobilanpassad analysapp för Stryktipset, anpassad till ett tipslag med 10 deltagare och ett budgettak på **1 800 kr per omgång**. Den lämnar aldrig in spel.

## Webbadresser när GitHub Pages har aktiverats

- App: https://johanclaesson0-png.github.io/stryktipslabbet/
- Datastatus: https://johanclaesson0-png.github.io/stryktipslabbet/status.html
- Automatiska systemförslag: https://johanclaesson0-png.github.io/stryktipslabbet/veckans-analys.html
- Spikvakten: https://johanclaesson0-png.github.io/stryktipslabbet/spikvakt.html
- **Femårsarkiv och lagstatistik:** https://johanclaesson0-png.github.io/stryktipslabbet/datadjup.html
- **Version 13 + 14 – marknadsrörelser och formmodell:** https://johanclaesson0-png.github.io/stryktipslabbet/marknad-och-form.html
- **Version 15 + 16 – streckvärde, andra spel och spelarnas frånvaro:** https://johanclaesson0-png.github.io/stryktipslabbet/spelvarde-och-spelformer.html

Om webbadressen inte fungerar än: öppna repositoryts **Settings → Pages → Build and deployment → Source** och välj **GitHub Actions**. Kontrollera under **Settings → Actions → General** att Actions får köras och att GitHub-tokenen har skrivbehörighet för arkivlagring. Kör därefter arbetsflödet manuellt via **Actions → Stryktipslabbet – samla och publicera → Run workflow**.

## Vad som finns i repositoryt

- index.html: Stryktipslabbet med beslutsstudio och historik.
- veckans-analys.html: automatiska systemförslag och historik för varje observerad omgång.
- status.html: visar senast publicerad observation och spelstopp.
- scripts/collect.py: tidsstämplad, läsande insamling av framtida Stryktipsomgångar och officiellt facit.
- scripts/analyze.py: räknar fram sannolikheter från observerade odds, optimerar tre matematiska system under budgettaket, arkiverar varianter före spelstopp och rättar mot officiellt facit.
- scripts/publish.py: bygger enbart validerad publik webbinformation och de senast arkiverade omgångarna.
- tests/test_pipeline.py, tests/test_analysis.py, tests/test_solo.py och tests/test_spikvakt.py: 47 automatiserade testfall.
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


## Version 13 – verkliga oddsrörelser och folkstreck

I scripts/market_moves.py används arkiverade tidsstämplade förhandsobservationer i data/analysis_history/<omgång>/*.json, **inte resultat**. För varje 1/X/2 visas förändringen från första till senaste lagrade observation i procentenheter för både normaliserade oddssannolikheter och folkets streck. Över 3 procentenheter i oddssannolikhet eller 5 i folkstreck markeras som större rörelse.

Rapporter skapas bara före spelstopp, fryses under data/market_moves/, föregående förhandsversioner sparas i data/market_moves_history/, och kan bara publiceras om de går att återuppbygga med källornas tidsstämplar och SHA256. Minst två oberoende observationstidpunkter krävs. En rörelse säger ingenting säkert om bakomliggande orsaker, vinnande strategi eller högre förväntad avkastning.

## Version 14 – alternativ testprognos med lagform

Skriptet scripts/feature_model.py jämför:
1. Oförändrad **normaliserad oddsbaslinje** (ursprungliga sannolikheter och system).
2. En **förregistrerad, försiktig formjustering** (version form-overlay-preregistered-2026-11-13-v14) utifrån de fem och tio senaste matchernas poäng/match, hemma-/bortaform och målskillnad.

Formjusteringen är en **heuristisk experimentmodell, inte en kalibrerad maskininlärningsmodell**. Om något lag har mindre än tre tidigare daterade matcher används odifferensierad oddsbaslinje för den matchen. Den exakta justeringsvikten är fixerad till 0,25 före de kommande resultat som modellen ska utvärderas mot. Alla datapunkter måste vara från före observationens kalenderdatum; dokumentationens förhandsrapport måste i sin tur ha frysts efter observation och före spelstopp. Läs hur siffrorna tolkas i marknad-och-form-vyn.

Både ditt eget system (normalt 96 kr) och lagets system (högst 1 800 kr) optimeras med **exakt samma totala radkostnad som baslinjen**, så att skillnader i antal rader inte förväxlas med skillnader i kvalitet. Om de nya data inte motiverar ändrade tecken visas samma system igen, utan att konstruera skillnader.

När officiella resultat kommer sparar scripts/feature_model.py hypotetiska 10–13-rättsrader, netto per system och Brier/log loss per modell under data/form_model_settlements/. Stryktipslabbet publicerar bara rapporter som kan verifieras mot originalobservationens tidsstämpel, källhash och lagformsrapporten. Framtida aggregat hålls separat under data/form-model-progress.json. Ingen äldre Elo-backtest eller lagets inskickade historiska kuponger räknas som bevis för denna nya modell.

**Begränsningar:** Vi saknar ännu tillräckligt många prospektiva rättade kuponger för att säga att formmodellen förbättrar sannolikheter eller utdelningar. De två modellerna bygger på olika sannolikhetsantaganden, och 13-rättschanserna kan därför inte jämföras som om båda vore kalibrerade. Vi saknar säker särmarkering av lottade matcher i framtida facit; detta måste lösas innan detaljerad fotbollskalibrering hävdas. Modellen påverkar inte originalets rekommendationer eller höjer insatsgränserna.

Kör manuellt: python -m scripts.market_moves --outdir data ; python -m scripts.feature_model --outdir data ; python -m scripts.publish


## Version 15: relativt streckvärde – inga påhittade vinster

scripts/pool_value.py beräknar ett alternativt streckvärdesystem med exakt samma radkostnad som det balanserade systemet. Det visar sannolikheten för 13 rätt, modellens relativa streckvärde och folkets förenklade täckningsmassa. Folkets täckning bygger på ett oberoendeantagande som inte gäller exakt i riktiga spelpooler.

V15 är INTE en bevisad modell för förväntad utdelning i kronor. Vi saknar säker kunskap om slutomsättning, jackpot och verklig gemensam radfördelning före spelstopp. Resultaten rättas hypotetiskt mot officiella utbetalningar efter spelstopp. Alla kupongprognoser fryses i förväg.

## Version 16: Topptipset och Europatipset

scripts/other_games.py hämtar och validerar skilda officiella kuponger för Topptipset (8 matcher, endast 8 rätt ger utdelning) och Europatipset (13 matcher, 10–13 rätt) från Svenska Spels öppna API. Varje produkt har separat omgångsnummer, källhash, dataarkiv och rättning. System för cirka 100 kr skapas bara om matchnummer, produkt, spelstopp, odds och streck är kompletta.

API-listor: https://api.spela.svenskaspel.se/draw/1/topptipsetfamily/draws respektive https://api.spela.svenskaspel.se/draw/1/europatipset/draws. Om en kupong är publicerad men ännu saknar odds visas de verkliga matcherna tydligt som ofullständiga – inga odds eller tecken hittas på. Topptipset och Europatipset blandas aldrig med Stryktipset.

## Senaste resultat och tillgängliga spelare

Lagens fem senaste verifierbara matchresultat visas med datum, motståndare, mål och hemma/borta/neutral arena. Underliggande data kommer från OpenFootball och CC0-licensierade internationella landslagsresultat. Endast resultat som är daterade före kupongens observation får användas.

scripts/player_availability.py har säker källgranskning men INTE automatisk levande skadehämtning. För en verifierad frånvarorapport krävs spelare, lag, status, HTTPS-källa, källa publicerad före förhandsobservation, kontrolltid högst sju dagar gammal och granskad källstatus. Utan sådan källa visas 'ej verifierat – okänt' – det betyder inte att laget är skadefritt.

För att ansluta automatiska skador, avstängningar och laguppställningar behövs en avtalad leverantör eller officiell källa, API-nyckel/anslutning, stabila lag-/spelar-ID och licensvillkor som tillåter användningen. Möjliga externa tjänster att undersöka är SportsDataIO och soccer-data.co. Dessa är inte anslutna.

## Hjälp för tabellen

ODDS 1/X/2: marginalnormaliserad marknadssannolikhet för hemma/kryss/borta. FORM 1/X/2: formmodellens experimentella sannolikheter. MARKNADSSYSTEM: grundmodellens valda tecken, till exempel 1X. FORMSYSTEM: formmodellens tecken med samma radkostnad. DATATÄCKNING: om båda lagens tidigare resultat finns i tillräcklig omfattning.

Version 15 och 16 använder inga riktiga spelkonton, lämnar aldrig in pengar och ändrar inte originalsystemets insatsgränser. 18+ – spela ansvarsfullt.

## Version 16.1 – djupare matchdata och verifierad frånvaro

scripts/match_insights.py skapar kompletterande, tidsfrysta matchfakta för kommande Stryktipsomgångar. Endast matcher med matchdatum strikt före originalobservationens datum får användas. Matchkorten under spelvarde-och-spelformer.html visar:

- Tio senaste faktiskt spelade matcherna, datum, resultat, motståndare, hemma/borta/neutral plan.
- Antal dagar sedan sista verifierade matchen vid oddsobservationen (INTE exakta dagar fram till kickoff), antal spelade matcher senaste 7/14 dagarna.
- Obesegrad/utan-seger-sviter, hållna nollor och matcher där båda lagen gjorde mål.
- Motståndarnas genomsnittliga poäng per match i deras fem senaste matcher **före** respektive historiska möte. Måttet är inte ligajusterat.
- Femtal senaste inbördes möten när källan har dem.
- För klubblag: härledd tabellplacering från de tillgängliga ligamatcherna, utan poängavdrag eller officiell tabellgaranti.

Alla värden och källor är märkta med observationstid och kopplade till analysens originalhash. Inga av dessa nya beskrivande signaler påverkar ännu modellens sannolikheter, tecken eller insatser; utvärdering på framtida omgångar måste göras först.

**Spelarstatus:** två officiella nyheter från Svenska Fotbollförbundet har granskats för Stryktipsomgång 4979: Besfort Zeneli (9 november 2026) och Patrik Wålemark (12 november 2026) missar landslagssamlingen på grund av skada. Källor:
- https://www.svenskfotboll.se/nyheter/landslag/2026/11/herrlandslaget-aterbud
- https://www.svenskfotboll.se/nyheter/landslag/2026/11/herrlandslaget-walemark/

data/player_reports/verified.json lagrar källgranskningstid, giltigt lag och produktomgång. scripts/player_availability.py fortsätter att skapa frysta spelerstatusrapporter först när kontrollen gjorts före originaloddsobservationen. Om en verifierad nyhet är nyare än observationen kan den visas **separat som källgranskad nyhet**, aldrig som del av den äldre prognosen. Det är inte en automatisk skadeleverantör och innebär inte täckning för andra lag eller matcher. Spelarstatus ska kontrolleras på nytt nära avspark.

tests/test_match_insights.py kontrollerar datumfilter, resttid, inbördes möten, spårbarhet, icke-officiella tabeller och att resultat i framtiden inte kan ändra en äldre förhandsrapport.

## Version 17 integrerad i version 15–16: nyckelspelare och lika dyra system

Den befintliga källkontrollerade modellen i `scripts/player_impact.py` visas också på
`spelvarde-och-spelformer.html`. Den identifierar viktiga spelare ur verklig
säsongsstatistik (minuter, starter, mål, assist) och rapporterad frånvaro för
engelska Premier League, Championship, League One och League Two när API-Football
har verifierbar täckning. Avsaknad av uppgifter är **okänt**, inte skadefri trupp.

När en licensgodkänd rapport med tillräcklig täckning finns skapas två
**separata experimentella** spelarjusterade system, ett baserat på det befintliga
100-kronorssystemet och ett på tipslagets högst 1 800 kr. Båda har **exakt samma
faktiska radkostnad** som respektive marknadssystem. Matcher utan tillförlitlig
spelarstatus behåller oddsprognosen. Differenser i 1/X/2 redovisas i
procentenheter, och det går att kopiera teckenförslagen. Den ordinarie
version 15-värdemodellen, version 16:s separata Topptips/Europa-kuponger,
formmodellen och historiska rättningar ändras inte.

Effekterna är en **okallibrerad känslighetsanalys**. Bookmakeroddsen kan redan
ha tagit hänsyn till skador och avstängningar. Varken originaltecken eller
insats påverkas, och inget spel lämnas in automatiskt.

Käll- och rättighetskraven för API-Football fortsätter gälla oförändrade:
`APIFOOTBALL_KEY` i GitHub Actions Secrets samt verifierade rättigheter
(`PLAYER_DATA_PUBLICATION_APPROVED=1` i Repository Variables). Utan båda
publiceras inga licensierade spelaruppgifter och ordinarie tipsverktyg fortsätter
fungera. SportsDataIO är ännu inte autentiserat och ska inte utges för att vara
en aktiv källa. Test: `python -m unittest discover -s tests -v`.
