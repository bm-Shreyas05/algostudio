"""Generate the raster brand assets from one definition.

The mark is three bars of different lengths with a playhead to their right:
an array mid-sort, frozen at a step. It is the product in one glyph, and it
survives being shrunk to 16 px because it is four rectangles and nothing else.

The SVG at frontend/public/favicon.svg is the same drawing by hand; this script
produces the raster sizes browsers still ask for, plus the social card. Assets
are committed, but they are regenerable:

    python frontend/scripts/make_brand.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PUBLIC = Path(__file__).resolve().parent.parent / "public"

BG = (13, 17, 23)
FG = (219, 227, 236)
MUTED = (125, 137, 150)
BLUE = (76, 154, 255)
GREEN = (74, 160, 107)
AMBER = (217, 164, 65)

#: x, width, colour — as fractions of the icon box, matching favicon.svg.
BARS = [(0.1875, 0.531, BLUE), (0.1875, 0.344, GREEN), (0.1875, 0.4375, AMBER)]
BAR_Y = [0.25, 0.4453, 0.6406]
BAR_H = 0.109


def rounded(size: int, radius_frac: float = 0.219) -> Image.Image:
    """The icon at an arbitrary size, drawn at 4x and downsampled."""
    scale = 4
    box = size * scale
    image = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        [0, 0, box - 1, box - 1], radius=int(radius_frac * box), fill=BG
    )
    for (x, w, colour), y in zip(BARS, BAR_Y):
        x0, y0 = x * box, y * box
        x1, y1 = x0 + w * box, y0 + BAR_H * box
        draw.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) / 2, fill=colour)
    # the playhead
    px0, py0 = 0.781 * box, 0.156 * box
    draw.rounded_rectangle(
        [px0, py0, px0 + 0.047 * box, py0 + 0.688 * box],
        radius=0.023 * box, fill=FG,
    )
    return image.resize((size, size), Image.LANCZOS)


def _font(size: int) -> ImageFont.FreeTypeFont:
    """A real font if this machine has one, else the bitmap default."""
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        for root in (Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"),
                     Path("/Library/Fonts")):
            candidate = root / name
            if candidate.exists():
                return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size)


def social_card() -> Image.Image:
    """1200x630 Open Graph card.

    Deliberately typographic: a screenshot would date the moment the UI moves,
    and a card that lies about the product is worse than one that states it.
    """
    width, height = 1200, 630
    card = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(card)

    # a faint grid, so the card is not a flat rectangle
    for x in range(0, width, 40):
        draw.line([(x, 0), (x, height)], fill=(18, 24, 31), width=1)
    for y in range(0, height, 40):
        draw.line([(0, y), (width, y)], fill=(18, 24, 31), width=1)

    icon = rounded(96)
    card.paste(icon, (80, 84), icon)

    draw.text((200, 100), "AlgoStudio", font=_font(54), fill=FG)

    # Not "any Python program": the supported subset is documented and finite,
    # and a social card is the easiest place in a project to start lying.
    draw.text((80, 254), "Step backwards through", font=_font(64), fill=FG)
    draw.text((80, 330), "a running program.", font=_font(64), fill=BLUE)

    body = _font(26)
    draw.text((80, 436),
              "An event-driven execution engine, not a set of canned animations.",
              font=body, fill=MUTED)
    draw.text((80, 476),
              "49 algorithms. Views inferred from the data's shape at runtime.",
              font=body, fill=MUTED)

    # the mark repeated as a rhythm strip along the bottom
    y = 560
    for i, (w, colour) in enumerate(
        [(150, BLUE), (96, GREEN), (124, AMBER), (72, BLUE), (110, GREEN)]
    ):
        x = 80 + i * 190
        draw.rounded_rectangle([x, y, x + w, y + 14], radius=7, fill=colour)
    return card


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)

    # .ico carries the small sizes Windows and older browsers still request.
    rounded(64).save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    # Apple refuses transparency and composites on black, so flatten on the
    # brand background rather than letting it pick.
    apple = Image.new("RGB", (180, 180), BG)
    icon = rounded(180)
    apple.paste(icon, (0, 0), icon)
    apple.save(PUBLIC / "apple-touch-icon.png")

    rounded(192).save(PUBLIC / "icon-192.png")
    rounded(512).save(PUBLIC / "icon-512.png")
    social_card().save(PUBLIC / "og.png", optimize=True)

    for path in sorted(PUBLIC.glob("*")):
        print(f"{path.name:<24}{path.stat().st_size:>8,} bytes")


if __name__ == "__main__":
    main()
