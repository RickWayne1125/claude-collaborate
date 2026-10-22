# Helper, configuration, and sessions

Use Python 3.9+ with the absolute path to this skill's `scripts/claude_session.py`: `python3` on macOS/Linux, and `python` or `py -3` on Windows. Each command prints exactly one ASCII JSON object on stdout. Check the exit status and `ok`/`error`, not just nonempty output. Progress notes go to stderr. The helper never installs Claude Code, logs in, reads credential files, or switches billing paths.

```sh
python3 <skill-dir>/scripts/claude_session.py config [--config <file>]
python3 <skill-dir>/scripts/claude_session.py doctor --project <absolute-project-path>
python3 <skill-dir>/scripts/claude_session.py status --project <absolute-project-path>
python3 <skill-dir>/scripts/claude_session.py send --project <absolute-project-path> --topic <slug> --mode <mode> --trigger explicit|auto --packet <file>
python3 <skill-dir>/scripts/claude_session.py migrate-legacy --project <absolute-project-path> [--dismiss]
```

- `config` shows effective settings, their sources, `auto_consult`, and `routing`. It calls nothing.
- `doctor` checks the executable, required isolation flags, login method, and permission-import summary. It sends no inference and creates no state.
- `status` lists known topics, session IDs, states, discussion counts, and legacy-registry status. It calls nothing.

All commands accept `--project` (default: current directory), `--config <file>`, `--no-user-config`, and `--state-dir <dir>`.

## Configuration

Precedence is built-in defaults < per-user file < explicit `--config` < command-line flags. The per-user file is `$XDG_CONFIG_HOME/claude-collaborate/config.json` (default `~/.config/claude-collaborate/config.json`) on macOS/Linux, and `%APPDATA%\claude-collaborate\config.json` on Windows. Project-local configuration is never loaded automatically. Pass `--config` only for a file the user chose.

Configuration files are trusted because they can select executables. On POSIX they must be owned by you and not writable by group or others. Never put credentials or private prompts in them. The file is strict JSON with `"version": 1`. Unknown keys, duplicate keys, wrong types, or out-of-range values stop the helper with `config_invalid`. Every key except `version` is optional.

| Key | Default | Accepted values |
| --- | --- | --- |
| `model` | `"opus"` | Model name or alias; aliases are reported as unverified resolution |
| `effort` | `"high"` | `low`, `medium`, `high`, `xhigh`, `max` |
| `auto_consult` | `false` | `true` lets Codex consult Claude without an explicit request (`--trigger auto`) |
| `access` | `"project"` | `project` (scoped file tools) or `packet` (no tools) |
| `auth` | `"claude.ai"` | `claude.ai` or `api-key` |
| `telemetry` | `"off"` | `off` or `inherit` |
| `routing.simple` / `.moderate` / `.complex` | `direct` / `auto` / `discuss-implement` | `direct`, `auto`, `cross-validate`, `review`, `discuss`, `discuss-implement` |
| `limits.packet_bytes` | `2097152` | 1 B–64 MiB per packet or context file |
| `limits.output_bytes` | `67108864` | 64 KiB–1 GiB of Claude stream output per call |
| `limits.timeout_seconds` | `900` | 1–7200 |
| `limits.discussion_sends` | `3` | 1–20 sends per discussion ID |
| `limits.max_turns` | `null` | `null` or 1–1000, passed as `--max-turns` |
| `limits.max_budget_usd` | `null` | `null` or a positive amount up to 10000, passed as `--max-budget-usd` |
| `permissions.extra_deny` | `[]` | Extra deny rules using `//absolute`, `~/home`, or project-relative paths; concatenated across files |
| `claude_command` | `null` | Trusted argv list; the first item must be an absolute path and not `.cmd`, `.bat`, or `.ps1` |
| `state_dir` | `null` | Absolute path for helper state |

Command-line overrides on `send`: `--model`, `--effort`, `--access`, `--auth`, `--timeout-seconds`, `--max-turns`, `--max-budget-usd`, and `--state-dir`. `doctor` also accepts `--auth`.

The compatibility profile restores the earlier personal experience: a pinned model, `xhigh` effort, and automatic routing. To use it, copy this to the per-user file, or pass it with `--config`. The selected model and effort must be supported by the installed CLI and account; use `doctor` and inspect the actual invocation result.

