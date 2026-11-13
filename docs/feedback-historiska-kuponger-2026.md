# Feedback från 39 historiska Stryktipskuponger

**Sammanställd:** 13 november 2026  
**Status:** Backtest/diagnostik, **inte** bevis på prediktiv modellfördel eller framtida vinst.  
**Omfattning:** 39 unika kuponger, 15 november 2025–7 november 2026, totalt 507 matcher. Varje kupong har 13 teckenrader i den privata genomgången.  
**Integritet:** Här dokumenteras **enbart aggregerade siffror och utvecklingsförslag**. Enskilda lagkuponger och detaljerade tecken läggs inte i det offentliga repositoryt.

## Vad resultaten faktiskt visar

| Mått | Resultat |
| --- | ---: |
| Kuponger | 39 |
| Matcher | 507 |
| Insatser | 61 212 kr |
| Utdelningar enligt historikgenomgången | 7 247 kr |
| Netto | −53 965 kr |
| Kuponger med nettovinst | 2 av 39 |
| Kuponger utan utdelning | 24 av 39 |
| Täckta matcher per kupong | 9,05 i genomsnitt |
| Rader med 13 / 12 / 11 / 10 rätt | 0 / 2 / 31 / 228 |
| Spikar | 159; 77 rätt, 82 fel (51,6 % fel) |
| Halvgarderingar | 236; 164 rätt, 72 fel (30,5 % fel) |
| Helgarderingar | 112; samtliga resultat täcks per definition |
| Matcher som slutade 1 / X / 2 | 214 / 136 / 157 |
| Missade utfall 1 / X / 2 | 40 / 60 / 54 |
| Missade X vid spik | 46 av 82 felspikar |
| Missade X vid halvgardering | 14 av 72 felhalvgarderingar |
| Omgångar med över 1 800 kr i insats | 1 (1 944 kr) |

**Viktiga tolkningar:**
- 82 felspikar utgör 53,2 % av alla 154 missade matcher. Även halvgarderingarna förklarar mycket (46,8 %).
- 60 av 136 kryss missades, men detta kan **inte** ensamt visa underbetting av X. Jämför frekvensen med ex ante-prognos, odds och kupongstreck. Det är naturligt att favorittecken oftare är 1 än X.
- En helgardering ger aldrig en missad match, men kostar fler rader. Hur garderingar bör fördelas kan inte utläsas av de faktiska resultaten efteråt.
- Ett system kan täcka 12 matcher utan att göra vinst om utdelningen är låg; nettot beror på antalet vinnande systemrader i varje prisklass, insats, potter och spelarnas streck.
- Några historiska matcher var **lottade**; markera dessa separat och uteslut dem från bedömning av fotbollsprognosernas kalibrering. De kan fortfarande påverka riktig kupongrättning enligt officiella regler.
- Systemen har olika insats. Jämför därför ekonomiskt resultat i kronor **och per satsad krona**. Äldre Elo-modelltest är efterhandsrekonstruktion, skilt från den nya oddsbaserade, tidsfrysta modellen.

## Rekommenderade åtgärder – prioriteringsordning

### P0 – Rättvis historik, korrekta mått

- [ ] Spara inskickad (eller hypotetisk) systemprofil, budget, tidsstämpel, odds och streck **före spelstopp**.
- [ ] Skilj på faktiska inlämnade system, hypotetiska förhandsprognoser och efterhandsrekonstruktioner. Visualisera detta tydligt på sidan.
- [ ] Spåra officella utdelningar per 13/12/11/10 rätt, inklusive nollutdelning i lägre kategorier, och beräkna antal vinnande rader exakt.
- [ ] Markera lottade/inställda matcher och utvärdera fotbollsmodellen bara på faktiskt spelade matcher.
- [ ] Håll det privata lagets råa kuponger utanför publikt GitHub. Endast aggregerad feedback publiceras.
- [ ] Validera totaler och dubbletthantering när nya uppladdade kuponger tillkommer.

