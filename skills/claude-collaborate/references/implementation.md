# Implementing / 实现

Codex generates the plan; Claude performs the authorized implementation and runs tests. For complex work with no explicit mode, first complete the bounded discussion when routing selects `discuss-implement`. If implementation is explicitly requested and the approach is already concrete, a mandatory discussion is unnecessary. Implementation requires `project` access.

## Prepare a concrete handoff

Inspect the current workspace and applicable project instructions, then pass:

- The original request, accepted plan, relevant verified context, and expected behavior.
- The project directory and the allowed files or subdirectories. Identify existing user changes and concurrent work to preserve. Include relevant `AGENTS.md` / `CLAUDE.md` instructions deliberately, because the helper disables automatic customization loading.
- Acceptance criteria, exact test and build commands, and any approved environment requirements. Never forward secret-bearing environment dumps.
- The scope of authority: the local edits and tests the task requested. Commits, pushes, deployments, publishing, dependency installation, and destructive operations each need their own existing task authorization. Do not infer them from a request to implement.
- The required return report: changes made, files affected, actual commands and results, unresolved failures, and permission denials.

Before dispatch, record the relevant diff, status, or file baseline. Avoid concurrent Codex and Claude writes to the same files, and pause other writers. Use the requested current project by default. An isolated checkout is appropriate only when the task or existing concurrency requires one, with the working directory and topic stated explicitly.

## Execute with scoped tools

Use `implement` mode. It exposes `Read`, `Glob`, `Grep`, `Edit`, `Write`, and `Bash`, with `Read`/`Edit` allowed only under the project and secret paths denied. Grant each needed command exactly with its own `--allow-tool 'Bash(<command>)'`. Select commands from the actual repository and do not copy a generic test command blindly. For example, a Python unittest project might use `Bash(python3 -B -m unittest discover -s tests -v)`.

The helper refuses:
- wildcards and `:*` prefixes
- shell metacharacters
- shells and wrappers such as `bash`, `sh`, `cmd`, `env`, `xargs`, and `sudo`
- `VAR=value` prefixes
- bare interpreters, and inline code such as `python -c` or `node -e`

File edit and read scope in the packet is a task constraint. CLI permissions and the host sandbox remain the enforcement boundary.

Restricted file tools do not turn allowed commands into an OS sandbox: a test command runs repository code as the user. It can read, write, or reach the network outside the file rules. Grant only commands justified by the task and permitted by the host. Do not widen permissions merely to silence a denial. If a legitimate needed action is already authorized, provide a precise additional grant and a focused continuation. Otherwise, request the missing authorization after preparing the reviewable change.

Do not switch to bypass permissions, another credential path, or an unapproved execution environment. Writes to settings, Git metadata, and tool configuration are denied. Keep such changes in the authorized host workflow rather than evading the restriction through Bash.

## Verify the actual work

Inspect the resulting files and diff yourself. Check scope, preserve unrelated changes, and verify the reported test evidence. Run targeted independent checks when needed to validate the behavior; do not blindly accept a claimed passing test or repeat an expensive suite without reason.

If a concrete defect remains, send Claude the failing evidence and a focused repair request in the same topic. Stop the loop in any of these cases:
- the same failure recurs without new evidence
- the scope would expand
- permissions block the next action
- a model or runtime failure, turn limit, or budget limit makes the prior attempt uncertain

Do not re-execute a possibly completed implementation automatically. Codex may finish a small correction itself when useful, but disclose that contribution. If Claude was unavailable, do not claim delegated implementation succeeded.

Deliver the completed change, meaningful validation, and any real limitation. Attribute implementation to Claude and review/verification to Codex where applicable.

中文示例：`你先制定计划，然后交给 Claude 写代码并运行测试，最后检查实际改动。`
