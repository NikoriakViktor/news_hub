"""Карта погоди — Streamlit-клієнт до Meteo API v2 (урок 32).

Ідея і «HTTP-інспектор» — з streamlit_app.py викладача (legacy/streamlit_app.py);
тут вони працюють з REST-версією API через MeteoClient.

    uvicorn meteo_api.app:app --port 8032                 # термінал 1: API
    streamlit run weather_map/app.py                      # термінал 2: карта, http://localhost:8501

Адреса API — змінна середовища METEO_API_URL (у Docker Compose: http://api:8032).
"""
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from client import MeteoClient, MeteoError   # noqa: E402

API_URL = os.environ.get("METEO_API_URL", "http://127.0.0.1:8032")
# Діверґентна шкала: холодно (синій) — 0 °C (сірий) — тепло (червоний)
TEMPERATURE_SCALE = [[0.0, "#2a78d6"], [0.5, "#f0efec"], [1.0, "#e34948"]]

st.set_page_config(page_title="Карта погоди | Урок 32", page_icon="🌦️", layout="wide")
st.title("🌦️ Погода на метеостанціях України")
st.caption(f"Дані: телеграми SYNOP з ogimet.com через Meteo API v2 · API: `{API_URL}`")

client = MeteoClient(API_URL)
try:
    latest = pd.DataFrame(client.latest())
except MeteoError as error:
    st.error(f"Не вдалося отримати дані: {error}. Запусти API: `uvicorn meteo_api.app:app --port 8032`")
    st.stop()

tab_map, tab_station, tab_http = st.tabs(["🗺️ Карта", "📈 Станція", "🔍 HTTP-інспектор"])

with tab_map:
    placed = latest.dropna(subset=["lat", "lon", "temperature"])
    if placed.empty:
        st.info("У станцій немає координат — завантаж знімок: `python -m meteo_api.fetch_snapshot`.")
    else:
        limit = max(abs(placed["temperature"].min()), abs(placed["temperature"].max()), 1)
        fig = px.scatter_map(
            placed, lat="lat", lon="lon", color="temperature", text="station_name",
            color_continuous_scale=TEMPERATURE_SCALE, range_color=(-limit, limit),
            hover_name="station_name",
            hover_data={"temperature": ":.1f", "pressure": ":.1f", "wind_speed": True, "time": True,
                        "lat": False, "lon": False},
            labels={"temperature": "t, °C", "pressure": "тиск, гПа", "wind_speed": "вітер, м/с",
                    "time": "строк (UTC)"},
            zoom=4.6, height=560, map_style="open-street-map",
        )
        fig.update_traces(marker={"size": 16}, textposition="top center")
        fig.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0})
        st.plotly_chart(fig, width="stretch")
    st.dataframe(latest[["station", "station_name", "time", "temperature", "pressure", "wind_speed"]],
                 hide_index=True, width="stretch")

with tab_station:
    names = dict(zip(latest["station_name"], latest["station"]))
    name = st.selectbox("Станція", sorted(names))
    history = pd.DataFrame(client.observations(names[name]))
    history["time"] = pd.to_datetime(history["time"])
    # Дві величини з різними одиницями — два графіки, а не дві осі на одному
    for column, title in [("temperature", "Температура, °C"), ("pressure", "Тиск на станції, гПа")]:
        chart = px.line(history, x="time", y=column, markers=True, title=f"{name}: {title}",
                        labels={"time": "строк (UTC)", column: title})
        chart.update_traces(line={"width": 2, "color": "#2a78d6"}, marker={"size": 8})
        st.plotly_chart(chart, width="stretch")

with tab_http:
    st.markdown("Останній запит, який `MeteoClient` надіслав до API, — те саме, що в уроці 31, але з браузера.")
    st.json(client.last_exchange)
