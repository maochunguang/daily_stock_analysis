# QMT Bridge (Windows only)

This service wraps QMT/miniQMT `xtquant` behind a small HTTP API so the macOS
personal layer never talks to the broker directly.

## Prerequisites

1. Windows machine with QMT/miniQMT installed and logged in.
2. miniQMT/xtquant permission enabled by the broker.
3. Copy the `xtquant` folder from the QMT installation into this Python
   environment (or use the Python bundled with QMT).
4. Set environment variables:

```env
QMT_MODE=xtquant
QMT_USERDATA_MINI=C:\中信建投QMT\userdata_mini
QMT_ACCOUNT_ID=你的资金账号
QMT_BRIDGE_TOKEN=change-me
QMT_BRIDGE_HOST=0.0.0.0
QMT_BRIDGE_PORT=8710
```

## Run

```bash
pip install -r requirements.txt
python app.py
```

Use `QMT_MODE=mock` to test the HTTP contract without QMT.

## Safety

- Bind to the LAN only; never expose this service to the public internet.
- Always set `QMT_BRIDGE_TOKEN`.
- Start with the mock adapter, then a simulated account, then small live size.
- The bridge does not bypass QMT/broker risk checks; it adds a local pre-check
  layer in the personal client.
