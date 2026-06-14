# install

## 1. 适用场景

当本项目不能正常进入记录、查询、完成、取消、聊天或其他扩展流程，并且原因与首次启动、数据库缺失或运行目录异常有关时，使用本扩展。

以下情况必须进入本扩展：

- `.\run.cmd` 返回 `status: needs_init`；
- `.\run.cmd doctor` 返回 `status: environment_error`；
- `.\run.cmd` 命令自身无法运行；
- 用户要求初始化、安装、检查便携包或排查运行目录；
- 当前确认 `data/assistant.sqlite` 不存在。

进入本扩展后，不继续处理用户原始请求。无论用户原始请求是记录、查询、完成、取消、维护、聊天还是其他扩展请求，都先完成本扩展的说明和确认流程。

## 2. 职责边界

本扩展负责：

1. 告知用户当前项目还不能正常使用（数据库缺失时）；
2. 逐字展示第 3 节的固定说明（数据库缺失时）；
3. 询问用户是否开始使用本项目；
4. 确认便携包内部文件已放在目标运行根目录；
5. 检查 `run.cmd`、`assistant.py`、`schema.sql`、`extensions/` 和 `runtime/`，并在初始化时创建或检查 `data/`；
6. 执行 `.\run.cmd doctor`、`init`、`--help` 和最小可用测试；
7. 处理便携包文件缺失、运行目录错误、数据库不可写、中文编码和查询验证中的常见问题；
8. 常规分支失败时继续主动排查，直到项目可用或明确阻塞。

本扩展不负责：

1. 修改业务数据结构；
2. 物理删除或重置数据库；
3. 手工编辑 `data/assistant.sqlite`；
4. 把数据库迁移到工作区外路径；
5. 安装与 DailyAssistant 便携包无关的外部集成；
6. 在没有用户明确要求时修改 `assistant.py`、`AGENTS.md` 或 `schema.sql`；
7. 不恢复旧数据（旧数据只能通过备份恢复）。

## 3. 固定展示内容

当用户第一次安装、本项目还没有开始使用，或数据库不存在时，必须向用户逐字展示"固定文案开始"和"固定文案结束"之间的内容。不要改写、扩写、缩写或临时调整文案；不要放进 `text` 代码块或其他代码块；如需补充解释，只能放在固定文案之后。

如果是因为便携包缺失、`run.cmd` 不可用或 `environment_error` 等原因进入本扩展，而数据库已存在，则跳过本节，直接进入第 7 节的环境检查和安装流程，不要展示数据库缺失文案。

"固定文案开始"和"固定文案结束"只是边界标记，不属于展示给用户的内容。

固定文案开始

当前本地数据库不存在，本项目还没有开始使用，或数据库已被删除。

DailyAssistant 是一个本地运行的任务和日程助理。它采用 LLM + 本地 CLI + SQLite 的架构：LLM 负责理解你的输入，`run.cmd` 调用本地程序负责校验、写入和查询，SQLite 负责在本机保存任务、日程和待确认事项。

本项目最大的优势是你不需要学习命令，也不需要把事情写成固定格式。你可以直接用自然语言输入，也可以发送语音或图片；例如，把邮件、通知、聊天记录或截图发给它，它会先转换和理解内容，再整理成任务、日程或待确认事项。

它主要能做这些：

1. 记录任务：周五前提交报告、记一下要买墨盒。
2. 记录日程：明天下午三点和导师开会、下周一上午体检。
3. 记录周期事项：每天早上 9 点吃水果，到下周五结束。
4. 查询安排：今天有什么？本周任务，明天有哪些日程？
5. 修改事项：把和导师开会改到下午 4 点。
6. 完成事项：报告已经提交了。
7. 删除/取消事项：取消明天的体检。
8. 处理不确定信息：如果一句话不够清楚，我会只问一个必要的确认问题。

你最省心的用法就是像发消息一样说：

1. 明天上午 10 点和张老师开会。
2. 这周还有什么任务没做？
3. 把提交论文的截止时间改到 6 月 20 日晚上 11 点。
4. 我完成了买药这件事。

也可以用语音或图片输入：

1. 语音说："明天上午十点和张老师开会""提醒我周五前交报告"。
2. 发送课程通知、邮件、聊天记录或会议截图，让我识别其中的考试、会议、预约、截止日期或待办事项。

