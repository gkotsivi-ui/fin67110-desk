"""The claims ledger: what a model's text cannot do to a number.

On 2026-11-22 the audit drove the ledger with made-up filings and made-up replies. It found that code itself wrote
"$1.16 million" for a dividend (a table header's scale went on every "$" value of the section); that a header
worded "(in millions, ...)" was not read at all; that a loss in parentheses was published as a gain; that a unit,
a scale, a sign or a multiplier typed next to a claim passed ("$9,200 [cited] billion", "-$4.1 billion"); that a
number written in words or in other numerals passed with no claim; that a typed citation passed; and that a draft
could hold a table that reads as the desk's own. Every line and amount here is made up.
"""
import unittest

from desk_claims import check

FILING = "\n".join([
    "Item 7. Management's discussion",                                                            # 1
    "(amounts in millions, except per share data)",                                               # 2
    "Net sales were $9,226 and net income was $452.",                                             # 3
    "The company raised its quarterly dividend to $1.16 and its starting wage to $20 an hour.",   # 4
    "Net income was $7,367, or $16.56 per diluted share.",                                        # 5
    "Net loss $(1,234)",                                                                          # 6
    "Operating margin changed –0.4 points",                                                       # 7
    "Operating income was $4.1 billion in the year.",                                             # 8
    "9,200",                                                                                      # 9
    "The company operates 612 warehouses.",                                                       # 10
    "Item 8. Financial statements",                                                               # 11
    "(in millions, except per share data)",                                                       # 12
    "Total revenue $93,900",                                                                      # 13
    "32.95",                                                                                      # 14
])
TEXTS = {"10-K.txt": FILING}


def claim(line, value, quote=None, cid="c1"):
    return {"id": cid, "file": "10-K.txt", "line": line, "quote": quote or FILING.splitlines()[line - 1], "value": value}


def run(claims, draft):
    return check({"claims": claims, "draft": draft}, TEXTS)


class TheScaleOfADollarAmount(unittest.TestCase):
    def test_whole_dollars_with_a_thousands_separator_take_the_headers_scale(self):
        result = run([claim(3, "$9,226")], "Net sales were {c1}.")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.rendered, "Net sales were $9,226 million [10-K.txt:L3].")

    def test_a_dividend_and_a_wage_are_never_made_millions(self):
        for value in ("$1.16", "$20"):
            with self.subTest(value=value):
                result = run([claim(4, value)], "It is {c1}.")
                self.assertNotIn("million", " ".join(result.values.values()) if result.ok else "")
        self.assertEqual(run([claim(4, "$20")], "The starting wage is {c1} an hour.").rendered, "The starting wage is $20 [10-K.txt:L4] an hour.")
        refused = run([claim(4, "$1.16")], "The dividend is {c1}.")
        self.assertFalse(refused.ok)
        self.assertIn("does not say whether $1.16 is in that scale", refused.errors[0])

    def test_a_per_share_amount_keeps_its_own_unit(self):
        self.assertEqual(run([claim(5, "$16.56")], "Diluted earnings were {c1} a share.").rendered, "Diluted earnings were $16.56 [10-K.txt:L5] a share.")

    def test_an_amount_in_doubt_is_refused_with_the_reason(self):
        refused = run([claim(3, "$452")], "Net income was {c1}.")
        self.assertFalse(refused.ok)
        self.assertIn("Cite a line that states the scale in words, or use a saved fact", refused.errors[0])

    def test_a_scale_stated_on_the_line_is_the_scale(self):
        self.assertEqual(run([claim(8, "$4.1 billion")], "Operating income was {c1}.").rendered, "Operating income was $4.1 billion [10-K.txt:L8].")

    def test_a_header_worded_in_millions_is_read(self):
        self.assertEqual(run([claim(13, "$93,900")], "Total revenue was {c1}.").rendered, "Total revenue was $93,900 million [10-K.txt:L13].")


