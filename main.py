import os
import requests
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
import WazeRouteCalculator

app = Flask(__name__)

BOT_TOKEN = "8744802014:AAGkTNyb4RC_LfG0grxr2j01BsJ8xkCtg2c"
CHAT_ID = "-1004349956233"

# Bounding Box Dublin pentru API-ul mobil
WAZE_ROUTING_URL = "https://www.waze.com/RoutingManager/routingRequest"

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
    print("[WAZE JOB] Querying Waze Routing Engine...", flush=True)

    # Coordonate cheie Dublin (O'Connell St -> M50 Interchange)
    # Folosirea motorului de rutare forțează API-ul mobil să returneze toate alertele active pe traseu/zonă
    from_lat, from_lon = 53.3498, -6.2603
    to_lat, to_lon = 53.3900, -6.1500

    try:
        route = WazeRouteCalculator.WazeRouteCalculator(
            f"{from_lat},{from_lon}", 
            f"{to_lat},{to_lon}", 
            region='EU'
        )
        
        # Generăm o cerere de rutare care returnează toate incidentele din jur
        params = {
            "from": f"x:{from_lon} y:{from_lat}",
            "to": f"x:{to_lon} y:{to_lat}",
            "at": "0",
            "returnJSON": "true",
            "returnGeometries": "true",
            "returnInstructions": "true",
            "timeout": "60000",
            "nPaths": "3",
            "options": "AVOID_TRAFFIC:f"
        }
        
        headers = {
            "User-Agent": "Android-Waze/4.90.0.0",
            "Referer": "https://www.waze.com/"
        }

        response = requests.get(WAZE_ROUTING_URL, params=params, headers=headers, timeout=10)

        if response.status_code != 200:
            print(f"[WAZE JOB] Status Error: HTTP {response.status_code}", flush=True)
            return

        data = response.json()
        
        # Alertele vin în răspunsul de rutare direct sub cheia 'alerts' sau 'alternatives'
        alerts = []
        if "response" in data and "alerts" in data["response"]:
            alerts = data["response"]["alerts"]
        
        print(f"[WAZE JOB] SUCCESS! Connection active. Found {len(alerts)} alerts on main corridor.", flush=True)

        for alert in alerts:
            uuid = alert.get("id") or alert.get("uuid")

            if uuid and uuid not in seen_incidents:
                report_type = alert.get("type", "ALERT")
                subtype = alert.get("subtype", "")
                street = alert.get("street", "Dublin Road")
                
                location = alert.get("location", {})
                lat = location.get("y")
                lon = location.get("x")

                title = subtype.replace("_", " ").title() if subtype else report_type.title()

                message = (
                    f"🚨 **{title} : {street}, Dublin**\n\n"
                    f"🔗 [Vezi pe Livemap](https://www.waze.com/livemap?zoom=17&lat={lat}&lon={lon})\n"
                    f"🚗 [Condu acolo](https://www.waze.com/ul?ll={lat},{lon}&navigate=yes&zoom=17)"
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
