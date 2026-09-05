import os
import requests
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

BOT_TOKEN = "8744802014:AAGkTNyb4RC_LfG0grxr2j01BsJ8xkCtg2c"
CHAT_ID = "-1004349956233"

# Pune AICI cheia ta de la ScrapingAnt
SCRAPINGANT_API_KEY = "PUNE_AICI_API_KEY_DE_LA_SCRAPINGANT"

WAZE_URL = "https://www.waze.com/live-map/api/georss?top=53.45&bottom=53.20&left=-6.45&right=-6.05&env=row&types=alerts"
PROXY_ENDPOINT = f"https://api.scrapingant.com/v2/general?api_key={SCRAPINGANT_API_KEY}&url={requests.utils.quote(WAZE_URL)}&proxy_type=residential"

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
    print("[WAZE JOB] Fetching via Residential Proxy...", flush=True)

    try:
        response = requests.get(PROXY_ENDPOINT, timeout=20)

        if response.status_code != 200:
            print(f"[WAZE JOB] Status Error: HTTP {response.status_code}", flush=True)
            return

        data = response.json()
        alerts = data.get("alerts", [])
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

# Schimbăm la 3 minute pentru a încadra cererile în limita gratuită lunară
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(check_waze, 'interval', minutes=3)
scheduler.start()

@app.route("/")
def home():
    return "Dublin Waze Multi-Alert Bot is running 24/7!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
