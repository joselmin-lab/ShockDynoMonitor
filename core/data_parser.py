"""
Módulo: data_parser.py
Descripción: Definición del dataclass ShockDynoData que representa una lectura
             completa de los sensores del banco de pruebas de amortiguadores.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

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
