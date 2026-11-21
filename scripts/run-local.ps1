param(
  [string]$Python,
  [string]$Wheelhouse,
  [ValidateRange(1024,65535)][int]$Port = 18760,
  [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Management,Microsoft.PowerShell.Utility
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$work = Join-Path $repo '.calisma'
$app = Join-Path $work 'runtime/01_GELISTIRME_KAYNAK'
$venv = Join-Path $app '.venv-hydraulic/Scripts/python.exe'
$lock = Join-Path $repo 'requirements-lock.txt'
$mark = Join-Path $app '.venv-hydraulic/.requirements-sha256'
$sha = [Security.Cryptography.SHA256]::Create()
try { $digest = [BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($lock))).Replace('-','') }
finally { $sha.Dispose() }
if (!(Test-Path -LiteralPath (Join-Path $repo 'docs/index.html'))) {
  throw 'Kayıtlı gösterim dosyaları eksik. Yayın kaynak kopyasını yeniden açın.'
}
if (!(Test-Path -LiteralPath $venv)) {
  if (!$Python) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) { $Python = & $launcher.Source -3.12 -c 'import sys; print(sys.executable)' 2>$null }
    if (!$Python) {
      $command = Get-Command python -ErrorAction SilentlyContinue
      if ($command) { $Python = $command.Source }
    }
  }
  if (!$Python) { throw 'Python 3.12 x64 bulunamadı. Mevcut yorumlayıcının yolunu -Python ile belirtin.' }
  & $Python -c 'import sys; sys.exit(0 if sys.version_info[:2]==(3,12) and sys.maxsize>2**32 else 1)'
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 gereklidir.' }
  & $Python (Join-Path $PSScriptRoot 'stage_runtime.py') (Join-Path $work 'runtime')
  if ($LASTEXITCODE -ne 0) { throw 'Çalışma kopyası hazırlanamadı.' }
  & $Python -m venv (Join-Path $app '.venv-hydraulic')
  if ($LASTEXITCODE -ne 0) { throw 'Yalıtılmış Python ortamı hazırlanamadı.' }
}
& $venv (Join-Path $PSScriptRoot 'stage_runtime.py') (Join-Path $work 'runtime')
if ($LASTEXITCODE -ne 0) { throw 'Çalışma kopyası güncellenemedi.' }
if (!(Test-Path -LiteralPath $mark) -or (Get-Content -LiteralPath $mark -Raw).Trim() -ne $digest) {
  $pipArgs = @('-m','pip','--disable-pip-version-check','install','-r',$lock)
  if ($Wheelhouse) { $pipArgs += @('--no-index','--find-links',(Resolve-Path -LiteralPath $Wheelhouse).Path) }
  & $venv @pipArgs
  if ($LASTEXITCODE -ne 0) { throw 'Bağımlılıklar kurulamadı. Kayıtlı gösterim ve PDF yedeği kullanılabilir.' }
  & $venv -m pip check
  if ($LASTEXITCODE -ne 0) { throw 'Python bağımlılık doğrulaması geçmedi.' }
  Set-Content -LiteralPath $mark -Value $digest -Encoding ASCII
}
function Select-LocalPort([int]$Initial) {
  foreach ($candidate in $Initial..([Math]::Min(65535,$Initial+49))) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $candidate)
    try { $listener.Start(); return $candidate }
    catch [Net.Sockets.SocketException] {}
    finally { $listener.Stop() }
  }
  throw 'Bos yerel port bulunamadi.'
}
$selected = Select-LocalPort $Port
$base = "http://127.0.0.1:$selected"
$env:PYTHONPATH = Join-Path $app 'backend'
$env:PYTHONDONTWRITEBYTECODE = '1'
$settings = @{
  FilePath = $venv
  ArgumentList = @('-m','uvicorn','sebekekalkan_core.release_server:app','--host','127.0.0.1','--port',$selected,'--no-proxy-headers')
  WindowStyle = 'Hidden'
  WorkingDirectory = $app
  PassThru = $true
  RedirectStandardOutput = Join-Path $work 'local-out.log'
  RedirectStandardError = Join-Path $work 'local-error.log'
}
$service = Start-Process @settings
try {
  $healthy = $false
  for ($attempt = 0; $attempt -lt 100; $attempt++) {
    if ($service.HasExited) { throw "Sunucu kapandi. Gunluk $(Join-Path $work 'local-error.log')" }
    try {
      $health = Invoke-RestMethod "$base/healthz" -TimeoutSec 1
      if ($health.status -eq 'ok' -and $health.live -eq 'local') { $healthy = $true; break }
    } catch { Start-Sleep -Milliseconds 200 }
  }
  if (!$healthy) { throw 'ŞebekeKalkan sağlık kontrolünü geçmedi.' }
  Write-Output "READY $base/demo/"
  if (!$NoBrowser) { Start-Process "$base/demo/" }
  $service.WaitForExit()
} finally {
  if (!$service.HasExited) { Stop-Process -Id $service.Id }
}
