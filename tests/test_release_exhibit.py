"""The group desk reads the newest earnings 8-K, and finds its release by what the exhibit holds.

On 2026-11-22 the audit ran made-up filings through step 2 of both desks. The group desk took the first file
whose name or type matched "99.1": it read a slide deck as the release when the release was Exhibit 99.2, and
when the newest earnings 8-K typed its exhibit "EX-99" it went back, without a word, to last quarter's 8-K, whose
Accepted time then set the price and the live-record window. The base desk has had the right rule since
2026-11-11 (lab02_desk.py). The rule now lives in desk_rules.py and both desks use it. Every filing here is made up.
"""
import contextlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from equity_research_desk import Desk, filings_line

CIK = "0000999999"
ROOT = "https://www.sec.gov/Archives/edgar/data/999999"
NEW_8K, OLD_8K, TEN_K, TEN_Q = "0000999999-26-000030", "0000999999-26-000015", "0000999999-26-000010", "0000999999-26-000020"
RELEASE = "<html><body><p>Made Up Stores reports results</p><p>Condensed Consolidated Statements of Income</p><table><tr><td>Net sales</td><td>100</td></tr></table></body></html>"
SLIDES = "<html><body><p>Made Up Stores Investor Presentation</p><p>Our strategy</p></body></html>"


def index_page(accepted, exhibits):
    rows = "".join(f"<tr><td>{n}</td><td>a document</td><td><a href='/x/{name}'>{name}</a></td><td>{kind}</td><td>1</td></tr>"
                   for n, (kind, name) in enumerate(exhibits, 1))
    return f"<html><body><div>Accepted</div><div>{accepted}</div><table>{rows}</table></body></html>"


def folder(accession):
    return f"{ROOT}/{accession.replace('-', '')}"


