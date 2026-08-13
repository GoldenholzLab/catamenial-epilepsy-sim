from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import textwrap
from contextlib import redirect_stdout
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
MPLCONFIGDIR = Path("/tmp") / "catamenial-epilepsy-sim-mplconfig"
CACHE_DIR = Path("/tmp") / "catamenial-epilepsy-sim-cache"
NOTEBOOK_PATH = ROOT / "running_an_example.ipynb"

os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_DIR))
MPLCONFIGDIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def to_source_lines(text: str) -> List[str]:
    """Convert a source block to notebook JSON line format."""

    if not text:
        return []
    return [f"{line}\n" for line in text.splitlines()]


def markdown_cell(text: str) -> Dict[str, object]:
    """Return a notebook markdown cell."""

    source = textwrap.dedent(text).strip()
    return {
        "cell_type": "markdown",
        "id": hashlib.sha256(f"markdown\0{source}".encode("utf-8")).hexdigest()[:12],
        "metadata": {},
        "source": to_source_lines(source),
    }


def code_cell(text: str, execution_count: int | None = None, stdout: str = "") -> Dict[str, object]:
    """Return a notebook code cell with optional captured stdout."""

    source = textwrap.dedent(text).strip()
    outputs: List[Dict[str, object]] = []
    if stdout:
        outputs.append(
            {
                "name": "stdout",
                "output_type": "stream",
                "text": to_source_lines(stdout.rstrip("\n")),
            }
        )
    return {
        "cell_type": "code",
        "id": hashlib.sha256(f"code\0{source}".encode("utf-8")).hexdigest()[:12],
        "metadata": {},
        "execution_count": execution_count,
        "outputs": outputs,
        "source": to_source_lines(source),
    }


def dataframe_to_markdown(rows: List[Dict[str, object]], columns: List[str]) -> str:
    """Render a list of dictionaries as a markdown table."""

    def _format(value: object) -> str:
        if isinstance(value, float):
            return f"{value:.3f}".rstrip("0").rstrip(".")
        return str(value)

    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(_format(row.get(column, "")) for column in columns) + " |")
    return "\n".join([header, divider, *body])


IMPORTS_CODE = """
from __future__ import annotations

import csv
import math
import os
import random
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "src"))
MPLCONFIGDIR = Path("/tmp") / "catamenial-epilepsy-sim-mplconfig"
CACHE_DIR = Path("/tmp") / "catamenial-epilepsy-sim-cache"
MPLCONFIGDIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_DIR))

import matplotlib.pyplot as plt
import pandas as pd

OUTPUT_DIR = ROOT / "examples" / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EXAMPLE1000_PATH = ROOT / "example1000.csv"
ONE_HEALTHY_PATH = ROOT / "oneHealthy.csv"
COHORT_OVERVIEW_FIG = OUTPUT_DIR / "running_example_cohort_overview.png"
COHORT_AGE_FIG = OUTPUT_DIR / "running_example_age_patterns.png"
HEALTHY_FIG = OUTPUT_DIR / "running_example_one_healthy.png"
HEALTHY_KINETICS_FIG = OUTPUT_DIR / "running_example_hormone_kinetics.png"

SEED = 20260315
NUM_PATIENTS = 1000
DAYS = 365 * 3

LARC_TO_IUD_SHARE = 8.1 / 10.5
LNG_IUD_SHARE = 541_635 / (541_635 + 99_389)
COPPER_IUD_SHARE = 1.0 - LNG_IUD_SHARE
PCOS_PREVALENCE = 0.066
DYSMENORRHEA_PREVALENCE = 0.20

US_INPUT_CITATIONS = {
    "daniels_abma_2025": {
        "label": "Daniels and Abma 2025",
        "reference": (
            "Daniels K, Abma JC. Current contraceptive status among females ages 15-49: "
            "United States, 2022-2023. NCHS Data Brief. 2025 Aug;(539):1-11. "
            "doi:10.15620/cdc/174618."
        ),
        "url": "https://www.cdc.gov/nchs/products/databriefs/db539.htm",
    },
    "azziz_2004": {
        "label": "Azziz et al. 2004",
        "reference": (
            "Azziz R, Woods KS, Reyna R, Key TJ, Knochenhauer ES, Yildiz BO. "
            "The prevalence and features of the polycystic ovary syndrome in an unselected "
            "population. Journal of Clinical Endocrinology & Metabolism. 2004;89(6):2745-2749. "
            "doi:10.1210/jc.2003-032046."
        ),
        "url": "https://pubmed.ncbi.nlm.nih.gov/15181052/",
    },
    "ju_2014": {
        "label": "Ju et al. 2014",
        "reference": (
            "Ju H, Jones M, Mishra G. The prevalence and risk factors of dysmenorrhea. "
            "Epidemiologic Reviews. 2014;36:104-113. doi:10.1093/epirev/mxt009."
        ),
        "url": "https://pubmed.ncbi.nlm.nih.gov/24284871/",
    },
    "marcus_2020": {
        "label": "Marcus et al. 2020",
        "reference": (
            "Marcus JL, Snowden JM, Murray Horwitz ME, et al. Use of intrauterine devices and "
            "risk of human immunodeficiency virus acquisition among insured women in the United "
            "States. Clinical Infectious Diseases. 2020;70(10):2221-2223. doi:10.1093/cid/ciz791."
        ),
        "url": "https://pubmed.ncbi.nlm.nih.gov/31412356/",
    },
}

from hormone_cycler.literature import CITATIONS
from hormone_cycler.model import simulate_diary
from hormone_cycler.types import MedicalFactors
"""