```json
{"version": 1, "model": "claude-opus-5-5", "effort": "xhigh", "auto_consult": true,
 "telemetry": "off", "limits": {"discussion_sends": 3, "timeout_seconds": 900}}
```

## Authentication, data flow, and privacy

- **`claude.ai`** uses the existing local Claude Code login. The helper refuses to run when any of these are set: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_BASE_URL`, or `CLAUDE_CODE_USE_BEDROCK` / `_VERTEX` / `_FOUNDRY`. It names the variables, never their values.
- **`api-key`** reads only `ANTHROPIC_API_KEY` from the helper's environment, never from configuration or argv. It passes the key only to Claude and requires `auth status` to report API-key authentication. Other credential and provider variables are still refused.
- Bedrock, Vertex, Foundry, and custom gateways are unsupported. There is no silent billing, provider, or login fallback.
- Each topic is bound to the account identity and the Claude configuration directory. The binding is an HMAC under a private random key in the state directory, computed from email plus organization, or from the API key. Resuming after a change of account, key, profile, or configuration directory stops with `account_changed` or `config_store_changed`. Rotating an API key therefore intentionally prevents resuming its earlier sessions. Identity values are never stored or printed.
- The child process gets an allowlisted environment, never the whole parent environment. It receives paths, locale, proxies, CA settings, and the Windows system variables, including `CLAUDE_CODE_GIT_BASH_PATH`.
- With `telemetry: "off"`, these are set to `1`: `DISABLE_TELEMETRY`, `DISABLE_ERROR_REPORTING`, `DO_NOT_TRACK`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY`, and `DISABLE_FEEDBACK_COMMAND`. With `inherit`, those keys keep their exact process values, or else the values from the user's Claude settings `env`. Other telemetry or exporter variables are not forwarded. None of this stops the task itself from reaching the model service.
- Data flow: the packet, the context file, resumed history, and project files Claude reads go to the model service. Claude Code keeps its own transcripts under its configuration directory, and the helper preserves the user's `cleanupPeriodDays`. Helper state stores no prompts or answers. Removing it neither deletes transcripts nor revokes sent data.

## Permissions and isolation

Every call uses `--safe-mode`, `--restricted`, `--permission-mode dontAsk`, and `--permission-prompts none`. Hooks, MCP servers, slash commands, Chrome, and automatic `CLAUDE.md` loading are disabled. Restricted mode ignores user, project, and local settings, so the helper re-supplies only the following through `--settings`:

- **Imported deny and ask rules** come from the user's Claude `settings.json` and from this project's `.claude/settings.json` and `.claude/settings.local.json`. Parent directories are not searched. Ask rules become deny rules; under `dontAsk` they would be denied anyway.
- **Anchors are preserved.**
  - A single leading `/path` from user settings is rebased under the Claude configuration directory.
  - A single leading `/path` from project or local settings is rebased under the project.
  - `//absolute` and `~/home` patterns are unchanged.
  - Bare and `./` patterns stay relative to the project working directory.
  - Windows drives become `//c/...`.
