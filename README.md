# DailyAssistant

当前适配 Windows 下的 Codex，其他平台暂未测试。

DailyAssistant 是一个本地运行的任务和日程助手。它使用 LLM 理解自然语言输入，使用 `assistant.py` 校验、写入和查询数据，并使用 SQLite 在本机保存任务、日程和待确认事项。

本项目适合用来记录和查询个人安排，例如待办事项、会议、课程、预约、考试、截止日期，以及需要之后再确认的信息。

## 当前版本

- 应用版本：`DailyAssistant 3.0.0`
- 版本来源：`assistant.py` 中的 `APP_VERSION`
- 查看版本：

```powershell
.\run.cmd --version
```

当前版本使用本地 SQLite 数据库保存数据，支持记录、查询、完成、取消、待确认处理和扩展能力；主版本以便携包形式运行，普通用户通过 `run.cmd` 使用随包提供的本地运行时。

## 核心能力

- 记录：把自然语言整理为任务、日程或待确认事项。
- 查询：查看今天、某天、本周、本月或指定时间范围内的任务和日程。
- 完成：把明确的任务标记为已完成。
- 取消：把记错、取消或作废的事项标记为已取消。
- 待确认：在日期、类型或时间含义不清时，先进入待确认队列；澄清后可关闭、作废、重开并关联到实际事项。
- 扩展：通过 `extensions/` 目录维护安装、备份、更新等可选能力。

## 项目结构

```text
.
|-- run.cmd
|-- assistant.py
|-- schema.sql
|-- AGENTS.md
|-- data/
|-- runtime/
|   `-- python/
`-- extensions/
    |-- catalog.md
    |-- init.md
    |-- install.md
    |-- backup.md
    |-- update.md
    `-- daily-work.md
```

其中：

- `assistant.py` 是唯一的写库和查询入口。
- `run.cmd` 是日常 CLI 入口，便携包内会调用 `runtime/python/python.exe`。
- `schema.sql` 定义 SQLite 数据库结构。
- `data/assistant.sqlite` 是安装后由 `init` 创建的本地数据库文件，默认不随便携包发布。
- `runtime/python/` 是便携包运行时目录。
- `extensions/` 保存扩展能力说明。
- 本项目依赖大语言模型代理作为入口，`AGENTS.md` 必须放在项目根目录文件夹下，用于保存代理在本目录内工作的项目规则。

## 运行环境

运行便携包只需要：

- Windows PowerShell
- 完整的 DailyAssistant 运行根目录
- 可写的安装目录；初始化时会创建本地数据库

运行所需组件已随便携包提供；用户只需保留便携包内文件并在运行根目录中使用 `run.cmd`。

## 安装与初始化

推荐安装方式是直接下载 GitHub Release 中的 `DailyAssistantPortable-3.0.0.zip`，并把压缩包内容解压到目标运行根目录。AI 或 Codex 等自动工具安装本项目时，应下载 Release 里的便携 zip，不要克隆或下载整个仓库来安装；解压 Release zip 后，直接读取并执行 `extensions/install.md` 中的安装流程。

目标运行根目录必须直接包含 `run.cmd`、`assistant.py`、`schema.sql`、`AGENTS.md`、`extensions/` 和 `runtime/`；发布包默认不包含 `data/`，初始化时会创建本地数据库。不要在运行根目录下再套一层 `DailyAssistantPortable` 子目录。

安装后的根目录结构应类似：

```text
DailyAssistant/
|-- run.cmd
|-- assistant.py
|-- schema.sql
|-- AGENTS.md
|-- extensions/
`-- runtime/
```

普通用户进入这个安装根目录后运行：

```powershell
.\run.cmd doctor
.\run.cmd init
.\run.cmd --help
```

默认不会复制当前项目的私人数据库，也不会在便携包中内置 `data/assistant.sqlite`；用户安装后运行 `.\run.cmd init` 时会创建本地数据库。

初始化成功后，数据库会位于：

```text
data/assistant.sqlite
```

## 常用查询命令

查看今天的任务、日程和待确认事项：

```powershell
.\run.cmd query --period today
```

查看本周安排：

```powershell
.\run.cmd query --period week
```

查看指定日期：

```powershell
.\run.cmd query --date 2026-06-12
```

查看全部活跃任务：

```powershell
.\run.cmd query --type task --status active
```

查看全部活跃日程：

```powershell
.\run.cmd query --type event --status active
```

查看待确认队列：

```powershell
.\run.cmd query --type reviews --status active
```

待确认状态映射：

- `active`：待处理，对应 `open`。
- `completed`：已解决，对应 `resolved`。
- `cancelled`：已作废，对应 `dismissed`。
- `all`：全部待确认项。

