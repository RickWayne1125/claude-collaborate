#!/usr/bin/env python3
"""Offline behavioral tests; only a fake Claude executable is invoked (no network, no account)."""

import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

HELPER = Path(__file__).resolve().with_name("claude_session.py")
REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("claude_session", HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

POSIX = os.name != "nt"
GRANT = "Bash(python3 -B -m unittest discover -s tests -v)"

FAKE = r'''
import base64, json, os, pathlib, re, signal, subprocess, sys, time
root = pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"])
args = sys.argv[1:]
state = json.loads((root / "fake-state.json").read_text(encoding="utf-8"))
behavior = state.get("behavior", "success")
WATCH = ("DISABLE_TELEMETRY", "DISABLE_ERROR_REPORTING", "DO_NOT_TRACK",
         "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY",
         "DISABLE_FEEDBACK_COMMAND", "ANTHROPIC_API_KEY", "CLAUDE_CODE_SAFE_MODE",
         "CLAUDE_CODE_DISABLE_CLAUDE_MDS")

def log(extra=None):
    entry = {"args": args, "env_names": sorted(os.environ), "cwd": os.getcwd(),
             "env": {key: os.environ[key] for key in WATCH if key in os.environ}}
    entry.update(extra or {})
    with (root / "calls.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry) + "\n")

def out(event):
    sys.stdout.buffer.write(json.dumps(event).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()

if args == ["--version"]:
    log(); print("2.1.290 (Claude Code)"); sys.exit(0)
if args == ["--help"]:
    log(); print(state.get("help", "--effort --safe-mode --restricted --disable-slash-commands "
                          "--system-prompt-snapshot --permission-prompts --strict-mcp-config --max-turns")); sys.exit(0)
if args == ["auth", "status", "--json"]:
    log()
    auth = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty",
            "email": "PRIVATE_EMAIL@example.com", "orgId": "PRIVATE_ORG_ID",
            "configDirectory": str(root), "projectsDirectory": str(root / "projects")}
    auth.update(state.get("auth", {}))
    print(json.dumps({key: value for key, value in auth.items() if value is not None})); sys.exit(0)
if behavior == "no_stdin":
    log({"stdin_read": False}); time.sleep(60); sys.exit(0)
data = sys.stdin.buffer.read()
log({"stdin_b64": base64.b64encode(data).decode("ascii")})
sid = args[args.index("--resume") + 1] if "--resume" in args else args[args.index("--session-id") + 1]
model = args[args.index("--model") + 1]
folder = root / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", os.getcwd())
folder.mkdir(parents=True, exist_ok=True)
with (folder / (sid + ".jsonl")).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"cwd": os.getcwd(), "sessionId": sid, "message": "PRIVATE_TRANSCRIPT_CONTENT"}) + "\n")
if behavior == "timeout":
    child = ("import os,signal,time,pathlib; r=pathlib.Path(os.environ['CLAUDE_CONFIG_DIR']); "
             "signal.signal(signal.SIGTERM, lambda *a: (r.joinpath('child-stopped').write_text('yes'), os._exit(0))); "
             "r.joinpath('child-started').write_text('yes'); time.sleep(60)")
    subprocess.Popen([sys.executable, "-c", child])
    time.sleep(60)
if behavior == "slow":
    time.sleep(state.get("delay", 2))
if behavior == "fail":
    sys.stderr.write("SENSITIVE_STDERR\n"); sys.exit(7)
if behavior == "malformed":
    print("SENSITIVE_INVALID_JSON"); sys.exit(0)
if behavior == "stderr_flood":
    sys.stderr.write("SENSITIVE_STDERR" * 200000); sys.stderr.flush()
if behavior in ("big_output", "huge_line"):
    try:
        if behavior == "huge_line":
            sys.stdout.buffer.write(b'{"type":"user","message":"' + b"SENSITIVE_FILE_CONTENT" * 60000)
        else:
            line = json.dumps({"type": "user", "message": "SENSITIVE_FILE_CONTENT" * 1000}).encode() + b"\n"
            for _ in range(3000):
                sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
    except OSError:
        pass
    time.sleep(60)
response = {"type": "result", "subtype": "success", "is_error": False, "session_id": sid,
            "result": "独立的回答 / Answer", "modelUsage": {model: {}}, "permission_denials": []}
current = model
if behavior == "wrong_model":
    current = "claude-sonnet-4-6"; response["modelUsage"] = {"claude-sonnet-4-6": {}}
if behavior == "wrong_session": response["session_id"] = "12345678-1234-5678-1234-567812345678"
if behavior == "error_result": response.update(is_error=True, subtype="error_during_execution", result="SENSITIVE_ERROR")
if behavior == "max_turns": response.update(is_error=True, subtype="error_max_turns"); response.pop("result")
if behavior == "budget": response.update(is_error=True, subtype="error_max_budget_usd"); response.pop("result")
if behavior == "denied":
    response["permission_denials"] = [{"tool_name": "Bash", "tool_use_id": "x", "tool_input": {"command": "SENSITIVE_COMMAND"}}]
if behavior == "forward_answer": response["result"] = state["answer"]
if behavior == "alias": current = "claude-opus-5-5"; response["modelUsage"] = {"claude-opus-5-5": {}}
if behavior == "mixed_usage": response["modelUsage"] = {model: {}, "claude-sonnet-4-6": {}}
out({"type": "system", "subtype": "init", "session_id": sid, "model": current})
out({"type": "user", "message": {"content": "tool result SENSITIVE_FILE_CONTENT"}})
assistant_model = "claude-sonnet-4-6" if behavior == "assistant_mismatch" else current
out({"type": "assistant", "session_id": sid,
     "message": {"model": assistant_model, "content": [{"type": "thinking", "thinking": "PRIVATE_REASONING"}]}})
out(response)
sys.exit(1 if behavior in ("max_turns", "budget") else 0)
'''


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claude-collaborate-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "proj 项目"
        self.project.mkdir()
        (self.project / "example.py").write_text("print('hello')\n", encoding="utf-8")
        self.claude_config = self.root / "claude-config"
        self.claude_config.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.state_dir = self.root / "state"
        self.fake = self.root / "tools" / "fake_claude.py"
        self.fake.parent.mkdir()
        self.fake.write_text(FAKE, encoding="utf-8")
        self.helper_config = self.root / "helper.json"
        self.write_config({})
        self.packet = self.root / "packet.txt"
        self.packet.write_text("Original request: explain the proof. 用户要求：解释证明。", encoding="utf-8")
        drop = set(helper.CREDENTIAL_ENV + helper.PROVIDER_ENV + helper.TELEMETRY_KEYS)
        self.env = {key: value for key, value in os.environ.items()
                    if key.upper() not in drop and not key.upper().startswith(("XDG_", "CLAUDE_", "OTEL_"))}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                        APPDATA=str(self.home / "AppData" / "Roaming"),
                        LOCALAPPDATA=str(self.home / "AppData" / "Local"),
                        XDG_CONFIG_HOME=str(self.home / ".config"),
                        XDG_STATE_HOME=str(self.home / ".local" / "state"),
                        CLAUDE_CONFIG_DIR=str(self.claude_config), PYTHONDONTWRITEBYTECODE="1",
                        UNRELATED_SECRET="DO_NOT_FORWARD", OTEL_EXPORTER_OTLP_ENDPOINT="http://private.invalid")
        self.behavior("success")

    # -- fixtures -------------------------------------------------------
    def write_config(self, extra, path=None, command=True):
        data = {"version": 1}
        if command:
            data["claude_command"] = [sys.executable, str(self.fake)]
        data.update(extra)
        (path or self.helper_config).write_text(json.dumps(data), encoding="utf-8")

    def behavior(self, name, **extra):
        (self.claude_config / "fake-state.json").write_text(json.dumps({"behavior": name, **extra}), encoding="utf-8")

    def write_settings(self, where, data):
        path = {"user": self.claude_config / "settings.json",
                "project": self.project / ".claude" / "settings.json",
                "local": self.project / ".claude" / "settings.local.json"}[where]
        path.parent.mkdir(exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return path

    def clear_settings(self):
        for path in (self.claude_config / "settings.json", self.project / ".claude" / "settings.json",
                     self.project / ".claude" / "settings.local.json"):
            if path.exists():
                path.unlink()

    def run_helper(self, command, *args, success=True, env=None, expect=None, project=True, config=True,
                   state_dir=True, cwd=None):
        argv = [sys.executable, "-B", str(HELPER), command]
        if project:
            argv += ["--project", str(self.project)]
        if config:
            argv += ["--config", str(self.helper_config)]
        if state_dir:
            argv += ["--state-dir", str(self.state_dir)]
        argv += list(args)
        result = subprocess.run(argv, capture_output=True, env=env or self.env, timeout=90, cwd=cwd)
        code = expect if expect is not None else (0 if success else 1)
        self.assertEqual(result.returncode, code, (result.stdout + result.stderr).decode("utf-8", "replace"))
        if code == 2:
            return None, result
        return json.loads(result.stdout.decode("ascii")), result  # output must be pure ASCII JSON

    def send(self, *args, mode="review", topic="topic-a", trigger="explicit", **kwargs):
        return self.run_helper("send", "--topic", topic, "--mode", mode, "--trigger", trigger,
                               "--packet", str(kwargs.pop("packet", self.packet)), *args, **kwargs)

    def calls(self):
        path = self.claude_config / "calls.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def sends(self):
        return [call for call in self.calls() if "--print" in call["args"]]

    @staticmethod
    def flag(call, name):
        return call["args"][call["args"].index(name) + 1]

    @staticmethod
    def allowed(call):
        args = call["args"]
        if "--allowedTools" not in args:
            return []
        values = []
        for item in args[args.index("--allowedTools") + 1:]:
            if item.startswith("--"):
                break
            values.append(item)
        return values

    def settings(self, call):
        return json.loads(self.flag(call, "--settings"))

    def paths(self):
        return helper.state_paths(self.state_dir, self.project)

    def state(self):
        return json.loads(self.paths()["state"].read_text(encoding="utf-8"))

    def transcript(self, sid):
        return next(self.claude_config.glob("projects/*/" + sid + ".jsonl"))

    def add_transcript(self, sid):
        folder = self.claude_config / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", str(self.project))
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (sid + ".jsonl")).write_text(json.dumps({"message": "PRIVATE_TRANSCRIPT_CONTENT"}) + "\n",
                                               encoding="utf-8")

    def assertNoLeak(self, process, *markers):
        text = process.stdout + process.stderr
        for marker in markers + (b"PRIVATE_EMAIL", b"PRIVATE_ORG_ID", b"PRIVATE_REASONING", b"SENSITIVE"):
            self.assertNotIn(marker if isinstance(marker, bytes) else marker.encode(), text)


