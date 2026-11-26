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


class HonestTextThatWasRefused(unittest.TestCase):
    """Two sentences of the Lowe's practice run of 2026-11-22, each refused once. Each refusal was one more paid
    call, and each repair lost something: the Financial Analyst's sentence no longer said that a figure is a
    difference, and the Verifier, told to fix one line, rewrote ninety of its ninety-nine reasons."""

    def test_one_claim_minus_another_is_a_difference_in_words_not_a_sign(self):
        cell, income = claim(9, "9,200"), claim(8, "$4.1 billion", cid="c2")
        for draft in ("The second half is {c1} minus {c2}.", "It equals {c1} minus {c2}, as the note says."):
            with self.subTest(draft=draft):
                result = run([cell, income], draft)
                self.assertTrue(result.ok, result.errors)
        self.assertEqual(run([cell, income], "It is {c1} minus {c2}.").rendered, "It is 9,200 [10-K.txt:L9] minus $4.1 billion [10-K.txt:L8].")

    def test_a_minus_that_is_a_sign_is_still_refused(self):
        cell, income = claim(9, "9,200"), claim(8, "$4.1 billion", cid="c2")
        for claims, draft in (([income], "The result was minus {c2}."), ([cell, income], "Sales were {c1}; the change was minus {c2}."),
                              ([cell, income], "Sales were {c1}. Minus {c2} was the result."),
                              ([cell, income], "Sales were {c1} and negative {c2}."), ([cell, income], "Sales were {c1} -{c2}.")):
            with self.subTest(draft=draft):
                result = run(claims, draft)
                self.assertFalse(result.ok)
                self.assertTrue(any("next to a claim" in error for error in result.errors), result.errors)


class AYearInAFilingsOwnName(unittest.TestCase):
    """Filings name their loans, notes and plans by year: "the 2025 Term Loan", "2029 Notes". A year after "the"
    always passed. The same name in parentheses, or after "its", was refused as a typed number (the Lowe's run of
    2026-11-22, in the Verifier's reason: "(2025 Term Loan)"). A year now passes when the saved filing itself
    prints it with the capitalised word that follows. Every other bare year is refused as before."""
    NOTE = FILING + "\nBorrowings under the 2025 Term Loan and the 2029 Notes were unchanged.\nThe 2019 Equity Plan expired."
    TEXTS = {"10-K.txt": NOTE}

    def checked(self, draft, claims=()):
        return check({"claims": list(claims), "draft": draft}, self.TEXTS)

    def test_the_name_passes_wherever_it_stands(self):
        for draft in ("It drew on a facility (2025 Term Loan) in the year.", "Its 2025 Term Loan was unchanged.",
                      "Debt includes 2029 Notes and 2025 Term Loan borrowings.", "Awards under its 2019 Equity Plan have ended."):
            with self.subTest(draft=draft):
                result = self.checked(draft)
                self.assertTrue(result.ok, result.errors)

    def test_a_year_the_filing_does_not_print_with_that_word_is_refused(self):
        for draft in ("It drew on a facility (2024 Term Loan) in the year.",      # another year
                      "Its 2025 Revolver was unchanged.",                          # a name the filing does not print
                      "It operates 2025 Stores.",                                  # a count that looks like a year
                      "Sales reached 2025 Million.", "It paid 2025 in fees.", "Margin was 2025."):
            with self.subTest(draft=draft):
                result = self.checked(draft)
                self.assertFalse(result.ok)
                self.assertTrue(any("typed directly" in error for error in result.errors), result.errors)

    def test_a_count_is_not_a_name_even_when_the_filing_prints_the_words(self):
        texts = {"10-K.txt": self.NOTE + "\n2025 Stores opened in the year."}
        self.assertFalse(check({"claims": [], "draft": "It opened 2025 Stores."}, texts).ok)