HELPERS_CODE = """
def balanced_ages(num_patients: int, seed: int) -> list[float]:
    \"\"\"Return a balanced age spread across the requested 12-52 year range.\"\"\"

    rng = random.Random(seed)
    ages = list(range(12, 53))
    base = num_patients // len(ages)
    remainder = num_patients % len(ages)
    values: list[float] = []
    for index, age in enumerate(ages):
        count = base + (1 if index < remainder else 0)
        for _ in range(count):
            jitter = rng.uniform(-0.45, 0.45)
            values.append(round(min(52.0, max(12.0, age + jitter)), 1))
    rng.shuffle(values)
    return values


def contraceptive_probabilities(age_years: float) -> dict[str, float]:
    \"\"\"Return age-specific medication probabilities from NSFG 2022-2023.\"\"\"

    if age_years < 15.0 or age_years >= 50.0:
        return {"pill": 0.0, "hormonal_iud": 0.0, "copper_iud": 0.0}

    if age_years < 20.0:
        pill = 0.142
        larc = 0.046
    elif age_years < 30.0:
        pill = 0.168
        larc = 0.138
    elif age_years < 40.0:
        pill = 0.090
        larc = 0.124
    else:
        pill = 0.069
        larc = 0.081

    iud_total = larc * LARC_TO_IUD_SHARE
    return {
        "pill": pill,
        "hormonal_iud": iud_total * LNG_IUD_SHARE,
        "copper_iud": iud_total * COPPER_IUD_SHARE,
    }


def assign_medical_factors(age_years: float, rng: random.Random) -> MedicalFactors:
    \"\"\"Sample one factor profile using published prevalence inputs.\"\"\"

    probabilities = contraceptive_probabilities(age_years)
    draw = rng.random()
    oral_contraceptive_mode = None
    hormonal_iud = False
    copper_iud = False

    if draw < probabilities["pill"]:
        oral_contraceptive_mode = "cyclic"
    elif draw < probabilities["pill"] + probabilities["hormonal_iud"]:
        hormonal_iud = True
    elif draw < probabilities["pill"] + probabilities["hormonal_iud"] + probabilities["copper_iud"]:
        copper_iud = True

    return MedicalFactors(
        pcos=rng.random() < PCOS_PREVALENCE,
        oral_contraceptive_mode=oral_contraceptive_mode,
        hormonal_iud=hormonal_iud,
        copper_iud=copper_iud,
        dysmenorrhea=rng.random() < DYSMENORRHEA_PREVALENCE,
    )


def flatten_daily_row(row: dict[str, object]) -> dict[str, object]:
    \"\"\"Expand nested medical factor dictionaries into analysis-friendly columns.\"\"\"

    factors = row.pop("medical_factors", {})
    flat = dict(row)
    flat["pcos"] = int(bool(factors.get("pcos", False)))
    flat["oral_contraceptive_mode"] = factors.get("oral_contraceptive_mode") or "none"
    flat["hormonal_iud"] = int(bool(factors.get("hormonal_iud", False)))
    flat["copper_iud"] = int(bool(factors.get("copper_iud", False)))
    flat["perimenopause"] = int(bool(factors.get("perimenopause", False)))
    flat["peri_menarche"] = int(bool(factors.get("peri_menarche", False)))
    flat["dysmenorrhea"] = int(bool(factors.get("dysmenorrhea", False)))
    if flat["oral_contraceptive_mode"] != "none":
        flat["medication_category"] = "oral_contraceptive"
    elif flat["hormonal_iud"]:
        flat["medication_category"] = "hormonal_iud"
    elif flat["copper_iud"]:
        flat["medication_category"] = "copper_iud"
    else:
        flat["medication_category"] = "none"
    return flat


def flatten_cycle_row(row: dict[str, object]) -> dict[str, object]:
    factors = row.pop("medical_factors", {})
    flat = dict(row)
    flat["pcos"] = int(bool(factors.get("pcos", False)))
    flat["oral_contraceptive_mode"] = factors.get("oral_contraceptive_mode") or "none"
    flat["hormonal_iud"] = int(bool(factors.get("hormonal_iud", False)))
    flat["copper_iud"] = int(bool(factors.get("copper_iud", False)))
    flat["dysmenorrhea"] = int(bool(factors.get("dysmenorrhea", False)))
    return flat


def age_group(age_years: float) -> str:
    if age_years < 20.0:
        return "12-19"
    if age_years < 30.0:
        return "20-29"
    if age_years < 40.0:
        return "30-39"
    return "40-52"


def mean_absolute_adjacent_difference(cycle_lengths: list[int]) -> float:
    if len(cycle_lengths) < 2:
        return float("nan")
    diffs = [abs(right - left) for left, right in zip(cycle_lengths[:-1], cycle_lengths[1:])]
    return sum(diffs) / len(diffs)
"""


