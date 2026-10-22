# Claude Collaborate

通过本机安装的 Claude Code CLI，让 Codex 与 Claude 协作的技能。支持独立交叉验证、审阅修订、多轮讨论、委托实现，以及原请求与回答的直接转发。

[English](README.md) · [配置](docs/configuration.md) · [隐私](docs/privacy.md) · [平台支持](docs/platforms.md)

## 五种模式

| 模式 | 工作方式 |
| --- | --- |
| `cross-validate` | Codex 先生成答案，Claude 独立解答同一问题，再展示两份答案的实质差异与验证依据。 |
| `review` | Claude 按原始需求审阅 Codex 的草稿，Codex 核实反馈后修订。 |
| `discuss` | Codex 与 Claude 讨论并完善计划；每轮讨论默认最多向 Claude 发送三条消息，可通过配置调整上限。 |
| `implement` | Claude 执行已获授权的计划和检查，Codex 核验代码变化与测试证据。 |
| `forward` | 将原请求原样发给 Claude，再原样返回其回答；运行限制另行说明。 |

支持中文和英文。全部模式使用同一个当前项目目录，可以读取相关项目文件。默认开放项目文件访问。实现模式，或使用 `--forward-write` 的转发模式，可为用户已授权的工作启用编辑与指定 shell 命令。使用 `--access packet` 可禁用项目工具，保留文本材料与已保存会话上下文；提示词仍包含项目和主题标识。

同一主题在切换模式或后续修订时复用 Claude 会话。完全不同的主题可以使用独立会话，返回旧主题时复用已记录的会话身份。默认将状态保存在用户级状态目录，不写入项目；不会自动扫描或认领其他 Claude 会话。

## 环境要求

- Python 3.9 或更高版本。
- 受支持的本地 Claude Code，以及准备使用的认证方式。
- 如果从 Codex 调用，需要其本地技能功能。
- 有权将选定的任务材料发送给 Claude。

通用默认值为模型别名 `opus` 和 effort `high`。别名实际对应的版本可能随 Claude 或提供商更新而变化。`profiles/compatible.json` 保留之前的 `claude-opus-5-5` / `xhigh` 偏好和自动模式选择；具体模型是否可用取决于账户。

“本地 CLI”不等于本地模型推理。提示词、使用到的会话历史和文件内容仍会发往所配置的模型服务。处理私有仓库前请阅读[隐私说明](docs/privacy.md)。

## 安装

### 1. 获取源码

```sh
git clone https://github.com/RickWayne1125/claude-collaborate.git
cd claude-collaborate
```

