---
name: claude-collaborate
description: Coordinate Codex with a locally installed Claude Code CLI for cross-validation, review and revision, bounded discussion, delegated implementation, or verbatim request forwarding. Use when the user asks to involve Claude (协作、交叉验证、审阅、讨论、转发、让 Claude 实现), or for substantial problem solving and development when the helper configuration enables auto_consult. Supports English and Chinese; simple explanations normally need no Claude call.
---

# Claude Collaborate

Codex owns coordination, context selection, and verification. Claude is a second solver, reviewer, discussion partner, implementer, or direct recipient according to the selected mode. Codex synthesizes results except in forward mode, which returns Claude's answer unchanged. Communicate in the user's language; preserve technical identifiers. Understand English and Chinese requests without requiring exact keywords.

## Decide whether to call Claude

- **Explicit request** — the user invokes this skill, names a mode, or asks to involve Claude: proceed and pass `--trigger explicit`. That request authorizes task-scoped collaboration; do not ask again for already authorized work.
- **No explicit request** — run the helper's `config` command once per conversation. Consult Claude only when `auto_consult` is `true`, and pass `--trigger auto`. Otherwise work without Claude.
- An instruction not to use Claude overrides all routing.

## Select the mode

Honor an explicit mode. Otherwise classify the request, apply the configured `routing` tier from `config`, and briefly tell the user the chosen mode and why.

| Request | Mode | Read before executing |
| --- | --- | --- |
| Two solutions or competing conclusions need comparison; 交叉验证、双重验证、分别解答 | `cross-validate` | [cross-validation.md](references/cross-validation.md) |
| A Codex draft, change, or answer needs criticism and revision; 审阅、评审、复核 | `review` | [review.md](references/review.md) |
| Uncertain approach, meaningful tradeoffs, or planning; 讨论、商讨、共同规划 | `discuss` | [discussion.md](references/discussion.md) |
| Send the request directly to Claude and return its answer; 转发、直传、原样返回 | `forward` | [forward.md](references/forward.md) |
| A concrete plan should be executed by Claude; 实现、实施、让 Claude 写代码并测试 | `implement` | [implementation.md](references/implementation.md) |

Routing tiers map `simple`, `moderate`, and `complex` requests to `direct`, `auto`, `cross-validate`, `review`, `discuss`, or `discuss-implement`. Defaults are simple → `direct`, moderate → `auto`, complex → `discuss-implement`.

- `direct`: answer without Claude unless the user explicitly asked for Claude; then use the lightest useful mode.
- `auto`: choose the lightest mode that resolves the actual uncertainty; do not run every mode.
- `discuss-implement`: discuss, then give Claude the synthesized plan to implement in the same session when implementation is part of the requested deliverable. Plan-only requests end after discussion.

An explicit forward request overrides planning and synthesis routes. This is a standalone workflow: do not stack another Claude-consultation skill on the same question. If the user explicitly invokes a different Claude skill, follow that skill instead. Do not alter other skills or global configuration to enable this one.

## Defaults and session continuity

- Run Claude in the **current project folder** unless the user selects another. Resolve its absolute path; do not silently substitute a parent Git root or another checkout.
- The helper explicitly passes the configured model and effort on every request, including resumes. Public defaults are `opus` / `high`; the compatibility profile pins `claude-opus-5-5` / `xhigh`. Pass `--model` / `--effort` only for a user override and keep a still-applicable override on later calls. Never fall back to another model or effort. These settings apply to Claude, not to Codex.
- Keep **one session per project topic**. Reuse the same `--topic` across mode changes, revisions, follow-ups, and repairs; returning to a known topic reuses its session automatically. Start a new topic, with `--new-topic-reason`, only for a genuinely unrelated task or an explicit user request.
- Before the first call in a conversation, read [cli-and-sessions.md](references/cli-and-sessions.md). It covers commands, configuration, authentication, permissions, recovery, and model verification. Use the bundled helper rather than reconstructing session bookkeeping.

## Context, consent, and authority

Before the first transmission, briefly state which categories of task material will go to Claude. Claude Code sends the prompt, the resumed session history, and any project files Claude reads to its configured model service. Running it locally does not make it offline. Automatic selection must stay within the user's current task and workspace authorization.

With the default `project` access, Claude can use `Read`, `Glob`, and `Grep` in the current project folder in every mode. Ordinary task-relevant files need no additional approval. Do not deliberately expose credentials, unrelated private records, or unrelated files. With `packet` access Claude gets no tools, but still receives the packet, any forward context, helper instructions and project/topic metadata, and resumed session history. Include the needed evidence; disabling tools does not clear the existing conversation.

For cross-validation, review, discussion, and implementation, send the original request, relevant constraints and project instructions, selected evidence, and the requested output format. Distinguish source material from Codex's instructions and verified observations. For forward mode, put the actual original request verbatim in `--packet`. Provide necessary context separately through optional `--context`, without a Codex solution or mandatory plan.

Implementation adds `Edit`, `Write`, and `Bash`, with exact command grants only. So does forwarding with `--forward-write`, which applies when the actual request already authorizes edits or tests; do not ask for redundant confirmation. Both require `project` access. Mode changes do not grant more authority than the user and host permit. Do not work around a host sandbox or approval restriction by asking Claude to do the blocked action.

## Deliver and verify

For the four collaborative modes, treat Claude's output as a proposal or report, not proof. Check consequential claims against sources, calculations, code, diffs, or observed tests. Disagreement remains visible when evidence cannot settle it.

Forward mode instead returns the helper's `answer` unchanged with simple attribution. Do not automatically rewrite it, critique it, or start another consultation. If forwarding changed files, inspect the actual changes and test evidence. Report material verification or CLI/permission limitations separately, without altering Claude's text.

Keep Codex's and Claude's contributions attributable, and do not invent a successful Claude pass when a call failed. For modes other than forward, deliver the requested result in the user's language, plus the mode-specific comparison or material revision notes where applicable. Include the session ID when creating or switching sessions, or when the user needs it to resume. Report model, permission, or partial-completion limitations accurately, without dumping transcripts or internal reasoning.
