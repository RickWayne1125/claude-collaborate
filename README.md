# Claude Collaborate

A Codex skill for working with a locally installed Claude Code CLI. Codex can compare an independent answer, request a review, discuss an approach, delegate implementation, or forward a request and relay Claude's answer unchanged.

[简体中文](README.zh-CN.md) · [Configuration](docs/configuration.md) · [Privacy](docs/privacy.md) · [Platforms](docs/platforms.md)

## What it does

| Mode | Workflow |
| --- | --- |
| `cross-validate` | Codex produces an answer, Claude solves the same problem independently, and Codex presents the meaningful differences and supporting evidence. |
| `review` | Claude reviews Codex's draft against the original request; Codex checks the feedback and revises the result. |
| `discuss` | Codex and Claude refine a plan, with a default limit of three messages sent to Claude per discussion (configurable). |
| `implement` | Claude carries out an authorized plan and runs permitted checks; Codex verifies the resulting changes and test evidence. |
| `forward` | Send the original request verbatim and return Claude's answer unchanged, keeping operational limitations separate. |

The skill supports English and Chinese. Every mode works in the same current project directory and can inspect relevant project files. Project file access is the default. Implementation mode, or forwarding with `--forward-write`, enables edits and scoped shell commands for work the user has authorized. Use `--access packet` to disable project tools while retaining the supplied text and saved session context; the prompt still identifies the project and topic.

Related work reuses a recorded Claude session across mode changes. Unrelated topics can have separate sessions, and returning to a topic reuses its recorded identity. State belongs in the user's state directory, outside the project by default. The helper does not discover or adopt unrelated Claude sessions automatically.

## Requirements

- Python 3.9 or later.
- A supported local Claude Code installation and the authentication method you intend to use.
- Codex with local skills support, if using the skill through Codex.
- Permission to send the selected task material to Claude.

The general defaults are model alias `opus` and effort `high`. An alias can resolve differently as Claude or the selected provider changes. `profiles/compatible.json` preserves the earlier pinned `claude-opus-5-5` / `xhigh` preferences and automatic mode routing. Model availability remains account-dependent.

Local CLI execution still sends prompts, selected history, and file contents used by Claude to its configured model service. Read [Privacy](docs/privacy.md) before using it on private repositories.

## Install the skill

### 1. Get the source

```sh
git clone https://github.com/RickWayne1125/claude-collaborate.git
cd claude-collaborate
```

