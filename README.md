# Low Loss Volume Maker

Python-based Ondo Perps automation console for XAU-USD.P.

## Safety

Do not commit real API keys. The real `.env`, runtime `logs/`, and persisted `state/` are ignored by git.

## Current Runtime

- Web console: `http://127.0.0.1:8782/console`
- Mode: `live`
- Market: `XAU-USD.P`
- Leverage: `10x`
- Order size: `90%` of equity per order
- Daily target stop: disabled
- Loop timing: randomized

## Setup

Copy `.env.example` to `.env`, then fill in:

```powershell
ONDO_KEY_ID=...
ONDO_API_SECRET=...
ONDO_LIVE_ENABLED=1
```

## Run Console

```powershell
powershell -ExecutionPolicy Bypass -File start_live_console.ps1
```

To keep the local console alive during the current Windows session and start the live bot once after the console is reachable:

```powershell
powershell -ExecutionPolicy Bypass -File keep_console_alive.ps1
```

The watchdog starts the bot only once per Windows session. If you press `거래 중지`, it will stay stopped until you press `계속 거래 시작` again or restart the watchdog/session.

## Run Bot Directly

```powershell
python main.py --config config.json
```
