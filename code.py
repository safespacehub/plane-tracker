# CircuitPython (ESP32) — Multi-session uptime with in-place updates + store-and-forward
import time, os, json, rtc, wifi, socketpool, ssl
import adafruit_ntp, adafruit_requests

# ---------- CONFIG ----------
STATE_PATH = "/sessions.json"   # single JSON file
SAVE_PERIOD_SEC = 60            # update the current session at most once/min
POST_PERIOD_SEC = 5             # try to POST pending sessions this often when online
MAX_SESSIONS = 200              # keep at most this many sessions (drop oldest fully-ack'd)
WIFI_RETRIES = 15
NTP_RETRIES = 8

# ---------- UTILS ----------
def remount_rw():
    try:
        import storage
        storage.remount("/", False)
    except Exception:
        pass

def file_exists(p):
    try:
        os.stat(p)
        return True
    except OSError:
        return False

def _ymdhms_from_dt(dt):
    # Handle both struct_time and tuple variants
    if hasattr(dt, "tm_year"):
        return (dt.tm_year, dt.tm_mon, dt.tm_mday, dt.tm_hour, dt.tm_min, dt.tm_sec)
    # Common 9-tuple: (Y, M, D, H, M, S, Wd, Yd, Isdst)
    return (dt[0], dt[1], dt[2], dt[3], dt[4], dt[5])

def iso_utc(dt=None):
    if dt is None:
        dt = rtc.RTC().datetime
    y, mo, d, hh, mm, ss = _ymdhms_from_dt(dt)
    return f"{y:04d}-{mo:02d}-{d:02d}T{hh:02d}:{mm:02d}:{ss:02d}Z"

def save_json_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
        f.flush()
        os.sync()
    try:
        os.remove(path)
    except OSError:
        pass
    os.rename(tmp, path)

def load_state():
    if not file_exists(STATE_PATH):
        return {"device_id": None, "sessions": []}
    try:
        with open(STATE_PATH, "r") as f:
            data = json.load(f)
            if "sessions" not in data or not isinstance(data["sessions"], list):
                data["sessions"] = []
            return data
    except Exception as e:
        print("Load error, starting fresh:", e)
        return {"device_id": None, "sessions": []}

def connect_wifi():
    from secrets import secrets
    for i in range(WIFI_RETRIES):
        try:
            wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'), os.getenv('CIRCUITPY_WIFI_PASSWORD'))
            print("Wi-Fi:", wifi.radio.ipv4_address)
            return True
        except Exception as e:
            print("Wi-Fi retry", i + 1, "/", WIFI_RETRIES, "-", e)
            time.sleep(1.5)
    return False

def set_time_from_ntp():
    pool = socketpool.SocketPool(wifi.radio)
    last = None
    for i in range(NTP_RETRIES):
        try:
            ntp = adafruit_ntp.NTP(pool, server="pool.ntp.org", tz_offset=0)
            rtc.RTC().datetime = ntp.datetime
            print("NTP:", iso_utc())
            return True
        except Exception as e:
            last = e
            print("NTP retry", i + 1, "/", NTP_RETRIES, "-", e)
            time.sleep(2.0)
    print("NTP failed:", repr(last))
    return False

def prune_fully_acked(state):
    # Keep newest MAX_SESSIONS entries; prefer to drop oldest sessions that are fully acked
    sess = state["sessions"]
    if len(sess) <= MAX_SESSIONS:
        return
    # Partition: keep all not-fully-acked; among fully-acked drop oldest first
    keep = []
    drop_candidates = []
    for s in sess:
        if int(s.get("acked_run_seconds", 0)) >= int(s.get("run_seconds", 0)) and s.get("status") == "closed":
            drop_candidates.append(s)
        else:
            keep.append(s)
    # Drop as many from the oldest fully-acked to reach limit
    need_to_drop = max(0, (len(keep) + len(drop_candidates)) - MAX_SESSIONS)
    if need_to_drop > 0:
        drop_candidates = drop_candidates[need_to_drop:]  # drop oldest ones
    state["sessions"] = keep + drop_candidates

