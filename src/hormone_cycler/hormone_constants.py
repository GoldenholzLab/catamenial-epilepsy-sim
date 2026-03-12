"""Central numerical constants for the hormone_cycler simulator.

Every scientific constant that was previously hard-coded inside functions is defined here so
the model assumptions are auditable in one place.
"""

from __future__ import annotations


# Li et al. 2024 define cycle irregularity using adjacent-cycle differences of at least 7 days.
# The simulator uses the same threshold when inverting age-band irregularity prevalence into a
# within-person cycle-length SD for each simulated patient.
IRREGULARITY_THRESHOLD_DAYS = 7.0


# The age-specific ovulation probabilities below are calibration constants constrained by:
# 1. Venturoli et al. 1987, which supports more frequent anovulation early after menarche.
# 2. Santoro and Randolph 2011, which supports more frequent anovulation near menopause.
# 3. Li et al. 2024, whose age-specific mean cycle-length and irregularity targets are matched
#    in validation, so these probabilities cannot be chosen independently of those targets.
BASELINE_AGE_OVULATION_PROBABILITIES = (
    (0.0, 15.0, 0.62),
    (15.0, 20.0, 0.90),
    (20.0, 40.0, 0.97),
    (40.0, 45.0, 0.95),
    (45.0, 50.0, 0.88),
    (50.0, 200.0, 0.70),
)


# Explicit peri-menarche and perimenopause flags should shift the patient to clinically distinct
# states. The values below keep those flagged cohorts inside the broad endocrine patterns reported
# by Venturoli et al. 1987 and Santoro and Randolph 2011, while still allowing validation against
# the higher-level cycle statistics.
PERI_MENARCHE_OVULATION_PROBABILITY_LT16 = 0.52
PERI_MENARCHE_OVULATION_PROBABILITY_GTE16 = 0.65
PERIMENOPAUSE_OVULATION_PROBABILITY_LT52 = 0.68
PERIMENOPAUSE_OVULATION_PROBABILITY_GTE52 = 0.48


# Between-person cycle-length dispersion is a calibration parameter fit to large-scale population
# cycle statistics from Li et al. 2024. Younger and older groups are wider because population
# variability is larger at the edges of reproductive life.
BETWEEN_PERSON_SIGMA_BY_AGE = (
    (0.0, 20.0, 2.4),
    (20.0, 30.0, 2.1),
    (30.0, 45.0, 1.9),
    (45.0, 200.0, 2.5),
)


# These factors shape patient-level hormone amplitude heterogeneity. They are calibration terms
# used to keep simulated estradiol and progesterone medians near Stricker et al. 2006 while
# preserving realistic between-person spread.
BASELINE_ESTRADIOL_SCALE_CV = 0.18
BASELINE_PROGESTERONE_SCALE_CV = 0.22
BASELINE_NOISE_SCALE = 0.06
PERSONAL_SIGMA_SCALE_FROM_IRREGULARITY = 0.92
PERSONAL_SIGMA_CV_FROM_IRREGULARITY = 0.14
BASELINE_BLEED_SIGMA_DAYS = 1.0


# Bull et al. 2019 support a cycle length floor in the high teens, and clinically implausible
# cycle lengths above roughly four months are excluded. These bounds prevent the truncated normal
# samplers from producing non-physiologic cycles.
MIN_CYCLE_LENGTH_DAYS = 18.0
MAX_CYCLE_LENGTH_DAYS = 120.0


# PCOS modifiers are constrained by Mortimer et al. 2025 for longer and more irregular cycles and
# by Doi et al. 2005 for blunted progesterone patterns. The age-stratified multipliers preserve the
# Mortimer finding that the gap narrows with age rather than remaining constant.
PCOS_CYCLE_MEAN_MULTIPLIER_BY_AGE = (
    (0.0, 25.0, 1.30),
    (25.0, 35.0, 1.22),
    (35.0, 200.0, 1.15),
)
PCOS_CYCLE_SIGMA_MULTIPLIER = 1.55
PCOS_OVULATION_MULTIPLIER = 0.48
PCOS_BLEED_MEAN_DELTA_DAYS = 0.4
PCOS_ESTRADIOL_SCALE_MULTIPLIER = 1.08
PCOS_PROGESTERONE_SCALE_MULTIPLIER = 0.58
PCOS_NOISE_SCALE_MULTIPLIER = 1.15


