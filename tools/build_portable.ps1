param(
  [string]$PythonVersion = "3.10.11",
  [string]$Architecture = "amd64",
  [switch]$IncludeDatabase,
  [switch]$SkipDownload,
  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

function Resolve-ExistingPath {
  param([Parameter(Mandatory = $true)][string]$Path)
  return (Resolve-Path -LiteralPath $Path).ProviderPath
}

function Assert-UnderPath {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Root
  )

  $fullPath = [System.IO.Path]::GetFullPath($Path)
  $fullRoot = [System.IO.Path]::GetFullPath($Root)

  if (-not $fullRoot.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
    $fullRoot = $fullRoot + [System.IO.Path]::DirectorySeparatorChar
  }

  if (-not $fullPath.StartsWith($fullRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to touch path outside expected root. Path: $fullPath Root: $fullRoot"
  }
}

function Copy-RequiredFile {
  param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Destination
  )

  if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
    throw "Missing required file: $Source"
  }
  Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Copy-RequiredDirectory {
  param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Destination
  )

  if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
    throw "Missing required directory: $Source"
  }
  Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

function Get-PythonMinorTag {
  param([Parameter(Mandatory = $true)][string]$Version)
  $parts = $Version.Split(".")
  if ($parts.Count -lt 2) {
    throw "PythonVersion must look like 3.10.11, got: $Version"
  }
  return "python$($parts[0])$($parts[1])"
}

function Remove-PortableDatabaseFiles {
  param([Parameter(Mandatory = $true)][string]$DataRoot)

  Assert-UnderPath -Path $DataRoot -Root $packageRoot
  if (Test-Path -LiteralPath $DataRoot -PathType Container) {
    Get-ChildItem -LiteralPath $DataRoot -Force -Filter "assistant.sqlite*" |
      Remove-Item -Force
  }
}

$projectRoot = Resolve-ExistingPath (Join-Path $PSScriptRoot "..")
$distRoot = Join-Path $projectRoot "dist"
$downloadRoot = Join-Path $projectRoot "download"
$packageRoot = Join-Path $distRoot "DailyAssistantPortable"
$runtimeRoot = Join-Path $packageRoot "runtime\python"
$zipName = "python-$PythonVersion-embed-$Architecture.zip"
$zipPath = Join-Path $downloadRoot $zipName
$pythonUrl = "https://www.python.org/ftp/python/$PythonVersion/$zipName"

foreach ($required in @("assistant.py", "schema.sql", "AGENTS.md", "README.md", "extensions")) {
  if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $required))) {
    throw "Project root is missing required entry: $required"
  }
}

New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null

Assert-UnderPath -Path $packageRoot -Root $distRoot
if (Test-Path -LiteralPath $packageRoot) {
  Get-ChildItem -LiteralPath $packageRoot -Force | Remove-Item -Recurse -Force
}

New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot "data") -Force | Out-Null

if (-not $SkipDownload) {
  if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
    Write-Host "Downloading $pythonUrl"
    Invoke-WebRequest -Uri $pythonUrl -OutFile $zipPath
  } else {
    Write-Host "Using cached $zipPath"
  }
}

if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
  throw "Missing embeddable Python zip: $zipPath"
}

Expand-Archive -LiteralPath $zipPath -DestinationPath $runtimeRoot -Force

$pythonTag = Get-PythonMinorTag -Version $PythonVersion
$pthPath = Join-Path $runtimeRoot "$pythonTag._pth"
if (-not (Test-Path -LiteralPath $pthPath -PathType Leaf)) {
  throw "Expected embedded Python path file not found: $pthPath"
}

$builderPipPath = & python -c "import pathlib, pip; print(pathlib.Path(pip.__file__).resolve().parent)"
if ($LASTEXITCODE -ne 0 -or -not $builderPipPath) {
  throw "The build environment must provide pip so the portable doctor check can pass."
}

$portablePipPath = Join-Path $runtimeRoot "pip"
Copy-Item -LiteralPath $builderPipPath -Destination $portablePipPath -Recurse -Force

Copy-RequiredFile -Source (Join-Path $projectRoot "assistant.py") -Destination $packageRoot
Copy-RequiredFile -Source (Join-Path $projectRoot "schema.sql") -Destination $packageRoot
Copy-RequiredFile -Source (Join-Path $projectRoot "AGENTS.md") -Destination $packageRoot
Copy-RequiredFile -Source (Join-Path $projectRoot "README.md") -Destination $packageRoot
Copy-RequiredFile -Source (Join-Path $projectRoot "run.cmd") -Destination $packageRoot
Copy-RequiredDirectory -Source (Join-Path $projectRoot "extensions") -Destination $packageRoot

if ($IncludeDatabase) {
  $dbPath = Join-Path $projectRoot "data\assistant.sqlite"
  if (Test-Path -LiteralPath $dbPath -PathType Leaf) {
    Copy-Item -LiteralPath $dbPath -Destination (Join-Path $packageRoot "data") -Force
  } else {
    Write-Host "No database found to include: $dbPath"
  }
}

if (-not $SkipVerify) {
  $runCmd = Join-Path $packageRoot "run.cmd"
  & $runCmd doctor
  if ($LASTEXITCODE -ne 0) {
    throw "Portable doctor failed."
  }

  & $runCmd --help | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Portable help failed."
  }

  & $runCmd init
  if ($LASTEXITCODE -ne 0) {
    throw "Portable init failed."
  }
}

if (-not $IncludeDatabase) {
  Remove-PortableDatabaseFiles -DataRoot (Join-Path $packageRoot "data")
  Write-Host "Portable database files were not included."
}

Write-Host "Portable package created:"
Write-Host $packageRoot
