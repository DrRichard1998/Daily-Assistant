# install

## 1. 目的

本扩展用于基于 DailyAssistant 便携包安装本项目：检查运行根目录，初始化本地数据库，并验证项目可用。

主版本是便携包版本：日常用户通过 `.\run.cmd` 运行项目。安装本项目时，只需要保留便携包内容目录里的文件，并把这些文件放在目标运行根目录下。

最终目标不是解释安装概念，而是把便携包安装到可用状态：

1. 确认当前目录是 DailyAssistant 运行根目录；
2. 确认便携包内部文件直接位于该根目录；
3. 确认 `.\run.cmd` 可用；
4. 初始化 `data/assistant.sqlite`；
5. 验证 CLI 可正常执行；
6. 验证中文记录可写入；
7. 验证任务、日程和待确认查询可用；
8. 遇到问题时主动排查并尽量修复。

## 2. 职责边界

本扩展负责：

1. 确认便携包内部文件已放在目标运行根目录；
2. 检查 `run.cmd`、`assistant.py`、`schema.sql`、`extensions/`、`data/` 和 `runtime/`；
3. 执行 `.\run.cmd doctor`、`init`、`--help` 和最小可用测试；
4. 处理便携包文件缺失、运行目录错误、数据库不可写、中文编码和查询验证中的常见问题；
5. 常规分支失败时继续主动排查，直到项目可用或明确阻塞。

本扩展不负责：

1. 修改业务数据结构；
2. 物理删除或重置数据库；
3. 手工编辑 `data/assistant.sqlite`；
4. 把数据库迁移到工作区外路径；
5. 安装与 DailyAssistant 便携包无关的外部集成；
6. 在没有用户明确要求时修改 `assistant.py`、`AGENTS.md` 或 `schema.sql`。

## 3. 触发条件

当用户表达以下意图时使用本扩展：

1. 用户要求基于便携包安装本项目；
2. 用户要求初始化本项目；
3. 用户要求检查便携包；
4. 用户要求检查运行目录；
5. 用户要求排查运行问题；
6. 遇到 `run.cmd`、便携运行时、SQLite、中文编码、数据库只读等运行问题；
7. 要求做一个最小可用测试；
8. 已经通过 `extensions/init.md` 确认开始使用本项目。

## 4. 基本事实

### 4.1 运行根目录

运行根目录必须直接包含便携包内部文件。不要在运行根目录下再套一层 `DailyAssistantPortable` 子目录。

运行根目录必须直接包含：

```text
./
  run.cmd
  assistant.py
  schema.sql
  AGENTS.md
  README.md
  data/
  extensions/
    catalog.md
    init.md
    install.md
    daily-work.md
  runtime/
    python/
      python.exe
```

普通用户只需要：

1. Windows PowerShell 或 Windows 命令行；
2. 完整的 DailyAssistant 便携包内部文件；
3. 这些文件位于同一个目标运行根目录；
4. 当前目录具备写入权限，至少能写入 `data/assistant.sqlite`。

`assistant.py` 仍是唯一写库入口。不要手工编辑 `data/assistant.sqlite`。

### 4.2 便携包缺失处理

如果 `run.cmd`、`runtime\python\python.exe`、`assistant.py`、`schema.sql` 或 `extensions/` 缺失，说明当前目录不是完整运行根目录。

处理规则：

1. 如果当前目录下只有一个 `DailyAssistantPortable` 子目录，并且核心文件位于该子目录内，应进入该子目录或把该子目录内的文件移动到目标运行根目录。
2. 如果用户拿到的是不完整便携包，应重新复制或重新获取完整便携包。
3. 不要通过安装其他系统组件来规避便携包缺失问题。
4. 不要临时创建空的 `assistant.py`、`schema.sql`、`AGENTS.md` 或 `extensions/install.md` 代替缺失文件。

## 5. 总体执行顺序

基于便携包安装和验证必须按以下顺序推进：

1. 确认当前位置是 DailyAssistant 运行根目录；
2. 确认便携包内部文件直接位于该根目录；
3. 确认 `data/` 可写或可由初始化流程创建；
4. 运行 `.\run.cmd doctor` 检查基础状态；
5. 运行 `.\run.cmd --help` 确认 CLI 可用；
6. 运行 `.\run.cmd init` 初始化或升级数据库；
7. 使用 UTF-8 base64 写入一条最小中文案例；
8. 运行查询命令确认写入结果可读；
9. 对照第 10 节最小可用标准给出结论。

如果任何一步失败，进入第 9 节排错流程。排错完成后回到失败步骤继续执行，不要跳到后续步骤。

## 6. 环境检查

### 6.1 确认目录和核心文件

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

### 6.2 确认 CLI

在目标运行根目录运行：

```powershell
.\run.cmd doctor
```

根据返回结果处理：