# ---------- NETWORK SEND ----------
def build_requests_session():
    pool = socketpool.SocketPool(wifi.radio)
    ctx = ssl.create_default_context()
    return adafruit_requests.Session(pool, ctx)

def try_post_updates(req, state):
    """Send any session whose run_seconds > acked_run_seconds. Returns True if progress was made."""
    from secrets import secrets
    url = secrets["ingest_url"]
    headers = {"Content-Type": "application/json"}

    progressed = False
    # Send oldest first so the server timeline is monotonic
    for s in state["sessions"]:
        rs = int(s.get("run_seconds", 0))
        ack = int(s.get("acked_run_seconds", 0))
        if rs > ack:
            payload = {
                "device_id": secrets.get("device_id", "device-unknown"),
                "session_start": s["start"],
                "run_seconds": rs,
                "last_update": s.get("last_update", None),
                "status": s.get("status", "open"),
                # Optional idempotency key: same session_start + run_seconds
                "msg_id": "{}:{}".format(s["start"], rs),
            }
            try:
                resp = req.post(url, json=payload, headers=headers, timeout=10)
                ok = 200 <= resp.status_code < 300
                if not ok:
                    print("POST failed:", resp.status_code)
                #resp.close()
                if ok:
                    s["acked_run_seconds"] = rs
                    progressed = True
                    print("POST acknowledged")
                else:
                    # Stop on first failure to avoid hammering
                    break
            except Exception as e:
                print("POST error:", e)
                break
    return progressed

# ---------- MAIN ----------
def main():
    remount_rw()
    print("Boot…")

    wifi_ok = connect_wifi()
    ntp_ok = set_time_from_ntp() if wifi_ok else False

    from secrets import secrets
    device_id = secrets.get("device_id", "device-unknown")

    state = load_state()
    state["device_id"] = device_id

    # Close any previously-open session (power loss) before starting a new one
    for s in state["sessions"]:
        if s.get("status") != "closed":
            s["status"] = "closed"

    # Start new session (one entry per boot)
    session = {
        "start": iso_utc() if ntp_ok else "(unsynced)",
        "run_seconds": 0,
        "acked_run_seconds": 0,
        "last_update": iso_utc() if ntp_ok else "(unsynced)",
        "status": "open"
    }
    state["sessions"].append(session)
    save_json_atomic(STATE_PATH, state)
    print("New session:", session["start"])

    boot_t0 = time.monotonic()
    last_save_t = -9999
    last_post_t = -9999
    req = None

    # On boot, if online, create requests session
    if wifi.radio.ipv4_address:
        try:
            req = build_requests_session()
        except Exception as e:
            print("requests session error:", e)

    while True:
        now = time.monotonic()

        # Periodic session update (in-place)
        if int(now) - last_save_t >= SAVE_PERIOD_SEC:
            last_save_t = int(now)
            elapsed = int(now - boot_t0)
            session["run_seconds"] = elapsed
            session["last_update"] = iso_utc() if ntp_ok else "(unsynced)"
            save_json_atomic(STATE_PATH, state)
            print("Updated:", session["start"], "run", elapsed, "s")

        # Networking: reconnect if needed
        if not wifi.radio.ipv4_address:
            # backoff-ish reconnect
            print("No Wi-Fi; reconnecting soon…")
            time.sleep(2)
            if connect_wifi():
                if not ntp_ok:
                    ntp_ok = set_time_from_ntp()
                try:
                    req = build_requests_session()
                except Exception as e:
                    print("requests session error:", e)

        # Try to POST pending updates
        if wifi.radio.ipv4_address and (int(now) - last_post_t >= POST_PERIOD_SEC):
            last_post_t = int(now)
            if req is None:
                try:
                    req = build_requests_session()
                except Exception as e:
                    print("requests session error:", e)
            if req is not None:
                progressed = try_post_updates(req, state)
                if progressed:
                    # We updated ack counters; persist lazily (piggyback on minute save),
                    # but if you want stronger durability, uncomment the next line:
                    # save_json_atomic(STATE_PATH, state)
                    prune_fully_acked(state)

        time.sleep(0.25)

main()

