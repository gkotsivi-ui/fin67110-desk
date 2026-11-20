"""Paths that differ between Windows and a Mac. On 2026-11-19 the LSEG worker pointed at a Mac path on Windows.

Run: python -m unittest discover -s tests
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import closes_reader  # noqa: E402


class LsegWorkerPython(unittest.TestCase):
    def test_the_default_worker_python_is_this_systems_own(self) -> None:
        path = closes_reader.lseg_python()
        self.assertEqual(path.parent.parent.name, ".venv-lseg")
        if os.name == "nt":
            self.assertEqual((path.parent.name, path.name), ("Scripts", "python.exe"))
        else:
            self.assertEqual((path.parent.name, path.name), ("bin", "python"))

    def test_each_system_gets_its_own_layout(self) -> None:
        self.assertEqual(closes_reader.lseg_python("nt").parts[-2:], ("Scripts", "python.exe"))
        self.assertEqual(closes_reader.lseg_python("posix").parts[-2:], ("bin", "python"))


if __name__ == "__main__":
    unittest.main()
