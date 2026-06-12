# update

## 1. 目的

本扩展用于从固定 GitHub 仓库检查、下载并应用 DairyAssistant 程序更新。

默认更新源：

```text
https://github.com/DrRichard1998/Daily-Assistant.git
```

默认分支：

```text
main
```

本扩展的目标不是直接覆盖当前数据，而是完成以下闭环：

1. 确认当前目录和更新源正确；
2. 保护当前本地数据和程序文件；
3. 从 GitHub 获取最新程序版本；
4. 只更新程序文件，不覆盖用户数据库；
5. 更新后运行可用性验证；
6. 更新失败时能回滚到更新前状态。

## 2. 触发条件

当用户表达以下意图时使用本扩展：

1. 在线更新程序；
2. 检查新版本；
3. 从 GitHub 更新 DairyAssistant；
4. 从 `DrRichard1998/Daily-Assistant` 更新；
5. 绑定或修改程序更新源；
6. 排查更新失败、版本不一致或远程仓库配置问题。

## 3. 职责边界

本扩展负责：

1. 检查 Git、网络、远程仓库地址和当前分支；
2. 在更新前创建保护备份；
3. 使用 Git 从默认更新源获取程序更新；
4. 在 Git 不可用时，按用户确认使用 GitHub ZIP 包更新；
5. 更新后运行 `doctor`、语法检查和命令帮助检查；
6. 更新失败时按保护备份回滚。

本扩展不负责：

1. 上传或发布新版本到 GitHub；
2. 覆盖、清空或迁移 `data/assistant.sqlite`；
3. 物理删除用户业务记录；
4. 自动执行远程脚本；
5. 在用户未确认时切换远程仓库地址；
6. 在用户未确认时丢弃本地未提交改动。

## 4. 更新范围

允许从远程更新的程序文件包括：

```text
assistant.py
schema.sql
AGENTS.md
extensions/
```

如果远程仓库以后增加程序相关文件，可在用户确认后纳入更新范围。

更新时必须保护本地用户数据。以下路径不得被远程更新覆盖：

```text
data/assistant.sqlite
backup/
```

以下本地环境目录默认不作为程序更新内容：

```text
.git/
__pycache__/
.cc-connect/
.obsidian/
```

## 5. 更新前检查

进入更新流程后，先确认当前位置是项目根目录，且至少存在：

```text
assistant.py
schema.sql
AGENTS.md
extensions/catalog.md
```

然后运行：

```powershell
git --version
git status --short
git remote -v
git branch --show-current
```

处理规则：

1. 如果未安装 Git，询问用户是否安装 Git；用户确认后再进入安装流程。
2. 如果当前目录不是 Git 仓库，进入第 6 节“首次绑定更新源”。
3. 如果没有 `origin`，进入第 6 节“首次绑定更新源”。
4. 如果 `origin` 不是默认更新源，先向用户说明当前地址和默认地址，只能在用户确认后修改。
5. 如果存在未提交的本地程序改动，不能直接更新；先询问用户要备份、提交、暂存还是取消更新。
6. 如果只有用户数据、备份或缓存目录变化，不应阻止程序更新。

## 6. 首次绑定更新源

当当前目录不是 Git 仓库或没有远程仓库时，按本节处理。

### 6.1 最小确认问题

只问用户一个问题：

```text
是否把当前项目绑定到 GitHub 更新源 https://github.com/DrRichard1998/Daily-Assistant.git，并以后默认从 main 分支更新？
```

用户确认前，不运行 `git init`，不新增 remote，不拉取远程内容。

### 6.2 绑定命令

用户确认后，按实际状态执行：

```powershell
git init
git remote add origin https://github.com/DrRichard1998/Daily-Assistant.git
git branch -M main
```

如果已经存在 `origin` 但地址为空或错误，必须先显示当前地址，并在用户确认后执行：

```powershell
git remote set-url origin https://github.com/DrRichard1998/Daily-Assistant.git
```

### 6.3 首次绑定后的处理

绑定后先运行：

```powershell
git fetch origin main
git status --short
```

如果远程仓库为空或没有 `main` 分支，说明还不能从远程更新。此时停止更新流程，并提示用户需要先把当前程序版本发布到该仓库。

如果远程仓库已有内容，不能直接覆盖本地文件。必须先进入第 7 节创建保护备份，再对比差异，最后询问用户是否应用更新。

## 7. 更新前保护备份

