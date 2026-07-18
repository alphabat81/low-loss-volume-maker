$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:ONDO_LIVE_ENABLED = "1"
$env:LLV_WEB_PORT = "8782"
$consoleUrl = "http://127.0.0.1:8782/console"
$startUrl = "http://127.0.0.1:8782/api/start"
$botStartAttempted = $false

while ($true) {
  $consoleReady = $false

  try {
    Invoke-WebRequest -UseBasicParsing $consoleUrl -TimeoutSec 5 | Out-Null
    $consoleReady = $true
  } catch {
    Start-Process -FilePath "python" -ArgumentList "web_server.py" -WorkingDirectory $root -WindowStyle Hidden
    Start-Sleep -Seconds 3
  }

  if ($consoleReady -and -not $botStartAttempted) {
    try {
      Invoke-WebRequest -UseBasicParsing $startUrl -Method POST -TimeoutSec 10 | Out-Null
      $botStartAttempted = $true
    } catch {
      Start-Sleep -Seconds 5
    }
  }

  Start-Sleep -Seconds 15
}
