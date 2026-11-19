#!/usr/bin/env python3
"""Audit the saved Markdown, offline. Unclassified numeric tokens fail closed.

Evidence annotations belong in the worksheet next to the actual claim, never
in an audit manifest. See README.md for the deliberately small syntax.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext, ROUND_CEILING
import json
from pathlib import Path
import re
import shlex
import sys

NUMBER = r'[+−-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?%?'
# Do not hide digits embedded in arbitrary words: an unrecognized token fails.
NUM = re.compile(NUMBER)
ANNOTATION = re.compile(r'\[(fact|filing|rule|reader|calc)\s+([^\]\n]+)\]')
DATE = re.compile(r'\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?\b')
ACCESSION = re.compile(r'\b\d{10}-\d{2}-\d{6}\b')
TEXT_DATE = re.compile(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b', re.I)
NAMED_ID = re.compile(r'\b(?:accession\s*[:=]?\s*\d{18}|line\s*[:=]?\s*\d+|L\d+)\b', re.I)
LINE_REF = re.compile(r'\[(?P<file>[^\]\n]+?\.txt):L(?P<line>\d+)\]')
WORD_NUMBER = re.compile(r'\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion)\b', re.I)
FORM_ID = re.compile(r'\bForm\s*(?:10-K|10-Q|10|20-F|40-F|6-K|8-K|S-1|S-3|S-4|F-1|F-3|F-4|13F|13D|13G|144|3|4|5)(?:/A)?\b', re.I)
PERIOD_ID = re.compile(r'\b(?:(?:fiscal\s+year|FY)\s*\d{4}|Q[1-4](?:\s+\d{4})?)\b', re.I)
LABEL_ID = re.compile(r'\b(?:criterion|chapter|section|table|figure)\s+\d+\b', re.I)
FINANCIAL_CONTEXT = re.compile(r'\b(?:earnings|income|revenue|cash|debt|price|cost|capex|spending|profit|assets|liabilities|shares|volume|rate|weight|score|valuation|dividend|yield|margin)\b', re.I)
FINANCIAL_UNIT = re.compile(r'^\s*(?:dollars?|USD|EUR|GBP|cents?|percent|percentage|shares?|basis\s+points?)\b', re.I)


def financial_word_numbers(line):
    """Check spelled amounts in financial context, not logical prose counts."""
    words = list(WORD_NUMBER.finditer(line))
    groups = []
    for word in words:
        if groups and re.fullmatch(r'[\s-]+', line[groups[-1][-1].end():word.start()]):
            groups[-1].append(word)
        else:
            groups.append([word])
    for group in groups:
        start, end = group[0].start(), group[-1].end()
        # A sentence/semicolon boundary prevents unrelated financial prose from
        # turning "at least one" later in the sentence into a financial amount.
        prefix = re.split(r'[.;:!?]', line[:start])[-1]
        prefix = prefix[-50:]
        logical = bool(re.search(r'\b(?:at least|at most|any|each|either|only)\s*$', prefix, re.I))
        if FINANCIAL_UNIT.match(line[end:]) or (FINANCIAL_CONTEXT.search(prefix) and not logical):
            yield from group


def amount(text):
    value = Decimal(str(text).replace(',', '').replace('−', '-').removesuffix('%'))
    if not value.is_finite():
        raise ValueError('Nonfinite number')
    return value / 100 if str(text).endswith('%') else value


def rounded_equal(printed, expected):
    """Only calculated results may round, to the last printed decimal place."""
    raw = printed.replace(',', '').replace('−', '-').removesuffix('%')
    shown = Decimal(raw)
    target = expected * 100 if printed.endswith('%') else expected
    quantum = Decimal(1).scaleb(shown.as_tuple().exponent)
    with localcontext() as ctx:
        ctx.prec = 100
        return shown == target.quantize(quantum)


def within(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Source path leaves its allowed directory')
    return path


def options(text):
    result = {}
    for item in shlex.split(text):
        key, sep, value = item.partition('=')
        if not sep or key in result:
            raise ValueError('Use unique key=value fields in an evidence annotation')
        result[key] = value
    return result


def strict_keys(data, required, optional=()):
    if not set(required) <= data.keys() or data.keys() - set(required) - set(optional):
        raise ValueError('Missing or unsupported evidence fields')


def literal_numbers(text):
    return [amount(m[0]) for m in NUM.finditer(text)]


def evaluate(expression, values):
    """Arithmetic on earlier verified, named worksheet inputs; no bare literals."""
    tree = ast.parse(expression, mode='eval')
    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            args = [visit(x) for x in node.args]
            if not args: raise ValueError('Calculation has no printed inputs')
            if node.func.id == 'median':
                ordered = sorted(args)
                middle = len(ordered)//2
                return ordered[middle] if len(ordered)%2 else (ordered[middle-1]+ordered[middle])/2
            if node.func.id == 'count': return Decimal(len(args))
            if node.func.id == 'ceil' and len(args) == 1:
                return args[0].to_integral_value(rounding=ROUND_CEILING)
        raise ValueError('Calculation needs earlier verified worksheet input names; no bare constants')
    with localcontext() as ctx:
        ctx.prec = 60
        return visit(tree)


@dataclass
class Failure:
    path: Path
    line: int
    text: str
    reason: str

    def __str__(self):
        return f'{self.path}:{self.line}: {self.reason}\n{self.text}'


class Auditor:
    def __init__(self, run, workspace):
        self.run = Path(run).resolve()
        self.workspace = Path(workspace).resolve()
        self.values = {}

    def source(self, kind, args, printed):
        value = amount(printed)
        if kind == 'fact':
            strict_keys(args, ('tag', 'period'), ('start',))
            facts = json.loads((self.run / 'facts.json').read_text(), parse_float=Decimal)
            matches = []
            for row in facts.get('facts', {}).values():
                if not isinstance(row, dict) or row.get('tag') != args['tag']: continue
                for prefix in ('', 'prior_'):
                    if row.get(prefix + 'period_end') != args['period']: continue
                    if 'start' in args and row.get(prefix + 'period_start') != args['start']: continue
                    x = row.get(prefix + 'value')
                    if x is not None and not isinstance(x, bool): matches.append(Decimal(str(x)))
            if not matches or set(matches) != {value}:
                raise ValueError('No exact, unambiguous tag/period/value match in facts.json')
        elif kind in ('filing', 'rule'):
            strict_keys(args, ('path', 'line'), ('literal',))
            root = self.run if kind == 'filing' else self.workspace
            path = within(root, args['path'])
            if kind == 'rule':
                allowed = {self.workspace / 'spinoff-rules.md', self.workspace / 'persona-why-cheap.md'}
                if path not in {p.resolve() for p in allowed} and not (path.is_relative_to(self.workspace / 'skills/spinoff-worksheet') and path.suffix == '.md'):
                    raise ValueError('Rate or weight source is not an authored skill/rules file')
            lines = path.read_text().splitlines()
            index = int(args['line']) - 1
            if not 0 <= index < len(lines): raise ValueError('Source line does not exist')
            if 'literal' in args:
                literal = args['literal']
                if not re.fullmatch(NUMBER, literal) or amount(literal) != value:
                    raise ValueError('Source literal differs from the worksheet number')
                if literal not in [m[0] for m in NUM.finditer(lines[index])]:
                    raise ValueError('Exact literal is absent from the cited source line')
            elif value not in literal_numbers(lines[index]):
                raise ValueError('Number is absent from the exact cited source line')
        elif kind == 'reader':
            strict_keys(args, ('path', 'ticker', 'date', 'field'))
            if args['field'] not in ('close', 'volume'): raise ValueError('Unsupported reader field')
            path = within(self.run, args['path'])
            if path.name.startswith('Spinoff worksheet') or 'model' in path.name.lower():
                raise ValueError('Price/volume must cite saved reader output, not worksheet/model output')
            data = json.loads(path.read_text(), parse_float=Decimal)
            rows = data if isinstance(data, list) else data.get('rows', [data])
            matches = [r.get(args['field']) for r in rows if r.get('ticker') == args['ticker'] and r.get('date') == args['date']]
            if len(matches) != 1 or matches[0] is None or isinstance(matches[0], bool) or Decimal(str(matches[0])) != value:
                raise ValueError('No unique exact price/volume match in saved reader output')
        elif kind == 'calc':
            strict_keys(args, ('expr',))
            expected = evaluate(args['expr'], self.values)
            if not rounded_equal(printed, expected): raise ValueError('Printed calculation does not equal its printed inputs')
        else:
            raise ValueError('Unsupported numeric claim')
        return value

    def check(self, worksheet):
        self.values = {}
        failures = []
        text = worksheet.read_text()
        if not text.strip():
            return [Failure(worksheet, 1, '', 'Worksheet is empty')]
        from worksheet_format import WorksheetFormat
        try:
            native = WorksheetFormat(self.run, self.workspace, worksheet, text)
        except Exception as error:
            native = None
            failures.append(Failure(worksheet, 1, text.splitlines()[0], 'Cannot interpret worksheet format: '+str(error)))
        for lineno, line in enumerate(text.splitlines(), 1):
            covered = [False] * len(line)
            def cover(start, end): covered[start:end] = [True] * (end-start)
            # Only validated identifier shapes are skipped. Years alone are claims.
            for m in DATE.finditer(line):
                try:
                    datetime.fromisoformat(m[0].replace('Z', '+00:00'))
                except ValueError:
                    continue
                cover(*m.span())
            for m in ACCESSION.finditer(line): cover(*m.span())
            for m in NAMED_ID.finditer(line): cover(*m.span())
            for pattern in (FORM_ID, PERIOD_ID, LABEL_ID):
                for m in pattern.finditer(line): cover(*m.span())
            enumeration = re.match(r'^\s*\d+[.)]\s+', line)
            if enumeration: cover(*enumeration.span())
            for m in TEXT_DATE.finditer(line):
                try:
                    datetime.strptime(re.sub(r'\s+', ' ', m[0]), '%B %d, %Y')
                except ValueError:
                    continue
                cover(*m.span())
            # Filing names and line numbers are source identifiers, never amounts.
            for m in LINE_REF.finditer(line): cover(*m.span())
            if native:
                spans, errors = native.result(lineno)
                for start, end in spans: cover(start, end)
                for error in errors: failures.append(Failure(worksheet, lineno, line, error))
            for annotation in ANNOTATION.finditer(line):
                cover(*annotation.span())
                before = line[:annotation.start()]
                claim = re.search('('+NUMBER+r')\s*$', before)
                if not claim:
                    failures.append(Failure(worksheet, lineno, line, 'Evidence annotation has no adjacent numeric claim'))
                    continue
                cover(*claim.span(1))
                try:
                    binding = re.search(r'\b([a-zA-Z_]\w*)\s*=\s*$', before[:claim.start(1)])
                    label = binding[1].lower() if binding else before[:claim.start(1)].strip().lower().rstrip(':').strip()
                    if re.search(r'(?:^|_)(?:rate|weight)(?:_|$)', label) and annotation[1] != 'rule':
                        raise ValueError('A rate or weight must cite the authored skill/rules file')
                    if (label in ('price','market_price','close') or label.startswith('close_')) and annotation[1] != 'reader':
                        raise ValueError('A market price must cite saved reader output')
                    value = self.source(annotation[1], options(annotation[2]), claim[1])
                    if binding:
                        name = binding[1]
                        if name in self.values: raise ValueError('Duplicate worksheet input name: '+name)
                        self.values[name] = value
                except Exception as error:
                    failures.append(Failure(worksheet, lineno, line, str(error)))
            # Existing citation style: accept only amounts actually on that line.
            # No adjacent-line guessing or unproved unit conversion is permitted.
            refs = list(LINE_REF.finditer(line))
            for match in NUM.finditer(line):
                if all(covered[match.start():match.end()]): continue
                reason = 'Number has no supported source or calculation: '+match[0]
                legacy_label = line.split('|', 1)[0].lower()
                special = re.search(r'price|close|rate|weight|\btag\b', legacy_label)
                if len(refs) == 1 and '|' in line and not special:
                    ref = refs[0]
                    try:
                        self.source('filing', {'path':ref['file'], 'line':ref['line']}, match[0])
                        cover(*match.span())
                        continue
                    except (ValueError, OSError, ArithmeticError) as error:
                        reason = str(error)+': '+match[0]
                failures.append(Failure(worksheet, lineno, line, reason))
            for match in financial_word_numbers(line):
                if not all(covered[match.start():match.end()]):
                    failures.append(Failure(worksheet, lineno, line, 'Spelled-out number needs an explicit sourced numeric claim: '+match[0]))
        return failures


def audit_paths(paths, workspace):
    failures = []
    for path in paths:
        try:
            failures.extend(Auditor(path.parent, workspace).check(path))
        except (OSError, ValueError, TypeError) as error:
            failures.append(Failure(path, 1, '', 'Cannot audit worksheet: '+str(error)))
    return failures


def failure_report(failures):
    """Print each failed original line once, with all reasons for that line."""
    grouped = {}
    for failure in failures:
        key = (failure.path, failure.line, failure.text)
        grouped.setdefault(key, [])
        if failure.reason not in grouped[key]: grouped[key].append(failure.reason)
    return '\n'.join(f'{path}:{line}: '+ '; '.join(reasons)+'\n'+text
                     for (path, line, text), reasons in grouped.items())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--worksheet', type=Path, help='One worksheet filename within the run; default: all saved worksheets')
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        paths = [within(args.run, args.worksheet)] if args.worksheet else sorted(args.run.glob('Spinoff worksheet*.md'))
        if not paths: raise ValueError('No saved worksheet found in the run')
        failures = audit_paths(paths, args.workspace)
    except (ValueError, OSError) as error:
        print('FAIL: '+str(error), file=sys.stderr)
        return 1
    if failures: print(failure_report(failures), file=sys.stderr)
    print(f'{"FAIL" if failures else "PASS"}: {len(paths)} worksheet(s), {len(failures)} failed check(s)')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