# Venturoli et al. 1987 support longer, more variable, and more often anovulatory cycles soon
# after menarche. These constants widen cycle dispersion and reduce luteal progesterone accordingly.
PERI_MENARCHE_CYCLE_MEAN_DELTA_DAYS = 2.5
PERI_MENARCHE_CYCLE_SIGMA_MULTIPLIER = 1.25
PERI_MENARCHE_MAX_OVULATION_PROBABILITY = 0.55
PERI_MENARCHE_BLEED_MEAN_DELTA_DAYS = 0.5
PERI_MENARCHE_ESTRADIOL_SCALE_MULTIPLIER = 0.92
PERI_MENARCHE_PROGESTERONE_SCALE_MULTIPLIER = 0.72
PERI_MENARCHE_NOISE_SCALE_MULTIPLIER = 1.15


# Santoro and Randolph 2011 describe greater cycle variability and more anovulation during the
# menopause transition, with progesterone attenuation and high estradiol variability.
PERIMENOPAUSE_CYCLE_SIGMA_MULTIPLIER = 1.35
PERIMENOPAUSE_OVULATION_MULTIPLIER = 0.78
PERIMENOPAUSE_BLEED_MEAN_DELTA_DAYS = 0.6
PERIMENOPAUSE_PROGESTERONE_SCALE_MULTIPLIER = 0.82
PERIMENOPAUSE_NOISE_SCALE_MULTIPLIER = 1.25


# Copper IUDs preserve ovarian cycling but increase menstrual bleeding, while levonorgestrel IUDs
# preserve ovulation in most cycles yet reduce bleeding and increase amenorrhea.
COPPER_IUD_BLEED_MEAN_DELTA_DAYS = 1.2
COPPER_IUD_BLEED_SIGMA_DELTA_DAYS = 0.25
HORMONAL_IUD_MAX_OVULATION_PROBABILITY = 0.82
HORMONAL_IUD_BLEED_MEAN_DELTA_DAYS = -2.2
HORMONAL_IUD_MIN_BLEED_MEAN_DAYS = 0.8
HORMONAL_IUD_BLEED_SIGMA_DELTA_DAYS = -0.2
HORMONAL_IUD_MIN_BLEED_SIGMA_DAYS = 0.5
HORMONAL_IUD_ESTRADIOL_SCALE_MULTIPLIER = 0.95
HORMONAL_IUD_PROGESTERONE_SCALE_MULTIPLIER = 0.92
HORMONAL_IUD_AMENORRHEA_PROBABILITY = 0.17


# Dawood 2006 supports dysmenorrhea as largely a pain phenotype in ovulatory cycles rather than a
# large estradiol/progesterone shift. The simulator therefore changes bleeding duration only mildly.
DYSMENORRHEA_BLEED_MEAN_DELTA_DAYS = 0.5
DYSMENORRHEA_BLEED_SIGMA_DELTA_DAYS = 0.15


# Edelman et al. 2014 support near-complete ovulation suppression under cyclic or continuous
# combined OCP use. The hormone values are endogenous-equivalent suppression targets rather than
# direct synthetic ethinyl-estradiol/progestin assay values.
OCP_REFERENCE_CYCLE_LENGTH_DAYS = 28.0
CYCLIC_OCP_CYCLE_SIGMA_DAYS = 0.25
CONTINUOUS_OCP_CYCLE_SIGMA_DAYS = 0.20
CYCLIC_OCP_BLEED_MEAN_DAYS = 4.0
CYCLIC_OCP_BLEED_SIGMA_DAYS = 0.6
CONTINUOUS_OCP_BLEED_MEAN_DAYS = 1.5
CONTINUOUS_OCP_BLEED_SIGMA_DAYS = 0.7
CYCLIC_OCP_ESTRADIOL_SCALE = 0.60
CYCLIC_OCP_PROGESTERONE_SCALE = 0.22
CONTINUOUS_OCP_ESTRADIOL_SCALE = 0.58
CONTINUOUS_OCP_PROGESTERONE_SCALE = 0.18
OCP_NOISE_SCALE = 0.03
CONTINUOUS_OCP_AMENORRHEA_PROBABILITY = 0.55
CONTINUOUS_OCP_BREAKTHROUGH_BLEED_MEAN_DAYS = 2.0
CONTINUOUS_OCP_BREAKTHROUGH_BLEED_SIGMA_DAYS = 0.8
CONTINUOUS_OCP_BREAKTHROUGH_BLEED_RANGE = (1.0, 5.0)
CYCLIC_OCP_BLEED_RANGE = (2.0, 7.0)