COHORT_CODE = """
rng = random.Random(SEED)
ages = balanced_ages(NUM_PATIENTS, SEED)
profiles: list[dict[str, object]] = []
cycle_rows: list[dict[str, object]] = []

daily_fieldnames = [
    "patient_id",
    "day_index",
    "age_years",
    "cycle_index",
    "cycle_day",
    "cycle_length",
    "estradiol_pg_ml",
    "progesterone_ng_ml",
    "ovulation",
    "uterine_bleeding",
    "pcos",
    "oral_contraceptive_mode",
    "hormonal_iud",
    "copper_iud",
    "perimenopause",
    "peri_menarche",
    "dysmenorrhea",
    "medication_category",
]

with EXAMPLE1000_PATH.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=daily_fieldnames)
    writer.writeheader()
    for patient_index, age_years in enumerate(ages, start=1):
        factors = assign_medical_factors(age_years, rng)
        patient_seed = rng.randint(0, 2**31 - 1)
        patient_id = f"example-{patient_index:04d}"
        result = simulate_diary(
            days=DAYS,
            age_years=age_years,
            medical_factors=factors,
            seed=patient_seed,
            patient_id=patient_id,
        )
        profile = result.profile.to_dict()
        profile["age_group"] = age_group(float(profile["age_years"]))
        profile["pcos"] = int(bool(profile["medical_factors"]["pcos"]))
        profile["dysmenorrhea"] = int(bool(profile["medical_factors"]["dysmenorrhea"]))
        profile["oral_contraceptive_mode"] = profile["medical_factors"]["oral_contraceptive_mode"] or "none"
        profile["hormonal_iud"] = int(bool(profile["medical_factors"]["hormonal_iud"]))
        profile["copper_iud"] = int(bool(profile["medical_factors"]["copper_iud"]))
        if profile["oral_contraceptive_mode"] != "none":
            profile["medication_category"] = "oral_contraceptive"
        elif profile["hormonal_iud"]:
            profile["medication_category"] = "hormonal_iud"
        elif profile["copper_iud"]:
            profile["medication_category"] = "copper_iud"
        else:
            profile["medication_category"] = "none"
        profiles.append(profile)

        for cycle in result.cycles:
            cycle_row = flatten_cycle_row(cycle.to_dict())
            cycle_row["age_group"] = age_group(float(cycle_row["age_years"]))
            cycle_rows.append(cycle_row)

        for row in result.diary:
            writer.writerow(flatten_daily_row(row.to_dict()))

profiles_df = pd.DataFrame(profiles)
cycles_df = pd.DataFrame(cycle_rows)

patient_irregularity = (
    cycles_df.sort_values(["patient_id", "cycle_index"])
    .groupby("patient_id")["cycle_length"]
    .apply(lambda s: mean_absolute_adjacent_difference([int(value) for value in s.tolist()]))
    .reset_index(name="mean_absolute_adjacent_difference_days")
)
profiles_df = profiles_df.merge(patient_irregularity, on="patient_id", how="left")
profiles_df["irregular_participant"] = (
    profiles_df["mean_absolute_adjacent_difference_days"] >= 7.0
)

factor_summary_df = pd.DataFrame(
    [
        {"feature": "PCOS", "patients": int(profiles_df["pcos"].sum()), "percent": 100.0 * profiles_df["pcos"].mean()},
        {
            "feature": "Dysmenorrhea",
            "patients": int(profiles_df["dysmenorrhea"].sum()),
            "percent": 100.0 * profiles_df["dysmenorrhea"].mean(),
        },
        {
            "feature": "Cyclic oral contraceptive",
            "patients": int((profiles_df["oral_contraceptive_mode"] == "cyclic").sum()),
            "percent": 100.0 * (profiles_df["oral_contraceptive_mode"] == "cyclic").mean(),
        },
        {
            "feature": "Hormonal IUD",
            "patients": int(profiles_df["hormonal_iud"].sum()),
            "percent": 100.0 * profiles_df["hormonal_iud"].mean(),
        },
        {
            "feature": "Copper IUD",
            "patients": int(profiles_df["copper_iud"].sum()),
            "percent": 100.0 * profiles_df["copper_iud"].mean(),
        },
    ]
)

cohort_summary_df = pd.DataFrame(
    [
        {"metric": "Patients", "value": len(profiles_df)},
        {"metric": "Diary days per patient", "value": DAYS},
        {"metric": "Mean age (years)", "value": profiles_df["age_years"].mean()},
        {"metric": "Median age (years)", "value": profiles_df["age_years"].median()},
        {"metric": "Mean personal cycle length target (days)", "value": profiles_df["personal_cycle_mean_days"].mean()},
        {"metric": "Observed mean cycle length (days)", "value": cycles_df["cycle_length"].mean()},
        {"metric": "Observed ovulatory cycle rate", "value": cycles_df["ovulatory"].mean()},
        {"metric": "Observed mean bleeding days per cycle", "value": cycles_df["bleeding_days"].mean()},
        {"metric": "Mean absolute adjacent-cycle difference (days)", "value": profiles_df["mean_absolute_adjacent_difference_days"].dropna().mean()},
        {"metric": "Participants meeting the >=7-day irregularity definition", "value": profiles_df["irregular_participant"].mean()},
    ]
)

age_band_summary_df = (
    cycles_df.groupby("age_group")
    .agg(
        patients=("patient_id", "nunique"),
        cycles=("cycle_index", "count"),
        mean_cycle_length=("cycle_length", "mean"),
        ovulatory_cycle_rate=("ovulatory", "mean"),
        mean_bleeding_days=("bleeding_days", "mean"),
    )
    .reset_index()
)

medication_by_age_df = (
    profiles_df.groupby(["age_group", "medication_category"])
    .size()
    .unstack(fill_value=0)
    .reindex(columns=["none", "oral_contraceptive", "hormonal_iud", "copper_iud"], fill_value=0)
)

print(f"Wrote cohort diary CSV to {EXAMPLE1000_PATH}")
print(f"Simulated {len(profiles_df)} patients and {len(cycles_df)} complete or truncated cycles")
"""


