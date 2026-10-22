# Configuration

Configuration controls collaboration preferences and local execution boundaries. It must not contain credentials. A setting does not authorize sharing private material, changing files, or taking external actions beyond the user's request.

## Quick start

The examples below run from this source repository's root. They use `--project .` to select that directory; replace `.` with another existing project when appropriate. After installing the skill, substitute the installed helper's path. Options go **after** the subcommand.

Inspect the built-in configuration without loading your personal helper configuration:

```sh
python skills/claude-collaborate/scripts/claude_session.py config --no-user-config
```

Check the local CLI and selected login without sending an inference request:

```sh
python skills/claude-collaborate/scripts/claude_session.py doctor --project .
```

Save the request in a nonempty UTF-8 file named `request.txt`. For example:

```text
Explain the difference between a unit test and an integration test, with one small example of each.
```

Then send it explicitly in forward mode:

```sh
python skills/claude-collaborate/scripts/claude_session.py send --project . --topic testing-basics --mode forward --trigger explicit --access packet --packet request.txt
```

This last command sends a real model request and can consume account usage. The result is a JSON object; `answer` contains Claude's unchanged answer. JSON escaping is transport encoding, not an edit to the answer. Operational fields such as `partial` and `permission_denial_count` must be considered separately. Ordinary failures return nonzero with an error category; do not interpret an incomplete run as success.

## Configuration files and precedence

Precedence is built-ins, then the per-user helper configuration, then explicit `--config`, then supported command-line overrides. `--no-user-config` skips the per-user **helper** configuration; it does not discard Claude's permission policy.

| Platform | Default helper configuration | Default helper state |
| --- | --- | --- |
| macOS/Linux | `$XDG_CONFIG_HOME/claude-collaborate/config.json`, otherwise `~/.config/claude-collaborate/config.json` | `$XDG_STATE_HOME/claude-collaborate`, otherwise `~/.local/state/claude-collaborate` |
| Windows | `%APPDATA%/claude-collaborate/config.json` | `%LOCALAPPDATA%/claude-collaborate/state` |

Only absolute XDG overrides are used. Windows falls back to the corresponding `AppData/Roaming` or `AppData/Local` directory under the user profile. There is no automatically loaded project-local helper configuration. `CLAUDE_CONFIG_DIR` still selects Claude's own configuration store.

Every configuration file must include `"version": 1`. Unknown keys, duplicate keys, invalid types, and out-of-range values are errors. Files can override only the fields they need. On POSIX they must be owned by the current user or root and not be writable by group or others; on Windows protect them with the account's filesystem ACLs. Configuration can select an executable, so treat it as trusted code.

A complete general-purpose configuration is:

```json
{
  "version": 1,
  "model": "opus",
  "effort": "high",
  "auto_consult": false,
  "access": "project",
  "auth": "claude.ai",
  "telemetry": "off",
  "routing": {
    "simple": "direct",
    "moderate": "auto",
    "complex": "discuss-implement"
  },
  "limits": {
    "packet_bytes": 2097152,
    "output_bytes": 67108864,
    "timeout_seconds": 900,
    "discussion_sends": 3,
    "max_turns": null,
    "max_budget_usd": null
  },
  "permissions": {"extra_deny": []},
  "claude_command": null,
  "state_dir": null
}
```

Save a personal configuration outside the source tree, or keep it locally ignored. To inspect an explicit profile from this repository:

```sh
python skills/claude-collaborate/scripts/claude_session.py config --no-user-config --config profiles/compatible.json
```

The compatible profile uses `claude-opus-5-5`, `xhigh`, and `auto_consult: true`, with the same default routing and three-message discussion limit. Selecting it explicitly opts into automatic collaboration. It does not change Codex's model or reasoning effort. To customize only automatic use, a valid minimal configuration is `{"version":1,"auto_consult":true}`.

