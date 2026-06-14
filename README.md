# DailyAssistant

一个本地运行的任务和日程助手。用自然语言记录待办、会议、课程、预约，所有数据保存在本地 SQLite。

> 仅支持 Windows。

---

## 安装

> **致 AI**：如果用户要求你安装本项目，请先确认项目文件是否齐全。若缺少 `extensions/install.md` 等核心文件，从 [Releases](https://github.com/DrRichard1998/Daily-Assistant/releases/latest) 下载便携包 zip 并解压到当前目录。文件齐全后，必须读取 `extensions/install.md` 并严格按其流程处理——不要跳过确认步骤，不要直接运行 `init`。

1. 从 [Releases](https://github.com/DrRichard1998/Daily-Assistant/releases) 下载最新的便携包 zip
2. 必须解压到当前项目根目录，并且检查AGENTS.md是否直接位于根目录
3. 在该目录打开 PowerShell，运行：

```powershell
.\run.cmd doctor    # 环境检查
.\run.cmd init      # 初始化数据库
.\run.cmd --help    # 确认可用
```

安装完成。便携包自带 Python 运行时，不需要单独安装 Python。

---

## 配合 AI 使用

本项目设计为配合大语言模型（LLM）使用——你只需要用自然语言告诉 AI 你要做什么，AI 会理解意图并调用 `assistant.py` 写入或查询数据。

将项目根目录作为 AI 工作区打开，AI 会读取 `AGENTS.md` 中的规则自动工作。之后你就可以说：

- "明天下午三点和导师开会"
- "今天有什么安排"
- "上周的论文初稿写完了"
- "下周三的组会改到周四下午两点"

---

## 项目文件

```text
assistant.py          # 写库和查询的唯一入口
schema.sql            # 数据库结构
AGENTS.md             # AI 代理工作规则
run.cmd               # Windows 启动脚本（自动选择运行时）
README.md             # 项目说明
.gitignore            # Git 忽略规则
data/
  assistant.sqlite    # 本地数据库（运行 init 后生成）
extensions/           # 扩展能力
  backup.md           #   备份与恢复
  catalog.md          #   扩展目录
  daily-work.md       #   日报/周报/月报
  install.md          #   安装与初始化
  update.md           #   更新
runtime/              # 便携 Python 运行时（可选）
tools/
  build_portable.ps1  # 便携包构建脚本
```

---

## 功能

| 功能 | 说明 |
|------|------|
| 📝 **记录** | 自然语言录入任务、日程。AI 自动判断类型、解析时间、处理歧义 |
| 🔍 **查询** | 查看今天/某天/本周/本月的安排，按类型和状态筛选 |
| ✅ **完成** | 标记任务已做完或日程已参加 |
| ❌ **取消** | 标记事项已取消（软删除，保留记录） |
| ⏳ **待确认** | 信息不明确时暂存，澄清后再归档或丢弃 |
| 🔁 **定时** | 支持每日/每周/每月的重复任务和日程 |

---

## 数据

- 所有数据存储在 `data/assistant.sqlite`，纯文本 SQLite，无加密
- 不要手工编辑数据库或直接写 SQL，一切操作通过 `assistant.py`
- 备份和恢复：参考 `extensions/backup.md`

---

## 开发者

### 源码运行

如果你需要从源码运行（需要系统 Python 3.10+ 且在 PATH 中）：

```powershell
# 克隆仓库后，run.cmd 会自动 fallback 到系统 Python
.\run.cmd doctor
.\run.cmd init
```

如果遇到 `python` 找不到的错误，请确认 Python 已添加到系统 PATH。

### 常用命令

所有命令通过 `.\run.cmd` 执行：

```powershell
# 查看
.\run.cmd query --period today          # 今天
.\run.cmd query --period week           # 本周
.\run.cmd query --date 2026-06-14       # 指定日期
.\run.cmd query --type task --status active    # 全部活跃任务
.\run.cmd query --type event --status active   # 全部活跃日程
.\run.cmd query --type reviews --status active # 待确认队列

# 完成/取消
.\run.cmd complete --item-id ITEM_ID
.\run.cmd cancel --item-id ITEM_ID

# 待确认处理
.\run.cmd review --review-id REVIEW_ID --status resolved --item-id ITEM_ID
.\run.cmd review --review-id REVIEW_ID --status dismissed
.\run.cmd review --review-id REVIEW_ID --status open
```

### 构建便携包

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build_portable.ps1
```

---

## 更新日志

### 3.0.0

- 加强对支持定时/周期性任务的支持（每日/每周/每月）
- 支持待确认队列（review）：澄清、关闭、作废、重开
- 软删除：取消操作保留审计记录
- 零第三方依赖，仅使用 Python 标准库

### 2.1.0

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