COHORT_FIGURES_CODE = """
plt.style.use("seaborn-v0_8-whitegrid")
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

axes[0, 0].hist(profiles_df["age_years"], bins=20, color="#4C72B0", edgecolor="white")
axes[0, 0].set_title("Age distribution")
axes[0, 0].set_xlabel("Age (years)")
axes[0, 0].set_ylabel("Patients")

axes[0, 1].bar(
    factor_summary_df["feature"],
    factor_summary_df["percent"],
    color=["#C44E52", "#55A868", "#8172B3", "#CCB974", "#64B5CD"],
)
axes[0, 1].set_title("Assigned condition and medication prevalence")
axes[0, 1].set_ylabel("Percent of patients")
axes[0, 1].tick_params(axis="x", rotation=25)

box_groups = [cycles_df.loc[cycles_df["age_group"] == label, "cycle_length"] for label in ["12-19", "20-29", "30-39", "40-52"]]
axes[1, 0].boxplot(
    box_groups,
    tick_labels=["12-19", "20-29", "30-39", "40-52"],
    patch_artist=True,
)
axes[1, 0].set_title("Cycle length by age band")
axes[1, 0].set_ylabel("Cycle length (days)")

ovulation_rates = age_band_summary_df["ovulatory_cycle_rate"] * 100.0
axes[1, 1].plot(age_band_summary_df["age_group"], ovulation_rates, marker="o", linewidth=2, color="#4C72B0")
axes[1, 1].set_title("Ovulatory cycle rate by age band")
axes[1, 1].set_ylabel("Ovulatory cycles (%)")
axes[1, 1].set_ylim(0, 100)

fig.suptitle("Cohort overview: 1,000 simulated females over 3 years", fontsize=15)
fig.tight_layout()
fig.savefig(COHORT_OVERVIEW_FIG, dpi=180, bbox_inches="tight")
plt.close(fig)

irregularity_by_age_df = (
    profiles_df.groupby("age_group")
    .agg(
        irregular_participant_prevalence=("irregular_participant", "mean"),
        mean_personal_target=("personal_cycle_mean_days", "mean"),
    )
    .reset_index()
)

medication_share_df = medication_by_age_df.div(medication_by_age_df.sum(axis=1), axis=0) * 100.0

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
axes[0].plot(
    irregularity_by_age_df["age_group"],
    irregularity_by_age_df["mean_personal_target"],
    marker="o",
    linewidth=2,
    color="#DD8452",
)
axes[0].set_title("Mean personal cycle target by age band")
axes[0].set_ylabel("Days")

left = pd.Series(0.0, index=medication_share_df.index)
colors = {
    "none": "#9A9A9A",
    "oral_contraceptive": "#8172B3",
    "hormonal_iud": "#64B5CD",
    "copper_iud": "#CCB974",
}
for column in medication_share_df.columns:
    axes[1].bar(
        medication_share_df.index,
        medication_share_df[column],
        bottom=left.values,
        label=column.replace("_", " "),
        color=colors[column],
    )
    left += medication_share_df[column]
axes[1].set_title("Medication mix by age band")
axes[1].set_ylabel("Percent of patients")
axes[1].legend(frameon=False, fontsize=9)

fig.tight_layout()
fig.savefig(COHORT_AGE_FIG, dpi=180, bbox_inches="tight")
plt.close(fig)

print(f"Wrote cohort figures to {COHORT_OVERVIEW_FIG} and {COHORT_AGE_FIG}")
"""


