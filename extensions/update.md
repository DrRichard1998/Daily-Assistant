# update

## 1. 目的

本扩展用于从固定 GitHub 仓库下载新版 DailyAssistant，并用“重建式升级”替代原地数据库迁移。

默认更新源：

```text
https://github.com/DrRichard1998/Daily-Assistant.git
```

默认分支：

```text
main
```

本扩展的目标是完成以下闭环：

1. 确认当前目录和更新源正确；
2. 先完整保护当前数据和程序文件；
3. 从旧数据库导出所有事项条目到 `items-backup.txt`；
4. 下载一个全新的项目副本到临时目录；
5. 在新项目副本中初始化新数据库；
6. 把 `items-backup.txt` 导入新数据库；
7. 验证新项目和新数据库可用；
8. 验证通过后，再替换当前项目文件和数据库；
9. 失败时保留旧项目和旧数据库，或从保护备份回滚。

本流程不依赖旧数据库结构迁移。新版架构变化时，只要新版程序仍支持当前 `items-backup.txt` 格式，就通过“导出条目、重建新库、导入条目”完成升级。

## 2. 触发条件

当用户表达以下意图时使用本扩展：

1. 在线更新程序；
2. 检查新版本；
3. 从 GitHub 更新 DailyAssistant；
4. 从 `DrRichard1998/Daily-Assistant` 更新；
5. 绑定或修改程序更新源；
6. 排查更新失败、版本不一致或远程仓库配置问题。

## 3. 职责边界

本扩展负责：

1. 检查 Git、网络、远程仓库地址和当前分支；
2. 在升级前创建保护备份；
3. 从当前数据库导出 `items-backup.txt`；
4. 使用 Git 或 GitHub ZIP 下载新项目到临时目录；
5. 在临时新项目中初始化数据库并导入事项条目；
6. 验证新项目、新数据库和导入结果；
7. 验证通过后替换当前项目文件和数据库；
8. 升级失败时保留旧项目，或按保护备份回滚。

本扩展不负责：

1. 上传或发布新版本到 GitHub；
2. 手工迁移 SQLite 表结构；
3. 手工编辑 `data/assistant.sqlite`；
4. 物理删除用户业务记录；
5. 自动执行远程脚本；
6. 在用户未确认时切换远程仓库地址；
7. 在用户未确认时丢弃本地未提交改动。

## 4. 升级范围

升级完成后，当前项目应来自新项目副本的程序文件：

```text
assistant.py
schema.sql
AGENTS.md
extensions/
```

如果远程仓库以后增加程序相关文件，可在用户确认后纳入升级范围。

升级完成后，`data/assistant.sqlite` 不再沿用旧文件，而是使用新项目初始化后、由 `items-backup.txt` 导入生成的新数据库。

以下路径不得从远程项目直接覆盖：

```text
backup/
.git/
__pycache__/
.cc-connect/
.obsidian/
```

## 5. 升级前检查

进入升级流程后，先确认当前位置是项目根目录，且至少存在：

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

1. 如果未安装 Git，询问用户是否改用 ZIP 更新；用户确认后才能进入 ZIP 流程。
2. 如果当前目录不是 Git 仓库，进入第 6 节“首次绑定更新源”或按用户确认使用 ZIP 流程。
3. 如果没有 `origin`，进入第 6 节“首次绑定更新源”。
4. 如果 `origin` 不是默认更新源，先向用户说明当前地址和默认地址，只能在用户确认后修改。
5. 如果存在未提交的本地程序改动，不能直接升级；先询问用户要备份、提交、暂存还是取消升级。
6. 如果只有用户数据、备份或缓存目录变化，不应阻止升级。

## 6. 首次绑定更新源

当当前目录不是 Git 仓库或没有远程仓库时，按本节处理。

### 6.1 最小确认问题

只问用户一个问题：

