# install

## 1. 目的

本扩展用于把 DairyAssistant 的本地 SQLite 版本安装、初始化并验证到可用状态。

最终目标不是解释安装概念，而是完成以下闭环：

1. 确认运行环境可用；
2. 初始化 `data/assistant.sqlite`；
3. 验证 CLI 可正常执行；
4. 验证中文记录可写入；
5. 验证任务、日程和待确认查询可用；
6. 遇到问题时主动排查并尽量修复。

## 2. 职责边界

本扩展负责：

1. 检查 Python、pip、SQLite 标准库、PATH 和项目目录权限；
2. 指导安装或修复必要的本机运行环境；
3. 执行 `assistant.py doctor`、`init`、`--help` 和最小可用测试；
4. 处理安装、初始化、权限、编码和查询验证中的常见问题；
5. 常规分支失败时继续主动排查，直到项目可用或明确阻塞。

本扩展不负责：

1. 修改业务数据结构；
2. 物理删除或重置数据库；
3. 手工编辑 `data/assistant.sqlite`；
4. 把数据库迁移到工作区外路径；
5. 安装与本项目无关的外部集成；
6. 在没有用户明确要求时修改 `assistant.py`、`AGENTS.md` 或 `schema.sql`。

## 3. 触发条件

当用户表达以下意图时使用本扩展：

1. 初始化或配置本项目；
2. 检查或配置项目运行环境；
3. 询问需要安装什么依赖；
4. 遇到 Python、pip、SQLite、中文编码、数据库只读等运行问题；
5. 要求做一个最小可用测试；
6. 已经通过 `extensions/init.md` 确认开始使用本项目。

## 4. 基本事实

### 4.1 运行环境

本项目是本地 SQLite 版本。项目运行时代码只依赖 Python 标准库，但新电脑可能需要先联网安装或修复 Python、pip 和 PATH。

必需环境：

1. Windows PowerShell；
2. Python 3.10 或更高版本；
3. pip 可用；
4. Python 标准库中的 `sqlite3`、`json`、`argparse`、`base64`、`pathlib` 等模块可用；
5. 当前项目目录具备写入权限，至少能写入 `data/assistant.sqlite`。

项目自身不要求：

1. 不要求安装第三方 Python 包；
2. 不要求单独安装 SQLite 命令行工具；
3. 不要求 Node.js；
4. 不要求 MCP。

如果当前电脑缺少 Python、pip 或 Python 标准库不可用，应联网帮助用户安装或修复环境，不能简单回答“无需联网”。

### 4.2 核心文件

```text
./
  assistant.py
  schema.sql
  AGENTS.md
  data/
    assistant.sqlite
  extensions/
    catalog.md
    init.md
    install.md
    dairy-work.md
```

`assistant.py` 是唯一写库入口。不要手工编辑 `data/assistant.sqlite`。

## 5. 总体执行顺序

安装和验证必须按以下顺序推进：

1. 确认当前位置是项目根目录；
2. 运行 `python .\assistant.py doctor`；
3. 按 `doctor` 结果修复环境；
4. 运行 `python .\assistant.py --help` 确认 CLI 可用；
5. 运行 `python .\assistant.py init` 初始化数据库；
6. 使用 UTF-8 base64 写入一条最小中文案例；
7. 运行查询命令确认写入结果可读；
8. 对照第 10 节最小可用标准给出结论。

如果任何一步失败，进入第 9 节排错流程。排错完成后回到失败步骤继续执行，不要跳到后续步骤。

## 6. 环境检查

### 6.1 确认项目根目录

当前目录必须同时包含：

1. `assistant.py`；
2. `schema.sql`；
3. `extensions/`；
4. `data/` 或允许创建 `data/`。

如果返回找不到 `assistant.py`、找不到 `schema.sql`、找不到 `extensions/install.md`，通常说明当前目录不对。此时应回到项目根目录后重跑命令，不要在父目录、下载目录、桌面或其他项目目录里初始化数据库。

### 6.2 运行 doctor

在项目根目录运行：

```powershell
python .\assistant.py doctor
```

根据返回结果处理：