HEALTHY_CODE = """
healthy_result = simulate_diary(
    days=DAYS,
    age_years=30.0,
    medical_factors=MedicalFactors(),
    seed=SEED + 5000,
    patient_id="healthy-30y",
)

healthy_rows = [flatten_daily_row(row.to_dict()) for row in healthy_result.diary]
healthy_df = pd.DataFrame(healthy_rows)
healthy_df.to_csv(ONE_HEALTHY_PATH, index=False)

healthy_cycles_df = pd.DataFrame([flatten_cycle_row(cycle.to_dict()) for cycle in healthy_result.cycles])

complete_cycle_indices = [
    int(cycle_index)
    for cycle_index, group in healthy_df.groupby("cycle_index")
    if (
        len(group) == int(group["cycle_length"].iloc[0])
        and int(group["cycle_day"].iloc[0]) == 1
        and int(group["cycle_day"].iloc[-1]) == int(group["cycle_length"].iloc[0])
    )
]
complete_ovulatory_indices = [
    cycle_index
    for cycle_index in complete_cycle_indices
    if bool(healthy_cycles_df.loc[healthy_cycles_df["cycle_index"] == cycle_index, "ovulatory"].iloc[0])
]
kinetic_cycle_index = complete_ovulatory_indices[0]
kinetic_cycle_df = healthy_df.loc[healthy_df["cycle_index"] == kinetic_cycle_index].copy()
kinetic_following_df = healthy_df.loc[healthy_df["cycle_index"] == kinetic_cycle_index + 1].head(1)
kinetic_plot_df = pd.concat([kinetic_cycle_df, kinetic_following_df], ignore_index=True)

ovulation_day = int(kinetic_cycle_df.loc[kinetic_cycle_df["ovulation"] == 1, "cycle_day"].iloc[0])
follicular_e2 = kinetic_cycle_df.loc[kinetic_cycle_df["cycle_day"] <= ovulation_day, "estradiol_pg_ml"]
peak_width_days = int((follicular_e2 >= 0.80 * follicular_e2.max()).sum())
progesterone_values = kinetic_cycle_df["progesterone_ng_ml"].tolist()
progesterone_peak = max(progesterone_values)
progesterone_peak_day = progesterone_values.index(progesterone_peak) + 1
progesterone_plateau_days = sum(value >= 0.75 * progesterone_peak for value in progesterone_values)
progesterone_rise_day = next(
    day
    for day, value in enumerate(progesterone_values, start=1)
    if day >= ovulation_day and value >= 5.0
)
luteal_e2 = kinetic_cycle_df.loc[
    kinetic_cycle_df["cycle_day"] > ovulation_day, "estradiol_pg_ml"
]
luteal_e2_peak_ratio = float(luteal_e2.max() / follicular_e2.max())
withdrawal_transitions = 0
for earlier, later in zip(reversed(progesterone_values[:-1]), reversed(progesterone_values[1:])):
    if later < earlier:
        withdrawal_transitions += 1
    else:
        break
cross_cycle_jump = abs(
    float(kinetic_following_df["progesterone_ng_ml"].iloc[0])
    - float(kinetic_cycle_df["progesterone_ng_ml"].iloc[-1])
)

healthy_kinetics_df = pd.DataFrame(
    [
        {"metric": "Preovulatory estradiol width at >=80% maximum (days)", "value": peak_width_days},
        {"metric": "Luteal E2 peak / follicular E2 peak", "value": luteal_e2_peak_ratio},
        {"metric": "Progesterone width at >=75% maximum (days)", "value": progesterone_plateau_days},
        {"metric": "Progesterone peak offset from ovulation (days)", "value": progesterone_peak_day - ovulation_day},
        {"metric": "Progesterone 5 ng/mL rise offset (days)", "value": progesterone_rise_day - ovulation_day},
        {"metric": "Consecutive progesterone-decline transitions before bleeding", "value": withdrawal_transitions},
        {"metric": "Final-cycle progesterone / cycle maximum", "value": progesterone_values[-1] / max(progesterone_values)},
        {"metric": "Progesterone jump across cycle boundary (ng/mL)", "value": cross_cycle_jump},
    ]
)
healthy_summary_df = pd.DataFrame(
    [
        {"metric": "Diary days", "value": len(healthy_df)},
        {"metric": "Cycles captured", "value": len(healthy_cycles_df)},
        {"metric": "Mean cycle length (days)", "value": healthy_cycles_df["cycle_length"].mean()},
        {"metric": "Ovulatory cycle rate", "value": healthy_cycles_df["ovulatory"].mean()},
        {"metric": "Total ovulation events", "value": int(healthy_df["ovulation"].sum())},
        {"metric": "Total bleeding days", "value": int(healthy_df["uterine_bleeding"].sum())},
    ]
)

print(f"Wrote healthy-patient diary CSV to {ONE_HEALTHY_PATH}")
"""


