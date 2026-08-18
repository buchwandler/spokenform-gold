import unittest

from spokenform_gold.importers.surface_patterns import infer_surface_pattern


class SurfacePatternTests(unittest.TestCase):
    def test_decimal_patterns(self):
        self.assertEqual(
            infer_surface_pattern(category="decimal", surface="1.2"), "plain_decimal"
        )
        self.assertEqual(
            infer_surface_pattern(category="decimal", surface=".3"), "leading_decimal"
        )
        self.assertEqual(
            infer_surface_pattern(category="decimal", surface="0.02"), "leading_zero"
        )
        self.assertEqual(
            infer_surface_pattern(category="decimal", surface="-1.2"),
            "negative_decimal",
        )
        self.assertEqual(
            infer_surface_pattern(category="decimal", surface="1,000.2"),
            "grouped_decimal",
        )

    def test_date_and_time_patterns(self):
        self.assertEqual(
            infer_surface_pattern(category="date", surface="2025-03-04"), "iso_date"
        )
        self.assertEqual(
            infer_surface_pattern(category="date", surface="May 12, 2025"),
            "month_name_date",
        )
        self.assertEqual(
            infer_surface_pattern(category="date", surface="03/04/2025"),
            "ambiguous_numeric_date",
        )
        self.assertEqual(
            infer_surface_pattern(category="date", surface="20/04/2025"), "slash_date"
        )
        self.assertEqual(
            infer_surface_pattern(category="time", surface="09:30"), "leading_zero_time"
        )
        self.assertEqual(
            infer_surface_pattern(category="time", surface="10:30 PM"), "time_12h"
        )
        self.assertEqual(
            infer_surface_pattern(category="time", surface="00:00"), "midnight"
        )
        self.assertEqual(
            infer_surface_pattern(category="time", surface="10:30"), "time_24h"
        )

    def test_ambiguous_and_context_patterns(self):
        self.assertEqual(
            infer_surface_pattern(
                category="fraction", surface="3/4", text="The fraction is 3/4"
            ),
            "numeric_fraction",
        )
        self.assertEqual(
            infer_surface_pattern(
                category="fraction", surface="3/4", text="The score was 3/4"
            ),
            "fraction_vs_slash",
        )
        self.assertEqual(
            infer_surface_pattern(
                category="score_or_range", surface="3-2", text="The score was 3-2"
            ),
            "score",
        )
        self.assertEqual(
            infer_surface_pattern(
                category="score_or_range", surface="3-2", text="The range is 3-2"
            ),
            "numeric_range",
        )
        self.assertEqual(
            infer_surface_pattern(
                category="score_or_range", surface="3-2", text="Countdown 3-2-1"
            ),
            "countdown",
        )

    def test_math_version_identifier_and_network_patterns(self):
        self.assertEqual(
            infer_surface_pattern(category="math_expression", surface="3-2"),
            "subtraction",
        )
        self.assertEqual(
            infer_surface_pattern(category="math_expression", surface="3/2"), "division"
        )
        self.assertEqual(
            infer_surface_pattern(category="math_expression", surface="2^3"), "power"
        )
        self.assertEqual(
            infer_surface_pattern(category="math_expression", surface="x2"), "subscript"
        )
        self.assertEqual(
            infer_surface_pattern(category="version", surface="v2.0"), "simple_version"
        )
        self.assertEqual(
            infer_surface_pattern(category="version", surface="v2.0.0"),
            "semantic_version",
        )
        self.assertEqual(
            infer_surface_pattern(category="version", surface="v2.0.0-beta.4"),
            "prerelease_version",
        )
        self.assertEqual(
            infer_surface_pattern(category="ip_address", surface="192.168.0.1"), "ipv4"
        )
        self.assertEqual(
            infer_surface_pattern(
                category="url_or_email", surface="https://example.com"
            ),
            "url",
        )
        self.assertEqual(
            infer_surface_pattern(category="url_or_email", surface="a@example.com"),
            "email",
        )
        self.assertEqual(
            infer_surface_pattern(category="acronym", surface="NASA"), "initialism"
        )
        self.assertEqual(
            infer_surface_pattern(category="acronym", surface="APIs"), "plural_acronym"
        )
        self.assertEqual(
            infer_surface_pattern(category="acronym", surface="Radar"),
            "word_like_acronym",
        )


if __name__ == "__main__":
    unittest.main()