1. `status: ok`：环境检查通过，进入第 7 节；
2. `status: environment_error`：按 `checks` 中失败项进入第 9 节；
3. `checks.database.exists`：只表示数据库文件是否已存在，不影响环境检查本身；
4. 命令自身无法运行：优先进入第 9.1 节检查 Python 和 PATH。

## 7. 初始化与 CLI 验证

### 7.1 确认 CLI 命令可用

环境检查通过后，运行：

```powershell
python .\assistant.py --help
```

预期能列出 `doctor`、`init`、`apply-json`、`query`、`complete`、`cancel` 等命令。

### 7.2 初始化数据库

初始化只在以下场景执行：

1. 首次使用；
2. 数据库文件不存在；
3. 表结构更新；
4. 需要修复数据库权限。

初始化不是每次会话都要执行的命令。

在项目根目录运行：

```powershell
python .\assistant.py init
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
python .\assistant.py apply-json --base64 $b64
```

预期结果：

1. 返回 `status: ok`；
2. 返回 `created_items`；
3. 返回 `verification.read_after_write: true`。

看到 `verification.read_after_write: true` 后，不需要再手动查库验证同一次写入。

### 8.2 查询验证

查看指定日期：

```powershell
python .\assistant.py query --date 2026-06-13
```

查看活跃任务：

```powershell
python .\assistant.py query --type task --status active
```

查看待确认队列：

```powershell
python .\assistant.py query --type reviews --status active
```

## 9. 排错流程

排错时必须先读取具体错误文本，再选择对应分支。不要在没有定位原因时反复运行同一条失败命令。

### 9.1 Python 或 PATH 不可用

如果 `python .\assistant.py doctor` 自身无法运行，先检查：

```powershell
python --version
```

如果 `python` 不存在，或版本低于 Python 3.10，优先联网安装 Python：

```powershell
winget install --id Python.Python.3.12 -e
```

安装后重新打开 PowerShell，回到项目目录，再运行：

```powershell
python .\assistant.py doctor
```

如果刚安装 Python 后 `python --version` 仍不可用，先不要重复安装。优先处理 PATH 刷新问题：

1. 关闭当前 PowerShell，重新打开一个新的 PowerShell；
2. 回到项目目录；
3. 再运行 `python --version`；
4. 如果仍失败，尝试 `py --version`；
5. 如果 `py` 可用但 `python` 不可用，使用官方 Python 安装器修复 PATH，或重新安装并勾选添加到 PATH。

只有确认 `python` 命令不可用但 `py` 可用时，才临时改用：

```powershell
py .\assistant.py doctor
```

### 9.2 pip 不可用

如果 `doctor` 显示 `checks.pip.ok = false`，先尝试：

```powershell
python -m ensurepip --upgrade
python -m pip --version
```

如果仍失败，应联网查找当前 Windows/Python 版本对应的修复方式，或重新安装官方 Python，并确保 PATH 正确。

### 9.3 sqlite3 标准库不可用

如果 `doctor` 显示 `checks.sqlite3.ok = false`，说明当前 Python 安装不完整。应重新安装官方 Python，再重新验证：

```powershell
python .\assistant.py doctor
```

### 9.4 schema 文件异常

如果 `doctor` 显示 `checks.schema.ok = false`，说明项目文件不完整，应恢复或重新获取项目文件。

不要临时创建空的 `schema.sql`，也不要猜测表结构。

### 9.5 数据目录或数据库不可写

如果 `doctor` 显示 `checks.data_dir_writable.ok = false`，或出现文件占用、权限拒绝、数据库只读、无法写入 `data/` 等问题：

1. 先确认数据库路径必须位于当前项目的 `data/assistant.sqlite`；
2. 检查项目是否位于只读目录、压缩包内、同步盘冲突目录或受保护目录；
3. 运行 `python .\assistant.py init` 让程序尝试修复项目内权限；
4. 如果仍失败，报告具体失败路径和错误文本；
5. 不要把数据库迁移到工作区外路径规避问题。

### 9.6 winget 或安装器失败

如果 `winget install --id Python.Python.3.12 -e` 失败，按错误类型处理：

