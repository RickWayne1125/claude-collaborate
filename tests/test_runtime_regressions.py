"""Independent regressions: only synthetic processes, settings, and session state."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "skills" / "claude-collaborate" / "scripts" / "claude_session.py"
spec = importlib.util.spec_from_file_location("claude_runtime_regression_helper", HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class RuntimeRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claude-runtime-regression-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        self.config_dir = self.root / "claude-config"
        self.config_dir.mkdir()
        self.state_root = self.root / "state"
        self.config = copy.deepcopy(helper.BUILTIN_CONFIG)
        self.config["state_dir"] = str(self.state_root)

    def test_sandbox_policy_without_enabled_cannot_be_discarded(self):
        settings_dir = self.project / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text(json.dumps({
            "sandbox": {"filesystem": {"denyRead": ["./private-research"]}}
        }), encoding="utf-8")
        with self.assertRaises(helper.SessionError) as caught:
            helper.build_policy(self.project, self.config_dir, self.state_root, self.config)
        self.assertEqual(caught.exception.code, "unsupported_sandbox_policy")

    @unittest.skipUnless(os.name == "posix", "Windows uses profile ACLs, not POSIX permission bits")
    def test_existing_state_directory_must_not_be_world_readable(self):
        self.state_root.mkdir(mode=0o700)
        self.state_root.chmod(0o755)
        with self.assertRaises(helper.SessionError) as caught:
            helper.ensure_private_dir(self.state_root)
        self.assertEqual(caught.exception.code, "unsafe_state_permissions")

    @unittest.skipUnless(os.name == "posix", "Windows uses profile ACLs, not POSIX permission bits")
    def test_existing_secret_key_must_not_be_world_readable(self):
        self.state_root.mkdir(mode=0o700)
        secret = self.state_root / "secret.key"
        secret.write_bytes(b"x" * 32)
        secret.chmod(0o644)
        with self.assertRaises(helper.SessionError) as caught:
            helper.read_private_file(secret, 64)
        self.assertEqual(caught.exception.code, "unsafe_state_permissions")

    @unittest.skipUnless(os.name == "posix", "Windows uses profile ACLs, not POSIX permission bits")
    def test_existing_state_file_must_not_be_world_readable(self):
        self.state_root.mkdir(mode=0o700)
        state = self.state_root / "state.json"
        state.write_text("{}", encoding="utf-8")
        state.chmod(0o644)
        with self.assertRaises(helper.SessionError) as caught:
            helper.read_private_file(state, 65536)
        self.assertEqual(caught.exception.code, "unsafe_state_permissions")

    def test_parentheses_in_valid_permission_anchor_are_supported(self):
        for windows, anchor, expected in (
            (False, "/tmp/project (review)", "Read(//tmp/project (review)/private/**)"),
            (True, "C:\\Users\\Example\\Project (review)", "Read(//c/Users/Example/Project (review)/private/**)"),
        ):
            with self.subTest(windows=windows):
                result = helper.normalize_rule("Read(/private/**)", "project", anchor, windows=windows)
                self.assertEqual(result, expected)

    def test_inherited_mcp_wildcard_deny_is_preserved(self):
        (self.config_dir / "settings.json").write_text(
            json.dumps({"permissions": {"deny": ["mcp__*"]}}), encoding="utf-8")
        policy = helper.build_policy(self.project, self.config_dir, self.state_root, self.config)
        self.assertIn("mcp__*", policy["settings"]["permissions"]["deny"])

    def test_windows_lock_reparse_metadata_is_rejected(self):
        # Exercise the guard using synthetic metadata; native Windows CI is separate.
        lock = self.root / "reparse.lock"
        lock.touch(mode=0o600)
        info = lock.stat()
        reparse_info = argparse.Namespace(st_mode=info.st_mode, st_file_attributes=helper.FILE_ATTRIBUTE_REPARSE_POINT)
        with mock.patch.object(helper, "IS_WINDOWS", True), \
                mock.patch.object(helper.os, "lstat", return_value=reparse_info):
            with self.assertRaises(helper.SessionError) as caught:
                with helper.file_lock(lock):
                    self.fail("A reparse lock file was accepted")
        self.assertEqual(caught.exception.code, "unsafe_state_path")

    def test_successful_process_closes_owned_pipes(self):
        fake = self.root / "successful_fake.py"
        fake.write_text("import sys; sys.stdin.buffer.read(); print('{\"type\":\"result\"}')", encoding="utf-8")
        created = []
        real_popen = subprocess.Popen
        def track_popen(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            created.append(process)
            return process
        try:
            with mock.patch.object(helper.subprocess, "Popen", side_effect=track_popen):
                helper.run_claude([sys.executable, "-B", str(fake)], self.project, dict(os.environ), b"fixture", 3, 65536)
            self.assertEqual(len(created), 1)
            self.assertTrue(created[0].stdin.closed)
            self.assertTrue(created[0].stdout.closed, "Successful calls leaked their owned stdout pipe")
        finally:
            for process in created:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        stream.close()

    def test_windows_exited_parent_does_not_claim_verified_tree_cleanup(self):
        # Unit-test the decision only; this is not native Windows execution.
        process = mock.Mock()
        process.pid = 99999
        process.poll.return_value = 0
        process.wait.return_value = 0
        runner = mock.Mock()
        result = helper.terminate_tree(process, windows=True, runner=runner,
                                       environ={"SYSTEMROOT": "C:\\Windows"})
        self.assertEqual(result, "incomplete")
        runner.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "Exercises real POSIX process groups; Windows needs native CI")
    def test_finished_parent_cannot_escape_deadline_with_live_descendant(self):
        fake = self.root / "fake_cli.py"
        ready = self.root / "descendant-ready"
        stopped = self.root / "descendant-stopped"
        parent_pid_file = self.root / "parent-pid"
        child_pid_file = self.root / "child-pid"
        child_source = (
            "import pathlib,signal,sys,time; "
            "ready=pathlib.Path(sys.argv[1]); stopped=pathlib.Path(sys.argv[2]); "
            "signal.signal(signal.SIGTERM,lambda *a:(stopped.write_text('stopped'),sys.exit(0))); "
            "ready.write_text('ready'); time.sleep(30)"
        )
        fake.write_text(
            "import json,os,pathlib,subprocess,sys,time\n"
            "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
            f"child=subprocess.Popen([sys.executable,'-c',{child_source!r},sys.argv[3],sys.argv[4]])\n"
            "pathlib.Path(sys.argv[2]).write_text(str(child.pid))\n"
            "deadline=time.monotonic()+5\n"
            "while not pathlib.Path(sys.argv[3]).exists() and time.monotonic()<deadline: time.sleep(.01)\n"
            "print(json.dumps({'type':'result','subtype':'success','is_error':False}),flush=True)\n",
            encoding="utf-8",
        )
        command = [sys.executable, "-B", str(fake), str(parent_pid_file), str(child_pid_file), str(ready), str(stopped)]
        started = time.monotonic()
        error = None
        created_processes = []
        real_popen = subprocess.Popen
        def track_popen(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            created_processes.append(process)
            return process
        try:
            try:
                with mock.patch.object(helper.subprocess, "Popen", side_effect=track_popen):
                    helper.run_claude(command, self.project, dict(os.environ), b"request\r\n", 1, 65536)
            except helper.SessionError as exc:
                error = exc
            elapsed = time.monotonic() - started
            self.assertTrue(ready.exists(), "Synthetic descendant did not start")
            # A successful return must not leave a descendant holding stdout alive.
            # A timed-out call must stop that same owned process group as well.
            self.assertTrue(stopped.exists(), "A descendant survived run_claude's return/error")
            if error is None:
                self.assertLess(elapsed, 1.9, "The fixed two-second stdout wait bypassed the one-second deadline")
            else:
                self.assertIn(error.code, {"timeout", "cleanup_incomplete", "descendants_running"})
        finally:
            # Both processes were created by this test; never touch other groups.
            if parent_pid_file.exists():
                try:
                    os.killpg(int(parent_pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if child_pid_file.exists():
                try:
                    os.kill(int(child_pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

            for process in created_processes:
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        stream.close()

    @unittest.skipUnless(os.name == "posix", "Exercises a real legacy flock held by another process")
    def test_migrated_send_respects_legacy_session_lock(self):
        legacy_dir = self.project / ".claude"
        legacy_dir.mkdir()
        legacy_lock = legacy_dir / "codex-collaborate.lock"
        legacy_lock.touch()
        session_id = str(uuid.uuid4())
        legacy_data = json.dumps({
            "version": 1, "project": str(self.project), "history": [],
            "active": {"topic": "topic", "session_id": session_id, "state": "ready",
                       "discussion_counts": {}, "config_dir": str(self.config_dir)}
        }).encode()
        (legacy_dir / "codex-collaborate.json").write_bytes(legacy_data)
        paths = helper.state_paths(self.state_root, self.project)
        helper.ensure_private_dir(self.state_root)
        helper.ensure_private_dir(paths["projects"])
        secret = helper.load_secret(paths)
        projects_dir = self.config_dir / "projects"
        (projects_dir / "fixture").mkdir(parents=True)
        (projects_dir / "fixture" / (session_id + ".jsonl")).touch()
        binding = {"account": helper.account_binding(secret, b"synthetic identity"),
                   "auth": "claude.ai", "config_dir": str(self.config_dir)}
        state = helper.new_state(self.project, paths["key"])
        record, _, _ = helper.select_topic(state, "topic", None, False, binding, projects_dir)
        record.update(session_id=session_id, started=True)
        state["last_topic"] = "topic"
        state["legacy"] = {"status": "migrated", "fingerprint": hashlib.sha256(legacy_data).hexdigest()}
        helper.save_state(paths, state)
        packet = self.root / "packet.txt"
        packet.write_text("Synthetic request", encoding="utf-8")
        args = argparse.Namespace(mode="review", trigger="explicit", packet=packet, context=None,
                                  forward_write=False, allow_tool=[], topic="topic", new_topic_reason=None,
                                  recover=False, discussion_id=None)
        prep = helper.Prepared(state_root=self.state_root, config_dir=self.config_dir,
                               info={"identity": b"synthetic identity", "projects_dir": projects_dir,
                                     "version": "fake", "auth_method": "claude.ai"},
                               claude=["never-executed"], env={}, policy={"settings": {}})
        holder = subprocess.Popen(
            [sys.executable, "-B", "-c",
             "import fcntl,sys,time; f=open(sys.argv[1],'r+'); fcntl.flock(f,fcntl.LOCK_EX); "
             "print('LOCKED',flush=True); time.sleep(30)", str(legacy_lock)],
            stdout=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual(holder.stdout.readline().strip(), "LOCKED")
            collector = helper.StreamCollector(65536)
            collector.handle_line(json.dumps({"type": "system", "subtype": "init", "session_id": session_id,
                                             "model": "claude-opus"}).encode())
            collector.handle_line(json.dumps({"type": "result", "session_id": session_id, "subtype": "success",
                                             "is_error": False, "result": "fixture", "modelUsage": {"claude-opus": {}}}).encode())
            with mock.patch.object(helper, "prepare", return_value=prep), \
                    mock.patch.object(helper, "run_claude", return_value=(0, collector)) as launch:
                with self.assertRaises(helper.SessionError) as caught:
                    helper.command_send(args, self.config, self.project)
                self.assertEqual(caught.exception.code, "legacy_busy")
                launch.assert_not_called()
        finally:
            holder.terminate()
            try:
                holder.wait(timeout=5)
            except subprocess.TimeoutExpired:
                holder.kill()
                holder.wait(timeout=5)
            holder.stdout.close()


if __name__ == "__main__":
    unittest.main()