我会负责判断输入是任务、日程还是待确认项，并把结果写进本地数据库。

它的核心能力包括：
1. 记录：把自然语言、语音转写或图片识别结果整理为任务、日程或待确认事项。
2. 查询：查看今天、指定日期、时间范围、任务、日程和待确认事项。
3. 修改：更新任务或日程的标题、内容、时间、地点、人员、项目、状态等字段。
4. 完成：把明确的任务或已发生的日程标记为已完成；周期性事项支持按某一次打卡。
5. 取消：把记错、识别错、取消或作废的事项软删除；周期性事项支持取消某一次或整个计划。
6. 待确认：在日期、类型或时间含义不清时，先进入待确认队列；澄清后可关闭、作废、重开并关联到实际事项。
7. 周期事项：支持每天、每周、每月或每隔一定周期重复的任务和日程。
8. 聊天：与记录、日程和数据库维护无关的问题不会写入数据库。
9. 扩展：通过 extensions 目录增加可选能力，例如安装初始化、备份恢复、更新升级和每日任务清单。

当前状态：
1. SQLite 数据库：不存在。
2. 已有记录：无法读取。
3. 下一步：需要先检查便携包运行目录，并初始化本地 SQLite 数据库。

是否开始使用本项目？如果确认，我会检查 `run.cmd` 和运行目录，初始化 SQLite 数据库，并做一个最小案例测试。

固定文案结束

## 4. 用户确认规则

以下表达视为明确确认：

- "开始"
- "确认"
- "可以"
- "初始化"
- "开始使用"
- "是"
- "好"
- "继续"
- "按这个来"

以下情况不视为明确确认：

- 用户只是继续提出记录、查询、完成、取消或聊天请求；
- 用户询问项目细节或数据库缺失原因；
- 用户要求先恢复备份；
- 用户明确表示暂不使用或不想初始化；
- 用户表达含糊，例如"再说""等等""这是什么"。

用户未明确确认时，不得进入安装或初始化流程。

## 5. 用户未确认或拒绝时

用户未确认时，停止在本扩展，不初始化数据库，也不继续执行用户原始请求。

用户明确拒绝时，回复应简短说明：

```text
好的，暂不初始化。当前数据库不存在，因此记录、查询、完成和取消功能暂时不可用。
```

如果用户之后继续提出任何需要数据库的请求，仍然先进入本扩展，并再次展示第 3 节的固定说明。

## 6. 特殊情况

### 6.1 用户要求解释数据库缺失

先展示第 3 节固定说明，再补充简短解释。可以说明数据库可能尚未初始化、被删除、移动，或当前运行目录不正确。不要猜测具体原因。

### 6.2 用户要求恢复备份

先展示第 3 节固定说明，再说明当前数据库不存在。随后只问一个最小澄清问题：用户是要恢复已有备份，还是重新初始化一个空数据库。

### 6.3 用户要求检查便携包或排查运行目录

先展示第 3 节固定说明。只有用户确认开始使用本项目后，才进入后续安装流程。

### 6.4 用户明确不想使用本项目

不进入后续安装流程，不初始化数据库。后续只要数据库仍不存在，任何依赖数据库的请求都继续进入本扩展。

### 6.5 便携包缺失导致的异常

如果 `.\run.cmd` 命令自身无法运行，且原因是 `run.cmd` 缺失、便携运行时缺失、便携包未构建、运行根目录不完整或权限异常，则不要展示第 3 节数据库缺失固定文案；应直接进入第 7 节的环境检查和排错流程。

## 7. 基本事实

### 7.1 运行根目录

运行根目录必须直接包含便携包内部文件。不要在运行根目录下再套一层 `DailyAssistantPortable` 子目录。

运行根目录必须直接包含：

```text
./
  run.cmd
  assistant.py
  schema.sql
  AGENTS.md
  README.md
  extensions/
    catalog.md
    install.md
    daily-work.md
  runtime/
    python/
      python.exe
```

发布包默认不包含 `data/` 目录，也不包含 `data/assistant.sqlite`。`data/` 和本地数据库由 `.\run.cmd init` 在安装目录内创建。

普通用户只需要：

1. Windows PowerShell 或 Windows 命令行；
2. 完整的 DailyAssistant 便携包内部文件；
3. 这些文件位于同一个目标运行根目录；
4. 当前目录具备写入权限，至少能创建 `data/` 并写入 `data/assistant.sqlite`。

