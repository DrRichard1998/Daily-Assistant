# DailyAssistant 工作规则

本目录使用 SQLite 作为事实来源。处理本目录内的记录、查询、完成和维护请求时，只遵守本文件；不要回到父目录，也不要扫描无关目录。

## 1. 核心原则

- 用户可以自然语言输入，不需要学习命令格式。
- Codex 负责理解用户意图并生成 JSON。
- `assistant.py` 负责校验、写库、查询和写后读取。
- 不直接写 SQL，不手工修改数据库文件。
- 不为同一次写入额外运行查询命令做验证；`apply-json` 已经返回写后读取结果。
- 默认中文回复，除非用户明确要求其他语言。

事实来源：

```text
data/assistant.sqlite
schema.sql
assistant.py
extensions/catalog.md
```

## 2. 意图分流

收到用户输入后，先只判定一个意图，再进入对应路径。不要展开架构讨论，不要生成多套方案，不要读取无关文件，除非用户明确要求。

先判断用户请求是否属于基础意图：`record`、`query`、`update`、`complete`、`delete`、`maintenance`。

如果请求不属于这些基础意图，或者看起来属于 `chat`，但内容可能是项目扩展能力，例如安装、初始化、备份、恢复、升级、导出、报表、日报、周报、月报、自动化、定时生成、周期性处理等，必须先读取 `extensions/catalog.md`。若目录中有匹配扩展，再读取对应的 `extensions/{name}.md` 并按该扩展说明处理。只有确认没有匹配扩展后，才进入普通 `chat` 路径。

扩展发现只允许读取 `extensions/catalog.md` 和已匹配到的扩展文件；不要扫描父目录、无关目录或未匹配扩展文件。

| 意图 | 使用条件 | 处理路径 |
|---|---|---|
| `record` | 用户要记录新任务、新日程或待确认事项 | 记录路径 |
| `query` | 用户要查看今天、某天、某段时间、本周、本月、任务、日程或待确认事项 | 查询路径 |
| `update` | 用户要修改某个任务或日程的标题、内容、时间、地点、人员、项目、状态或其他字段 | 修改路径 |
| `complete` | 用户表示某个任务或日程已完成、已参加或已发生 | 完成路径 |
| `delete` | 用户表示某个事项记错了、要删除、取消或作废 | 删除/取消路径 |
| `maintenance` | 用户要求修改本目录代码、规则、数据库或文档 | 维护路径 |
| `chat` | 用户提出与任务、日程、完成、数据库维护和项目扩展能力无关的问题或闲聊 | 聊天路径 |

## 3. 输入预处理

收到图片、语音或混合输入时，先转成文字，形成 `canonical_text`，再按统一文本进入意图分流。

- 图片：通过 OCR 或视觉理解提取文字和任务信号。
- 语音：先转写，再提取任务信号。
- 混合输入：合并文字、图片识别结果和语音转写结果。

如果 `canonical_text` 包含日程、会议、课程、预约、考试、截止日期、待办清单或待确认事项，即使用户没有额外说明，也按 `record` 路径写入 `event`、`task` 或 `review`。只有内容没有可记录事项时，才按 `chat` 处理。

不保存图片或语音原文件；写入数据库的只允许是转换后的文字。

## 4. 分类规则

只创建两类 `item`。

`task`：可以提前完成，日期通常是截止时间。

常见动作：提交、完成、准备、填写、上传、发送、支付、申请、注册、回复、修改、整理、跟进。

`event`：只能到点发生或参与，日期是发生时间。

常见信号：会议、开会、课程、电话、面试、预约、考试、直播、出席、到场、参加。

一句话同时包含准备事项和到点发生的事件时，拆成多个 `item`，并用 `prepares_for` 关联准备任务和对应日程。

如果类型、日期语义会影响 `task`/`event` 判断，或日程缺少发生时间，不要强行创建任务或日程，应创建 `review` 或向用户提出一个最小澄清问题。

