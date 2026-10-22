# Forwarding / 转发

Send the user's actual request directly to Claude, then return Claude's answer unchanged. Honor this mode even for simple tasks or complex development. Codex does not first generate a solution, impose a plan, or run an automatic review or discussion cycle.

## Request and project access

Save the actual original request verbatim as UTF-8 and pass that file through `--packet`. The helper sends its bytes unchanged, including line endings. Put any necessary project instructions, relevant prior context, existing changes to preserve, or scope information in a separate optional `--context` file. Do not replace the request with a Codex paraphrase or add a Codex solution. Both `--context` and `--forward-write` are forward-only flags.

Use the same exact current project directory, topic, session continuity, and configured model/effort as the other modes. With the default `project` access, Claude has `Read`, `Glob`, and `Grep`, and may inspect relevant project contents without additional approval for ordinary task files. With `packet` access it gets no tools, but still receives the original request, optional context, helper instructions and project/topic metadata, and any resumed session history. This option does not start a clean conversation.

```sh
python3 <skill-dir>/scripts/claude_session.py send \
  --project <absolute-project-path> --topic <stable-topic-slug> --trigger explicit \
  --mode forward --packet <original-request.txt> \
  --context <project-context.txt>
```

Omit `--context` when none is needed. If the actual request authorizes local edits or tests, select `--forward-write` directly. This enables `Edit`, `Write`, and `Bash` in addition to read tools, and requires `project` access. Give each needed test or build command its own exact `--allow-tool 'Bash(<command>)'` rule, chosen from the actual project. Wildcards, shells, and inline interpreter code are refused.

Preserve existing user changes, and record the relevant file or diff baseline before a mutating call. Avoid concurrent writers. These flags select tools for work already requested. Do not ask for redundant confirmation, and do not infer additional authority for commits, publishing, or unrelated operations.

## Return the result

Return the helper's `answer` text unchanged, with a simple attribution such as `Claude's response:` or `Claude 的回复：`. Do not automatically summarize, translate, polish, critique, or send a follow-up consultation. A different collaboration mode requires a new user direction or an already explicit follow-on request.

Check the helper's `ok`, model metadata, and `partial`/permission-denial fields. If Claude changed files, inspect the resulting changes and reported test evidence; this verification does not authorize rewriting Claude's answer. Keep any material verification findings and CLI, model, or permission limitations outside the unchanged answer. If no answer was returned, report the concrete failure without inventing a response or silently retrying.

中文示例：`转发模式：直接把这个请求发给 Claude，然后把它的回答原样给我。`
English example: `Forward this request to Claude and return its response unchanged.`