`assistant.py` 仍是唯一写库入口。不要手工编辑 `data/assistant.sqlite`。

### 7.2 便携包缺失处理

如果 `run.cmd`、`runtime\python\python.exe`、`assistant.py`、`schema.sql` 或 `extensions/` 缺失，说明当前目录不是完整运行根目录。

处理规则：

1. 如果当前目录下只有一个 `DailyAssistantPortable` 子目录，并且核心文件位于该子目录内，应进入该子目录或把该子目录内的文件移动到目标运行根目录。
2. 如果用户拿到的是不完整便携包，应重新复制或重新获取完整便携包。
3. 不要通过安装其他系统组件来规避便携包缺失问题。
4. 不要临时创建空的 `assistant.py`、`schema.sql`、`AGENTS.md` 或 `extensions/install.md` 代替缺失文件。

## 8. 总体执行顺序

用户确认后（或环境问题直接进入安装流程时），按以下顺序推进：

1. 确认当前位置是 DailyAssistant 运行根目录；
2. 确认便携包内部文件直接位于该根目录；
3. 确认 `data/` 可写或可由初始化流程创建；
4. 运行 `.\run.cmd doctor` 检查基础状态；
5. 运行 `.\run.cmd --help` 确认 CLI 可用；
6. 运行 `.\run.cmd init` 初始化或升级数据库；
7. 使用 UTF-8 base64 写入一条最小中文案例；
8. 运行查询命令确认写入结果可读；
9. 对照第 13 节最小可用标准给出结论。

如果任何一步失败，进入第 12 节排错流程。排错完成后回到失败步骤继续执行，不要跳到后续步骤。

## 9. 环境检查

### 9.1 确认目录和核心文件

在目标运行根目录运行以下检查：

```powershell
$requiredRootFiles = @("run.cmd", "assistant.py", "schema.sql", "AGENTS.md")
$requiredRootDirs = @("extensions", "runtime")

foreach ($file in $requiredRootFiles) {
  if (-not (Test-Path -LiteralPath ".\$file" -PathType Leaf)) {
    Write-Output "missing-root-file: $file"
  }
}

foreach ($dir in $requiredRootDirs) {
  if (-not (Test-Path -LiteralPath ".\$dir" -PathType Container)) {
    Write-Output "missing-root-dir: $dir"
  }
}

if (-not (Test-Path -LiteralPath ".\extensions\install.md" -PathType Leaf)) {
  Write-Output "missing-extension-file: extensions/install.md"
}

if (-not (Test-Path -LiteralPath ".\runtime\python\python.exe" -PathType Leaf)) {
  Write-Output "missing-runtime: runtime\python\python.exe"
}
```

处理规则：

1. 如果当前目录不是运行根目录，但能明确找到包含 `run.cmd`、`assistant.py`、`schema.sql`、`AGENTS.md` 和 `extensions/install.md` 的目录，应先切换到该目录后重跑检查。
2. 如果当前目录下只有一个 `DailyAssistantPortable` 子目录，并且核心文件位于该子目录内，应进入该子目录或把该子目录内的文件移动到目标运行根目录；不要在错误的外层目录初始化数据库。
3. 如果存在多份同名核心文件、目标位置已有同名文件、来源路径不明确，或文件位于当前工作区外，不要猜测，也不要覆盖；只问用户一个最小确认问题。
4. 如果核心文件确实缺失，应恢复或重新获取完整便携包。
5. 不要在父目录、下载目录、桌面或其他项目目录里初始化数据库。

### 9.2 确认 CLI

在目标运行根目录运行：

```powershell
.\run.cmd doctor
```

根据返回结果处理：

1. `status: ok`：基础检查通过，进入第 10 节；
2. `status: environment_error`：按 `checks` 中失败项进入第 12 节；
3. `checks.database.exists`：只表示数据库文件是否已存在，不影响基础检查本身；
4. 如果这条命令自身无法运行，先回到第 9.1 节确认 `run.cmd` 与便携运行时，再进入第 12 节排查；
5. 只有 `assistant.py` 已经通过 `run.cmd` 成功启动并明确返回 `status: needs_init`，才按数据库缺失处理。

## 10. 初始化与 CLI 验证

### 10.1 确认 CLI 命令可用

基础检查通过后，运行：

