
# ESP32 Device Simulator (Uptime & Session Logger)

This Go program simulates an ESP32 running the **Uptime & Session Logger** project.  
It generates random sessions, increments uptime, and posts JSON updates to an HTTP ingest endpoint — just like the real CircuitPython device would.

You can use this simulator to:
- **Test your ingest server** before deploying real hardware  
- **Stress test** store-and-forward and retry logic  
- **Generate synthetic data** for development and visualization

---

## 🧩 Features

- Creates a configurable number of **random sessions**
- Sends periodic JSON updates (`run_seconds`, `last_update`, etc.)
- Automatically **queues failed uploads** and retries oldest-first
- Simulates **network dropouts** and **server errors**
- Adjustable time acceleration (1 simulated minute = N milliseconds)
- Supports **idempotent message IDs** (`session_start:run_seconds`)
- Easy to integrate with a local or remote ingest server

---

## 🗂 Project Structure

```

/simulator
├── main.go          # the simulator
└── ingest.go    # minimal POST receiver (optional)

````

---

## ⚙️ Build & Run

### 1. Run an ingest server

Start a simple HTTP endpoint that accepts JSON `POST` requests at `/ingest`.

Minimal version:

```bash
go run ingest.go
````

Default address: `http://127.0.0.1:8080/ingest`

---

### 2. Run the simulator

```bash
go run main.go \
  -url http://127.0.0.1:8080/ingest \
  -device airplane-esp32-sim-01 \
  -sessions 10 \
  -minSessionMin 5 \
  -maxSessionMin 30 \
  -tickMS 150 \
  -updateEveryMin 1 \
  -offlineProb 0.25 \
  -serverErrProb 0.1 \
  -batch 8 \
  -flushEveryMS 400 \
  -jitterMS 50
```

The simulator will generate random sessions and print output like:

```
Starting simulator: device=airplane-esp32-sim-01 url=http://127.0.0.1:8080/ingest sessions=10
New session #1 start=2025-10-26T07:31:40Z target=12m
[sent ] 2025-10-26T07:31:40Z run=60s
[queue] offline -> 2025-10-26T07:31:40Z run=120s
[flushed] 2025-10-26T07:31:40Z run=120s
[sent ] final 2025-10-26T07:31:40Z run=720s (closed)
...
```

---

## 🔧 Command-Line Flags

| Flag              | Default                        | Description                                        |
| ----------------- |--------------------------------| -------------------------------------------------- |
| `-url`            | `http://127.0.0.1:8080/ingest` | Ingest endpoint URL                                |
| `-device`         | `airplane-esp32-sim-01`        | Device ID                                          |
| `-sessions`       | `5`                            | How many sessions to simulate                      |
| `-minSessionMin`  | `5`                            | Minimum session length (minutes)                   |
| `-maxSessionMin`  | `60`                           | Maximum session length (minutes)                   |
| `-tickMS`         | `200`                          | Real milliseconds per simulated minute             |
| `-updateEveryMin` | `1`                            | How often to send updates (simulated minutes)      |
| `-offlineProb`    | `0.2`                          | Probability of being “offline” at any given update |
| `-serverErrProb`  | `0.1`                          | Probability of simulated server failure            |
| `-batch`          | `8`                            | Number of queued updates sent per flush            |
| `-flushEveryMS`   | `400`                          | Interval between retry flushes (ms)                |
| `-jitterMS`       | `75`                           | Random jitter added to each tick                   |
| `-seed`           | (random)                       | RNG seed for reproducibility                       |
| `-v`              | `true`                         | Enable verbose logging                             |

Environment variables also work:

```
INGEST_URL, DEVICE_ID
```

---

## 🧠 Behavior Overview

### Session lifecycle

* Each session represents one boot cycle of a device.
* The session has a random duration (`minSessionMin`–`maxSessionMin`).
* Each “device minute” the simulator may:

    * go offline (based on `offlineProb`),
    * send a JSON update with the current `run_seconds`,
    * or queue the update for later transmission.

### Store-and-forward

* Failed or offline updates are **enqueued**.
* The background flush loop retries oldest-first until the queue is empty.
* Once acknowledged (HTTP `2xx`), updates are dropped from the queue.

### Idempotent uploads

Every update includes:

```
"msg_id": "session_start:run_seconds"
```

Your server should treat this key as unique so duplicates are safe.

---

## 🌐 Example Server JSON Payload

```json
{
  "device_id": "airplane-esp32-01",
  "session_start": "2025-10-23T18:00:00Z",
  "run_seconds": 1200,
  "last_update": "2025-10-23T18:20:00Z",
  "status": "open",
  "msg_id": "2025-10-23T18:00:00Z:1200"
}
```

---

## 🧪 Testing Scenarios

| Scenario                                  | What to observe                                          |
| ----------------------------------------- | -------------------------------------------------------- |
| Simulate weak Wi-Fi (`-offlineProb 0.5`)  | Device queues most updates; flushes when “online” again  |
| Server instability (`-serverErrProb 0.3`) | Retries until 2xx, no lost messages                      |
| Long sessions (hours)                     | Continuous updates; only last one per minute per session |
| Many concurrent devices                   | Run multiple simulators with different `-device` values  |

---

## 🛠 Example Local Test Setup

1. Run the logging ingest server:

   ```
   go run ingest.go
   ```

2. In another terminal, start several simulators:

   ```
   go run main.go -device plane01 &
   go run main.go -device plane02 &
   ```

3. Watch the logs accumulate while each simulator randomly goes online/offline.

---

## 🧰 Developer Notes

* Written for Go 1.20+
* Pure standard library (no external dependencies)
* Deterministic if you pass a fixed `-seed`
