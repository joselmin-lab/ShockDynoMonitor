"""
Módulo: data_parser.py
Descripción: Conversión de los 128 bytes de payload de la ECU Speeduino
             a valores físicos calibrados para el banco de pruebas de amortiguadores.

Offsets validados mediante captura real (2026-03-12):
    Offset 0: secCounter (ignorar)
    Offset 1: MAP raw → Fuerza (N) = raw / 2.0
    Offset 2: TPS raw → Recorrido (mm) = (raw / 255.0) * 100
    Offset 3: CLT raw → Temp Amortiguador (°C) = raw - 40
    Offset 4: IAT raw → Temp Reservorio (°C) = raw - 40
    Offsets 5-6: RPM uint16 big-endian → Velocidad (RPM) = (byte5 << 8) | byte6
"""

import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Logger del módulo
logger = logging.getLogger(__name__)


@dataclass
class ShockDynoData:
    """
    Dataclass que representa una lectura completa de los 5 sensores del banco
    de pruebas de amortiguadores.

    Attributes:
        timestamp: Marca de tiempo de la lectura (datetime con microsegundos).
        fuerza_n: Fuerza medida en Newtons (N). Rango típico: 0-3000 N.
        recorrido_mm: Recorrido del amortiguador en milímetros (mm).
                      Rango: 0-100 mm.
        temp_amortiguador_c: Temperatura del cuerpo del amortiguador en °C.
                              Rango: -40 a 215 °C.
        temp_reservorio_c: Temperatura del reservorio de aceite en °C.
                           Rango: -40 a 215 °C.
        velocidad_rpm: Velocidad de ciclo en RPM. Rango: 0-9999 RPM.
        valido: True si los datos fueron parseados correctamente.

    Ejemplo::

        dato = ShockDynoData(
            timestamp=datetime.now(),
            fuerza_n=1250.0,
            recorrido_mm=45.5,
            temp_amortiguador_c=38.0,
            temp_reservorio_c=32.0,
            velocidad_rpm=120,
        )
    """
    timestamp: datetime = field(default_factory=datetime.now)
    fuerza_n: float = 0.0
    recorrido_mm: float = 0.0
    temp_amortiguador_c: float = 0.0
    temp_reservorio_c: float = 0.0
    velocidad_rpm: int = 0
    valido: bool = True

    def to_dict(self) -> dict:
        """
        Convierte la lectura a un diccionario para logging o exportación.

        Returns:
            Diccionario con todos los campos de la lectura.
        """
        return {
            "Timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "Fuerza_N": round(self.fuerza_n, 2),
            "Recorrido_mm": round(self.recorrido_mm, 2),
            "Temp_Amortiguador_C": round(self.temp_amortiguador_c, 1),
            "Temp_Reservorio_C": round(self.temp_reservorio_c, 1),
            "Velocidad_RPM": self.velocidad_rpm,
        }


