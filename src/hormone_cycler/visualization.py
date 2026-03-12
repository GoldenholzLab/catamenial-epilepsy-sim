"""SVG visualizer for individual cycle diaries."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from .model import simulate_diary
from .types import DailyRecord, MedicalFactors


def _load_rows(input_path: Path) -> List[Dict[str, object]]:
    """Load diary rows from a CSV or JSON file."""

    if input_path.suffix.lower() == ".json":
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "diary" in payload:
            return list(payload["diary"])
        if isinstance(payload, list):
            return payload
        raise ValueError("Unsupported JSON structure for visualization input.")
    rows: List[Dict[str, object]] = []
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows.extend(reader)
    return rows


def _coerce_rows(rows: Iterable[Dict[str, object]]) -> List[DailyRecord]:
    """Convert loosely typed serialized diary rows into :class:`DailyRecord` instances."""

    coerced: List[DailyRecord] = []
    for row in rows:
        coerced.append(
            DailyRecord(
                patient_id=str(row["patient_id"]),
                day_index=int(row["day_index"]),
                age_years=float(row["age_years"]),
                cycle_index=int(row["cycle_index"]),
                cycle_day=int(row["cycle_day"]),
                cycle_length=int(row["cycle_length"]),
                estradiol_pg_ml=float(row["estradiol_pg_ml"]),
                progesterone_ng_ml=float(row["progesterone_ng_ml"]),
                ovulation=int(row["ovulation"]),
                uterine_bleeding=int(row["uterine_bleeding"]),
                medical_factors={},
            )
        )
    return coerced


def _polyline(points: Sequence[tuple], stroke: str, stroke_width: float = 2.0) -> str:
    """Convert point tuples into an SVG polyline element string."""

    encoded = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return (
        f'<polyline fill="none" stroke="{stroke}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round" points="{encoded}" />'
    )


def render_svg(records: Sequence[DailyRecord], title: str = "Hormone Cycle") -> str:
    """Render a diary as a standalone SVG string.

    Args:
        records: Ordered daily records from one simulated patient.
        title: Plot title to display at the top of the figure.

    Returns:
        SVG markup as a string.
    """

    if not records:
        raise ValueError("No records available to visualize.")

    width = 1200
    height = 720
    margin_left = 78
    margin_right = 24
    hormone_top = 70
    hormone_height = 420
    event_top = 540
    event_height = 110
    plot_width = width - margin_left - margin_right

    estradiol_max = max(record.estradiol_pg_ml for record in records) * 1.1
    progesterone_max = max(record.progesterone_ng_ml for record in records) * 1.1
    total_days = len(records)

    def x_pos(day_index: int) -> float:
        if total_days == 1:
            return margin_left + plot_width / 2
        return margin_left + (day_index - 1) / (total_days - 1) * plot_width

    def e2_y(value: float) -> float:
        return hormone_top + hormone_height - (value / estradiol_max) * hormone_height

    def p4_y(value: float) -> float:
        return hormone_top + hormone_height - (value / progesterone_max) * hormone_height

    estradiol_points = [(x_pos(record.day_index), e2_y(record.estradiol_pg_ml)) for record in records]
    progesterone_points = [(x_pos(record.day_index), p4_y(record.progesterone_ng_ml)) for record in records]

    grid_lines = []
    for step in range(6):
        y = hormone_top + hormone_height * step / 5
        grid_lines.append(f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" stroke="#d7dee6" stroke-width="1" />')

    day_ticks = []
    for step in range(min(total_days, 12)):
        day = 1 + round(step * (total_days - 1) / max(1, min(total_days, 12) - 1))
        x = x_pos(day)
        day_ticks.append(f'<line x1="{x:.1f}" y1="{event_top + event_height}" x2="{x:.1f}" y2="{event_top + event_height + 8}" stroke="#1f2933" stroke-width="1" />')
        day_ticks.append(f'<text x="{x:.1f}" y="{event_top + event_height + 24}" text-anchor="middle" font-size="12" fill="#1f2933">Day {day}</text>')

    bleeding_rects = []
    ovulation_markers = []
    for record in records:
        x = x_pos(record.day_index)
        if record.uterine_bleeding:
            bleeding_rects.append(
                f'<rect x="{x - 3:.1f}" y="{event_top + 44}" width="6" height="34" rx="2" fill="#c03221" opacity="0.88" />'
            )
        if record.ovulation:
            ovulation_markers.append(
                f'<circle cx="{x:.1f}" cy="{event_top + 24}" r="7" fill="#2f855a" />'
            )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#f7f3ea" />',
            '<rect x="24" y="24" width="1152" height="672" rx="22" fill="#fffdf8" stroke="#d6c7ae" stroke-width="2" />',
            f'<text x="{margin_left}" y="44" font-size="24" font-family="Georgia, serif" fill="#2d3748">{title}</text>',
            f'<text x="{margin_left}" y="64" font-size="13" font-family="Arial, sans-serif" fill="#4a5568">Estradiol and progesterone trajectories with bleeding and ovulation events</text>',
            *grid_lines,
            f'<line x1="{margin_left}" y1="{hormone_top}" x2="{margin_left}" y2="{hormone_top + hormone_height}" stroke="#1f2933" stroke-width="1.5" />',
            f'<line x1="{margin_left}" y1="{hormone_top + hormone_height}" x2="{width - margin_right}" y2="{hormone_top + hormone_height}" stroke="#1f2933" stroke-width="1.5" />',
            f'<line x1="{margin_left}" y1="{event_top + event_height}" x2="{width - margin_right}" y2="{event_top + event_height}" stroke="#1f2933" stroke-width="1.5" />',
            _polyline(estradiol_points, "#d97706", 3.0),
            _polyline(progesterone_points, "#2563eb", 3.0),
            f'<text x="{margin_left}" y="{hormone_top - 16}" font-size="14" fill="#d97706">Estradiol (pg/mL)</text>',
            f'<text x="{margin_left + 180}" y="{hormone_top - 16}" font-size="14" fill="#2563eb">Progesterone (ng/mL)</text>',
            f'<text x="{margin_left}" y="{event_top + 20}" font-size="14" fill="#2f855a">Ovulation</text>',
            f'<text x="{margin_left}" y="{event_top + 92}" font-size="14" fill="#c03221">Bleeding</text>',
            *bleeding_rects,
            *ovulation_markers,
            *day_ticks,
            "</svg>",
        ]
    )


def write_svg(records: Sequence[DailyRecord], output_path: Path, title: str = "Hormone Cycle") -> None:
    """Render a diary to SVG and write it to disk."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_svg(records, title=title), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for ``vis_cycles``."""

    parser = argparse.ArgumentParser(prog="vis_cycles", description="Render an SVG graph of a simulated hormone diary.")
    parser.add_argument("--input", type=Path, help="CSV or JSON diary/result input.")
    parser.add_argument("--output", type=Path, required=True, help="SVG output path.")
    parser.add_argument("--title", default="Hormone Cycle", help="Plot title.")
    parser.add_argument("--days", type=int, default=120, help="If no input is supplied, simulate this many days.")
    parser.add_argument("--age", type=float, default=30.0, help="Age for on-the-fly simulation.")
    parser.add_argument("--seed", type=int, default=11, help="Random seed for on-the-fly simulation.")
    parser.add_argument("--pcos", action="store_true")
    parser.add_argument("--hormonal-iud", action="store_true")
    parser.add_argument("--copper-iud", action="store_true")
    parser.add_argument("--perimenopause", action="store_true")
    parser.add_argument("--peri-menarche", action="store_true")
    parser.add_argument("--dysmenorrhea", action="store_true")
    parser.add_argument("--oral-contraceptive-mode", choices=["cyclic", "continuous"])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the SVG visualization CLI.

    Args:
        argv: Optional argument vector. When omitted, ``argparse`` reads ``sys.argv``.

    Returns:
        Process exit status code.
    """

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.input:
        rows = _load_rows(args.input)
        records = _coerce_rows(rows)
    else:
        factors = MedicalFactors(
            pcos=args.pcos,
            oral_contraceptive_mode=args.oral_contraceptive_mode,
            hormonal_iud=args.hormonal_iud,
            copper_iud=args.copper_iud,
            perimenopause=args.perimenopause,
            peri_menarche=args.peri_menarche,
            dysmenorrhea=args.dysmenorrhea,
        )
        result = simulate_diary(args.days, args.age, medical_factors=factors, seed=args.seed)
        records = result.diary
    write_svg(records, args.output, title=args.title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
