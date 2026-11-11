"""Сховище метеоданих у пам'яті: станції і спостереження.

Шар «репозиторій» (урок 29): API нічого не знає, звідки дані, — зі знімка CSV,
MongoDB чи PostgreSQL. Щоб перейти на базу, замінюють лише цей клас.
"""
import csv
import threading
from datetime import datetime, timezone
from pathlib import Path

from .decoder import decode_synop

DATA_DIR = Path(__file__).parent / "data"


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


def parse_time(value):
    """'2024-09-02T18:00Z' / '2024-09-02T18:00:00+00:00' → datetime у UTC."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def format_time(moment):
    return moment.strftime("%Y-%m-%dT%H:%MZ")


def parse_ogimet_csv(lines):
    """Рядки у форматі ogimet getsynop → список сирих записів.

    Формат рядка: 33345,2024,09,02,18,00,AAXX 02181 33345 …=
    """
    records = []
    for row in csv.reader(line for line in lines if line.strip()):
        wmo, year, month, day, hour, minute, telegram = row[:7]
        moment = datetime(int(year), int(month), int(day), int(hour), int(minute), tzinfo=timezone.utc)
        records.append({"station": wmo, "time": moment, "telegram": telegram.strip()})
    return records


class MeteoRepository:
    def __init__(self, stations=(), observations=()):
        self._lock = threading.Lock()
        self._stations = {s["wmo"]: dict(s) for s in stations}
        self._observations = {}                 # (wmo, datetime) → dict
        for obs in observations:
            self._observations[(obs["station"], obs["time"])] = dict(obs)

    # ---------- завантаження ----------
    @classmethod
    def from_files(cls, stations_csv, synop_csv):
        with open(stations_csv, encoding="utf-8") as f:
            stations = [
                {"wmo": row["wmo"], "name": row["name"],
                 "lat": float(row["lat"]) if row["lat"] else None,
                 "lon": float(row["lon"]) if row["lon"] else None,
                 "elevation": float(row["elevation"]) if row["elevation"] else None}
                for row in csv.DictReader(f)
            ]
        repo = cls(stations)
        with open(synop_csv, encoding="utf-8") as f:
            repo.import_records(parse_ogimet_csv(f))
        return repo

    @classmethod
    def default(cls):
        """Знімок даних уроку, а якщо його ще немає — маленька фікстура для тестів."""
        if (DATA_DIR / "stations_ua.csv").exists():
            return cls.from_files(DATA_DIR / "stations_ua.csv", DATA_DIR / "synop_ua.csv")
        return cls.from_files(DATA_DIR / "stations_sample.csv", DATA_DIR / "synop_sample.csv")

    def import_records(self, records):
        """Розкодувати й зберегти телеграми; повертає (додано, пропущено)."""
        added = skipped = 0
        for record in records:
            values = decode_synop(record["telegram"])
            if values is None or record["station"] not in self._stations:
                skipped += 1
                continue
            with self._lock:
                self._observations[(record["station"], record["time"])] = {**record, **values}
            added += 1
        return added, skipped

    # ---------- станції ----------
    def list_stations(self):
        return sorted(self._stations.values(), key=lambda s: s["wmo"])

    def add_station(self, wmo, name, lat=None, lon=None, elevation=None):
        with self._lock:
            if wmo in self._stations:
                raise ConflictError(f"станція {wmo} вже є")
            self._stations[wmo] = {"wmo": wmo, "name": name, "lat": lat, "lon": lon, "elevation": elevation}
        return self._stations[wmo]

    def get_station(self, wmo):
        try:
            return self._stations[wmo]
        except KeyError:
            raise NotFoundError(f"станцію {wmo} не знайдено") from None

    # ---------- спостереження ----------
    def list_observations(self, wmo, date_from=None, date_to=None, hour=None):
        self.get_station(wmo)
        items = [obs for (station, moment), obs in self._observations.items()
                 if station == wmo
                 and (date_from is None or moment >= date_from)
                 and (date_to is None or moment <= date_to)
                 and (hour is None or moment.hour == hour)]
        return sorted(items, key=lambda obs: obs["time"])

    def latest(self):
        """Останнє спостереження кожної станції, в якої вони є."""
        newest = {}
        for (station, moment), obs in self._observations.items():
            if station not in newest or moment > newest[station]["time"]:
                newest[station] = obs
        return [newest[wmo] for wmo in sorted(newest)]

    def get_observation(self, wmo, moment):
        self.get_station(wmo)
        try:
            return self._observations[(wmo, moment)]
        except KeyError:
            raise NotFoundError(f"спостереження {wmo} на {format_time(moment)} немає") from None

    def add_observation(self, obs):
        self.get_station(obs["station"])
        key = (obs["station"], obs["time"])
        with self._lock:
            if key in self._observations:
                raise ConflictError(f"спостереження {obs['station']} на {format_time(obs['time'])} вже є")
            self._observations[key] = dict(obs)
        return self._observations[key]

    def update_observation(self, wmo, moment, changes):
        obs = self.get_observation(wmo, moment)
        with self._lock:
            obs.update(changes)
        return obs

    def delete_observation(self, wmo, moment):
        self.get_observation(wmo, moment)
        with self._lock:
            del self._observations[(wmo, moment)]
