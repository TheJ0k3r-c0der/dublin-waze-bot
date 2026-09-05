import html
import json
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

app = Flask(__name__)


# -----------------------------------------------------------------------------
# Configurare
# -----------------------------------------------------------------------------

def required_env(name: str) -> str:
    """Returnează o variabilă de mediu obligatorie."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variabila de mediu obligatorie lipsește: {name}")
    return value


# Valorile reale se configurează în Render, nu în GitHub.
BOT_TOKEN = required_env("BOT_TOKEN")
CHAT_ID = required_env("CHAT_ID")
SCRAPINGANT_API_KEY = required_env("SCRAPINGANT_API_KEY")

WAZE_URL = os.getenv(
    "WAZE_URL",
    "https://www.waze.com/live-map/api/georss?top=53.45&bottom=53.20&left=-6.45&right=-6.05&env=row&types=alerts",
).strip()

POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "3"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
TELEGRAM_TIMEOUT_SECONDS = int(os.getenv("TELEGRAM_TIMEOUT_SECONDS", "10"))

SCRAPINGANT_ENDPOINT = "https://api.scrapingant.com/v2/general"
ACCIDENT_TYPE = "ACCIDENT"
DUBLIN_TIMEZONE = ZoneInfo("Europe/Dublin")

# Deduplicare în memorie. După repornirea serviciului, setul se golește.
# Pentru deduplicare persistentă va fi necesară o bază de date SQLite.
seen_incidents: set[str] = set()


# -----------------------------------------------------------------------------
# Utilitare
# -----------------------------------------------------------------------------

def normalize_type(value: Any) -> str:
    """Normalizează tipul incidentului pentru comparație exactă."""
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def escape_html(value: Any) -> str:
    """Protejează valorile introduse într-un mesaj Telegram HTML."""
    return html.escape(str(value if value is not None else ""), quote=True)


def format_report_time(alert: dict[str, Any]) -> str:
    """Returnează ora incidentului în fusul Europe/Dublin.

    Sunt încercate mai multe câmpuri și sunt acceptate timestampuri Unix
    exprimate în secunde sau milisecunde.
    """
    timestamp = (
        alert.get("pubMillis")
        or alert.get("pubMillisUTC")
        or alert.get("reportedAt")
        or alert.get("created")
        or alert.get("time")
    )

    if timestamp is None or timestamp == "":
        return "ora necunoscută"

    try:
        numeric_timestamp = float(timestamp)
        if numeric_timestamp > 10_000_000_000:
            numeric_timestamp /= 1000

        return datetime.fromtimestamp(
            numeric_timestamp,
            tz=DUBLIN_TIMEZONE,
        ).strftime("%H:%M:%S")
    except (TypeError, ValueError, OSError, OverflowError):
        return "ora necunoscută"


def extract_waze_payload(raw_response: str) -> dict[str, Any]:
    """Extrage payloadul JSON Waze din răspunsul ScrapingAnt."""
    try:
        parsed_response = json.loads(raw_response)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed_response, dict):
        return {}

    # Unele răspunsuri pot împacheta conținutul în câmpul content.
    raw_content = parsed_response.get("content")

    if isinstance(raw_content, dict):
        return raw_content

    if isinstance(raw_content, str) and raw_content.strip():
        try:
            parsed_content = json.loads(raw_content)
            if isinstance(parsed_content, dict):
                return parsed_content
        except json.JSONDecodeError:
            pass

    # În cazul răspunsului JSON direct, obiectul conține chiar alerts.
    return parsed_response


def get_alerts(waze_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Returnează alertele într-o formă sigură."""
    alerts = waze_data.get("alerts", [])
    if not isinstance(alerts, list):
        return []
    return [alert for alert in alerts if isinstance(alert, dict)]


# -----------------------------------------------------------------------------
# Telegram
# -----------------------------------------------------------------------------

