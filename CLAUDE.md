# CLAUDE.md

Permanenta regler för detta repo. Läs hela filen innan du ändrar kod. Reglerna nedan
är inte förslag — de är resultatet av fyra tidigare versioner som misslyckats på exakt
de sätt reglerna förbjuder.

---

## Vad systemet gör

Läser en vektor-PDF av en byggritning (VVS) och producerar en mängdförteckning: total
rörlängd per beteckning och system, antal vertikala rör, med osäkerhet redovisad per
rad. Facit finns för ritning W-50-1-A-0011 (~291 rader), 0012 (18) och 0013 (132).
W-50-1-A-0032 saknar facit och används som generaliseringstest.

Motorn är Python. Ingen webapp byggs förrän motorn träffar facit på 0011, 0012 och
0013 med oförändrad kod. Granskning sker under tiden via genererade overlay-PDF:er.

---

## Icke-förhandlingsbara regler

### R1 — Inga absoluta trösklar

Varje tröskel uttrycks som percentil av ritningens egen fördelning, multipel av en
uppmätt median, eller andel av sidans diagonal. En numerisk konstant med enheten `pt`
eller `mm` i en jämförelse är ett fel, oavsett hur väl den fungerar på 0011.

Fel: `if line_width < 0.35:`
Rätt: `if line_width < profile.width_p25:`

Detta är grundorsaken till att 0032 gav "antagen 1:100, 191 rörsegment, 0
beteckningar". Motorn var kalibrerad mot en ritning.

### R2 — Projektprofilen härleds ur ritningen, aldrig återanvänds

Lagernamn, färger, linjebredder, linjetyper och beteckningsgrammatik varierar mellan
projekterande företag. Allt sådant härleds per ritning och sparas i en profil. Profilen
får återanvändas inom samma projekt, aldrig mellan projekt.

### R3 — Triage före mätning

Varje ritning klassas innan något mäts:

| Spår | Signal | Vad som får levereras |
|---|---|---|
| A | Vektor + OCG-lager | Mängder per system som **mätvärden** |
| B | Vektor utan lager | Totalsumma som mätvärde, per system som **uppskattning** |
| C | Raster | Allt flaggat osäkert, annan metod |

Mätvärden och uppskattningar får aldrig blandas i en leverans utan märkning. Ett spår
B-resultat presenterat som spår A är ett allvarligare fel än ett saknat rör.

### R4 — Skala verifieras geometriskt

Skaltext i titelfältet räcker inte (A1/A3-fällan: texten gäller originalarket, inte
den PDF som levererats). Skalan ska verifieras mot minst en känd geometrisk längd:
skalstock, modulnät med känt c/c, eller måttsatt längd.

Avvikelse över **0,5 %** mellan källorna → stoppa körningen och flagga. Anta aldrig en
skala tyst.

### R5 — Status separeras (ny / befintlig / rivning)

Ritningar innehåller normalt fler kategorier än den som ska mängdas. Skillnaden kan
ligga i lager, färg, linjetyp eller ljushet. Kategorierna mäts **var för sig** och
redovisas var för sig. Normalt går bara "ny" in i mängden.

Detta är en trolig förklaring till 605,0 m mot facit 213,7 m. Kvoten 2,8 är för stor
för att vara en tröskelfråga. Utred detta innan någon tröskel justeras.

### R6 — Täckning ska alltid vara 1,00

Varje bana i ritningen hamnar antingen i ett resultat eller i `blocked_paths` med
orsak och steg. `accepterade + spärrade == totalt` är ett assert som körs efter varje
steg, inte ett debugmått. Tyst efterfiltrering är förbjudet.

### R7 — Stil före geometri, ankare före rör

Klassificera inte enskilda banor. Gruppera först alla banor i stilkluster
(färg + linjebredd + strecksignatur + lager), klassificera sedan klustret. Låt
ritningens egna beteckningar rösta fram vilket kluster som är rörstilen.

Ordningen "hitta rör, koppla sedan beteckning" har misslyckats fyra gånger och gav 301
stråk utan beteckning. Ordningen är omvänd.

### R8 — En koordinatsanning

Rotation (`/Rotate`), MediaBox, CropBox och UserUnit hanteras på exakt ett ställe,
direkt efter parsning. All geometri i systemet — vektorer, textrutor, OCR-träffar,
overlay — ligger därefter i samma koordinatrymd: PDF-punkter, origo uppe till vänster,
y nedåt. Ingen annan modul får konvertera koordinater.