- **Fail-closed checks** stop the run before any request. They cover malformed JSON or types, negated `!` patterns, path rules for `Glob`, `Write`, `NotebookEdit`, or `MultiEdit` (use `Read(...)` / `Edit(...)`), drive-letter rule paths, and control characters in project paths. A nonempty `sandbox` policy in any source stops with `unsupported_sandbox_policy`, except an explicit `{"enabled":false}`. Empty `{}` is also inactive; other policy fields cannot be silently discarded. Do not delete the policy to continue; use host or OS isolation.
- **Baseline denies** cover `Read` and `Edit` of `.env`, `.env.*`, `.ssh`, `.aws`, `.kube/config`, `.docker/config.json`, `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, `id_rsa`, `id_ed25519`, and `secrets/` in the project and home. They also deny `Edit` under `.git`, `.claude`, `.codex`, and `.agents`, plus any access to the helper state directory. Extend the list with `permissions.extra_deny`.
- **Allow rules** are `Read(//<project>/**)`; write modes add `Edit(//<project>/**)` and the exact `Bash(...)` grants. There are no bare tool grants and no extra directories. Managed organization policy still applies.

These are Claude file rules, not an OS sandbox. Any permitted command or test can read, write, or reach the network as you. Deny patterns do not sanitize packet text or Claude's answers.

Command grants (`--allow-tool`, write modes only) must be exact: `Bash(<command>)`, one per command. The helper rejects:

- wildcards, `:*` prefixes, and shell metacharacters (`; & | < > $` and backticks, parentheses, braces, brackets, `,`, `!`)
- shells and wrappers (`sh`, `bash`, `cmd`, `powershell`, `env`, `xargs`, `sudo`, and similar)
- `VAR=value` prefixes
- bare interpreters, and inline code such as `python -c`, `node -e`, `ruby -e`, `perl -e`, or `php -r`

Example: `--allow-tool 'Bash(python3 -B -m unittest discover -s tests -v)'`.

## Topics, state, and sessions

State lives outside the project by default. It is in `$XDG_STATE_HOME/claude-collaborate`, or `~/.local/state/claude-collaborate`, on macOS/Linux, and in `%LOCALAPPDATA%\claude-collaborate\state` on Windows. `--state-dir` or `state_dir` changes it, for example for tests or CI. On POSIX, directories are `0700`, files are `0600`, and ownership is checked and all group/other access is rejected. On Windows the directory relies on the inherited per-user profile ACL. Links are refused, and writes are atomic. State is keyed by the canonical project path. For each topic it records the session UUID, state, account binding, configuration directory, and counters, with no prompt text and no free-text topic reasons.

1. Reuse the recorded topic slug exactly for related work, even across mode changes. Any known topic resumes its own session; there is no history truncation.
2. The first topic in a project needs no reason. A different new topic needs `--new-topic-reason '<concrete distinction>'`, which is checked but not stored. If the topic slug is unknown, the error lists the recent known topics; pick the right one rather than creating a duplicate.
3. One project-wide lock serializes helper calls, and a second caller gets `session_busy`. Avoid resuming the same session in a separate Claude terminal; the helper cannot coordinate external writers.
4. The helper does not scan or adopt arbitrary Claude transcripts. It checks only that the transcript filename `<uuid>.jsonl` exists; it never reads transcript content.

**Earlier project-local helper.** If `<project>/.claude/codex-collaborate.json` exists, `send` stops with `legacy_registry_present`. Run `migrate-legacy` once to import its topics, or `migrate-legacy --dismiss` to continue without them.

Migration validates the old format, project path, and configuration directory. Each `ready` session needs its transcript file. Migration binds the topics to the current account, keeps discussion counts, never modifies the old files, and refuses conflicting topics. The account that originally created a legacy session cannot be verified, which is reported as `account_origin_verified: false`. If the old registry changes after migration, `send` stops again. Migration, dismissal, and sends also acquire the existing legacy lock, in new-lock → legacy-lock order. No missing legacy lock is created. Do not run the old and new tools concurrently; they cannot coordinate an external writer that does not honor the existing lock.

## Sending

Prepare each packet as a UTF-8 file. Use a private temporary file for short-lived packets and remove it afterward. Bytes are passed through unchanged, including CRLF.

In `forward` mode, `--packet` is the verbatim original request, and the optional `--context <file>` holds separate project context. `--context` and `--forward-write` are forward-only. `--discussion-id` is required in, and limited to, `discuss` mode.

```sh
python3 <skill-dir>/scripts/claude_session.py send \
  --project <absolute-project-path> --topic <stable-topic-slug> --trigger explicit \
  --mode discuss --discussion-id <stable-discussion-slug> --packet <packet.txt>

python3 <skill-dir>/scripts/claude_session.py send \
  --project <absolute-project-path> --topic <same-topic-slug> --trigger explicit \
  --mode implement --packet <handoff.txt> \
  --allow-tool 'Bash(python3 -B -m unittest discover -s tests -v)'
```

Successful JSON includes `answer`, `session_id`, `resumed`, `new_session`, `requested_model`, `requested_effort`, `current_model`, `models_used` (cumulative), `model_verified`, `permission_denials` (tool names only), `permission_denial_count`, `partial`, and the discussion count and limit.

## Model, effort, and result verification

The configured or overridden model and effort are passed explicitly on every call. The helper verifies the current invocation using the stream's `init` and assistant-message metadata. Resumed `modelUsage` is cumulative and cannot prove which model answered this turn.

A pinned `claude-*` request must match exactly, or the call fails with `model_mismatch`. An alias is reported with `model_verified: false`, meaning resolution is unverified. Effort is requested, but the CLI does not attest it (`effort_verified: false`); organization settings may constrain it. A missing model or unsupported effort is a surfaced failure, never permission to downgrade.

The required flags were checked against Claude Code 2.1.290. Run `doctor` rather than assuming a release has them. `--max-turns` and `--max-budget-usd` may be absent from `--help` and still work, so `doctor` reports them without rejecting. Do not auto-upgrade the user's installation.

## Failure handling

**Timeouts, cancellation, and bad results.** Any timeout, cancellation, output overflow, malformed result, session or model mismatch, turn or budget limit, or other inference failure marks the topic `uncertain` and keeps its UUID. The request may already have reached Claude or changed files. **There is no automatic resend or fresh-session retry.**

**Deliberate recovery.** Inspect the diff and test artifacts first, then use `--recover` deliberately. Recovery resumes the transcript when its file exists. If the first attempt never created a transcript, recovery reuses the same UUID. A session that previously succeeded but whose transcript is gone stops with `transcript_missing`.

**Process cleanup.**
- On POSIX, the helper stops the process group; on Windows, it runs `taskkill /T /F` on the process tree.
- Errors report `cleanup: "complete"` only when stopping was verified.
- An `incomplete` cleanup, or a forcibly killed helper, can leave descendants running. On Windows, an already exited parent prevents `taskkill` from verifying its former process tree; cleanup is reported as incomplete. A final result does not bypass the output-reader deadline.

**Partial work.** `max_turns_reached`, `budget_exceeded`, and permission denials mean partial work. The USD budget uses the CLI's estimate, not an exact billing ceiling. Resolve only actions justified by the existing authority; do not widen permissions just to silence a denial.

**Errors stop before sending.**
- `auth_*`, `login_required`, `settings_invalid`, `unsupported_*`, `config_*`, `invalid_state`, `account_changed`, `legacy_registry_present`, `session_busy`, and `discussion_limit` all stop before anything is sent.
- Report the concrete limitation and preserve completed Codex work.
- Raw stderr, auth output, environment values, tool inputs, and transcript content are never printed.

## Platforms

- macOS and Linux use the `claude` executable on `PATH`, `fcntl` locks, and process groups.
- Windows needs native `claude.exe`. A `.cmd`, `.bat`, or `.ps1` launcher is refused (`windows_wrapper_unsupported`). Instead, set `claude_command` to `["C:\\path\\node.exe", "C:\\path\\to\\cli.js"]`.
- Windows uses `msvcrt` byte-range locks and `taskkill /T /F`. Claude's Bash tool there may need Git Bash (`CLAUDE_CODE_GIT_BASH_PATH`).
- WSL counts as Linux. Do not mix a Windows executable with Linux paths.
- Offline tests use a fake CLI. They do not prove live model access, billing, or native Windows behavior.

## Official references

- [CLI reference](https://code.claude.com/docs/en/cli-reference): print mode, tools, permissions, and resume flags.
- [Programmatic usage](https://code.claude.com/docs/en/headless): JSON results and session continuation.
- [Model configuration](https://code.claude.com/docs/en/model-config): model identifiers and effort levels.
- [Permissions](https://code.claude.com/docs/en/permissions#read-and-edit): Read/Edit path anchors and limitations.
- [Settings](https://code.claude.com/docs/en/settings): settings files, `cleanupPeriodDays`, and sandbox settings.
- [Environment variables](https://code.claude.com/docs/en/env-vars): authentication and telemetry controls.
- [Data usage](https://code.claude.com/docs/en/data-usage): what is sent and retained.
- [Usage across resumed sessions](https://code.claude.com/docs/en/agent-sdk/cost-tracking#accumulate-costs-across-multiple-calls): cumulative model-usage metadata.
