# Дані Meteo API

- `synop_sample.csv`, `stations_sample.csv` — фікстура для тестів: одна справжня телеграма станції 34504 (Дніпро) за 02.09.2024 18:00 UTC з документації першої версії API (репозиторій `NikoriakViktor/ogimet`). Координати — з `stations_ua.csv`.
- `stations_ua.csv` — 12 українських станцій WMO з координатами й висотою зі списку станцій NOAA ISD
  (`isd-history.csv`, колонки `LAT`, `LON`, `ELEV(M)`). Лежить у репозиторії.
- `synop_ua.csv` — знімок телеграм з ogimet.com, який робить `../fetch_snapshot.py` (формат рядка `getsynop`:
  `станція,рік,місяць,день,година,хвилина,телеграма`). Є цей файл — `MeteoRepository.default()` бере його разом зі
  `stations_ua.csv`; немає — фікстуру.