HEALTHY_FIGURE_CODE = """
fig, axes = plt.subplots(3, 1, figsize=(15, 10), sharex=True)

axes[0].plot(healthy_df["day_index"], healthy_df["estradiol_pg_ml"], color="#C44E52", linewidth=1.2)
axes[0].set_ylabel("Estradiol\\n(pg/mL)")
axes[0].set_title("One healthy 30-year-old female over 3 years")

axes[1].plot(healthy_df["day_index"], healthy_df["progesterone_ng_ml"], color="#4C72B0", linewidth=1.2)
axes[1].set_ylabel("Progesterone\\n(ng/mL)")

axes[2].bar(
    healthy_df.loc[healthy_df["uterine_bleeding"] == 1, "day_index"],
    1,
    width=1.0,
    color="#DD8452",
    label="Menses",
)
ovulation_days = healthy_df.loc[healthy_df["ovulation"] == 1, "day_index"]
axes[2].scatter(ovulation_days, [1.05] * len(ovulation_days), color="#55A868", marker="^", s=28, label="Ovulation")
axes[2].set_ylabel("Events")
axes[2].set_xlabel("Day index")
axes[2].set_ylim(0, 1.25)
axes[2].legend(frameon=False, loc="upper right")

fig.tight_layout()
fig.savefig(HEALTHY_FIG, dpi=180, bbox_inches="tight")
plt.close(fig)

print(f"Wrote healthy-patient figure to {HEALTHY_FIG}")

fig, axes = plt.subplots(3, 1, figsize=(13, 8.5), sharex=True, gridspec_kw={"height_ratios": [3, 3, 1]})
x_values = list(range(1, len(kinetic_plot_df) + 1))
boundary_x = len(kinetic_cycle_df) + 0.5

axes[0].plot(x_values, kinetic_plot_df["estradiol_pg_ml"], color="#C44E52", linewidth=2.2)
axes[0].set_ylabel("Estradiol (pg/mL)")
axes[0].set_title("Complete ovulatory cycle and first day of the next cycle")

axes[1].plot(x_values, kinetic_plot_df["progesterone_ng_ml"], color="#4C72B0", linewidth=2.2)
axes[1].set_ylabel("Progesterone (ng/mL)")

bleeding_positions = [
    position
    for position, bleeding in zip(x_values, kinetic_plot_df["uterine_bleeding"])
    if int(bleeding) == 1
]
axes[2].bar(bleeding_positions, [1.0] * len(bleeding_positions), color="#DD8452", width=0.85, label="Bleeding")
ovulation_positions = [
    position
    for position, ovulation in zip(x_values, kinetic_plot_df["ovulation"])
    if int(ovulation) == 1
]
axes[2].scatter(ovulation_positions, [1.08] * len(ovulation_positions), marker="^", s=65, color="#55A868", label="Ovulation")
axes[2].set_ylabel("Events")
axes[2].set_xlabel("Day within displayed interval")
axes[2].set_ylim(0, 1.25)
axes[2].legend(frameon=False, loc="upper right")

for axis in axes:
    axis.axvline(boundary_x, color="#666666", linestyle="--", linewidth=1.2, label="Cycle boundary")
fig.suptitle("Hormone-waveform check: luteal E2 rebound and broad P4 summit", fontsize=15)
fig.tight_layout()
fig.savefig(HEALTHY_KINETICS_FIG, dpi=180, bbox_inches="tight")
plt.close(fig)

print(f"Wrote hormone-kinetic figure to {HEALTHY_KINETICS_FIG}")
"""


def execute_code(source: str, namespace: Dict[str, object]) -> str:
    """Execute a code cell source and capture stdout."""

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(textwrap.dedent(source), namespace)
    return buffer.getvalue()