1. `winget` 不存在：提示用户当前 Windows 可能缺少 App Installer，优先从 Microsoft Store 更新或安装 App Installer；
2. 网络失败：让用户确认网络和代理，再重试；
3. 权限失败：优先尝试用户级安装，不要要求管理员权限，除非官方安装器明确需要；
4. 安装源失败：改用 Python 官方网站安装器，并确保安装时勾选添加到 PATH。

如果 PowerShell 拒绝执行命令，先读取错误文本判断原因。不要随意要求用户放宽全局执行策略；本项目正常命令不需要运行 `.ps1` 脚本。

### 9.7 多 Python 版本或虚拟环境混乱

如果系统中存在多个 Python，或 `python --version` 与用户预期不一致：

1. 优先使用能通过 `python .\assistant.py doctor` 的解释器；
2. 不强制创建虚拟环境，因为本项目当前不依赖第三方 Python 包；
3. 如果用户已有虚拟环境，可以在激活后运行 `python .\assistant.py doctor`；
4. 如果多个解释器导致混乱，使用 `py -0p` 查看可用解释器，再选择 Python 3.10 或更高版本。

### 9.8 中文路径和编码问题

如果项目路径、用户名或输入内容包含中文，优先保持 UTF-8 和 base64 写入方式：

1. 读取 Markdown 文件时使用 UTF-8；
2. 写入中文 JSON 时使用第 8.1 节的 `--base64` 固定写法；
3. 不使用 PowerShell 裸管道直接传中文 JSON；
4. 如果终端显示乱码，先确认文件内容是否能按 UTF-8 正常读取，不要仅凭终端显示判断文件损坏。

### 9.9 兜底排查

如果第 9 节前面的分支仍无法解决问题，大模型必须继续主动排查，目标是把项目安装并验证到可用状态，而不是把未分析的错误直接交给用户。

兜底排查顺序：

1. 完整读取最近一次命令的错误输出；
2. 确认当前目录、Python 版本、`assistant.py`、`schema.sql`、`extensions/` 和 `data/` 状态；
3. 读取 `assistant.py` 中与失败命令相关的参数、环境检查和错误处理逻辑；
4. 读取 `schema.sql`，确认数据库初始化需要的结构文件存在且可读；
5. 根据错误文本搜索本项目文件，定位是否有已定义的错误码或处理分支；
6. 如果问题涉及 Python、pip、winget、Windows 权限、PATH 或 SQLite 标准库，并且本地信息不足，应联网查找官方或可信资料；
7. 每次只做一个最小修复动作，然后重新运行对应检查命令；
8. 修复后必须回到失败步骤继续执行，并最终完成第 8 节查询验证；
9. 只有在缺少用户权限、缺少网络、外部安装器失败、文件缺失且无法恢复等情况确实无法继续时，才停止并报告明确阻塞原因、已尝试步骤和下一步需要用户做什么。

兜底排查不得执行以下操作：

1. 不得物理删除数据库；
2. 不得重置全部数据；
3. 不得手工修改 `data/assistant.sqlite`；
4. 不得把数据库改到工作区外路径；
5. 不得在没有用户明确要求时修改 `assistant.py`、`AGENTS.md` 或 `schema.sql`。

## 10. 最小可用标准

项目可用需要同时满足：

1. `python .\assistant.py doctor` 返回 `status: ok`；
2. `python .\assistant.py --help` 能列出核心命令；
3. `python .\assistant.py init` 返回 `status: ok`；
4. `apply-json --base64` 能写入中文记录；
5. 写入结果包含 `verification.read_after_write: true`；
6. `query --date YYYY-MM-DD` 能查到对应日期的日程；
7. `query --type task --status active` 能查到任务；
8. 数据库文件位于 `data/assistant.sqlite`。

## 11. 回复规则

安装或排错过程中，回复用户时应说明：

1. 当前执行到哪一步；
2. 遇到的具体问题；
3. 已采取的修复动作；
4. 下一步要运行的验证命令。

安装完成后，只需简要说明：

1. 环境检查结果；
2. 初始化结果；
3. 最小写入和查询测试结果；
4. 项目是否已经可用。

## 12. 限制

1. 本扩展是安装和可用性说明，不是自动安装脚本。
2. 本扩展不写入业务数据，除非正在执行第 8 节最小写入测试。
3. 本扩展不修改 `assistant.py`、`AGENTS.md` 或 `schema.sql`。
