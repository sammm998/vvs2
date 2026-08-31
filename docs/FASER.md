# Faser — prompter att klistra in i Claude Code

Kör en fas i taget. Varje fas har en stoppgrind. Gå inte vidare när grinden inte är
uppfylld — det var vad som skapade version 1–4.

Lägg `CLAUDE.md` i repo-roten först. Claude Code läser den automatiskt.

---

## Fas 0 — Triage-probe

**Detta är dagens viktigaste arbete och det får kastas bort efteråt.** Hela
arkitekturen vilar på två hypoteser. Testa dem innan något byggs.

```
Skriv ett engångsskript scratch/probe.py som körs på data/W-50-1-A-0011.pdf och
data/W-50-1-A-0032.pdf. Det ska svara på fem frågor och skriva ut svaren rakt i
terminalen. Kasta inget, spara utskriften.

1. Finns OCG-lager? Skriv ut doc.get_ocgs() och antal banor per lager.
2. Finns riktig PDF-text? Antal textobjekt, och andel av dem som ligger innanför
   den största inramade tomma ytan.
3. Stilinventering: gruppera alla banor på (kvantiserad stroke-färg, linjebredd
   avrundad till 2 decimaler, strecksignatur, lager). Skriv ut klustren sorterade
   på total längd: antal banor, total längd i punkter, andel av ritningen.
4. Rendera varje kluster som en egen PNG-overlay ovanpå sidan, i out/probe/, ett
   klart färgat lager per bild. Filnamn med klusterindex.
5. Skalstock: finns vektorobjekt med regelbundna delstreck i ramzonen? Skriv ut
   deras koordinater och eventuella närliggande siffror.

Använd pymupdf. Ingen abstraktion, inga klasser, inga tester. Ett skript.
```

**Titta sedan på bilderna själv.** Frågorna du ska besvara:

- Ligger rörstråken i ett eller två kluster, eller är de utspridda över åtta?
- Finns ett kluster som uppenbart är väggar? Ett som är hänvisningsstreck?
- Finns fler kategorier än en, det vill säga syns befintliga eller rivningsrör i
  separata kluster? Detta är spåret till 605 m mot 213,7 m.

**Stoppgrind:** rören ska vara identifierbara som ett eller två stilkluster på 0011.
Är de det inte behöver arkitekturen ändras innan fas 1, och du bör komma tillbaka med
utskriften.

Om `get_ocgs()` returnerar lager är du på spår A och resten blir väsentligt enklare.

---

## Fas 1 — Repo, extraktion, normalisering, facit, evaluate-skelett

```
Sätt upp repot enligt strukturen i CLAUDE.md. Python 3.12, pymupdf, typer för CLI,
SQLite via sqlite3 eller sqlmodel, pytest.

Bygg i denna fas:

1. normalize.py — beräknar EN transform per sida av /Rotate, MediaBox, CropBox och
   UserUnit. All geometri passerar denna. Regel R8 i CLAUDE.md.

2. extract.py — pymupdf, per sida: alla banor med punkter, bbox, stroke-färg,
   fill-färg, linjebredd, dash-array, dash-phase, line-cap, OCG-lager,
   operatorindex. Plus alla textobjekt med bbox. Splittra banor i segment vid
   riktningsändringar över 3x medianvinkeländringen i ritningen (relativ tröskel,
   R1).

3. triage.py — spår A/B/C enligt R3. Skriver ut lagerlista, färger, linjetyper,
   om texten är riktig text eller glyfkonturer, och var teckenförklaring och
   titelfält ligger.

4. Facit-import: läs Excel med openpyxl till tabellen ground_truth. Kolumnalias
   för beteckning/label/benämning, dimension/dim, längd/length/m,
   antal/vertikala/st. VIKTIGT: jag har inte verifierat de faktiska kolumnnamnen i
   facitfilen — läs den först, skriv ut kolumnrubrikerna, och bekräfta med mig
   innan du hårdkodar en mappning. Omimport ska radera tidigare facit för samma
   ritning, inte lägga till.

5. evaluate.py som skelett. I denna fas rapporterar den bara två mått: täckning
   (accepterade + spärrade / totalt, ska vara 1,00) och antal banor per spår.
   Varje senare fas lägger till mått i samma funktion. Resultat sparas i
   eval_results med tidsstämpel och git-sha.

6. CLI: takeoff triage, takeoff evaluate.

Skriv tester för normalize (roterade sidor) och för täckningsinvarianten.
```

