"""Reflow Figure 2 tick labels without changing the original plot elements."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import re

from lxml import etree
from matplotlib.font_manager import FontProperties
from matplotlib.path import Path as MplPath
from matplotlib.textpath import TextPath, TextToPath


SVG_NS = "http://www.w3.org/2000/svg"
NS = {"svg": SVG_NS}
FONT = FontProperties(family="DejaVu Sans", size=10)
LABELS = [
    ["Healthy", "ovulatory", "Windowed", "Herzog", "n=50,000"],
    ["Healthy", "ovulatory", "Herzog + >=4", "seizure days", "n=50,000"],
    ["Heterogeneous", "menstruating-age", "Windowed", "Herzog", "n=50,000"],
    ["Heterogeneous", "menstruating-age", "Herzog + >=4", "seizure days", "n=50,000"],
]


def path_commands(path: MplPath) -> str:
    commands = []
    names = {
        MplPath.MOVETO: "M",
        MplPath.LINETO: "L",
        MplPath.CURVE3: "Q",
        MplPath.CURVE4: "C",
    }
    for vertices, code in path.iter_segments(curves=True, simplify=False):
        if code == MplPath.CLOSEPOLY:
            commands.append("z")
        elif code in names:
            commands.append(names[code] + " " + " ".join(f"{v:.6f}" for v in vertices))
    return "\n".join(commands)


def revise(source: Path, destination: Path) -> None:
    document = etree.parse(str(source))
    root = document.getroot()
    width = float(root.get("width").removesuffix("pt"))
    root_defs = root.find(f"{{{SVG_NS}}}defs")
    rows = [0, 12, 28, 40, 56]
    boxes = []
    glyph_ids = set(root.xpath("//svg:defs/svg:path/@id", namespaces=NS))

    for index, lines in enumerate(LABELS, start=1):
        tick = root.xpath(f'//svg:g[@id="xtick_{index}"]', namespaces=NS)[0]
        original = tick.find(f'{{{SVG_NS}}}g[@id="text_{index}"]')
        first_line = original.find(f"{{{SVG_NS}}}g")
        baseline = float(re.search(r"translate\([^ ]+ ([^)]+)\)", first_line.get("transform"))[1])
        anchor = float(tick.xpath(".//svg:use/@x", namespaces=NS)[0])

        # Other labels reuse glyph definitions stored inside the original ticks.
        for definition in original.xpath(".//svg:defs/*", namespaces=NS):
            root_defs.append(deepcopy(definition))

        replacement = etree.Element(f"{{{SVG_NS}}}g", id=f"text_{index}")
        title = etree.SubElement(replacement, f"{{{SVG_NS}}}title")
        title.text = " ".join(lines)
        for line, offset in zip(lines, rows):
            path = TextPath((0, 0), line, prop=FONT, size=10)
            advance, _, _ = TextToPath().get_text_width_height_descent(line, FONT, ismath=False)
            x, y = anchor - advance / 2, baseline + offset
            element = etree.SubElement(replacement, f"{{{SVG_NS}}}path")
            element.set("d", path_commands(path))
            element.set("transform", f"translate({x:.6f} {y:.6f}) scale(1 -1)")
            element.set("style", "fill: #000000")
            replacement.append(etree.Comment(f" {line} "))
            bounds = path.get_extents()
            boxes.append((index, line, x + bounds.x0, y - bounds.y1, x + bounds.x1, y - bounds.y0))
        tick.replace(original, replacement)

    height = max(box[5] for box in boxes) + 9
    root.set("height", f"{height:.6f}pt")
    root.set("viewBox", f"0 0 {width:.6f} {height:.6f}")
    background = root.xpath('//svg:g[@id="patch_1"]/svg:path', namespaces=NS)[0]
    background.set("d", f"M 0 {height:.6f}\nL {width:.6f} {height:.6f}\nL {width:.6f} 0\nL 0 0\nz")

    for i, first in enumerate(boxes):
        assert first[2] >= 0 and first[4] <= width
        assert first[3] > 302.214125 and first[5] < height
        for second in boxes[i + 1 :]:
            overlap = (min(first[4], second[4]) > max(first[2], second[2])
                       and min(first[5], second[5]) > max(first[3], second[3]))
            assert not overlap, f"Overlapping labels: {first[:2]} and {second[:2]}"

    # Preserve every original node except the tick text and page background.
    before = etree.parse(str(source))
    after = deepcopy(document)
    for tree in (before, after):
        for index in range(1, 5):
            element = tree.xpath(f'//svg:g[@id="text_{index}"]', namespaces=NS)[0]
            element.getparent().remove(element)
        tree.xpath('//svg:g[@id="patch_1"]', namespaces=NS)[0].getparent().remove(
            tree.xpath('//svg:g[@id="patch_1"]', namespaces=NS)[0]
        )
        for definition in tree.getroot().find(f"{{{SVG_NS}}}defs"):
            if definition.get("id") in glyph_ids:
                definition.getparent().remove(definition)
        for attribute in ("height", "viewBox"):
            tree.getroot().attrib.pop(attribute, None)
    assert etree.tostring(before) == etree.tostring(after), "An unrelated plot element changed"

    destination.parent.mkdir(parents=True, exist_ok=True)
    document.write(str(destination), xml_declaration=True, encoding="utf-8")
    gaps = []
    for row in range(5):
        row_boxes = boxes[row::5]
        gaps.extend(second[2] - first[4] for first, second in zip(row_boxes, row_boxes[1:]))
    print(f"Saved {destination}")
    print(f"Figure size: {width:.3f} x {height:.3f} pt")
    print(f"Minimum gap between neighboring labels: {min(gaps):.2f} pt")
    print("All plot elements preserved; label bounds checked for overlap and clipping.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("outputs/fig2_pattern_decomposition.svg"))
    parser.add_argument("--output", type=Path, default=Path("outputs/2.1 Epilepsia - R1/fig2_pattern_decomposition.svg"))
    arguments = parser.parse_args()
    revise(arguments.source, arguments.output)
