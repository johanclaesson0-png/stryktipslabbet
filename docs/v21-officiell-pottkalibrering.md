# V21 – officiell omsättning, vinnande rader och hederlig pottkalibrering

## Syfte

V20:s beräknade netto i kronor var ett **illustrativt scenario** eftersom
slutlig omsättning, verkliga vinnarrader, deltagarnas kombinerade tecken
och jackpot saknades. V21 gör en tydlig åtskillnad mellan två typer av
historiska jämförelser:

1. **Officiella avslutade omgångar:** faktisk omsättning
   \`result.currentNetSale\`, verkliga antalet vinnande *rader*
   \`result.distribution[].winners\` samt kronor per rad
   \`result.distribution[].amount\`. Dessa data kan granskas långt bakåt.
   De är **efterhandsfacit** och kan användas för utdelningsstatistik
   och redovisningskontroll, inte för att återskapa dåtidens odds.
2. **Verklig förhandsvalidering:** bara om Stryktipslabbet redan före
   spelstopp sparat ett SHA-verifierat 13-matcher-streckunderlag för
   exakt samma omgång och om senare officiella vinnarsiffror finns
   får modellen testa det oberoende antagandet om hur många andra
   spelare som får 10/11/12/13 rätt. Inga framtida data används
   i prognosen.

Primärkälla:
\`https://api.spela.svenskaspel.se/draw/1/stryktipset/draws/{draw}/result\`.

Den 14 november 2026 verifierades direkt mot Svenska Spels API:
omgång 4978 omsättning **33 004 181 kr** och 9/438/6 341/54 475
vinnarrader för 13/12/11/10 rätt; omgång 4977 omsättning
**48 392 935 kr** och 63/1 880/25 449/197 996 vinnarrader.
Siffrorna stämmer med motsvarande publicerade tabell hos
https://stryktipsetdata.se/stryktipset/utdelning, men
**själva arkivimporten kommer från Svenska Spels API**, inte
från tredjepartssajten.

## Kod och uppdateringar

\`scripts/v21_pool_history.py\`:

- hämtar offentliga resultat under en begränsad förfrågningskvot
  (max 80, normalt 24 per körning),
- läser \`currentNetSale\` i kronor via decimalformat med kommatecken,
- kräver fyra unika vinstgrupper med icke-negativa antal vinnarrader,
- verifierar samma resultat/utdelning mot våra tidigare
  **262 redan officiellt kontrollerade** resultat från
  \`data/history/payouts.json\`,
- lagrar enbart offentlig, kompakt numerisk metadata
  i \`data/history/official_pools.json\`,
- sparar läget i \`data/history/official_pools_state.json\`
  och hoppar över tidigare kontrollerade omgångar.

Körning sker som en del av ordinarie GitHub Actions-workflow;
fel i det offentliga nätverket stoppar inte publiceringen.
\`scripts/v21_calibration.py\` bygger en aggregerad
\`data/v21/calibration.json\`.

\`scripts.collect.parse_draw\` sparar även
\`observed_turnover_so_far_kr\` när den offentliga öppna
kupongen ger \`currentNetSale\`, tillsammans med
\`sales_observed_at_utc\`. Det är **inlämnat hittills** och
får aldrig kallas slutlig omsättning eller
retroaktivt ges som värde för en gammal observation.

V20:s ursprungliga simulator sparas nu som
\`data/v20_history/{draw}.json\` när den gamla kupongen stängs
eller byts mot en ny. Bara en redan genererad **förhandsmodell**
får utvärderas mot officiellt resultat efteråt.

## Vad V21 mäter

### A. Historiskt facit (kan sammanställas utan gamla odds)

- Antal officiellt verifierade omgångar
- Median och 10–90-percentiler för faktisk omsättning
- Antal vinnarrader 13/12/11/10 rätt, median och spridning
- Faktisk utdelning per rad, median
- Redovisningskvot:
  \`verkliga vinnarrader × utdelning per rad /
  (slutlig omsättning × 65 % × klassens andel)\`.

Den sista kvoten är **en efterhandskontroll av en förenklad
pottformel**, inte en utvärdering av oddschanser, och
påverkas av jackpottar, garantier, avrundningar och
omfördelade potter.

### B. Modellfel för andra vinnare (kräver samma kupongs frysta streck)

För varje historiskt utfall, om förhandsstreck finns sparade
från samma omgång, beräknas Poisson-binomial-sannolikheten
att en hypotetisk konkurrentrad fått exakt 13, 12, 11, 10 rätt.
Antalet förväntade vinnarrader sätts illustrativt till
\`slutlig omsättning × sannolikheten\`.

Jämför därefter verkliga vinnarrader med modellens resultat
med median av faktiskt/förväntat och logaritmisk felfunktion.
Detta kan kalibrera fel från att anta oberoende tecken;
inga sådana slutsatser dras förrän **20 olika kuponger**
finns i den prospektiva jämförelsen.

V21 visar inga bakåtberäknade ”odds” för våra
262 äldre resultatrader. Endast verkligen arkiverade
förhandsstreck gäller.

### C. Verklig rättning av frysta V20-system

Om \`data/v20_history/{draw}.json\` har en till
samma råsnapshot kopplad, tidsfryst V20-modell från
före spelstopp, räknas den senare mot **officiell
utdelning** för 10/11/12/13 rätt och verkligt netto.
Systemen i jämförelsen måste ha exakt samma radkostnad.

Detta är en utvärdering av *hypotetiska förhandsbeslut*,
inte bevis på att någon faktisk rad spelats eller
att förväntad vinst var positiv. Efterhandsomsättning
används aldrig som indata till originalprognosen.

## Rättigheter och publicering

Webbplatsen \`v21-verklig-pott.html\` publicerar bara
officiella aggregerade efterhandsvärden och
metadatastatus. Inga API-Football-spelarnamn,
API-nycklar, råa Svenska Spel JSON-objekt eller
personliga vinstärenden publiceras. Ingen
automatisk inlämning eller ändring av radbudgeten.

## Begränsningar

- Korrelation mellan spelade rader, poolomfördelning,
  jackpot och ensamvinstgaranti är ännu inte lösta
  genom att vi känner det verkliga historiska
  antalet vinnare.
- Omsättningen \`currentNetSale\` i en **öppen**
  omgång är tidstämplad summa hittills, inte
  framtida slutvärde.
- Historiska faktiska utfall får **inte**
  användas för att välja vikter och därefter
  rapportera samma historik som oberoende test.
- För 2021–2026 har vi 262 resultatrader med
  officiella utdelningsbelopp. Det utökade
  omsättnings-/vinnarradsarkivet byggs stegvis.
  Jämförbara förhandsrader samlas först när
  modellen och råstrecken varit sparade före matcherna.

## Körning

\`python -m scripts.v21_pool_history --outdir data --limit 24\`

\`python -m scripts.v21_calibration --outdir data\`

\`python -m unittest tests.test_v21_pool_history -v\`

[Öppna V21:s verkliga historik](https://johanclaesson0-png.github.io/stryktipslabbet/v21-verklig-pott.html).