**Stoppgrind:** `takeoff evaluate --all` kör på alla fyra ritningarna och rapporterar
täckning 1,00. Siffrorna får vara usla, poängen är att en baslinje existerar.

---

## Fas 2 — Stilinventering och projektprofil

```
Bygg styles.py och profile.py.

styles.py:
- Stilvektor per bana: kvantiserad färg (slå ihop vid delta-E under 5),
  percentilbaserad linjebreddsbucket, normaliserad strecksignatur
  (on/period, off/period, antal termer), OCG-lager, is_closed.
- Gruppera på exakt matchning. Varje bana MÅSTE hamna i exakt ett kluster (R6).
- Per kluster: antal banor, total längd, andel av ritningen, vinkelhistogram,
  längdfördelning, kollinearitetsgrad för parallella par 60–500 mm isär, rumslig
  spridning, kopplingsgrad (andel banor med ändpunkt inom epsilon av annan bana i
  samma kluster).

profile.py:
- Härleder projektprofilen enligt schemat i CLAUDE.md och sparar till
  profiles/<ritning>.json.
- Klusterklasser sätts ännu inte automatiskt; lämna dem som "unknown" och tillåt
  manuell märkning i JSON-filen. Automatiken kommer i fas 6.

Lägg till: takeoff profile, och en debugkommando som renderar valfritt kluster som
overlay-PDF.

evaluate lägger till måtten: antal stilkluster, andel banor i de tre största
klustren.
```

**Stoppgrind:** 5–30 kluster per ritning, täckning 1,00, och overlay-renderingen
fungerar på alla fyra.

---

## Fas 3 — Skala

```
Bygg scale.py med tre oberoende källor enligt R4:

1. Skalstock i ramzonen: regelbundna delstreck med sifferetiketter, mät
   pixelavstånd mot utsatt värde. På 0011 syns 0/70/140/210.
2. Skaltext: regex 1\s*:\s*(\d+) i titelfältet.
3. Måttsatt längd eller modulnät med känt c/c i planet.

Kräv att minst två källor stämmer inom 0,5 %. Vid större avvikelse: sätt
scale_verified = false, skriv orsaken som en strukturerad flagga, och låt hela
mängdningen märkas preliminär. Systemet får ALDRIG anta en skala tyst.

Observera A1/A3-fällan: skaltexten gäller originalarket, inte nödvändigtvis den PDF
vi fått. Om källa 2 avviker från källa 1 och 3 är det källa 2 som är fel.

evaluate lägger till: skala hittad vs facit, procentuellt fel, verifierad ja/nej.
```

**Stoppgrind:** skala verifierad geometriskt på 0011, 0012, 0013 **och 0032**. Detta är
en hård grind. Utan verifierad skala på 0032 är generaliseringsproblemet olöst och
resten av bygget är förgäves.

---

## Fas 4 — Zoner och status

```
Bygg zones.py och status.py.

zones.py:
- Planyta = största rektangulära inramade tomma ytan. Allt utanför är ram.
  Topologisk härledning, inga fasta koordinater (R-förbud i CLAUDE.md).
- Identifiera teckenförklaring, titelfält, orienteringsfigur, detaljrutor,
  matchlines och maskade zoner. Rörgeometri förekommer i dessa som symboler och
  får aldrig in i mängden.
- Väggzoner: bygg ur schrafferingens diagonalfamilj, plus parallella linjepar
  60–500 mm isär som centerlinjer.

status.py — regel R5, den viktigaste i denna fas:
- Undersök om ritningen skiljer ny / befintlig / rivning via lager, färg, linjetyp
  eller ljushet. Testa alla fyra hypoteserna och rapportera vilken som ger en ren
  uppdelning.
- Mät kategorierna var för sig. Skriv ut total längd per kategori.

Detta är den troliga förklaringen till 605,0 m mot facit 213,7 m. Kvoten är 2,8.
Rapportera uttryckligen om summan för en delmängd av kategorierna ligger nära
213,7 m — i så fall mäter motorn rätt geometri men fel uppsättning.

evaluate lägger till: total längd per statuskategori, andel geometri i
exkluderingszoner.
```

**Stoppgrind:** kategoriuppdelningen verifierad visuellt på overlay. Rapportera vad
uppdelningen ger för totaler innan fas 5 påbörjas.