`routing` is guidance for the calling Codex skill; the helper still requires a concrete `--mode`. Each routing tier accepts `direct`, `auto`, `cross-validate`, `review`, `discuss`, or `discuss-implement`. The default keeps simple explanations with Codex, chooses a mode for moderate tasks, and discusses before implementing complex development. A request not to use Claude always takes precedence.

Nested `routing` and `limits` objects merge by field. `permissions.extra_deny` adds restrictions across layers; a later profile cannot remove earlier deny rules. Other fields replace their earlier value.

## Modes and request files

Every send requires `--trigger explicit` when the user requested Claude, or `--trigger auto` when Codex selected collaboration. Automatic use requires `auto_consult: true`. This is a workflow gate, not proof of human consent: a caller can set the flag itself. Authorization must still come from the user's request and applicable policy.

The current project is the process's working directory unless `--project` selects another existing directory. A Git root, parent folder, or other checkout is not substituted silently. All modes use this same directory.

Examples use the topic `feature-plan` for related work. If your registry already has unrelated topics, supply `--new-topic-reason` when creating this topic. Create each named packet as a UTF-8 file containing the material indicated below.

| Mode | Packet contents | Additional behavior |
| --- | --- | --- |
| `cross-validate` | Original request, relevant facts and constraints; keep Codex's proposed answer out of the packet | Codex retains its own answer and compares independent results. |
| `review` | Original request, context, Codex's draft, and acceptance criteria | Codex checks Claude's critique before revising. |
| `discuss` | Initial plan or the next specific question, plus necessary context | Keep the same `--discussion-id` across rounds. |
| `implement` | Final authorized plan, permitted files, acceptance criteria and checks | Edits are enabled; each shell command still needs an exact grant. |
| `forward` | The original user request verbatim | Optional `--context` is separate; no Codex draft or plan is required. |

```sh
python skills/claude-collaborate/scripts/claude_session.py send --project . --topic feature-plan --mode cross-validate --trigger explicit --packet independent-question.txt
python skills/claude-collaborate/scripts/claude_session.py send --project . --topic feature-plan --mode review --trigger explicit --packet review-packet.txt
python skills/claude-collaborate/scripts/claude_session.py send --project . --topic feature-plan --mode discuss --trigger explicit --discussion-id design-1 --packet discussion-round-1.txt
python skills/claude-collaborate/scripts/claude_session.py send --project . --topic feature-plan --mode implement --trigger explicit --packet implementation-plan.txt --allow-tool "Bash(python -m unittest discover -s tests)"
python skills/claude-collaborate/scripts/claude_session.py send --project . --topic feature-plan --mode forward --trigger explicit --packet request.txt --context project-context.txt
```

These are separate workflow examples, not a requirement to run every mode for one task. Replace a test grant with the exact command appropriate to the project. For an authorized forwarded request that includes changes or tests, add `--forward-write` and any needed `--allow-tool` grants. `--context` and `--forward-write` are valid only in forward mode.

With `--access project` (the default), read-only modes expose `Read`, `Glob`, and `Grep`; write-enabled modes also expose `Edit`, `Write`, and `Bash`. File permissions are scoped to the selected project, subject to deny rules. `--access packet` supplies no tools and cannot be combined with `implement`, `--forward-write`, or command grants. It does not erase context from a resumed session; the prompt still includes the project path and topic metadata.

## Authentication and executable selection

`auth` accepts exactly `claude.ai` or `api-key`. Override it for a single preflight or send with `--auth`.

- `claude.ai` uses the existing local Claude.ai login. The helper rejects conflicting API keys, OAuth-token overrides, and custom provider routing instead of silently changing billing.
- `api-key` requires `ANTHROPIC_API_KEY` in the helper's environment and verifies that the CLI selected API-key authentication. The key must not appear in configuration, command-line arguments, or issue reports.

After securely setting `ANTHROPIC_API_KEY` in the process environment, test the selected authentication path without inference:

```sh
python skills/claude-collaborate/scripts/claude_session.py doctor --project . --auth api-key
```

