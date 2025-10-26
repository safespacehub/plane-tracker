Sure — here’s the same **README** in plain text form (no Markdown formatting):

---

ESP32 Uptime & Session Logger (Store-and-Forward)

This project turns an ESP32 running CircuitPython into a resilient uptime recorder.
It creates a new “session” each time the device boots, keeps track of how long it runs,
and syncs those updates to a remote HTTP endpoint whenever Wi-Fi is available.

If the ESP32 goes offline (e.g., a car leaving the garage), it continues tracking uptime locally.
When Wi-Fi returns, it automatically uploads any missed updates — no data loss.

---

## Features

* Accurate session tracking using NTP time on each boot
* Single JSON file with one entry per session, updated in-place (no endless appending)
* Automatic store-and-forward: unsent updates are kept until they reach the server
* Atomic file writes: prevents corruption during power loss
* Idempotent uploads: duplicate posts are safe (msg_id = session_start:run_seconds)
* Self-healing: tolerates Wi-Fi failures, DNS issues, power cuts
* Easily portable to FRAM or SD storage if desired

---

## File Structure

/
├── code.py          (main application)
├── secrets.py       (Wi-Fi & server credentials; you create this)
└── sessions.json    (generated automatically; holds all sessions)

---

## Hardware Requirements

* ESP32 (or compatible) running CircuitPython 9.x or later
* Optional:

  * I2C FRAM module (for near-infinite write endurance)
  * microSD card (if you want long-term archives)
* Wi-Fi network reachable at least occasionally (for example, your garage)

---

## Creating secrets.py

Create a file named secrets.py in the same directory as code.py:

secrets = {
"ssid": "YOUR_WIFI_SSID",
"password": "YOUR_WIFI_PASSWORD",

```
# Unique device ID for your deployment
"device_id": "car-esp32-01",

# URL of your server endpoint that accepts POST JSON
"ingest_url": "https://example.com/ingest"
```

}

Keep this file private — never upload it to public repositories.

---

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

---

## Server Endpoint Specification

HTTP Method: POST
Content-Type: application/json

Example body:
{
"device_id": "car-esp32-01",
"session_start": "2025-10-23T18:00:00Z",
"run_seconds": 1200,
"last_update": "2025-10-23T18:20:00Z",
"status": "open",
"msg_id": "2025-10-23T18:00:00Z:1200"
}

Your server should:

* Accept duplicates safely (idempotent on msg_id)
* Respond 200 OK for success
* Optionally store/aggregate by device_id and session_start

---

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

---


## Example Log Output

Boot…
Wi-Fi: 192.168.1.45
NTP: 2025-10-23T18:00:02Z
New session: 2025-10-23T18:00:02Z
Updated: 2025-10-23T18:00:02Z run 60 s
POST OK 200
Updated: 2025-10-23T18:00:02Z run 120 s
Wi-Fi lost; reconnecting…
NTP failed; continuing offline
...