Without Git, select **Code → Download ZIP** on the [repository page](https://github.com/RickWayne1125/claude-collaborate), extract it, and open a terminal in the extracted repository folder. The commands below run from that folder.

Install and authenticate Claude Code using its [official setup instructions](https://code.claude.com/docs/en/overview). This repository does not install Claude Code or change your login. Use Python 3.9 or later; the examples use `python3` on macOS/Linux and `py -3` on Windows. If your installation uses `python`, substitute that command.

### 2. Copy the skill into Codex

The recommended per-user location is `~/.agents/skills/claude-collaborate`, following the [official Codex skills guide](https://learn.chatgpt.com/docs/build-skills). These examples stop if an installation already exists. Compare or back up an older installation before replacing it yourself.

For an older Codex installation that already discovers skills in `$CODEX_HOME/skills` or `~/.codex/skills`, set the skill-root variable below to that existing directory. Do not install the same skill in multiple discovery locations.

**macOS / Linux**

```sh
collaborate_skill_root="$HOME/.agents/skills"
collaborate_skill_dir="$collaborate_skill_root/claude-collaborate"
if [ -e "$collaborate_skill_dir" ] || [ -L "$collaborate_skill_dir" ]; then
  printf 'An installation already exists: %s\n' "$collaborate_skill_dir" >&2
else
  mkdir -p "$(dirname "$collaborate_skill_dir")"
  cp -R skills/claude-collaborate "$collaborate_skill_dir"
fi
```

**Windows PowerShell**

```powershell
$collaborateSkillRoot = Join-Path $HOME '.agents/skills'
$collaborateSkillDir = Join-Path $collaborateSkillRoot 'claude-collaborate'
if (Get-Item -LiteralPath $collaborateSkillDir -Force -ErrorAction SilentlyContinue) {
    throw "An installation already exists: $collaborateSkillDir"
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $collaborateSkillDir) | Out-Null
Copy-Item -LiteralPath 'skills/claude-collaborate' -Destination $collaborateSkillDir -Recurse
```

The installed folder must directly contain `SKILL.md`, `scripts/`, `references/`, and `agents/`. Keep the checkout if you want the example profiles and extended documentation. Reopen Codex if the new skill is not visible, then invoke `$claude-collaborate` in the project you want Claude to work on.

### 3. Check the CLI

From the repository root, run:

```sh
python3 skills/claude-collaborate/scripts/claude_session.py doctor --project .
```

On Windows, replace `python3` with `py -3`. `doctor` checks installation, authentication, and permissions without sending a model request. Select your real project with `--project /path/to/project` when appropriate. Windows requires native `claude.exe` or a configured executable; see [platform support](docs/platforms.md).

## Configure it

No configuration file is required. Built-in defaults use Claude's existing local login, `opus`, `high`, project read access, and explicit collaboration requests only.

| Preference | General defaults / [`profiles/default.json`](profiles/default.json) | [`profiles/compatible.json`](profiles/compatible.json) |
| --- | --- | --- |
| Requested Claude model | `opus` alias | `claude-opus-5-5` |
| Requested effort | `high` | `xhigh` |
| Automatic collaboration | `false` | `true` |
| Discussion message limit | `3` | `3` |
| Telemetry policy | `off` | `off` |

`telemetry: "off"` disables supported nonessential telemetry; inference content is still sent to Claude.

The compatible profile enables automatic mode selection: simple questions stay with Codex; moderate tasks choose a mode; complex development proceeds from discussion to authorized implementation. Model and effort availability depend on your Claude installation and account. The helper does not silently substitute an unavailable model or effort. These settings do not change Codex's model.

### Configuration location and format

| Platform | Per-user configuration file |
| --- | --- |
| macOS / Linux | `~/.config/claude-collaborate/config.json` |
| macOS / Linux with an absolute `XDG_CONFIG_HOME` | `$XDG_CONFIG_HOME/claude-collaborate/config.json` |
| Windows | `%APPDATA%\claude-collaborate\config.json` |
| Windows without `APPDATA` | `%USERPROFILE%\AppData\Roaming\claude-collaborate\config.json` |

Save UTF-8 JSON with `"version": 1`. Do not add API keys, tokens, passwords, or personal project paths to a shared profile. Configuration is separate from the Codex skill installation and is not automatically loaded from the current project. Only supply preferences you want to override; omitted fields retain their defaults. A minimal configuration that opts into automatic collaboration is:

```json
{
  "version": 1,
  "auto_consult": true
}
```

For a complete starting point, use:

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

`null` means no configured turn or USD limit; size and time limits still apply. Set appropriate limits for your workload. The USD option is an estimated API-cost control, not an exact billing ceiling.

### Enable the compatible profile

To persist the `claude-opus-5-5` / `xhigh` / automatic-routing preferences, copy the compatible profile into the per-user location. Run these commands from the repository root. They preserve any existing configuration; if one exists, edit its selected fields after reviewing it.

**macOS / Linux**

```sh
case "${XDG_CONFIG_HOME:-}" in
  /*) collaborate_config_dir="$XDG_CONFIG_HOME/claude-collaborate" ;;
  *) collaborate_config_dir="$HOME/.config/claude-collaborate" ;;
esac
collaborate_config_file="$collaborate_config_dir/config.json"
if [ -e "$collaborate_config_file" ] || [ -L "$collaborate_config_file" ]; then
  printf 'Configuration already exists; review it before changing: %s\n' "$collaborate_config_file" >&2
else
  mkdir -p "$collaborate_config_dir"
  cp profiles/compatible.json "$collaborate_config_file"
  chmod 600 "$collaborate_config_file"
fi
```

**Windows PowerShell**

```powershell
$collaborateConfigBase = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $env:USERPROFILE 'AppData/Roaming' }
$collaborateConfigDir = Join-Path $collaborateConfigBase 'claude-collaborate'
$collaborateConfigFile = Join-Path $collaborateConfigDir 'config.json'
if (Get-Item -LiteralPath $collaborateConfigFile -Force -ErrorAction SilentlyContinue) {
    throw "Configuration already exists; review it before changing: $collaborateConfigFile"
}
New-Item -ItemType Directory -Force -Path $collaborateConfigDir | Out-Null
Copy-Item -LiteralPath 'profiles/compatible.json' -Destination $collaborateConfigFile
```

Inspect the effective configuration without model inference:

```sh
python3 skills/claude-collaborate/scripts/claude_session.py config
```

For a one-off profile, pass `--config profiles/compatible.json` after a subcommand instead. For example, `config --no-user-config --config profiles/compatible.json` inspects that profile without loading your personal helper configuration; inspection does not install or persist it. Precedence is built-ins → per-user file → explicit profile → supported command-line overrides. Additional deny rules accumulate across layers.

The default `auth: "claude.ai"` uses your existing Claude login. API-key use is an explicit alternative: select `"auth": "api-key"` and provide `ANTHROPIC_API_KEY` through your process environment, never JSON or command-line arguments. Only first-party Anthropic authentication is supported. Account access and usage charges remain your responsibility.

The helper blocks common secret-file names and imports existing Claude deny/ask rules, but it cannot identify every private file or constrain arbitrary programs as an OS sandbox would. Share only authorized material. `"access": "packet"` disables project tools for text-only work; it does not erase earlier session history. See [configuration](docs/configuration.md) for per-project permissions, executable selection, limits, and session recovery, and [privacy](docs/privacy.md) for data handling.

## Use it in Codex

Invoke the skill directly and name a mode when you have a preference:

```text
$claude-collaborate Review this patch against the acceptance criteria.
```

```text
$claude-collaborate 讨论模式：先比较这两个实现方案，再给出最终计划。
```

```text
$claude-collaborate Forward this request to Claude and return its answer unchanged.
```

Automatic collaboration is off by default. Enable it explicitly in configuration if you want Codex to select this workflow without a direct collaboration request. With automatic routing enabled, simple explanations normally stay with Codex, moderate tasks select an appropriate mode, and complex development proceeds from discussion to implementation when implementation is part of the requested work. A request not to use Claude always takes precedence.

For a command-line smoke check from this repository's root:

```sh
python3 skills/claude-collaborate/scripts/claude_session.py config --no-user-config
python3 skills/claude-collaborate/scripts/claude_session.py doctor --project .
```

`config` only inspects helper configuration; `doctor` checks the CLI and login without inference. To send a real request, save it in a UTF-8 `request.txt` and run:

```sh
python3 skills/claude-collaborate/scripts/claude_session.py send --project . --topic first-request --mode forward --trigger explicit --packet request.txt
```

Replace `--project .` with another existing project when appropriate. This uses default project read access and returns JSON with the unchanged response in `answer`. Add `--access packet` to expose no tools. The send consumes normal Claude account usage. See [Configuration](docs/configuration.md) for all five modes, a complete JSON configuration, opt-in routing, authentication, permissions, limits, and recovery.

## Develop and package

Run the offline suite from the repository root:

```sh
python3 -B -m unittest discover -s tests -p "test_*.py"
python3 -B -m unittest discover -s skills/claude-collaborate/scripts -p "test_*.py"
```

Tests use a fake Claude process; they do not validate live model access, billing, or provider behavior. Platform test coverage is described in [Platforms](docs/platforms.md).

Build a local release archive:

```sh
python3 scripts/build_release.py --output dist/claude-collaborate.zip
```

The archive preserves repository-relative paths, including `skills/claude-collaborate/`, with no extra enclosing directory. Only files listed in `release-files.txt` are included. Omitting `--output` writes `dist/claude-collaborate-source.zip`.

Building creates a local artifact. It does not install the skill or upload a release. Review the archive's contents before distributing it.

## License

MIT. See [LICENSE](LICENSE). Claude Code and any connected services are separate products with their own terms.
