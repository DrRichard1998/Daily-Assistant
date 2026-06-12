# backup

## 1. 目的

本扩展用于备份和恢复当前用户数据。

用户数据范围只包括：

1. `data/assistant.sqlite`；
2. 由数据库导出的事项文本副本 `items-backup.txt`。

备份时不得备份 `extensions/`。扩展文件可能随项目更新，且通常不是用户自己创建的数据，不应混入用户数据备份。

备份产物必须是一个 `.bak` 文件，按备份日期和时间命名，保存到项目根目录下的 `backup/` 文件夹中。若 `backup/` 不存在，先创建该文件夹。

`.bak` 文件本质上是 ZIP 兼容归档，但最终扩展名必须是 `.bak`。

## 2. 触发条件

当用户表达以下意图时使用本扩展：

1. 备份当前数据；
2. 备份数据库和事项文本；
3. 恢复备份；
4. 从某个 `.bak` 文件恢复用户数据；
5. 查看或说明备份、恢复流程。

## 3. 职责边界

本扩展负责：

1. 将当前数据库和 `items-backup.txt` 打包成一个 `.bak` 文件；
2. 从指定 `.bak` 文件优先恢复数据库；
3. 数据库恢复成功后，用 `items-backup.txt` 与数据库相互校验；
4. 数据库恢复不成功时，尝试从 `items-backup.txt` 重新写入数据库；
5. 在覆盖当前数据前创建恢复前保护备份。

本扩展不负责：

1. 手工编辑 SQLite 数据库内容；
2. 物理删除业务记录；
3. 把数据库迁移到项目目录外；
4. 备份或恢复 `extensions/`；
5. 在用户未确认恢复范围时覆盖当前文件。

## 4. 备份内容

每次备份都必须完整包含：

```text
data/assistant.sqlite
items-backup.txt
manifest.json
```

其中：

1. `data/assistant.sqlite` 是当前数据库；
2. `items-backup.txt` 是由 `assistant.py` 从数据库导出的所有事项文本副本；
3. `manifest.json` 是备份清单，用于恢复前校验。

`items-backup.txt` 必须由以下命令生成，不得手写：

```powershell
python .\assistant.py export-items-backup --output .\backup\.work-backup-YYYYMMDD-HHMMSS\items-backup.txt
```

`manifest.json` 至少包含：

```json
{
  "app": "DairyAssistant",
  "app_version": "1.0.5",
  "items_backup_version": 1,
  "created_at": "YYYY-MM-DDTHH:mm:ss+08:00",
  "backup_type": "user_data",
  "includes": [
    "data/assistant.sqlite",
    "items-backup.txt",
    "manifest.json"
  ],
  "excludes": [
    "extensions/"
  ]
}
```

其中：

1. `app_version` 必须取自 `python .\assistant.py --version` 返回的 DairyAssistant 版本号；
2. `items_backup_version` 必须取自刚生成的 `items-backup.txt` 内嵌 JSON 元数据；
3. 如果任一版本号无法读取，应停止备份并报告错误。

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

