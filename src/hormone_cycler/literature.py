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
    title: str
    full_reference: str
    url: str
    pmid: str = ""
    doi: str = ""
    evidence_role: str = ""


@dataclass(frozen=True)
class AgeBandTarget:
    """Published healthy-cycle targets and fitted latent calibration terms.

    ``mean_cycle_days`` is the only derived target: Li et al. report adjusted
    differences from ages 35--39 rather than absolute age-band means.  The
    differences are anchored so their AWHS cycle-count-weighted mean is the
    published overall mean of 28.7 days.  All other outcome targets are copied
    directly from Li et al. Tables 4--5 and Supplementary Table 2.  The final
    three fields are simulator parameters fitted to those outcomes, not
    independently observed biological quantities.
    """

    label: str
    age_min: float
    age_max: float
    mean_cycle_days: float
    within_person_sd_days: float
    within_person_sd_ci: Tuple[float, float]
    irregular_participant_probability: float
    short_cycle_probability: float
    long_cycle_probability: float
    high_variability_component_probability: float
    low_component_sigma_days: float
    high_component_sigma_days: float
    long_cycle_episode_probability: float = 0.0
    long_cycle_episode_extension_days: float = 0.0


@dataclass(frozen=True)
class ExternalAgeBandTarget:
    """Held-out age-band summaries used for external validation."""

    label: str
    age_min: float
    age_max: float
    mean_cycle_days: float
    mean_personal_sd_days: float


@dataclass(frozen=True)
class HormoneAnchor:
    name: str
    estradiol_pg_ml: float
    progesterone_ng_ml: float


@dataclass(frozen=True)
class DailyHormoneReference:
    """One Stricker daily median indexed to the serum LH-peak day."""

    lh_offset_days: int
    estradiol_pmol_l: float
    progesterone_nmol_l: float

    @property
    def estradiol_pg_ml(self) -> float:
        """Return estradiol in the simulator's reporting unit."""

        return self.estradiol_pmol_l / ESTRADIOL_PMOL_L_PER_PG_ML

    @property
    def progesterone_ng_ml(self) -> float:
        """Return progesterone in the simulator's reporting unit."""

        return self.progesterone_nmol_l / PROGESTERONE_NMOL_L_PER_NG_ML


@dataclass(frozen=True)
class HormoneSubphaseTarget:
    """Independent serum-hormone median for a standardized cycle subphase."""

    name: str
    estradiol_pmol_l: float
    progesterone_nmol_l: float

    @property
    def estradiol_pg_ml(self) -> float:
        """Return estradiol in the simulator's reporting unit."""

        return self.estradiol_pmol_l / ESTRADIOL_PMOL_L_PER_PG_ML

    @property
    def progesterone_ng_ml(self) -> float:
        """Return progesterone in the simulator's reporting unit."""

        return self.progesterone_nmol_l / PROGESTERONE_NMOL_L_PER_NG_ML


ESTRADIOL_PMOL_L_PER_PG_ML = 3.671
PROGESTERONE_NMOL_L_PER_NG_ML = 3.18