class ConfigTests(Base):
    def test_builtin_defaults_are_public_and_conservative(self):
        data, _ = self.run_helper("config", "--no-user-config", config=False)
        config = data["config"]
        self.assertEqual((config["model"], config["effort"], config["auto_consult"]), ("opus", "high", False))
        self.assertEqual((config["telemetry"], config["access"], config["auth"]), ("off", "project", "claude.ai"))
        self.assertEqual(config["routing"], {"simple": "direct", "moderate": "auto", "complex": "discuss-implement"})
        self.assertEqual(config["limits"]["discussion_sends"], 3)
        self.assertEqual(data["sources"], ["builtin", "command-line"])
        self.assertFalse(self.calls())

    @unittest.skipUnless((REPO / "profiles" / "compatible.json").exists(), "repository profiles not present")
    def test_shipped_profiles_validate_and_compatible_preserves_previous_defaults(self):
        default = helper.copy.deepcopy(helper.BUILTIN_CONFIG)
        helper.merge_config(default, helper.read_config_file(REPO / "profiles" / "default.json", "explicit", True))
        self.assertEqual(default, helper.BUILTIN_CONFIG)
        data, _ = self.run_helper("config", "--config", str(REPO / "profiles" / "compatible.json"), config=False)
        config = data["config"]
        self.assertEqual((config["model"], config["effort"], config["auto_consult"]), ("claude-opus-5-5", "xhigh", True))
        self.assertEqual(config["limits"]["discussion_sends"], 3)
        self.assertEqual(config["limits"]["timeout_seconds"], 900)
        self.assertEqual(config["telemetry"], "off")

    def test_precedence_builtin_user_explicit_cli_and_no_project_config(self):
        user = self.home / ".config" / "claude-collaborate" / "config.json"
        user.parent.mkdir(parents=True)
        user.write_text(json.dumps({"version": 1, "model": "user-model", "effort": "medium",
                                    "limits": {"timeout_seconds": 100},
                                    "permissions": {"extra_deny": ["Read(docs/user-private/**)"]}}), encoding="utf-8")
        if not POSIX:
            user = Path(self.env["APPDATA"]) / "claude-collaborate" / "config.json"
            user.parent.mkdir(parents=True)
            user.write_text((self.home / ".config" / "claude-collaborate" / "config.json").read_text())
        self.write_config({"effort": "low", "permissions": {"extra_deny": ["Read(//opt/private/**)"]}})
        for name in (".claude-collaborate.json", ".codex/claude-collaborate.json", "claude-collaborate.json"):
            path = self.project / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps({"version": 1, "model": "project-model"}), encoding="utf-8")
        data, _ = self.run_helper("config")
        config = data["config"]
        self.assertEqual(data["sources"], ["builtin", "user", "explicit", "command-line"])
        self.assertEqual((config["model"], config["effort"]), ("user-model", "low"))
        self.assertEqual(config["limits"]["timeout_seconds"], 100)
        self.assertEqual(config["permissions"]["extra_deny"], ["Read(docs/user-private/**)", "Read(//opt/private/**)"])
        self.send("--model", "cli-model")
        call = self.sends()[-1]
        self.assertEqual((self.flag(call, "--model"), self.flag(call, "--effort")), ("cli-model", "low"))
        deny = self.settings(call)["permissions"]["deny"]
        self.assertIn("Read(docs/user-private/**)", deny)
        self.assertIn("Read(//opt/private/**)", deny)
        data, _ = self.run_helper("config", "--no-user-config")
        self.assertEqual(data["config"]["model"], "opus")

    def test_invalid_configuration_fails_closed(self):
        cases = [
            {"version": 2}, {"version": 1, "unknown": 1}, {"version": 1, "auto_consult": "yes"},
            {"version": 1, "effort": "extreme"}, {"version": 1, "model": "-bad"},
            {"version": 1, "limits": {"timeout_seconds": 0}}, {"version": 1, "limits": {"discussion_sends": True}},
            {"version": 1, "limits": {"max_budget_usd": -1}}, {"version": 1, "limits": {"other": 1}},
            {"version": 1, "routing": {"simple": "forward"}}, {"version": 1, "claude_command": ["relative/claude"]},
            {"version": 1, "permissions": {"extra_deny": ["Read(/ambiguous/**)"]}},
            {"version": 1, "permissions": {"extra_deny": ["Glob(src/**)"]}},
            {"version": 1, "state_dir": "relative/state"}, [1],
        ]
        for case in cases:
            with self.subTest(case=case):
                self.helper_config.write_text(json.dumps(case), encoding="utf-8")
                data, process = self.run_helper("config", success=False)
                self.assertEqual(data["error"], "config_invalid")
                self.assertNotIn(b"Traceback", process.stderr)
        for raw in ('{"version": 1, "model": "a", "model": "b"}', "{not json", "\xff"):
            with self.subTest(raw=raw):
                self.helper_config.write_bytes(raw.encode("latin-1"))
                data, _ = self.run_helper("config", success=False)
                self.assertEqual(data["error"], "config_invalid")
        data, _ = self.run_helper("config", "--config", str(self.root / "missing.json"), config=False, success=False)
        self.assertEqual(data["error"], "config_not_found")
        self.assertFalse(self.calls())

    @unittest.skipUnless(POSIX, "POSIX permission bits")
    def test_group_writable_configuration_is_rejected(self):
        self.helper_config.chmod(0o666)
        data, _ = self.run_helper("config", success=False)
        self.assertEqual(data["error"], "config_insecure")

    def test_trigger_gate_and_required_trigger(self):
        data, _ = self.send(trigger="auto", success=False)
        self.assertEqual(data["error"], "auto_consult_disabled")
        self.assertFalse(self.calls())
        self.run_helper("send", "--topic", "t", "--mode", "review", "--packet", str(self.packet), expect=2)
        self.write_config({"auto_consult": True})
        data, _ = self.send(trigger="auto")
        self.assertEqual(data["trigger"], "auto")

    def test_turn_and_budget_flags_from_config_and_cli(self):
        self.write_config({"limits": {"max_turns": 3, "max_budget_usd": 0.5}})
        self.send()
        call = self.sends()[-1]
        self.assertEqual((self.flag(call, "--max-turns"), self.flag(call, "--max-budget-usd")), ("3", "0.5"))
        self.send("--max-turns", "5", "--max-budget-usd", "1.25")
        call = self.sends()[-1]
        self.assertEqual((self.flag(call, "--max-turns"), self.flag(call, "--max-budget-usd")), ("5", "1.25"))
        self.write_config({})
        self.send()
        self.assertNotIn("--max-turns", self.sends()[-1]["args"])
        self.assertNotIn("--max-budget-usd", self.sends()[-1]["args"])
        count = len(self.calls())
        for flags in (("--max-turns", "0"), ("--max-budget-usd", "0"), ("--max-budget-usd", "nan"),
                      ("--max-budget-usd", "inf"), ("--timeout-seconds", "0"), ("--model", "-x")):
            with self.subTest(flags=flags):
                self.send(*flags, expect=2)
        self.assertEqual(len(self.calls()), count)

    def test_small_positive_budget_is_not_rounded_to_zero(self):
        self.send("--max-budget-usd", "0.00000001")
        value = self.flag(self.sends()[-1], "--max-budget-usd")
        self.assertEqual(float(value), 0.00000001)

    def test_doctor_is_offline_minimal_and_creates_no_state(self):
        data, process = self.run_helper("doctor")
        self.assertFalse(data["inference_sent"])
        self.assertEqual(len(self.calls()), 3)
        self.assertFalse(self.sends())
        self.assertEqual(data["optional_flags_in_help"], {"--max-turns": True, "--max-budget-usd": False})
        self.assertTrue(data["config_dir_verified"])
        self.assertEqual(data["permission_policy"]["sandbox"], "inactive")
        self.assertNoLeak(process)
        self.assertFalse(self.state_dir.exists())
        self.assertEqual(sorted(p.name for p in self.project.iterdir()), ["example.py"])

    def test_status_without_state_has_no_side_effects(self):
        data, _ = self.run_helper("status")
        self.assertEqual((data["topic_count"], data["legacy_registry"]), (0, "absent"))
        self.assertFalse(self.state_dir.exists())
        self.assertFalse(self.calls())