1. 确认当前位置是项目根目录，且存在 `assistant.py`、`schema.sql` 和 `data/assistant.sqlite`。
2. 创建 `backup/` 文件夹。
3. 在 `backup/` 下创建临时工作目录，例如 `backup/.work-backup-YYYYMMDD-HHMMSS/`。
4. 复制 `data/assistant.sqlite` 到临时目录的 `data/assistant.sqlite`。
5. 运行 `python .\assistant.py export-items-backup --output 临时目录\items-backup.txt`。
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
$itemsBackup = Join-Path $work "items-backup.txt"
python .\assistant.py export-items-backup --output $itemsBackup
$appVersion = (python .\assistant.py --version) -replace "^DairyAssistant\s+", ""
if (-not $appVersion) {
  throw "无法从 assistant.py 读取应用版本号"
}
$itemsText = Get-Content -Raw -Encoding UTF8 -Path $itemsBackup
$begin = "BEGIN_DAIRY_ASSISTANT_ITEMS_BACKUP_JSON"
$end = "END_DAIRY_ASSISTANT_ITEMS_BACKUP_JSON"
$start = $itemsText.IndexOf($begin)
$finish = $itemsText.IndexOf($end)
if ($start -lt 0 -or $finish -lt 0 -or $finish -le $start) {
  throw "无法从 items-backup.txt 读取版本信息"
}
$encodedPayload = $itemsText.Substring($start + $begin.Length, $finish - ($start + $begin.Length)).Trim()
$itemsPayloadJson = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedPayload))
$itemsPayload = $itemsPayloadJson | ConvertFrom-Json
if (-not $itemsPayload.metadata.version) {
  throw "无法从 items-backup.txt 读取事项文本备份版本号"
}
$manifest = @{
  app = "DairyAssistant"
  app_version = $appVersion
  items_backup_version = $itemsPayload.metadata.version
  created_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
  backup_type = "user_data"
  includes = @("data/assistant.sqlite", "items-backup.txt", "manifest.json")
  excludes = @("extensions/")
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
- 事项文本：items-backup.txt
- 清单：manifest.json
- 备份文件：backup/backup-20260612-153045.bak
```

## 7. 恢复前规则

恢复是覆盖性操作。执行恢复前必须确认使用哪个 `.bak` 文件。

如果用户没有指定 `.bak` 文件，先列出 `backup/*.bak`，让用户选择一个。

确认 `.bak` 文件后，只问一个最小澄清问题：

```text
确认要从这个备份恢复用户数据吗？恢复会先创建保护备份，再覆盖当前数据库。
```

## 8. 恢复前校验

恢复前必须先把 `.bak` 复制成临时 `.zip`，再解包到 `backup/.work-restore-YYYYMMDD-HHMMSS/`。

校验内容：

1. 备份中存在 `manifest.json`；
2. `manifest.json` 的 `app` 为 `DairyAssistant`；
3. 备份中存在 `data/assistant.sqlite`；
4. 备份中存在 `items-backup.txt`。

如果缺少 `manifest.json`，但备份中存在 `data/assistant.sqlite`，可视为旧格式备份；继续前必须说明“该备份缺少清单文件”，并询问用户是否继续恢复。

如果备份缺少 `items-backup.txt`，只能尝试数据库恢复，不能执行文本校验或文本重建；继续前必须说明该限制。

## 9. 恢复前保护备份

任何恢复覆盖前，都必须先对当前数据生成一次完整保护备份。

保护备份规则与普通备份相同，文件名使用：

```text
backup/pre-restore-YYYYMMDD-HHMMSS.bak
```

保护备份成功后，才允许继续覆盖当前数据库。

## 10. 恢复执行顺序

1. 确认用户指定或选择的 `.bak` 文件存在。
2. 将 `.bak` 复制为临时 `.zip`。
3. 解包到 `backup/.work-restore-YYYYMMDD-HHMMSS/`。
4. 按第 8 节校验备份内容。
5. 创建恢复前保护备份。
6. 优先复制备份中的 `data/assistant.sqlite` 覆盖当前数据库。
7. 运行 `python .\assistant.py doctor` 确认项目基础环境可用。
8. 如果数据库恢复成功且存在 `items-backup.txt`，运行：

```powershell
python .\assistant.py verify-items-backup --file .\backup\.work-restore-YYYYMMDD-HHMMSS\items-backup.txt
```

9. 如果校验通过，恢复完成。
10. 如果数据库复制、打开或校验失败，且存在 `items-backup.txt`，先确保当前数据库已初始化，再运行：

```powershell
python .\assistant.py restore-items-backup --file .\backup\.work-restore-YYYYMMDD-HHMMSS\items-backup.txt
```

11. 文本重建完成后，再运行 `python .\assistant.py verify-items-backup --file ...\items-backup.txt` 校验。
12. 删除恢复临时目录和临时 `.zip`。
13. 回复恢复方式、保护备份路径和验证结果。

## 11. 校验规则

`items-backup.txt` 与数据库校验必须使用：

```powershell
python .\assistant.py verify-items-backup --file 路径\items-backup.txt
```

如果命令返回 `status = "ok"`，表示数据库与文本副本一致。

如果命令返回 `status = "mismatch"`，必须报告差异摘要，并说明数据库已经恢复但与文本副本不一致；不要声称完全恢复成功。

如果数据库恢复失败但文本重建成功，回复中必须说明“通过事项文本重建数据库”。

## 12. 回复规则

备份完成后只报告实际生成结果：

```text
已备份：
- 数据库：data/assistant.sqlite
- 事项文本：items-backup.txt
- 备份文件：backup/backup-YYYYMMDD-HHMMSS.bak
```

恢复完成后只报告实际恢复结果：

```text
已恢复：
- 数据库：已直接恢复 / 已通过事项文本重建 / 未恢复
- 事项文本校验：通过 / 不一致 / 未执行
- 保护备份：backup/pre-restore-YYYYMMDD-HHMMSS.bak
- 验证：doctor 通过 / doctor 未通过
```

## 13. 限制

1. 不在用户未确认恢复时执行覆盖。
2. 不物理删除当前数据库文件；覆盖前必须先创建保护备份。
3. 不把备份文件放到项目根目录外。
4. 不直接写 SQL。
5. 不手工修改 `data/assistant.sqlite`。
6. 不备份、不恢复 `extensions/`。
7. 备份和恢复过程中的临时目录必须位于 `backup/` 下，并在成功后清理。
