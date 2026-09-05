import os
import requests
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

BOT_TOKEN = "8744802014:AAGkTNyb4RC_LfG0grxr2j01BsJ8xkCtg2c"
CHAT_ID = "-1004349956233"

# URL-ul GeoRSS public Waze (bypass la blocajul 403)
WAZE_URL = (
    "https://www.waze.com/rtserver/web/TGeoRSS"
    "?left=-6.45&right=-6.05&bottom=53.20&top=53.45"
    "&types=alerts,jams"
)

seen_incidents = set()

ALERT_TYPES = {
    "ACCIDENT": {"emoji": "🚨", "title": "Accident"},
    "POLICE": {"emoji": "👮‍♂️", "title": "Police Presence"},
    "JAM": {"emoji": "🚗🚗", "title": "Traffic Jam"},
    "WEATHERHAZARD": {"emoji": "⚠️", "title": "Weather Hazard"},
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
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[Telegram Error]: {e}", flush=True)

def check_waze():
    print("[WAZE JOB] Connecting to Waze GeoRSS...", flush=True)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(WAZE_URL, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"[WAZE JOB] Error HTTP {response.status_code}", flush=True)
            return

        data = response.json()
        
        # Extragere alerte din structura GeoRSS
        alerts = data.get("alerts", [])
        if not alerts and "commons" in data:
            alerts = data.get("commons", [])

        print(f"[WAZE JOB] Success! Found {len(alerts)} active reports in Dublin.", flush=True)

        for alert in alerts:
            uuid = alert.get("uuid") or f"{alert.get('location', {}).get('x')}_{alert.get('location', {}).get('y')}"

            if uuid not in seen_incidents:
                alert_type = alert.get("type", "HAZARD")
                street = alert.get("street", "Unspecified Road")
                subtype = alert.get("subtype", "")
                location = alert.get("location", {})
                lat = location.get("y")
                lon = location.get("x")

                type_info = ALERT_TYPES.get(alert_type, {"emoji": "⚠️", "title": "Traffic Alert"})
                emoji = type_info["emoji"]
                clean_title = subtype.replace("_", " ").title() if subtype else type_info["title"]

                message = (
                    f"{emoji} **{clean_title} in Dublin**\n\n"
                    f"📍 **Location:** {street}\n"
                    f"🗺️ [View on Google Maps](https://www.google.com/maps?q={lat},{lon})\n"
                    f"🚗 [Open in Waze](https://waze.com/ul?ll={lat},{lon}&navigate=yes)"
                )

                send_telegram_alert(message)
                seen_incidents.add(uuid)

    except Exception as e:
        print(f"[WAZE JOB] Exception: {e}", flush=True)

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(check_waze, 'interval', seconds=60)
scheduler.start()

@app.route("/")
def home():
    return "Dublin Waze Multi-Alert Bot is running 24/7!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