class PrivacyTests(Base):
    def test_off_policy_sets_exact_optouts_and_filters_environment(self):
        env = dict(self.env, DISABLE_TELEMETRY="0")
        self.send(env=env)
        for call in self.calls():
            for key in helper.TELEMETRY_KEYS:
                self.assertEqual(call["env"][key], "1")
            for name in ("UNRELATED_SECRET", "OTEL_EXPORTER_OTLP_ENDPOINT", "ANTHROPIC_API_KEY"):
                self.assertNotIn(name, call["env_names"])
            self.assertEqual(call["env"]["CLAUDE_CODE_SAFE_MODE"], "1")
            self.assertEqual(call["env"]["CLAUDE_CODE_DISABLE_CLAUDE_MDS"], "1")

    def test_inherit_policy_preserves_exact_values_and_selected_user_settings(self):
        self.write_config({"telemetry": "inherit"})
        self.write_settings("user", {"env": {"DISABLE_TELEMETRY": "from-settings", "DISABLE_ERROR_REPORTING": "kept",
                                             "DISABLE_FEEDBACK_COMMAND": 1, "OTEL_METRICS_EXPORTER": "otlp",
                                             "ANTHROPIC_API_KEY": "PRIVATE_SETTINGS_KEY"}})
        env = dict(self.env, DISABLE_TELEMETRY="0", DO_NOT_TRACK="false")
        _, process = self.send(env=env)
        call = self.sends()[-1]
        self.assertEqual(call["env"]["DISABLE_TELEMETRY"], "0")  # process value wins
        self.assertEqual(call["env"]["DO_NOT_TRACK"], "false")
        self.assertEqual(call["env"]["DISABLE_ERROR_REPORTING"], "kept")
        self.assertEqual(call["env"]["DISABLE_FEEDBACK_COMMAND"], "1")
        self.assertNotIn("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", call["env"])
        self.assertNotIn("OTEL_METRICS_EXPORTER", call["env_names"])
        self.assertNotIn("ANTHROPIC_API_KEY", call["env_names"])
        self.assertNoLeak(process, "PRIVATE_SETTINGS_KEY")
        self.write_settings("user", {"env": {"DISABLE_TELEMETRY": True}})
        data, _ = self.send(success=False)
        self.assertEqual(data["error"], "settings_invalid")
        self.write_config({})
        self.send()  # malformed telemetry env is irrelevant when the policy is off

    def test_settings_env_hooks_and_allow_rules_are_not_propagated(self):
        self.write_settings("user", {"env": {"ANTHROPIC_BASE_URL": "https://gateway.invalid", "NODE_OPTIONS": "--x"},
                                     "hooks": {"PreToolUse": []}, "apiKeyHelper": "/bin/echo",
                                     "permissions": {"allow": ["Bash(*)", "Read"], "additionalDirectories": ["/"],
                                                     "defaultMode": "bypassPermissions"},
                                     "model": "claude-other", "enabledPlugins": {"x": True}})
        self.write_settings("project", {"permissions": {"allow": ["Edit"]}, "hooks": {"Stop": []}})
        self.send()
        call = self.sends()[-1]
        settings = self.settings(call)
        self.assertEqual(set(settings), {"disableAllHooks", "permissions"})
        self.assertTrue(settings["disableAllHooks"])
        self.assertEqual(set(settings["permissions"]), {"deny"})
        for value in ("Bash(*)", "bypassPermissions", "/bin/echo", "claude-other"):
            self.assertNotIn(value, call["args"])
        self.assertNotIn("NODE_OPTIONS", call["env_names"])
        self.assertNotIn("ANTHROPIC_BASE_URL", call["env_names"])
        self.assertEqual(self.flag(call, "--permission-mode"), "dontAsk")
        self.assertNotIn("--dangerously-skip-permissions", call["args"])

    def test_api_key_profile_uses_only_selected_credential_and_binds_it(self):
        self.write_config({"auth": "api-key"})
        self.behavior("success", auth={"authMethod": "api_key", "email": None, "orgId": None})
        env = dict(self.env, ANTHROPIC_API_KEY="test-api-key-PRIVATE")
        data, process = self.send(env=env)
        for call in self.calls():
            self.assertEqual(call["env"]["ANTHROPIC_API_KEY"], "test-api-key-PRIVATE")
        self.assertNoLeak(process, "test-api-key-PRIVATE")
        self.assertNotIn(b"test-api-key-PRIVATE", self.paths()["state"].read_bytes())
        count = len(self.sends())
        conflict, process = self.send(env=dict(env, CLAUDE_CODE_OAUTH_TOKEN="PRIVATE_TOKEN"), success=False)
        self.assertEqual((conflict["error"], conflict["variables"]), ("auth_environment_conflict", ["CLAUDE_CODE_OAUTH_TOKEN"]))
        self.assertNoLeak(process, "PRIVATE_TOKEN")
        missing, _ = self.send(success=False)
        self.assertEqual(missing["error"], "api_key_missing")
        rotated, _ = self.send(env=dict(env, ANTHROPIC_API_KEY="rotated-key"), success=False)
        self.assertEqual(rotated["error"], "account_changed")
        self.write_config({})
        self.behavior("success")
        switched, _ = self.send(success=False)
        self.assertEqual(switched["error"], "account_changed")
        self.assertEqual(len(self.sends()), count)
        self.behavior("success", auth={"authMethod": "api_key", "email": None, "orgId": None})
        resumed, _ = self.send("--auth", "api-key", env=env)  # same key + profile resumes
        self.assertEqual((resumed["session_id"], resumed["resumed"]), (data["session_id"], True))

    def test_claude_ai_profile_rejects_credentials_and_provider_routing(self):
        for name in helper.CREDENTIAL_ENV + helper.PROVIDER_ENV:
            with self.subTest(name=name):
                data, process = self.send(env=dict(self.env, **{name: "PRIVATE_VALUE"}), success=False)
                self.assertEqual((data["error"], data["variables"]), ("auth_environment_conflict", [name]))
                self.assertNoLeak(process, "PRIVATE_VALUE")
        self.assertFalse(self.calls())

    def test_login_metadata_mismatches_fail_before_inference(self):
        cases = [({"authMethod": "api_key"}, "auth_method_mismatch"), ({"apiProvider": "bedrock"}, "unsupported_provider"),
                 ({"loggedIn": False}, "login_required"), ({"email": None}, "account_identity_unavailable"),
                 ({"configDirectory": "/elsewhere/claude"}, "config_directory_mismatch")]
        for auth, code in cases:
            with self.subTest(code=code):
                self.behavior("success", auth=auth)
                data, process = self.send(success=False)
                self.assertEqual(data["error"], code)
                self.assertNoLeak(process)
        self.assertFalse(self.sends())


