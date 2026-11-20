"""Prove that a group-only copy imports and runs without its personal/workspace siblings."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IndependenceTests(unittest.TestCase):
    def test_cli_rejects_paths_into_another_project(self):
        import desk
        with tempfile.TemporaryDirectory() as outside:
            for flag in ['--registry', '--screen-folder', '--screen-report', '--factors',
                         '--worksheet-rules', '--persona', '--runs-root', '--replay']:
                args = desk.parser().parse_args(['ZZZZ', flag, outside])
                with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'inside this repository'):
                    desk.validate_local_options(args)

    def test_cli_defaults_stay_in_group_repository(self):
        import desk
        desk.validate_local_options(desk.parser().parse_args(['ZZZZ']))

    def test_standalone_copy_loads_local_components_and_runs_seeded_pipeline(self):
        manifest = json.loads((ROOT / 'docs/pipeline-import.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            clone = Path(temp) / 'group-only'
            clone.mkdir()
            for item in manifest['files']:
                rel = Path(item['destination'])
                if rel.parts[0] == 'tests' and rel.name != 'test_joined_desk.py':
                    continue
                source = ROOT / rel
                target = clone / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            for relative in manifest.get('group_only_files', []):
                target=clone/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/relative,target)
            script = '''
from pathlib import Path
import desk, desk_sources, desk_parts, desk_hook, equity_research_desk, equity_research_agent_team, closes_reader
root=Path.cwd().resolve()
for module in [desk,desk_sources,desk_parts,desk_hook,equity_research_desk,equity_research_agent_team,closes_reader]:
    assert Path(module.__file__).resolve().is_relative_to(root), module.__file__
for name in ['us-spinoff-seeker','spinoff-worksheet']:
    module=desk_sources.skill(name)
    assert Path(module.__file__).resolve().is_relative_to(root)
    assert module.ANALYST==root
assert desk_sources.ROOT==root and desk_sources.WORKSPACE==root
assert desk_hook.HOOK_DIR==root/'hooks'
assert closes_reader.ENV_FILE==root/'.env'
import unittest
result=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.discover('tests',pattern='test_joined_desk.py'))
assert result.wasSuccessful()
print('STANDALONE PASS')
'''
            # UTF-8 mode, as desk.py starts itself on Windows (utf8_mode.py); macOS and Linux are UTF-8 already.
            done = subprocess.run([sys.executable, '-X', 'utf8', '-c', script], cwd=clone, capture_output=True,
                                  encoding='utf-8', errors='replace', timeout=300)
            self.assertEqual(done.returncode, 0, done.stderr[-3000:])
            self.assertIn('STANDALONE PASS', done.stdout)

    def test_authored_inputs_and_personas_are_unchanged_copies(self):
        import hashlib
        manifest = json.loads((ROOT / 'docs/pipeline-import.json').read_text())
        for entry in manifest['files']:
            path = Path(entry['destination'])
            if path.name in {'spinoff_factors.json', 'spinoff-rules.md', 'persona-why-cheap.md'} or path.parts[0] == 'pipeline_roles':
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), entry['source_sha256'])
