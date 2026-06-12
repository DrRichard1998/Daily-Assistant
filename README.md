# DailyAssistant

当前适配 Windows 下的 Codex，其他平台暂未测试。

DailyAssistant 是一个本地运行的任务和日程助理。它采用 LLM + 本地 CLI + SQLite 的架构：LLM 负责理解你的输入，`run.cmd` 调用本地程序负责校验、写入和查询，SQLite 负责在本机保存任务、日程和待确认事项。

本项目最大的优势是你不需要学习命令，也不需要把事情写成固定格式。你可以直接用自然语言输入，也可以发送语音或图片；例如，把邮件、通知、聊天记录或截图发给它，它会先转换和理解内容，再整理成任务、日程或待确认事项。

本项目适合用来记录和查询个人安排，例如待办事项、会议、课程、预约、考试、截止日期，以及需要之后再确认的信息。

它主要能做这些：

- 记录任务：周五前提交报告、记一下要买墨盒。
- 记录日程：明天下午三点和导师开会、下周一上午体检。
- 记录周期事项：每天早上 9 点吃水果，到下周五结束。
- 查询安排：今天有什么？本周任务，明天有哪些日程？
- 修改事项：把和导师开会改到下午 4 点。
- 完成事项：报告已经提交了。
- 删除/取消事项：取消明天的体检。
- 处理不确定信息：如果一句话不够清楚，它会只问一个必要的确认问题。

最省心的用法就是像发消息一样说：

- 明天上午 10 点和张老师开会。
- 这周还有什么任务没做？
- 把提交论文的截止时间改到 6 月 20 日晚上 11 点。
- 我完成了买药这件事。

也可以用语音或图片输入：

- 语音说：“明天上午十点和张老师开会”“提醒我周五前交报告”。
- 发送课程通知、邮件、聊天记录或会议截图，让它识别其中的考试、会议、预约、截止日期或待办事项。

它会负责判断输入是任务、日程还是待确认项，并把结果写进本地数据库。

## 当前版本

- 应用版本：`DailyAssistant 3.0.0`
- 版本来源：`assistant.py` 中的 `APP_VERSION`
- 查看版本：

```powershell
.\run.cmd --version
```

当前版本使用本地 SQLite 数据库保存数据，支持记录、查询、修改、完成、取消、待确认处理和扩展能力；主版本以便携包形式运行，通常由 Codex 等 AI 工具调用本地 `run.cmd` 完成数据库操作。用户主要用自然语言交互，不需要直接学习 CLI 命令。

## 核心能力

- 记录：把自然语言、语音转写或图片识别结果整理为任务、日程或待确认事项。
- 查询：查看今天、某天、本周、本月或指定时间范围内的任务、日程和待确认事项。
- 修改：更新任务或日程的标题、内容、时间、地点、人员、项目、状态等字段。
- 完成：把明确的任务或已发生的日程标记为已完成；周期性事项支持按某一次打卡。
- 取消：把记错、识别错、取消或作废的事项软删除；周期性事项支持取消某一次或整个计划。
- 待确认：在日期、类型或时间含义不清时，先进入待确认队列；澄清后可关闭、作废、重开并关联到实际事项。
- 周期事项：支持每天、每周、每月或每隔一定周期重复的任务和日程。
- 聊天：与记录、日程和数据库维护无关的问题不会写入数据库。
- 扩展：通过 `extensions/` 目录维护安装初始化、备份恢复、更新升级、每日任务清单等可选能力。

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

运行所需组件已随便携包提供；用户只需保留便携包内文件，Codex 等 AI 工具会在运行根目录中调用 `run.cmd` 完成本地校验、写入和查询。

## 安装与初始化

推荐安装方式是直接下载 GitHub Release 中的 `DailyAssistantPortable-3.0.0.zip`，并把压缩包内容解压到目标运行根目录。AI 或 Codex 等自动工具安装本项目时，应下载 Release 里的便携 zip，不要克隆或下载整个仓库来安装；解压 Release zip 后，直接读取并执行 `extensions/install.md` 中的安装流程。遇到 CLI 返回 `status: needs_init` 时，应展示 `extensions/init.md` 中的固定文本，再按用户确认转入安装流程。

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

需要手动检查安装状态时，可在这个安装根目录运行：

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