class SettingsTests(Base):
    def test_deny_and_ask_import_preserves_source_anchors(self):
        self.write_settings("user", {"permissions": {
            "deny": ["Read(/secrets/**)", "Read(./notes.txt)", "Edit(//abs/x/**)", "Read(~/private/**)",
                     "Bash(curl:*)", "WebFetch(domain:example.com)", "Read(src/*.key)", "mcp__server__tool"],
            "ask": ["Bash(git push:*)", "Edit(/drafts/**)"], "allow": ["Bash(*)"]}})
        self.write_settings("project", {"permissions": {"deny": ["Read(/private/**)"], "allow": ["Read"]}})
        self.write_settings("local", {"permissions": {"deny": ["Edit(/local/**)"], "ask": ["Read(./ask.txt)"]}})
        self.write_config({"permissions": {"extra_deny": ["Read(//opt/private/**)"]}})
        self.send()
        deny = self.settings(self.sends()[-1])["permissions"]["deny"]
        user_prefix = helper.absolute_rule_path(str(self.claude_config))
        project_prefix = helper.absolute_rule_path(str(self.project))
        expected = [f"Read({user_prefix}/secrets/**)", "Read(./notes.txt)", "Edit(//abs/x/**)", "Read(~/private/**)",
                    "Bash(curl:*)", "WebFetch(domain:example.com)", "Read(src/*.key)", "mcp__server__tool",
                    "Bash(git push:*)", f"Edit({user_prefix}/drafts/**)", f"Read({project_prefix}/private/**)",
                    f"Edit({project_prefix}/local/**)", "Read(./ask.txt)", "Read(//opt/private/**)"]
        for rule in expected:
            self.assertIn(rule, deny)
        self.assertNotIn("Read(/secrets/**)", deny)
        self.assertNotIn("Bash(*)", self.sends()[-1]["args"])

    def test_malformed_or_unsupported_rules_fail_closed(self):
        cases = [
            ("user", "{not json", "settings_invalid"), ("user", ["array"], "settings_invalid"),
            ("user", {"permissions": []}, "settings_invalid"),
            ("project", {"permissions": {"deny": "Read(x)"}}, "settings_invalid"),
            ("local", {"permissions": {"ask": [42]}}, "invalid_permission_rule"),
            ("user", {"permissions": {"deny": ["Read(!secret-name)"]}}, "unsupported_permission_rule"),
            ("project", {"permissions": {"deny": ["Glob(src/**)"]}}, "unsupported_permission_rule"),
            ("user", {"permissions": {"ask": ["Write(/x)"]}}, "unsupported_permission_rule"),
            ("local", {"permissions": {"deny": ["NotebookEdit(nb/**)"]}}, "unsupported_permission_rule"),
            ("user", {"permissions": {"deny": ["MultiEdit(x)"]}}, "unsupported_permission_rule"),
            ("user", {"permissions": {"deny": ["Read(C:\\\\x)"]}}, "unsupported_permission_rule"),
            ("user", {"permissions": {"deny": ["not a rule"]}}, "unsupported_permission_rule"),
            ("user", {"cleanupPeriodDays": "30"}, "settings_invalid"),
            ("user", {"sandbox": "on"}, "settings_invalid"),
        ]
        for where, content, code in cases:
            with self.subTest(where=where, content=content):
                self.clear_settings()
                self.write_settings(where, content)
                data, process = self.send(success=False)
                self.assertEqual((data["error"], data["source"]), (code, where))
                self.assertNoLeak(process, "secret-name")
        self.assertFalse(self.sends())

    def test_enabled_sandbox_fails_closed_and_disabled_is_allowed(self):
        for where in ("user", "project", "local"):
            with self.subTest(where=where):
                self.clear_settings()
                self.write_settings(where, {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True}})
                data, _ = self.send(success=False)
                self.assertEqual((data["error"], data["source"]), ("unsupported_sandbox_policy", where))
        self.assertFalse(self.calls())
        self.clear_settings()
        for policy in ({}, {"enabled": False}):
            self.write_settings("user", {"sandbox": policy})
            self.send()
        self.write_settings("user", {"sandbox": {"enabled": False, "network": {}}})
        data, _ = self.send(success=False)
        self.assertEqual(data["error"], "unsupported_sandbox_policy")

    def test_cleanup_period_is_preserved_only_when_set(self):
        self.write_settings("user", {"cleanupPeriodDays": 365})
        self.send()
        self.assertEqual(self.settings(self.sends()[-1])["cleanupPeriodDays"], 365)
        self.clear_settings()
        self.send()
        self.assertNotIn("cleanupPeriodDays", self.settings(self.sends()[-1]))

    def test_baseline_denies_and_project_scoped_allows(self):
        self.send()
        call = self.sends()[-1]
        deny = self.settings(call)["permissions"]["deny"]
        for rule in ("Read(**/.env)", "Read(**/.env.*)", "Edit(**/.env)", "Read(~/.ssh/**)", "Read(**/.aws/**)",
                     "Read(~/.kube/config)", "Read(**/.docker/config.json)", "Read(**/.npmrc)", "Read(**/.pypirc)",
                     "Read(**/id_rsa)", "Read(**/id_ed25519)", "Read(**/secrets/**)", "Edit(**/.git/**)",
                     "Edit(**/.claude/**)", "Edit(**/.codex/**)", "Edit(**/.agents/**)"):
            self.assertIn(rule, deny)
        state_prefix = helper.absolute_rule_path(os.path.realpath(str(self.state_dir)))
        self.assertIn(f"Read({state_prefix}/**)", deny)
        self.assertIn(f"Edit({state_prefix}/**)", deny)
        self.assertEqual(self.allowed(call), [f"Read({helper.absolute_rule_path(str(self.project))}/**)"])

    def test_rule_anchor_conversion_helpers(self):
        self.assertEqual(helper.absolute_rule_path("/tmp/a*b[1]?", False), "//tmp/a\\*b\\[1\\]\\?")
        self.assertEqual(helper.normalize_rule("Read(/x/**)", "user", "/", False), "Read(//x/**)")
        self.assertEqual(helper.normalize_rule("Edit(/src/**)", "project", "/work/项目 x", False),
                         "Edit(//work/项目 x/src/**)")
        for rule in ("Read(//abs)", "Read(~/x)", "Read(x/**)", "Read(./x)", "Bash(npm run build)", "Read"):
            self.assertEqual(helper.normalize_rule(rule, "user", "/cfg", False), rule)
        self.assertEqual(helper.absolute_rule_path("/tmp/with (parens)", False), "//tmp/with (parens)")
        with self.assertRaises(helper.SessionError) as caught:
            helper.absolute_rule_path("/tmp/control\ncharacter", False)
        self.assertEqual(caught.exception.code, "unsupported_path_characters")