# Anovulatory cycles are usually longer because the luteal phase is absent and follicular timing
# becomes less constrained. The shifts below are calibration parameters used to match age-band
# irregularity without overshooting mean cycle length.
ANOVULATORY_MEAN_SHIFT_REPRODUCTIVE_DAYS = 1.5
ANOVULATORY_MEAN_SHIFT_PERI_MENARCHE_DAYS = 2.5
ANOVULATORY_MEAN_SHIFT_PERIMENOPAUSE_LONG_DAYS = 2.5
ANOVULATORY_MEAN_SHIFT_PERIMENOPAUSE_SHORT_DAYS = -1.25
ANOVULATORY_PERIMENOPAUSE_LONG_CYCLE_PROBABILITY = 0.65
ANOVULATORY_SIGMA_MULTIPLIER = 1.15


# Bull et al. 2019 showed a relatively stable luteal phase compared with the follicular phase.
# These constants encode that structure while allowing clinical modifiers to shorten the luteal
# phase modestly in peri-menarche, perimenopause, and PCOS.
LUTEAL_SIGMA_DAYS = 1.7
PERI_MENARCHE_LUTEAL_MEAN_DELTA_DAYS = -0.7
PERI_MENARCHE_LUTEAL_SIGMA_DELTA_DAYS = 0.2
PERIMENOPAUSE_LUTEAL_MEAN_DELTA_DAYS = -0.6
PERIMENOPAUSE_LUTEAL_SIGMA_DELTA_DAYS = 0.2
PCOS_LUTEAL_MEAN_DELTA_DAYS = -0.8
PCOS_LUTEAL_SIGMA_DELTA_DAYS = 0.2
MIN_LUTEAL_LENGTH_DAYS = 9.0
LUTEAL_ROOM_BUFFER_DAYS = 8
MIN_FOLLICULAR_LENGTH_DAYS = 7


# Bull et al. 2019 and Fraser et al. 2011 support average bleeding near 4.7 days in natural
# cycles. The additions below create the clinically expected increases in adolescent and
# perimenopausal anovulatory cycles.
ANOVULATORY_STAGE_BLEED_MEAN_DELTA_DAYS = 0.8
ANOVULATORY_STAGE_BLEED_SIGMA_DELTA_DAYS = 0.3
MAX_BLEEDING_DAYS = 12.0


# Stricker et al. 2006 provide sub-phase hormone medians. These placement constants control where
# those medians are evaluated inside each synthetic cycle so the simulator interpolates from study
# values instead of drawing arbitrary peaks.
FOLLICULAR_MIDPOINT_FRACTION = 0.45
PRE_OVULATION_DAY_OFFSET = 1.0
EARLY_LUTEAL_FRACTION = 0.22
EARLY_LUTEAL_MIN_OFFSET_DAYS = 1.5
MID_LUTEAL_FRACTION = 0.55
MID_LUTEAL_MIN_OFFSET_DAYS = 3.0
LATE_LUTEAL_DAY_OFFSET = 2.0