---

## Fas 5 — Text och beteckningar

```
Bygg text.py och labels.py.

text.py:
- Riktiga PDF-textobjekt först. Om fler än 50 ligger i planytan, använd dem.
- Annars (SHX-vektoriserad text): klustra glyfer till rader till block, rendera
  contact sheets i hög upplösning, läs med Claude via Anthropic API.
- Hård timeout per block och en total budget. OCR får aldrig låsa körningen; en
  timeout loggar och fortsätter.
- Alla träffar mappas genom transformen i normalize.py. Bbox, inte bara centrum.
- Text i exkluderingszoner markeras och får aldrig användas som ankare.

labels.py:
- Parser för mönstret SYSTEM-TYP[-DIMENSION]: S3-R8-110, KV2-X31, S1-P2.
- Rader utan dimension är GILTIGA. dimension = null, inte kasserad. Dimensionen
  ärvs i fas 8.
- Systemtillhörighet kommer gratis om texten ligger på systemets eget textlager
  (spår A) — kolla det först.

evaluate lägger till: antal beteckningar hittade, precision/recall/F1 mot facits
beteckningsuppsättning.
```

**Stoppgrind:** minst 90 % av facits beteckningar hittas på 0011. Fler än noll
beteckningar på 0032.

---

## Fas 6 — Ankare och rörstilsval

```
Detta är systemets kärna. Regel R7.

anchors.py, per beteckningstext:
1. Understrykning: nästan horisontell bana direkt under textens bbox, längd inom
   20 % av textens bredd.
2. Hänvisningsstreck: bana som startar inom epsilon av understrykningens ände.
   Följ genom skarvar, max 5 hopp. Epsilon relativt medianlinjebredden (R1).
3. Träffpunkt: banan hänvisningsstrecket slutar på eller korsar.
4. Spara som ankare med konfidens.

pipes.py — röstningen:
5. Varje ankare över konfidenströskeln röstar på stilklustret för sin träffbana.
6. Varje ⊗-symbol röstar på stilklustret för banan den sitter på.
7. Klustret eller klustren med över 70 % av rösterna ÄR rörstilen för ritningen.
8. Expandera: varje bana i rörstilsklustret blir rörkandidat, även utan eget
   ankare. Det är så de 301 stråken utan beteckning ska fångas.

Negativa filter, EFTER expansion och bara på klusternivå:
- Hög kollinearitet i parallella par 60–500 mm isär → VÄGG
- Enriktat vinkelhistogram plus hög lokal täthet → SCHRAFFERING
- Kluster i ramzon → RAM
- Klustret som verifierade hänvisningsstreck tillhör → HÄNVISNING

Varje utesluten bana skrivs till blocked_paths med orsak och steg. Assert på
täckning efter varje filter.

Skriv klusterklasserna tillbaka till projektprofilen.

evaluate lägger till: antal ankare, andel beteckningar med ankare, rörstilsklustrets
totala längd.
```

**Stoppgrind, tre delar:**

1. Rörstilsklustrets totala längd på 0011, efter naiv sammanfogning, inom 25 % av
   facit 213,7 m **innan** något finjusteras
2. Vägg- och hänvisningskluster identifierade, verifierat på overlay
3. Samma kod, oförändrad, ger ett icke-tomt rörkluster på 0032

Uppfylls inte punkt 3: gå tillbaka till fas 2. Fortsätt inte.

---

## Fas 7 — Sammanfogning och nätverk

```
chain.py — sammanfogning med platåtest istället för en gissad tröskel:
1. Svep sammanfogningströskeln över ett intervall, mät totallängden vid varje steg,
   plotta kurvan till out/.
2. Hitta platån (det plana partiet där totalen är okänslig för tröskeln) och sätt
   tröskeln mitt i den. Spara platåns bredd i profilen som känslighetstal.
3. Finns ingen platå är strecksammanfogningen inte tillförlitlig på den ritningen.
   Flagga det, gissa inte.
4. Sammanfoga bara banor i samma stil, kollinjära inom 2 grader, sidoförskjutning
   under 0,5x linjebredd.
5. Dubbelritade rör: kollinjära par inom 1x linjebredd slås ihop till EN
   centerlinje före mätning. Avgör först ur profilen om systemet är
   single_line eller double_line.

network.py:
6. Noder skapas EFTER sammanfogning, och ENDAST vid: verklig T- eller X-korsning,
   riktningsändring över 15 grader, dimensionsbyte, eller ändpunkt utan
   fortsättning. ALDRIG vid streckskarv. Det var felet bakom magenta punkter vid
   varje skarv.
7. Stråk = sammanhängande kedja mellan noder. Detta är enheten som mängdas.
8. Vertikala rör: ⊗-symboler matchas mot NÄRMASTE stråk. Varje symbol ger exakt EN
   räkning, aldrig en per passerande stråk. Facit är 55; tidigare version gav 149,
   vilket är dubbelräkning.

Längd mäts på grafens kanter, aldrig på banor. En kant räknas exakt en gång.

evaluate lägger till: total längd vs facit, antal noder, antal vertikala vs facit,
platåbredd.
```