```powershell
.\run.cmd --help
```

预期能列出 `doctor`、`init`、`apply-json`、`query`、`complete`、`cancel` 等命令。

### 10.2 初始化数据库

初始化只在以下场景执行：

1. 首次使用；
2. 数据库文件不存在；
3. 表结构更新；
4. 需要修复数据库权限。

初始化不是每次会话都要执行的命令。

在目标运行根目录运行：

```powershell
.\run.cmd init
```

预期结果：

```json
{
  "status": "ok",
  "db": "...assistant.sqlite",
  "permissions_repaired": false
}
```

`permissions_repaired` 可能是 `true` 或 `false`。只要 `status` 是 `ok`，就表示数据库已经可用。

注意：初始化只会创建或更新表结构，不代表删除数据。删除数据库或重置全部数据属于破坏性操作，必须由用户明确提出并二次确认。

## 11. 最小写入与查询测试

### 11.1 中文写入固定方式

PowerShell 直接传中文 JSON 容易出现编码问题。写入记录时必须使用 UTF-8 base64。

固定写法：

```powershell
$json = @'
{
  "record": {
    "source": "codex",
    "input_type": "text",
    "canonical_text": "明天下午三点和导师开会，今天晚上前准备会议材料",
    "raw_text": "明天下午三点和导师开会，今天晚上前准备会议材料",
    "extraction_method": "user_text",
    "extraction_confidence": 1.0,
    "original_retained": 0,
    "parse_status": "parsed",
    "parse_confidence": 0.95
  },
  "operations": [
    {
      "action": "create",
      "temp_id": "event_1",
      "item": {
        "type": "event",
        "title": "和导师开会",
        "status": "active",
        "start_at": "2026-06-13T15:00:00+08:00",
        "end_at": null,
        "all_day": 0,
        "people": ["导师"],
        "confidence": 0.95
      }
    },
    {
      "action": "create",
      "temp_id": "task_1",
      "item": {
        "type": "task",
        "title": "准备会议材料",
        "status": "active",
        "due_at": "2026-06-12T23:59:00+08:00",
        "confidence": 0.92
      }
    }
  ],
  "relations": [
    {
      "from_temp_id": "task_1",
      "to_temp_id": "event_1",
      "relation_type": "prepares_for"
    }
  ],
  "review": null
}
'@
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
.\run.cmd apply-json --base64 $b64
```

预期结果：

1. 返回 `status: ok`；
2. 返回 `created_items`；
3. 返回 `verification.read_after_write: true`。

看到 `verification.read_after_write: true` 后，不需要再手动查库验证同一次写入。

注意验证成功安装后，需要删除或取消掉用于验证的条目。

### 11.2 查询验证

查看指定日期：

```powershell
.\run.cmd query --date 2026-06-13
```

查看活跃任务：

```powershell
.\run.cmd query --type task --status active
```

查看待确认队列：

```powershell
.\run.cmd query --type reviews --status active
```

## 12. 排错流程

排错时必须先读取具体错误文本，再选择对应分支。不要在没有定位原因时反复运行同一条失败命令。

### 12.1 `run.cmd` 不存在或不能启动

如果目标目录缺少 `run.cmd`：

1. 先确认是否在正确目录；
2. 如果当前目录下只有一个 `DailyAssistantPortable` 子目录，并且其中存在 `run.cmd`，应进入该子目录或把其内部文件移动到目标运行根目录；
3. 如果找不到 `run.cmd`，说明便携包不完整，应重新复制或重新获取完整便携包。

如果 `run.cmd` 存在但不能启动：

1. 读取命令输出；
2. 确认 `assistant.py` 是否存在；
3. 确认 `runtime\python\python.exe` 是否存在；
4. 如果缺少核心文件或运行时目录，说明便携包不完整，应重新复制或重新获取完整便携包；
5. 不要通过安装其他系统组件来规避便携包缺失问题。

### 12.2 便携运行时异常

如果 `doctor` 显示运行时相关检查项失败：

1. 优先判断便携包是否被手工删改、杀毒隔离或复制不完整；
2. 重新复制或重新获取完整便携包；
3. 如果仍失败，报告 `doctor` 返回的具体失败项；
4. 不要把安装其他系统组件当作便携包的修复方案。

### 12.3 schema 文件异常

