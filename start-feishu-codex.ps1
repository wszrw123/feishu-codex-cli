[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $Root ".runtime"
New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

$env:PATH = "C:\Users\14617\.local\bin;C:\Program Files\Git\usr\bin;C:\Windows\System32;C:\Windows;$env:PATH"

$pythonCandidates = @(
  (Join-Path $Root ".venv\Scripts\python.exe"),
  (Join-Path $Root "python\python.exe"),
  "D:\person\xcode-tg\.venv\Scripts\python.exe",
  "C:\Users\14617\AppData\Local\Programs\Python\Python313\python.exe",
  "C:\Python313\python.exe"
)

$pythonBin = $null
foreach ($candidate in $pythonCandidates) {
  if ($candidate -and (Test-Path $candidate)) {
    if ($candidate -like '*.venv\Scripts\python.exe') {
      $venvRoot = Split-Path -Parent (Split-Path -Parent $candidate)
      if (-not (Test-Path (Join-Path $venvRoot 'pyvenv.cfg'))) {
        continue
      }
    }
    $pythonBin = $candidate
    break
  }
}

if (-not $pythonBin) {
  throw "python runtime not found for feishu-codex-cli"
}

& $pythonBin (Join-Path $Root "service.py")