单纯缺少待办事项的截止日期不属于歧义。明确是 `task` 时直接创建任务，并将 `due_at` 设为 `null`。

## 5. 记录路径

适用：用户要保存一条或多条任务、日程或待确认事项。

执行步骤：

1. 保留用户原话或输入预处理得到的文字为 `record.canonical_text`；图片、语音或混合输入应设置相应的 `record.input_type`，并且不保留原始媒体文件。
2. 基于当前日期和 `Asia/Shanghai` 解析相对日期。
3. 只判断 `task`、`event` 或 `review`。
4. 明确是待办事项但没有明确截止日期时，创建 `task`，并把 `due_at` 设为 `null`；不要为缺少截止日期追问。
5. 生成符合 JSON 合约的对象。
6. 将 JSON 按 UTF-8 编码为 base64。
7. 运行 `python .\assistant.py apply-json --base64 BASE64_JSON`。
8. 不保留临时 JSON 文件。
9. 只根据 CLI 返回的 `verification` 回复用户。

PowerShell 固定写法：

```powershell
$json = @'
{JSON}
'@
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
python .\assistant.py apply-json --base64 $b64
```

不要使用 PowerShell 裸管道或 `--json` 直接传中文 JSON。

## 6. 查询路径

适用：用户要查看已有安排、任务、日程或待确认项。

统一使用 `query` 命令。

```powershell
python .\assistant.py query
python .\assistant.py query --date YYYY-MM-DD
python .\assistant.py query --period today
python .\assistant.py query --period week
python .\assistant.py query --period month
python .\assistant.py query --from YYYY-MM-DD --to YYYY-MM-DD
python .\assistant.py query --date YYYY-MM-DD --type task --status active
python .\assistant.py query --date YYYY-MM-DD --type event --status active
python .\assistant.py query --date YYYY-MM-DD --type reviews --status active
```

范围选择规则：

- 用户问“今天有什么”“今天安排”“今天任务和日程”“今天待办和日程”等完整视图：运行 `python .\assistant.py query --period today`。
- 用户只问某天的任务、待办、事项：运行 `python .\assistant.py query --date YYYY-MM-DD --type task --status active`。
- 用户只问某天的日程、会议、预约、课程、考试、活动：运行 `python .\assistant.py query --date YYYY-MM-DD --type event --status active`。
- 用户问“本周有什么”“这周安排”“本周任务和日程”：运行 `python .\assistant.py query --period week`。
- 用户问“本月有什么”“这个月安排”“本月任务和日程”：运行 `python .\assistant.py query --period month`。
- 用户只问某段时间的任务、待办、事项：运行 `python .\assistant.py query --from YYYY-MM-DD --to YYYY-MM-DD --type task --status active`。
- 用户只问某段时间的日程、会议、预约、课程、考试、活动：运行 `python .\assistant.py query --from YYYY-MM-DD --to YYYY-MM-DD --type event --status active`。
- 用户明确要查看已完成、已取消或全部状态时，分别使用 `--status completed`、`--status cancelled` 或 `--status all`。
- 用户明确要查看全部活跃任务列表，而不是某天或某段时间视图：运行 `python .\assistant.py query --type task --status active`。
- 用户明确要查看全部活跃日程列表，而不是某天或某段时间视图：运行 `python .\assistant.py query --type event --status active`。
- 用户只问某天的待确认、待澄清、需要我确认的事项：运行 `python .\assistant.py query --date YYYY-MM-DD --type reviews --status active`。
- 用户只问某段时间的待确认、待澄清、需要我确认的事项：运行 `python .\assistant.py query --from YYYY-MM-DD --to YYYY-MM-DD --type reviews --status active`。
- 用户明确要查看待确认队列，而不是某天或某段时间视图：运行 `python .\assistant.py query --type reviews --status active`。

`query` 入参规则：

