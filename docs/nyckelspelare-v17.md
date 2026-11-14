# Stryktipslabbet v17 – generella nyckelspelare i engelska ligor

Status: experimentell funktion på egen gren. Påverkar inte ordinarie
oddsprognos, matchtecken eller insats (100 kr / 1 800 kr).

## Varför?

Alla 13 matcher analyseras, inte bara namngivna exempelspelare. Fokus är
engelsk Premier League, Championship, League One och League Two. Matcher i
andra ligor och engelska cuper rapporteras som saknar täckning tills de
har verifierade datakällor. Inga spelare skapas manuellt.

## Datakällans arbetsgång

Vald förberedande adapter: API-Football i scripts/api_football_adapter.py.

1. Använd en tidsfryst Stryktipsanalys med verkliga lag, odds och spelstopp.
2. Hämta engelska ligor och kontrollera säsongens coverage för players och injuries.
3. Hitta rätt match genom hemma- och bortalag, liga, säsong och matchtid.
   Om flera matcher matchar samma par: markera okänt.
4. Läs säsongsstatistik per lag och liga med stabila player/team/fixture-ID.
5. Läs frånvaro för exakt samma fixture. Leverantören anger
   Missing Fixture eller Questionable samt möjlig orsak.
6. Rangordna spelarna med minuter, starter, mål, assist och antal framträdanden.
   Om statistik saknas för en rapporterad frånvarande spelare gissas ingen procent.
7. Frys källans hämtningstid före spelstopp och jämför med oddsbaslinjen.

Spelarbetydelse är en heuristik: 52 % relativ speltid,
30 % starter, 18 % mål-/assistproduktion per 90, multiplicerat med
tillförlitlighetsfaktor upp till åtta framträdanden. En bra försvarare får
värde för minuter och starter även utan mål.

En rapporterad definitiv frånvaro får större scenarioeffekt än en osäker.
Flera frånvaror i samma lag summeras med ett tak för att undvika absurda
justeringar. Dessa vikter är inte skattade på historiska matcher.
Det går inte att från säsongsstatistik bevisa exakt vad en spelare
är värd i procent.

## Prognoserna

- ODDS 1/X/2: oförändrad marginalnormaliserad marknadssannolikhet.
- SPELARSCENARIO 1/X/2: illustrativ ändring OM frånvaron inte redan är
  inprisad av spelmarknaden. Det är inte en extra säker vinnarsannolikhet.
- DIFFERENS: procentenheter (p.e.).

När data saknas är scenarioprocenten null, aldrig 0 % och aldrig samma
sak som en bekräftat frisk startelva.

## Datatider, testning och dubbelräkning

Svenska Spels spelstopp och källans hämtningstid är tidszonssäkrade.
Ingen ny scenariofil får skapas efter spelstopp och källan får vara högst
36 timmar gammal vid rapportens skapande. En äldre tidssäker källa kan
jämföras med en senare oddsobservation, men detta innebär inte att
skadeinformationen verkligen var ny för spelmarknaden.

Marknaden kan redan känna till skadorna. För att motivera att en
spelarkorrigering ersätter ordinarie odds måste framtida källfrysta
experiment jämföras mot oddsbaslinjen i Brier/log loss och
hypotetiska lika dyra system. Ingen historisk data får tränas och
utvärderas på samma period. V17 gör än så länge bara scenarier.

Testa: python -m unittest discover -s tests -v

## Driftsättning

Gör ingenting tills publiceringsrättigheterna är utredda.
API-Footballs villkor (https://www.api-football.com/terms) anger att
tjänsten inte själv ger licens för publicering av ligornas data och att
vissa användningar inom betting kan kräva ytterligare rättigheter.
Stryktipslabbet ligger i ett publikt GitHub-repository. Kopiera inte
API-nycklar eller råa leverantörssvar dit.

När rättigheter finns:
1. Registrera ett API-Football-konto och kontrollera i tjänstens
   täckningsverktyg att alla fyra ligorna har spelare/skador för rätt säsong.
2. Lägg API-nyckeln som GitHub Actions repository secret
   APIFOOTBALL_KEY (aldrig i källkod).
3. Skapa GitHub Actions repository variable
   PLAYER_DATA_PUBLICATION_APPROVED med värde 1 först efter
   dokumenterad kontroll av tillämpliga publiceringsrättigheter.
4. Kör arbetsflödet och kontrollera den nya sidan:
   https://johanclaesson0-png.github.io/stryktipslabbet/spelarpaverkan.html
5. Begränsa API-användningen. Adaptern hämtar högst en gång per
   kupong och UTC-dygn och högst 80 anrop per körning.

Vid utebliven nyckel eller rättighetshantering kör Stryktipslabbet vidare
precis som förut utan att fylla på falska spelaruppgifter.

## Filer

- scripts/api_football_adapter.py – kontrollerad frivillig hämtning
- scripts/player_impact.py – nyckelspelarrankning och 1/X/2-känslighet
- tests/test_player_impact_v17.py – säkerhets- och regressionsprov
- spelarpaverkan.html – ny mobilanpassad publiksida
- .github/workflows/player-impact-ci.yml – enbart testkörningar på PR

Datakontrakt:
- data/player_feed/<omgång>.json – begränsat härlett API-underlag
- data/player_impact/<omgång>.json – fryst scenario med källtider
- .site/data/player_impact/latest.json – publiceras endast vid
  aktivt godkända rättigheter och passerad källvalidering

## Nästa kalibreringsfas

Utöka med ordinarie elva de senaste 5–10 matcherna, målvaktsspecifika mått,
lagets prestation med/utan spelaren justerad för motståndarnivå, och
källkontrollerad publiceringstid för frånvaronyheter.