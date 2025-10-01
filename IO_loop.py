import os, time, requests, logging
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# --- config ---
BERLIN = ZoneInfo("Europe/Berlin")
POLL_INTERVAL_SEC = 1.1
STALE_AFTER = timedelta(minutes=2)  # treat data older than this as failure

# --- logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
)

def iso_utc(ts: str) -> datetime:
    # Normalize common API variants to an aware UTC datetime
    # Examples seen: "2025-09-08T13:23:00Z", "2025-09-08T13:23:00+00:00", "2025-09-08T13:23:00"
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"     # make it explicit UTC
    dt = datetime.fromisoformat(ts) # may be naive or aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # assume UTC if missing
    return dt.astimezone(timezone.utc)

# --- hardware stubs (replace later) ---
def led_ok(color: str):
    print(f"[LED] {color} solid")

def led_error_blink():
    print("[LED] ERROR: blink all")

def buzzer_ok():
    print("[BUZZER] ok tone")

def buzzer_error():
    print("[BUZZER] error tone")

def self_test_start():
    print("[SELF-TEST] LED sweep + tone")  

def self_test_success():
    print("[SELF-TEST] PASS")

def self_test_fail():
    print("[SELF-TEST] FAIL")

# --- value map (exactly as requested) ---
VALUE_MAP = {
    "BLUE": 0,
    "GREEN_POS": 1, "GREEN_NEG": -1,
    "YELLOW_POS": 2, "YELLOW_NEG": -2,
    "RED_POS": 3,   "RED_NEG": -3,
}

def get_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(
        "https://identity.netztransparenz.de/users/connect/token",
        data={"grant_type": "client_credentials",
              "client_id": client_id, "client_secret": client_secret},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=5
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

# --- state output (map API value -> LED/buzzer) ---
def apply_state(api_value: str):
    v = VALUE_MAP[api_value]
    if v == 0:
        led_ok("blue");   #buzzer_ok()
    elif v == 1:
        led_ok("green");  #buzzer_ok()
    elif v == -1:
        led_ok("green");  #buzzer_ok()
    elif v == 2:
        led_ok("yellow"); #buzzer_ok()
    elif v == -2:
        led_ok("yellow"); #buzzer_ok()
    elif v == 3:
        led_ok("red");    #buzzer_ok()
    elif v == -3:
        led_ok("red");    #buzzer_ok()

def failure_mode(reason: str):
    logging.error("Failure mode: %s", reason)
    led_error_blink()
    buzzer_error()

def fetch_latest_rows(token: str, client_id: str, client_secret: str):
    now_utc = datetime.now(timezone.utc)
    to_utc  = now_utc.replace(second=0, microsecond=0)
    from_utc = to_utc - timedelta(minutes=10)
    fmt_api = "%Y-%m-%dT%H:%M:%SZ"
    api_url = (
        f"https://ds.netztransparenz.de/api/v1/data/TrafficLight/"
        f"{from_utc.strftime(fmt_api)}/{to_utc.strftime(fmt_api)}"
    )

    try:
        r = requests.get(api_url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
        r.raise_for_status()
        return r.json(), token
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            # refresh token once, then retry the same call
            new_token = get_token(client_id, client_secret)
            r2 = requests.get(api_url, headers={"Authorization": f"Bearer {new_token}"}, timeout=5)
            r2.raise_for_status()
            return r2.json(), new_token
        raise


def main():
    load_dotenv()
    CLIENT_ID     = os.getenv("IPNT_CLIENT_ID")
    CLIENT_SECRET = os.getenv("IPNT_CLIENT_SECRET")

    token = get_token(CLIENT_ID, CLIENT_SECRET)

    self_test_start()
    last_to = None
    in_failure = False
    first_after_start = True  # <- add this

    # --- startup probe (unchanged logic, but using new fetch) ---
    try:
        rows, token = fetch_latest_rows(token, CLIENT_ID, CLIENT_SECRET)
        if not rows:
            self_test_fail(); failure_mode("startup: empty response"); in_failure = True
        else:
            latest = rows[-1]
            latest_to = iso_utc(latest["To"])
            age = datetime.now(timezone.utc) - latest_to
            if age > STALE_AFTER:
                self_test_fail(); failure_mode(f"startup: stale data ({age})"); in_failure = True
            else:
                self_test_success()
                apply_state(latest["Value"])
                last_to = latest_to
                in_failure = False
                f_loc = iso_utc(latest["From"]).astimezone(BERLIN).strftime("%Y-%m-%d %H:%M:%S %Z")
                t_loc = latest_to.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M:%S %Z")
                logging.info("Initial state: %s → %s : %s", f_loc, t_loc, VALUE_MAP[latest["Value"]])
    except Exception as e:
        self_test_fail(); failure_mode(f"startup error: {e}"); in_failure = True

    while True:
        try:
            rows, token = fetch_latest_rows(token, CLIENT_ID, CLIENT_SECRET)

            if not rows:
                if not in_failure:
                    failure_mode("empty response"); in_failure = True
            else:
                latest = rows[-1]
                val = latest.get("Value")
                if val not in VALUE_MAP:
                    if not in_failure:
                        failure_mode(f"unknown value: {val}"); in_failure = True
                else:
                    latest_to = iso_utc(latest["To"])
                    if last_to is None or latest_to > last_to:
                        last_to = latest_to
                        apply_state(val)
                        f_loc = iso_utc(latest["From"]).astimezone(BERLIN).strftime("%Y-%m-%d %H:%M:%S %Z")
                        t_loc = latest_to.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M:%S %Z")
                        logging.info("%s → %s : %s", f_loc, t_loc, VALUE_MAP[val])


                        if first_after_start:
                            # skip the very first countdown
                            first_after_start = False
                        else:
                            for sec in range(55, 0, -1):
                                print(f"\rSleeping: {sec:02d}s", end="", flush=True)
                                time.sleep(1)
                            print("\r", end="")  # clear line when done

                    # stale check
                    age = datetime.now(timezone.utc) - latest_to
                    if age > STALE_AFTER:
                        if not in_failure:
                            failure_mode(f"stale data ({age})"); in_failure = True
                    else:
                        # success path clears failure state
                        in_failure = False

        except Exception as e:
            if not in_failure:
                failure_mode(str(e)); in_failure = True

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
