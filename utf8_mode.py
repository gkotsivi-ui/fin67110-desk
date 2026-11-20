"""Run a program of this desk in Python's UTF-8 mode on Windows.

The filings, the rules, the role files and the reports are UTF-8. Without UTF-8 mode, Python on Windows reads
and writes text in the Windows code page: on 2026-11-19 the worksheet's rule "owner cash flow ÷ 10%" stopped
matching its own pattern, and the worksheet failed. Python 3.15 makes UTF-8 mode the default. Until then, a
program started without it starts itself again with it, and PYTHONUTF8 passes it on to every process it starts.
macOS and Linux are left as they are: their text is UTF-8 already.

Ctrl+C, or closing the window, stops both processes. A tool that stops the first process from outside leaves
the second one running, so a launcher or a supervisor should start Python in UTF-8 mode itself: `-X utf8`,
or PYTHONUTF8=1, as start_page.bat and page.py do.
"""
import os
import subprocess
import sys


def ensure():
    """Call first, and only when the program is started as a program, not when a test imports it."""
    if os.name != "nt" or sys.flags.utf8_mode:
        return
    os.environ["PYTHONUTF8"] = "1"
    try:
        code = subprocess.call([sys.executable, *sys.orig_argv[1:]])
    except KeyboardInterrupt:
        code = 130
    raise SystemExit(code)