没有 Git 时，在[仓库页面](https://github.com/RickWayne1125/claude-collaborate)选择 **Code → Download ZIP**，解压后在仓库文件夹打开终端。下方命令均从该文件夹运行。

请先按[官方说明](https://code.claude.com/docs/en/overview)安装并登录 Claude Code。本仓库不会安装 Claude Code 或改变登录方式。需要 Python 3.9 或更新版本；下方 macOS/Linux 示例使用 `python3`，Windows 使用 `py -3`，也可替换为本机的 `python` 命令。

### 2. 将技能复制到 Codex

按照 [Codex 官方技能指南](https://learn.chatgpt.com/docs/build-skills)，推荐的用户级位置为 `~/.agents/skills/claude-collaborate`。以下示例遇到已有安装会停止复制。升级前请自行比较或备份旧版。

如果旧版 Codex 已在 `$CODEX_HOME/skills` 或 `~/.codex/skills` 中识别现有技能，请将下面的技能根目录变量改为该实际目录。不要在多个识别目录重复安装同名技能。

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

安装后的文件夹内应直接包含 `SKILL.md`、`scripts/`、`references/` 和 `agents/`。建议保留源码目录，以便使用示例配置和完整文档。若 Codex 尚未显示新技能，请重新打开 Codex，然后在需要处理的项目里调用 `$claude-collaborate`。

### 3. 检查 CLI

在仓库根目录运行：

```sh
python3 skills/claude-collaborate/scripts/claude_session.py doctor --project .
```

Windows 将 `python3` 替换为 `py -3`。`doctor` 检查安装、认证和权限，不发送模型推理请求。可用 `--project /path/to/project` 指定实际项目。Windows 需要原生 `claude.exe` 或明确配置的可执行程序，详见[平台支持](docs/platforms.md)。

## 配置指南

不创建配置文件也能使用。内置默认值采用已有 Claude 登录、`opus` 模型、`high` effort、项目读取权限，仅在明确请求协作时调用。

| 偏好 | 通用默认值 / [`profiles/default.json`](profiles/default.json) | [`profiles/compatible.json`](profiles/compatible.json) |
| --- | --- | --- |
| 请求的 Claude 模型 | `opus` 别名 | `claude-opus-5-5` |
| 请求的 effort | `high` | `xhigh` |
| 自动协作 | `false` | `true` |
| 单次讨论消息上限 | `3` | `3` |
| 遥测策略 | `off` | `off` |

`telemetry: "off"` 关闭所支持的非必要遥测；推理内容仍会发送给 Claude。

兼容配置启用自动模式选择：简单问题由 Codex 直接回答，中等任务选择合适模式，复杂开发先讨论再执行已获授权的实现。模型与 effort 是否可用取决于本机 Claude 版本和账户；不可用时不会静默替换。这里的配置不会改变 Codex 自身的模型。

### 配置文件位置与格式

| 平台 | 用户配置文件 |
| --- | --- |
| macOS / Linux | `~/.config/claude-collaborate/config.json` |
| macOS / Linux，且 `XDG_CONFIG_HOME` 为绝对路径 | `$XDG_CONFIG_HOME/claude-collaborate/config.json` |
| Windows | `%APPDATA%\claude-collaborate\config.json` |
| Windows 未设置 `APPDATA` | `%USERPROFILE%\AppData\Roaming\claude-collaborate\config.json` |

保存为 UTF-8 JSON，必须包含 `"version": 1`。不要将 API key、令牌、密码或个人项目路径写入共享配置。配置文件与 Codex 技能安装目录独立，也不会自动从当前项目加载。只填写需要调整的字段，其余采用默认值。开启自动协作的最小配置为：

```json
{
  "version": 1,
  "auto_consult": true
}
```

完整的初始配置如下：

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

`null` 表示未设置对应的轮次或美元限额；大小和时间限制仍生效。请按工作负载调整。美元选项基于估计 API 成本，不是精确的账单上限。

### 启用兼容配置

要长期采用 `claude-opus-5-5` / `xhigh` / 自动模式选择，将兼容配置复制到上述用户配置位置。以下命令从仓库根目录运行，并保留任何已有配置；如果配置已存在，请核对后只编辑需要修改的字段。

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

查看最终生效的配置，不会发送模型请求：

```sh
python3 skills/claude-collaborate/scripts/claude_session.py config
```

只想单次使用时，可在子命令后添加 `--config profiles/compatible.json`。例如，`config --no-user-config --config profiles/compatible.json` 会跳过个人 helper 配置并检查该 profile；检查本身不会安装或持久启用它。优先级为：内置默认值 → 用户配置 → 明确指定的 profile → 支持的命令行参数；额外 deny 规则会累积。

默认 `auth: "claude.ai"` 使用已有的 Claude 登录。若明确选择 API key，请设置 `"auth": "api-key"`，通过进程环境提供 `ANTHROPIC_API_KEY`，不要放进 JSON 或命令行参数。当前仅支持 Anthropic 第一方认证。模型访问权限和使用费用由你的 Claude 账户决定。

helper 会阻止常见敏感文件名，并继承已有 Claude deny/ask 规则，但不能识别所有隐私文件，也不能像操作系统沙箱一样限制任意程序。请仅发送有权共享的材料。`"access": "packet"` 可为纯文本任务关闭项目工具，但不会清空已保存的会话历史。逐项目权限、可执行程序选择、限额和会话恢复见[完整配置文档](docs/configuration.md)，数据处理边界见[隐私说明](docs/privacy.md)。

## 在 Codex 中使用

直接调用技能，并按需指定模式：

```text
$claude-collaborate 审阅模式：检查这份补丁是否满足验收条件。
```

```text
$claude-collaborate 讨论模式：先比较两个方案，再给出最终计划。
```

```text
$claude-collaborate 转发模式：把这个请求直接发给 Claude，并将回答原样返回。
```

默认关闭自动协作。只有在配置中明确启用后，Codex 才能在未直接请求协作时选择此流程。启用后，简单解释通常由 Codex 直接回答；中等任务选择合适模式；需要实现的复杂开发任务先讨论，再委托实现。用户要求不用 Claude 时始终遵守。

也可以在本仓库根目录先检查配置与 CLI：

```sh
python3 skills/claude-collaborate/scripts/claude_session.py config --no-user-config
python3 skills/claude-collaborate/scripts/claude_session.py doctor --project .
```

`config` 只查看 helper 配置；`doctor` 检查 CLI 与登录状态，不发推理请求。将实际请求保存为 UTF-8 的 `request.txt` 后，运行：

```sh
python3 skills/claude-collaborate/scripts/claude_session.py send --project . --topic first-request --mode forward --trigger explicit --packet request.txt
```

需要处理其他项目时，将 `--project .` 改为实际存在的目录。默认允许读取该项目；返回 JSON 中的 `answer` 是未改写的回答。添加 `--access packet` 可禁用全部工具。发送会消耗正常 Claude 账户用量。五种模式、完整 JSON 配置、自动协作选择、认证、权限、限额与恢复示例见[配置文档](docs/configuration.md)。

## 测试与打包

在仓库根目录运行离线测试：

```sh
python3 -B -m unittest discover -s tests -p "test_*.py"
python3 -B -m unittest discover -s skills/claude-collaborate/scripts -p "test_*.py"
```

测试使用假的 Claude 进程，不验证真实模型访问、计费或提供商行为。平台测试范围见[平台文档](docs/platforms.md)。

构建本地发布包：

```sh
python3 scripts/build_release.py --output dist/claude-collaborate.zip
```

压缩包直接保留仓库相对路径，包括 `skills/claude-collaborate/`，不增加额外顶层目录。只打包 `release-files.txt` 明确列出的文件。省略 `--output` 时输出到 `dist/claude-collaborate-source.zip`。

该命令只生成本地文件，不安装技能，也不上传发布。分发前检查压缩包内容。

## 许可

MIT，见 [LICENSE](LICENSE)。Claude Code 及连接的服务是独立产品，适用各自的条款。
