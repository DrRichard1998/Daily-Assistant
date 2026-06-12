# backup

## 1. 目的

本扩展用于备份和恢复当前用户数据。

用户数据范围包括：

1. `data/assistant.sqlite`；
2. 整个 `extensions/` 文件夹。

备份产物必须是一个 `.bak` 文件，按备份日期和时间命名，保存到项目根目录下的 `backup/` 文件夹中。若 `backup/` 不存在，先创建该文件夹。

`.bak` 文件本质上是 ZIP 兼容归档，但最终扩展名必须是 `.bak`。

## 2. 触发条件

当用户表达以下意图时使用本扩展：

1. 备份当前数据；
2. 备份数据库和扩展；
3. 恢复备份；
4. 从某个 `.bak` 文件恢复用户数据；
5. 查看或说明备份、恢复流程。

## 3. 职责边界

本扩展负责：

1. 将当前数据库和扩展目录完整打包成一个 `.bak` 文件；
2. 从指定 `.bak` 文件恢复数据库；
3. 恢复全部扩展或指定扩展；
4. 恢复扩展时同步维护 `extensions/catalog.md`；
5. 在覆盖当前数据前创建恢复前保护备份。

本扩展不负责：

1. 手工编辑 SQLite 数据库内容；
2. 物理删除业务记录；
3. 把数据库迁移到项目目录外；
4. 在用户未确认恢复范围时覆盖当前文件；
5. 修改 `assistant.py`、`schema.sql` 或 `AGENTS.md`，除非用户明确要求维护这些文件。

## 4. 备份内容

每次备份都必须完整包含：

```text
data/assistant.sqlite
extensions/
manifest.json
```

其中：

1. `data/assistant.sqlite` 是当前数据库；
2. `extensions/` 是当前全部扩展文件，包括 `extensions/catalog.md`；
3. `manifest.json` 是备份清单，用于恢复前校验。

`manifest.json` 至少包含：

```json
{
  "app": "DairyAssistant",
  "created_at": "YYYY-MM-DDTHH:mm:ss+08:00",
  "backup_type": "user_data",
  "includes": [
    "data/assistant.sqlite",
    "extensions/"
  ]
}
```

## 5. 备份命名与位置

备份目录：

```text
backup/
```

普通备份文件名：

```text
backup-YYYYMMDD-HHMMSS.bak
```

恢复前保护备份文件名：

```text
pre-restore-YYYYMMDD-HHMMSS.bak
```

示例：

```text
backup/backup-20260612-153045.bak
backup/pre-restore-20260612-154200.bak
```

时间使用当前本地时间。

## 6. 备份执行顺序

执行备份时：

1. 确认当前位置是项目根目录，且存在 `assistant.py`、`schema.sql`、`data/assistant.sqlite` 和 `extensions/`。
2. 创建 `backup/` 文件夹。
3. 在 `backup/` 下创建临时工作目录，例如 `backup/.work-backup-YYYYMMDD-HHMMSS/`。
4. 复制 `data/assistant.sqlite` 到临时目录的 `data/assistant.sqlite`。
5. 复制整个 `extensions/` 到临时目录的 `extensions/`。
6. 写入 `manifest.json`。
7. 先压缩成 `.zip` 文件，再改名为 `.bak`。
8. 删除临时工作目录和中间 `.zip` 文件。
9. 确认 `.bak` 文件存在。
10. 回复用户备份文件路径和备份范围。

推荐 PowerShell 流程：

```powershell
New-Item -ItemType Directory -Path .\backup -Force
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$work = ".\backup\.work-backup-$stamp"
$zip = ".\backup\backup-$stamp.zip"
$bak = ".\backup\backup-$stamp.bak"
New-Item -ItemType Directory -Path $work -Force
New-Item -ItemType Directory -Path (Join-Path $work "data") -Force
Copy-Item .\data\assistant.sqlite (Join-Path $work "data\assistant.sqlite") -Force
Copy-Item .\extensions (Join-Path $work "extensions") -Recurse -Force
$manifest = @{
  app = "DairyAssistant"
  created_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
  backup_type = "user_data"
  includes = @("data/assistant.sqlite", "extensions/")
} | ConvertTo-Json -Depth 4
Set-Content -Encoding UTF8 -Path (Join-Path $work "manifest.json") -Value $manifest
Compress-Archive -Path (Join-Path $work "*") -DestinationPath $zip -Force
Move-Item -Path $zip -Destination $bak -Force
Remove-Item $work -Recurse -Force
```

回复示例：

```text
已备份：
- 数据库：data/assistant.sqlite
- 扩展目录：extensions/
- 清单：manifest.json
- 备份文件：backup/backup-20260612-153045.bak
```

## 7. 恢复前规则

