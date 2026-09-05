import json
import os
from typing import Any

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

app = Flask(__name__)


def required_env(name: str) -> str:
    """Returnează o variabilă obligatorie sau oprește aplicația cu un mesaj clar."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variabila de mediu obligatorie lipsește: {name}")
    return value


BOT_TOKEN = required_env("8744802014:AAGkTNyb4RC_LfG0grxr2j01BsJ8xkCtg2c")
CHAT_ID = required_env("-1004349956233")
SCRAPINGANT_API_KEY = required_env("3a79ecac33a64c3aab256e9bf39656c1")

WAZE_URL = os.getenv(
    "WAZE_URL",
    "https://www.waze.com/live-map/api/georss?top=53.45&bottom=53.20&left=-6.45&right=-6.05&env=row&types=alerts",
).strip()

POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "3"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
TELEGRAM_TIMEOUT_SECONDS = int(os.getenv("TELEGRAM_TIMEOUT_SECONDS", "10"))

SCRAPINGANT_ENDPOINT = "https://api.scrapingant.com/v2/general"

# Doar tipul ACCIDENT este acceptat. Nu folosim subtype pentru a transforma
# alte alerte, precum HAZARD sau JAM, în accidente.
ACCIDENT_TYPE = "ACCIDENT"

# Păstrat în memorie pentru compatibilitate cu versiunea inițială.
# Pentru deduplicare persistentă după restart, folosește o bază de date.
seen_incidents: set[str] = set()


def normalize_type(value: Any) -> str:
    """Normalizează tipul primit de la Waze pentru comparația strictă."""
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def send_telegram_alert(text: str) -> bool:
    """Trimite un mesaj Telegram și raportează explicit succesul sau eroarea."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        # HTML evită multe probleme cauzate de caractere speciale din numele drumurilor.
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=TELEGRAM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()

        if not result.get("ok"):
            print(f"[Telegram Error] API response: {result}", flush=True)
            return False

        return True
    except requests.RequestException as exc:
        print(f"[Telegram Error] {exc}", flush=True)
        return False
    except ValueError as exc:
        print(f"[Telegram Error] Răspuns JSON invalid: {exc}", flush=True)
        return False


def escape_html(value: Any) -> str:
    """Escape minimal pentru textul introdus într-un mesaj Telegram HTML."""
    text = str(value or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def extract_waze_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Încearcă să extragă JSON-ul Waze din răspunsul ScrapingAnt."""
    raw_content = data.get("content", "")

    if isinstance(raw_content, dict):
        return raw_content

    if isinstance(raw_content, str) and raw_content.strip():
        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return data


def build_accident_message(alert: dict[str, Any]) -> str:
    location = alert.get("location") or {}
    lat = location.get("y")
    lon = location.get("x")

    street = escape_html(alert.get("street") or "Drum nespecificat")
    city = escape_html(alert.get("city") or "Dublin")
    subtype = escape_html(alert.get("subtype") or "")

    # Linkurile se construiesc doar când Waze a furnizat coordonate valide.
    links = ""
    if lat is not None and lon is not None:
        safe_lat = escape_html(lat)
        safe_lon = escape_html(lon)
        links = (
            f"\n🔗 <a href=\"https://www.waze.com/live-map?zoom=17&lat={safe_lat}&lon={safe_lon}\">"
            "Vezi pe Live Map</a>"
            f"\n🚗 <a href=\"https://www.waze.com/ul?ll={safe_lat},{safe_lon}&navigate=yes&zoom=17\">"
            "Condu acolo</a>"
        )

    subtype_line = f"\nTip: {subtype}" if subtype else ""

    return (
        f"🚨 <b>Accident raportat: {street}, {city}</b>"
        f"{subtype_line}\n"
        f"Sursă: Waze"
        f"{links}"
    )


def check_waze() -> None:
    print("[WAZE JOB] Se preiau alertele...", flush=True)

    params = {
        "api_key": SCRAPINGANT_API_KEY,
        "url": WAZE_URL,
        "browser_scanner": "true",
    }

    try:
        response = requests.get(
            SCRAPINGANT_ENDPOINT,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        data = response.json()
        waze_data = extract_waze_payload(data)
        alerts = waze_data.get("alerts", [])

        if not isinstance(alerts, list):
            print("[WAZE JOB] Format neașteptat: alerts nu este listă.", flush=True)
            return

        accident_count = 0

        for alert in alerts:
            if not isinstance(alert, dict):
                continue

            # Filtrare strictă: orice tip diferit de ACCIDENT este ignorat.
            report_type = normalize_type(alert.get("type"))
            if report_type != ACCIDENT_TYPE:
                continue

            accident_count += 1
            incident_id = str(alert.get("uuid") or alert.get("id") or "").strip()
            if not incident_id:
                print("[WAZE JOB] Accident fără ID, ignorat pentru a evita duplicatele.", flush=True)
                continue

            if incident_id in seen_incidents:
                continue

            message = build_accident_message(alert)
            if send_telegram_alert(message):
                seen_incidents.add(incident_id)
                print(f"[WAZE JOB] Accident publicat: {incident_id}", flush=True)

        print(
            f"[WAZE JOB] Au fost găsite {accident_count} accidente; "
            f"alerte totale: {len(alerts)}.",
            flush=True,
        )

    except requests.RequestException as exc:
        print(f"[WAZE JOB] Eroare HTTP: {exc}", flush=True)
    except (ValueError, TypeError, KeyError) as exc:
        print(f"[WAZE JOB] Răspuns Waze invalid: {exc}", flush=True)
    except Exception as exc:
        print(f"[WAZE JOB] Excepție neașteptată: {exc}", flush=True)


scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(
    check_waze,
    "interval",
    minutes=POLL_INTERVAL_MINUTES,
    id="waze_poll",
    max_instances=1,
    coalesce=True,
)
scheduler.start()


@app.route("/")
def home() -> str:
    return "Dublin Waze Accident Bot is running!"


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
