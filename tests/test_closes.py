"""Offline tests of the closes reader: an exported CSV file, a fake LSEG session, and the price the desk takes.

No test reads .env, opens an LSEG session or reads real market data.
Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import types
import unittest
from datetime import date, datetime
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import closes  # noqa: E402
import lab03_app as app  # noqa: E402
from test_desk import example_desk  # noqa: E402

# Made-up closes, in the shape of an export: title lines, then the header, an adjusted close beside the close.
EXPORT = """Closes export
Made-up numbers for a test
Instrument,Date,Close,Adj Close
EXM.O,10/02/2026,"1,000.50",990.00
EXM.O,10/05/2026,1002.25,991.00
EXM.O,10/06/2026,1004.75,992.00
OTHER.N,10/06/2026,55.10,55.10
"""


def sources(**values: str) -> Settings:
    """Only these settings: nothing from the environment or from .env."""
    base = {name: "" for name in ("LSEG_APP_KEY", "CLOSES_FILE", "LSEG_RICS", "LSEG_CLOSE_FIELD")}
    return Settings({**base, **values})


class Settings:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.stack = contextlib.ExitStack()

    def __enter__(self) -> None:
        self.stack.enter_context(mock.patch.object(closes, "load_dotenv", return_value={}))
        self.stack.enter_context(mock.patch.dict(closes.os.environ, self.values))

    def __exit__(self, *exc: Any) -> None:
        self.stack.close()


class FileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        (self.folder / "export.csv").write_text(EXPORT, encoding="utf-8")

    def test_the_closes_between_two_dates(self) -> None:
        with sources(CLOSES_FILE=str(self.folder / "export.csv")):
            rows = closes.daily_closes("EXM", date(2026, 10, 1), date(2026, 10, 5))
        self.assertEqual(rows, [(date(2026, 10, 2), 1000.5), (date(2026, 10, 5), 1002.25)])

    def test_a_close_counts_from_4_pm_eastern(self) -> None:
        with sources(CLOSES_FILE=str(self.folder / "export.csv")):
            self.assertEqual(closes.last_close_before("EXM", datetime(2026, 10, 6, 16, 17, 37)), (date(2026, 10, 6), 1004.75))
            self.assertEqual(closes.last_close_before("EXM", datetime(2026, 10, 6, 15, 59, 0)), (date(2026, 10, 5), 1002.25))

    def test_nothing_for_a_ticker_is_not_available(self) -> None:
        with sources(CLOSES_FILE=str(self.folder / "export.csv")):
            self.assertEqual(closes.last_close_before("NONE", datetime(2026, 10, 6, 17, 0)), closes.NOT_AVAILABLE)
        with sources():
            self.assertEqual(closes.daily_closes("EXM", date(2026, 10, 1), date(2026, 10, 6)), closes.NOT_AVAILABLE)

    def test_a_folder_of_files_named_by_ticker(self) -> None:
        (self.folder / "EXM.csv").write_text("Date,Price Close\n2026-10-06,1004.75\n", encoding="utf-8")
        (self.folder / "EXMX.csv").write_text("Date,Price Close\n2026-10-06,7.00\n", encoding="utf-8")
        with sources(CLOSES_FILE=str(self.folder)):
            self.assertEqual(closes.daily_closes("EXM", date(2026, 10, 6), date(2026, 10, 6)), [(date(2026, 10, 6), 1004.75)])

    def test_a_file_without_a_ticker_column_must_be_named_for_the_ticker(self) -> None:
        (self.folder / "closes.csv").write_text("Date,Close\n2026-10-06,1004.75\n", encoding="utf-8")
        with sources(CLOSES_FILE=str(self.folder / "closes.csv")):
            self.assertEqual(closes.daily_closes("EXM", date(2026, 10, 6), date(2026, 10, 6)), closes.NOT_AVAILABLE)


class FakeFrame:
    """The parts of a pandas DataFrame that the reader uses: a date index and one column."""

    def __init__(self, rows: list[tuple[Any, Any]]) -> None:
        self.index = [r[0] for r in rows]
        self.columns = ["Price Close"]
        self.values = [r[1] for r in rows]

    def __getitem__(self, column: str) -> list[Any]:
        return self.values


class LsegTests(unittest.TestCase):
    def test_a_desktop_session_with_the_app_key_and_the_next_suffix_after_a_miss(self) -> None:
        calls: list[tuple[Any, ...]] = []
        module = types.ModuleType("lseg.data")

        def get_history(universe: str, fields: list[str], interval: str, start: str, end: str) -> FakeFrame:
            calls.append(("history", universe, tuple(fields), interval, start, end))
            if universe.endswith(".O"):
                raise RuntimeError("Unable to resolve the identifier")
            return FakeFrame([(datetime(2026, 10, 5), 1002.25), (datetime(2026, 10, 6), float("nan")), (datetime(2026, 10, 6), 1004.75)])

        module.open_session = lambda **kw: calls.append(("open", kw))
        module.get_history = get_history
        module.close_session = lambda: calls.append(("close",))
        package = types.ModuleType("lseg")
        package.data = module
        with sources(LSEG_APP_KEY="test-app-key"), mock.patch.dict(sys.modules, {"lseg": package, "lseg.data": module}):
            found = closes.last_close_with_source("EXM", datetime(2026, 10, 6, 16, 17, 37))
        self.assertEqual(found, (date(2026, 10, 6), 1004.75, "LSEG Workspace, EXM.N TR.PriceClose"))
        self.assertEqual(calls[0], ("open", {"name": "desktop.workspace", "app_key": "test-app-key"}))
        self.assertEqual([c[1] for c in calls if c[0] == "history"], ["EXM.O", "EXM.N"])
        self.assertEqual(calls[-1], ("close",))

    def test_without_the_library_the_reader_says_how_to_install_it(self) -> None:
        err = io.StringIO()
        with sources(LSEG_APP_KEY="test-app-key"), mock.patch.dict(sys.modules, {"lseg": None, "lseg.data": None}), contextlib.redirect_stderr(err):
            self.assertEqual(closes.daily_closes("EXM", date(2026, 10, 1), date(2026, 10, 6)), closes.NOT_AVAILABLE)
        self.assertIn("python -m pip install lseg-data", err.getvalue())


class PriceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.desk = example_desk(Path(tempfile.mkdtemp()))  # its 8-K was accepted 2026-10-06 21:13:15 Eastern
        self.folder = Path(tempfile.mkdtemp())
        (self.folder / "EXM.csv").write_text("Date,Close\n2026-10-05,1002.25\n2026-10-06,1004.75\n", encoding="utf-8")

    def price(self, given: float | None = None, filed: datetime | None = None) -> tuple[float | None, str]:
        with sources(CLOSES_FILE=str(self.folder)), contextlib.redirect_stdout(io.StringIO()):
            return app.resolve_price(given, self.desk, "", filed)

    def test_the_last_close_before_the_accepted_time_is_the_price(self) -> None:
        price, note = self.price()
        self.assertEqual(price, 1004.75)
        self.assertIn("the last close before 2026-10-06 21:13:15 ET, when the release was accepted", note)

    def test_filed_overrides_the_accepted_time(self) -> None:
        price, note = self.price(filed=datetime(2026, 10, 6, 9, 30))
        self.assertEqual(price, 1002.25)
        self.assertIn("given with --filed", note)

    def test_a_price_given_by_hand_wins(self) -> None:
        self.assertEqual(self.price(given=992.13), (992.13, "$992.13, given with --price"))

    def test_the_reader_names_no_company(self) -> None:
        source = (ROOT / "closes.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b(COST|WMT|TGT|BJ|AAPL|MSFT)\b", source))


if __name__ == "__main__":
    unittest.main()
