"""Завантажити знімок телеграм SYNOP з ogimet.com для станцій уроку.

Логіка — з TelegramProcessor.get_station_data проєкту викладача
(https://github.com/NikoriakViktor/ogimet), виправлена за уроком 31:
тайм-аут, перевірка статусу, пауза між запитами, чесний User-Agent замість fake_useragent.

    python -m meteo_api.fetch_snapshot --days 3        # → meteo_api/data/synop_ua.csv
"""
import argparse
import time
from datetime import datetime, timedelta, timezone

import requests

from .storage import DATA_DIR

GETSYNOP_URL = "https://www.ogimet.com/cgi-bin/getsynop"
# Станції зі streamlit_app.py викладача: назва → WMO-індекс
STATIONS_UA = {
    "Київ": "33345", "Харків": "34300", "Дніпро": "34504", "Львів": "33393",
    "Полтава": "33506", "Одеса": "33837", "Чернігів": "33135", "Суми": "33275",
    "Рівне": "33301", "Житомир": "33325", "Тернопіль": "33415", "Хмельницький": "33429",
}
HEADERS = {"User-Agent": "py-course-lesson-32 (educational; github.com/NikoriakViktor)"}


def fetch_station(session, wmo, begin, end):
    """Рядки CSV однієї станції: 33345,2026,09,25,18,00,AAXX …="""
    params = {"block": wmo, "begin": f"{begin:%Y%m%d%H%M}", "end": f"{end:%Y%m%d%H%M}"}
    response = session.get(GETSYNOP_URL, params=params, headers=HEADERS, timeout=(5, 60))
    response.raise_for_status()
    return [line for line in response.text.splitlines() if line.startswith(wmo + ",")]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--pause", type=float, default=3.0, help="секунд між запитами — не перевантажуємо ogimet")
    args = parser.parse_args()

    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    begin = end - timedelta(days=args.days)
    lines = []
    with requests.Session() as session:
        for name, wmo in STATIONS_UA.items():
            station_lines = fetch_station(session, wmo, begin, end)
            print(f"{name:13} {wmo}: {len(station_lines)} телеграм")
            lines += station_lines
            time.sleep(args.pause)
    out = DATA_DIR / "synop_ua.csv"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"збережено {len(lines)} рядків у {out}")


if __name__ == "__main__":
    main()
