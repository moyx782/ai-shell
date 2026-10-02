import json
import os
import pty
import select
import signal
import time
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
elif sys.argv[-1] == 'wait':
    import time
    print(json.dumps({'type':'text','sessionID':'ses_test','part':{'text':'backend-started'}}), flush=True)
    time.sleep(5)
else:
    print(json.dumps({'type': 'text', 'sessionID': 'ses_test', 'part': {'text': 'answer'}}))
'''


class ShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build_dir.cleanup)
        cls.executable = os.environ.get('AI_TEST_EXECUTABLE')
        if not cls.executable:
            cls.executable = str(Path(cls.build_dir.name) / 'ai')
            subprocess.run(['go', 'build', '-o', cls.executable, './cmd/ai'],
                           cwd=ROOT, env=dict(os.environ, CGO_ENABLED='0'), check=True)

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
        result = subprocess.run([self.executable, *args],
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
        self.assertIn('7', output)
        self.assertIn('answer', output)

    def test_cd_resets_session(self):
        destination = self.directory / 'my project'
        destination.mkdir()
        self.run_ai(f'first\n/cd "{destination}"\nsecond\nexit\n')
        self.assertNotIn('--session', self.calls()[1])

    def test_eof_and_version(self):
        self.run_ai('')
        self.assertIn('ai-shell 0.2.0', self.run_ai('', '--version'))
        self.assertFalse(self.log.exists())

    def test_install_and_upgrade_preserves_backup(self):
        target = self.directory / 'custom bin'
        target.mkdir()
        old = target / 'ai'
        old.write_text('old executable\n')
        command = ['bash', str(ROOT / 'install.sh'), '--bin-dir', str(target), '--binary', self.executable]
        for _ in range(2):
            result = subprocess.run(command, capture_output=True, text=True,
                                    env=self.env, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(old.read_bytes(), Path(self.executable).read_bytes())
        self.assertTrue(os.access(old, os.X_OK))
        backups = list(target.glob('ai.backup-*'))
        self.assertEqual(len(backups), 2)
        self.assertIn(b'old executable\n', [p.read_bytes() for p in backups])

    def test_install_rejects_invalid_options(self):
        for args in [['--bin-dir'], ['--binary'], ['--unknown']]:
            result = subprocess.run(['bash', str(ROOT / 'install.sh'), *args],
                                    capture_output=True, text=True, env=self.env, timeout=15)
            self.assertEqual(result.returncode, 2)

    def test_plan_build_switch_preserves_session(self):
        output = self.run_ai('/plan\nfirst\n/build implement it\n/plan review it\nexit\n')
        calls = self.calls()
        self.assertEqual([c[c.index('--agent') + 1] for c in calls], ['plan', 'build', 'plan'])
        self.assertEqual(calls[1][-1], 'implement it')
        for call in calls[1:]:
            self.assertEqual(call[call.index('--session') + 1], 'ses_test')
        self.assertIn('ai[plan]>', output)
        self.assertIn('ai[build]>', output)
        self.assertIn('ai --session ses_test --agent plan', output)

    def test_plan_startup_and_new_preserve_agent(self):
        self.run_ai('/new\nsecond\nexit\n', '--plan', 'first')
        for call in self.calls():
            self.assertEqual(call[call.index('--agent') + 1], 'plan')
            self.assertNotIn('--session', call)

    def test_plan_status_and_no_implicit_request(self):
        output = self.run_ai('/plan\n/status\nexit\n')
        self.assertIn('Agent：plan', output)
        self.assertFalse(self.log.exists())

    def test_no_python_or_node_on_path(self):
        fake = self.directory / 'opencode'
        fake.write_text('#!/bin/sh\nprintf \'%s\\n\' \'{"type":"text","sessionID":"ses_native","part":{"text":"native-ok"}}\'\n')
        output = subprocess.run([self.executable, '--plan'], input='hello\nexit\n',
                                env=dict(self.env, PATH=str(self.directory)),
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn('native-ok', output.stdout)
        self.assertIn('ai --session ses_native --agent plan', output.stdout)

    def test_model_request_passes_plain_prompt(self):
        self.run_ai('$(touch injected); echo nope\nexit\n')
        self.assertEqual(self.calls()[0][-1], '$(touch injected); echo nope')
        self.assertFalse((self.directory / 'injected').exists())

    def test_ctrl_c_returns_to_repl_in_real_terminal(self):
        pid, fd = pty.fork()
        if pid == 0:
            os.execve(self.executable, [self.executable], self.env)
        def receive(marker):
            output = b''
            deadline = time.monotonic() + 4
            while marker not in output and time.monotonic() < deadline:
                if select.select([fd], [], [], 0.1)[0]:
                    output += os.read(fd, 65536)
            self.assertIn(marker, output)
            return output
        try:
            receive(b'ai> ')
            os.write(fd, b"/run printf '\\nLOCAL-READY\\n'; sleep 5\n")
            receive(b'\r\nLOCAL-READY\r\n')
            os.write(fd, b'\x03')
            receive(b'ai> ')
            os.write(fd, b'wait\n')
            receive(b'backend-started')
            os.write(fd, b'\x03')
            receive(b'ai> ')
            os.write(fd, b'exit\n')
        finally:
            os.close(fd)
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
            os.waitpid(pid, 0)

    def test_download_verification_and_progress_options(self):
        curl = self.directory / 'curl'
        curl.write_text('''#!/usr/bin/env python3
import hashlib, os, pathlib, shutil, sys
args = sys.argv[1:]
assert '--silent' not in args and '-s' not in args
target = pathlib.Path(args[args.index('--output')+1])
source = pathlib.Path(os.environ['AI_INSTALL_SOURCE'])
if args[-1].endswith('SHA256SUMS'):
    digest = '0'*64 if os.environ.get('AI_BAD_HASH') else hashlib.sha256(source.read_bytes()).hexdigest()
    target.write_text(''.join(digest+'  ai-'+platform+'\\n' for platform in ['linux-amd64','linux-arm64','darwin-amd64','darwin-arm64']))
else: shutil.copyfile(source, target)
''')
        curl.chmod(0o755)
        for bad in (False, True):
            with self.subTest(bad_checksum=bad):
                target = self.directory / ('bad-install' if bad else 'good-install')
                target.mkdir()
                (target / 'ai').write_text('original')
                env = dict(self.env, AI_INSTALL_SOURCE=self.executable)
                if bad: env['AI_BAD_HASH'] = '1'
                result = subprocess.run(['bash', str(ROOT/'install.sh'), '--bin-dir', str(target)],
                                        env=env, text=True, capture_output=True, timeout=15)
                if bad:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual((target/'ai').read_text(), 'original')
                    self.assertIn('SHA256 mismatch', result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('SHA256 verified', result.stdout)


if __name__ == '__main__':
    unittest.main()
