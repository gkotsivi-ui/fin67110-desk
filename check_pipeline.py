"""Local pipeline setup check. No network calls and no printed credentials or identity values.

desk.py runs the same check of the three required settings (settings_problems) as its first step, so a run with a
wrong key or model stops before it asks SEC EDGAR or a model for anything.
"""
from importlib.metadata import PackageNotFoundError, version
import os
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REQUIRED = ("SEC_USER_AGENT", "API_KEY", "MODEL")
# The start of a model's name, and the start of a key of that provider.
PROVIDERS = {"anthropic/": "sk-ant-", "gemini/": "AIza", "openai/": "sk-"}
# The examples that README.md and .env.example print, as whole phrases. A setting that still holds one was never
# filled in. The first form of this list (2026-11-22) held short words, "fill" and "paste", and looked for them
# anywhere in a value: a member named Fillmore or Pasternak was told to write a name and email, on every run.
EXAMPLE_WORDS = ("your name", "your.email", "your model key")
MODEL_PLACEHOLDER = "model_id"
# Windows PowerShell 5.1 writes a file made with ">" as UTF-16. The base desk's reader accepts it and python-dotenv
# does not: until 2026-11-22 the group desk stopped on it with a codec error that named neither .env nor the cure.
NOT_UTF8 = (".env is not saved as UTF-8. Open it in a text editor and save it with the encoding UTF-8 "
            "(Windows PowerShell writes UTF-16 when a file is made with >).")


def read_settings(root: Path = ROOT) -> dict:
    """The desk's settings as a run reads them: the environment's value when it is not empty, or else the one in .env."""
    from dotenv import dotenv_values
    try:
        saved = dotenv_values(root / ".env")
    except UnicodeDecodeError:
        raise ValueError(NOT_UTF8) from None
    return {**{name: value for name, value in saved.items() if value is not None},
            **{name: value for name, value in os.environ.items() if value.strip()}}


def settings_problems(settings: dict) -> list[str]:
    """What is wrong with the three required settings: one line for each, saying what to write in .env.

    Until 2026-11-22 the check passed anything that was not blank: the README's own example lines, an Anthropic key
    with an OpenAI model, a model with no provider. The run then found out at its first model call, after the
    data steps. The lines name the setting and never print its value.
    """
    def value(name: str) -> str:
        return (settings.get(name) or "").strip()

    def example(text: str) -> bool:
        return any(word in text.lower() for word in EXAMPLE_WORDS)

    problems = []
    agent, key, model = value("SEC_USER_AGENT"), value("API_KEY"), value("MODEL")
    words = agent.split()
    email = [word for word in words if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", word.strip("<>(),;"))]
    if not email or len(words) < 2 or example(agent):
        problems.append("SEC_USER_AGENT in .env must hold your own name and email: SEC EDGAR asks every program for them.")
    own_server = bool(value("LLM_BASE_URL"))  # a server of your own: its model names and keys follow no provider's form
    prefix = next((start for start in PROVIDERS if model.startswith(start)), None)
    # A real key holds no space, and is more than the letters every key of its provider starts with.
    no_key = not key or example(key) or " " in key or (not own_server and key in PROVIDERS.values())
    if no_key:
        problems.append("API_KEY in .env is empty, only the start of a key, or still the example. Paste your model key.")
    if not model:
        problems.append("MODEL in .env is empty. Write the model with its provider: anthropic/MODEL_ID, gemini/MODEL_ID or openai/MODEL_ID.")
    elif own_server:
        pass
    elif prefix is None:
        problems.append("MODEL in .env must start with its provider: anthropic/, gemini/ or openai/, then a model ID your account can use.")
    elif model[len(prefix):].strip().lower() in ("", MODEL_PLACEHOLDER):
        problems.append("MODEL in .env names a provider and no model: after " + prefix + " write a model ID your account can use.")
    elif not no_key and (not key.startswith(PROVIDERS[prefix]) or (prefix == "openai/" and key.startswith("sk-ant-"))):
        problems.append(f"API_KEY and MODEL in .env are of two providers: MODEL starts with {prefix}, and that provider's keys start with {PROVIDERS[prefix]}.")
    return problems


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
    config = {}
    try:
        from dotenv import dotenv_values
        try:
            settings = read_settings()
        except ValueError as error:
            report(False, str(error))
            return 1
        config = dotenv_values(ROOT / ".env")
        found = settings_problems(settings)
        for line in found:
            report(False, line)
        if not found:
            report(True, "SEC_USER_AGENT, API_KEY and MODEL are set, and the key and the model are of one provider.")
        for name in REQUIRED:
            if os.environ.get(name) and os.environ[name].strip() != (config.get(name) or "").strip():
                print(f"note  {name} comes from this terminal's environment, not from .env: a run uses the environment's value.")
        print("note  This check asks no one: whether the key is valid, has credit and can use the model is found by the run's first model call.")
    except ImportError:
        report(False, "Install python-dotenv to check this repository's .env.")
    from check_lseg import check as check_reader
    reader = check_reader(config)
    print(('ok    ' if reader['ok'] else 'note  ') + 'Optional LSEG: ' + reader['message'])
    return int(problems > 0)


if __name__ == "__main__":
    raise SystemExit(main())