class StateTests(Base):
    def test_topics_beyond_twelve_return_to_original_uuid_and_counts(self):
        first, _ = self.send("--discussion-id", "plan-1", mode="discuss", topic="topic-0")
        for index in range(1, 14):
            self.send("--new-topic-reason", "Unrelated task %d" % index, topic="topic-%d" % index)
        back, _ = self.send("--discussion-id", "plan-1", mode="discuss", topic="topic-0")
        self.assertEqual(back["session_id"], first["session_id"])
        self.assertTrue(back["resumed"])
        self.assertFalse(back["new_session"])
        self.assertEqual(back["discussion_send_count"], 2)
        self.assertEqual(len(self.state()["topics"]), 14)
        self.assertEqual(self.state()["last_topic"], "topic-0")

    def test_new_topic_requires_reason_and_reason_is_not_persisted(self):
        self.send()
        blocked, _ = self.send(topic="topic-b", success=False)
        self.assertEqual((blocked["error"], blocked["known_topics"]), ("topic_switch_requires_reason", ["topic-a"]))
        new, _ = self.send("--new-topic-reason", "PRIVATE_REASON_TEXT", topic="topic-b")
        self.assertTrue(new["new_session"])
        raw = self.paths()["state"].read_bytes()
        for marker in (b"PRIVATE_REASON_TEXT", b"PRIVATE_EMAIL", b"PRIVATE_ORG_ID", b"Original request"):
            self.assertNotIn(marker, raw)
        same, _ = self.send(topic="topic-a", mode="cross-validate")
        self.assertTrue(same["resumed"])

    def test_account_change_blocks_active_and_historical_topics(self):
        first, _ = self.send(topic="topic-a")
        self.send("--new-topic-reason", "Different task", topic="topic-b")
        self.behavior("success", auth={"email": "OTHER_PRIVATE@example.com"})
        count = len(self.sends())
        for topic in ("topic-b", "topic-a"):
            data, process = self.send(topic=topic, success=False)
            self.assertEqual(data["error"], "account_changed")
            self.assertNoLeak(process, "OTHER_PRIVATE")
        self.assertEqual(len(self.sends()), count)
        self.send("--new-topic-reason", "Separate task under another account", topic="topic-c")
        self.behavior("success", auth={"orgId": "OTHER_ORG"})
        data, _ = self.send(topic="topic-a", success=False)
        self.assertEqual(data["error"], "account_changed")
        self.behavior("success")
        again, _ = self.send(topic="topic-a")
        self.assertEqual(again["session_id"], first["session_id"])

    def test_config_store_change_blocks_resume(self):
        self.send()
        other = self.root / "other-config"
        other.mkdir()
        (other / "fake-state.json").write_text(json.dumps({"behavior": "success"}), encoding="utf-8")
        data, _ = self.send(env=dict(self.env, CLAUDE_CONFIG_DIR=str(other)), success=False)
        self.assertEqual(data["error"], "config_store_changed")

    def test_helper_writes_no_runtime_files_into_project(self):
        before = sorted(str(p.relative_to(self.project)) for p in self.project.rglob("*"))
        self.send()
        self.send("--allow-tool", GRANT, mode="implement")
        self.send("--discussion-id", "plan", mode="discuss")
        self.run_helper("status")
        after = sorted(str(p.relative_to(self.project)) for p in self.project.rglob("*"))
        self.assertEqual(before, after)

    @unittest.skipUnless(POSIX, "POSIX permission bits")
    def test_state_is_private(self):
        self.send()
        paths = self.paths()
        for path, mode in ((self.state_dir, 0o700), (paths["projects"], 0o700), (paths["state"], 0o600),
                           (paths["secret"], 0o600), (paths["lock"], 0o600)):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode, path.name)
        self.assertEqual(len(paths["secret"].read_bytes()), 32)

    def test_project_lock_blocks_concurrent_helper(self):
        self.send()
        count = len(self.sends())
        with helper.file_lock(self.paths()["lock"]):
            data, _ = self.send(success=False)
        self.assertEqual(data["error"], "session_busy")
        self.assertEqual(len(self.sends()), count)

    def test_simultaneous_sends_do_not_duplicate_sessions(self):
        self.behavior("slow", delay=3)
        argv = [sys.executable, "-B", str(HELPER), "send", "--project", str(self.project), "--config",
                str(self.helper_config), "--state-dir", str(self.state_dir), "--topic", "topic-a", "--mode", "review",
                "--trigger", "explicit", "--packet", str(self.packet)]
        processes = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env)
                     for _ in range(2)]
        results = [json.loads(process.communicate(timeout=60)[0]) for process in processes]
        outcomes = sorted("ok" if item["ok"] else item["error"] for item in results)
        self.assertIn(outcomes, (["ok", "session_busy"], ["ok", "state_busy"]))
        self.assertEqual(len(self.sends()), 1)
        self.assertEqual(len(self.state()["topics"]), 1)

    def test_corrupt_or_invalid_state_is_not_replaced(self):
        self.send()
        path = self.paths()["state"]
        for content in (b"{not json", json.dumps(dict(self.state(), schema=1)).encode()):
            with self.subTest(content=content[:20]):
                path.write_bytes(content)
                for command in ("send", "status"):
                    if command == "send":
                        data, process = self.send(success=False)
                    else:
                        data, process = self.run_helper("status", success=False)
                    self.assertEqual(data["error"], "invalid_state")
                    self.assertNotIn(b"Traceback", process.stderr)
                self.assertEqual(path.read_bytes(), content)
        state = json.loads(json.dumps(self.state_snapshot()))
        record = next(iter(state["topics"].values()))
        record["discussion_counts"] = {"plan": -1}
        path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(self.run_helper("status", success=False)[0]["error"], "invalid_state")
        record["discussion_counts"] = {"plan": 99}  # above the cap is still structurally valid
        path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(self.run_helper("status")[0]["topic_count"], 1)

    def state_snapshot(self):
        return {"schema": 2, "project": str(self.project), "project_key": self.paths()["key"], "last_topic": "topic-a",
                "legacy": None, "topics": {"topic-a": {
                    "session_id": str(uuid.uuid4()), "state": "ready", "started": True, "account": "a" * 64,
                    "auth": "claude.ai", "config_dir": str(self.claude_config), "created_at": "x", "updated_at": "x",
                    "discussion_counts": {}}}}

    def test_unsafe_state_locations_are_rejected(self):
        target = self.root / "real-state"
        target.mkdir()
        link = self.root / "state-link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest("symlinks unavailable: %s" % error)
        data, _ = self.run_helper("send", "--topic", "t", "--mode", "review", "--trigger", "explicit", "--packet",
                                  str(self.packet), "--state-dir", str(link), state_dir=False, success=False)
        self.assertEqual(data["error"], "unsafe_state_path")
        if POSIX:
            loose = self.root / "loose-state"
            loose.mkdir()
            loose.chmod(0o770)
            data, _ = self.run_helper("send", "--topic", "t", "--mode", "review", "--trigger", "explicit",
                                      "--packet", str(self.packet), "--state-dir", str(loose), state_dir=False,
                                      success=False)
            self.assertEqual(data["error"], "unsafe_state_permissions")
        self.assertFalse(self.sends())

    def test_atomic_write_failure_preserves_previous_state(self):
        target = self.root / "atomic.json"
        target.write_bytes(b"old")
        with mock.patch.object(helper.os, "replace", side_effect=OSError("simulated")):
            with self.assertRaises(OSError):
                helper.atomic_write(target, b"new")
        self.assertEqual(target.read_bytes(), b"old")
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".tmp-")], [])

    def test_uncertain_attempt_requires_deliberate_recovery(self):
        self.behavior("fail")
        failed, process = self.send("--discussion-id", "plan-1", mode="discuss", success=False)
        self.assertEqual(failed["error"], "claude_failed")
        self.assertNoLeak(process)
        record = self.state()["topics"]["topic-a"]
        self.assertEqual((record["state"], record["discussion_counts"]["plan-1"]), ("uncertain", 1))
        self.behavior("success")
        blocked, _ = self.send("--discussion-id", "plan-1", mode="discuss", success=False)
        self.assertEqual(blocked["error"], "uncertain_session")
        self.assertEqual(len(self.sends()), 1)
        recovered, _ = self.send("--discussion-id", "plan-1", "--recover", mode="discuss")
        self.assertEqual((recovered["discussion_send_count"], recovered["resumed"]), (2, True))
        self.assertEqual(recovered["session_id"], failed["session_id"])

    def test_unstarted_recovery_reuses_same_uuid_when_no_transcript_exists(self):
        self.behavior("fail")
        failed, _ = self.send(success=False)
        self.transcript(failed["session_id"]).unlink()  # launch failed before transcript creation
        self.behavior("success")
        result, _ = self.send("--recover")
        self.assertEqual((result["session_id"], result["resumed"]), (failed["session_id"], False))
        self.assertEqual(self.flag(self.sends()[-1], "--session-id"), failed["session_id"])

    def test_started_session_with_missing_transcript_is_not_resent(self):
        first, _ = self.send()
        self.transcript(first["session_id"]).unlink()
        data, _ = self.send(success=False)
        self.assertEqual(data["error"], "transcript_missing")
        self.assertEqual(len(self.sends()), 1)


