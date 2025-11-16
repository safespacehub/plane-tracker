# CircuitPython (ESP32) — Multi-session uptime with in-place updates + store-and-forward
# https://learn.adafruit.com/adafruit-adalogger-featherwing/rtc-with-circuitpython

import time, os, json, rtc, wifi, socketpool, ssl, random
import board, busio, digitalio, storage
import adafruit_ntp, adafruit_requests
import adafruit_sdcard
from adafruit_pcf8523.pcf8523 import PCF8523

# ---------- UUID Generation ----------
def generate_uuid():
    """Generate a UUID v4-like string."""
    # Generate 16 random bytes
    rand_bytes = bytearray(16)
    for i in range(16):
        rand_bytes[i] = random.randint(0, 255)
    
    # Set version (4) and variant (2) bits
    rand_bytes[6] = (rand_bytes[6] & 0x0F) | 0x40  # version 4
    rand_bytes[8] = (rand_bytes[8] & 0x3F) | 0x80  # variant 2
    
    # Format as UUID string
    uuid = "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x" % tuple(rand_bytes)
    return uuid

# ---------- CONFIG ----------
# SD card pin S3 is board.D33
# SD card pin S2 is board.D10
SD_CS_PIN = board.D33         # SD card chip select pin (adjust for your board)
SD_MOUNT_PATH = "/sd"           # Where to mount the SD card
STATE_FILENAME = "sessions.json"
DEVICE_ID_FILENAME = "device_id.txt"
SAVE_PERIOD_SEC = 60            # update the current session at most once/min
POST_PERIOD_SEC = 5             # try to POST pending sessions this often when online
WIFI_RECONNECT_COOLDOWN = 60    # wait this long between WiFi reconnection attempts
MAX_SESSIONS = 200              # keep at most this many sessions (drop oldest fully-ack'd)
WIFI_RETRIES = 15
NTP_RETRIES = 8

# ---------- STORAGE SETUP ----------
def init_sd_card():
    """Initialize SD card. Returns mount path if successful, None if SD card not available."""
    try:
        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        cs = digitalio.DigitalInOut(SD_CS_PIN)
        sdcard = adafruit_sdcard.SDCard(spi, cs)
        vfs = storage.VfsFat(sdcard)
        storage.mount(vfs, SD_MOUNT_PATH)
        print("SD card mounted at", SD_MOUNT_PATH)
        return SD_MOUNT_PATH
    except Exception as e:
        print("No SD card found:", e)
        return None

def get_storage_paths(sd_path):
    """Get file paths for state and device ID. Uses SD card if available, otherwise internal flash."""
    if sd_path:
        # Use SD card
        state_path = sd_path + "/" + STATE_FILENAME
        device_id_path = sd_path + "/" + DEVICE_ID_FILENAME
        print("Using SD card storage")
        
        # Migrate device_id from internal flash to SD card if it doesn't exist on SD
        flash_device_id_path = "/" + DEVICE_ID_FILENAME
        if not file_exists(device_id_path) and file_exists(flash_device_id_path):
            print("Migrating device_id from internal flash to SD card...")
            try:
                with open(flash_device_id_path, "r") as f:
                    device_id = f.read().strip()
                with open(device_id_path, "w") as f:
                    f.write(device_id)
                    f.flush()
                    os.sync()
                print("Device ID migrated successfully:", device_id)
            except Exception as e:
                print("Warning: Could not migrate device ID:", e)
        
        # Migrate sessions.json from internal flash to SD card if it doesn't exist on SD
        flash_state_path = "/" + STATE_FILENAME
        if not file_exists(state_path) and file_exists(flash_state_path):
            print("Migrating sessions from internal flash to SD card...")
            try:
                with open(flash_state_path, "r") as f:
                    state_data = f.read()
                with open(state_path, "w") as f:
                    f.write(state_data)
                    f.flush()
                    os.sync()
                print("Session data migrated successfully")
            except Exception as e:
                print("Warning: Could not migrate session data:", e)
    else:
        # Fall back to internal flash
        state_path = "/" + STATE_FILENAME
        device_id_path = "/" + DEVICE_ID_FILENAME
        print("Using internal flash storage")
        # Try to remount flash as writable
        try:
            storage.remount("/", False)
        except Exception:
            pass
    
    return state_path, device_id_path

