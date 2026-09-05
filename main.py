import os
import requests
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

BOT_TOKEN = "8744802014:AAGkTNyb4RC_LfG0grxr2j01BsJ8xkCtg2c"
CHAT_ID = "-1004349956233"

# Endpoint-ul curent pentru LiveMap (corectat fără 404)
WAZE_URL = (
    "https://www.waze.com/live-map/api/georss"
    "?top=53.45&bottom=53.20&left=-6.45&right=-6.05"
    "&env=row&types=alerts"
)

seen_incidents = set()
session = requests.Session()

def init_session():
    """Inițializează cookie-urile accesând pagina principala LiveMap."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        session.get("https://www.waze.com/live-map", headers=headers, timeout=10)
        print("[SESSION] Cookies initialized successfully.", flush=True)
    except Exception as e:
        print(f"[SESSION Error]: {e}", flush=True)

def send_telegram_alert(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    try:
        session.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[Telegram Error]: {e}", flush=True)

def check_waze():
    print("[WAZE JOB] Fetching LiveMap feed...", flush=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.waze.com/live-map/",
        "X-Requested-With": "XMLHttpRequest"
    }

    try:
        response = session.get(WAZE_URL, headers=headers, timeout=10)
        
        if response.status_code in [403, 401]:
            print(f"[WAZE JOB] Status {response.status_code}. Re-initializing session...", flush=True)
            init_session()
            return

        if response.status_code != 200:
            print(f"[WAZE JOB] Status Error: HTTP {response.status_code}", flush=True)
            return

        data = response.json()
        alerts = data.get("alerts", [])

        print(f"[WAZE JOB] SUCCESS! Found {len(alerts)} items in Dublin.", flush=True)

        for alert in alerts:
            uuid = alert.get("id") or alert.get("uuid")

            if uuid and uuid not in seen_incidents:
                report_type = alert.get("type", "ALERT")
                subtype = alert.get("subtype", "")
                street = alert.get("street", "Unspecified Road")
                city = alert.get("city", "Dublin")
                
                report_rating = alert.get("reportRating", 0)
                reliability = alert.get("reliability", 0)
                confidence = alert.get("confidence", 0)
                n_thumbs_up = alert.get("nThumbsUp", 0)
                road_type = alert.get("roadType", 0)

                location = alert.get("location", {})
                lat = location.get("y")
                lon = location.get("x")

                title = subtype.replace("_", " ").title() if subtype else report_type.title()

                message = (
                    f"🚨 **{title} : {street}, {city}**\n"
                    f"de = Wazer({report_rating}) Rel={reliability} Conf={confidence} ThumbsUp={n_thumbs_up}\n\n"
                    f"🔗 [Vezi pe Livemap](https://www.waze.com/livemap?zoom=17&lat={lat}&lon={lon})\n"
                    f"🚗 [Condu acolo](https://www.waze.com/ul?ll={lat},{lon}&navigate=yes&zoom=17)\n\n"
                    f"`InfoAdditionalRoadType: {road_type}`"
                )

                send_telegram_alert(message)
                seen_incidents.add(uuid)

    except Exception as e:
        print(f"[WAZE JOB] Exception: {e}", flush=True)

init_session()

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(check_waze, 'interval', seconds=60)
scheduler.start()

@app.route("/")
def home():
    return "Dublin Waze Multi-Alert Bot is running 24/7!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