def build_input_rows(namespace: Dict[str, object]) -> List[Dict[str, object]]:
    """Create a markdown-friendly table of cohort input assumptions."""

    larc_share = namespace["LARC_TO_IUD_SHARE"]
    lng_share = namespace["LNG_IUD_SHARE"]
    copper_share = namespace["COPPER_IUD_SHARE"]
    return [
        {
            "Input": "Age range",
            "Value used": "Balanced spread from 12.0 to 52.0 years",
            "Source / note": "User requested ages spanning 12-52; balanced rather than U.S.-weighted so all age ranges are represented.",
        },
        {
            "Input": "Oral contraceptive prevalence",
            "Value used": "15-19: 14.2%; 20-29: 16.8%; 30-39: 9.0%; 40-49: 6.9%; outside 15-49: 0%",
            "Source / note": "NSFG 2022-2023 pill use among all U.S. females ages 15-49 (Daniels and Abma 2025).",
        },
        {
            "Input": "IUD prevalence",
            "Value used": (
                f"Age-band LARC rate multiplied by IUD/LARC share ({larc_share:.3f}); "
                "outside 15-49: 0%"
            ),
            "Source / note": "Inference from Daniels and Abma 2025 because NSFG reports age-specific LARC use and overall IUD use separately.",
        },
        {
            "Input": "Hormonal vs copper IUD split",
            "Value used": f"{lng_share * 100:.1f}% hormonal IUD, {copper_share * 100:.1f}% copper IUD",
            "Source / note": "Inference from U.S. insured IUD insertions in Marcus et al. 2020.",
        },
        {
            "Input": "PCOS prevalence",
            "Value used": "6.6% of patients",
            "Source / note": "Azziz et al. 2004 U.S. unselected premenopausal sample.",
        },
        {
            "Input": "Dysmenorrhea prevalence",
            "Value used": "20% of patients",
            "Source / note": (
                "Conservative proxy for clinically meaningful dysmenorrhea, chosen inside the "
                "2%-29% severe-pain range summarized by Ju et al. 2014."
            ),
        },
        {
            "Input": "Peri-menarche / perimenopause flags",
            "Value used": "Not explicitly sampled",
            "Source / note": (
                "The simulator already encodes age effects from Li et al. 2023 and related calibration. "
                "Leaving these subgroup flags off avoids double counting explicit stage modifiers."
            ),
        },
    ]


def build_reference_markdown(namespace: Dict[str, object]) -> str:
    """Render full citations used in the notebook."""

    literature = namespace["CITATIONS"]
    extra = namespace["US_INPUT_CITATIONS"]

    lines = [
        "## Full citations",
        "",
        "The notebook uses the simulator's built-in calibration, held-out, context, and direction/range references plus four additional input-distribution references. Evidence roles are declared in the machine-readable validation report.",
        "",
    ]
    for citation in extra.values():
        lines.append(f"- {citation['reference']} [{citation['url']}]({citation['url']})")
    lines.append("")
    lines.append("### Simulator scientific-source registry")
    lines.append("")
    for citation in literature.values():
        lines.append(
            f"- **{citation.evidence_role}.** {citation.full_reference} "
            f"[{citation.url}]({citation.url})"
        )
    return "\n".join(lines)