# When ovulation does not occur, progesterone remains low and estradiol shows only a blunted rise.
# The anchor values below are calibration targets chosen to keep anovulatory cycles physiologic and
# consistent with the qualitative endocrine patterns described in adolescent and anovulatory-cycle
# literature referenced by Venturoli et al. 1987 and Santoro and Randolph 2011.
ANOVULATORY_MIDPOINT_FRACTION = 0.55
ANOVULATORY_LATE_DAY_OFFSET = 3.0
ANOVULATORY_ESTRADIOL_ANCHORS_PG_ML = (38.0, 86.0, 74.0, 44.0)
ANOVULATORY_PROGESTERONE_ANCHORS_NG_ML = (0.35, 0.55, 0.75, 0.40)


# The cyclic OCP points approximate suppressed endogenous ovarian hormones during active pills and
# placebo-week withdrawal. Continuous OCP points keep hormones flat and low.
CYCLIC_OCP_ESTRADIOL_POINTS = ((1.0, 32.0), (21.0, 28.0), (24.0, 25.0), (28.0, 34.0))
CYCLIC_OCP_PROGESTERONE_POINTS = ((1.0, 0.28), (21.0, 0.24), (24.0, 0.18), (28.0, 0.22))
CONTINUOUS_OCP_ESTRADIOL_POINTS = ((1.0, 30.0), (28.0, 29.0))
CONTINUOUS_OCP_PROGESTERONE_POINTS = ((1.0, 0.22), (28.0, 0.20))


# These cycle-to-cycle amplitude CVs preserve realistic variability while keeping medians close to
# Stricker et al. 2006 during validation.
CYCLE_ESTRADIOL_SCALE_CV = 0.08
CYCLE_PROGESTERONE_SCALE_CV = 0.10


# Spotting rules create clinically expected irregular bleeding in anovulatory peri-menarche and
# perimenopause cycles, and breakthrough bleeding in continuous OCP use.
ANOVULATORY_STAGE_SPOTTING_PROBABILITY = 0.25
ANOVULATORY_STAGE_SPOTTING_START_FRACTION = 0.65
ANOVULATORY_STAGE_SPOTTING_DURATION_DAYS = 2
CONTINUOUS_OCP_BREAKTHROUGH_START_RANGE = (4, 23)
PLACEBO_WEEK_START_DAY = 22
PLACEBO_WEEK_REFERENCE_DAY = 29


# The AR(1) noise coefficient below is a calibration choice that keeps day-to-day hormone values
# smooth rather than white-noise jagged, while preserving modest physiologic fluctuations.
HORMONE_NOISE_AR_COEFFICIENT = 0.65
PROGESTERONE_NOISE_SCALE_MULTIPLIER = 0.9
MIN_ESTRADIOL_PG_ML = 5.0
MIN_PROGESTERONE_NG_ML = 0.05
SERUM_REPORTING_DECIMALS = 2


# Validation phase bins are positioned to align simulated cycle days with the sub-phases reported
# by Stricker et al. 2006 and with follicular/luteal timing from Bull et al. 2019.
VALIDATION_EARLY_FOLLICULAR_FRACTION = 0.20
VALIDATION_MID_FOLLICULAR_FRACTION = 0.60
VALIDATION_EARLY_LUTEAL_FRACTION = 0.30
VALIDATION_MID_LUTEAL_START_FRACTION = 0.35
VALIDATION_MID_LUTEAL_END_FRACTION = 0.70
VALIDATION_MIN_EARLY_FOLLICULAR_DAYS = 2
VALIDATION_MIN_MID_FOLLICULAR_DAYS = 3
VALIDATION_MIN_EARLY_LUTEAL_DAYS = 3
VALIDATION_MIN_MID_LUTEAL_START_DAYS = 4
VALIDATION_MIN_MID_LUTEAL_END_DAYS = 5


# The equivalence margins below are deliberately wider than the source-study confidence intervals.
# Li et al. 2024 had very large samples, so exact CI overlap would be an unrealistically strict
# requirement for a simulator calibrated from published summary statistics rather than raw data.
VALIDATION_CYCLE_MARGIN_MIN_DAYS = 0.50
VALIDATION_CYCLE_MARGIN_BUFFER_DAYS = 0.15
VALIDATION_IRREGULARITY_MARGIN_MIN = 0.04
VALIDATION_IRREGULARITY_MARGIN_BUFFER = 0.015