**Godkänt när:** ex ante-test kan återupprepas utan framtidsinformation; resultat och källstatus kan granskas per omgång.

### P1 – Spiksäkerhet och X-bedömning

- [ ] Visa enkel *spikrisk*: uppskattad risk att den valda spiken inte inträffar, med tydlig varning om hög osäkerhet.
- [ ] Jämför varje möjlig spik med matchens **alla tre förhandsalternativ**; använd marknadsbaserad sannolikhet som baslinje.
- [ ] Testa spiktrösklar på helt separata framtida omgångar; optimera inte tröskeln på samma 39 historiska kuponger.
- [ ] Visa särskild X-indikator där sannolikhet för oavgjort är hög relativt övriga utfall. Undvik generell regel att alltid lägga till X.
- [ ] Redovisa kalibrering (Brier score, log loss) och jämförelse mot normaliserade odds, uppdelat på 1/X/2 och på spelade respektive lottade matcher.

**Godkänt när:** ett förregistrerat förslag förbättrar riktiga framåtprognoser i kalibrering eller annan förvald indikator jämfört med baslinjen; inte bara antal träffar i efterhandsdata.

### P2 – Bättre garderingar för given budget

- [ ] Jämför alternativa matematiska M-system för **samma budget**, 100 respektive 1 800 kr.
- [ ] Visa tre tydliga mål: (a) störst oddsbaserad chans till 13 rätt, (b) variation/skrällfördelning, (c) preliminärt uppskattat värde i pott – det sista kräver robust pott-/streckmodell.
- [ ] Ange tydligt att streckvärde *P−streck* **inte** är bevis på positivt väntevärde i poolspel.
- [ ] Visa vad det kostar att lägga till X eller 2 i en viss spik och vilken modellsannolikhet som då tillkommer; gör beräkningen i **hela systemrader**.
- [ ] Redovisa inte förväntad ekonomisk avkastning när nödvändiga pott- och förhandsdata saknas.

**Godkänt när:** systemförslag har verifierat antal rader och kostnad och kan jämföras på samma spelstoppstidpunkt.

### P3 – Separat eget spel (100 kr) och andra spel

- [ ] Följ 96-kronorssystemet **separat** från lagets system på 1 800 kr.
- [ ] Jämför Topptipset (8 matcher) och Europatipset (13 matcher) bara när deras egna verifierade kuponger, odds, streck, facit och utdelningar finns.
- [ ] Kommunicera realistisk risk: liten insats minskar beloppet som kan förloras per omgång, men innebär inte att strategin har positivt väntevärde.

## Föreslagna dashboardsignaler

1. **Inför omgången:** senaste oddsobservation, tydlig ålder på data, spikval, spikrisk, fördelning av 1/X/2, budget/rader och modellversion.
2. **Efter omgången:** täckta matcher, rader med 10–13 rätt, faktisk/hypotetisk utdelning, netto, resultat från lottning (flagga).
3. **Över tid:** Brier/log loss per tecken, andel rätt spikar, resultat per insatt krona och jämförelse mot marknadsbaslinjen, med osäkerhet och antal testade omgångar.

## Metodförbehåll

Den privata 39-omgångssammanställningen har rekonstruerats från skärmbilder och kompletterande historiskt facit. Den kan innehålla avläsnings- och matchningsfel och är **inte** en oberoende revision av Svenska Spels kvitton. Före varje framtida ROI-beslut bör insatser och utbetalningar stämmas av mot faktiska kontoutdrag eller officiella omgångsresultat.

Vi kan inte från dessa 39 historiska utfall fastställa att någon viss spik, X-regel eller modell ger vinst framåt. Därför ska åtgärderna ovan betraktas som testbara hypoteser, inte vinnande regler.

**18+ — Spela ansvarsfullt, sätt förlustgräns.**