class LegacyTests(Base):
    def legacy_session(self, topic, state="ready", counts=None, transcript=True, config_dir=None):
        sid = str(uuid.uuid4())
        if transcript:
            self.add_transcript(sid)
        return {"session_id": sid, "topic": topic, "state": state, "created_at": "2026-10-01T00:00:00+00:00",
                "updated_at": "2026-10-01T00:00:00+00:00", "discussion_counts": counts or {},
                "config_dir": config_dir or str(self.claude_config)}

    def make_legacy(self, history, active=None, **overrides):
        registry = {"version": 1, "project": str(self.project), "active": active, "history": history}
        registry.update(overrides)
        folder = self.project / ".claude"
        folder.mkdir(exist_ok=True)
        path = folder / "codex-collaborate.json"
        path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        return path

    def test_legacy_registry_blocks_send_without_touching_it(self):
        path = self.make_legacy([], active=self.legacy_session("topic-a"))
        before, mtime = path.read_bytes(), path.stat().st_mtime_ns
        data, _ = self.send(success=False)
        self.assertEqual((data["error"], data["legacy_status"]), ("legacy_registry_present", "pending"))
        self.assertFalse(self.sends())
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), (before, mtime))
        self.assertEqual(self.run_helper("status")[0]["legacy_registry"], "pending")

    def test_migration_imports_metadata_and_leaves_legacy_untouched(self):
        a = self.legacy_session("topic-a", counts={"plan-1": 2})
        b = self.legacy_session("topic-b")
        c = self.legacy_session("topic-c", state="uncertain", transcript=False)
        path = self.make_legacy([b, c], active=a)
        lock = path.with_name("codex-collaborate.lock")
        lock.write_bytes(b"")
        before = (path.read_bytes(), path.stat().st_mtime_ns, lock.read_bytes(), lock.stat().st_mtime_ns)
        data, process = self.run_helper("migrate-legacy")
        self.assertEqual(sorted(item["topic"] for item in data["migrated_topics"]), ["topic-a", "topic-b", "topic-c"])
        self.assertFalse(data["account_origin_verified"])
        self.assertNoLeak(process, "PRIVATE_TRANSCRIPT_CONTENT")
        self.assertFalse(self.sends())
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns, lock.read_bytes(), lock.stat().st_mtime_ns),
                         before)
        status, _ = self.run_helper("status")
        self.assertEqual((status["legacy_registry"], status["last_topic"], status["topic_count"]),
                         ("migrated", "topic-a", 3))
        self.assertTrue(status["topics"]["topic-a"]["migrated_from_legacy"])
        self.assertNotIn("account", status["topics"]["topic-a"])
        resumed, _ = self.send("--discussion-id", "plan-1", mode="discuss", topic="topic-a")
        self.assertEqual((resumed["session_id"], resumed["resumed"], resumed["discussion_send_count"]),
                         (a["session_id"], True, 3))
        other, _ = self.send(topic="topic-b")
        self.assertEqual((other["session_id"], other["resumed"]), (b["session_id"], True))
        blocked, _ = self.send(topic="topic-c", success=False)
        self.assertEqual(blocked["error"], "uncertain_session")
        recovered, _ = self.send("--recover", topic="topic-c")
        self.assertEqual((recovered["session_id"], recovered["resumed"]), (c["session_id"], False))
        again, _ = self.run_helper("migrate-legacy")
        self.assertTrue(again["already_migrated"])

    def test_migration_refuses_unverifiable_or_conflicting_input(self):
        cases = [
            (lambda: self.make_legacy([self.legacy_session("t1", transcript=False)]), "legacy_transcript_missing"),
            (lambda: self.make_legacy([self.legacy_session("t2", config_dir="/elsewhere/claude")]),
             "legacy_config_mismatch"),
            (lambda: self.make_legacy([], version=2), "invalid_legacy_registry"),
            (lambda: self.make_legacy([self.legacy_session("t3"), self.legacy_session("t3")]), "legacy_topic_conflict"),
            (lambda: self.make_legacy([dict(self.legacy_session("t4"), discussion_counts={"x": -1})]),
             "invalid_legacy_registry"),
        ]
        for build, code in cases:
            with self.subTest(code=code):
                path = build()
                before = path.read_bytes()
                data, _ = self.run_helper("migrate-legacy", success=False)
                self.assertEqual(data["error"], code)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(self.run_helper("status")[0]["topic_count"], 0)
        self.write_config({"auth": "api-key"})
        data, _ = self.run_helper("migrate-legacy", success=False)
        self.assertEqual(data["error"], "legacy_auth_mismatch")
        self.assertFalse(self.sends())

    def test_changed_legacy_blocks_again_and_dismiss_is_explicit(self):
        a = self.legacy_session("topic-a")
        path = self.make_legacy([], active=a)
        self.run_helper("migrate-legacy")
        self.send()
        registry = json.loads(path.read_text(encoding="utf-8"))
        registry["active"]["discussion_counts"] = {"later": 1}  # earlier helper kept running
        path.write_text(json.dumps(registry), encoding="utf-8")
        count = len(self.sends())
        data, _ = self.send(success=False)
        self.assertEqual((data["error"], data["legacy_status"]), ("legacy_registry_present", "changed"))
        conflict, _ = self.run_helper("migrate-legacy", success=False)
        self.assertEqual(conflict["error"], "migration_conflict")
        dismissed, _ = self.run_helper("migrate-legacy", "--dismiss")
        self.assertEqual(dismissed["legacy_registry"], "dismissed")
        self.send()
        self.assertEqual(len(self.sends()), count + 1)
        missing = self.root / "empty-project"
        missing.mkdir()
        data, _ = self.run_helper("migrate-legacy", "--project", str(missing), project=False, success=False)
        self.assertEqual(data["error"], "legacy_registry_not_found")