- `--date`、`--period`、`--from/--to` 三选一；不传时默认等同 `--period today`。
- `--from` 和 `--to` 必须同时出现，且范围包含起止两天。
- `--period` 可选 `today`、`week`、`month`。
- `--type` 可选 `task`、`event`、`reviews`；不传时返回三类内容。
- `--status` 可选 `active`、`completed`、`cancelled`、`all`；不传时默认 `active`。
- 当 `--type reviews` 时，`active` 对应 `open`，`completed` 对应 `resolved`，`cancelled` 对应 `dismissed`。

回复只总结 CLI 返回的数据，不补充未查询到的信息。CLI 返回的非空列表字段必须覆盖；可以合并展示，但不得遗漏。

## 7. 修改路径

适用：用户表示要修改某个任务或日程的任意用户输入字段，例如标题、内容、截止时间、开始时间、结束时间、全天、项目、人员、地点、类型或状态。

修改默认是原地更新：更新 `items` 对应字段和 `updated_at`，并写入 `item_events.action='update'` 审计记录；不要取消旧事项后重新创建，除非用户明确要求。

执行步骤：

1. 如果用户提供明确 `item_id`，直接运行 `python .\assistant.py update --item-id ITEM_ID ...`。
2. 如果没有 `item_id`，先运行 `python .\assistant.py query --status active`。
3. 如果能唯一、高置信度匹配，修改该事项。
4. 如果无匹配或多匹配，不猜测，只问一个最小澄清问题。
5. 需要清空字段时使用 `--clear FIELD`；不要用空字符串或“无”冒充空值。
6. 回复时只报告 CLI 返回的更新结果，不为同一次修改额外查询验证。

常用命令示例：

```powershell
python .\assistant.py update --item-id ITEM_ID --title 新标题
python .\assistant.py update --item-id ITEM_ID --due-at 2026-06-16T23:59:00+08:00
python .\assistant.py update --item-id ITEM_ID --start-at 2026-06-16T14:00:00+08:00 --end-at 2026-06-16T15:00:00+08:00
python .\assistant.py update --item-id ITEM_ID --location 会议室A --people [张三,李四]
python .\assistant.py update --item-id ITEM_ID --clear due_at
```

支持修改的字段：

```text
type, title, content, status, confidence, due_at, start_at, end_at, all_day, project, people, location
```

## 8. 完成路径

适用：用户表示某项任务或日程已经完成、已参加或已发生。完成是修改状态的一种快捷路径。

执行步骤：

1. 如果用户提供明确 `item_id`，运行 `python .\assistant.py complete --item-id ITEM_ID`。
2. 如果没有 `item_id`，先运行 `python .\assistant.py query --status active`。
3. 如果能唯一、高置信度匹配，完成该事项。
4. 如果无匹配或多匹配，不猜测，只问一个最小澄清问题。

## 9. 删除/取消路径

适用：用户表示某个任务或日程记错了、识别错了、要删除、取消或作废。

本项目的删除默认是软删除：将 `items.status` 标记为 `cancelled`，并写入 `item_events.action='cancel'` 审计记录；不物理删除 SQLite 行。

执行步骤：

1. 如果用户提供明确 `item_id`，运行 `python .\assistant.py cancel --item-id ITEM_ID`。
2. 如果没有 `item_id`，先运行 `python .\assistant.py query --status active`。
3. 如果能唯一、高置信度匹配，取消该事项。
4. 如果无匹配或多匹配，不猜测，只问一个最小澄清问题。
5. 回复时可以按用户语义说“已删除”或“已取消”，但不要声称已从数据库物理删除。

## 10. 维护路径

适用：用户要求修改本目录实现、规则、数据库结构或文档。

执行步骤：

1. 先读取相关文件。
2. 给出拟修改的文件、目的和影响。
3. 等待用户二次确认。
4. 用户确认后，做最小必要改动。
5. 运行可用的 CLI 或语法检查验证。
6. 简要说明改动和验证结果。

