import os
import json
import requests
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

BOT_TOKEN = "8744802014:AAGkTNyb4RC_LfG0grxr2j01BsJ8xkCtg2c"
CHAT_ID = "-1004349956233"

# Cheia ta ScrapingAnt
SCRAPINGANT_API_KEY = "3a79ecac33a64c3aab256e9bf39656c1"

WAZE_URL = "https://www.waze.com/live-map/api/georss?top=53.45&bottom=53.20&left=-6.45&right=-6.05&env=row&types=alerts"

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
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[Telegram Error]: {e}", flush=True)

def check_waze():
    print("[WAZE JOB] Fetching via ScrapingAnt Proxy...", flush=True)

    # Configurare compatibilă cu planul gratuit ScrapingAnt
    proxy_endpoint = "https://api.scrapingant.com/v2/general"
    params = {
        "api_key": SCRAPINGANT_API_KEY,
        "url": WAZE_URL,
        "browser_scanner": "true"
    }

    try:
        response = requests.get(proxy_endpoint, params=params, timeout=30)

        if response.status_code != 200:
            print(f"[WAZE JOB] Status Error: HTTP {response.status_code}", flush=True)
            return

        data = response.json()
        raw_content = data.get("content", "")

        # Preluăm datele extrase din pagina Waze
        try:
            waze_data = json.loads(raw_content)
        except Exception:
            waze_data = data

        alerts = waze_data.get("alerts", [])
        print(f"[WAZE JOB] SUCCESS! Received {len(alerts)} alerts in Dublin.", flush=True)

        for alert in alerts:
            uuid = alert.get("uuid") or alert.get("id")

            if uuid and uuid not in seen_incidents:
                report_type = alert.get("type", "HAZARD")
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

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(check_waze, 'interval', minutes=3)
scheduler.start()

@app.route("/")
def home():
    return "Dublin Waze Multi-Alert Bot is running 24/7!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