class PeriodsNamesAndFileNamesAreNotAmounts(unittest.TestCase):
    """Wording from the saved replies of twelve runs (Lowe's, Walmart, Dell, Workday; 2026-11-19 to 2026-11-25).

    On 2026-11-25 every saved reply was run through the ledger again. Sixteen of 103 still held a number refused
    as "typed directly", in a handful of shapes: a month with its year, a quarter with its year, a second year
    after "and", the release's file name, a term such as "364-day", a list such as "the Fortune 500", "Note 17",
    and a numbered heading in bold. Each is a period, a name or a label, and none is an amount. In a run, each
    refusal was one more paid call for the role; in the Workday live run it was the Financial Analyst's. The
    sentences below keep the wording and change the facts. Every rule has a sentence that it must still refuse.
    """
    NOTE = FILING + "\n" + "\n".join([
        "It counts more than half of the Fortune 500 among its customers.", "A 364-day revolving credit facility was added.",
        "Its 12-month subscription revenue backlog grew.", "See Note 17 for revenue by product category.", "Locations 612",
        "Most of the backlog will be recognized over the next 12 months."])
    TEXTS = {"10-K.txt": NOTE, "earnings_release_Ex99-1.txt": "Net sales rose.\nComparable sales rose."}

    def passes(self, *drafts):
        for draft in drafts:
            with self.subTest(passes=draft):
                result = check({"claims": [], "draft": draft}, self.TEXTS)
                self.assertTrue(result.ok, result.errors)

    def refused(self, *drafts):
        for draft in drafts:
            with self.subTest(refused=draft):
                result = check({"claims": [], "draft": draft}, self.TEXTS)
                self.assertFalse(result.ok)
                self.assertTrue(any("typed directly" in error or "written amount" in error for error in result.errors), result.errors)

    def test_a_month_with_its_year(self):
        self.passes("The price is from November 2026, but the EPS is for a fiscal year that ended in January 2026.",
                    "It was acquired in September 2025 (FY2026).", "The quarters ended October 31 of 2026 are compared.")
        self.refused("Sales were November 2026 million.", "It paid May 2026 dollars.", "The fee was March 2026%.", "It was November 20266.")

    def test_a_quarter_a_half_or_months_with_their_year(self):
        self.passes("In Q3 2026, comparable sales rose.", "Sales in the third quarter of 2025 were lower.",
                    "It rose in the nine months of 2025 and fell in the first half of 2026.")
        self.refused("Sales were Q3 2026 million.", "A quarter of 2025 million was spent.", "Sales were Q3 26.", "It kept a quarter of 2025 stores.")

    def test_a_second_year_after_the_first(self):
        self.passes("Growth in fiscal 2026 and 2025 was similar.", "Results for 2026, 2025 and 2024 are shown.", "It fell from 2025 to 2026.")
        self.refused("Sales in 2026 and 2025 million were flat.", "It opened 2026 and 2025.", "Growth in fiscal 2026 and 25 was similar.",
                     "In fiscal 2026 and 2025 stores it grew.")

    def test_the_name_of_a_saved_file(self):
        self.passes("Comparable sales rose (earnings_release_Ex99-1.txt L1, L2).", "Management says so (earnings_release_Ex99-1.txt line 2).")
        self.refused("Comparable sales rose (another_release_Ex99-1.txt L1).", "Comparable sales rose by Ex99-1.")

    def test_a_term_the_filing_prints_with_a_hyphen(self):
        self.passes("It added a 364-day revolving facility.", "Its 12-month subscription revenue backlog grew.")
        self.refused("It added a 180-day facility.", "Backlog covers 12 months.", "It grew over a 5-year period.",
                     "It added 364-day facilities worth 364.")

    def test_a_list_or_a_note_the_filing_names(self):
        self.passes("It serves more than half of the Fortune 500.", "Note 17 gives revenue by product category.")
        self.refused("It serves the Fortune 1000.",            # the filing does not print it
                     "It runs the Locations 612 today, 612.",   # a second, bare number
                     "It runs Locations 612.",                  # a row of a table read as a name: no "the" before it
                     "It serves the Fortune 500 million.", "Note 17 million was paid.")

    def test_a_span_of_months_the_filing_prints(self):
        self.passes("Most of it is to be recognized over the next 12 months.")
        self.refused("Most of it is to be recognized over the next 24 months.",   # the filing says 12
                     "It took 12 months.", "It was open for the next 12 stores.")

    def test_a_years_share_of_something_is_not_a_count_of_shares(self):
        self.passes("The line gives the fiscal 2026 share of net revenue.")
        self.refused("It issued the fiscal 2026 shares of stock.", "It sold in 2026 share after share.")

    def test_the_number_of_a_standard_or_a_level(self):
        # Names that accounting text uses, as "Note 17" is: an accounting standard, a fair-value level, a capital tier.
        self.passes("Revenue is recognized under ASC 606.", "Leases follow Topic 842.", "These are Level 2 inputs.", "Its Tier 1 capital rose.")
        self.refused("It paid ASC 606 million.", "Sales reached Level 2 billion.", "Tier 1 percent was the rate.", "It follows ASC 606 and 842.")

    def test_a_numbered_heading_in_bold(self):
        self.passes("**1. Thesis support: mixed.**\nThe analysts agree.", "**2. Downside exposure: mixed.** Cash generation is solid.")
        self.refused("**1. Thesis support: 40.**", "**12 million.** was the figure.")


