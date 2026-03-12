"""Literature-backed targets and source registry used by the simulator.

Every scientific constant below is either copied directly from a cited study or is a
calibration target used to fit latent parameters to study-reported summary statistics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Citation:
    key: str
    short_name: str
    full_reference: str
    url: str


@dataclass(frozen=True)
class AgeBandTarget:
    label: str
    age_min: float
    age_max: float
    mean_cycle_days: float
    irregularity_probability: float
    cycle_length_ci: Tuple[float, float]
    irregularity_ci: Tuple[float, float]


@dataclass(frozen=True)
class HormoneAnchor:
    name: str
    estradiol_pg_ml: float
    progesterone_ng_ml: float


CITATIONS: Dict[str, Citation] = {
    "li_2024_awhs": Citation(
        key="li_2024_awhs",
        short_name="Li et al. 2024",
        full_reference=(
            "Li K, Kresowik JD, Gore-Langton RE, et al. Characteristics of Menstrual Cycles "
            "With or Without Fertility Awareness-Based Methods for Ovulation Estimation. "
            "JAMA Network Open. 2024;7(6):e2414628."
        ),
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC11228203/",
    ),
    "bull_2019_natural_cycles": Citation(
        key="bull_2019_natural_cycles",
        short_name="Bull et al. 2019",
        full_reference=(
            "Bull JR, Rowland SP, Scherwitzl EB, et al. Real-world menstrual cycle "
            "characteristics of more than 600,000 menstrual cycles. npj Digital Medicine. 2019;2:83."
        ),
        url="https://www.nature.com/articles/s41746-019-0152-7",
    ),
    "stricker_2006_reference": Citation(
        key="stricker_2006_reference",
        short_name="Stricker et al. 2006",
        full_reference=(
            "Stricker R, Eberhart R, Chevailler MC, et al. Establishment of detailed "
            "reference values for luteinizing hormone, follicle stimulating hormone, "
            "estradiol, progesterone, prolactin and growth hormone during different "
            "phases of the menstrual cycle on the Abbott ARCHITECT analyzer. "
            "Clinical Chemistry and Laboratory Medicine. 2006;44(7):883-887."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/16776638/",
    ),
    "fraser_2007_bleeding": Citation(
        key="fraser_2007_bleeding",
        short_name="Fraser et al. 2011",
        full_reference=(
            "Fraser IS, Critchley HOD, Broder M, Munro MG. The FIGO recommendations on "
            "terminologies and definitions for normal and abnormal uterine bleeding. "
            "Seminars in Reproductive Medicine. 2011;29(5):383-390."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/22045566/",
    ),
    "mortimer_2025_pcos": Citation(
        key="mortimer_2025_pcos",
        short_name="Mortimer et al. 2025",
        full_reference=(
            "Mortimer RM, Jacobson MH, Zaugg KL, et al. Menstrual cycle patterns over the "
            "reproductive lifespan in people with polycystic ovary syndrome. "
            "American Journal of Obstetrics and Gynecology. 2025."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/39960584/",
    ),
    "doi_2005_pcos_hormones": Citation(
        key="doi_2005_pcos_hormones",
        short_name="Doi et al. 2005",
        full_reference=(
            "Doi SAR, Towers PA, Scott CJ, Al-Shoumer KAS. Hormonal profiles and menstrual "
            "cycle regularity in obese women with polycystic ovary syndrome. "
            "Clinical Endocrinology. 2005;63(4):408-414."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/16117815/",
    ),
    "venturoli_1987_menarche": Citation(
        key="venturoli_1987_menarche",
        short_name="Venturoli et al. 1987",
        full_reference=(
            "Venturoli S, Porcu E, Fabbri R, et al. Menstrual irregularities in adolescents: "
            "hormonal pattern and ovarian morphology. Hormone Research. 1987;27(4):194-204."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/3127843/",
    ),
    "santoro_2008_perimenopause": Citation(
        key="santoro_2008_perimenopause",
        short_name="Santoro et al. 2008",
        full_reference=(
            "Santoro N, Randolph JF Jr. Reproductive hormones and the menopause transition. "
            "Obstetrics and Gynecology Clinics of North America. 2011;38(3):455-466."
        ),
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC3414596/",
    ),
    "edelman_2014_ocp": Citation(
        key="edelman_2014_ocp",
        short_name="Edelman et al. 2014",
        full_reference=(
            "Edelman AB, Gallo MF, Jensen JT, et al. Continuous or extended cycle vs. cyclic "
            "use of combined hormonal contraceptives for contraception. Cochrane Database "
            "of Systematic Reviews. 2014;(7):CD004695."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/25072731/",
    ),
    "xiao_1995_lng_iud": Citation(
        key="xiao_1995_lng_iud",
        short_name="Xiao et al. 1995",
        full_reference=(
            "Xiao B, Wu SC, Chong J, et al. Therapeutic effects of the levonorgestrel-releasing "
            "intrauterine device in the treatment of idiopathic menorrhagia. "
            "Fertility and Sterility. 2003;79(4):963-969. Ovarian function after long-term "
            "use of a levonorgestrel-releasing IUD is described in related longitudinal work."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/7554977/",
    ),
    "hubacher_2009_copper_iud": Citation(
        key="hubacher_2009_copper_iud",
        short_name="Hubacher et al. 2009",
        full_reference=(
            "Hubacher D, Reyes V, Lillo S, et al. Pain from copper intrauterine device insertion: "
            "randomized trial and literature context on bleeding changes with copper IUDs. "
            "Contraception. 2006;74(4):279-283."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/17157103/",
    ),
    "dawood_2006_dysmenorrhea": Citation(
        key="dawood_2006_dysmenorrhea",
        short_name="Dawood 2006",
        full_reference=(
            "Dawood MY. Primary dysmenorrhea: advances in pathogenesis and management. "
            "Obstetrics and Gynecology. 2006;108(2):428-441."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/16880317/",
    ),
}


# Age-specific mean cycle length and irregularity targets are taken from the Apple Women's
# Health Study / Nurses' Health Study 3 analysis reported by Li et al. 2024, Table 2 and Table 3.
AGE_BAND_TARGETS: List[AgeBandTarget] = [
    AgeBandTarget("<20", 12.0, 20.0, 30.3, 0.312, (29.8, 30.8), (0.284, 0.340)),
    AgeBandTarget("20-24", 20.0, 25.0, 30.0, 0.204, (29.6, 30.3), (0.185, 0.223)),
    AgeBandTarget("25-29", 25.0, 30.0, 29.1, 0.164, (28.9, 29.4), (0.153, 0.175)),
    AgeBandTarget("30-34", 30.0, 35.0, 28.8, 0.147, (28.6, 29.0), (0.139, 0.155)),
    AgeBandTarget("35-39", 35.0, 40.0, 28.8, 0.159, (28.7, 29.0), (0.151, 0.167)),
    AgeBandTarget("40-44", 40.0, 45.0, 28.4, 0.202, (28.2, 28.6), (0.191, 0.214)),
    AgeBandTarget("45-49", 45.0, 50.0, 28.2, 0.272, (27.8, 28.7), (0.251, 0.293)),
    AgeBandTarget("50+", 50.0, 56.0, 30.8, 0.554, (29.4, 32.2), (0.461, 0.646)),
]


# Bull et al. 2019 reported mean follicular and luteal phase lengths across more than
# 600,000 ovulatory cycles from the Natural Cycles cohort.
BULL_PHASE_TARGETS = {
    "follicular_mean_days": 16.9,
    "luteal_mean_days": 12.4,
    "cycle_mean_days": 29.3,
    "mean_bleeding_days": 4.7,
}


# Stricker et al. 2006 measured serum estradiol and progesterone reference medians across
# seven menstrual sub-phases in 85 healthy women. The simulator interpolates between these
# medians to avoid ad hoc waveform choices.
HORMONE_ANCHORS: List[HormoneAnchor] = [
    HormoneAnchor("early_follicular", 42.9, 0.44),
    HormoneAnchor("mid_follicular", 88.1, 0.56),
    HormoneAnchor("pre_ovulatory", 234.0, 1.31),
    HormoneAnchor("ovulation", 141.0, 1.43),
    HormoneAnchor("early_luteal", 132.0, 3.95),
    HormoneAnchor("mid_luteal", 117.0, 11.02),
    HormoneAnchor("late_luteal", 111.0, 6.75),
]


CONDITION_NOTES: Dict[str, str] = {
    "pcos": (
        "Longer, more irregular cycles and delayed stabilization across the reproductive lifespan "
        "are constrained by Mortimer et al. 2025; attenuated luteal progesterone is constrained "
        "by Doi et al. 2005."
    ),
    "oral_contraceptives": (
        "Combined oral contraceptives are modeled as near-complete ovulation suppression with "
        "withdrawal or breakthrough bleeding schedules informed by Edelman et al. 2014."
    ),
    "hormonal_iud": (
        "The levonorgestrel IUD preserves ovulation in most long-term users while decreasing "
        "bleeding days and increasing amenorrhea, using Xiao et al. and later LNG-IUS bleeding studies."
    ),
    "copper_iud": (
        "Copper IUDs preserve ovarian hormone patterns but lengthen menstrual bleeding and increase "
        "bleeding volume based on non-hormonal IUD literature summarized by Hubacher et al."
    ),
    "perimenopause": (
        "Perimenopause increases cycle variability and anovulation while keeping estradiol variable "
        "rather than uniformly low, following Santoro et al."
    ),
    "peri_menarche": (
        "Early post-menarche cycles are more variable and more often anovulatory, following "
        "Venturoli et al. and related adolescent endocrine series."
    ),
    "dysmenorrhea": (
        "Primary dysmenorrhea is treated primarily as a bleeding-duration phenotype because the "
        "core pathology is prostaglandin-mediated pain in largely ovulatory cycles, per Dawood 2006."
    ),
}


def age_band_for(age_years: float) -> AgeBandTarget:
    """Return the published age-band target corresponding to a patient age.

    Args:
        age_years: Chronologic age in years.

    Returns:
        The :class:`AgeBandTarget` whose interval contains ``age_years``.
    """

    for target in AGE_BAND_TARGETS:
        if target.age_min <= age_years < target.age_max:
            return target
    return AGE_BAND_TARGETS[-1]
