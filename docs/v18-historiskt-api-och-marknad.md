# Version 18 – tre separata tester med API-Football

## 1. Större historiskt test (frånvarofrekvens)

V17-testet den 14 november 2026 använde 48 matchningar (2022–2024)
och 8 kuponger. Testet visade ett retrospektivt Brier-fel på 0,602660
för Elo och 0,584088 med antal rapporterat frånvarande spelare.
Det var **inte ett tidsfryst spelbart backtest**: gamla API-skaderapporter
hade ingen verifierad publiceringstid före match.

V18 kör samma förregistrerade vikter på **icke överlappande, kronologiska
batchar** med upp till åtta nya matcher per liga och API-säsong,
sammanlagt högst 48 matcher per körning. Varken matchutfall,
antal skadade eller efterföljande Brier används för att välja matcher.
Vikterna är fortsatt 0,045 per definitivt saknad och 0,018 per osäker,
med maxsignal ±0,22.

Gratisplanen tillåter enskilda historiska \`injuries?fixture=...\`,
men **inte** batchparametern \`ids\`; därför högst 65 API-anrop
per körning med minst 6,5 sekunder mellan dem. Ingen rårespons lagras.

- Automatiserat flöde: [V18 utökad historik](https://github.com/johanclaesson0-png/stryktipslabbet/actions/workflows/v18-history-expansion.yml)
- Schemalagt på söndagar 05:21 UTC. Batch 1 är veckan som börjar
  15 november 2026; sedan nästföljande icke överlappande batch.
- Manuellt kan ett specifikt batchindex 1–40 anges. Välj samma
  index igen för reproduktion, inte som en ny oberoende observation.
- Körningen redovisar Brier, log-loss, top1, 95%-bootstrap per
  kupong och teckensystem med exakt samma radkostnader.
- En körning med slut på API-kvoten eller för få säkert matchade
  matcher får **inte** rapporteras som verifierad förbättring.

**Viktigt:** varje körning ger separat sammanfattning i GitHub Actions.
Kombinera inte dessa som om de vore ett gemensamt tränings-/teststickprov
utan kontroll för återanvända kuponger och tidigare modellval.

## 2. Nyckelspelarnas betydelse från *tidigare* minuter och starter

V18:s viktade jämförelse får aldrig använda hela den historiska säsongens
slutstatistik som om den funnits tillgänglig vid en match mitt i säsongen.

I stället väljs de tre närmast **föregående spelade matcherna**
i samma liga och säsong för varje lag. API:t läser
\`fixtures/players?fixture=...\` och använder endast:

- spelade minuter per spelare i de tidigare matcherna,
- om spelaren startade eller kom in som avbytare.

Betydelsen är en *heuristisk ranking inom laget*:
55 % relativ minutandel och 45 % relativ startandel.
Frånvaroeffekten är 0,065 gånger relativ betydelse per
definitivt frånvarande spelare, med 40 % av vikten för en
osäker spelare och total maxsignal ±0,20.
Dessa koefficienter har inte tränats på matchresultat.

Om äldre data för skadad spelare saknas står **okänd betydelse**.
Får inte gissas till noll eller en godtycklig nyckelspelarvikt.
När datakvaliteten inte når minimikraven redovisas matchen
som ej utvärderbar med denna modell.

- [V18 viktad historik](https://github.com/johanclaesson0-png/stryktipslabbet/actions/workflows/v18-prior-player-weighting.yml)
- Schemalagt torsdagar 05:29 UTC, separat från större historik
  så API-Footballs fria dygnskvot inte delas mellan testerna.
- En körning tar högst en match per liga/säsong med upp till tre
  tidigare matchers spelarrapporter per lag; högst 85 API-anrop.
- Jämför Elo, enkel frånvaro och viktad frånvaro på **samma
  utvärderbara matcher**; samma radkostnad på alla system.

Förutsättning: API-Football ger åtkomst till \`fixtures/players\` i
de valda historiska säsongerna. Om den endpointen är spärrad
eller saknar tidigare individuella minuter ska modellen **inte**
framställa en beräknad förbättring.

## 3. Prognos mot verkligt förhandsfrysta odds och streck

\`scripts/market_player_audit.py\` körs varje normal
Stryktipslabbet-insamling och producerar en **anonym, aggregerad
revisionsstatus** i \`data/market_audit/latest.json\`.
GitHub Pages publicerar bara en allowlist av dessa aggregat.

För att en spelarrapport ska få ingå måste den och oddsen:
1. tillhöra samma Stryktipsomgång,
2. ha *identiskt* tidsfryst käll-SHA och tidsstämplad
   ursprungsobservation,
3. komma från en verifierad råodds- och strecksnapshot före spelstopp,
4. ha API-insamling efter eller samtidig med den ursprungliga
   oddsobservationen och både insamling + rapport före spelstopp,
5. ha en rapport vars hypotetiska sannolikheter kan återskapas
   exakt från originalkällorna,
6. ha ett senare officiellt resultat enligt projektets giltighetskontroll.

Matchresultat får aldrig användas till att ändra ett redan
fryst marknads- eller spelarscenario. Om något saknas redovisas
**ingen jämförelse** och inga gissade utfall/odds.

- [V18 instrumentpanel](https://johanclaesson0-png.github.io/stryktipslabbet/historiskt-api.html)
- Äldre arkivet innehåller 262 omgångar/3 406 slutresultat
  men saknar gamla tidsfrysta odds och streck; det går därför
  inte att ge historisk odds-baserad ROI för dem.
- API-Footballs gratisplan ger bara historiska säsonger.
  Innan rättigheter till offentlig publicering är klarlagda
  förblir automatisk publicering av API-spelaruppgifter avstängd.
  Marknadsrevisionen får då sanningsenligt visa noll godkända par.
- Endast utvärderade par bör användas för att jämföra
  Brier och log-loss; mer data och oberoende perioder krävs
  innan kausala eller ekonomiska påståenden kan göras.

## Körtester

\`python -m unittest tests.test_api_football_historical_backtest tests.test_v18_player_backtests -v\`

\`python -m scripts.market_player_audit\`

Det normala \`python -m unittest discover -s tests -v\`
ingår även i GitHub Actions. Ovanstående offline-prov
kräver **ingen API-nyckel**.