class Web:
    """A stand-in for SEC EDGAR: the pages of one made-up company, and a count of each page asked for."""

    def __init__(self, filings, pages):
        recent = {key: [row[key] for row in filings] for key in ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument", "items")}
        self.pages = {f"https://data.sec.gov/submissions/CIK{CIK}.json": {"filings": {"recent": recent, "files": []}}, **pages}
        self.asked = []

    def get(self, url):
        self.asked.append(url)
        if url not in self.pages:
            raise AssertionError("The desk asked for a page the test did not make: " + url)
        page = self.pages[url]
        return SimpleNamespace(content=page.encode("utf-8") if isinstance(page, str) else b"", json=lambda: page)


def filing(form, accession, filed, items="", report="2026-06-30", primary="main.htm"):
    return {"form": form, "accessionNumber": accession, "filingDate": filed, "reportDate": report, "primaryDocument": primary, "items": items}


ANNUAL = [filing("10-K", TEN_K, "2026-08-15"), filing("10-Q", TEN_Q, "2026-05-10", report="2026-03-31")]
ANNUAL_PAGES = {f"{folder(TEN_K)}/{TEN_K}-index.html": index_page("2026-08-15 16:10:00", [("10-K", "main.htm")]),
                f"{folder(TEN_Q)}/{TEN_Q}-index.html": index_page("2026-05-10 16:10:00", [("10-Q", "main.htm")])}


def step2(filings, pages):
    web = Web(filings + ANNUAL, {**ANNUAL_PAGES, **pages})
    desk = Desk.__new__(Desk)
    desk.ticker, desk.company, desk.cik, desk.filed_override, desk.market_evidence = "ZZZZ", "Made Up Stores", CIK, None, {}
    desk.output_dir = Path(tempfile.mkdtemp())
    desk.get = web.get
    with contextlib.redirect_stdout(io.StringIO()):
        desk.step2()
    return desk, web


class TheReleaseIsFoundByWhatItHolds(unittest.TestCase):
    def test_a_slide_deck_in_99_1_is_not_the_release(self):
        desk, _ = step2([filing("8-K", NEW_8K, "2026-11-19", items="2.02,9.01")],
                        {f"{folder(NEW_8K)}/{NEW_8K}-index.html": index_page("2026-11-19 16:05:00", [("8-K", "main.htm"), ("EX-99.1", "slides.htm"), ("EX-99.2", "release.htm")]),
                         f"{folder(NEW_8K)}/slides.htm": SLIDES, f"{folder(NEW_8K)}/release.htm": RELEASE})
        release = desk.filings["8-K"]
        self.assertEqual((release.release_label, release.release_document), ("99.2", "release.htm"))
        self.assertTrue(release.release_url.endswith("/release.htm"))
        self.assertIn("Item 2.02 earnings release, Exhibit 99.2 release.htm", filings_line(desk.filings, CIK))

    def test_one_exhibit_99_is_the_release_and_is_not_read_twice(self):
        desk, web = step2([filing("8-K", NEW_8K, "2026-11-19", items="2.02")],
                          {f"{folder(NEW_8K)}/{NEW_8K}-index.html": index_page("2026-11-19 16:05:00", [("8-K", "main.htm"), ("EX-99.1", "release.htm")])})
        self.assertEqual((desk.filings["8-K"].release_label, desk.filings["8-K"].release_document), ("99.1", "release.htm"))
        self.assertFalse(any(url.endswith("release.htm") for url in web.asked))


class TheNewestEarnings8KIsTheOneRead(unittest.TestCase):
    OLD_PAGES = {f"{folder(OLD_8K)}/{OLD_8K}-index.html": index_page("2026-08-20 16:05:00", [("8-K", "main.htm"), ("EX-99.1", "q2release.htm")])}

    def test_an_exhibit_typed_ex_99_is_read_and_last_quarters_8k_is_not(self):
        desk, _ = step2([filing("8-K", OLD_8K, "2026-08-20", items="2.02"), filing("8-K", NEW_8K, "2026-11-19", items="2.02")],
                        {**self.OLD_PAGES, f"{folder(NEW_8K)}/{NEW_8K}-index.html": index_page("2026-11-19 16:05:00", [("8-K", "main.htm"), ("EX-99", "release.htm")])})
        release = desk.filings["8-K"]
        self.assertEqual((release.accession, release.accepted, release.release_label), (NEW_8K, "2026-11-19 16:05:00", "99"))
        self.assertIn("Exhibit 99 release.htm", filings_line(desk.filings, CIK))

    def test_an_earnings_8k_with_no_exhibit_99_stops_and_names_itself(self):
        with self.assertRaisesRegex(RuntimeError, NEW_8K + r".*no Exhibit 99"):
            step2([filing("8-K", OLD_8K, "2026-08-20", items="2.02"), filing("8-K", NEW_8K, "2026-11-19", items="2.02")],
                  {**self.OLD_PAGES, f"{folder(NEW_8K)}/{NEW_8K}-index.html": index_page("2026-11-19 16:05:00", [("8-K", "main.htm"), ("EX-10.1", "contract.htm")])})

    def test_an_8k_without_item_2_02_is_skipped_by_its_items_alone(self):
        other = "0000999999-26-000040"
        desk, web = step2([filing("8-K", other, "2026-11-20", items="5.02"), filing("8-K", NEW_8K, "2026-11-19", items="2.02")],
                          {f"{folder(NEW_8K)}/{NEW_8K}-index.html": index_page("2026-11-19 16:05:00", [("8-K", "main.htm"), ("EX-99.1", "release.htm")])})
        self.assertEqual(desk.filings["8-K"].accession, NEW_8K)
        self.assertFalse(any(other.replace("-", "") in url for url in web.asked))

    def test_an_8k_that_lists_no_items_is_read_for_item_2_02(self):
        desk, _ = step2([filing("8-K", NEW_8K, "2026-11-19", items="")],
                        {f"{folder(NEW_8K)}/main.htm": "<html><body>Item 2.02 Results of Operations and Financial Condition</body></html>",
                         f"{folder(NEW_8K)}/{NEW_8K}-index.html": index_page("2026-11-19 16:05:00", [("8-K", "main.htm"), ("EX-99.1", "release.htm")])})
        self.assertEqual(desk.filings["8-K"].accession, NEW_8K)

    def test_the_newest_filing_is_chosen_by_its_date_not_by_the_lists_order(self):
        older_10k = "0000999999-25-000009"
        desk, _ = step2([filing("10-K", older_10k, "2025-08-15", report="2025-06-30"), filing("8-K", NEW_8K, "2026-11-19", items="2.02")],
                        {f"{folder(NEW_8K)}/{NEW_8K}-index.html": index_page("2026-11-19 16:05:00", [("8-K", "main.htm"), ("EX-99.1", "release.htm")])})
        self.assertEqual(desk.filings["10-K"].accession, TEN_K)


if __name__ == "__main__":
    unittest.main()
