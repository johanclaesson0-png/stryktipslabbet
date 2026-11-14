# V19 – modellutvärdering och beslutsmotor

Version 19 inför en **bevisbaserad kontroll** av nya faktorer och en
**hypotetisk** beslutsstudio för 100 kr och högst 1 800 kr. Versionen
ändrar inte ordinarie prognoser, inlämning eller budgets.

## 1. Vilken modell tillför något över oddsen?

Utgångspunkt: odds från Svenska Spel, omräknade till summa 100 %.

En historisk match räknas som prospektivt utvärderbar bara om:

1. Den kommer från en **äkta, arkiverad råsnapshot med SHA**, som
   redan fanns **minst 30 minuter före omgångens spelstopp**.
   För varje kupong väljs deterministiskt **den senaste** råsnapshoten
   före denna gräns, oavsett matchresultat eller hur många prognoser
   som senare råkar finnas.
2. Baslinjen **rekonstrueras** från just denna snapshot med
   \`scripts.analyze.create_analysis\`. Inga gamla odds gissas.
3. Formanalysen måste härröra från **samma snapshot/SHA**, ha skapats
   före spelstopp och gå att reproducera från arkiverade förhandsfakta.
   Finns formrapporten men det verifierbara källunderlaget inte längre
   kvar, räknas den **inte** som en utvärderbar datapunkt.
4. Spelarscenariot behöver tidsstämplade källor före spelstopp,
   identiskt SHA och vara reproducerbart från sitt API-flöde. Gamla
   frånvarorapporter som hämtades i efterhand räknas **inte**.
5. Utfallet måste vara ett senare verifierat **officiellt facit**.
6. Olika faktorer bedöms **parvis på samma delmängd av matcher**.
   En faktor får aldrig gynnas av att jämföras med en annan omgång.

Mätetal: Brier score, log-loss och topp-1-träffar; lägre Brier och
log-loss är bättre. Osäkerhetsintervall beräknas med 1 500 parvisa
bootstrap-samplingar på **kupongnivå**, inte som 13 oberoende
observationer i samma kupong.

En faktor kan bli **kandidat för manuell prövning**, men inte
automatiskt aktiverad, endast när den har:

- minst **30 självständiga kuponger**,
- minst **300 jämförbara matcher**,
- bättre Brier med minst **0,004** samt bättre log-loss,
- **95 % bootstrapintervall** för Brier-förbättring med positiv
  nedre gräns,
- positiv förbättring även i **senaste tredjedelen** av kupongerna,
  vilket måste omfatta minst **10 kuponger**.

Dessa krav är försiktiga beslutsgates, inte statistisk garanti för
lönsamhet. Rättigheter till externa data bedöms separat.
Beslutsmotorn tillämpar ALDRIG en faktor automatiskt.

Streckvärde bedöms **inte** som en ny sannolikhetsmodell utan
enbart som en systemurvalsmetod: väljs fler 10–13-rättsrader
och vad skulle de hypotetiska utbetalningarna vara? Ingen
oberoende historisk utdelningsinformation hittas på.

### Små och ofullständiga underlag

- 0 riktiga jämförelser = **otillräckligt underlag**.
- En liten positiv förbättring = **lovande men osäkert**.
- Samma utfall/försämring = **ingen påvisad förbättring**.
- Uppnått minimiantal men otillräckligt stöd = **osäker eller
  ingen förbättring**.
- Först med alla krav ovan = **tillräckligt stöd för manuell
  prövning**. Aldrig ”garanterat bättre” eller ”automatisk spik”.

Retrospektiva 48 matcher med API-Football och femårig Elo-historik
visas separat; dessa är inte bevis för bättre förhandsprognoser
än bookmakerodds.

## 2. Beslutsstudio: spikar, garderingar och 100 / 1 800 kr

\`scripts.v19_decision\` läser samma förhandsfrysta kupong som
ordinarie modell och originalsystem. Den gör sedan:

- **Originalsystem:** de faktiska system som Stryktipslabbet redan
  bygger för 100 kr respektive upp till 1 800 kr.
- **Formscenario:** exakt samma rader/kostnad som original,
  från en omräknad formmodell där både källa och modell går att
  verifiera.
- **Streckvärdescenario:** exakt samma rader/kostnad, men med den
  redan befintliga prioriteringen av populära/underskattade
  tecken. Det är ingen verifierad förväntad utdelning.
- **Match för match:** normaliserade 1/X/2-sannolikheter,
  folkets procentfördelning, skillnad i procentenheter och
  vilka tecken som byts ut i varje experiment.
- **Granskningsordning:** transparent heuristik med
  störst odds–folket-skillnad först, plus
  antal avvikande systemsymboler. Den är en
  granskningsprioritering och inte en vinstrangordning.

Vyn låter användaren välja budget och visa enbart ändrade
tecken. Den kan inte spela, ändra original eller ta betalt.

## 3. Källrättigheter och automatisk uppföljning

Den normala GitHub Actions-körningen gör:

\`python -m scripts.v19_evaluation --outdir data\`

\`python -m scripts.v19_decision --outdir data\`

Då skapas \`data/v19/evidence.json\` och
\`data/v19/decision.json\`. Publikationssteget kopierar bara
marknadsbaserade, validerade beslutsdata och **aggregerade**
resultat, och publicerar aldrig externa spelares identiteter
eller API-Football-flöden. Spelarfaktorns interna underlag
får inte publiceras utan rättighetsklartecken.

När det inte finns en aktiv öppet observerad kupong eller när
väsentligt underlag saknas ska sidan tydligt visa **ingen
verifierad jämförelse**, inte fabricera ett system eller ett
positivt backtest.

[Öppna V19-sidan](https://johanclaesson0-png.github.io/stryktipslabbet/v19-beslutsstudio.html).

## Tekniska kontroller

\`python -m unittest discover -s tests -v\`

\`python -m scripts.v19_evaluation --outdir data\`

\`python -m scripts.v19_decision --outdir data\`

V19-testerna verifierar upprepningsbar snapshot-låsning, 
avsaknad av framtidsinformation, parvis utvärdering,
kostnadslås, källmatchning och att otillräckliga data inte
kan ge en falsk ”verifierad förbättring”.