class WordsAroundAReply(unittest.TestCase):
    """In the Dell practice run on Claude Opus (2026-11-23) eight of thirteen role calls were refused, none for a
    wrong number, and three roles passed only on their last allowed try. Four refusals were for words around a
    valid JSON object: a sentence before the fence ("Here is the corrected JSON:") or a summary after it. Words
    before the one object cannot be a second answer, so they are dropped. Anything after it still can be."""
    REPLY = '{"claims": [], "draft": "A line."}'

    def test_words_before_the_one_object_are_dropped(self):
        from desk_claims import parse_response
        for reply in ("Here is the corrected JSON:\n\n```json\n" + self.REPLY + "\n```", "I found no failures. All five parts are there.\n```\n" + self.REPLY + "\n```",
                      "Here it is: " + self.REPLY, "Each role has one `Insight:` line; see `draft` below.\n```json\n" + self.REPLY + "\n```"):
            with self.subTest(reply=reply):
                self.assertEqual(parse_response(reply, "Financial Analyst"), {"claims": [], "draft": "A line."})

    def test_anything_after_the_object_or_a_second_object_is_refused(self):
        from desk_claims import ResponseFormatError, parse_response
        for reply in ("```json\n" + self.REPLY + "\n```\n**Results:** every claim is correct.", self.REPLY + "\nCorrection: the line should read B.",
                      "First:\n```json\n" + self.REPLY + "\n```\nSecond:\n```json\n" + self.REPLY + "\n```",
                      "A note on {c1} first.\n```json\n" + self.REPLY + "\n```", "```json\n" + self.REPLY + "\n```\nSee `draft` above.",
                      "Here is the JSON.", "```json\n" + self.REPLY):
            with self.subTest(reply=reply):
                with self.assertRaises(ResponseFormatError):
                    parse_response(reply, "Verifier")

    def test_the_refusal_names_what_is_wrong_and_the_repair_asks_for_the_object_alone(self):
        from desk_claims import ResponseFormatError, Result, parse_response
        with self.assertRaises(ResponseFormatError) as refused:
            parse_response("```json\n" + self.REPLY + "\n```\n**Results:** every claim is correct.", "Verifier")
        self.assertIn("after", str(refused.exception))            # the fence is closed: "unmatched" was not true
        self.assertNotIn("unmatched", str(refused.exception))
        self.assertIn("nothing before or after", Result(errors=["c1: a made-up error."]).repair_message())