Only the first-party Anthropic provider is supported. The helper does not log in, purchase usage, or fall back to another method. Custom base URLs, Bedrock, Vertex, Foundry, and token-based overrides are rejected. A login that does not report a stable identity cannot safely bind resumable sessions and is rejected.

By default the helper resolves `claude` on POSIX or native `claude.exe` on Windows. A trusted `claude_command` can instead be a list beginning with an absolute executable path, followed by fixed arguments. For example, an explicit Node installation can use:

```json
{
  "version": 1,
  "claude_command": ["C:/Tools/node.exe", "C:/Tools/claude/cli.js"]
}
```

Replace both paths with real installed files; this example does not install them. The list is not shell text: pipes, redirects, or variable syntax are not expanded by the helper. `.cmd`, `.bat`, and `.ps1` are rejected as the first program. See [Platforms](platforms.md).

## Permissions and privacy policy

The helper runs Claude in restricted mode and explicitly passes a merged permission policy. It imports deny and ask rules from Claude's user `settings.json`, project `.claude/settings.json`, and local `.claude/settings.local.json`. Imported ask rules become deny rules because this noninteractive workflow cannot prompt for them. Broad allow rules, hooks, arbitrary environment changes, and MCP configuration are not imported. Managed policy can still apply.

`Read(...)` and `Edit(...)` express path rules. Unsupported path-bearing `Glob`, `Write`, `NotebookEdit`, and `MultiEdit` rules are rejected. For imported Read/Edit rules:

- Unanchored `path` and `./path` remain relative to the working directory.
- `/path` is rebased from its source: Claude's configuration directory for user rules, or the selected project for project/local rules.
- `//absolute` and `~/home-relative` retain their meanings.
- Negated patterns beginning with `!` are rejected because combining sources can broaden their effect.

`permissions.extra_deny` accepts additional rules, for example `{"version":1,"permissions":{"extra_deny":["Read(**/customer-data/**)","Edit(**/customer-data/**)"]}}`. Use project-relative, `~/`, or `//` paths here; single-leading-slash patterns have no source anchor in helper configuration and are rejected.

