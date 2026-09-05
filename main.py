import os
import requests
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

BOT_TOKEN = "8744802014:AAGkTNyb4RC_LfG0grxr2j01BsJ8xkCtg2c"
CHAT_ID = "-1004349956233"

# Endpoint-ul intern Waze fără protecție anti-bot Cloudflare
WAZE_URL = (
    "https://www.waze.com/row-rtserver/web/TGeoRSS"
    "?left=-6.45&right=-6.05&bottom=53.20&top=53.45"
    "&ma=600&mj=100&mu=100"
)

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
    print("[WAZE JOB] Fetching row-rtserver feed...", flush=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://www.waze.com/live-map/",
    }

    try:
        response = requests.get(WAZE_URL, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"[WAZE JOB] Status Error: HTTP {response.status_code}", flush=True)
            return

        data = response.json()
        alerts = data.get("alerts", [])

        print(f"[WAZE JOB] SUCCESS! Found {len(alerts)} items in Dublin area.", flush=True)

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

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(check_waze, 'interval', seconds=60)
scheduler.start()

@app.route("/")
def home():
    return "Dublin Waze Multi-Alert Bot is running 24/7!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
