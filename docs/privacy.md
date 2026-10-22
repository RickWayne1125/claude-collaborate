# Privacy and execution boundaries

Claude Code runs locally, but model inference uses its configured remote service. Prompts, selected conversation history, and project content that Claude reads may leave the machine. Installing this skill does not make Claude an offline model or establish a special data-retention agreement.

Only send material the user is authorized to share with the configured service. Provider terms, account settings, organization policy, and any applicable data-retention agreement still apply.

## What the helper handles

The helper receives task text through UTF-8 files and passes it to Claude through stdin. It uses subprocess argument arrays rather than constructing a shell command from the prompt. Forward mode preserves the original request and Claude's substantive answer; operational metadata is separate. The prompt also identifies the selected project's absolute path, topic label, mode, and access level, including in packet-only mode. Use non-sensitive project and topic names when that metadata matters.

With the default `project` access, all modes can read task-relevant files from the selected project. The optional `packet` access supplies task text without project file tools, but a resumed session still has its earlier context. Read access is broader than the text pasted into the prompt. Check the project for credentials, private records, and material unrelated to the request before granting access. Passing a narrowly selected task packet does not by itself prevent Claude from seeing other allowed project files.

The helper filters its child environment. Both public and compatible profiles default to the `off` privacy policy, which disables nonessential telemetry and reporting for the child process. The optional `inherit` policy preserves supported telemetry opt-out variables verbatim; it does not forward the entire environment or automatically enable custom telemetry exporters. An opt-out from telemetry is separate from the model request itself: the task still goes to the configured model service. Managed organizational policy may also apply.

## File rules and shell access

Restricted mode, explicit file tools, sensitive-file deny rules, and imported user/project/local deny and ask rules reduce unintended access. Imported ask rules are denied in this noninteractive workflow. These controls are not a complete confidentiality boundary:

- Sensitive information can appear in ordinary source, logs, fixture files, or prompts with no recognizable secret filename.
- Claude's file rules cover its recognized file operations. Arbitrary programs can access files indirectly, so an allowed Python, Node, test runner, or build command needs the same trust as running that program yourself.
- The helper rejects broad interpreter and shell-wrapper grants such as bare `python` or `sh -c`; a named script or module can still perform arbitrary operations internally.
- A repository's tests and build scripts can perform network requests or mutate files. Inspect unfamiliar commands before authorizing them.

Existing Claude sandbox settings must not be silently discarded. The helper rejects nonempty sandbox policies it cannot preserve; an empty object or explicit `{"enabled":false}` is inactive. Removing a policy is not a privacy fix. Use an OS sandbox or container when execution needs an enforced boundary. An isolated checkout helps preserve unrelated changes but does not, on its own, restrict filesystem or network access. This helper must not be used to work around a restriction imposed by its host. Prompt instructions describe scope; they do not enforce filesystem or network isolation.

## Local records and retention

The helper keeps user-level state for session selection, topic identities, account binding, and discussion counts. Treat this metadata as personal: topic labels and project paths can reveal work even without prompt text. Use non-sensitive topic labels and avoid sharing a state directory. On POSIX, state directories and files must be private to the owner (normally `0700` and `0600`); group or other access is rejected. Windows relies on the inherited per-user ACL, so a custom state location needs equivalent protection.

The helper stores a keyed fingerprint for API credential binding instead of the credential. Protect the state directory and its local identity key; rotating the API key intentionally prevents an automatic resume under the old binding.

Claude maintains its own persistent session data, subject to its own retention settings, including the user's `cleanupPeriodDays` preference. Resuming a session reuses its previous context. Deleting the helper registry, moving the project, or removing this skill does not automatically delete Claude transcripts, account-side records, or temporary task files. Follow the relevant CLI and provider procedures for their own records.

Temporary task packets should be created with private file permissions and removed when no longer needed. Keep retained outputs only when they are useful task artifacts. Deleting a local file is not a promise of secure erasure or deletion from a remote service.

## Output and reports

Failures should expose error categories and useful non-secret metadata, not raw authentication output, environment values, tool inputs, or full debug logs. Permission-denial summaries should identify the tool without echoing its sensitive arguments.

`config`, `doctor`, and `status` can reveal local paths, preferences, topic labels, or session identifiers. They are local diagnostics, not automatically safe public bug reports.

Successful answers are not automatically redacted. Forward mode deliberately returns the answer unchanged. Before posting a result, diagnostic output, screenshot, or bug report publicly, inspect it for personal paths, topic labels, session/account identifiers, and quoted project content.

Use synthetic examples when reporting a bug. Never attach real API keys, credential files, Claude transcripts, or an entire state directory. A minimal reproducer and sanitized error category are usually enough.

## Distributing this project

Build the release from the maintained source allowlist. Exclude `.DS_Store`, `__pycache__`, `.pyc`, local configuration, state, transcripts, temporary prompts, and generated test artifacts. Python bytecode can embed an absolute source path even when the source files themselves contain no personal path.

The build command creates a local archive; it does not publish it. Inspect the archive before sharing. Offline tests and pattern scans can catch known cases, but they do not prove that every possible secret or provider behavior has been covered.

## Provider documentation

- [Claude Code data usage](https://code.claude.com/docs/en/data-usage)
- [Permission-rule coverage and limitations](https://code.claude.com/docs/en/permissions#read-and-edit)
- [Environment variables and telemetry controls](https://code.claude.com/docs/en/env-vars)