def main() -> None:
    namespace: Dict[str, object] = {}

    imports_stdout = execute_code(IMPORTS_CODE, namespace)
    helpers_stdout = execute_code(HELPERS_CODE, namespace)
    cohort_stdout = execute_code(COHORT_CODE, namespace)
    cohort_fig_stdout = execute_code(COHORT_FIGURES_CODE, namespace)
    healthy_stdout = execute_code(HEALTHY_CODE, namespace)
    healthy_fig_stdout = execute_code(HEALTHY_FIGURE_CODE, namespace)

    input_rows = build_input_rows(namespace)
    input_table = dataframe_to_markdown(input_rows, ["Input", "Value used", "Source / note"])

    cohort_summary_df = namespace["cohort_summary_df"]
    factor_summary_df = namespace["factor_summary_df"]
    age_band_summary_df = namespace["age_band_summary_df"]
    healthy_summary_df = namespace["healthy_summary_df"]
    healthy_kinetics_df = namespace["healthy_kinetics_df"]

    cohort_summary_rows = cohort_summary_df.to_dict(orient="records")
    factor_summary_rows = factor_summary_df.to_dict(orient="records")
    age_band_summary_rows = age_band_summary_df.to_dict(orient="records")
    healthy_summary_rows = healthy_summary_df.to_dict(orient="records")

    cohort_summary_table = dataframe_to_markdown(cohort_summary_rows, ["metric", "value"])
    factor_summary_table = dataframe_to_markdown(factor_summary_rows, ["feature", "patients", "percent"])
    age_band_summary_table = dataframe_to_markdown(
        age_band_summary_rows,
        ["age_group", "patients", "cycles", "mean_cycle_length", "ovulatory_cycle_rate", "mean_bleeding_days"],
    )
    healthy_summary_table = dataframe_to_markdown(healthy_summary_rows, ["metric", "value"])
    healthy_kinetics_table = dataframe_to_markdown(
        healthy_kinetics_df.to_dict(orient="records"), ["metric", "value"]
    )

    overview_fig = namespace["COHORT_OVERVIEW_FIG"].relative_to(ROOT)
    age_fig = namespace["COHORT_AGE_FIG"].relative_to(ROOT)
    healthy_fig = namespace["HEALTHY_FIG"].relative_to(ROOT)
    healthy_kinetics_fig = namespace["HEALTHY_KINETICS_FIG"].relative_to(ROOT)

    references_md = build_reference_markdown(namespace)

    cells = [
        markdown_cell(
            """
            # `running_an_example`

            This notebook simulates a 1,000-female cohort for 3 years and one healthy 30-year-old female for 3 years using the existing `hormone_cycler` simulator.

            Design choices used here:

            - Ages are deliberately balanced across 12-52 years so the cohort spans the full requested range.
            - Medication probabilities are taken from U.S. National Survey of Family Growth estimates when the simulator can represent the method directly.
            - PCOS and dysmenorrhea prevalences are mapped onto the simulator's supported factor flags using published prevalence data.
            - Explicit `peri_menarche` and `perimenopause` subgroup flags are left off because the simulator already embeds age effects in its baseline cycle model, and enabling those flags across the general population would double count stage effects.
            - Participant irregularity uses the Apple Women's Health Study participant-level estimand: mean adjacent-cycle difference of at least seven days. The table footnote omits “absolute,” but the methods define adjacent-cycle differences as absolute values; the notebook follows that convention.
            """
        ),
        code_cell(IMPORTS_CODE, execution_count=1, stdout=imports_stdout),
        code_cell(HELPERS_CODE, execution_count=2, stdout=helpers_stdout),
        markdown_cell(
            f"""
            ## Published input assumptions

            {input_table}

            Notes:

            - The age-specific IUD probabilities are an explicit inference: Daniels and Abma 2025 give age-specific LARC rates and overall IUD prevalence, so the notebook multiplies each age-band LARC rate by the overall IUD/LARC ratio.
            - The hormonal-versus-copper IUD split is also an inference from U.S. insertion data, because the NSFG brief does not break current IUD use out by device type.
            - The dysmenorrhea input is intentionally conservative because the simulator's `dysmenorrhea` flag represents a clinically relevant phenotype rather than any mild menstrual discomfort.
            """
        ),
        code_cell(COHORT_CODE, execution_count=3, stdout=cohort_stdout),
        markdown_cell(
            f"""
            ## Cohort summary statistics

            ### Overall cohort summary

            {cohort_summary_table}

            ### Assigned medications and medical problems

            {factor_summary_table}

            ### Cycle outcomes by age band

            {age_band_summary_table}
            """
        ),
        code_cell(COHORT_FIGURES_CODE, execution_count=4, stdout=cohort_fig_stdout),
        markdown_cell(
            f"""
            ## Cohort figures

            ![Cohort overview]({overview_fig.as_posix()})

            ![Age-pattern figure]({age_fig.as_posix()})
            """
        ),
        code_cell(HEALTHY_CODE, execution_count=5, stdout=healthy_stdout),
        markdown_cell(
            f"""
            ## One healthy 30-year-old female

            {healthy_summary_table}
            """
        ),
        code_cell(HEALTHY_FIGURE_CODE, execution_count=6, stdout=healthy_fig_stdout),
        markdown_cell(
            f"""
            ## Healthy-patient plot

            ![Healthy patient figure]({healthy_fig.as_posix()})

            ### Hormone-kinetic verification

            The zoomed cycle below uses separate physical scales for estradiol and progesterone,
            shows the secondary luteal estradiol rise and broadened progesterone summit, and
            includes the first day of the following cycle so the absence of a vertical reset is
            directly visible. The waveform uses all daily LH-aligned Stricker serum medians; its
            subphase amplitudes are checked independently against Anckaert et al.'s 85-woman cohort.

            {healthy_kinetics_table}

            ![Hormone kinetic verification]({healthy_kinetics_fig.as_posix()})
            """
        ),
        markdown_cell(references_md),
    ]

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": ".".join(map(str, sys.version_info[:3])),
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    NOTEBOOK_PATH.write_text(json.dumps(notebook, indent=2), encoding="utf-8")
    print(f"Wrote notebook to {NOTEBOOK_PATH}")


if __name__ == "__main__":
    main()
