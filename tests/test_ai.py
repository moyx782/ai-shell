import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FAKE = r'''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['AI_TEST_LOG'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\n')
if sys.argv[1] == 'models':
    print('test/model-a\ntest/model-b')
elif sys.argv[-1] == 'fail':
    print(json.dumps({'type': 'error', 'error': {'message': 'backend failed'}}))
    sys.exit(7)
else:
    print(json.dumps({'type': 'text', 'sessionID': 'ses_test', 'part': {'text': 'answer'}}))
'''


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        fake = self.directory / 'opencode'
        fake.write_text(FAKE)
        fake.chmod(0o755)
        self.log = self.directory / 'calls.jsonl'
        self.env = dict(os.environ, PATH=str(self.directory) + os.pathsep + os.environ['PATH'],
                        AI_TEST_LOG=str(self.log))

    def run_ai(self, commands, *args):
        result = subprocess.run(['python3', str(ROOT / 'bin/ai'), *args],
                                input=commands, capture_output=True, text=True,
                                env=self.env, cwd=self.directory, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_session_continuation_and_new(self):
        self.run_ai('first\nsecond\n/new\nthird\nexit\n')
        calls = self.calls()
        self.assertNotIn('--session', calls[0])
        self.assertEqual(calls[1][calls[1].index('--session') + 1], 'ses_test')
        self.assertNotIn('--session', calls[2])

    def test_model_switch_and_reset(self):
        self.run_ai('/model\n/model test/model-a\nfirst\n/model\ttest/model-b\nsecond\n/model default\nthird\nexit\n')
        calls = self.calls()
        self.assertEqual(calls[0], ['models'])
        self.assertEqual(calls[1][calls[1].index('--model') + 1], 'test/model-a')
        self.assertEqual(calls[2][calls[2].index('--model') + 1], 'test/model-b')
        self.assertIn('--session', calls[2])
        self.assertNotIn('--model', calls[3])

    def test_resume_options_and_prompt_are_preserved(self):
        output = self.run_ai('exit\n', '--session', 'ses_previous', '--model', 'test/model-a',
                             '--agent', 'build', 'a prompt with "quotes" and $(literal)')
        call = self.calls()[0]
        self.assertEqual(call[-1], 'a prompt with "quotes" and $(literal)')
        self.assertEqual(call[call.index('--session') + 1], 'ses_previous')
        self.assertIn('ai --session ses_test --model test/model-a --agent build', output)

    def test_invalid_model_and_local_command(self):
        output = self.run_ai('/model invalid\n/run printf local-ok\n/help\nexit\n')
        self.assertIn('用法：/model', output)
        self.assertIn('local-ok', output)
        self.assertFalse(self.log.exists())

    def test_backend_error_returns_to_repl(self):
        output = self.run_ai('fail\nrecover\nexit\n')
        self.assertIn('backend failed', output)
        self.assertIn('退出码：7', output)
        self.assertIn('answer', output)

    def test_cd_resets_session(self):
        destination = self.directory / 'my project'
        destination.mkdir()
        self.run_ai(f'first\n/cd "{destination}"\nsecond\nexit\n')
        self.assertNotIn('--session', self.calls()[1])

    def test_eof_and_version(self):
        self.run_ai('')
        self.assertIn('ai-shell 0.1.0', self.run_ai('', '--version'))
        self.assertFalse(self.log.exists())

    def test_install_and_upgrade_preserves_backup(self):
        target = self.directory / 'custom bin'
        target.mkdir()
        old = target / 'ai'
        old.write_text('old executable\n')
        command = ['bash', str(ROOT / 'install.sh'), '--bin-dir', str(target)]
        for _ in range(2):
            result = subprocess.run(command, capture_output=True, text=True,
                                    env=self.env, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(old.read_bytes(), (ROOT / 'bin/ai').read_bytes())
        self.assertTrue(os.access(old, os.X_OK))
        backups = list(target.glob('ai.backup-*'))
        self.assertEqual(len(backups), 2)
        self.assertIn('old executable\n', [p.read_text() for p in backups])

    def test_install_rejects_invalid_options(self):
        for args in [['--bin-dir'], ['--unknown']]:
            result = subprocess.run(['bash', str(ROOT / 'install.sh'), *args],
                                    capture_output=True, text=True, env=self.env, timeout=15)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
