# takeoff — mängdförteckning ur vektor-PDF (VVS)

Motorn läser en vektor-PDF av en byggritning och producerar rörlängd per
system, antal vertikala rör och osäkerhet per rad. Reglerna i `CLAUDE.md`
gäller före allt annat i detta repo; fasplanen ligger i `docs/FASER.md`.

## Status

Byggt och verifierat på **W-50-1-A-0011**. Fas 0–4, 7 och 9 är på plats.
Fas 5–6 (text, beteckningar, ankare) och fas 8 (per-beteckning) återstår.

Facitritningarna 0012, 0013 och generaliseringstestet 0032 fanns inte i
underlaget, så de stoppgrindar som kräver dem är **inte** kontrollerade.

## Resultat på 0011

```
täckning (R6)                1,0000
skala                        1:50, verifierad, 0,03 % mellan källorna
rörstilskluster              6 (noll falska träffar)
total längd i facitomfång    223,1 m mot facit 213,7 m   (+4,4 %)
utanför facitomfång          58,8 m  (VVC1, ett eget system)
vertikala rör                61 mot facit 55             (+6)
MAPE per system              13,9 %
```

Per system:

| mätt | facit | fel | lager |
|---|---|---|---|
| 115,0 | 114,0 | +0,9 % | `V-53BB-FE--S3-` |
| 33,6 | 34,1 | −1,5 % | `V-52BC-FE--V1-` |
| 32,6 | 33,3 | −2,2 % | `V-52BB-FE--V2-` |
| 21,4 | 14,6 | +46,5 % | `V-53BB-FE--S1-` |
| 20,5 | 17,4 | +18,2 % | `V-52BB-FE--V1-` |
| 58,8 | — | utanför omfång | `V-5--BEE--_V50` (VVC1) |

De tre största systemen ligger inom 2,2 %. Felet sitter i de två minsta.

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
