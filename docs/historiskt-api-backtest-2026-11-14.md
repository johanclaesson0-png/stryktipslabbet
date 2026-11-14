# Retrospektivt API-Football-test – 14 november 2026

**Status:** Genomförd, reproducerbar, explorativ känslighetsanalys.
**Fullständig Actions-körning:** https://github.com/johanclaesson0-png/stryktipslabbet/actions/runs/43580656854
**Kod:** [scripts/api_football_historical_backtest.py](../scripts/api_football_historical_backtest.py).

## Vad som faktiskt jämfördes

- Historiskt underlag: 262 Stryktipsomgångar med 3 406 matchresultat från
  2021-11-13–2026-11-07. Historiskt frysta bookmakerodds och streck finns
  **inte** för dessa omgångar.
- Baslinje: projektets Elo-modell som använder *endast tidigare avslutade
  Stryktipsomgångars resultat* per föregående kupong.
- API: API-Football Free, säsong 2022, 2023, 2024; Premier League och
  Championship, där skadeflaggorna är aktiva.
- Matchkoppling: samma kanoniska hemmalag och bortalag, avspark 0–3 dagar
  efter kupongdatum och exakt bekräftat slutresultat.
- Förhandsbestämt urval: de åtta tidigaste säkert kopplade matcherna per
  liga och säsong. **48 matcher från åtta kuponger**, 16 matcher/säsong.
  Varken antalet frånvarande eller resultaten användes för att välja ut
  bland dessa säkert identifierade matcher.
- Förändring: varje "Missing Fixture" är en räkneenhet på logit-skalan,
  och "Questionable" har lägre vikt. Endast rapporterat antal spelare,
  inte individuell spelarkvalitet, användes i *detta* test.
- Testvikter: 0,045 per nettoskillnad i definitivt saknade spelare,
  0,018 per nettoskillnad i tveksamma spelare, maximalt logit-skift
  ±0,22. **Vikterna är inte skattade, tränade eller kalibrerade.**
- En retrospektiv API-rapport får INTE tolkas som verifierad information
  som fanns tillgänglig före den historiska matchen eller spelstoppet.
  API-data hämtades **2026-11-14**, långt efter matcherna.

API-Football Free bekräftades förfråga enskilda historiska matcher via
\`/injuries?fixture=...\`; flera match-ID:n i en batch via \`ids\`
nekades för detta konto med \`errors.plan\`. Därför 57 anrop i den
genomförda körningen. Ingen råleverantörsdata, hemlig nyckel,
spelarnamn eller skadehändelser sparades.

## Faktiskt utfall

| Mått | Elo-baslinje | Med retrospektivt frånvaroscenario | Förändring |
| --- | ---: | ---: | ---: |
| Utvärderade matcher | 48 | 48 | Samma urval |
| Brier score (lägre = bättre) | 0,602660 | 0,584088 | −0,018572 (−3,08 %) |
| Log-loss (lägre = bättre) | 1,009623 | 0,984944 | −0,024679 (−2,44 %) |
| Rätt för högst sannolika 1/X/2 | 30/48 (62,50 %) | 29/48 (60,42 %) | −1 rätt |
| Matcher där sannolikheten faktiskt ändrades | — | 44/48 | — |

Parat 95-procentigt *dragblock-bootstrap*-intervall för förbättringen i
Brier score: **[0,000091; 0,038393]**. Det bygger dock bara på **8
kuponger som oberoende dragblock**, med ett kronologiskt och
icke-representativt litet matchurval. Ett sådant intervall styrker
inte i sig generaliserbarhet eller pre-match-prediktiv förmåga.

### Uppdelat per historisk API-säsong

| Säsong | Matcher / kuponger | Elo Brier | Med frånvaro Brier | Skillnad (positivt = bättre) |
| --- | ---: | ---: | ---: | ---: |
| 2022 | 16 / 3 | 0,626685 | 0,619690 | +0,006995 |
| 2023 | 16 / 3 | 0,603664 | 0,568772 | +0,034893 |
| 2024 | 16 / 2 | 0,577632 | 0,563802 | +0,013830 |

## System: exakt samma radkostnad

Jämförelserna gäller **8 kuponger med minst en förändrad prognos**, där
kuponger med icke matchade ligor behåller sin ursprungliga Elo-sannolikhet.

| System | Radkostnad per omgång | Omgångar där systemet ändrades | Minst en rad med exakt 10 rätt (Elo → frånvaro) | Exakt 11 rätt | Exakt 12 rätt | Exakt 13 rätt |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Budget högst 100 kr | 96 kr | 7/8 | 2 → 3 | 0 → 1 | 0 → 0 | 0 → 0 |
| Budget högst 1 800 kr | 1 536 eller 1 728 kr | 7/8 | 6 → 7 | 4 → 3 | 0 → 0 | 0 → 0 |

**Observera:** Tabellen räknar antalet *kuponger med minst en vinnande
rad i varje separat rättklass*, inte antalet totala rader eller
bekräftade utbetalningar. Samma kostnad jämförs inom varje enskild
omgång, inte en blandning av olika budgetar.

## Vad resultatet INTE bevisar

1. Att spelaruppgifter var kända före spelstopp. Ex post-rapporterade
   skador kan skapa tidsläckage. Detta är inte en riktig walk-forward
   spelarmodell, till skillnad från den ursprungliga Elo-baslinjen.
2. Att samma förbättring uppstår på nya matcher: 48 matcher, 8 kuponger,
   selektion på säker matchidentitet och ingen oberoende kontrollperiod.
3. Att individuell *nyckelspelarbetydelse* har validerats: endast antal
   frånvarande testades. Ingen beräknad individuell kausal påverkan.
4. Att marknadsmodellen förbättrats: faktiska historiskt frysta odds
   saknas. Historiska bookmakerodds kan redan ha reflekterat frånvaro.
5. Att lönsamheten ökar: ingen tillförlitlig historisk streck-/oddssnapshot
   eller fullständigt officiellt utbetalningsunderlag användes.

## Fortsättning

- Större testgrupp över fler kuponger och fler ligor, stratifierat i tid,
  utan att välja om vikter efter dagens resultat.
- Endast tidsstämplade källor kända *före spelstopp* när modellen ska
  kallas validerad inför riktiga matcher.
- Nyckelspelarkvalitet bör bygga på *tidigare* minuter/starter och
  verifierad lagidentitet, aldrig säsongens slutstatistik efter match.
- Behåll de ursprungliga systemen och API-frånvaro-scenariot sida vid
  sida tills resultaten håller på oberoende tester.