# ---------- UTILS ----------
def init_hardware_rtc():
    """Initialize the hardware RTC (PCF8523). Returns RTC object or None if not available."""
    try:
        i2c = board.I2C()
        hw_rtc = PCF8523(i2c)
        print("Hardware RTC found")
        return hw_rtc
    except Exception as e:
        print("No hardware RTC found:", e)
        return None

def get_or_create_device_id(device_id_path):
    """Get the device ID from storage or create a new one."""
    try:
        with open(device_id_path, "r") as f:
            device_id = f.read().strip()
            # Validate UUID format
            if len(device_id) == 36 and device_id.count("-") == 4:
                return device_id
    except OSError:
        pass
    
    # Create new device ID if none exists or invalid
    device_id = generate_uuid()
    try:
        with open(device_id_path, "w") as f:
            f.write(device_id)
            f.flush()
            os.sync()
    except Exception as e:
        print("Warning: Could not save device ID:", e)
    
    return device_id

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

def iso_utc(dt=None, hw_rtc=None):
    """Get ISO UTC timestamp. Prefers hardware RTC if available, falls back to software RTC."""
    if dt is None:
        if hw_rtc is not None:
            try:
                dt = hw_rtc.datetime
            except Exception:
                dt = rtc.RTC().datetime
        else:
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

def load_state(state_path):
    """Load state from the specified path."""
    if not file_exists(state_path):
        return {"sessions": []}
    try:
        with open(state_path, "r") as f:
            data = json.load(f)
            if "sessions" not in data or not isinstance(data["sessions"], list):
                data["sessions"] = []
            return data
    except Exception as e:
        print("Load error, starting fresh:", e)
        return {"sessions": []}

def connect_wifi():
    """Connect to WiFi using environment credentials."""
    ssid = os.getenv('CIRCUITPY_WIFI_SSID')
    password = os.getenv('CIRCUITPY_WIFI_PASSWORD')
    
    for i in range(WIFI_RETRIES):
        try:
            wifi.radio.connect(ssid, password)
            print("Wi-Fi connected:", wifi.radio.ipv4_address)
            return True
        except Exception as e:
            print("Wi-Fi retry", i + 1, "/", WIFI_RETRIES, "-", e)
            time.sleep(1.5)
    
    print("Wi-Fi connection failed after", WIFI_RETRIES, "attempts")
    return False

def set_time_from_ntp(hw_rtc=None):
    """Sync time from NTP server. Updates both software and hardware RTC if available."""
    pool = socketpool.SocketPool(wifi.radio)
    last = None
    for i in range(NTP_RETRIES):
        try:
            ntp = adafruit_ntp.NTP(pool, server="pool.ntp.org", tz_offset=0)
            ntp_time = ntp.datetime
            
            # Update software RTC
            rtc.RTC().datetime = ntp_time
            
            # Update hardware RTC if available
            if hw_rtc is not None:
                try:
                    hw_rtc.datetime = ntp_time
                    print("NTP synced to hardware RTC:", iso_utc(ntp_time))
                except Exception as e:
                    print("Warning: Could not sync hardware RTC:", e)
            else:
                print("NTP synced:", iso_utc(ntp_time))
            
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
    """Build and return a requests session, or None if it fails."""
    try:
        pool = socketpool.SocketPool(wifi.radio)
        ctx = ssl.create_default_context()
        return adafruit_requests.Session(pool, ctx)
    except Exception as e:
        print("Failed to create requests session:", e)
        return None

def try_post_updates(req, state, device_id, ingest_url):
    """Send any session whose run_seconds > acked_run_seconds. Returns True if progress was made."""
    headers = {"Content-Type": "application/json"}
    progressed = False
    
    # Send oldest first so the server timeline is monotonic
    for s in state["sessions"]:
        rs = int(s.get("run_seconds", 0))
        ack = int(s.get("acked_run_seconds", 0))
        status = s.get("status", "open")
        
        if rs > ack:
            payload = {
                "device_id": device_id,
                "session_start": s["start"],
                "run_seconds": rs,
                "last_update": s.get("last_update"),
                "status": status,
            }
            
            try:
                resp = req.post(ingest_url, json=payload, headers=headers, timeout=10)
                
                if 200 <= resp.status_code < 300:
                    s["acked_run_seconds"] = rs
                    progressed = True
                    if status == "closed":
                        print("POST acknowledged (closed session)")
                    else:
                        print("POST acknowledged")
                else:
                    print("POST failed:", resp.status_code)
                    break  # Stop on first failure to avoid hammering
                    
            except Exception as e:
                print("POST error:", e)
                break  # Stop on network error
                
    return progressed