除非用户明确点名要求修改，否则不得修改 `AGENTS.md` 和 `assistant.py`。

## 11. 聊天路径

适用：用户提出与日程、任务、完成状态或本目录维护无关的问题。

执行规则：

- 不运行 `assistant.py`。
- 不写入 SQLite。
- 不创建 `record`、`item` 或 `review`。
- 不修改任何文件。
- 纯寒暄或无需外部事实的问题直接回答。
- 需要外部事实、实时信息、网页资料，或用户明确要求查询时，调用联网能力后回答。

## 12. 回复规则

记录成功后只报告实际写入结果：

```text
已记录：
- 日程：...
- 任务：...
```

除非用户明确要求，不要在回复中列出 `record_id`、`item_id` 或其他数据库 ID。

进入待确认时只问一个最小问题。查询结果只总结 CLI 返回的数据。维护任务说明改动和验证结果。

查询回复规则：

- 只总结本次 CLI 返回的数据，不从其他文件、记忆或推断中补充内容。
- CLI 返回的非空列表字段必须覆盖；可以合并展示，但不得遗漏。
- CLI 未返回的字段不得主动补充。例如使用 `--type event` 查询时，不输出任务；使用 `--type task` 查询时，不输出日程。
- 空列表可以简要说明“没有”，但不必逐个列出所有空字段。
- 默认不输出 `id`、`record_id`、`created_at`、`updated_at` 等内部字段，除非用户明确要求或后续完成/取消操作需要用户区分具体条目。
- 完整查询视图中，`events.next_upcoming` 和 `tasks.upcoming_after_range` 应合并到“后续安排”中展示；如果同一天既有后续日程又有后续任务，应放在同一日期下。
- 任务查询中，默认按“逾期任务”“范围内到期任务”“后续任务”“无明确截止日期任务”的顺序回复。
- 日程查询中，默认按“范围内日程”“下一个日程”的顺序回复。
- 待确认查询中，只列出待确认问题；每条保留问题原文，必要时可附简短原因。

## 13. 当前限制

- `apply-json` 目前只支持 `create`。
- `apply-json` 返回的 `verification.read_after_write = true` 表示程序已完成写后读取。
- `update` 目前用明确 `item_id` 修改任务或日程字段；自然语言无 `item_id` 时应先查询并高置信匹配。
- `complete` 目前用明确 `item_id` 完成任务或日程。
- `cancel` 目前用明确 `item_id` 软删除任务或日程。
- 本目录的数据写入只通过 `assistant.py` 完成。

## 14. 异常、初始化与环境处理

### 14.1 通用顺序

不要为了每次用户输入额外手动检查 `data/assistant.sqlite`。正常情况下，先按用户意图进入对应路径，并运行该路径需要的 `assistant.py` 命令。

只在以下情况进入本节：

- 用户要求安装、初始化、配置环境或排查运行环境；
- 任一 `assistant.py` 命令返回 `needs_init`；
- `assistant.py` 返回 `environment_error`；
- `assistant.py` 命令自身无法运行；
- CLI 返回编码、权限、只读数据库等异常。

### 14.2 可绕过环境问题的提醒

如果 `record`、`query`、`update`、`complete`、`delete`、`maintenance` 或扩展流程在执行中遇到环境或配置问题，即使 Codex 已经通过备用方案完成本次请求，也应判断该问题是否会在后续操作中反复出现。

当问题明显会导致以后每次执行都增加思考时间、命令重试、额外上下文或 token 消耗时，最终回复中应简短提醒用户自行修复。提醒应包含：

1. 遇到的具体问题或现象；
2. 本次采用的备用处理方式；
3. 建议用户修复的方向。

这种提醒不应中断已经成功完成的主任务，也不要展开长篇环境排查，除非用户继续要求处理。

### 14.3 数据库缺失

如果任一 `assistant.py` 命令返回：