```text
是否把当前项目绑定到 GitHub 更新源 https://github.com/DrRichard1998/Daily-Assistant.git，并以后默认从 main 分支升级？
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

如果远程仓库为空或没有 `main` 分支，说明还不能从远程升级。此时停止升级流程，并提示用户需要先把当前程序版本发布到该仓库。

如果远程仓库已有内容，不能直接覆盖本地文件。必须先进入第 7 节创建保护备份和事项导出，再按后续流程在临时目录中构建新项目。

## 7. 升级前保护备份与事项导出

任何会改动当前项目文件或数据库的升级前，都必须先完成两件事：

1. 创建完整保护备份；
2. 从当前数据库导出所有事项条目到 `items-backup.txt`。

备份目录：

```text
backup/
```

保护备份文件名：

```text
pre-update-YYYYMMDD-HHMMSS.bak
```

事项导出文件名：

```text
backup/items-backup-pre-update-YYYYMMDD-HHMMSS.txt
```

保护备份至少包含：

```text
assistant.py
schema.sql
AGENTS.md
extensions/
data/assistant.sqlite
items-backup.txt
manifest.json
```

`items-backup.txt` 必须由当前版本程序导出，不得手写：

```powershell
python .\assistant.py export-items-backup --output .\backup\items-backup-pre-update-YYYYMMDD-HHMMSS.txt
```

导出后必须确认命令返回 `status = "ok"`，并记录返回的 `checksum` 和 `summary`。

如果事项导出失败，必须停止升级；不能只依赖 SQLite 文件继续升级。

保护备份和事项导出成功前，不允许覆盖任何当前项目文件或数据库。

## 8. 下载新项目

新项目必须下载到临时目录，不得直接下载或解压到当前项目根目录。

推荐临时目录：

```text
backup/.work-update-YYYYMMDD-HHMMSS/new-project/
```

### 8.1 Git 下载流程

当 Git 可用且远程仓库配置正确时，优先使用本流程。

先检查远程差异：

```powershell
git fetch origin main
git log --oneline HEAD..origin/main
git diff --name-status HEAD..origin/main
```

如果 `HEAD` 不存在，例如本地从未提交过，改用：

```powershell
git diff --name-status origin/main
```

向用户说明：

1. 当前更新源；
2. 当前分支；
3. 将要升级到的远程提交；
4. 将使用的保护备份路径；
5. 将使用“导出事项、重建新库、导入事项”的升级方式。

用户确认前，不执行会替换当前项目的命令。

用户确认后，下载新项目到临时目录：

```powershell
git clone --branch main --single-branch https://github.com/DrRichard1998/Daily-Assistant.git .\backup\.work-update-YYYYMMDD-HHMMSS\new-project
```

### 8.2 ZIP 下载流程

只有在 Git 不可用、用户确认使用 ZIP 包、且网络可访问 GitHub 时，才使用本流程。

下载地址：

```text
https://github.com/DrRichard1998/Daily-Assistant/archive/refs/heads/main.zip
```

基本流程：

1. 下载 ZIP 到 `backup/.work-update-YYYYMMDD-HHMMSS/`；
2. 解压到临时目录；
3. 把解压后的项目目录视为 `new-project/`；
4. 不得直接在当前项目根目录解压 ZIP。

### 8.3 新项目完整性检查

下载后必须确认新项目目录中至少存在：

```text
assistant.py
schema.sql
extensions/catalog.md
```

如果缺少任一文件，停止升级，保留当前项目不变。

## 9. 在新项目中初始化并导入条目

本节只操作临时新项目，不操作当前项目。

先把第 7 节导出的事项文本复制到新项目内部，例如：

```text
backup/.work-update-YYYYMMDD-HHMMSS/new-project/backup/items-backup-pre-update-YYYYMMDD-HHMMSS.txt
```

然后在新项目目录中运行：

```powershell
python .\assistant.py init
python .\assistant.py restore-items-backup --file .\backup\items-backup-pre-update-YYYYMMDD-HHMMSS.txt
python .\assistant.py verify-items-backup --file .\backup\items-backup-pre-update-YYYYMMDD-HHMMSS.txt
python .\assistant.py doctor
python .\assistant.py query --period today
```

通过条件：

1. `init` 返回成功；
2. `restore-items-backup` 返回 `status = "restored"`；
3. `verify-items-backup` 返回 `status = "ok"`；
4. `doctor` 返回 `status = "ok"`；
5. `query --period today` 可以正常返回结果。

如果任何一步失败，停止升级；当前项目文件和当前数据库不得被替换。

## 10. 替换当前项目

只有第 9 节全部通过后，才允许替换当前项目。

替换内容：

```text
assistant.py
schema.sql
AGENTS.md
extensions/
data/assistant.sqlite
```

其中：

1. 程序文件来自临时新项目；
2. `data/assistant.sqlite` 来自临时新项目中已经完成导入和校验的新数据库；
3. 当前项目的 `backup/`、`.git/` 和本地环境目录必须保留；
4. 不从远程项目复制 `backup/`。

替换前再次确认保护备份存在。若保护备份不存在，停止升级。

## 11. 升级后验证

替换当前项目后必须在当前项目根目录运行：

```powershell
python -m py_compile .\assistant.py
python .\assistant.py doctor
python .\assistant.py --help
python .\assistant.py verify-items-backup --file .\backup\items-backup-pre-update-YYYYMMDD-HHMMSS.txt
python .\assistant.py query --period today
```

通过条件：

1. 语法检查通过；
2. `doctor` 返回 `status = "ok"`；
3. `--help` 正常输出；
4. `verify-items-backup` 返回 `status = "ok"`；
5. `query --period today` 可以正常返回结果。

升级成功后，可以删除 `backup/.work-update-YYYYMMDD-HHMMSS/` 临时目录；不得删除 `pre-update-*.bak` 和 `items-backup-pre-update-*.txt`。

## 12. 失败与回滚

如果失败发生在第 10 节替换当前项目前：

1. 当前项目和当前数据库不得被替换；
2. 报告失败步骤、错误摘要、保护备份路径和事项导出路径；
3. 保留临时目录供排查，除非用户要求清理。

如果失败发生在第 10 节替换当前项目后：

1. 先判断是否能用最小修复解决；
2. 如果不能快速修复，必须询问用户是否从本次 `pre-update-*.bak` 回滚；
3. 回滚时从保护备份恢复程序文件、`extensions/` 和旧 `data/assistant.sqlite`；
4. 回滚后重新运行第 11 节验证。

不得使用 `git reset --hard`、`git clean` 或物理删除命令处理用户文件。

## 13. 回复规则

检查升级时，回复应包含：

1. 当前更新源；
2. 当前分支；
3. 是否发现远程更新；
4. 是否需要用户确认；
5. 本次将使用“导出事项、重建新库、导入事项”的升级方式。

升级成功后，回复应包含：

1. 已升级到的远程提交或版本范围；
2. 保护备份路径；
3. 事项导出路径；
4. 导入校验结果；
5. 升级后验证命令和结果。

升级失败后，回复应包含：

1. 失败步骤；
2. 错误摘要；
3. 保护备份路径；
4. 事项导出路径；
5. 当前项目是否已保持不变、已回滚或等待用户确认回滚。

## 14. 安全规则

1. 不执行从网络下载的脚本。
2. 不在没有保护备份和事项导出时替换当前项目。
3. 不手工迁移 SQLite 表结构。
4. 不手工修改 `data/assistant.sqlite`。
5. 不在当前项目根目录直接解压 ZIP。
6. 不从远程项目复制 `backup/`。
7. 不在用户未确认时修改 Git remote。
8. 不在用户未确认时解决冲突或覆盖本地改动。
9. 网络失败时只报告具体失败原因，不伪造升级结果。
