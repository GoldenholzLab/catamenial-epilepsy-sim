"""Integrity tests for scientific-source provenance."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hormone_cycler.literature import (
    ANCKAERT_HORMONE_SUBPHASE_TARGETS,
    CITATIONS,
    STRICKER_DAILY_SERUM_REFERENCE,
)


class LiteratureRegistryTest(unittest.TestCase):
    """Keep citation identifiers, titles, and evidence roles internally coherent."""

    def test_citation_mapping_keys_match_embedded_keys(self) -> None:
        self.assertEqual(list(CITATIONS), [citation.key for citation in CITATIONS.values()])

    def test_pubmed_urls_and_evidence_roles_are_declared(self) -> None:
        for citation in CITATIONS.values():
            with self.subTest(citation=citation.key):
                self.assertTrue(citation.title)
                self.assertTrue(citation.evidence_role)
                if citation.pmid:
                    self.assertIn(f"/{citation.pmid}/", citation.url)

    def test_primary_and_held_out_sources_have_distinct_roles(self) -> None:
        self.assertIn("Primary", CITATIONS["li_2023_awhs"].evidence_role)
        self.assertIn("Held-out", CITATIONS["cunningham_2024_flo"].evidence_role)
        self.assertIn("Direction-only", CITATIONS["mortimer_2026_pcos"].evidence_role)

    def test_stricker_daily_reference_is_complete_and_lh_aligned(self) -> None:
        """The waveform source should preserve all published LH-relative daily medians."""

        self.assertEqual(
            [row.lh_offset_days for row in STRICKER_DAILY_SERUM_REFERENCE],
            list(range(-15, 15)),
        )
        progesterone = [row.progesterone_ng_ml for row in STRICKER_DAILY_SERUM_REFERENCE]
        self.assertLess(progesterone[15], progesterone[17])
        self.assertGreaterEqual(sum(value >= 0.75 * max(progesterone) for value in progesterone), 6)

    def test_anckaert_targets_preserve_independent_subphase_ordering(self) -> None:
        """The held-out cohort should show low follicular and broad high-luteal P4."""

        targets = {target.name: target for target in ANCKAERT_HORMONE_SUBPHASE_TARGETS}
        self.assertLess(
            targets["early_follicular"].progesterone_ng_ml,
            targets["early_luteal"].progesterone_ng_ml,
        )
        self.assertGreater(
            targets["mid_luteal"].progesterone_ng_ml,
            targets["early_luteal"].progesterone_ng_ml,
        )
        self.assertGreater(
            targets["mid_luteal"].estradiol_pg_ml,
            targets["early_luteal"].estradiol_pg_ml,
        )


if __name__ == "__main__":
    unittest.main()
