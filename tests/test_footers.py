"""The course's three-line footer, word for word, in what the error review, the hit-rate table and the page write.

On 2026-11-21 these three wrote their own second line ("No human source verification is claimed.", "Calculations
use saved views and sourced closes.", or none), and the hit-rate table printed its footer before the agreement count.
"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

LINE_1 = "This is a learning exercise, not financial advice."
VERIFIED = "I verified the sources myself; the judgments are mine."
LINE_3 = "Any remaining errors are my own."


class CourseFooter(unittest.TestCase):
    def test_the_error_review_ends_with_the_course_footer(self):
        import desk_error_review
        text = desk_error_review.FOOTER.format(model="a model")
        self.assertTrue(text.endswith(f"{LINE_1}\n\nAI assistance: OpenAI Codex and Claude Code (review software) and "
                                      f"a model (review analysis). {VERIFIED}\n\n{LINE_3}\n"))

    def test_the_hit_rate_table_ends_with_the_course_footer(self):
        import hit_rate
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, patch.object(sys, "argv", ["hit_rate.py", folder, "--offline"]), \
                contextlib.redirect_stdout(out):
            hit_rate.main()
        text = out.getvalue().rstrip("\n")
        self.assertTrue(text.endswith(f"{LINE_1}\n\nAI assistance: OpenAI Codex. {VERIFIED}\n\n{LINE_3}"))
        self.assertLess(text.index("Agreements: 0/0 (not computed)"), text.index(LINE_1))

    def test_the_page_review_shows_the_course_footer(self):
        source = (Path(__file__).resolve().parents[1] / "page.py").read_text(encoding="utf-8")
        for line in (LINE_1, VERIFIED, LINE_3):
            self.assertIn(line, source)
        self.assertNotIn("No human source verification", source)


if __name__ == "__main__":
    unittest.main()