**Stoppgrind:** total längd inom 10 % av facit på 0011. Vertikala rör inom ±10 av 55.
Antal noder under 3× antalet beteckningar.

---

## Fas 8 — Tillhörighet och mängdning

```
attribute.py:
1. Stråk med ankare får sin beteckning direkt, label_source = 'anchor'.
2. Sprid längs grafen till angränsande stråk, label_source = 'propagated'. Stoppa
   vid: stråk med annan beteckning av högre konfidens, dimensionsbyte, systembyte.
3. Stråk vars beteckning saknar dimension ärver från närmaste stråk i samma system
   som har en.
4. Stråk som ingen beteckning når får label_source = 'none' och redovisas som EGEN
   RAD "okopplade rör" med längd. De tilldelas ALDRIG närmaste beteckning som
   gissning (R10).
5. Ett stråk tillhör exakt en beteckning.

quantify.py:
6. Per beteckning: längd i meter, antal vertikala rör, antal böjar, antal
   T-stycken. Uppdelat per statuskategori från fas 4.
7. Känslighetstal: platåbredd, rör-i-väggzon-överlapp (alltid, oavsett om
   väggregeln tillämpas), andel symboler, antal olästa beteckningsblock.
8. Osäkerhetsflaggor per rad: skala overifierad, beteckning spridd i stället för
   ankarbunden, hög andel sammanfogad geometri, spår B.
9. Excel-export med tre blad: Sammanställning, Per rör, Avvikelser.

Mätvärden och uppskattningar får aldrig blandas utan märkning (R3).

evaluate lägger till: MAPE på längd per beteckning, andel av total längd i
kategorin okopplat.
```

**Stoppgrind:** MAPE under 10 % på 0011. Under 15 % av total längd okopplat. **Och
0012 och 0013 inom 15 % utan att någon parameter rörts sedan 0011.** Sista delen är
det verkliga testet.

---

## Fas 9 — Verifieringsoverlay

```
overlay.py genererar en PDF: originalet orört, med mätt geometri i färg ovanpå.
Färgkodning per system och per statuskategori. Okopplade rör i en egen färg.
Spärrade banor tillgängliga som separat tänd-/släckbart lager.

Granskningsregeln, som ska stå tryckt i legenden på overlayen:
  originallinje utan färg = missat rör
  färg utan originallinje = felmätt

Detta är vad en människa granskar, inte koden. Den ska gå att granska på tre
minuter per ritning.
```

**Stoppgrind:** en människa granskar 0011-overlayen och hittar inga systematiska fel.

---

## Fas 10 — Regressionssvit

```
Gör evaluate till en CI-grind. Varje bygge kör hela facituppsättningen. Sjunker F1
eller stiger MAPE går bygget inte igenom.

Lägg till takeoff compare <run_a> <run_b> som visar beteckning för beteckning vad
en ändring gjorde, sorterat på största försämring först.

Varje knäckt ritningskonvention blir ett testfall. När en ny ritning avslöjar en ny
konvention läggs den till i sviten, så att metodfel fångas före leverans i stället
för efter.
```

---

## Efter fas 10

Först nu är det motiverat att bygga webbgränssnittet: uppladdning, granskningsvy,
feedbackpanel, export. Motorn är då verifierad, och UI:t blir ett skal runt något som
fungerar i stället för ett skal runt något som ska börja fungera.

Och en sak att spara som rutin: begär **en handmätt ritning per nytt projekt**. En
enda kalibrerar hela profilen — trösklar, väggregel, statustolkning — och gör resten
av uppsättningen till en batchkörning.