1. `status: ok`：基础检查通过，进入第 7 节；
2. `status: environment_error`：按 `checks` 中失败项进入第 9 节；
3. `checks.database.exists`：只表示数据库文件是否已存在，不影响基础检查本身；
4. 如果这条命令自身无法运行，先回到第 6.1 节确认 `run.cmd` 与便携运行时，再进入第 9 节排查；
5. 只有 `assistant.py` 已经通过 `run.cmd` 成功启动并明确返回 `status: needs_init`，才按数据库缺失处理。

## 7. 初始化与 CLI 验证

### 7.1 确认 CLI 命令可用

基础检查通过后，运行：

```powershell
.\run.cmd --help
```

预期能列出 `doctor`、`init`、`apply-json`、`query`、`complete`、`cancel` 等命令。

### 7.2 初始化数据库

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

## 8. 最小写入与查询测试

### 8.1 中文写入固定方式

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

### 8.2 查询验证

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

## 9. 排错流程

排错时必须先读取具体错误文本，再选择对应分支。不要在没有定位原因时反复运行同一条失败命令。

### 9.1 `run.cmd` 不存在或不能启动

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

### 9.2 便携运行时异常

如果 `doctor` 显示运行时相关检查项失败：

1. 优先判断便携包是否被手工删改、杀毒隔离或复制不完整；
2. 重新复制或重新获取完整便携包；
3. 如果仍失败，报告 `doctor` 返回的具体失败项；
4. 不要把安装其他系统组件当作便携包的修复方案。

### 9.3 schema 文件异常

如果 `doctor` 显示 `checks.schema.ok = false`，说明项目文件不完整，应恢复或重新获取完整便携包。

不要临时创建空的 `schema.sql`，也不要猜测表结构。

### 9.4 数据目录或数据库不可写

如果 `doctor` 显示 `checks.data_dir_writable.ok = false`，或出现文件占用、权限拒绝、数据库只读、无法写入 `data/` 等问题：

1. 先确认数据库路径必须位于当前运行根目录下的 `data/assistant.sqlite`；
2. 检查项目是否位于只读目录、压缩包内、同步盘冲突目录或受保护目录；
3. 运行 `.\run.cmd init` 让程序尝试修复项目内权限；
4. 如果仍失败，报告具体失败路径和错误文本；
5. 不要把数据库迁移到工作区外路径规避问题。

### 9.5 中文路径和编码问题

如果项目路径、用户名或输入内容包含中文，优先保持 UTF-8 和 base64 写入方式：

1. 读取 Markdown 文件时使用 UTF-8；
2. 写入中文 JSON 时使用第 8.1 节的 `--base64` 固定写法；
3. 不使用 PowerShell 裸管道直接传中文 JSON；
4. 如果终端显示乱码，先确认文件内容是否能按 UTF-8 正常读取，不要仅凭终端显示判断文件损坏。

### 9.6 兜底排查

如果第 9 节前面的分支仍无法解决问题，大模型必须继续主动排查，目标是把项目安装并验证到可用状态，而不是把未分析的错误直接交给用户。

兜底排查顺序：

1. 完整读取最近一次命令的错误输出；
2. 确认当前目录、`run.cmd`、`runtime\python\python.exe`、`assistant.py`、`schema.sql`、`extensions/` 和 `data/` 状态；
3. 读取 `assistant.py` 中与失败命令相关的参数、环境检查和错误处理逻辑；
4. 读取 `schema.sql`，确认数据库初始化需要的结构文件存在且可读；
5. 根据错误文本搜索本项目文件，定位是否有已定义的错误码或处理分支；
6. 如果问题涉及 Windows 权限、文件占用或 SQLite 标准库，并且本地信息不足，应联网查找官方或可信资料；
7. 每次只做一个最小修复动作，然后重新运行对应检查命令；
8. 修复后必须回到失败步骤继续执行，并最终完成第 8 节查询验证；
9. 只有在缺少用户权限、文件缺失且无法恢复、或外部状态无法改变等情况确实无法继续时，才停止并报告明确阻塞原因、已尝试步骤和下一步需要用户做什么。

兜底排查不得执行以下操作：

1. 不得物理删除数据库；
2. 不得重置全部数据；
3. 不得手工修改 `data/assistant.sqlite`；
4. 不得把数据库改到工作区外路径；
5. 不得在没有用户明确要求时修改 `assistant.py`、`AGENTS.md` 或 `schema.sql`。

## 10. 最小可用标准

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

## 11. 回复规则

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

## 12. 限制

1. 本扩展是便携包安装和可用性说明，不是便携包构建、下载或发布脚本。
2. 本扩展不写入业务数据，除非正在执行第 8 节最小写入测试。
3. 本扩展不修改 `assistant.py`、`AGENTS.md` 或 `schema.sql`。
