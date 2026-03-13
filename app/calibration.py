"""Calibration helpers – load and save calibration values to/from a JSON file."""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

_DEFAULTS: dict[str, Any] = {
    "temp_amo_offset": 0.0,
    "temp_res_offset": 0.0,
    "raw_pmi": 0.0,
    "raw_pms": 1023.0,
    "stroke_length_mm": 150.0,
    "force_zero_raw": 0.0,
    "force_known_raw": 1.0,
    "force_known_physical": 98.1,
}


def load_calibration() -> dict[str, Any]:
    """Return calibration values, falling back to defaults for any missing key."""
    result = dict(_DEFAULTS)
    if os.path.isfile(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            for key in _DEFAULTS:
                if key in stored:
                    result[key] = float(stored[key])
            logger.debug("Calibración cargada desde %s", _CONFIG_PATH)
        except Exception as exc:
            logger.warning("No se pudo leer config.json: %s", exc)
    return result


def save_calibration(values: dict[str, Any]) -> None:
    """Persist calibration *values* to disk (only known keys are written)."""
    to_save = {key: float(values.get(key, _DEFAULTS[key])) for key in _DEFAULTS}
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(to_save, fh, indent=2)
        logger.debug("Calibración guardada en %s", _CONFIG_PATH)
    except Exception as exc:
        logger.error("No se pudo guardar config.json: %s", exc)