The baseline denies Read/Edit access to `.env`, `.env.*`, `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, common SSH key filenames, `.kube/config`, `.docker/config.json`, and `.ssh`, `.aws`, and `secrets` directories. It also protects writes under `.git`, `.claude`, `.codex`, and `.agents`, and denies Read/Edit access to the helper state directory. These filename rules are not a secret scanner; the configuration can add denies but cannot remove the baseline.

An existing sandbox policy must not silently disappear during selective import. Empty sandbox configuration or an explicit `{"enabled":false}` is inactive; other nonempty sandbox policies stop with `unsupported_sandbox_policy`. Use supported host isolation rather than removing a policy just to continue.

`--allow-tool` accepts only exact `Bash(command)` grants in a write-enabled mode. Wildcards, shell operators, environment-assignment prefixes, shell wrappers, bare interpreters, and recognized inline-code forms are rejected. Grants do not inspect the called program: even a named test script can read files, access the network, or write data. These rules are not an OS sandbox.

`telemetry: "off"` is the default in both profiles. It sets supported telemetry/reporting opt-outs for the child process. `"inherit"` preserves those variables' exact values, preferring the parent environment over selected user Claude settings. It does not forward the whole environment or all telemetry exporter settings. Some opt-outs treat any nonempty value, including `0`, as enabled; they must not be normalized to one shared Boolean rule. Inference still goes to the provider. See [Privacy](privacy.md).

## Limits and model metadata

| Setting | Default | Accepted range |
| --- | --- | --- |
| `limits.packet_bytes` | 2 MiB | 1 byte–64 MiB, per packet or separate context file |
| `limits.output_bytes` | 64 MiB | 64 KiB–1 GiB, captured Claude output |
| `limits.timeout_seconds` | 900 | 1–7200 seconds |
| `limits.discussion_sends` | 3 | 1–20 sends per discussion ID |
| `limits.max_turns` | `null` | `null`, or 1–1000 agentic turns per call |
| `limits.max_budget_usd` | `null` | `null`, or a positive finite number up to 10000 |

Per-send overrides are `--timeout-seconds`, `--max-turns`, and `--max-budget-usd`. There is no default USD or agentic-turn limit when these values are `null`; timeout and size limits still apply. Discussion sends count attempts that may have reached Claude, including uncertain attempts. Internal agentic turns are a different unit from discussion messages.

The USD control uses Claude's estimated API cost and is not an exact billing ceiling. A limit or timeout can end a request after partial work. Inspect state and file changes before recovery; do not automatically replay implementation.

`--model` and `--effort` override a send's requested model and effort. Effort accepts `low`, `medium`, `high`, `xhigh`, or `max`; support depends on the selected CLI/account/model. The helper does not silently substitute a different model or lower effort.

For exact model IDs beginning with `claude-`, verification uses the current invocation's initialization and available assistant metadata. For aliases such as `opus`, the helper reports the resolved `current_model` but does not claim an independently verified alias mapping. `models_used` is cumulative session metadata, not evidence that all those models ran this turn. `effort_verified` remains false: sending a CLI flag does not attest the server's actual reasoning effort.

## Session state, migration, and recovery

Inspect recorded topics without invoking Claude:

```sh
python skills/claude-collaborate/scripts/claude_session.py status --project .
```

Related requests keep the same `--topic` across modes. The first topic is created automatically. A new topic after that requires a nonempty `--new-topic-reason` describing a genuinely different task; returning to a known topic needs no reason. Topic and discussion identifiers are 1–100 characters, with letters, digits, underscores, dots, or hyphens and no spaces or slashes. Chinese characters are accepted. Topic records are not pruned to a fixed recent-history count, although the state file has a size limit.

State binds canonical project identity, topic/session IDs, discussion counts, authentication identity, and Claude's configuration store. Account identifiers and API keys are represented by keyed fingerprints rather than stored verbatim. API-key rotation intentionally changes the binding. Changing identity or store does not silently resume an earlier session. Select another private state directory with an absolute `state_dir` in configuration or `--state-dir`; protect it as personal data. POSIX state directories and files require owner-only permissions (normally `0700` and `0600`); Windows relies on the per-user ACL.

The helper checks a recorded session's transcript filename when deciding whether it can resume. It does not read transcript contents to discover or adopt unrelated sessions. An already-started session whose transcript is missing stops with `transcript_missing`; no replacement UUID is silently created. Claude's user `cleanupPeriodDays` setting is preserved, but a retained topic record does not guarantee its transcript still exists.

A legacy project-local registry causes normal sends to stop until it is explicitly handled. After confirming that the old sessions belong to the same account and project, migrate with:

```sh
python skills/claude-collaborate/scripts/claude_session.py migrate-legacy --project .
```

Migration validates and locks state, imports recorded identities and discussion counts, and leaves the old registry intact. Normal sends also hold the legacy lock when needed so the older helper cannot use that registry concurrently. The old format did not bind accounts: `account_origin_verified: false` states that the helper cannot independently prove the historic account. If you deliberately want to leave the old sessions unused, record that decision instead:

```sh
python skills/claude-collaborate/scripts/claude_session.py migrate-legacy --project . --dismiss
```

Neither operation deletes Claude transcripts or the old registry. A changed legacy file requires another explicit decision.

An interrupted or failed send becomes `uncertain`. Inspect `status`, the project diff, and available Claude records before deciding to continue. Add `--recover` to the same intended send only after that inspection. Recovery preserves the recorded UUID; it is not an automatic rollback or a guarantee against duplicated work. Do not reset a discussion ID merely to evade its send budget.

Deleting the helper registry does not remove Claude's transcripts or revoke data already sent. See [Privacy](privacy.md) for retention and reporting boundaries.

## References

- [Claude CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Permission rules](https://code.claude.com/docs/en/permissions)
- [Authentication and environment variables](https://code.claude.com/docs/en/env-vars)