class NoNumberWithoutAClaim(unittest.TestCase):
    def test_numbers_in_words_and_in_other_numerals(self):
        for draft in ("Revenue grew eleven per cent.", "Revenue grew eleven % this year.", "An eleven-percent rise in revenue.",
                      "Debt of two bn is due.", "It runs nine hundred locations.", "Revenue grew ¹²%.", "Margin fell ½ point.",
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


REVIEW = "\n".join([
    "Item 7. Management's Discussion and Analysis",                                                                              # 1
    "(amounts in millions, except per share data)",                                                                              # 2
    "Net sales increased 11.2 percent to $48,310 in fiscal 2026 from $43,440 a year ago.",                                       # 3
    "Net income was $2,150, or $4.82 per diluted share, compared with $1,980, or $4.41 per diluted share, in the prior year.",   # 4
    "Selling expenses were $6,120, or 12.7% of net sales, compared with $5,560 a year earlier.",                                 # 5
    "Membership cardholders (in thousands) 71,400",                                                                              # 6
    "Membership fee revenue was $4,828 and the renewal rate was 92.9%.",                                                         # 7
    "The membership fee is $65 a year and the starting wage is $20 an hour.",                                                    # 8
    "The effective tax rate is expected to be in the range of 24.5%–25.5%.",                                                     # 9
    "Segment operating margin—12.3 percent—was a record.",                                                                       # 10
    "Operating income increased $412 million (9%) to $4,990 million.",                                                           # 11
    "Operating margin changed –0.4 points",                                                                                      # 12
    "Net loss $(1,234)",                                                                                                         # 13
    "Statements of Cash Flows (in thousands)",                                                                                   # 14
    "Cash paid for interest was $7,845 in the year.",                                                                            # 15
])


def reviewed(line, value, draft="The figure was {c1}."):
    made_up = {"id": "c1", "file": "10-K.txt", "line": line, "quote": REVIEW.splitlines()[line - 1], "value": value}
    return check({"claims": [made_up], "draft": draft}, {"10-K.txt": REVIEW})


class WhatAnIndependentReviewFound(unittest.TestCase):
    """The audit's first form of the scale rule and of the word rules, read by someone else on 2026-11-22.

    Three sentences were published at a wrong scale where the code before the audit was right: "$43,440 a year ago"
    was taken for an amount "a year", "$1,980" after "per diluted share, compared with" for a per-share amount, and
    a row's own unit, "Membership cardholders (in thousands)", for the scale of the whole section. And honest
    words were refused as amounts: "a third party", "double taxation", "twice in the filing".
    """
    def test_the_headers_scale_goes_on_amounts_that_only_look_like_per_unit_amounts(self):
        for line, value, printed in ((3, "$43,440", "$43,440 million"), (5, "$5,560", "$5,560 million"), (4, "$1,980", "$1,980 million"),
                                     (4, "$2,150", "$2,150 million"), (7, "$4,828", "$4,828 million")):
            with self.subTest(value=value):
                result = reviewed(line, value)
                self.assertTrue(result.ok, result.errors)
                self.assertIn(f"The figure was {printed} [10-K.txt:L{line}]", result.rendered)

    def test_an_amount_per_share_per_year_or_per_hour_keeps_its_own_unit(self):
        for line, value in ((4, "$4.82"), (4, "$4.41"), (8, "$65"), (8, "$20")):
            with self.subTest(value=value):
                result = reviewed(line, value)
                self.assertTrue(result.ok, result.errors)
                self.assertIn(f"The figure was {value} [10-K.txt:L{line}]", result.rendered)

    def test_a_statements_title_gives_the_scale_and_a_rows_label_does_not(self):
        self.assertIn("$7,845 thousand [10-K.txt:L15]", reviewed(15, "$7,845").rendered)

    def test_a_percentage_in_a_sentences_parentheses_or_after_a_range_dash_is_whole(self):
        for line, value in ((11, "9%"), (9, "25.5%"), (9, "24.5%"), (10, "12.3 percent")):
            with self.subTest(value=value):
                result = reviewed(line, value)
                self.assertTrue(result.ok, result.errors)

    def test_a_loss_and_a_decline_still_keep_their_sign(self):
        for line, value in ((13, "1,234"), (13, "$1,234"), (12, "0.4 points"), (12, "0.4")):
            with self.subTest(value=value):
                self.assertFalse(reviewed(line, value).ok)

    def test_ordinary_words_are_not_amounts(self):
        for draft in ("The work is done by a third party.", "A quarter of weak traffic followed, by a quarter of the stores' count.",
                      "The story will unfold over the year, on a scaffold of new stores.", "Management doubled down on its plan.",
                      "Double taxation is a risk, and the lease is triple-net.", "The reasons are twofold: price and mix.",
                      "The figure appears twice in the filing.", "Basel III points to higher capital, and Phase II points to more.",
                      "In 2026 thousands of members joined.", "The core claims above show the same.", "CO₂ emissions are in the filing.",
                      "Net income more than doubled from the prior year.", "Management expects low double-digit growth."):
            with self.subTest(draft=draft):
                result = run([], draft)
                self.assertTrue(result.ok, result.errors)

    def test_the_second_half_is_not_a_half_of_a_claim(self):
        income = claim(8, "$4.1 billion")
        self.assertTrue(run([income], "In the second half {c1} of income was reported.").ok)
        for draft in ("Income was half of {c1}.", "Income was twice {c1}.", "Income was double {c1}."):
            with self.subTest(draft=draft):
                self.assertFalse(run([income], draft).ok)

    def test_a_scale_the_filing_prints_right_after_the_number_may_be_typed(self):
        # The desk saves each tagged piece of a filing on a line of its own: "approximately $", "99.6", "billion,
        # $", "79.3", "billion". The scale cannot be part of the claim's value, which is one line. A real reply of
        # 2026-11-19 wrote "{c33} billion" for such a number, rightly, and the rule refused it.
        pieces = "Of total net sales, approximately $\n99.6\nbillion were online, and $\n79.3\nmillion came from clubs.\nOther income\n12.5\n"
        number = {"id": "c1", "file": "10-K.txt", "line": 2, "quote": "99.6", "value": "99.6"}
        other = {"id": "c1", "file": "10-K.txt", "line": 7, "quote": "12.5", "value": "12.5"}
        ask = lambda claim, draft: check({"claims": [claim], "draft": draft}, {"10-K.txt": pieces})
        self.assertTrue(ask(number, "Online net sales were {c1} billion.").ok, ask(number, "Online net sales were {c1} billion.").errors)
        self.assertFalse(ask(number, "Online net sales were {c1} million.").ok)      # the filing says billion
        self.assertFalse(ask(number, "Online net sales were {c1} bn.").ok)           # the filing's own word, or none
        self.assertFalse(ask(other, "Other income was {c1} billion.").ok)            # no scale follows this number

    def test_each_word_before_a_claim_that_changes_it(self):
        income = claim(8, "$4.1 billion")
        for word in ("negative", "minus", "twice", "thrice", "double", "triple", "half of"):
            with self.subTest(word=word):
                self.assertFalse(run([income], f"The result was {word} {{c1}}.").ok)

    def test_a_per_share_amount_named_before_or_after_it_and_each_unit_word(self):
        lines = "\n".join(["Item 7. Results", "(amounts in millions, except per share data)", "Diluted earnings per share of $4.82 rose.",
                           "The fee is $120 per member and $10 each month, or $3 a day.", "Net sales were $9,226."])
        ask = lambda line, value: check({"claims": [{"id": "c1", "file": "10-K.txt", "line": line, "quote": lines.splitlines()[line - 1], "value": value}],
                                         "draft": "It was {c1}."}, {"10-K.txt": lines})
        for line, value in ((3, "$4.82"), (4, "$120"), (4, "$10"), (4, "$3")):
            with self.subTest(value=value):
                self.assertIn(f"It was {value} [10-K.txt:L{line}]", ask(line, value).rendered)
        self.assertIn("It was $9,226 million [10-K.txt:L5]", ask(5, "$9,226").rendered)

    def test_the_whole_amount_behind_a_dash_passes(self):
        self.assertTrue(reviewed(12, "–0.4 points").ok)

    def test_amounts_in_words_are_still_refused(self):
        for draft in ("Revenue grew eleven per cent.", "Debt of two bn is due.", "It runs nine hundred locations.", "Revenue grew XII percent.",
                      "Revenue grew ¹²%.", "### The core claims, read and computed in code", "Sales of Item 12 million in revenue."):
            with self.subTest(draft=draft):
                self.assertFalse(run([], draft).ok)


if __name__ == "__main__":
    unittest.main()
