"""Names and report identities shared by full runs and verification runs."""
import json
import re
from datetime import datetime
from pathlib import Path


def company_name(company: str) -> str:
    return re.sub(r'[/:\\\x00-\x1f,]', '_', company).strip() or 'company'


def report_runs(root: Path, company: str) -> list[Path]:
    legacy = re.sub(r'[^A-Za-z0-9._-]+', '_', company).strip('_') or 'company'
    runs = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        metadata = path / 'run_identity.json'
        if metadata.exists():
            data = json.loads(metadata.read_text())
            if data.get('company') == company and data.get('kind') == 'report':
                runs.append(path)
        elif path.name.startswith(legacy + '_') and re.fullmatch(
            re.escape(legacy) + r'_\d{8}_\d{6}(?:_\d{2})?', path.name
        ) and any((path / name).exists() for name in ('report.md', 'equity_research_report.md')):
            runs.append(path)
    return sorted(runs, key=lambda p: p.name)


def report_number(source: Path, root: Path, company: str) -> int:
    metadata = source / 'run_identity.json'
    if metadata.exists():
        return int(json.loads(metadata.read_text())['report_number'])
    runs = report_runs(root, company)
    if source in runs:
        return runs.index(source) + 1
    raise ValueError('Source report has no report identity. Use an original report folder.')


def create_run(root: Path, company: str, started: datetime, kind: str,
               number: int | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if number is None:
        runs = report_runs(root, company)
        numbers = [report_number(p, root, company) for p in runs]
        number = max(numbers, default=0) + 1
    base = f'{company_name(company)}, {started:%Y-%m-%d}, {started:%H-%M-%S}, {kind} {number}'
    for suffix in range(1000):
        target = root / (base if suffix == 0 else f'{base} ({suffix + 1})')
        try:
            target.mkdir()
        except FileExistsError:
            continue
        (target / 'run_identity.json').write_text(json.dumps({
            'company': company, 'report_number': number, 'kind': kind,
            'run_time': started.isoformat(timespec='seconds'),
        }, indent=2) + '\n')
        return target
    raise RuntimeError('Could not create a unique run folder')
