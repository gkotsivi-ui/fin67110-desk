#!/usr/bin/env python3
"""Save your settings into .env without editing the file: paste each one at the prompt."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
ENV = HERE / ".env"
EXAMPLE = HERE / ".env.example"
# Each setting: its name, what to paste, and the check a pasted value must pass (None: any value).
KEYS: list[tuple[str, str, Callable[[str], str | None] | None]] = [
    ("SEC_USER_AGENT", "name and email for SEC EDGAR, as in Your Name your.email@purdue.edu",
     lambda v: None if "@" in v else "it has no email"),
    ("API_KEY", "Anthropic API key (it starts with sk-ant-) or Google AI Studio key (it starts with AIza)",
     lambda v: None if v.startswith(("sk-ant-", "AIza")) else "it does not start with sk-ant- or AIza"),
    ("FINANCIAL_DATASETS_API_KEY", "class financialdatasets.ai key", None),
]


def read(path: Path) -> str:
    """The file's text; UTF-16 too, as Windows PowerShell 5.1 writes it."""
    data = path.read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    return data.decode("utf-8-sig", errors="replace")


def save(name: str, value: str) -> None:
    """Replace or add one NAME=value line, reading .env fresh so other lines stay as they are.
    A new .env starts as a copy of .env.example."""
    source = ENV if ENV.exists() else EXAMPLE
    lines = read(source).splitlines() if source.exists() else []
    found = [i for i, line in enumerate(lines) if line.strip().startswith(f"{name}=")]
    if found:
        lines[found[0]] = f"{name}={value}"
    else:
        lines.append(f"{name}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    print(f"This saves into {ENV}. Press Enter to skip a setting and keep what .env has.")
    for name, prompt, check in KEYS:
        # Visible on purpose: a hidden prompt looks as if typing does not work.
        value = input(f"\nPaste your {prompt}, then press Enter:\n> ").strip()
        if not value:
            print(f"  {name}: skipped")
            continue
        problem = check(value) if check else None
        if problem:
            print(f"  {name}: not saved, because {problem}")
            continue
        save(name, value)
        print(f"  {name}: saved ({value if name == 'SEC_USER_AGENT' else value[:4] + '...'})")
    print("\nDone. .env is listed in .gitignore, so these values never reach GitHub. Check the setup: python check_env.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