恢复是覆盖性操作。执行恢复前必须确认两件事：

1. 使用哪个 `.bak` 文件；
2. 恢复哪些内容。

如果用户没有指定 `.bak` 文件，先列出 `backup/*.bak`，让用户选择一个。

如果用户没有明确恢复范围，只问一个最小澄清问题：

```text
要从这个备份中恢复哪些内容：数据库、全部扩展，还是只恢复指定扩展？
```

如果用户选择只恢复指定扩展，继续询问要恢复的扩展文件名或扩展名称。

## 8. 可选恢复范围

支持以下恢复范围：

1. 只恢复数据库；
2. 恢复数据库和全部扩展；
3. 只恢复全部扩展；
4. 只恢复指定扩展；
5. 恢复数据库和指定扩展。

## 9. 恢复前校验

恢复前必须先把 `.bak` 复制成临时 `.zip`，再解包到 `backup/.work-restore-YYYYMMDD-HHMMSS/`。

校验内容：

1. 备份中存在 `manifest.json`；
2. `manifest.json` 的 `app` 为 `DairyAssistant`；
3. 备份中存在 `data/assistant.sqlite`；
4. 备份中存在 `extensions/`；
5. 若恢复指定扩展，备份中存在对应的 `extensions/{name}.md`。

如果缺少 `manifest.json`，但备份中存在 `data/assistant.sqlite` 和 `extensions/`，可视为旧格式备份；继续前必须说明“该备份缺少清单文件”，并询问用户是否继续恢复。

## 10. 恢复前保护备份

任何恢复覆盖前，都必须先对当前数据生成一次完整保护备份。

保护备份规则与普通备份相同，文件名使用：

```text
backup/pre-restore-YYYYMMDD-HHMMSS.bak
```

保护备份成功后，才允许继续覆盖当前数据库或扩展文件。

## 11. 恢复执行顺序

1. 确认用户指定或选择的 `.bak` 文件存在。
2. 将 `.bak` 复制为临时 `.zip`。
3. 解包到 `backup/.work-restore-YYYYMMDD-HHMMSS/`。
4. 按第 9 节校验备份内容。
5. 确认恢复范围。
6. 创建恢复前保护备份。
7. 按用户确认的范围恢复数据库和扩展。
8. 如果恢复了扩展，按第 12 节同步 `extensions/catalog.md`。
9. 删除恢复临时目录和临时 `.zip`。
10. 运行可用的检查命令确认项目仍可用：

```powershell
python .\assistant.py doctor
```

11. 回复恢复范围、保护备份路径和验证结果。

## 12. catalog.md 同步规则

恢复扩展时必须同步处理 `extensions/catalog.md`。

### 12.1 全部恢复扩展

如果用户选择恢复全部扩展：

1. 用备份中的整个 `extensions/` 覆盖当前 `extensions/`；
2. 备份中的 `extensions/catalog.md` 随扩展目录一起恢复；
3. 不需要手工合并目录条目。

### 12.2 只恢复指定扩展

如果用户选择只恢复指定扩展：

1. 只复制对应的 `extensions/{name}.md`；
2. 不得用备份中的完整 `catalog.md` 覆盖当前 `catalog.md`；
3. 从备份的 `extensions/catalog.md` 中读取该扩展对应表格行；
4. 如果当前 `catalog.md` 已有同名扩展行，用备份中的行替换；
5. 如果当前 `catalog.md` 没有同名扩展行，追加备份中的行；
6. 如果备份 `catalog.md` 中没有该扩展行，停止并询问用户是否手动补充目录条目。

匹配扩展行时以第一列扩展名称为准，例如：

```text
| `backup` | `backup.md` | ... |
```

## 13. 回复规则

备份完成后只报告实际生成结果：

```text
已备份：
- 数据库：data/assistant.sqlite
- 扩展目录：extensions/
- 备份文件：backup/backup-YYYYMMDD-HHMMSS.bak
```

恢复完成后只报告实际恢复结果：

```text
已恢复：
- 数据库：已恢复 / 未恢复
- 扩展：全部恢复 / 已恢复指定扩展 / 未恢复
- 保护备份：backup/pre-restore-YYYYMMDD-HHMMSS.bak
- 验证：doctor 通过 / doctor 未通过
```

## 14. 限制

1. 不在用户未确认恢复范围时执行覆盖。
2. 不物理删除当前数据库或扩展目录。
3. 不把备份文件放到项目根目录外。
4. 不直接写 SQL。
5. 不手工修改 `data/assistant.sqlite`。
6. 恢复扩展时必须同步考虑 `extensions/catalog.md`。
7. 备份和恢复过程中的临时目录必须位于 `backup/` 下，并在成功后清理。
