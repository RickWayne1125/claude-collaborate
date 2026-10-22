# Platforms and validation

The helper targets Python 3.9 or later on macOS, Linux, and Windows. It uses the Python standard library. Platform support depends on a compatible local Claude Code executable and the authentication method in use.

## macOS and Linux

Use a native `claude` executable available on `PATH`. The helper starts it in the selected project directory. POSIX file locking serializes helper calls, and process-group termination is used to stop an active invocation and its ordinary child processes during cancellation or timeout.

A process that deliberately detaches from that group may need separate cleanup. Avoid parallel helper calls or a separate Claude terminal writing the same session or project.

## Windows

Prefer native `claude.exe`. A trusted explicit command list can instead name an absolute `node.exe` and a fixed Claude CLI script. A PowerShell function, shell alias, or `.cmd`/`.bat`/`.ps1` launcher is not an equivalent executable interface; these script launchers are rejected as the first program. Use `python` or `py -3` according to the installed Python launcher.

Windows uses its own file-locking and process-tree termination path rather than POSIX `fcntl`/`killpg`. If the parent Claude process has already exited, Windows tree cleanup may be incomplete; inspect returned cleanup metadata and remaining processes before recovery. Force-killing the helper is not safe cancellation on either platform: it can prevent cleanup and leave delegated commands running. Path comparisons and executable resolution must be tested with spaces and non-ASCII directory names. A Windows implementation must not be treated as tested merely because mocked platform tests pass on another operating system.

WSL is a Linux environment for this helper. Use a Linux Python and Claude installation inside WSL rather than mixing a Windows executable with Linux session paths.

## What offline tests establish

The unit suite uses a fake Claude executable to exercise argument construction, request and answer preservation, session reuse, discussion limits, permission handling, failure state, and subprocess cleanup. It does not send a model request.

These tests do not establish model availability, successful real authentication, server-side effort, exact billing behavior, or complete sandbox isolation. Tests that mock Windows APIs are useful checks of code paths, not a native Windows execution result.

CI configuration describes the intended test matrix: Python 3.9, 3.12, and 3.13 on Ubuntu, macOS, and Windows. Do not read its presence as evidence that every job has run successfully. Check actual CI results for the revision being used. The matrix configuration alone is not evidence of a successful run; consult the repository’s [actual checks](https://github.com/RickWayne1125/claude-collaborate/actions) for the revision you use.

## Local validation scope

Local checks used Claude Code 2.1.290 with only synthetic temporary files. A direct CLI conformance check confirmed scoped `Read` access and denials for a `.env` file and a file outside the selected directory.

A subsequent end-to-end helper check passed `doctor` and a forward-mode send. A public file was readable; four reads were denied: the built-in `.env` case, a local-setting `Read(/private.txt)` rule, an imported `ask` rule for `Read(./approval.txt)`, and a file outside the project. The helper reported `partial: true` and four permission denials. Current-invocation metadata matched the requested exact `claude-opus-5-5` model. A second helper send resumed the same UUID with `--access packet`, no tools, and no permission denials; it recalled the exact synthetic marker from the earlier turn. These checks do not establish arbitrary shell-command isolation or native Windows/Linux behavior.

## Compatibility checks

Use the helper's `doctor` operation to inspect the installed executable and supported controls before a real collaboration. It should not perform inference, log in, install software, or alter the user's configuration.

Claude Code changes independently of this project. Some supported flags are omitted from `claude --help`; consult the [official CLI reference](https://code.claude.com/docs/en/cli-reference) when diagnosing compatibility. Do not silently replace a requested model, lower an effort setting, or change authentication to make a check pass.