如果 `doctor` 显示 `checks.schema.ok = false`，说明项目文件不完整，应恢复或重新获取完整便携包。

不要临时创建空的 `schema.sql`，也不要猜测表结构。

### 12.4 数据目录或数据库不可写

如果 `doctor` 显示 `checks.data_dir_writable.ok = false`，或出现文件占用、权限拒绝、数据库只读、无法写入 `data/` 等问题：

1. 先确认数据库路径必须位于当前运行根目录下的 `data/assistant.sqlite`；
2. 检查项目是否位于只读目录、压缩包内、同步盘冲突目录或受保护目录；
3. 运行 `.\run.cmd init` 让程序尝试修复项目内权限；
4. 如果仍失败，报告具体失败路径和错误文本；
5. 不要把数据库迁移到工作区外路径规避问题。

### 12.5 中文路径和编码问题

如果项目路径、用户名或输入内容包含中文，优先保持 UTF-8 和 base64 写入方式：

1. 读取 Markdown 文件时使用 UTF-8；
2. 写入中文 JSON 时使用第 11.1 节的 `--base64` 固定写法；
3. 不使用 PowerShell 裸管道直接传中文 JSON；
4. 如果终端显示乱码，先确认文件内容是否能按 UTF-8 正常读取，不要仅凭终端显示判断文件损坏。

### 12.6 兜底排查

如果第 12 节前面的分支仍无法解决问题，大模型必须继续主动排查，目标是把项目安装并验证到可用状态，而不是把未分析的错误直接交给用户。

兜底排查顺序：

1. 完整读取最近一次命令的错误输出；
2. 确认当前目录、`run.cmd`、`runtime\python\python.exe`、`assistant.py`、`schema.sql`、`extensions/` 和 `data/` 状态；
3. 读取 `assistant.py` 中与失败命令相关的参数、环境检查和错误处理逻辑；
4. 读取 `schema.sql`，确认数据库初始化需要的结构文件存在且可读；
5. 根据错误文本搜索本项目文件，定位是否有已定义的错误码或处理分支；
6. 如果问题涉及 Windows 权限、文件占用或 SQLite 标准库，并且本地信息不足，应联网查找官方或可信资料；
7. 每次只做一个最小修复动作，然后重新运行对应检查命令；
8. 修复后必须回到失败步骤继续执行，并最终完成第 11 节查询验证；
9. 只有在缺少用户权限、文件缺失且无法恢复、或外部状态无法改变等情况确实无法继续时，才停止并报告明确阻塞原因、已尝试步骤和下一步需要用户做什么。

兜底排查不得执行以下操作：

1. 不得物理删除数据库；
2. 不得重置全部数据；
3. 不得手工修改 `data/assistant.sqlite`；
4. 不得把数据库改到工作区外路径；
5. 不得在没有用户明确要求时修改 `assistant.py`、`AGENTS.md` 或 `schema.sql`。

## 13. 最小可用标准

便携包可用需要同时满足：

1. 目标运行根目录直接包含 `run.cmd`；
2. 目标运行根目录直接包含 `runtime\python\python.exe`；
3. `.\run.cmd doctor` 返回 `status: ok`；
4. `.\run.cmd --help` 能列出核心命令；
5. `.\run.cmd init` 返回 `status: ok`；
6. `apply-json --base64` 能写入中文记录；
7. 写入结果包含 `verification.read_after_write: true`；
8. `query --date YYYY-MM-DD` 能查到对应日期的日程；
9. `query --type task --status active` 能查到任务；
10. 数据库文件位于 `data/assistant.sqlite`。

## 14. 回复规则

安装或排错过程中，回复用户时应说明：

1. 当前执行到哪一步；
2. 遇到的具体问题；
3. 已采取的修复动作；
4. 下一步要运行的验证命令。

安装完成后，只需简要说明：

1. 目录检查结果；
2. 初始化结果；
3. 最小写入和查询测试结果；
4. 项目是否已经可用。

## 15. 限制

1. 本扩展是便携包安装和可用性说明，不是便携包构建、下载或发布脚本。
2. 本扩展不写入业务数据，除非正在执行第 11 节最小写入测试。
3. 本扩展不修改 `assistant.py`、`AGENTS.md` 或 `schema.sql`。
4. 本扩展不是数据库恢复流程。
5. 数据库被删除后，本扩展不能恢复旧数据；旧数据只能通过备份恢复。