```json
{
  "status": "needs_init"
}
```

说明本项目处于未初始化状态。无论用户输入属于记录、查询、完成、维护、聊天或扩展请求，后续都必须先读取并执行：

```text
extensions/init.md
```

此时不要进入其他意图路径，不要直接运行 `python .\assistant.py init`，也不要写入数据库。只有用户确认开始使用本项目后，才按 `extensions/init.md` 转入 `extensions/install.md`。

### 14.4 环境异常

如果用户要求安装、初始化、配置环境或排查运行环境，先按 `extensions/install.md` 的解释器选择流程确定可用 Python 调用方式，再运行：

```powershell
& $DA_PY @DA_PY_ARGS .\assistant.py doctor
```

如果 `doctor` 返回：

```json
{
  "status": "environment_error"
}
```

则读取并执行：

```text
extensions/install.md
```

如果 `assistant.py doctor` 自身无法运行，必须先读取错误文本判断原因：

1. 若原因是 `python` 命令不存在、Python 未加入 PATH、需要使用完整解释器路径，或沙箱需要授权执行本机 Python，则直接读取并执行 `extensions/install.md`，不要展示数据库不存在或初始化数据库的文案。
2. 若 `assistant.py` 已经成功启动并明确返回 `status: needs_init`，才按第 14.3 节进入 `extensions/init.md`。
3. 若用户明确是在首次启用本项目且需要初始化数据库，可以进入 `extensions/init.md` 的确认流程；用户确认后再转入 `extensions/install.md`。

### 14.5 编码

中文 JSON 优先使用 `--base64`。

### 14.6 权限

`python .\assistant.py init` 会检查并修复本项目内 `data/` 和 `data/assistant.sqlite` 对当前 Windows 用户的写权限；所有写库命令也会在打开 SQLite 前执行同一套自检。

如果 CLI 返回 `readonly database`、`read-only` 或数据库不可写：

1. 不要请求在沙箱外重跑同一条写入命令。
2. 不要把权限问题交给用户确认。
3. 检查报错中的具体本地路径。
4. 如果无法在本目录内修复，停止并报告具体路径和错误。

数据库必须位于当前工作区内，不要为了写入记录改用工作区外路径。

## 15. JSON 合约

顶层结构：

```json
{
  "record": {
    "source": "codex",
    "input_type": "text",
    "canonical_text": "用户原话或统一后的文字",
    "raw_text": "用户原话",
    "extraction_method": "user_text",
    "extraction_confidence": 1.0,
    "original_retained": 0,
    "parse_status": "parsed",
    "parse_confidence": 0.95
  },
  "operations": [],
  "relations": [],
  "review": null
}
```

创建任务：

```json
{
  "action": "create",
  "temp_id": "task_1",
  "item": {
    "type": "task",
    "title": "准备会议材料",
    "status": "active",
    "due_at": "2026-06-16T23:59:00+08:00",
    "confidence": 0.92
  }
}
```

创建无明确截止日期的任务：

```json
{
  "action": "create",
  "temp_id": "task_1",
  "item": {
    "type": "task",
    "title": "定制 7763 的侧板",
    "status": "active",
    "due_at": null,
    "confidence": 0.9
  }
}
```

创建日程：

```json
{
  "action": "create",
  "temp_id": "event_1",
  "item": {
    "type": "event",
    "title": "和导师开会",
    "status": "active",
    "start_at": "2026-06-17T14:00:00+08:00",
    "end_at": null,
    "all_day": 0,
    "people": ["导师"],
    "confidence": 0.95
  }
}
```

创建关系：

```json
{
  "from_temp_id": "task_1",
  "to_temp_id": "event_1",
  "relation_type": "prepares_for"
}
```

待确认：

```json
{
  "reason": "ambiguous_type",
  "question": "“明天处理签证”是要明天完成一项任务，还是明天有预约或日程？"
}
```