class ExecutionTests(Base):
    def test_forward_preserves_request_bytes_and_answer_text(self):
        first, _ = self.send()
        original = "  请分析 src/example.py。\r\nKeep `code` and $HOME.\r\n\n末尾空格  ".encode("utf-8")
        self.packet.write_bytes(original)
        context = self.root / "context.txt"
        context.write_bytes("Project instruction: prefer evidence.\r\n".encode("utf-8"))
        answer = "  **Claude 原始回答**\r\n\r\n```python\nprint('答案')\n```\n  "
        self.behavior("forward_answer", answer=answer)
        data, _ = self.send("--context", str(context), mode="forward")
        self.assertEqual(data["answer"], answer)
        self.assertEqual((data["session_id"], data["resumed"]), (first["session_id"], True))
        self.assertIsNone(data["discussion_send_count"])
        stdin = base64.b64decode(self.sends()[-1]["stdin_b64"])
        prefix, request = stdin.split(b"Original user request (verbatim; everything below this line):\n", 1)
        self.assertEqual(request, original)
        self.assertIn(context.read_bytes(), prefix)
        self.assertIn(str(self.project).encode("utf-8"), prefix)

    def test_large_packet_is_delivered_completely_and_limits_apply(self):
        packet = self.root / "large.txt"
        content = ("数据\r\n" * 250000).encode("utf-8")
        packet.write_bytes(content)
        self.send(packet=packet)
        self.assertIn(content, base64.b64decode(self.sends()[-1]["stdin_b64"]))
        self.write_config({"limits": {"packet_bytes": 1024}})
        count = len(self.calls())
        data, _ = self.send(packet=packet, success=False)
        self.assertEqual((data["error"], data["limit_bytes"]), ("invalid_packet", 1024))
        self.assertEqual(len(self.calls()), count)

    def test_tools_and_scoped_permissions_follow_mode(self):
        prefix = helper.absolute_rule_path(str(self.project))
        for mode in ("cross-validate", "review", "discuss", "forward"):
            extra = ("--discussion-id", "plan-1") if mode == "discuss" else ()
            data, _ = self.send(*extra, mode=mode)
            call = self.sends()[-1]
            self.assertEqual((call["cwd"], data["project"]), (str(self.project), str(self.project)))
            self.assertEqual(self.flag(call, "--tools"), "Read,Glob,Grep")
            self.assertEqual(self.allowed(call), [f"Read({prefix}/**)"])
        for args, mode in ((("--allow-tool", GRANT), "implement"), (("--forward-write", "--allow-tool", GRANT), "forward")):
            self.send(*args, mode=mode)
            call = self.sends()[-1]
            self.assertEqual(self.flag(call, "--tools"), "Read,Glob,Grep,Edit,Write,Bash")
            self.assertEqual(self.allowed(call), [f"Read({prefix}/**)", f"Edit({prefix}/**)", GRANT])
            self.assertEqual(self.flag(call, "--permission-mode"), "dontAsk")
            self.assertEqual(self.flag(call, "--permission-prompts"), "none")
            for flag in ("--safe-mode", "--restricted", "--strict-mcp-config", "--disable-slash-commands"):
                self.assertIn(flag, call["args"])
            self.assertNotIn("--dangerously-skip-permissions", call["args"])

    def test_packet_access_exposes_no_tools_and_rejects_write_combinations(self):
        data, _ = self.send("--access", "packet")
        call = self.sends()[-1]
        self.assertEqual((self.flag(call, "--tools"), self.allowed(call), data["access"]), ("", [], "packet"))
        self.assertIn(b"Project access this turn: none", base64.b64decode(call["stdin_b64"]))
        self.write_config({"access": "packet"})
        count = len(self.calls())
        for args, mode in ((("--allow-tool", GRANT), "implement"), (("--forward-write",), "forward"),
                           ((), "implement")):
            with self.subTest(mode=mode, args=args):
                data, _ = self.send(*args, mode=mode, success=False)
                self.assertEqual(data["error"], "access_conflict")
        self.assertEqual(len(self.calls()), count)

    def test_grants_are_exact_commands_only(self):
        for grant in (GRANT, "Bash(python3 -B -m unittest discover -s skills/claude-collaborate/scripts -v)",
                      "Bash(npm test)", "Bash(pytest tests/test_x.py -q)", "Bash(python3 -m pytest -k 'a and b')",
                      "Bash(./scripts/check.sh --fast)", "Bash(node scripts/test.js)", "Bash(py -3 -m unittest)"):
            helper.validate_grants([grant], True)
        bad = ["Bash", "Read", "bypassPermissions", "Bash()", "Bash( pytest)", "Bash(*)", "Bash(:*)", "Bash(npm test:*)",
               "Bash(pytest *)", "Bash(pytest tests/test_?.py)", "Bash(sh -c ls)", "Bash(bash)", "Bash(/bin/zsh x.sh)",
               "Bash(cmd.exe /c dir)", "Bash(python3)", "Bash(python3 -c pass)", "Bash(python3 -Bc pass)",
               "Bash(python3 -)", "Bash(node -e x)", "Bash(node --eval=x)", "Bash(ruby -e x)", "Bash(perl -E x)",
               "Bash(php -r x)", "Bash(env pytest)", "Bash(FOO=1 pytest)", "Bash(sudo make test)", "Bash(xargs rm)",
               "Bash(make test && rm -rf x)", "Bash(echo $HOME)", "Bash(pytest; ls)", "Bash(a | b)",
               "Bash(pytest > out.txt)", "Bash(pytest),Bash(*)", "Bash(pytest) Bash(*)", "Bash('unbalanced)"]
        for grant in bad:
            with self.subTest(grant=grant):
                with self.assertRaises(helper.SessionError) as caught:
                    helper.validate_grants([grant], True)
                self.assertIn(caught.exception.code, {"invalid_tool_grant", "broad_tool_grant"})
        with self.assertRaises(helper.SessionError) as caught:
            helper.validate_grants(["Bash(pytest)"], False)
        self.assertEqual(caught.exception.code, "tools_not_allowed")
        for grant, mode in (("Bash(*)", "implement"), ("Bash(pytest)", "review"), ("Bash(pytest)", "forward")):
            data, _ = self.send("--allow-tool", grant, mode=mode, success=False)
            self.assertIn(data["error"], {"broad_tool_grant", "tools_not_allowed"})
        self.assertFalse(self.calls())

    def test_forward_only_flags_are_rejected_for_other_modes(self):
        for flags in (("--forward-write",), ("--context", str(self.packet))):
            self.send(*flags, expect=2)
        self.assertFalse(self.calls())

    def test_exact_model_uses_current_invocation_not_cumulative_history(self):
        self.send("--model", "claude-sonnet-4-6", "--effort", "medium")
        self.behavior("mixed_usage")
        result, process = self.send("--model", "claude-opus-5-5", "--effort", "xhigh")
        call = self.sends()[-1]
        self.assertEqual((self.flag(call, "--model"), self.flag(call, "--effort")), ("claude-opus-5-5", "xhigh"))
        self.assertTrue(result["resumed"])
        self.assertTrue(result["model_verified"])
        self.assertFalse(result["effort_verified"])
        self.assertEqual(result["current_model"], "claude-opus-5-5")
        self.assertEqual(result["models_used"], ["claude-opus-5-5", "claude-sonnet-4-6"])
        self.assertEqual(result["model_usage_scope"], "cumulative_session")
        self.assertNoLeak(process)

    def test_model_mismatch_and_alias_are_reported_honestly(self):
        self.behavior("assistant_mismatch")
        data, _ = self.send("--model", "claude-opus-5-5", success=False)
        self.assertEqual((data["error"], data["assistant_models"]), ("model_mismatch", ["claude-sonnet-4-6"]))
        self.behavior("alias")
        alias, _ = self.send("--recover")
        self.assertEqual(self.flag(self.sends()[-1], "--model"), "opus")
        self.assertFalse(alias["model_verified"])
        self.assertEqual((alias["models_used"], alias["current_model"]), (["claude-opus-5-5"], "claude-opus-5-5"))

    def test_failures_mark_uncertain_hide_raw_output_and_never_retry(self):
        cases = [("fail", "claude_failed"), ("malformed", "invalid_response"), ("error_result", "claude_error"),
                 ("wrong_session", "session_changed"), ("wrong_model", "model_mismatch"),
                 ("max_turns", "max_turns_reached"), ("budget", "budget_exceeded")]
        self.send(topic="seed")
        for behavior, code in cases:
            with self.subTest(behavior=behavior):
                topic = "t-" + behavior
                self.behavior(behavior)
                count = len(self.sends())
                data, process = self.send("--new-topic-reason", "Separate failure case", "--model", "claude-opus-5-5",
                                          topic=topic, success=False)
                self.assertEqual(data["error"], code)
                self.assertEqual(len(self.sends()), count + 1)
                self.assertEqual(self.state()["topics"][topic]["state"], "uncertain")
                self.assertNoLeak(process)
                self.behavior("success")
                blocked, _ = self.send("--model", "claude-opus-5-5", topic=topic, success=False)
                self.assertEqual(blocked["error"], "uncertain_session")
                self.assertEqual(len(self.sends()), count + 1)

    def test_stderr_is_discarded_and_permission_denials_are_partial(self):
        self.behavior("stderr_flood")
        _, process = self.send()
        self.assertNoLeak(process)
        self.behavior("denied")
        data, process = self.send("--allow-tool", GRANT, mode="implement")
        self.assertEqual((data["permission_denial_count"], data["permission_denials"], data["partial"]),
                         (1, [{"tool_name": "Bash"}], True))
        self.assertNoLeak(process, "SENSITIVE_COMMAND")

    def test_default_project_is_current_working_directory(self):
        data, _ = self.send(project=False, cwd=str(self.project))
        self.assertEqual(data["project"], str(self.project))
        self.assertEqual(self.sends()[0]["cwd"], str(self.project))

    def test_discussion_cap_default_and_configured(self):
        for expected in (1, 2, 3):
            data, _ = self.send("--discussion-id", "plan-1", mode="discuss")
            self.assertEqual((data["discussion_send_count"], data["discussion_send_limit"]), (expected, 3))
        blocked, _ = self.send("--discussion-id", "plan-1", mode="discuss", success=False)
        self.assertEqual(blocked["error"], "discussion_limit")
        self.write_config({"limits": {"discussion_sends": 2}})
        blocked, _ = self.send("--discussion-id", "plan-1", mode="discuss", success=False)
        self.assertEqual(blocked["error"], "discussion_limit")
        self.write_config({"limits": {"discussion_sends": 5}})
        data, _ = self.send("--discussion-id", "plan-1", mode="discuss")
        self.assertEqual((data["discussion_send_count"], data["discussion_send_limit"]), (4, 5))
        self.assertEqual(len(self.sends()), 4)
        self.send(mode="implement")  # implementation does not consume the discussion budget
        self.assertEqual(self.state()["topics"]["topic-a"]["discussion_counts"], {"plan-1": 4})

    def test_output_limit_stops_process_without_echoing_content(self):
        self.write_config({"limits": {"output_bytes": 65536}})
        for index, behavior in enumerate(("big_output", "huge_line")):
            with self.subTest(behavior=behavior):
                self.behavior(behavior)
                started = time.monotonic()
                topic = "out-%d" % index
                extra = ("--new-topic-reason", "Separate output case") if index else ()
                data, process = self.send(*extra, topic=topic, success=False)
                self.assertEqual(data["error"], "output_limit")
                self.assertLess(time.monotonic() - started, 30)
                self.assertEqual(self.state()["topics"][topic]["state"], "uncertain")
                if POSIX:
                    self.assertEqual(data["cleanup"], "complete")
                self.assertNoLeak(process)

    def test_unread_large_stdin_still_honors_timeout(self):
        packet = self.root / "large.txt"
        packet.write_bytes(b"x" * (1536 * 1024))
        self.behavior("no_stdin")
        started = time.monotonic()
        data, _ = self.send("--timeout-seconds", "2", packet=packet, success=False)
        self.assertEqual(data["error"], "timeout")
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(self.state()["topics"]["topic-a"]["state"], "uncertain")

    @unittest.skipUnless(POSIX, "POSIX process groups and signals")
    def test_timeout_stops_process_group(self):
        self.behavior("timeout")
        data, _ = self.send("--timeout-seconds", "3", success=False)
        self.assertEqual((data["error"], data["cleanup"]), ("timeout", "complete"))
        self.assertTrue((self.claude_config / "child-started").exists())
        self.assertTrue((self.claude_config / "child-stopped").exists())
        self.assertEqual(self.state()["topics"]["topic-a"]["state"], "uncertain")

    @unittest.skipUnless(POSIX, "POSIX process groups and signals")
    def test_sigterm_cancels_and_stops_process_group(self):
        self.behavior("timeout")
        argv = [sys.executable, "-B", str(HELPER), "send", "--project", str(self.project), "--config",
                str(self.helper_config), "--state-dir", str(self.state_dir), "--topic", "topic-a", "--mode", "review",
                "--trigger", "explicit", "--packet", str(self.packet)]
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        deadline = time.monotonic() + 20
        while not (self.claude_config / "child-started").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue((self.claude_config / "child-started").exists())
        process.send_signal(signal.SIGTERM)
        stdout, _stderr = process.communicate(timeout=20)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(json.loads(stdout)["error"], "cancelled")
        self.assertTrue((self.claude_config / "child-stopped").exists())
        self.assertEqual(self.state()["topics"]["topic-a"]["state"], "uncertain")

    @unittest.skipUnless(POSIX, "shebang PATH discovery")
    def test_default_discovery_uses_claude_on_path(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        executable = bin_dir / "claude"
        executable.write_text("#!" + sys.executable + "\n" + FAKE, encoding="utf-8")
        executable.chmod(0o700)
        self.write_config({}, command=False)
        env = dict(self.env, PATH=str(bin_dir) + os.pathsep + self.env.get("PATH", ""))
        data, _ = self.send(env=env)
        self.assertTrue(data["ok"])

    def test_configured_wrapper_or_missing_command_is_rejected(self):
        wrapper = self.root / "claude.cmd"
        wrapper.write_text("@echo off\n", encoding="utf-8")
        self.write_config({"claude_command": [str(wrapper)]}, command=False)
        data, _ = self.send(success=False)
        self.assertEqual(data["error"], "windows_wrapper_unsupported")
        self.write_config({"claude_command": [str(self.root / "missing-claude")]}, command=False)
        data, _ = self.send(success=False)
        self.assertEqual(data["error"], "claude_not_found")
        self.assertFalse(self.calls())


class WindowsHelperTests(unittest.TestCase):
    """Windows-specific branches exercised with injected fakes; not a native Windows run."""

    def test_environment_allowlist_is_case_insensitive(self):
        environ = {"Path": "C:\\Windows", "SystemRoot": "C:\\Windows", "ComSpec": "C:\\Windows\\cmd.exe",
                   "PATHEXT": ".EXE", "UserProfile": "C:\\Users\\me", "APPDATA": "a", "LocalAppData": "b",
                   "TEMP": "t", "Tmp": "t2", "ProgramData": "p", "windir": "w",
                   "CLAUDE_CODE_GIT_BASH_PATH": "C:\\Git\\bin\\bash.exe", "Unrelated_Secret": "x",
                   "otel_exporter_otlp_endpoint": "y", "disable_telemetry": "0", "LC_ALL": "C"}
        env = helper.build_child_env(environ, windows=True, telemetry="inherit")
        for key in ("PATH", "SYSTEMROOT", "COMSPEC", "PATHEXT", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP",
                    "TMP", "PROGRAMDATA", "WINDIR", "CLAUDE_CODE_GIT_BASH_PATH"):
            self.assertIn(key, env)
        self.assertEqual(env["DISABLE_TELEMETRY"], "0")
        upper = {key.upper() for key in env}
        for name in ("UNRELATED_SECRET", "OTEL_EXPORTER_OTLP_ENDPOINT", "LC_ALL"):
            self.assertNotIn(name, upper)
        self.assertEqual(helper.build_child_env(environ, windows=True)["DISABLE_TELEMETRY"], "1")
        with self.assertRaises(helper.SessionError):
            helper.check_auth_environment({"anthropic_api_key": "x"}, "claude.ai", windows=True)
        helper.check_auth_environment({"anthropic_api_key": "x"}, "claude.ai", windows=False)

    def test_default_paths_follow_platform_conventions(self):
        environ = {"APPDATA": "C:\\Users\\me\\AppData\\Roaming", "LOCALAPPDATA": "C:\\Users\\me\\AppData\\Local",
                   "USERPROFILE": "C:\\Users\\me"}
        user = helper.default_user_config_path(environ, windows=True)
        state = helper.default_state_root(environ, windows=True)
        self.assertTrue(str(user).startswith(environ["APPDATA"]))
        self.assertEqual(user.parts[-2:], ("claude-collaborate", "config.json"))
        self.assertTrue(str(state).startswith(environ["LOCALAPPDATA"]))
        self.assertEqual(state.parts[-2:], ("claude-collaborate", "state"))
        posix = {"HOME": "/home/me", "XDG_STATE_HOME": "relative", "XDG_CONFIG_HOME": "/cfg"}
        self.assertEqual(helper.default_state_root(posix, windows=False),
                         Path("/home/me/.local/state/claude-collaborate"))
        self.assertEqual(helper.default_user_config_path(posix, windows=False),
                         Path("/cfg/claude-collaborate/config.json"))
        self.assertEqual(helper.default_state_root(dict(posix, XDG_STATE_HOME="/state"), windows=False),
                         Path("/state/claude-collaborate"))

    def test_resolve_native_executable_and_reject_wrappers(self):
        config = {"claude_command": None}
        native = {"claude.exe": "C:\\bin\\claude.exe", "claude.cmd": "C:\\npm\\claude.cmd"}
        self.assertEqual(helper.resolve_claude(config, windows=True, which=native.get), ["C:\\bin\\claude.exe"])
        wrapper_only = {"claude.cmd": "C:\\npm\\claude.cmd"}
        for which, code in ((wrapper_only.get, "windows_wrapper_unsupported"), ({}.get, "claude_not_found")):
            with self.assertRaises(helper.SessionError) as caught:
                helper.resolve_claude(config, windows=True, which=which)
            self.assertEqual(caught.exception.code, code)
        launcher = {"claude_command": ["C:\\node\\node.exe", "C:\\npm\\cli.js"]}
        self.assertEqual(helper.resolve_claude(launcher, windows=True, isfile=lambda path: True), launcher["claude_command"])
        with self.assertRaises(helper.SessionError) as caught:
            helper.resolve_claude({"claude_command": ["C:\\npm\\CLAUDE.BAT"]}, windows=True, isfile=lambda path: True)
        self.assertEqual(caught.exception.code, "windows_wrapper_unsupported")

    def test_windows_lock_uses_msvcrt_byte_range(self):
        class FakeMsvcrt:
            LK_NBLCK, LK_UNLCK = 2, 0

            def __init__(self):
                self.calls, self.busy = [], False

            def locking(self, fd, mode, length):
                self.calls.append((mode, length))
                if mode == self.LK_NBLCK and self.busy:
                    raise OSError(13, "locked")
        fake = FakeMsvcrt()
        with tempfile.TemporaryFile() as stream:
            helper.lock_fd(stream.fileno(), windows=True, module=fake)
            helper.unlock_fd(stream.fileno(), windows=True, module=fake)
            fake.busy = True
            with self.assertRaises(helper.LockBusy):
                helper.lock_fd(stream.fileno(), windows=True, module=fake)
        self.assertEqual(fake.calls, [(2, 1), (0, 1), (2, 1)])

    def test_windows_termination_uses_taskkill_tree(self):
        class FakeProcess:
            pid = 4321

            def __init__(self, code=None):
                self.code = code

            def poll(self):
                return self.code

            def wait(self, timeout=None):
                self.code = 1
                return 1

            def kill(self):
                self.code = 1
        calls = []

        def runner(returncode):
            def run(argv, **kwargs):
                calls.append((argv, kwargs))
                return SimpleNamespace(returncode=returncode)
            return run
        environ = {"SystemRoot": "C:\\Windows"}
        self.assertEqual(helper.terminate_tree(FakeProcess(), True, runner(0), environ), "complete")
        argv, kwargs = calls[-1]
        self.assertTrue(argv[0].endswith("taskkill.exe"))
        self.assertTrue(argv[0].startswith("C:\\Windows"))
        self.assertEqual(argv[1:], ["/PID", "4321", "/T", "/F"])
        self.assertNotIn("shell", kwargs)
        self.assertEqual(helper.terminate_tree(FakeProcess(), True, runner(128), environ), "incomplete")

        def broken(argv, **kwargs):
            raise OSError("missing")
        self.assertEqual(helper.terminate_tree(FakeProcess(), True, broken, environ), "incomplete")
        count = len(calls)
        self.assertEqual(helper.terminate_tree(FakeProcess(code=0), True, runner(0), environ), "incomplete")
        self.assertEqual(len(calls), count)

    def test_windows_atomic_replace_retries_transient_sharing_violation(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "state.json"
            target.write_bytes(b"old")
            real_replace = os.replace
            attempts = []

            def flaky(source, destination):
                attempts.append(1)
                if len(attempts) < 3:
                    raise PermissionError("file in use")
                return real_replace(source, destination)
            with mock.patch.object(helper.os, "replace", side_effect=flaky), mock.patch.object(helper.time, "sleep"):
                helper.atomic_write(target, b"new", windows=True)
            self.assertEqual((target.read_bytes(), len(attempts)), (b"new", 3))
            with mock.patch.object(helper.os, "replace", side_effect=PermissionError("denied")):
                with self.assertRaises(PermissionError):
                    helper.atomic_write(target, b"newer", windows=False)
            self.assertEqual(target.read_bytes(), b"new")
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ["state.json"])

    def test_windows_permission_anchors(self):
        self.assertEqual(helper.absolute_rule_path("C:\\Users\\me\\proj", True), "//c/Users/me/proj")
        self.assertEqual(helper.absolute_rule_path("D:/Work/项目 x", True), "//d/Work/项目 x")
        self.assertEqual(helper.absolute_rule_path("\\\\?\\C:\\x", True), "//c/x")
        self.assertEqual(helper.normalize_rule("Read(/src/**)", "project", "C:\\Users\\me\\proj", True),
                         "Read(//c/Users/me/proj/src/**)")
        with self.assertRaises(helper.SessionError) as caught:
            helper.absolute_rule_path("\\\\server\\share\\x", True)
        self.assertEqual(caught.exception.code, "unsupported_path")


if __name__ == "__main__":
    unittest.main()
