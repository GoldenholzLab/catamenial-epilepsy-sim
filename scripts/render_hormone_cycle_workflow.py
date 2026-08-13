"""Render the Appendix Figure A1 HORMONE-CYCLE workflow with Pillow.

This renderer is dependency-light so the publication asset can be regenerated
with the bundled workspace Python runtime even when Matplotlib is unavailable.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 3240
HEIGHT = 1600
BLUE = "#1F4E79"
TEAL = "#2C7F8F"
GRAY = "#6B7280"
TEXT = "#222222"
WHITE = "#FFFFFF"

REGULAR_FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
BOLD_FONT = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(BOLD_FONT if bold else REGULAR_FONT), size=size)


def centered_multiline(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    text: str,
    text_font: ImageFont.FreeTypeFont,
    *,
    fill: str,
    spacing: int = 8,
) -> None:
    left, top, right, bottom = bounds
    box = draw.multiline_textbbox(
        (0, 0),
        text,
        font=text_font,
        spacing=spacing,
        align="center",
    )
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    x = left + (right - left - text_width) / 2
    y = top + (bottom - top - text_height) / 2 - box[1]
    draw.multiline_text(
        (x, y),
        text,
        font=text_font,
        fill=fill,
        spacing=spacing,
        align="center",
    )


def workflow_box(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    title: str,
    body: str,
    *,
    outline: str,
) -> None:
    draw.rounded_rectangle(bounds, radius=12, fill=WHITE, outline=outline, width=6)
    left, top, right, bottom = bounds
    centered_multiline(
        draw,
        (left + 18, top + 20, right - 18, top + 112),
        title,
        font(48, bold=True),
        fill=BLUE,
    )
    centered_multiline(
        draw,
        (left + 20, top + 118, right - 20, bottom - 20),
        body,
        font(39),
        fill=TEXT,
        spacing=9,
    )


def decision_box(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    text: str,
    *,
    half_width: int = 160,
    half_height: int = 135,
) -> tuple[int, int, int, int]:
    x, y = center
    points = [
        (x, y - half_height),
        (x + half_width, y),
        (x, y + half_height),
        (x - half_width, y),
    ]
    draw.polygon(points, fill=WHITE, outline=TEAL)
    draw.line(points + [points[0]], fill=TEAL, width=6, joint="curve")
    centered_multiline(
        draw,
        (x - 118, y - 82, x + 118, y + 82),
        text,
        font(39, bold=True),
        fill=BLUE,
        spacing=5,
    )
    return (x - half_width, y - half_height, x + half_width, y + half_height)


def lane_label(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    text: str,
) -> None:
    left, top, right, bottom = bounds
    draw.rounded_rectangle(bounds, radius=17, fill="#EEF4F7")
    centered_multiline(
        draw,
        (left + 10, top + 3, right - 10, bottom - 3),
        text,
        font(29, bold=True),
        fill=TEAL,
        spacing=3,
    )


def arrow_head(
    draw: ImageDraw.ImageDraw,
    tip: tuple[float, float],
    tail: tuple[float, float],
    *,
    fill: str = GRAY,
    size: float = 23,
) -> None:
    tx, ty = tip
    sx, sy = tail
    angle = math.atan2(ty - sy, tx - sx)
    left = (
        tx - size * math.cos(angle) + size * 0.55 * math.sin(angle),
        ty - size * math.sin(angle) - size * 0.55 * math.cos(angle),
    )
    right = (
        tx - size * math.cos(angle) - size * 0.55 * math.sin(angle),
        ty - size * math.sin(angle) + size * 0.55 * math.cos(angle),
    )
    draw.polygon([tip, left, right], fill=fill)


def straight_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    fill: str = GRAY,
    width: int = 8,
) -> None:
    draw.line([start, end], fill=fill, width=width)
    arrow_head(draw, end, start, fill=fill)


def polyline_arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    *,
    fill: str = GRAY,
    width: int = 8,
) -> None:
    draw.line(points, fill=fill, width=width, joint="curve")
    arrow_head(draw, points[-1], points[-2], fill=fill)


def render(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(image)

    centered_multiline(
        draw,
        (120, 52, WIDTH - 120, 162),
        "HORMONE-CYCLE diary-generation workflow",
        font(86, bold=True),
        fill=BLUE,
    )
    centered_multiline(
        draw,
        (180, 175, WIDTH - 180, 245),
        "Each cycle: timing → LH-aligned serum envelope → long-follicular E2 branch → PCHIP + bridged serial noise.",
        font(38),
        fill=GRAY,
    )

    lane_label(draw, (45, 290, 700, 345), "INITIALIZATION, WAVEFORM, AND FIRST CYCLE")
    lane_label(draw, (45, 890, 690, 945), "REPEATED COMPLETE-CYCLE GENERATION")

    inputs = (45, 390, 490, 750)
    first_cycle = (550, 370, 1050, 770)
    start = (1110, 370, 1630, 770)
    append = (1690, 390, 2160, 750)

    workflow_box(
        draw,
        inputs,
        "Initialize patient",
        "Read age, diary length,\nseed, and modifiers;\nsample stable traits\nonce",
        outline=BLUE,
    )
    workflow_box(
        draw,
        first_cycle,
        "Generate cycle 1",
        "Sample timing + bleeding;\nmap daily E2/P4 medians;\nlong-cycle E2 branch;\nPCHIP + bridged noise",
        outline=TEAL,
    )
    workflow_box(
        draw,
        start,
        "Select random start",
        "Choose k uniformly from\ncycle days 1,…,L1\nDiary day 1 = cycle day k",
        outline=BLUE,
    )
    workflow_box(
        draw,
        append,
        "Append cycle 1",
        "Keep cycle days k,…,L1\nin order",
        outline=TEAL,
    )

    mid_y = 570
    straight_arrow(draw, (inputs[2] + 12, mid_y), (first_cycle[0] - 12, mid_y))
    straight_arrow(draw, (first_cycle[2] + 12, mid_y), (start[0] - 12, mid_y))
    straight_arrow(draw, (start[2] + 12, mid_y), (append[0] - 12, mid_y))

    first_decision_center = (2435, 570)
    first_decision = decision_box(
        draw,
        first_decision_center,
        "Diary\ncomplete?",
    )
    straight_arrow(
        draw,
        (append[2] + 12, mid_y),
        (first_decision[0] - 12, mid_y),
    )

    first_output = (2745, 410, 3215, 730)
    workflow_box(
        draw,
        first_output,
        "Return diary",
        "Exactly the requested\ndiary length",
        outline=BLUE,
    )
    straight_arrow(
        draw,
        (first_decision[2] + 12, mid_y),
        (first_output[0] - 12, mid_y),
    )
    draw.text((2635, 520), "Yes", font=font(29, bold=True), fill=GRAY)

    next_cycle = (760, 1010, 1320, 1395)
    append_next = (1435, 1030, 1955, 1375)
    workflow_box(
        draw,
        next_cycle,
        "Generate next cycle",
        "Sample structure and render\na new LH-aligned E2/P4\ncycle after the current\ncycle is exhausted",
        outline=TEAL,
    )
    workflow_box(
        draw,
        append_next,
        "Append from day 1",
        "Keep cycle days 1,…,Ln\nin order; stop when\nthe diary is full",
        outline=TEAL,
    )

    # The first decision's No branch enters the lower lane from above.
    polyline_arrow(
        draw,
        [
            (first_decision_center[0], first_decision[3] + 10),
            (first_decision_center[0], 850),
            (1040, 850),
            (1040, next_cycle[1] - 14),
        ],
    )
    draw.text((2465, 780), "No", font=font(29, bold=True), fill=GRAY)

    straight_arrow(
        draw,
        (next_cycle[2] + 14, 1202),
        (append_next[0] - 14, 1202),
    )

    repeat_decision_center = (2245, 1202)
    repeat_decision = decision_box(
        draw,
        repeat_decision_center,
        "Diary\ncomplete?",
    )
    straight_arrow(
        draw,
        (append_next[2] + 14, 1202),
        (repeat_decision[0] - 14, 1202),
    )

    repeat_output = (2735, 1042, 3215, 1362)
    workflow_box(
        draw,
        repeat_output,
        "Return diary",
        "Exactly the requested\ndiary length",
        outline=BLUE,
    )
    straight_arrow(
        draw,
        (repeat_decision[2] + 14, 1202),
        (repeat_output[0] - 14, 1202),
    )
    draw.text((2440, 1150), "Yes", font=font(29, bold=True), fill=GRAY)

    # The repeated No branch runs below the lane and re-enters the next-cycle
    # box from the left. It does not intersect any other connector.
    polyline_arrow(
        draw,
        [
            (repeat_decision_center[0], repeat_decision[3] + 10),
            (repeat_decision_center[0], 1535),
            (690, 1535),
            (690, 1202),
            (next_cycle[0] - 14, 1202),
        ],
    )
    draw.rounded_rectangle(
        (2260, 1400, 2550, 1470),
        radius=12,
        fill=WHITE,
    )
    centered_multiline(
        draw,
        (2260, 1400, 2550, 1470),
        "No: repeat",
        font(27, bold=True),
        fill=GRAY,
    )

    image.save(output, format="PNG", dpi=(240, 240), optimize=True)


if __name__ == "__main__":
    render(Path("examples/reports/hormone_cycle_workflow_v13.png"))
