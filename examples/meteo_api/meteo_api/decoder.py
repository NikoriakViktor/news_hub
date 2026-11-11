"""Розкодування синоптичних телеграм SYNOP (КН-01).

Спрощена версія TelegramMeteoDecoder з проєкту викладача
(https://github.com/NikoriakViktor/ogimet, telegram_decode/class_metedecode.py).
Сам розбір коду робить бібліотека pymetdecoder.
"""
import math

from pymetdecoder import synop


def _get(data, *keys):
    """Безпечно дістати значення з вкладеного словника: _get(d, "surface_wind", "speed", "value")."""
    for key in keys:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def relative_humidity(temperature, dew_point):
    """Відносна вологість (%) за температурою і точкою роси — формула Магнуса."""
    if temperature is None or dew_point is None:
        return None
    return round(100 * math.exp(17.62 * dew_point / (243.12 + dew_point)
                                - 17.62 * temperature / (243.12 + temperature)))


def decode_synop(telegram):
    """Телеграма 'AAXX 02181 34504 …' → словник з основними величинами або None."""
    try:
        data = synop.SYNOP().decode(telegram.strip().rstrip("="))
    except Exception:           # бібліотека кидає різні винятки на пошкоджені телеграми
        return None
    temperature = _get(data, "air_temperature", "value")
    dew_point = _get(data, "dewpoint_temperature", "value")
    return {
        "temperature": temperature,
        "dew_point": dew_point,
        "relative_humidity": relative_humidity(temperature, dew_point),
        "wind_dir": _get(data, "surface_wind", "direction", "value"),
        "wind_speed": _get(data, "surface_wind", "speed", "value"),
        "pressure": _get(data, "station_pressure", "value"),
        "sea_level_pressure": _get(data, "sea_level_pressure", "value"),
        "max_temperature": _get(data, "maximum_temperature", "value"),
        "min_temperature": _get(data, "minimum_temperature", "value"),
    }