任何会改动本地程序文件的更新前，都必须创建保护备份。

备份目录：

```text
backup/
```

备份文件名：

```text
pre-update-YYYYMMDD-HHMMSS.bak
```

保护备份至少包含：

```text
assistant.py
schema.sql
AGENTS.md
extensions/
data/assistant.sqlite
manifest.json
```

如果某个文件不存在，在 `manifest.json` 中记录缺失项，但不要因此跳过其他已存在文件的备份。

备份成功前，不允许覆盖任何本地程序文件。

## 8. Git 更新流程

当 Git 可用且远程仓库配置正确时，优先使用本流程。

### 8.1 检查远程差异

运行：

```powershell
git fetch origin main
git log --oneline HEAD..origin/main
git diff --name-status HEAD..origin/main
```

如果 `HEAD` 不存在，例如本地从未提交过，改用：

```powershell
git diff --name-status origin/main
```

### 8.2 用户确认

向用户说明：

1. 当前更新源；
2. 当前分支；
3. 将要更新的文件列表；
4. 保护备份文件路径；
5. 不会覆盖 `data/assistant.sqlite`。

用户确认前，不执行会覆盖本地文件的命令。

### 8.3 应用更新

用户确认后，如果本地仓库状态干净，可执行：

```powershell
git pull --ff-only origin main
```

如果 `git pull --ff-only` 失败，不要强制合并，不要 reset。改用安全覆盖流程：

1. 把远程 `origin/main` 导出到临时目录；
2. 只复制第 4 节允许更新的程序文件；
3. 不复制 `data/assistant.sqlite`、`backup/`、`.git/` 和本地环境目录；
4. 复制完成后进入第 10 节验证。

## 9. ZIP 更新流程

只有在 Git 不可用、用户确认使用 ZIP 包、且网络可访问 GitHub 时，才使用本流程。

下载地址：

```text
https://github.com/DrRichard1998/Daily-Assistant/archive/refs/heads/main.zip
```

基本流程：

1. 下载 ZIP 到临时目录；
2. 解压到临时目录；
3. 检查解压目录中存在 `assistant.py`、`schema.sql` 和 `extensions/catalog.md`；
4. 创建第 7 节保护备份；
5. 只复制第 4 节允许更新的程序文件；
6. 删除临时目录；
7. 进入第 10 节验证。

不得直接在项目根目录解压 ZIP。

## 10. 更新后验证

更新后必须运行：

```powershell
python -m py_compile .\assistant.py
python .\assistant.py doctor
python .\assistant.py --help
```

如果 `doctor` 返回 `needs_init` 或 `environment_error`，按 `AGENTS.md` 第 13 节处理。

如果更新修改了 `schema.sql`，但数据库已经存在，不要手工改 SQLite。先运行：

```powershell
python .\assistant.py init
```

然后再运行：

```powershell
python .\assistant.py doctor
```

## 11. 失败与回滚

如果更新后语法检查、`doctor` 或 `--help` 失败，先判断是否能用最小修复解决。

如果不能快速修复，必须询问用户是否从本次 `pre-update-*.bak` 回滚。

回滚时：

1. 不物理删除当前数据库；
2. 先保留失败后的当前文件，必要时另存为排查备份；
3. 从保护备份恢复程序文件和 `extensions/`；
4. 只有用户明确要求时，才恢复 `data/assistant.sqlite`；
5. 回滚后重新运行第 10 节验证。

## 12. 回复规则

检查更新时，回复应包含：

1. 当前更新源；
2. 当前分支；
3. 是否发现远程更新；
4. 是否需要用户确认。

更新成功后，回复应包含：

1. 已更新的文件或提交范围；
2. 保护备份路径；
3. 验证命令和结果；
4. 是否保留了本地数据库。

更新失败后，回复应包含：

1. 失败步骤；
2. 错误摘要；
3. 保护备份路径；
4. 是否已回滚或等待用户确认回滚。

## 13. 安全规则

1. 不执行从网络下载的脚本。
2. 不在没有保护备份时覆盖程序文件。
3. 不用 `git reset --hard`、`git clean` 或物理删除命令处理用户文件。
4. 不把 `data/assistant.sqlite` 当作远程程序文件更新。
5. 不在用户未确认时修改 Git remote。
6. 不在用户未确认时解决冲突或覆盖本地改动。
7. 网络失败时只报告具体失败原因，不伪造更新结果。
