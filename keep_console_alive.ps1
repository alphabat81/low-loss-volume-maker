$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:ONDO_LIVE_ENABLED = "1"
$env:LLV_WEB_PORT = "8782"

while ($true) {
  try {
    Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8782/console" -TimeoutSec 5 | Out-Null
  } catch {
    Start-Process -FilePath "python" -ArgumentList "web_server.py" -WorkingDirectory $root -WindowStyle Hidden
    Start-Sleep -Seconds 3
  }
  Start-Sleep -Seconds 15
}