# Bull et al. 2019 are used directly for aggregate phase-length and bleeding validation windows.
BULL_FOLLICULAR_VALIDATION_BOUNDS = (15.9, 17.9)
BULL_LUTEAL_VALIDATION_BOUNDS = (11.7, 13.1)
BULL_BLEEDING_VALIDATION_BOUNDS = (4.0, 5.4)


# Stricker et al. 2006 provide median hormone targets, but the simulator is population-level and
# stochastic. These multiplicative windows allow realistic spread around the cited medians.
VALIDATION_ESTRADIOL_RATIO_BOUNDS = (0.75, 1.25)
VALIDATION_PROGESTERONE_RATIO_BOUNDS = (0.65, 1.35)
VALIDATION_MIN_PROGESTERONE_BOUND = 0.05


# The subgroup validation cohort sizes are large enough to stabilize stochastic summaries while
# staying practical for routine reruns during development.
SUBGROUP_BASELINE_REFERENCE_PATIENTS = 2000
SUBGROUP_REFERENCE_PATIENTS = 1200


# Each subgroup threshold below is tied to the cited clinical literature or to a conservative
# calibration window chosen so the simulation reflects the direction and approximate magnitude of
# the published effect instead of merely matching sign.
PCOS_VALIDATION_MIN_CYCLE_DELTA_DAYS = 2.0
PCOS_VALIDATION_MIN_IRREGULARITY_DELTA = 0.08
PCOS_VALIDATION_MIN_OVULATION_DELTA = 0.18

CYCLIC_OCP_VALIDATION_MAX_OVULATION_RATE = 0.02
CYCLIC_OCP_VALIDATION_EXPECTED_BLEEDING_DAYS = 4.0
CYCLIC_OCP_VALIDATION_BLEEDING_BOUNDS = (3.0, 5.0)

CONTINUOUS_OCP_VALIDATION_MAX_OVULATION_RATE = 0.02
CONTINUOUS_OCP_VALIDATION_EXPECTED_BLEEDING_DAYS = 1.5
CONTINUOUS_OCP_VALIDATION_MAX_BLEEDING_DAYS = 2.5
CONTINUOUS_OCP_VALIDATION_EXPECTED_AMENORRHEA_RATE = 0.55
CONTINUOUS_OCP_VALIDATION_MIN_AMENORRHEA_RATE = 0.40

HORMONAL_IUD_VALIDATION_EXPECTED_OVULATION_RATE = 0.80
HORMONAL_IUD_VALIDATION_OVULATION_BOUNDS = (0.70, 0.90)
HORMONAL_IUD_VALIDATION_EXPECTED_AMENORRHEA_RATE = 0.17
HORMONAL_IUD_VALIDATION_AMENORRHEA_BOUNDS = (0.10, 0.25)

COPPER_IUD_VALIDATION_MAX_OVULATION_DELTA = 0.05
COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS = (0.5, 2.0)

PERIMENOPAUSE_VALIDATION_EXPECTED_IRREGULARITY = 0.27
PERIMENOPAUSE_VALIDATION_MIN_IRREGULARITY = 0.25
PERIMENOPAUSE_VALIDATION_EXPECTED_OVULATION_RATE = 0.70
PERIMENOPAUSE_VALIDATION_OVULATION_BOUNDS = (0.45, 0.80)

PERI_MENARCHE_VALIDATION_EXPECTED_CYCLE_LENGTH = 30.5
PERI_MENARCHE_VALIDATION_MIN_CYCLE_LENGTH = 30.0
PERI_MENARCHE_VALIDATION_EXPECTED_IRREGULARITY = 0.30
PERI_MENARCHE_VALIDATION_MIN_IRREGULARITY = 0.28
PERI_MENARCHE_VALIDATION_EXPECTED_OVULATION_RATE = 0.55
PERI_MENARCHE_VALIDATION_MAX_OVULATION = 0.60

DYSMENORRHEA_VALIDATION_MAX_OVULATION_DELTA = 0.08
DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS = (0.2, 1.2)
