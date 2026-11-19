"""The seeker's and the worksheet gate's file locks: one owner at a time, on Windows as on a Mac.

Windows has no fcntl, so both files lock with msvcrt there. Run: python -m unittest discover -s tests
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    """The fcntl that a file uses: the real module on a Mac or Linux, the msvcrt stand-in on Windows."""
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module  # a dataclass in the file looks its module up by name
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
        sys.modules.pop(name, None)
    return module.fcntl


LOCKS = {
    "seeker": ROOT / "skills" / "us-spinoff-seeker" / "scripts" / "seeker.py",
    "worksheet gate": ROOT / "hooks" / "worksheet_gate.py",
}


class FileLocks(unittest.TestCase):
    def test_a_second_owner_is_refused_until_the_first_lets_go(self) -> None:
        for name, path in LOCKS.items():
            with self.subTest(name):
                fcntl = load(f"lock_test_{name.replace(' ', '_')}", path)
                lock_path = Path(tempfile.mkdtemp()) / ".run.lock"
                with lock_path.open("a+") as first, lock_path.open("a+") as second:
                    fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with self.assertRaises(BlockingIOError):  # what the seeker catches: "A seeker run already owns this registry."
                        fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(first, fcntl.LOCK_UN)
                    fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)  # free again
                    fcntl.flock(second, fcntl.LOCK_UN)

    def test_the_owner_reads_and_rewrites_the_file_it_locked(self) -> None:
        # The seeker's pause between SEC requests keeps the last request's time in the locked file.
        fcntl = load("lock_test_rate_gate", LOCKS["seeker"])
        path = Path(tempfile.mkdtemp()) / ".sec_rate_gate"
        with path.open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            self.assertEqual(stream.read(), "")
            stream.seek(0)
            stream.truncate()
            stream.write("1234.5")
            stream.flush()
            fcntl.flock(stream, fcntl.LOCK_UN)
        self.assertEqual(path.read_text(), "1234.5")


if __name__ == "__main__":
    unittest.main()
