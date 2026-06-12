# DairyAssistant

DairyAssistant 是一个本地运行的任务和日程助手。它使用 LLM 理解自然语言输入，使用 `assistant.py` 校验、写入和查询数据，并使用 SQLite 在本机保存任务、日程和待确认事项。

本项目适合用来记录和查询个人安排，例如待办事项、会议、课程、预约、考试、截止日期，以及需要之后再确认的信息。

## 当前版本

- 应用版本：`DairyAssistant 1.0.5`
- 版本来源：`assistant.py` 中的 `APP_VERSION`
- 查看版本：

```powershell
python .\assistant.py --version
```

当前版本使用本地 SQLite 数据库保存数据，支持记录、查询、完成、取消、待确认和扩展能力；运行环境仍以 Python 3.10+ 和标准库为主，不需要安装第三方 Python 包。

## 核心能力

- 记录：把自然语言整理为任务、日程或待确认事项。
- 查询：查看今天、某天、本周、本月或指定时间范围内的任务和日程。
- 完成：把明确的任务标记为已完成。
- 取消：把记错、取消或作废的事项标记为已取消。
- 待确认：在日期、类型或时间含义不清时，先进入待确认队列。
- 扩展：通过 `extensions/` 目录维护安装、备份、更新等可选能力。

## 项目结构

```text
.
|-- assistant.py
|-- schema.sql
|-- AGENTS.md
|-- data/
|   `-- assistant.sqlite
`-- extensions/
    |-- catalog.md
    |-- init.md
    |-- install.md
    |-- backup.md
    |-- update.md
    `-- dairy-work.md
```

其中：

- `assistant.py` 是唯一的写库和查询入口。
- `schema.sql` 定义 SQLite 数据库结构。
- `data/assistant.sqlite` 是本地数据库文件。
- `extensions/` 保存扩展能力说明。
- `AGENTS.md` 保存 Codex 在本目录内工作的项目规则。

## 运行环境

推荐环境：

- Windows PowerShell
- Python 3.10 或更高版本
- Python 标准库中的 `sqlite3`、`json`、`argparse`、`base64`、`pathlib`

当前项目不要求安装第三方 Python 包，也不要求单独安装 SQLite 命令行工具、Node.js 或 MCP。

## 安装与初始化

在项目根目录运行：

```powershell
python .\assistant.py doctor
```

如果环境检查通过，初始化数据库：

```powershell
python .\assistant.py init
```

确认 CLI 可用：

```powershell
python .\assistant.py --help
```

初始化成功后，数据库会位于：

```text
data/assistant.sqlite
```

## 常用查询命令

查看今天的任务、日程和待确认事项：

```powershell
python .\assistant.py query --period today
```

查看本周安排：

```powershell
python .\assistant.py query --period week
```

查看指定日期：

```powershell
python .\assistant.py query --date 2026-06-12
```

查看全部活跃任务：

```powershell
python .\assistant.py query --type task --status active
```

查看全部活跃日程：

```powershell
python .\assistant.py query --type event --status active
```

查看待确认队列：

```powershell
python .\assistant.py query --type reviews --status active
```

## 写入数据

日常使用时，推荐直接让 Codex 根据自然语言生成符合项目规则的 JSON，并通过 `assistant.py apply-json --base64` 写入数据库。

中文 JSON 应使用 UTF-8 base64 方式传递，避免 PowerShell 编码问题：

```powershell
$json = @'
{
  "record": {
    "source": "codex",
    "input_type": "text",
    "canonical_text": "明天下午三点和导师开会",
    "raw_text": "明天下午三点和导师开会",
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
    }
  ],
  "relations": [],
  "review": null
}
'@
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
python .\assistant.py apply-json --base64 $b64
```

写入成功后，`apply-json` 会返回写后读取结果。看到 `verification.read_after_write = true` 后，不需要再为同一次写入额外查询数据库。

## 完成和取消

完成明确任务：

```powershell
python .\assistant.py complete --item-id ITEM_ID
```

取消任务或日程：

```powershell
python .\assistant.py cancel --item-id ITEM_ID
```

取消是软删除：事项会被标记为 `cancelled`，数据库行不会被物理删除。

## 数据与安全

- 本项目的事实来源是 `data/assistant.sqlite`。
- 不要手工编辑 SQLite 数据库文件。
- 不要直接写 SQL 修改业务数据。
- 所有写入、查询、完成和取消操作都应通过 `assistant.py` 完成。
- 备份和恢复流程请参考 `extensions/backup.md`。

## 扩展能力

可用扩展记录在：

```text
extensions/catalog.md
```

常见扩展包括：

- `init`：首次使用或数据库缺失时的说明入口。
- `install`：检查和初始化本地运行环境。
- `backup`：备份和恢复用户数据。
- `update`：从 GitHub 仓库检查并应用程序更新。
- `dairy-work`：生成每日任务清单自动化。