def send_telegram_alert(text: str) -> bool:
    """Trimite mesajul în canal și verifică răspunsul Telegram."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=TELEGRAM_TIMEOUT_SECONDS,
        )

        if response.status_code != 200:
            print(
                f"[Telegram Error] HTTP {response.status_code}: "
                f"{response.text[:500]}",
                flush=True,
            )
            return False

        result = response.json()
        if not result.get("ok"):
            print(f"[Telegram Error] API response: {result}", flush=True)
            return False

        return True
    except requests.RequestException as exc:
        print(f"[Telegram Error] {exc}", flush=True)
        return False
    except ValueError as exc:
        print(f"[Telegram Error] Răspuns Telegram invalid: {exc}", flush=True)
        return False


# -----------------------------------------------------------------------------
# Formatarea mesajului
# -----------------------------------------------------------------------------

def build_accident_message(alert: dict[str, Any]) -> str:
    """Construiește mesajul în formatul canalului de referință."""
    location = alert.get("location") or {}
    lat = location.get("y")
    lon = location.get("x")

    street = escape_html(alert.get("street") or "Drum nespecificat")
    city = escape_html(alert.get("city") or "Dublin")
    reported_time = format_report_time(alert)

    report_rating = escape_html(alert.get("reportRating", 0))
    reliability = escape_html(alert.get("reliability", 0))
    confidence = escape_html(alert.get("confidence", 0))
    thumbs_up = escape_html(alert.get("nThumbsUp", 0))
    road_type = escape_html(alert.get("roadType", 0))

    if lat is not None and lon is not None:
        safe_lat = escape_html(lat)
        safe_lon = escape_html(lon)

        livemap_url = (
            "https://www.waze.com/ro/livemap"
            f"?zoom=17&lat={safe_lat}&lon={safe_lon}"
        )
        navigation_url = (
            "https://www.waze.com/ul"
            f"?ll={safe_lat},{safe_lon}&navigate=yes&zoom=17"
        )

        livemap_line = (
            "Vezi pe Livemap: "
            f'<a href="{livemap_url}">{livemap_url}</a>'
        )
        navigation_line = (
            "Condu acolo: "
            f'<a href="{navigation_url}">{navigation_url}</a>'
        )
    else:
        livemap_line = "Vezi pe Livemap: coordonate indisponibile"
        navigation_line = "Condu acolo: coordonate indisponibile"

    return (
        f"🚨 <b>Accident : {street}, {city} raportat la {reported_time}</b>\n"
        f"de = Wazer({report_rating}) "
        f"Rel={reliability} "
        f"Conf={confidence} "
        f"ThumbsUp={thumbs_up}\n"
        f"{livemap_line}\n\n"
        f"{navigation_line}\n\n"
        f"InfoAditionalRoadType: {road_type}"
    )


# -----------------------------------------------------------------------------
# Waze și jobul periodic
# -----------------------------------------------------------------------------

def check_waze() -> None:
    print("[WAZE JOB] Se preiau alertele...", flush=True)

    # Endpointul Waze este tratat ca endpoint de date, fără browser headless.
    # browser=false evită detectarea browserului ScrapingAnt de către Waze.
    params = {
        "url": WAZE_URL,
        "x-api-key": SCRAPINGANT_API_KEY,
        "browser": "false",
        "return_page_source": "true",
        "timeout": str(min(max(REQUEST_TIMEOUT_SECONDS, 5), 60)),
    }

    try:
        response = requests.get(
            SCRAPINGANT_ENDPOINT,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS + 5,
        )

        if response.status_code != 200:
            detail = response.text[:1000].replace("\n", " ")
            print(
                f"[WAZE JOB] ScrapingAnt HTTP {response.status_code}: {detail}",
                flush=True,
            )
            return

        waze_data = extract_waze_payload(response.text)
        if not waze_data:
            print(
                "[WAZE JOB] Răspunsul ScrapingAnt nu conține JSON Waze valid.",
                flush=True,
            )
            return

        alerts = get_alerts(waze_data)
        accident_count = 0
        published_count = 0

        for alert in alerts:
            # Filtrare strictă: HAZARD, JAM, POLICE etc. sunt ignorate.
            if normalize_type(alert.get("type")) != ACCIDENT_TYPE:
                continue

            accident_count += 1
            incident_id = str(
                alert.get("uuid") or alert.get("id") or ""
            ).strip()

            if not incident_id:
                print(
                    "[WAZE JOB] Accident fără uuid/id; este ignorat pentru "
                    "a evita duplicatele.",
                    flush=True,
                )
                continue

            if incident_id in seen_incidents:
                continue

            message = build_accident_message(alert)
            if send_telegram_alert(message):
                seen_incidents.add(incident_id)
                published_count += 1
                print(
                    f"[WAZE JOB] Accident publicat: {incident_id}",
                    flush=True,
                )

        print(
            f"[WAZE JOB] Accidente găsite: {accident_count}; "
            f"mesaje publicate: {published_count}; "
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