# ---------- MAIN ----------
def main():
    from secrets import secrets
    
    print("Boot…")

    # Initialize SD card storage (falls back to internal flash if not available)
    sd_path = init_sd_card()
    state_path, device_id_path = get_storage_paths(sd_path)

    # Initialize hardware RTC
    hw_rtc = init_hardware_rtc()

    # Connect to WiFi and sync time
    wifi_ok = connect_wifi()
    ntp_ok = set_time_from_ntp(hw_rtc) if wifi_ok else False
    
    # If NTP failed but we have hardware RTC, sync software RTC from hardware
    if not ntp_ok and hw_rtc is not None:
        try:
            rtc.RTC().datetime = hw_rtc.datetime
            print("Time loaded from hardware RTC:", iso_utc(hw_rtc=hw_rtc))
            ntp_ok = True  # We have valid time from hardware RTC
        except Exception as e:
            print("Could not read hardware RTC:", e)

    # Get or create persistent device ID
    device_id = get_or_create_device_id(device_id_path)
    print("Device ID:", device_id)

    # Load state and close any previously-open session
    state = load_state(state_path)
    closed_count = 0
    for s in state["sessions"]:
        if s.get("status") != "closed":
            s["status"] = "closed"
            # Force re-send by reducing acked_run_seconds by 1
            # This ensures the closed status gets sent to server
            ack = int(s.get("acked_run_seconds", 0))
            if ack > 0:
                s["acked_run_seconds"] = ack - 1
            closed_count += 1
    
    if closed_count > 0:
        print("Marked", closed_count, "session(s) as closed")

    # Start new session (one entry per boot)
    session = {
        "start": iso_utc(hw_rtc=hw_rtc) if ntp_ok else "(unsynced)",
        "run_seconds": 0,
        "acked_run_seconds": 0,
        "last_update": iso_utc(hw_rtc=hw_rtc) if ntp_ok else "(unsynced)",
        "status": "open"
    }
    state["sessions"].append(session)
    save_json_atomic(state_path, state)
    print("New session:", session["start"])

    # Initialize timing and network
    boot_t0 = time.monotonic()
    last_save_t = -9999
    last_post_t = -9999
    last_wifi_attempt = -9999
    req = build_requests_session() if wifi.radio.ipv4_address else None
    ingest_url = secrets["ingest_url"]

    while True:
        now = time.monotonic()
        now_int = int(now)

        # Periodic session update (in-place)
        if now_int - last_save_t >= SAVE_PERIOD_SEC:
            last_save_t = now_int
            elapsed = int(now - boot_t0)
            session["run_seconds"] = elapsed
            session["last_update"] = iso_utc(hw_rtc=hw_rtc) if ntp_ok else "(unsynced)"
            save_json_atomic(state_path, state)
            print("Updated:", session["start"], "run", elapsed, "s")

        # Networking: reconnect if needed (with cooldown to avoid hammering)
        if not wifi.radio.ipv4_address and (now_int - last_wifi_attempt >= WIFI_RECONNECT_COOLDOWN):
            last_wifi_attempt = now_int
            print("No Wi-Fi; attempting reconnection…")
            time.sleep(2)
            if connect_wifi():
                print("Reconnection successful!")
                # Try to sync time from NTP (especially if hardware RTC wasn't present at boot)
                if set_time_from_ntp(hw_rtc):
                    ntp_ok = True
                req = build_requests_session()
            else:
                print("Reconnection failed. Will retry in", WIFI_RECONNECT_COOLDOWN, "seconds")

        # Try to POST pending updates
        if wifi.radio.ipv4_address and (now_int - last_post_t >= POST_PERIOD_SEC):
            last_post_t = now_int
            
            # Ensure we have a requests session
            if req is None:
                req = build_requests_session()
            
            # Try to send updates
            if req is not None:
                progressed = try_post_updates(req, state, device_id, ingest_url)
                if progressed:
                    # Persist ack counters immediately to prevent duplicate sends
                    save_json_atomic(state_path, state)
                    prune_fully_acked(state)

        time.sleep(0.25)

main()

