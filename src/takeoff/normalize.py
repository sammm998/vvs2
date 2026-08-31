"""R8 - en koordinatsanning.

Rotation (/Rotate), MediaBox, CropBox och UserUnit hanteras har och ingen
annanstans. Efter ``PageTransform.apply`` ligger all geometri i samma rymd:
PDF-punkter, origo uppe till vanster, y nedat, skalad med UserUnit.

Ingen annan modul far rora koordinatsystemet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import pymupdf

Point = tuple[float, float]


@dataclass(frozen=True)
class PageTransform:
    """Affin transform fran raa PDF-anvandarkoordinater till normrymden."""

    a: float
    b: float
    c: float
    d: float
    e: float
    f: float
    width: float
    height: float
    rotate: int
    user_unit: float
    cropbox: tuple[float, float, float, float]
    mediabox: tuple[float, float, float, float]

    @property
    def matrix(self) -> pymupdf.Matrix:
        return pymupdf.Matrix(self.a, self.b, self.c, self.d, self.e, self.f)

    def apply(self, p: Point | pymupdf.Point) -> Point:
        x, y = (p.x, p.y) if isinstance(p, pymupdf.Point) else (p[0], p[1])
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    def apply_many(self, pts: Iterable[Point | pymupdf.Point]) -> list[Point]:
        return [self.apply(p) for p in pts]

    def apply_rect(self, r: pymupdf.Rect | Sequence[float]) -> pymupdf.Rect:
        x0, y0, x1, y1 = (r.x0, r.y0, r.x1, r.y1) if isinstance(r, pymupdf.Rect) else r
        corners = [self.apply(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        xs = [p[0] for p in corners]
        ys = [p[1] for p in corners]
        return pymupdf.Rect(min(xs), min(ys), max(xs), max(ys))

    @property
    def diagonal(self) -> float:
        """Sidans diagonal. Referenslangd for relativa trosklar (R1)."""
        return math.hypot(self.width, self.height)

    @property
    def scale_factor(self) -> float:
        """Langdskalning som transformen infor (UserUnit)."""
        return math.sqrt(abs(self.a * self.d - self.b * self.c))


def page_transform(page: pymupdf.Page) -> PageTransform:
    """Harled sidans transform.

    pymupdf levererar banor och textrutor i sidans *oroterade* anvandarrymd
    med origo uppe till vanster relativt CropBox. Vi bygger transformen
    explicit sa att den ar granskningsbar och testbar i stallet for
    underforstadd.
    """
    rotate = int(page.rotation) % 360
    user_unit = float(page.parent.xref_get_key(page.xref, "UserUnit")[1] or 1.0) if _has_user_unit(page) else 1.0

    crop = page.cropbox
    media = page.mediabox
    # Sidans matt i oroterat lage, fore rotation.
    w0 = crop.width
    h0 = crop.height

    # Rotation kring origo + translation sa att resultatet ligger i forsta
    # kvadranten med y nedat.
    rad = math.radians(rotate)
    cos, sin = round(math.cos(rad)), round(math.sin(rad))
    # Rotation medurs i ett y-nedat system.
    a, b, c, d = cos, sin, -sin, cos
    if rotate == 0:
        e, f = 0.0, 0.0
        width, height = w0, h0
    elif rotate == 90:
        e, f = h0, 0.0
        width, height = h0, w0
    elif rotate == 180:
        e, f = w0, h0
        width, height = w0, h0
    elif rotate == 270:
        e, f = 0.0, w0
        width, height = h0, w0
    else:  # pragma: no cover - PDF tillater bara multiplar av 90
        raise ValueError(f"ostodd rotation {rotate}")

    u = user_unit
    return PageTransform(
        a=a * u,
        b=b * u,
        c=c * u,
        d=d * u,
        e=e * u,
        f=f * u,
        width=width * u,
        height=height * u,
        rotate=rotate,
        user_unit=u,
        cropbox=(crop.x0, crop.y0, crop.x1, crop.y1),
        mediabox=(media.x0, media.y0, media.x1, media.y1),
    )


def _has_user_unit(page: pymupdf.Page) -> bool:
    try:
        key, _ = page.parent.xref_get_key(page.xref, "UserUnit")
    except Exception:
        return False
    return key not in (None, "null")