class SpeeduinoDataParser:
    """
    Clase que convierte los 128 bytes del payload de la ECU Speeduino
    a valores físicos calibrados para los sensores del banco de pruebas.

    Los offsets y conversiones fueron validados con capturas reales el 2026-03-12.

    Offsets de payload:
        - 0: secCounter (contador de segundos, ignorado)
        - 1: MAP (Fuerza) → raw / 2.0 = Newtons
        - 2: TPS (Recorrido) → (raw / 255.0) * 100 = mm
        - 3: CLT (Temp Amortiguador) → raw - 40 = °C
        - 4: IAT (Temp Reservorio) → raw - 40 = °C
        - 5-6: RPM (Velocidad) → (byte5 << 8) | byte6 = RPM (big-endian)

    Ejemplo de uso::

        parser = SpeeduinoDataParser()
        payload = bytes(128)  # 128 bytes del payload de la ECU
        datos = parser.parsear(payload)
        if datos.valido:
            print(f"Fuerza: {datos.fuerza_n:.1f} N")
            print(f"Recorrido: {datos.recorrido_mm:.1f} mm")
    """

    # Offsets validados dentro del payload de 128 bytes
    OFFSET_SEC_COUNTER = 0      # Contador de segundos (ignorar)
    OFFSET_MAP_FUERZA = 1       # MAP → Fuerza (N)
    OFFSET_TPS_RECORRIDO = 2    # TPS → Recorrido (mm)
    OFFSET_CLT_TEMP_AMO = 3     # CLT → Temp Amortiguador (°C)
    OFFSET_IAT_TEMP_RES = 4     # IAT → Temp Reservorio (°C)
    OFFSET_RPM_HIGH = 5         # RPM byte alto (big-endian)
    OFFSET_RPM_LOW = 6          # RPM byte bajo (big-endian)

    # Longitud mínima esperada del payload
    LONGITUD_MINIMA_PAYLOAD = 7

    def __init__(self, config: Optional[dict] = None) -> None:
        """
        Inicializa el parser con configuración opcional de calibración.

        Args:
            config: Diccionario de configuración con escalas y offsets.
                    Si es None, usa los valores por defecto del protocolo.

        Ejemplo::

            # Con calibración por defecto
            parser = SpeeduinoDataParser()

            # Con calibración personalizada
            parser = SpeeduinoDataParser(config={
                "sensores": {
                    "fuerza": {"escala": 0.5, "offset_valor": 0.0}
                }
            })
        """
        self._config = config or {}
        self._cfg_sensores = self._config.get("sensores", {})
        logger.debug("SpeeduinoDataParser inicializado.")

    def actualizar_config(self, nueva_config: dict) -> None:
        """
        Actualiza la configuración de calibración en tiempo real.

        Permite cambiar escalas y offsets de los sensores sin reiniciar
        el parser. Los cambios se aplican a partir de la próxima llamada
        a :meth:`parsear`.

        Args:
            nueva_config: Diccionario con la nueva configuración completa.
                          Se usa la clave ``"sensores"`` para los parámetros
                          de calibración de cada sensor.

        Ejemplo::

            parser.actualizar_config({
                "sensores": {
                    "fuerza": {"escala": 0.5, "offset_valor": -150.0},
                    "recorrido": {"escala": 0.45, "offset_valor": -5.0},
                }
            })
        """
        self._config = nueva_config or {}
        self._cfg_sensores = self._config.get("sensores", {})
        logger.info("Calibración del parser actualizada.")

    def _obtener_escala_offset(
        self, nombre_sensor: str, escala_default: float, offset_default: float
    ) -> tuple:
        """
        Obtiene la escala y offset de calibración para un sensor.

        Primero busca en la configuración cargada, y si no está, usa los
        valores por defecto del protocolo validado.

        Args:
            nombre_sensor: Clave del sensor en config["sensores"].
            escala_default: Escala por defecto del protocolo.
            offset_default: Offset por defecto del protocolo.

        Returns:
            Tupla (escala: float, offset: float).
        """
        cfg = self._cfg_sensores.get(nombre_sensor, {})
        escala = cfg.get("escala", escala_default)
        offset = cfg.get("offset_valor", offset_default)
        return escala, offset

    def parsear(self, payload: bytes) -> ShockDynoData:
        """
        Convierte el payload de 128 bytes de la ECU a datos físicos calibrados.

        Aplica las conversiones validadas para cada sensor:
        - Fuerza: raw / 2.0
        - Recorrido: (raw / 255.0) * 100
        - Temp Amortiguador: raw - 40
        - Temp Reservorio: raw - 40
        - Velocidad: (byte_high << 8) | byte_low  (big-endian)

        Args:
            payload: Bytes del payload (mínimo 7 bytes, típicamente 128 bytes).

        Returns:
            ShockDynoData con los valores físicos calculados y timestamp actual.
            Si el payload es inválido, retorna ShockDynoData con valido=False.

        Ejemplo::

            parser = SpeeduinoDataParser()
            # Payload de ejemplo con valores conocidos
            payload = bytearray(128)
            payload[1] = 200   # MAP raw → Fuerza = 200/2.0 = 100 N
            payload[2] = 128   # TPS raw → Recorrido = (128/255)*100 ≈ 50.2 mm
            payload[3] = 80    # CLT raw → Temp Amo = 80-40 = 40 °C
            payload[4] = 70    # IAT raw → Temp Res = 70-40 = 30 °C
            payload[5] = 0     # RPM high byte
            payload[6] = 120   # RPM low byte → Velocidad = 120 RPM
            datos = parser.parsear(bytes(payload))
            # datos.fuerza_n == 100.0
            # datos.recorrido_mm ≈ 50.2
            # datos.temp_amortiguador_c == 40.0
            # datos.temp_reservorio_c == 30.0
            # datos.velocidad_rpm == 120
        """
        # Marcar tiempo de la lectura
        ahora = datetime.now()

        # Validar longitud mínima del payload
        if len(payload) < self.LONGITUD_MINIMA_PAYLOAD:
            logger.error(
                f"Payload demasiado corto: {len(payload)} bytes "
                f"(mínimo {self.LONGITUD_MINIMA_PAYLOAD})"
            )
            return ShockDynoData(timestamp=ahora, valido=False)

        try:
            # --- Fuerza (N) ---
            # MAP raw (offset 1): raw / 2.0 = Newtons
            escala_fuerza, offset_fuerza = self._obtener_escala_offset(
                "fuerza", 0.5, 0.0
            )
            mapa_raw = payload[self.OFFSET_MAP_FUERZA]
            fuerza_n = (mapa_raw * escala_fuerza) + offset_fuerza

            # --- Recorrido (mm) ---
            # TPS raw (offset 2): (raw / 255.0) * 100 = mm (porcentaje de rango)
            escala_recorrido, offset_recorrido = self._obtener_escala_offset(
                "recorrido", 0.392157, 0.0
            )
            tps_raw = payload[self.OFFSET_TPS_RECORRIDO]
            recorrido_mm = (tps_raw * escala_recorrido) + offset_recorrido

            # --- Temperatura Amortiguador (°C) ---
            # CLT raw (offset 3): raw - 40 = °C
            escala_temp_amo, offset_temp_amo = self._obtener_escala_offset(
                "temp_amortiguador", 1.0, -40.0
            )
            clt_raw = payload[self.OFFSET_CLT_TEMP_AMO]
            temp_amortiguador_c = (clt_raw * escala_temp_amo) + offset_temp_amo

            # --- Temperatura Reservorio (°C) ---
            # IAT raw (offset 4): raw - 40 = °C
            escala_temp_res, offset_temp_res = self._obtener_escala_offset(
                "temp_reservorio", 1.0, -40.0
            )
            iat_raw = payload[self.OFFSET_IAT_TEMP_RES]
            temp_reservorio_c = (iat_raw * escala_temp_res) + offset_temp_res

            # --- Velocidad (RPM) ---
            # RPM uint16 big-endian (offsets 5-6): (byte_high << 8) | byte_low
            rpm_high = payload[self.OFFSET_RPM_HIGH]
            rpm_low = payload[self.OFFSET_RPM_LOW]
            velocidad_rpm = (rpm_high << 8) | rpm_low

            logger.debug(
                f"Datos parseados: F={fuerza_n:.1f}N, R={recorrido_mm:.1f}mm, "
                f"TA={temp_amortiguador_c:.1f}°C, TR={temp_reservorio_c:.1f}°C, "
                f"V={velocidad_rpm}RPM"
            )

            return ShockDynoData(
                timestamp=ahora,
                fuerza_n=round(fuerza_n, 2),
                recorrido_mm=round(recorrido_mm, 2),
                temp_amortiguador_c=round(temp_amortiguador_c, 1),
                temp_reservorio_c=round(temp_reservorio_c, 1),
                velocidad_rpm=velocidad_rpm,
                valido=True,
            )

        except (IndexError, struct.error) as e:
            logger.error(f"Error al parsear payload: {e}")
            return ShockDynoData(timestamp=ahora, valido=False)
