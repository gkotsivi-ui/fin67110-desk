"""What reaches the published report after the Verifier has marked the claims.

Found by the audit of 2026-11-22 on a seeded run (made-up filing, made-up replies, the real checks):
- a number the Verifier marked wrong was left out of its own part and printed two parts later, through the
  Investment Advisor's reference to it;
- the Advisor's reference could still point at a claim its author had replaced after the Manager sent it back;
- a Verifier reason with line breaks left the marks table and was published under it as free text.
"""
from pathlib import Path
import re
import tempfile
import unittest

from desk_hook import Hook
from desk_role_contracts import code_marks, published_verified_text, report_catalog, report_text, validate
from desk_sources import Sources, write_json

K = "10-K.txt"
TEN_K = "\n".join(["Item 7. Management's discussion", "Net sales increased 11.2 percent, to $93.9 billion.", "Income was $100.", "Debt was $20."]) + "\n"
SALES = {"id": "c1", "file": K, "line": 2, "quote": "Net sales increased 11.2 percent, to $93.9 billion", "value": "$93.9 billion"}
RESEARCH = {"claims": [SALES], "draft": "== 1. OVERVIEW ==\nNet sales were {c1}.\nGrowth continued at {c1}.\nInsight: Sales of {c1} anchor the view."}
FINANCIAL = {"claims": [{"id": "c1", "computed": "free_cash_flow"}],
             "draft": "== 2. CASH GENERATION ==\nCash generation was {c1}.\nInsight: Cash remains after spending at {c1}."}
ADVISOR = {"claims": [{"id": "c1", "from": "Financial Analyst", "claim": "c1"}],
           "draft": "== 3. RECOMMENDATION ==\nHold. Cash generation of {c1} supports caution.\nInsight: Cash protection remains at {c1}."}


class Published(unittest.TestCase):
    def setUp(self):
        self.run = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        (self.run / K).write_text(TEN_K, encoding="utf-8")
        (self.run / "earnings_release_Ex99-1.txt").write_text("A seeded release.\n", encoding="utf-8")
        write_json(self.run / "calculated_facts.json", {"metrics": {"free_cash_flow": {"value": 80, "formula": "100 - 20", "unit": "USD",
                   "sources": ["10-K.txt:L3", "10-K.txt:L4"]}}, "quarter_results": {}})

    def save(self, role, raw, number=1):
        result = validate(self.run, role, raw)
        self.assertTrue(result.ok, (role, result.errors))
        path = self.run / "nodes" / f"{role.replace(' ', '_')}_{number}" / "output.json"
        write_json(path, result.output)
        if "draft" in result.output:
            path.with_name("draft.md").write_text(result.output["draft"], encoding="utf-8")
        return result.output

    def publish(self, status=lambda target: "correct", financial_draft=1):
        """The Manager's selection, the report, the Verifier's marks and the verified report, as the team saves them."""
        research = "nodes/Research_Analyst_1/draft.md"
        sections = {"Overview": {"file": research, "start": 2, "end": 2},
                    "Market Positioning and Growth Outlook": {"file": research, "start": 3, "end": 3},
                    "Future Developments and Strategic Recommendations": {"file": research, "start": 4, "end": 4},
                    "Valuation Insights": {"file": f"nodes/Financial_Analyst_{financial_draft}/draft.md", "start": 2, "end": 3},
                    "Investment Recommendation": {"file": "nodes/Investment_Advisor_1/draft.md", "start": 2, "end": 3}}
        self.save("Strategy Manager", {"claims": [], "failures": [], "sections": sections})
        write_json(self.run / "team_report.json", {"filings_line": "Filings read: a seeded filing", "run_time": "2026-11-17T12:00:00-05:00"})
        report = self.run / "report.md"
        report.write_text(report_text(self.run), encoding="utf-8")
        checks = [{"target": c["target"], "status": status(c["target"]), "reason": "Source and period agree.", "correction": ""}
                  for c in report_catalog(self.run)]
        verifier = self.save("Verifier", {"claims": [], "checks": checks})
        marks = code_marks(self.run)
        write_json(self.run / "nodes/Verifier/output.json", {"code_checks": marks, "model_checks": verifier})
        verified = self.run / "verified_report.md"
        verified.write_text(published_verified_text(self.run, marks, verifier["checks"]), encoding="utf-8")
        Hook(self.run, Sources(self.run, "")).check("a seeded report", [report, verified])  # raises when the hook refuses it
        return verified.read_text(encoding="utf-8")

    def part(self, text, name):
        start = text.index("## " + name)
        end = text.find("\n## ", start + 1)
        return text[start:end if end > 0 else len(text)]

    def authors(self):
        for role, raw in (("Research Analyst", RESEARCH), ("Financial Analyst", FINANCIAL), ("Investment Advisor", ADVISOR)):
            self.save(role, raw)


