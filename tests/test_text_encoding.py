"""Every text file is read and written as UTF-8, and the code says so at each call.

The filings, the rules, the role files and the reports are UTF-8. On Windows, Python reads and writes text in the
Windows code page unless a call names its encoding or Python runs in UTF-8 mode. Until 2026-11-22 the desk relied
on UTF-8 mode (utf8_mode.py, `-X utf8`): 345 calls named no encoding, and the required check failed on Windows when
it was run as AGENTS.md writes it (13 errors in tests, 31 in hooks/tests). This test reads the syntax tree of every
Python file and fails on a text read or write with no encoding, so the next one is caught here and not in a run.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
# .open() on these is not a text file: os.open, gzip.open(path, "rb"), pdfplumber.open, an LSEG session, a browser.
NOT_FILES = {"os", "gzip", "pdfplumber", "session", "webbrowser"}


def without_encoding(source: str) -> list[tuple[int, str]]:
    """(line, call) for each text read or write in the source that names no encoding."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
        keywords = {k.arg for k in node.keywords}
        if "encoding" in keywords or None in keywords:
            continue
        mode = next((k.value.value for k in node.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)), None)
        if name == "read_text":
            bad = not node.args
        elif name == "write_text":
            bad = len(node.args) < 2
        elif name == "open" and isinstance(f, ast.Attribute):  # path.open(mode)
            first = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
            known = not node.args or first is not None
            bad = known and not (isinstance(f.value, ast.Name) and f.value.id in NOT_FILES) and "b" not in (mode or first or "r")
        elif name == "open":  # open(file, mode)
            second = node.args[1].value if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) else None
            bad = (len(node.args) < 2 or second is not None) and "b" not in (mode or second or "r")
        elif name in {"NamedTemporaryFile", "TemporaryFile"}:
            bad = bool(mode) and "b" not in mode
        elif name in {"run", "Popen", "check_output", "check_call"} and isinstance(f, ast.Attribute) and getattr(f.value, "id", "") == "subprocess":
            bad = bool(keywords & {"text", "universal_newlines"})
        else:
            bad = False
        if bad:
            found.append((node.lineno, name))
    return found


class TextEncoding(unittest.TestCase):
    def test_the_check_sees_each_kind_of_call(self):
        bad = ("p.read_text()\np.write_text(text)\np.open('a+')\nopen(name)\nopen(name, 'w')\n"
               "tempfile.NamedTemporaryFile(mode='w')\nsubprocess.run(cmd, text=True)\n")
        self.assertEqual([name for _, name in without_encoding(bad)],
                         ["read_text", "write_text", "open", "open", "open", "NamedTemporaryFile", "run"])

    def test_the_check_passes_what_is_right_or_is_not_text(self):
        good = ("p.read_text(encoding='utf-8')\np.write_text(text, encoding='utf-8')\np.open('rb')\nopen(name, 'rb')\n"
                "os.open(path, flags)\ngzip.open(path, 'rb')\nsession.open()\np.read_bytes()\n"
                "subprocess.run(cmd, capture_output=True)\nsubprocess.run(cmd, text=True, encoding='utf-8')\n")
        self.assertEqual(without_encoding(good), [])

    def test_no_python_file_reads_or_writes_text_without_an_encoding(self):
        problems = []
        for path in sorted(ROOT.rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if relative.startswith((".venv", "venv/", "runs/", "output/", "_")) or "__pycache__" in relative:
                continue
            problems += [f"{relative}:{line}: {name}" for line, name in without_encoding(path.read_text(encoding="utf-8"))]
        self.assertEqual(problems, [], "Name the encoding at each of these calls: encoding='utf-8'")


if __name__ == "__main__":
    unittest.main()
