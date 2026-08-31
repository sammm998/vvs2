# takeoff — mängdförteckning ur vektor-PDF (VVS)

Motorn läser en vektor-PDF av en byggritning och producerar rörlängd per
system, antal vertikala rör och osäkerhet per rad. Reglerna i `CLAUDE.md`
gäller före allt annat i detta repo; fasplanen ligger i `docs/FASER.md`.

## Status

Kalibrerad pa **W-50-1-A-0011**. Verifierad pa **0013**, **0014**, **0023** och
**0111**, som alla ar HALLNA UTE fran kalibreringen och inte har paverkat en
enda parameter.

| ritning | matt | facit | fel | MAPE/system | vertikala | roll |
|---|---|---|---|---|---|---|
| 0011 | 210,1 m | 213,7 m | **-1,7 %** | 2,3 % | 60 / 55 | kalibrering |
| 0013 | 110,3 m | 112,9 m | **-2,3 %** | 1,3 % | 24 / 24 | hallen ute |
| 0014 | 48,3 m | 50,9 m | **-5,0 %** | 4,4 % | 20 / 16 | hallen ute |
| 0023 | 35,6 m | 36,4 m | **-2,3 %** | 2,5 % | 13 / 9 | hallen ute |
| 0111 | 512,7 m | 519,5 m | **-1,3 %** | 20,8 % | 150 / 90 | hallen ute |

Medelavvikelse pa langd: 2,5 %. Alla fem passerar langdgrinden (+/-10 %) och
har tackning (R6) 1,0000 och skala 1:50 verifierad geometriskt med 0,03 %
avvikelse mellan kallorna.

Recall mot facitgeometrin ar 98-99 % pa alla fem: motorn hittar praktiskt
taget varje meter kalkylatorn matt.

0111 ar storst och tatast (519 m, 34 beteckningar, 45 000 banor mot 20-25 000)
och den enda som annu faller pa MAPE och vertikalrakning.

## Kan den nya ritningar?

Ja, inom samma projekt - och det ar en precis avgransning, inte en brasklapp.

**Inom ett kalibrerat projekt** kors en ny ritning utan handpaslag. Bade
lagerregeln och skalreferensen kommer ur projektprofilen. Sa kordes 0013,
0014, 0023 och 0111. Projektet identifieras av PROJEKTNUMRET i lagerprefixen,
inte av modellfilen: en ritning bar ofta flera modeller samtidigt
(`268140-W-50-P-A-01` for VVS, `268140-A-40-P-A-01` for arkitekt) och samma
projekt anvander flera. Att lasa nyckeln till modellfilen gjorde varje modell
till ett eget "projekt" och tvingade fram onodig omkalibrering.

**I ett nytt projekt** behovs EN handmatt ritning. `takeoff calibrate`
inducerar lagerregeln ur facitets geometri och skalstockens spann ur den
verifierade skalan. Det ar samma arbetsgang CLAUDE.md avslutar med, och skalet
ar att lagerkonventioner varierar mellan projekterande foretag (R2).

**Utan kalibrering** faller motorn tillbaka pa ett strukturellt urval
(linjebredd over ritningens median plus kopplingsgrad). Det urvalet ar markt
`pipe_style:structural` och ar matbart samre: pa 0013 missade det tre av sex
rorsystem och slappte igenom tva arkitektlager. Lita inte pa det utan
granskning.

**Nar underlaget inte racker vagrar motorn.** Bade 0023 och 0111 saknar
modulnat som riktig text; innan projektets skalreferens fanns stannade
korningen med `ambiguous:1:50,1:100` i stallet for att valja en skala. En
gissad skala multiplicerar hela mangdforteckningen med fel tal.

## Maskade zoner

Ritningarna redovisar geometri som ligger utanfor det som mangdas: rorstrackor
genom schrafferade omraden vid entreprenadgransen, ritade for att visa
anslutningen. Pa 0014 var det 39,9 m av 88,2 - nastan halva matningen, och pa
0111 84,8 m.

Zonen harleds ur ritningens egen schraffering, med tre villkor som alla ar
relativa till ritningen sjalv:

1. **Regelbundna parallella grannar.** Matt lokalt, granne mot granne, sa att
   det inte spelar nagon roll om monstret ligger som ett block eller som en
   ram runt planet. Ett bbox-baserat matt klarade 0011-0023 men foll pa 0111,
   dar schrafferingen ramar in planet i stallet for att fylla en ruta.
2. **Fin delning**, hogst en hundradel av arkets diagonal. Schraffering ar en
   ritteknisk fyllning; modulnat och rumsindelning har delningar i
   byggnadsmatt och faller bort har.
3. **Stor plantackning**, som utstickare. Dorrslag och trappor ar ocksa
   regelbundna och finmaskiga men tacker under 1 % av planet, mot
   schrafferingens 10-26 %.

Slutningen ar exakt sa bred som schrafferingens egen linjedelning, sa att ytan
mellan strecken sluts utan att zonen svaller ut over sin kant.

Bade langden och antalet vertikala ror i zonen redovisas som egna varden. De
tas aldrig bort tyst (R10).

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
