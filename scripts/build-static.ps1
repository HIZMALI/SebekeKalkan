param([string]$Python = 'python', [string]$Offline)
$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '../frontend')
try {
  npm run lint
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  npm run build
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  $argsForScript = @((Join-Path $PSScriptRoot 'stage_static.py'))
  if ($Offline) { $argsForScript += @('--offline',$Offline) }
  & $Python @argsForScript
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