class TheSignOfANumber(unittest.TestCase):
    def test_a_loss_in_parentheses_is_not_cut_out_of_them(self):
        self.assertFalse(run([claim(6, "1,234")], "Net income was {c1}.").ok)

    def test_a_decline_behind_an_en_dash_is_not_cut_from_it(self):
        self.assertFalse(run([claim(7, "0.4")], "Operating margin rose {c1} points.").ok)


class NothingTypedNextToAClaim(unittest.TestCase):
    """A scale, a sign or a multiplier typed next to a claim changes the number the claim checked.

    A rate typed after a bare table cell ("{c1} percent of sales") and a claim in parentheses as an aside are
    left alone. Both stand in the replies a real model gave on 2026-11-20, which the first form of this rule
    refused: replaying those saved replies showed it on 2026-11-22. Whether "percent" is the right label for
    the cell is the Verifier's question, as every label is.
    """
    def test_a_scale_a_sign_or_a_multiplier(self):
        cell, count, income = claim(9, "9,200"), claim(10, "612"), claim(8, "$4.1 billion")
        for claims, draft in (([cell], "Net sales were ${c1} billion."), ([cell], "Net sales were {c1} million."),
                              ([cell], "Net sales were {c1} bn."), ([cell], "Net sales were ${c1}."),
                              ([income], "The result was -{c1}."), ([income], "The result was minus {c1}."),
                              ([income], "Operating income was twice {c1}."), ([count], "Growth was {c1}-fold.")):
            with self.subTest(draft=draft):
                result = run(claims, draft)
                self.assertFalse(result.ok)
                self.assertTrue(any("next to a claim" in error for error in result.errors), result.errors)

    def test_ordinary_sentences_around_a_claim_pass(self):
        income, count = claim(8, "$4.1 billion"), claim(10, "612", cid="c2")
        for claims, draft in (([income], "Operating income was {c1}."), ([income], "Operating income ({c1} in the year) rose."),
                              ([count], "It operates {c2} warehouses."), ([income, count], "Income of {c1} came from {c2} warehouses."),
                              ([income], "A well-run business earned {c1}.")):
            with self.subTest(draft=draft):
                result = run(claims, draft)
                self.assertTrue(result.ok, result.errors)

    def test_a_rate_after_a_bare_cell_and_a_claim_in_parentheses_pass(self):
        cell, income = claim(14, "32.95"), claim(8, "$4.1 billion", cid="c2")
        for claims, draft in (([cell], "Gross margin was {c1} percent of sales."), ([cell], "Gross margin was {c1}% of sales."),
                              ([cell, income], "The margin ({c1}) and the income ({c2}) both rose."),
                              ([cell], "It trades at {c1} times earnings.")):
            with self.subTest(draft=draft):
                result = run(claims, draft)
                self.assertTrue(result.ok, result.errors)


class NoNumberWithoutAClaim(unittest.TestCase):
    def test_numbers_in_words_and_in_other_numerals(self):
        for draft in ("Revenue grew eleven per cent.", "Revenue grew eleven % this year.", "An eleven-percent rise in revenue.",
                      "Debt of two bn is due.", "It runs nine hundred locations.", "Debt tripled and margins fell by a half.",
                      "Growth was double-digit.", "Sales rose twofold.", "Revenue grew ¹²%.", "Margin fell ½ point.",
                      "Revenue grew XII percent.", "Revenue grew Ⅻ percent."):
            with self.subTest(draft=draft):
                self.assertFalse(run([], draft).ok)

    def test_plain_words_are_not_numbers(self):
        for draft in ("The company is one of the largest retailers.", "It reports two segments.", "Management kept a long-term view.",
                      "A single warehouse format serves members."):
            with self.subTest(draft=draft):
                result = run([], draft)
                self.assertTrue(result.ok, result.errors)