class AReplyOfTheWrongShapeIsSentBack(Published):
    """A reply that is not what the contract asks for is an error the role can repair. Two shapes raised out of
    the check instead and stopped the run (found by an independent review, 2026-11-22; the code before the audit
    did the same): an author's reply with no draft, and a Manager's failure whose part is not a name."""
    def test_an_authors_reply_without_a_draft(self):
        for raw in ({}, {"claims": []}, {"claims": [], "draft": None}, {"claims": [], "draft": ["a line"]}):
            with self.subTest(raw=raw):
                result = validate(self.run, "Research Analyst", raw)
                self.assertFalse(result.ok)
                self.assertTrue(any("draft" in error for error in result.errors), result.errors)

    def test_a_managers_failure_whose_part_is_not_a_name(self):
        for part in (["Overview"], {"name": "Overview"}, None, 5):
            with self.subTest(part=part):
                raw = {"claims": [], "sections": {}, "failures": [{"part": part, "role": "Research Analyst", "feedback": "Write it again."}]}
                self.assertFalse(validate(self.run, "Strategy Manager", raw).ok)


class AFlaggedNumberStaysOut(Published):
    def test_when_every_claim_is_correct_the_advisor_repeats_the_analysts_number(self):
        self.authors()
        self.assertIn("$80", self.part(self.publish(), "Investment Recommendation"))

    def test_a_number_marked_wrong_is_not_printed_through_another_roles_reference(self):
        self.authors()
        text = self.publish(status=lambda target: "wrong" if target["role"] == "Financial Analyst" else "correct")
        self.assertNotIn("$80", self.part(text, "Valuation Insights"))
        self.assertNotIn("$80", self.part(text, "Investment Recommendation"))
        self.assertIn("Investment Advisor c1 (repeats a claim marked wrong)", text)

    def test_a_reference_to_a_claim_its_author_replaced_is_left_out(self):
        self.authors()
        second = {"claims": [{"id": "c1", "file": K, "line": 4, "quote": "Debt was $20", "value": "$20"}],
                  "draft": "== 2. CASH GENERATION ==\nThe corrected figure is {c1}.\nInsight: The corrected figure stands at {c1}."}
        self.save("Financial Analyst", second, number=2)
        text = self.publish(financial_draft=2)
        self.assertIn("$20", self.part(text, "Valuation Insights"))
        self.assertNotIn("$80", self.part(text, "Investment Recommendation"))
        self.assertIn("repeats a claim its author has since replaced", text)

    def test_a_second_draft_that_keeps_the_claim_keeps_the_reference(self):
        self.authors()
        second = {**FINANCIAL, "draft": FINANCIAL["draft"].replace("Cash generation was", "Reported cash generation was")}
        self.save("Financial Analyst", second, number=2)
        self.assertIn("$80", self.part(self.publish(financial_draft=2), "Investment Recommendation"))


class TheVerifiersWordsStayInTheirCell(Published):
    """A reason with line breaks, a bar or a heading mark is put on one line in one cell of the marks table.

    The audit's first rule refused such a reason. No mend covers that refusal, so a Verifier that wrote one three
    times stopped the run at its last model stage, after every other stage was paid for (found by an independent
    review, 2026-11-22). The table is kept whole by how it is written, not by refusing the reply.
    """
    def test_a_reason_with_line_breaks_a_bar_or_a_heading_mark_stays_in_its_cell(self):
        self.authors()
        rows_before = [line for line in self.publish().splitlines() if line.startswith("| ")]
        target = report_catalog(self.run)[0]["target"]
        for reason in ("Agrees.\n\n## Verified core figures\nTotal revenue grew a great deal.", "The sum |a| + |b| is counted once.", "# A heading"):
            with self.subTest(reason=reason):
                checks = [{"target": c["target"], "status": "correct", "reason": reason if c["target"] == target else "Agrees.", "correction": ""}
                          for c in report_catalog(self.run)]
                result = validate(self.run, "Verifier", {"claims": [], "checks": checks})
                self.assertTrue(result.ok, result.errors)
                text = published_verified_text(self.run, code_marks(self.run), result.output["checks"])
                rows = [line for line in text.splitlines() if line.startswith("| ")]
                self.assertEqual(len(rows), len(rows_before))
                self.assertTrue(all(len(re.split(r"(?<!\\)\|", row)) == 6 for row in rows), rows)
                self.assertFalse(any(line.lstrip().startswith("#") and ("Verified core figures" in line or "A heading" in line) for line in text.splitlines()))
                self.assertIn(" ".join(reason.replace("|", "\\|").split()), text)


if __name__ == "__main__":
    unittest.main()