### R9 — Ingen optimering utan mätning före och efter

Att justera en parameter och titta på ritningen är inte mätning. Varje ändring som kan
påverka resultatet körs genom `evaluate` på hela facituppsättningen före och efter.
Diffen redovisas i commit-meddelandet.

"Trösklar har justerats många gånger utan verklig förbättring" är vad som händer utan
denna regel.

### R10 — Osäkerhet redovisas, aldrig döljs

Rör som ingen beteckning når redovisas som en egen rad "okopplade rör" med längd. De
tilldelas aldrig närmaste beteckning som gissning. Rader med overifierad skala, spridd
i stället för ankarbunden beteckning, eller hög andel sammanfogad geometri bär
flaggor.

---

## Projektprofil

Härleds i fas 2, sparas som `profiles/<ritning>.json`, versioneras i git.

```json
{
  "track": "A|B|C",
  "has_ocgs": true,
  "layers": ["..."],
  "scale": {"value": 50, "verified": true, "sources": ["scalebar", "grid"], "error_pct": 0.2},
  "width_percentiles": {"p10": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0},
  "style_clusters": [{"id": "...", "class": "pipe|wall|leader|hatch|text|frame|unknown", "confidence": 0.0}],
  "status_rule": {"field": "layer|color|linetype|lightness", "mapping": {}},
  "pipe_representation": "single_line|double_line",
  "wall_rule": "measure_through|cut_at_wall",
  "label_grammar": "SYSTEM-TYP[-DIM]",
  "chain_threshold": {"value": 0.0, "plateau_width": 0.0, "unit": "median_dash_period"}
}
```

`wall_rule` är ett projektbeslut, inte en detekteringsfråga. Ytmonterade rör mäts
genom väggenomföringar; ingjutna system där kalkylatorn kapar vid vägg kapas. Oavsett
beslut mäts alltid överlappet rör-i-väggzon och redovisas som känslighetstal, så att
det syns vad beslutet är värt.

---

## Repostruktur

```
src/takeoff/
  normalize.py      R8. Transform per sida. Enda stället som rör koordinatsystem.
  extract.py        pymupdf. Banor, text, OCG, operatorindex.
  triage.py         R3. Spår A/B/C.
  styles.py         R7. Stilvektor, klustring, klusterstatistik.
  profile.py        R2. Härleder och sparar projektprofil.
  scale.py          R4. Tre källor, korsvalidering, 0,5 %.
  zones.py          Ramzoner, teckenförklaring, maskade zoner, väggzoner.
  status.py         R5. Ny / befintlig / rivning.
  text.py           PDF-text först, glyfklustring + vision som fallback.
  labels.py         Beteckningsgrammatik.
  anchors.py        Understrykning → hänvisningsstreck → träffbana.
  pipes.py          R7. Ankarröstning, rörstilsval, expansion.
  chain.py          Sammanfogning med platåtest.
  network.py        Noder, stråk, vertikala rör.
  attribute.py      Stråk → beteckning via graf.
  quantify.py       Mängder, känslighetstal, osäkerhet.
  overlay.py        Verifierings-PDF.
  evaluate.py       R9. Diff mot facit.
tests/
data/               PDF:er och facit, gitignorerade
profiles/           Härledda profiler, versionerade
out/                Overlays, rapporter, gitignorerat
```

## Kommandon

```
takeoff triage    <pdf>            Spår A/B/C + inventering
takeoff profile   <pdf>            Härled och spara projektprofil
takeoff run       <pdf>            Hela kedjan → resultat i SQLite
takeoff overlay   <pdf>            Verifierings-PDF till out/
takeoff evaluate  [--all]          Diff mot facit, skriver till eval_results
takeoff compare   <run_a> <run_b>  Förbättrade ändringen resultatet?
```

## Definition of done för varje ändring

1. `takeoff evaluate --all` kört före och efter, diffen i commit-meddelandet
2. Täckning fortfarande 1,00 på alla fyra ritningarna
3. Inga nya numeriska konstanter med enheten pt eller mm
4. Testerna gröna

## Förbjudet

- Hårdkodade koordinater för titelfält, teckenförklaring eller ramzoner. Zoner härleds
  topologiskt.
- Trösklar kalibrerade mot en enskild ritning.
- Att gå vidare till nästa fas när stoppgrinden i den nuvarande inte är uppfylld.
- Att presentera spår B-resultat utan att märka per-system-siffrorna som uppskattning.
- Att tilldela okopplade rör en beteckning för att tabellen ska se komplett ut.