class NoTypedCitationAndNoTable(unittest.TestCase):
    def test_a_typed_citation_is_refused(self):
        for draft in ("Revenue rose [10-K.txt:L999].", "Revenue rose [XBRL tag Revenues, period end 2026-08-30, filing 0000000001-26-000001]."):
            with self.subTest(draft=draft):
                self.assertFalse(run([], draft).ok)

    def test_a_table_row_or_the_desks_own_title_is_refused(self):
        income = claim(8, "$4.1 billion")
        for draft in ("| Total revenue | {c1} | XBRL tag Revenues |", "### The core claims, read and computed in code\nIncome was {c1}."):
            with self.subTest(draft=draft):
                self.assertFalse(run([income], draft).ok)

    def test_a_roles_own_heading_passes(self):
        self.assertTrue(run([claim(8, "$4.1 billion")], "== 1. OVERVIEW ==\nIncome was {c1}.").ok)



class AReferenceIsNotAnAmount(unittest.TestCase):
    """An item, a form, a table, a year or a date may be typed. Followed by a scale or a rate, it is an amount.

    Until 2026-11-22 "Sales of Item 12 million" and "Insiders filed Form 4 billion" passed with no claim, because
    the words before the number made it a reference, whatever came after it.
    """
    def test_a_reference_followed_by_a_scale_or_a_rate_is_refused(self):
        for text in ("Sales of Item 12 million in revenue.", "Insiders filed Form 4 billion.",
                     "Revenue rose by a figure 12 percent above last year.", "Debt is a figure 400 million higher.",
                     "Growth in table 12 percent terms.", "Debt rose from 2019 bn.", "Margin for FY99 percent held.",
                     "Sales in Q3 billion rose."):
            with self.subTest(text=text):
                self.assertFalse(run([], text).ok)

    def test_a_date_that_is_no_date_is_refused(self):
        self.assertFalse(run([], "Net sales were 9999-99-99.").ok)
        self.assertFalse(run([], "Net sales were 2026-13-45.").ok)

    def test_plain_references_and_dates_pass(self):
        for text in ("See Item 7 and Item 1A of the 10-K.", "Insiders filed a Form 4.",
                     "Table 3 lists the segments, and figure 2 the stores.", "The release was filed on 2026-10-06.",
                     "Guidance for FY2027 was kept.", "Item 7 points to higher freight costs.", "Q3 and H2 were strong."):
            with self.subTest(text=text):
                self.assertTrue(run([], text).ok, run([], text).errors)


class AValueKeepsItsUnit(unittest.TestCase):
    """A value is the whole amount on the cited line. "5.2" cut from "5.2 per cent" left the unit to the model."""
    LINE = "Comparable sales rose 5.2 per cent, traffic rose 50 bp and the margin gained 0.4 points."

    def cut(self, value):
        made_up = {"id": "c1", "file": "10-K.txt", "line": 1, "quote": self.LINE, "value": value}
        return check({"claims": [made_up], "draft": "The figure was {c1}."}, {"10-K.txt": self.LINE})

    def test_a_value_cut_from_its_unit_is_refused(self):
        for value in ("5.2", "50", "0.4"):
            with self.subTest(value=value):
                self.assertFalse(self.cut(value).ok)

    def test_the_whole_amount_passes(self):
        for value in ("5.2 per cent", "50 bp", "0.4 points"):
            with self.subTest(value=value):
                self.assertTrue(self.cut(value).ok, self.cut(value).errors)


class ASavedFactIsADollarAmount(unittest.TestCase):
    """The ledger prints every saved fact with a dollar sign. That is right only while every fact the desk saves
    is in dollars: a share count added to the list would be published as "$443 million"."""
    def test_every_fact_the_desk_saves_is_in_dollars(self):
        from equity_research_desk import CONCEPTS
        self.assertEqual({spec["unit"] for spec in CONCEPTS.values()} - {"USD", "USD/shares"}, set())


if __name__ == "__main__":
    unittest.main()
