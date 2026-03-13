"""Calibration helpers – load and save calibration values to/from a JSON file."""

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

_DEFAULTS: dict[str, Any] = {
    "temp_amo_offset": 0.0,
    "temp_res_offset": 0.0,
    "raw_pmi": 0.0,
    "raw_pms": 1023.0,
    "stroke_length_mm": 150.0,
    # Force calibration (AD623 or any analog 0-1023 source)
    # calibrated_force = (raw - force_zero_raw) * (force_known_physical_n / (force_known_raw - force_zero_raw))
    "force_zero_raw": 512.0,
    "force_known_raw": 1023.0,
    "force_known_physical_n": 100.0,
}

# Graph axis limit defaults – None means "auto-range"
_GRAPH_DEFAULTS: dict[str, Optional[float]] = {
    "fvr_x_min": None,   # Fuerza vs Recorrido – X axis min (mm)
    "fvr_x_max": None,   # Fuerza vs Recorrido – X axis max (mm)
    "fvr_y_min": None,   # Fuerza vs Recorrido – Y axis min (N)
    "fvr_y_max": None,   # Fuerza vs Recorrido – Y axis max (N)
    "temp_y_min": None,  # Temperaturas vs Tiempo – Y axis min (°C)
    "temp_y_max": None,  # Temperaturas vs Tiempo – Y axis max (°C)
    "dist_y_min": None,  # Distancia vs Tiempo – Y axis min (mm)
    "dist_y_max": None,  # Distancia vs Tiempo – Y axis max (mm)
}


def _read_config() -> dict[str, Any]:
    """Read the full config.json, returning an empty dict on error."""
    if os.path.isfile(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            logger.warning("No se pudo leer config.json: %s", exc)
    return {}


def _write_config(data: dict[str, Any]) -> None:
    """Write *data* to config.json, logging any error."""
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception as exc:
        logger.error("No se pudo escribir config.json: %s", exc)


def load_calibration() -> dict[str, Any]:
    """Return calibration values, falling back to defaults for any missing key."""
    result = dict(_DEFAULTS)
    stored = _read_config()
    for key in _DEFAULTS:
        if key in stored:
            try:
                result[key] = float(stored[key])
            except (TypeError, ValueError):
                pass
    if stored:
        logger.debug("Calibración cargada desde %s", _CONFIG_PATH)
    return result


def save_calibration(values: dict[str, Any]) -> None:
    """Persist calibration *values* to disk, preserving other config sections."""
    existing = _read_config()
    for key in _DEFAULTS:
        existing[key] = float(values.get(key, _DEFAULTS[key]))
    _write_config(existing)
    logger.debug("Calibración guardada en %s", _CONFIG_PATH)


def load_graph_settings() -> dict[str, Optional[float]]:
    """Return graph axis limit settings, falling back to None (auto-range) for any missing key."""
    result: dict[str, Optional[float]] = dict(_GRAPH_DEFAULTS)
    stored = _read_config()
    graph_section = stored.get("graph_limits", {})
    if isinstance(graph_section, dict):
        for key in _GRAPH_DEFAULTS:
            if key in graph_section:
                val = graph_section[key]
                if val is None:
                    result[key] = None
                else:
                    try:
                        result[key] = float(val)
                    except (TypeError, ValueError):
                        pass
    return result


def save_graph_settings(settings: dict[str, Optional[float]]) -> None:
    """Persist graph axis limit settings under the 'graph_limits' key in config.json."""
    existing = _read_config()
    to_save: dict[str, Optional[float]] = {}
    for key in _GRAPH_DEFAULTS:
        val = settings.get(key)
        if val is None:
            to_save[key] = None
        else:
            try:
                to_save[key] = float(val)
            except (TypeError, ValueError):
                to_save[key] = None
    existing["graph_limits"] = to_save
    _write_config(existing)
    logger.debug("Configuración de gráficos guardada en %s", _CONFIG_PATH)
