# takeoff — mängdförteckning ur vektor-PDF (VVS)

Motorn läser en vektor-PDF av en byggritning och producerar rörlängd per
system, antal vertikala rör och osäkerhet per rad. Reglerna i `CLAUDE.md`
gäller före allt annat i detta repo; fasplanen ligger i `docs/FASER.md`.

## Status

Kalibrerad pa **W-50-1-A-0011**. Verifierad pa **0013** och **0023**, som bada
ar HALLNA UTE fran kalibreringen och inte har paverkat en enda parameter.

| ritning | matt | facit | fel | MAPE/system | roll |
|---|---|---|---|---|---|
| 0011 | 222,9 m | 213,7 m | **+4,3 %** | 13,8 % | kalibrering |
| 0013 | 117,8 m | 112,9 m | **+2,6 %** | 1,3 % | hallen ute |
| 0023 | 38,2 m | 36,4 m | **+5,0 %** | 4,8 % | hallen ute |

Skalan verifieras geometriskt till 1:50 pa alla tre, med 0,03 % avvikelse
mellan kallorna. Tackningen (R6) ar 1,0000 pa alla tre.

Recall mot facitgeometrin ar 98-99 % pa alla tre: motorn hittar praktiskt
taget varje meter kalkylatorn matt. Overskottet ar geometri som facit inte
tacker, inte missad geometri.

## Kan den nya ritningar?

Ja, inom samma projekt - och det ar en precis avgransning, inte en brasklapp.

**Inom ett kalibrerat projekt** kors en ny ritning utan handpaslag. Bade
lagerregeln och skalreferensen kommer ur projektprofilen. Det ar sa 0013 och
0023 kordes.

**I ett nytt projekt** behovs EN handmatt ritning. `takeoff calibrate`
inducerar da lagerregeln ur facitets geometri och skalstockens spann ur den
verifierade skalan. Det ar samma arbetsgang CLAUDE.md avslutar med, och skalet
ar att lagerkonventioner varierar mellan projekterande foretag (R2).

**Utan kalibrering** faller motorn tillbaka pa ett strukturellt urval
(linjebredd over ritningens median plus kopplingsgrad). Det urvalet ar
markerat `pipe_style:structural` och ar matbart samre: pa 0013 missade det
tre av sex rorsystem och slappte igenom tva arkitektlager. Lita inte pa det
utan granskning.

**Nar underlaget inte racker vagrar motorn.** 0023 saknar modulnat som riktig
text; innan skalreferensen fanns stannade korningen med
`ambiguous:1:50,1:100,1:200` i stallet for att valja en skala. En gissad
skala multiplicerar hela mangdforteckningen med fel tal, sa det ar ratt
beteende - men det betyder ocksa att en ny ritning kan krava kalibrering
innan den gar att mata.

## Vad probet visade (fas 0)

1. **Spår A.** Ritningen har 43 namngivna OCG-lager och varje bana bär sitt
   lagernamn. Per-system-siffror får därför levereras som mätvärden.
2. **Rören ligger i sex stilkluster**, inte utspridda över åtta eller fler.
   Klustret är `(lager, linjebredd)`: rörlinjen ritas grövre (1,44 och
   2,04 pt) än underlaget (median 0,72 pt), och stigarsymbolerna ligger på
   samma lager men i 0,48 pt.
3. **Texten är SHX-vektoriserad.** Bara 19 riktiga textord finns på arket,
   och de är modulnätets siffror. Beteckningarna kräver glyfklustring och
   vision — det är fas 5.
4. **Skalan går att verifiera geometriskt.** Modulnätet ger 1:49,998 och
   skalstocken 1:49,98. Väggtjockleken förkastar decennie­alternativet 1:500.

## De 605 m mot 213,7 m

`CLAUDE.md` R5 anger en statusuppdelning (ny/befintlig/rivning) som trolig
förklaring. **Den hypotesen håller inte här.** Alla fyra hypoteserna prövades
och rörgeometrin är enfärgad, heldragen och lika ljus rakt igenom — det finns
ingen uppdelning att göra:

```
color     {(0,0,0): 246,6 m}
linetype  {solid:   246,6 m}
lightness {0.0:     246,6 m}
```

Överskottet kom i stället av att tidigare versioner mätte geometri som inte är
rör: vektoriserad text, arkitektunderlag, schraffering och ram. Med stilgrind
på linjebredd och kopplingsgrad blir råsumman 246,6 m i stället för 605,0 m.

Kvar står en verklig upptäckt: `V-5--BEE--_V50` är **VVC1**, ett riktigt
rörsystem på 58,8 m som kalkylatorn inte tagit med i facit. Det är ett
omfångsbeslut, inte ett mätfel, och redovisas som egen rad (R10).

## Kom igång

```bash
pip install -e .
takeoff triage       data/W501A0011-single.pdf
takeoff profile      data/W501A0011-single.pdf
takeoff run          data/W501A0011-single.pdf
takeoff overlay      data/W501A0011-single.pdf
takeoff import-facit data/W501A0011.xlsx
takeoff evaluate --all
pytest
```

`data/` och `out/` är gitignorerade. `profiles/` versioneras.

## Facitfilens kolumner

Facit är en Bluebeam-markeringsexport. Den upplösta mappningen skrivs ut vid
import och ska bekräftas innan den används i leverans:

| fält | kolumn i filen |
|---|---|
| `label` | `Subject` |
| `length` | `Längd` |
| `count` | `Antal_VS` |
| `layer` | `Lager` |
| `document` | `Document` |

Beteckningen bär suffixet `Vertikal`/`VERTIKAL` på de rader som räknar
vertikala rör; suffixet skalas av och raden märks `is_vertical`.

## Nästa steg

1. **Fas 5** — glyfklustring av SHX-texten och läsning via vision. Utan den
   kan `S3-R8-110` inte skiljas från `S3-R8-75`, och MAPE per beteckning kan
   inte mätas alls.
2. **Fas 6** — ankarröstning. Underlinje → hänvisningsstreck → träffbana finns
   tydligt i ritningen och syns på overlayen. Då ersätts den strukturella
   stilgrinden av ritningens egna beteckningar, och flaggan
   `pipe_style:structural` försvinner.
3. **0012, 0013 och 0032** behövs för de stoppgrindar som mäter
   generalisering. Ingen av dem fanns i underlaget.
