# ESP32 Uptime & Session Logger (Store-and-Forward)

This project turns an ESP32 running CircuitPython into a resilient uptime recorder.
It creates a new “session” each time the device boots, keeps track of how long it runs,
and syncs those updates to a remote HTTP endpoint whenever Wi-Fi is available.

If the ESP32 goes offline (e.g., a airplane leaving the hangar Wi-Fi network), it continues tracking uptime locally.
When Wi-Fi returns, it automatically uploads any missed updates — no data loss.

## Features

* Accurate session tracking using NTP time on each boot
* Single JSON file with one entry per session, updated in-place
* Automatic store-and-forward: unsent updates are kept until they reach the server
* Atomic file writes: prevents corruption during power loss
* Idempotent uploads: duplicate posts are safe (msg_id = session_start:run_seconds)
* Self-healing: tolerates Wi-Fi failures, DNS issues, power cuts


## File Structure
```
/
├── code.py          (main application)
├── secrets.py       (Wi-Fi & server credentials; you create this)
└── sessions.json    (generated automatically; holds all sessions)
```

## Hardware Requirements

* ESP32 (or compatible) running CircuitPython 9.x or later. (https://www.adafruit.com/product/5400?srsltid=AfmBOopfVX9sTUdD7UWcMrLCqh4HohZRu2X3p2BO_jnP2IiykY71jl32)
* Wi-Fi network reachable at least occasionally


## Creating secrets.py

Create a file named secrets.py in the same directory as code.py:
```python
secrets = {
    # Supabase Edge Function URL
    "ingest_url": "https://your-project.supabase.co/functions/v1/ingest",
    
    # Access token (optional, leave empty)
    "access_token": "",
}
```

**Note:** Device UUID is now automatically generated on first boot using MicroPython's crypto.
You no longer need to manually specify a device_id!


## How It Works

1. On boot:

   * Connects to Wi-Fi
   * Fetches UTC time via NTP
   * Starts a new session:
     {
     "start": "2025-10-23T18:00:00Z",
     "run_seconds": 0,
     "acked_run_seconds": 0,
     "last_update": "2025-10-23T18:00:00Z",
     "status": "open"
     }

2. Every minute:

   * Increments run_seconds
   * Updates last_update
   * Saves the file atomically

3. Every few seconds (if online):

   * Sends pending sessions to the server
   * Marks them as acked_run_seconds = run_seconds

4. When offline:

   * Keeps counting uptime
   * Queues updates for later transmission


## Backend Architecture

This system uses **Supabase** for the backend:

- **PostgreSQL Database** - Stores planes, devices, and sessions
- **Edge Function** - Ingests data from ESP32 devices
- **Row Level Security** - Protects user data
- **Authentication** - Secure user accounts

### Edge Function Endpoint

**POST** `/functions/v1/ingest`

Example body:
```json
{
  "device_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "session_start": "2025-10-23T18:00:00Z",
  "run_seconds": 1200,
  "last_update": "2025-10-23T18:20:00Z",
  "status": "open",
  "msg_id": "550e8400-e29b-41d4-a716-446655440000:2025-10-23T18:00:00Z:1200"
}
```

The edge function:
- Accepts duplicates safely (idempotent on msg_id)
- Updates device last_seen timestamp
- Returns 200 OK on success
- Uses service role to bypass RLS

## Web Portal

Access your tracking data through the modern web portal:

- **Dashboard** - Overview of devices, planes, and flight time
- **Device Management** - Register and assign devices to planes
- **Plane Management** - Manage your aircraft fleet
- **Session History** - Complete flight logs with export

Deploy to GitHub Pages or any static hosting service.

See `site_sym/README.md` for portal documentation.
See `DEPLOYMENT.md` for complete setup guide.


## Initial ESP32 Setup
1. Follow Adafruit tutorial to install firmware (https://learn.adafruit.com/adafruit-huzzah32-esp32-feather/circuitpython) or (https://learn.adafruit.com/circuitpython-with-esp32-quick-start/installing-circuitpython)

## Connecting to serial output on Debian
**View available devices** `dmesg | grep tty`
**Connect to a device** `screen /dev/ttyACM1 115200`
**Create a settings.toml with Python over serial**
```
f = open('settings.toml', 'w') 
f.write('CIRCUITPY_WIFI_SSID = "my-wifi-name"\n') 
f.write('CIRCUITPY_WIFI_PASSWORD = "password"\n')
f.write('CIRCUITPY_WEB_API_PASSWORD = "password"\n') 
f.close()
```
**Find IP address over serial**
```
import wifi 
print("My MAC addr: %02X:%02X:%02X:%02X:%02X:%02X" % tuple(wifi.radio.mac_address)) 
print("My IP address is", wifi.radio.ipv4_address)
```

## Testing the System

1. Connect the board to a USB port and open the CircuitPython drive.
2. Copy code.py and secrets.py to it.
3. Open a serial console to watch log output.

Then try the following tests:

* Power off mid-update: File stays valid and resumes correctly next boot.
* Disconnect Wi-Fi: Device keeps logging uptime, posts later.
* Fake server error (HTTP 500): Retries later, no data loss.
* Toggle router power: Device reconnects within about 30 seconds.
* Long offline period: All updates transmit once Wi-Fi returns.


## Example Log Output
```
Boot…
Wi-Fi: 192.168.1.45
NTP: 2025-10-23T18:00:02Z
New session: 2025-10-23T18:00:02Z
Updated: 2025-10-23T18:00:02Z run 60 s
POST OK 200
Updated: 2025-10-23T18:00:02Z run 120 s
Wi-Fi lost; reconnecting…
NTP failed; continuing offline
```
...


