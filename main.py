import time
import requests

# 1. Telegram Credentials
BOT_TOKEN = "8744802014:AAGkTNyb4RC_LfG0grxr2j01BsJ8xkCtg2c"
CHAT_ID = "-1004349956233"

# 2. Waze Bounding Box Coordinates for Dublin Metropolitan Area
WAZE_URL = (
    "https://www.waze.com/live-map/api/georss"
    "?top=53.45&bottom=53.20&left=-6.45&right=-6.05"
    "&env=row&types=alerts"
)

# Temporary memory to avoid duplicate alerts
seen_incidents = set()


def send_telegram_alert(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("[OK] Alert sent successfully to Telegram!")
        else:
            print(f"[Telegram Error] Status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[Telegram Network Error]: {e}")


def check_waze():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(WAZE_URL, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"[Waze Error] Could not retrieve data. Status: {response.status_code}")
            return

        data = response.json()
        alerts = data.get("alerts", [])

        print(f"[{time.strftime('%H:%M:%S')}] Fetched {len(alerts)} total alerts from Dublin area...")

        for alert in alerts:
            # Filter only traffic accidents
            alert_type = alert.get("type")
            if alert_type == "ACCIDENT":
                uuid = alert.get("uuid")

                if uuid not in seen_incidents:
                    street = alert.get("street", "Unspecified Road")
                    subtype = alert.get("subtype", "ACCIDENT")
                    location = alert.get("location", {})
                    lat = location.get("y")
                    lon = location.get("x")

                    # Format the accident subtype description
                    clean_subtype = subtype.replace("_", " ").title() if subtype else "Traffic Accident"

                    # Build the English message for Telegram
                    message = (
                        f"🚨 **{clean_subtype} in Dublin**\n\n"
                        f"📍 **Location:** {street}\n"
                        f"🗺️ [View on Google Maps](https://www.google.com/maps?q={lat},{lon})\n"
                        f"🚗 [Open in Waze](https://waze.com/ul?ll={lat},{lon}&navigate=yes)"
                    )

                    send_telegram_alert(message)
                    seen_incidents.add(uuid)

    except Exception as e:
        print(f"[Waze Processing Error]: {e}")


if __name__ == "__main__":
    print("=== Dublin Waze Traffic Bot Started ===")
    print("Checking for new accidents every 90 seconds...\n")
    
    while True:
        check_waze()
        time.sleep(90)  # Wait 1.5 minutes between checks
