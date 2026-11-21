param([string]$Url = 'http://127.0.0.1:18760', [string]$Python = 'python', [switch]$RunWntr)
$ErrorActionPreference = 'Stop'
$site = $Url.TrimEnd('/')
$health = Invoke-RestMethod "$site/healthz" -TimeoutSec 5
if ($health.status -ne 'ok' -or $health.solver -ne 'WNTR') { throw 'WNTR healthz failed.' }
$page = Invoke-WebRequest "$site/demo/" -UseBasicParsing -TimeoutSec 5
if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'index-') { throw 'Recorded demo failed.' }
Write-Output 'HTTP 200 /healthz and /demo/'
if ($RunWntr) {
  $output = Join-Path $PSScriptRoot '../.calisma/api-smoke'
  & $Python (Join-Path $PSScriptRoot 'smoke_api.py') $site $output
  exit $LASTEXITCODE
}