`query --type reviews` 不带日期参数时会查询整个待确认队列；显式传入 `--date`、`--period` 或 `--from/--to` 时，会按待确认项创建时间过滤。

## 处理待确认项

用户补充信息后，先按实际情况创建或更新任务/日程，再关闭对应待确认项：

```powershell
.\run.cmd review --review-id REVIEW_ID --status resolved --item-id ITEM_ID
```

如果某条待确认项是误判、历史遗留或用户确认不需要处理，标记为作废：

```powershell
.\run.cmd review --review-id REVIEW_ID --status dismissed
```

如果误关了待确认项，可以重新打开：

```powershell
.\run.cmd review --review-id REVIEW_ID --status open
```

## 写入数据

日常使用时，推荐直接让 Codex 根据自然语言生成符合项目规则的 JSON，并通过 `.\run.cmd apply-json --base64` 写入数据库。

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
.\run.cmd apply-json --base64 $b64
```

写入成功后，`apply-json` 会返回写后读取结果。看到 `verification.read_after_write = true` 后，不需要再为同一次写入额外查询数据库。

## 完成和取消

完成明确任务：

```powershell
.\run.cmd complete --item-id ITEM_ID
```

取消任务或日程：

```powershell
.\run.cmd cancel --item-id ITEM_ID
```

取消是软删除：事项会被标记为 `cancelled`，数据库行不会被物理删除。

## 数据与安全

- 本项目的事实来源是 `data/assistant.sqlite`。
- 不要手工编辑 SQLite 数据库文件。
- 不要直接写 SQL 修改业务数据。
- 所有写入、查询、完成和取消操作都应通过 `run.cmd` 调用 `assistant.py` 完成。
- 备份和恢复流程请参考 `extensions/backup.md`。

## 扩展能力

可用扩展记录在：

```text
extensions/catalog.md
```

常见扩展包括：

- `init`：首次使用或数据库缺失时的说明入口。
- `install`：检查、构建和初始化便携运行环境。
- `backup`：备份和恢复用户数据。
- `update`：从 GitHub 仓库检查并应用程序更新。
- `daily-work`：生成每日任务清单自动化。

## 更新日志

### 3.0.0

- 更新应用版本号为 `DailyAssistant 3.0.0`。
- 发布 `DailyAssistantPortable-3.0.0.zip` 便携包；默认不包含当前项目的私人数据库，也不内置初始化数据库文件。

### 2.1.0

- 主运行入口切换为 `run.cmd`，便携包内使用 `runtime/python/python.exe`，运行所需组件随包提供。
- 新增 `tools/build_portable.ps1`，用于生成 `dist/DailyAssistantPortable`。

- 新增 `review` 命令，可用明确的 `review_id` 更新待确认项状态。
- `review --status resolved --item-id ITEM_ID` 用于在创建或更新事项后关闭待确认项，并关联到实际事项。
- `review --status dismissed` 用于标记误判、历史遗留或无需处理的待确认项。
- `review --status open` 用于重新打开误关的待确认项，并清空 `resolved_at`。
- `query --type reviews` 不带日期参数时查询整个待确认队列；显式传入日期或范围时，按 `review_queue.created_at` 过滤。
- `extensions/install.md` 强化安装前的项目根目录检查，要求核心文件位于根目录或正确的 `extensions/` 位置；发现错放文件时按安全规则修正或要求用户确认。

### 2.0.0

- 新增定时/周期性任务和日程支持：`apply-json` 可在 item 中写入 `recurrence`，支持 `daily`、`weekly`、`monthly`、`interval`、`by_weekday`、`by_month_day` 和 `active_until`。
- 查询命令保持不变，`query` 会按 `recurrence_rules` 在查询范围内展开周期实例，并用 `active_until` 过滤已结束的计划；周期实例返回 `recurrence.rule_id` 和 `recurrence.occurrence_date`。
- 支持打卡：对定时 item 执行 `complete` 会写入某次 `recurrence_status.status = completed`，不会把母 item 标记为完成；未指定日期时默认选择最近一条应完成的实例。
- 支持取消某次或整个定时任务：`cancel --scope occurrence --occurrence-date YYYY-MM-DD` 取消某次，`cancel --scope series` 取消整个计划。
- 支持修改某次或整个定时任务：`update --scope occurrence --occurrence-date YYYY-MM-DD` 写入某次覆盖字段，`update --scope series` 修改母 item。
- 有限周期计划到期后，在下一次 `complete` 前自动把母 item 标记为 `completed`；历史打卡记录保留。
- 备份和恢复已包含 `recurrence_rules` 和 `recurrence_status` 两张新表。