CITATIONS: Dict[str, Citation] = {
    "li_2023_awhs": Citation(
        key="li_2023_awhs",
        short_name="Li et al. 2023",
        title="Menstrual cycle length variation by demographic characteristics from the Apple Women's Health Study",
        full_reference=(
            "Li H, Gibson EA, Jukic AMZ, et al. Menstrual cycle length variation by "
            "demographic characteristics from the Apple Women's Health Study. "
            "NPJ Digital Medicine. 2023;6(1):100. doi:10.1038/s41746-023-00848-1."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/37248288/",
        pmid="37248288",
        doi="10.1038/s41746-023-00848-1",
        evidence_role="Primary healthy-cycle calibration target",
    ),
    "bull_2019_natural_cycles": Citation(
        key="bull_2019_natural_cycles",
        short_name="Bull et al. 2019",
        title="Real-world menstrual cycle characteristics of more than 600,000 menstrual cycles",
        full_reference=(
            "Bull JR, Rowland SP, Scherwitzl EB, et al. Real-world menstrual cycle "
            "characteristics of more than 600,000 menstrual cycles. NPJ Digital Medicine. "
            "2019;2:83. doi:10.1038/s41746-019-0152-7."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/31482137/",
        pmid="31482137",
        doi="10.1038/s41746-019-0152-7",
        evidence_role="Phase-timing and bleeding calibration target",
    ),
    "cunningham_2024_flo": Citation(
        key="cunningham_2024_flo",
        short_name="Cunningham et al. 2024",
        title="Chronicling menstrual cycle patterns across the reproductive lifespan with real-world data",
        full_reference=(
            "Cunningham AC, Pal L, Wickham AP, et al. Chronicling menstrual cycle "
            "patterns across the reproductive lifespan with real-world data. "
            "Scientific Reports. 2024;14(1):10172. doi:10.1038/s41598-024-60373-3."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/38702411/",
        pmid="38702411",
        doi="10.1038/s41598-024-60373-3",
        evidence_role="Held-out external healthy-cycle cross-check",
    ),
    "stricker_2006_reference": Citation(
        key="stricker_2006_reference",
        short_name="Stricker et al. 2006",
        title=(
            "Establishment of detailed reference values for luteinizing hormone, follicle "
            "stimulating hormone, estradiol, and progesterone during different phases of the "
            "menstrual cycle on the Abbott ARCHITECT analyzer"
        ),
        full_reference=(
            "Stricker R, Eberhart R, Chevailler MC, et al. Establishment of detailed "
            "reference values for luteinizing hormone, follicle stimulating hormone, "
            "estradiol, and progesterone during different phases of the menstrual cycle "
            "on the Abbott ARCHITECT analyzer. "
            "Clinical Chemistry and Laboratory Medicine. 2006;44(7):883-887. "
            "doi:10.1515/CCLM.2006.160."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/16776638/",
        pmid="16776638",
        doi="10.1515/CCLM.2006.160",
        evidence_role="Daily hormone-shape construction source and construction-fidelity target",
    ),
    "roos_2015_true_ovulation": Citation(
        key="roos_2015_true_ovulation",
        short_name="Roos et al. 2015",
        title=(
            "Monitoring the menstrual cycle: Comparison of urinary and serum reproductive "
            "hormones referenced to true ovulation"
        ),
        full_reference=(
            "Roos J, Johnson S, Weddell S, et al. Monitoring the menstrual cycle: "
            "Comparison of urinary and serum reproductive hormones referenced to true "
            "ovulation. European Journal of Contraception & Reproductive Health Care. "
            "2015;20(6):438-450. doi:10.3109/13625187.2015.1048331."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/26018113/",
        pmid="26018113",
        doi="10.3109/13625187.2015.1048331",
        evidence_role="Ultrasound-aligned waveform timing and heterogeneity context",
    ),
    "harlow_2000_long_follicular": Citation(
        key="harlow_2000_long_follicular",
        short_name="Harlow et al. 2000",
        title="Urinary oestrogen patterns in long follicular phases",
        full_reference=(
            "Harlow SD, Baird DD, Weinberg CR, Wilcox AJ. Urinary oestrogen "
            "patterns in long follicular phases. Human Reproduction. "
            "2000;15(1):11-16. doi:10.1093/humrep/15.1.11."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/10611180/",
        pmid="10611180",
        doi="10.1093/humrep/15.1.11",
        evidence_role="Long-follicular-phase estradiol morphology source",
    ),
    "mumford_2012_cycle_hormones": Citation(
        key="mumford_2012_cycle_hormones",
        short_name="Mumford et al. 2012",
        title="The utility of menstrual cycle length as an indicator of cumulative hormonal exposure",
        full_reference=(
            "Mumford SL, Steiner AZ, Pollack AZ, et al. The utility of menstrual "
            "cycle length as an indicator of cumulative hormonal exposure. Journal "
            "of Clinical Endocrinology & Metabolism. 2012;97(10):E1871-E1879. "
            "doi:10.1210/jc.2012-1350."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/22837188/",
        pmid="22837188",
        doi="10.1210/jc.2012-1350",
        evidence_role="Independent long-cycle hormone-timing context",
    ),
    "van_voorhis_2008_perimenopause": Citation(
        key="van_voorhis_2008_perimenopause",
        short_name="Van Voorhis et al. 2008",
        title=(
            "The relationship of bleeding patterns to daily reproductive hormones in women "
            "approaching menopause"
        ),
        full_reference=(
            "Van Voorhis BJ, Santoro N, Harlow S, Crawford SL, Randolph J. The relationship "
            "of bleeding patterns to daily reproductive hormones in women approaching "
            "menopause. Obstetrics & Gynecology. 2008;112(1):101-108. "
            "doi:10.1097/AOG.0b013e31817d452b."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/18591314/",
        pmid="18591314",
        doi="10.1097/AOG.0b013e31817d452b",
        evidence_role="Menopause-transition long-cycle/anovulation joint-dependence target",
    ),
    "oconnor_2009_perimenopause": Citation(
        key="oconnor_2009_perimenopause",
        short_name="O'Connor et al. 2009",
        title="Progesterone and ovulation across stages of the transition to menopause",
        full_reference=(
            "O'Connor KA, Ferrell R, Brindle E, et al. Progesterone and ovulation across "
            "stages of the transition to menopause. Menopause. 2009;16(6):1178-1187. "
            "doi:10.1097/gme.0b013e3181aa192d."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/19568209/",
        pmid="19568209",
        doi="10.1097/gme.0b013e3181aa192d",
        evidence_role="Long ovulatory-cycle and reproductive-stage interpretation context",
    ),
    "filicori_1984_progesterone_pulsatility": Citation(
        key="filicori_1984_progesterone_pulsatility",
        short_name="Filicori et al. 1984",
        title=(
            "Neuroendocrine regulation of the corpus luteum in the human. Evidence for "
            "pulsatile progesterone secretion"
        ),
        full_reference=(
            "Filicori M, Butler JP, Crowley WF Jr. Neuroendocrine regulation of the corpus "
            "luteum in the human. Evidence for pulsatile progesterone secretion. Journal of "
            "Clinical Investigation. 1984;73(6):1638-1647. doi:10.1172/JCI111370."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/6427277/",
        pmid="6427277",
        doi="10.1172/JCI111370",
        evidence_role="Intraday serum-progesterone pulsatility limitation context",
    ),
    "anckaert_2021_hormones": Citation(
        key="anckaert_2021_hormones",
        short_name="Anckaert et al. 2021",
        title=(
            "Extensive monitoring of the natural menstrual cycle using the serum "
            "biomarkers estradiol, luteinizing hormone and progesterone"
        ),
        full_reference=(
            "Anckaert E, Jank A, Petzold J, et al. Extensive monitoring of the "
            "natural menstrual cycle using the serum biomarkers estradiol, "
            "luteinizing hormone and progesterone. Practical Laboratory Medicine. "
            "2021;25:e00211. doi:10.1016/j.plabm.2021.e00211."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/33869706/",
        pmid="33869706",
        doi="10.1016/j.plabm.2021.e00211",
        evidence_role="Independent serum-hormone subphase validation target",
    ),
    "fraser_2011_bleeding": Citation(
        key="fraser_2011_bleeding",
        short_name="Fraser et al. 2011",
        title="The FIGO recommendations on terminologies and definitions for normal and abnormal uterine bleeding",
        full_reference=(
            "Fraser IS, Critchley HOD, Broder M, Munro MG. The FIGO recommendations on "
            "terminologies and definitions for normal and abnormal uterine bleeding. "
            "Seminars in Reproductive Medicine. 2011;29(5):383-390. "
            "doi:10.1055/s-0031-1287662."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/22065325/",
        pmid="22065325",
        doi="10.1055/s-0031-1287662",
        evidence_role="Normal/abnormal uterine-bleeding terminology and range context",
    ),
    "mortimer_2026_pcos": Citation(
        key="mortimer_2026_pcos",
        short_name="Mortimer et al. 2026",
        title=(
            "Variability of menstrual cycles by age, polycystic ovary syndrome, and early-life "
            "cycle irregularity in the Apple Women's Health Study"
        ),
        full_reference=(
            "Mortimer R, Asokan G, Baird DD, et al. Variability of menstrual cycles by age, "
            "polycystic ovary syndrome, and early-life cycle irregularity in the Apple "
            "Women's Health Study. American Journal of Obstetrics and Gynecology. "
            "2026;234(4):1042-1069. doi:10.1016/j.ajog.2025.11.031."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/41297783/",
        pmid="41297783",
        doi="10.1016/j.ajog.2025.11.031",
        evidence_role="Direction-only PCOS cycle-length and variability check",
    ),
    "doi_2005_pcos_hormones": Citation(
        key="doi_2005_pcos_hormones",
        short_name="Doi et al. 2005",
        title="Irregular cycles and steroid hormones in polycystic ovary syndrome",
        full_reference=(
            "Doi SAR, Al-Zaid M, Towers PA, Scott CJ, Al-Shoumer KAS. Irregular cycles and "
            "steroid hormones in polycystic ovary syndrome. Human Reproduction. "
            "2005;20(9):2402-2408. doi:10.1093/humrep/dei093."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/15932911/",
        pmid="15932911",
        doi="10.1093/humrep/dei093",
        evidence_role="Direction-only PCOS ovulatory-status and steroid-pattern check",
    ),
    "jarrett_2020_pcos": Citation(
        key="jarrett_2020_pcos",
        short_name="Jarrett et al. 2020",
        title="Ultrasound characterization of disordered antral follicle development in women with polycystic ovary syndrome",
        full_reference=(
            "Jarrett BY, Vanden Brink H, Oldfield AL, Lujan ME. Ultrasound characterization "
            "of disordered antral follicle development in women with polycystic ovary "
            "syndrome. Journal of Clinical Endocrinology & Metabolism. "
            "2020;105(11):e3847-e3861. doi:10.1210/clinem/dgaa515."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/32785651/",
        pmid="32785651",
        doi="10.1210/clinem/dgaa515",
        evidence_role="Direction-only PCOS follicular and hormone-pattern context",
    ),
    "who_1986_adolescent_cycles": Citation(
        key="who_1986_adolescent_cycles",
        short_name="WHO Task Force 1986",
        title=(
            "World Health Organization multicenter study on menstrual and ovulatory patterns "
            "in adolescent girls. II. Longitudinal study of menstrual patterns in the early "
            "postmenarcheal period, duration of bleeding episodes and menstrual cycles. World "
            "Health Organization Task Force on Adolescent Reproductive Health"
        ),
        full_reference=(
            "World Health Organization Task Force on Adolescent Reproductive Health. "
            "World Health Organization multicenter study on menstrual and ovulatory "
            "patterns in adolescent girls. II. Longitudinal study of menstrual patterns "
            "in the early postmenarcheal period, duration of bleeding episodes and "
            "menstrual cycles. Journal of Adolescent Health Care. 1986;7(4):236-244."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/3721946/",
        pmid="3721946",
        evidence_role="Direction-only peri-menarche cycle-length and regularity check",
    ),
    "venturoli_1986_menarche": Citation(
        key="venturoli_1986_menarche",
        short_name="Venturoli et al. 1986",
        title="Menstrual irregularities in adolescents: hormonal pattern and ovarian morphology",
        full_reference=(
            "Venturoli S, Porcu E, Fabbri R, et al. Menstrual irregularities in adolescents: "
            "hormonal pattern and ovarian morphology. Hormone Research. "
            "1986;24(4):269-279. doi:10.1159/000180567."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/3491030/",
        pmid="3491030",
        doi="10.1159/000180567",
        evidence_role="Direction-only peri-menarche ovulation and hormone-pattern check",
    ),
    "zhang_2008_menarche": Citation(
        key="zhang_2008_menarche",
        short_name="Zhang et al. 2008",
        title="Onset of ovulation after menarche in girls: a longitudinal study",
        full_reference=(
            "Zhang K, Pollack S, Ghods A, et al. Onset of ovulation after menarche in "
            "girls: a longitudinal study. Journal of Clinical Endocrinology & Metabolism. "
            "2008;93(4):1186-1194. doi:10.1210/jc.2007-1846."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/18252789/",
        pmid="18252789",
        doi="10.1210/jc.2007-1846",
        evidence_role="Peri-menarche hormone-pattern context and limitation",
    ),
    "santoro_2011_perimenopause": Citation(
        key="santoro_2011_perimenopause",
        short_name="Santoro and Randolph 2011",
        title="Reproductive hormones and the menopause transition",
        full_reference=(
            "Santoro N, Randolph JF Jr. Reproductive hormones and the menopause transition. "
            "Obstetrics and Gynecology Clinics of North America. 2011;38(3):455-466. "
            "doi:10.1016/j.ogc.2011.05.004."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/21961713/",
        pmid="21961713",
        doi="10.1016/j.ogc.2011.05.004",
        evidence_role="Direction-only perimenopause cycle and hormone-pattern check",
    ),
    "edelman_2014_ocp": Citation(
        key="edelman_2014_ocp",
        short_name="Edelman et al. 2014",
        title="Continuous or extended cycle vs. cyclic use of combined hormonal contraceptives for contraception",
        full_reference=(
            "Edelman AB, Gallo MF, Jensen JT, et al. Continuous or extended cycle vs. cyclic "
            "use of combined hormonal contraceptives for contraception. Cochrane Database "
            "of Systematic Reviews. 2014;(7):CD004695. "
            "doi:10.1002/14651858.CD004695.pub3."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/25072731/",
        pmid="25072731",
        doi="10.1002/14651858.CD004695.pub3",
        evidence_role="Direction/range check for combined oral-contraceptive regimens",
    ),
    "xiao_1995_lng_iud": Citation(
        key="xiao_1995_lng_iud",
        short_name="Xiao et al. 1995",
        title="Effect of levonorgestrel-releasing intrauterine device on hormonal profile and menstrual pattern after long-term use",
        full_reference=(
            "Xiao B, Zeng T, Wu S, Sun H, Xiao N. Effect of levonorgestrel-releasing "
            "intrauterine device on hormonal profile and menstrual pattern after long-term "
            "use. Contraception. 1995;51(6):359-365. "
            "doi:10.1016/0010-7824(95)00102-G."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/7554977/",
        pmid="7554977",
        doi="10.1016/0010-7824(95)00102-G",
        evidence_role="Direction/range check for long-term levonorgestrel-IUD ovarian function",
    ),
    "faundes_1980_copper_iud": Citation(
        key="faundes_1980_copper_iud",
        short_name="Faundes et al. 1980",
        title="The menstrual cycle in women using an intrauterine device",
        full_reference=(
            "Faundes A, Segal SJ, Adejuwon CA, et al. The menstrual cycle in women using "
            "an intrauterine device. Fertility and Sterility. 1980;34(5):427-430. "
            "doi:10.1016/S0015-0282(16)45131-9."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/7439408/",
        pmid="7439408",
        doi="10.1016/S0015-0282(16)45131-9",
        evidence_role="Direction-only copper-IUD ovulation and cycle-length check",
    ),
    "malmqvist_1974_copper_bleeding": Citation(
        key="malmqvist_1974_copper_bleeding",
        short_name="Malmqvist et al. 1974",
        title="Menstrual bleeding with copper-covered intrauterine contraceptive devices",
        full_reference=(
            "Malmqvist R, Petersohn L, Bengtsson LP. Menstrual bleeding with copper-covered "
            "intrauterine contraceptive devices. Contraception. 1974;9(6):627-633. "
            "doi:10.1016/0010-7824(74)90048-1."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/4448089/",
        pmid="4448089",
        doi="10.1016/0010-7824(74)90048-1",
        evidence_role="Direction-only copper-IUD bleeding check",
    ),
    "dawood_2006_dysmenorrhea": Citation(
        key="dawood_2006_dysmenorrhea",
        short_name="Dawood 2006",
        title="Primary dysmenorrhea: advances in pathogenesis and management",
        full_reference=(
            "Dawood MY. Primary dysmenorrhea: advances in pathogenesis and management. "
            "Obstetrics and Gynecology. 2006;108(2):428-441. "
            "doi:10.1097/01.AOG.0000230214.26638.0c."
        ),
        url="https://pubmed.ncbi.nlm.nih.gov/16880317/",
        pmid="16880317",
        doi="10.1097/01.AOG.0000230214.26638.0c",
        evidence_role="Direction-only primary-dysmenorrhea phenotype check",
    ),
}


# Li et al. 2023 reported an overall mean of 28.7 days and adjusted age-band differences
# from ages 35--39.  Anchoring those differences to the overall mean with the published
# age-band cycle counts gives the absolute means below.  Within-person SDs, participant-level
# irregularity percentages (mean absolute adjacent-cycle difference >=7 days), and short/long
# cycle percentages are direct AWHS results. The variability-component parameters were initialized
# with a deterministic Monte Carlo surrogate, refined against the complete simulator, and are
# explicitly treated as latent model terms rather than biological diagnoses.
AGE_BAND_TARGETS: List[AgeBandTarget] = [
    AgeBandTarget("<20", 12.0, 20.0, 29.82, 5.33, (5.16, 5.51), 0.204, 0.0771, 0.0833, 0.26, 4.3916, 7.1350),
    AgeBandTarget("20-24", 20.0, 25.0, 29.62, 5.07, (4.96, 5.18), 0.209, 0.0722, 0.0688, 0.87, 0.9853, 5.4037),
    AgeBandTarget("25-29", 25.0, 30.0, 29.31, 4.70, (4.62, 4.79), 0.159, 0.0607, 0.0616, 0.85, 1.0640, 5.0600),
    AgeBandTarget("30-34", 30.0, 35.0, 28.75, 4.28, (4.21, 4.34), 0.116, 0.0671, 0.0449, 0.76, 1.2606, 4.8362),
    AgeBandTarget("35-39", 35.0, 40.0, 28.19, 3.79, (3.77, 3.82), 0.106, 0.0812, 0.0293, 0.50, 0.8629, 5.2603),
    AgeBandTarget("40-44", 40.0, 45.0, 27.70, 3.99, (3.94, 4.04), 0.128, 0.1189, 0.0248, 0.48, 0.6673, 5.6621),
    AgeBandTarget("45-49", 45.0, 50.0, 27.86, 5.42, (5.27, 5.57), 0.282, 0.1595, 0.0421, 0.64, 0.2500, 6.6529),
    AgeBandTarget("50+", 50.0, 56.0, 30.21, 11.19, (8.94, 13.45), 0.602, 0.1866, 0.1481, 0.4072, 1.5563, 12.7992, 0.1090, 25.4912),
]


# Cunningham et al. 2024 are held out from calibration.  Their 12-month Flo cohort used a
# different population and a different aggregation estimator, so these values are cross-checks
# with prespecified practical equivalence margins rather than additional fitted constraints.
CUNNINGHAM_AGE_TARGETS: List[ExternalAgeBandTarget] = [
    ExternalAgeBandTarget("18-25", 18.0, 26.0, 28.99, 4.14),
    ExternalAgeBandTarget("26-30", 26.0, 31.0, 28.76, 3.95),
    ExternalAgeBandTarget("31-35", 31.0, 36.0, 28.28, 3.80),
    ExternalAgeBandTarget("36-40", 36.0, 41.0, 27.68, 3.72),
    ExternalAgeBandTarget("41-45", 41.0, 46.0, 27.18, 3.92),
    ExternalAgeBandTarget("46-50", 46.0, 51.0, 27.15, 4.72),
    ExternalAgeBandTarget("51-55", 51.0, 56.0, 28.00, 6.52),
]


# Bull et al. 2019 reported mean follicular and luteal phase lengths across more than
# 600,000 ovulatory cycles from the Natural Cycles cohort.
BULL_PHASE_TARGETS = {
    "follicular_mean_days": 16.9,
    "luteal_mean_days": 12.4,
    "cycle_mean_days": 29.3,
    "mean_bleeding_days": 4.0,
    "bleeding_sd_days": 1.5,
    "luteal_sd_days": 2.4,
}


# Stricker et al. 2006 measured daily serum estradiol and progesterone in 20 healthy volunteers.
# These legacy representative anchors retain the established ordinary-cycle follicular geometry;
# the luteal envelope below is now built from the complete daily median series rather than from
# only seven points.
HORMONE_ANCHORS: List[HormoneAnchor] = [
    HormoneAnchor("early_follicular", 42.9, 0.44),
    HormoneAnchor("mid_follicular", 88.1, 0.56),
    HormoneAnchor("pre_ovulatory", 234.0, 1.31),
    HormoneAnchor("ovulation", 141.0, 1.43),
    HormoneAnchor("early_luteal", 132.0, 3.95),
    HormoneAnchor("mid_luteal", 117.0, 11.02),
    HormoneAnchor("late_luteal", 111.0, 6.75),
]


# Table 1B daily serum medians from Stricker et al., indexed to the LH-peak day. Values are stored
# in the publication's SI units and converted through the properties above only at the model
# boundary. This preserves source precision and makes the event alignment auditable.
STRICKER_DAILY_SERUM_REFERENCE: Tuple[DailyHormoneReference, ...] = (
    DailyHormoneReference(-15, 139.46, 1.27),
    DailyHormoneReference(-14, 149.00, 1.27),
    DailyHormoneReference(-13, 137.63, 0.95),
    DailyHormoneReference(-12, 128.45, 0.64),
    DailyHormoneReference(-11, 130.29, 0.64),
    DailyHormoneReference(-10, 145.15, 0.64),
    DailyHormoneReference(-9, 154.14, 0.64),
    DailyHormoneReference(-8, 162.76, 0.48),
    DailyHormoneReference(-7, 196.16, 0.64),
    DailyHormoneReference(-6, 215.06, 0.32),
    DailyHormoneReference(-5, 262.22, 0.48),
    DailyHormoneReference(-4, 363.15, 0.64),
    DailyHormoneReference(-3, 485.72, 0.32),
    DailyHormoneReference(-2, 651.06, 0.64),
    DailyHormoneReference(-1, 939.34, 0.95),
    DailyHormoneReference(0, 671.06, 2.54),
    DailyHormoneReference(1, 312.87, 4.93),
    DailyHormoneReference(2, 260.57, 12.72),
    DailyHormoneReference(3, 322.96, 20.51),
    DailyHormoneReference(4, 403.52, 30.85),
    DailyHormoneReference(5, 450.68, 34.03),
    DailyHormoneReference(6, 486.64, 35.30),
    DailyHormoneReference(7, 551.78, 42.45),
    DailyHormoneReference(8, 491.23, 37.05),
    DailyHormoneReference(9, 503.52, 32.44),
    DailyHormoneReference(10, 495.45, 32.75),
    DailyHormoneReference(11, 340.41, 14.47),
    DailyHormoneReference(12, 314.52, 13.04),
    DailyHormoneReference(13, 170.10, 5.25),
    DailyHormoneReference(14, 151.20, 4.13),
)


# Held-out assay-specific medians from Anckaert et al. (85 apparently healthy participants).
# They are not used to construct the waveform and therefore provide a genuinely independent
# amplitude/order cross-check, with broad assay- and population-aware equivalence margins.
ANCKAERT_HORMONE_SUBPHASE_TARGETS: Tuple[HormoneSubphaseTarget, ...] = (
    HormoneSubphaseTarget("early_follicular", 125.0, 0.380),
    HormoneSubphaseTarget("mid_follicular", 172.0, 0.210),
    HormoneSubphaseTarget("pre_ovulatory", 464.0, 0.188),
    HormoneSubphaseTarget("ovulation", 817.0, 1.59),
    HormoneSubphaseTarget("early_luteal", 390.0, 22.6),
    HormoneSubphaseTarget("mid_luteal", 505.0, 39.2),
    HormoneSubphaseTarget("late_luteal", 396.0, 18.2),
)


CONDITION_NOTES: Dict[str, str] = {
    "pcos": (
        "Longer, more irregular cycles and delayed stabilization across the reproductive lifespan "
        "are constrained directionally by Mortimer et al. 2026; altered progesterone-to-estradiol "
        "balance and follicular development are constrained directionally by Doi et al. 2005 "
        "and Jarrett et al. 2020."
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
        "bleeding based on the studies by Faundes et al. 1980 and Malmqvist et al. 1974."
    ),
    "perimenopause": (
        "Perimenopause increases cycle variability and anovulation while keeping estradiol variable "
        "rather than uniformly low, following Santoro et al."
    ),
    "peri_menarche": (
        "Early post-menarche cycles are more variable and more often anovulatory, following "
        "the WHO Task Force 1986 and Venturoli et al. 1986; Zhang et al. 2008 is retained as "
        "a counterpoint showing rapid maturation in a small normal-weight cohort."
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
