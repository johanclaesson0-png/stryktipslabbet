# Version 20 – pott, kronor och skrällorienterade M-system

**Status:** teknisk, hypotetisk scenariomodell. Inte en verifierad
utdelningsprognos, spelrekommendation eller optimerad förväntad ROI.

## Bakgrund och källa

Stryktipset har enligt Svenska Spels officiella vinstplan:

- **65 % återbetalningsandel** av omsättningen,
- av vinstmedlen **40 % för 13 rätt**, **15 % för 12 rätt**,
  **12 % för 11 rätt**, **25 % för 10 rätt**,
- resterande **8 % av vinstmedlen** till garantifonden.

Källa:
https://spela.svenskaspel.se/fotboll/premier-league/stryktipset

Stryktipsets faktiska vinstbelopp beror på hur många vinnande rader
spelarna lämnat, jackpot och övriga spelregler. De gamla frysta
Stryktipslabbet-snapshotsen innehåller **odds och streck**, men ännu
inte verifierad omsättning som kan knytas till exakt samma tidpunkt
eller data om hur andra spelare **kombinerat** sina tecken.
V20 får därför **inte** använda oriktigt exakta kronbelopp.

## Modell

1. Läs exakt samma verifierade odds- och strecksnapshot som
   ordinarie Stryktipslabbet; aldrig matchresultat eller API-data
   efter spelstopp.
2. Bygg ett originalsystem för 100 kr och 1 800 kr (faktisk
   matematiskt möjlig radkostnad kan vara 96 respektive 1 458 kr).
   Bygg dessutom fyra experimentella system till **exakt
   samma kostnad** med fasta streckviktsexponenter
   0,25 / 0,45 / 0,70 / 1,00.
3. Sampla 6 000 möjliga kupongresultat från
   normaliserade förhandsodds, med samma slumpade resultat för
   alla jämförda strategier. Slumptalsfrö är fast:
   \`SEED=20261120\`.
4. Beräkna sannolikheten att en slumpmässigt simulerad
   konkurrentrad får precis 13, 12, 11 eller 10 rätt mot
   respektive resultatrad. Detta görs med en
   **Poisson-binomial-fördelning** där varje match antas vara
   **oberoende av övriga** för både resultat och spelade tecken.
5. Anta en omsättning på antingen 5, 15 eller 30 miljoner
   kronor (medvetet hypotetiska värden).
6. Anta att antalet konkurrentrader i en vinstklass är
   hälften, enligt modellen eller dubbelt så många. Det
   är **känslighetsscenarier**, inga 50 %/95 %-konfidensintervall.
7. Antagen vinst per egen rad i klass *k* är klassens
   vinstpott delat med summan av uppskattade andra vinnande
   rader och egna vinnande rader. Utbetalningar under 15 kr
   per rad behandlas förenklat som 0. Faktiska
   reallokeringsregler, ensamvinstgaranti och jackpot
   är **inte** implementerade.
8. Sammanställ **illustrativa** kronor netto, andel
   simuleringar med positivt netto, andel med 13-rättsrad,
   90:e percentilen och endast Monte Carlo-felmarginal
   (inte felmarginal för de viktiga modellantagandena).
9. Rangordna alternativen i *varje* antagandescenario
   efter simuleringens medelnetto. Det är **inte** ett
   godkänt val eller förbättrad verklig avkastning.

## Skrällindikatorer

För varje tecken *i* där oddssannolikheten *p* är större
än folkets andel *c* och *p* ligger mellan 6 % och 50 %
listas skillnaden *p-c* i procentenheter. Ett ovanligt
tecken är inte automatiskt ett bra val. Särskilt
flera ovanliga tecken tillsammans kan ge ett svårt
13-rättsspel, även om utdelningen blir hög om de går in.

## Risker och vad som återstår

- Streckprocent i en match är **marginaler**. Vi vet inte
  vilka kombinationer av tecken folk har spelat.
  Dessa rader är **korrelerade** och kupongen kan även
  innehålla reducerade system. Oberoende är därför
  en grov och särskilt vid skrällutfall riskabel approximation.
- Omsättningsvärdena är användarvalda scenarier,
  **inte** liveomsättning och **inte** säkra prognoser.
- Jackpot, ensamvinstgaranti, tak och överföring mellan
  klasser kan ge helt andra utbetalningar.
  V20 är alltså inte en exakt implementation av
  Svenska Spels regelbok för utdelning.
- Monte Carlo kan missa extremt sällsynta fullträffar.
  Intervallet avser endast simuleringsslumpen, och
  kan inte tolkas som tillförlitlig framtida ROI.
- Tidigare 262 omgångar saknar komplett tidsfryst
  odds-/streck-/omsättningshistorik och kan inte
  retroaktivt ge en validerad kronavkastningsanalys.
- De ordinarie Stryktipslabbet-systemen, pengarna,
  budgetarna och inlämningen ändras **inte**.

## Nästa verifieringssteg

- Hitta och tidsfrys omsättning från **officiell källa**,
  först om det går att binda till samma omgång och
  förhandstid. Visa källa och observationsdatum.
- Samla tillräckligt många avslutade kuponger med
  verifierade slututdelningar och sanningssäkra
  förhandsstreck. Mät faktisk hypotetisk nettoavkastning
  för original, streckprofiler och pottprofil
  på **samma kostnader**, utan efterhandsjusterade vikter.
- Kalibrera spridningen i antalet andra vinnande rader
  mot verkliga, historiska vinnarantal, inte enbart mot
  marginalstrecken. Gå från antagen till uppmätt
  pottmodell först när sådan data finns.

## Körning

\`python -m scripts.v20_payout_simulator --outdir data\`

\`python -m unittest tests.test_v20_payout_simulator -v\`

Körs automatiskt före spelstopp i GitHub Actions.
Resultatet sparas i \`data/v20/simulator.json\` och
visas enbart för en verifierat öppet spelomgång.

[Öppna V20-sidan](https://johanclaesson0-png.github.io/stryktipslabbet/v20-pottanalys.html).
