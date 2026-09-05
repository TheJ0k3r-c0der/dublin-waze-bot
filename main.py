import os
import threading
import time
import requests
from flask import Flask

# 1. Dummy Web Server for Render
app = Flask(__name__)

@app.route("/")
def home():
    return "Dublin Waze Multi-Alert Bot is running 24/7!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Telegram Credentials
BOT_TOKEN = "8744802014:AAGkTNyb4RC_LfG0grxr2j01BsJ8xkCtg2c"
CHAT_ID = "-1004349956233"

# 3. Waze Bounding Box Coordinates for Dublin
WAZE_URL = (
    "https://www.waze.com/live-map/api/georss"
    "?top=53.45&bottom=53.20&left=-6.45&right=-6.05"
    "&env=row&types=alerts"
)

seen_incidents = set()

# Emoji-uri și titluri în funcție de tipul de alertă
ALERT_TYPES = {
    "ACCIDENT": {"emoji": "🚨", "title": "Accident"},
    "POLICE": {"emoji": "👮‍♂️", "title": "Police Presence"},
    "JAM": {"emoji": "🚗🚗", "title": "Heavy Traffic Jam"},
    "WEATHERHAZARD": {"emoji": "⚠️", "title": "Weather Hazard / Road Hazard"},
    "HAZARD": {"emoji": "⚠️", "title": "Road Hazard"},
    "ROAD_CLOSED": {"emoji": "⛔", "title": "Road Closed"}
}

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
            uuid = alert.get("uuid")

            # Procesăm doar alertele noi
            if uuid not in seen_incidents:
                alert_type = alert.get("type", "HAZARD")
                street = alert.get("street", "Unspecified Road")
                subtype = alert.get("subtype", "")
                location = alert.get("location", {})
                lat = location.get("y")
                lon = location.get("x")

                # Preluăm emoji-ul și titlul corespunzător
                type_info = ALERT_TYPES.get(alert_type, {"emoji": "⚠️", "title": "Traffic Alert"})
                emoji = type_info["emoji"]
                
                if subtype:
                    clean_title = subtype.replace("_", " ").title()
                else:
                    clean_title = type_info["title"]

                # Mesaj în engleză
                message = (
                    f"{emoji} **{clean_title} in Dublin**\n\n"
                    f"📍 **Location:** {street}\n"
                    f"🗺️ [View on Google Maps](https://www.google.com/maps?q={lat},{lon})\n"
                    f"🚗 [Open in Waze](https://waze.com/ul?ll={lat},{lon}&navigate=yes)"
                )

                send_telegram_alert(message)
                seen_incidents.add(uuid)

    except Exception as e:
        print(f"[Waze Processing Error]: {e}")

def waze_loop():
    while True:
        check_waze()
        time.sleep(90)

if __name__ == "__main__":
    print("=== Dublin Waze Multi-Alert Bot Started ===")
    
    # Start Waze checking in background
    threading.Thread(target=waze_loop, daemon=True).start()
    
    # Start web server for Render
    run_web_server()
