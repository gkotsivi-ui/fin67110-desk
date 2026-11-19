"""Local pipeline setup check. No network calls and no printed credentials or identity values."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def main():
    problems = 0
    def report(ok, text):
        nonlocal problems
        print(("ok    " if ok else "FIX   ") + text)
        problems += not ok
    report((3, 10) <= sys.version_info[:2] < (3, 14), "Use the group's Python 3.13 .venv-desk environment.")
    for name in ("crewai", "python-dotenv", "beautifulsoup4", "markdown", "pdfplumber"):
        try:
            installed = version(name)
            report(name != "crewai" or installed == "1.15.34", name + " " + installed)
        except PackageNotFoundError:
            report(False, "Install requirements-pipeline.txt: missing " + name)
    for relative in ("desk.py", "hooks/worksheet_numbers.py", "hooks/worksheet_format.py",
                     "skills/us-spinoff-seeker/scripts/seeker.py", "skills/spinoff-worksheet/scripts/worksheet.py",
                     "spinoff_factors.json", "spinoff-rules.md", "persona-why-cheap.md"):
        report((ROOT / relative).is_file(), "Local component: " + relative)
    try:
        from dotenv import dotenv_values
        config = dotenv_values(ROOT / ".env")
        for key in ("SEC_USER_AGENT", "API_KEY", "MODEL"):
            value = (config.get(key) or "").strip()
            report(bool(value) and not value.startswith(("YOUR_", "FILL")), "Set " + key + " in this repository's .env.")
        print("note  The copied worksheet supports Anthropic judgment calls. Other providers remain an inherited limitation.")
    except ImportError:
        report(False, "Install python-dotenv to check this repository's .env.")
    return int(problems > 0)


if __name__ == "__main__":
    raise SystemExit(main())
