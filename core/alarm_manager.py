"""
Módulo: alarm_manager.py
Descripción: Gestión de alarmas para el banco de pruebas de amortiguadores.

Alarmas configurables:
    - Temperatura amortiguador > 60°C (peligro de degradación del aceite)
    - Temperatura reservorio > 50°C (sobrecalentamiento del fluido)
    - Fuerza > 2000 N (sobrecarga del amortiguador)
    - Velocidad > 5000 RPM (sobrevelocidad del banco)

Las alarmas se evalúan en cada lectura de datos y se retorna
la lista de alarmas activas para que la UI las muestre.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from core.data_parser import ShockDynoData

# Logger del módulo
logger = logging.getLogger(__name__)


class NivelAlarma(Enum):
    """
    Niveles de severidad para las alarmas del sistema.

    Values:
        ADVERTENCIA: Condición que requiere atención (color amarillo en UI).
        CRITICO: Condición peligrosa que requiere acción inmediata (color rojo en UI).
    """
    ADVERTENCIA = "ADVERTENCIA"
    CRITICO = "CRÍTICO"


@dataclass
class Alarma:
    """
    Representa una alarma activa en el sistema.

    Attributes:
        nombre: Nombre descriptivo de la alarma.
        mensaje: Mensaje detallado de la alarma con el valor actual.
        nivel: Nivel de severidad (ADVERTENCIA o CRITICO).
        sensor: Nombre del sensor que generó la alarma.
        valor_actual: Valor actual del sensor que disparó la alarma.
        umbral: Umbral que fue superado.
    """
    nombre: str
    mensaje: str
    nivel: NivelAlarma
    sensor: str
    valor_actual: float
    umbral: float


class AlarmManager:
    """
    Clase que evalúa los datos de sensores y genera alarmas cuando
    se superan los umbrales configurados.

    Los umbrales son configurables mediante config["alarmas"].
    Las alarmas se evalúan en cada llamada a check_alarmas().

    Ejemplo de uso::

        config = {
            "alarmas": {
                "temp_amortiguador_max": 60.0,
                "temp_reservorio_max": 50.0,
                "fuerza_max": 2000.0,
            }
        }
        gestor_alarmas = AlarmManager(config=config)
        datos = ShockDynoData(temp_amortiguador_c=75.0, ...)
        alarmas = gestor_alarmas.verificar_alarmas(datos)
        for alarma in alarmas:
            print(f"[{alarma.nivel.value}] {alarma.mensaje}")
    """

    # Umbrales por defecto (usados si no se configura nada)
    TEMP_AMORTIGUADOR_MAX_DEFAULT = 60.0   # °C
    TEMP_RESERVORIO_MAX_DEFAULT = 50.0     # °C
    FUERZA_MAX_DEFAULT = 2000.0            # N
    VELOCIDAD_MAX_DEFAULT = 5000.0         # RPM

    def __init__(self, config: Optional[dict] = None) -> None:
        """
        Inicializa el gestor de alarmas con los umbrales de la configuración.

        Args:
            config: Diccionario de configuración. Se usa config["alarmas"] con:
                - temp_amortiguador_max: Umbral máximo de temperatura del amortiguador (°C).
                - temp_reservorio_max: Umbral máximo de temperatura del reservorio (°C).
                - fuerza_max: Umbral máximo de fuerza (N).
                - velocidad_max: Umbral máximo de velocidad (RPM).
        """
        self._config = config or {}
        self._cfg_alarmas = self._config.get("alarmas", {})

        # Cargar umbrales (con valores por defecto si no están configurados)
        self.umbral_temp_amortiguador = self._cfg_alarmas.get(
            "temp_amortiguador_max", self.TEMP_AMORTIGUADOR_MAX_DEFAULT
        )
        self.umbral_temp_reservorio = self._cfg_alarmas.get(
            "temp_reservorio_max", self.TEMP_RESERVORIO_MAX_DEFAULT
        )
        self.umbral_fuerza = self._cfg_alarmas.get(
            "fuerza_max", self.FUERZA_MAX_DEFAULT
        )
        self.umbral_velocidad = self._cfg_alarmas.get(
            "velocidad_max", self.VELOCIDAD_MAX_DEFAULT
        )

        # Historial de alarmas activas (para evitar logs repetitivos)
        self._alarmas_previas: Dict[str, bool] = {}

        logger.debug(
            f"AlarmManager inicializado. Umbrales: "
            f"T_Amo={self.umbral_temp_amortiguador}°C, "
            f"T_Res={self.umbral_temp_reservorio}°C, "
            f"F={self.umbral_fuerza}N, "
            f"V={self.umbral_velocidad}RPM"
        )

    def verificar_alarmas(self, datos: ShockDynoData) -> List[Alarma]:
        """
        Evalúa los datos de sensores y retorna la lista de alarmas activas.

        Compara cada sensor con su umbral configurado. Si se supera el umbral,
        genera una Alarma con el nivel y mensaje correspondiente.

        Args:
            datos: ShockDynoData con los valores actuales de los sensores.

        Returns:
            Lista de Alarma activas. Lista vacía si todo está dentro de rangos.

        Ejemplo::

            gestor = AlarmManager()
            datos = ShockDynoData(temp_amortiguador_c=75.0, fuerza_n=500.0, ...)
            alarmas = gestor.verificar_alarmas(datos)
            # alarmas tendrá 1 alarma: temperatura amortiguador > 60°C
        """
        if not datos.valido:
            return []

        alarmas_activas: List[Alarma] = []

        # --- Verificar temperatura del amortiguador ---
        if datos.temp_amortiguador_c > self.umbral_temp_amortiguador:
            alarma = Alarma(
                nombre="Temp Amortiguador Alta",
                mensaje=(
                    f"Temperatura del amortiguador {datos.temp_amortiguador_c:.1f}°C "
                    f"supera el límite de {self.umbral_temp_amortiguador:.1f}°C"
                ),
                nivel=NivelAlarma.CRITICO,
                sensor="temp_amortiguador",
                valor_actual=datos.temp_amortiguador_c,
                umbral=self.umbral_temp_amortiguador,
            )
            alarmas_activas.append(alarma)
            self._log_cambio_alarma("temp_amortiguador", True, alarma.mensaje)
        else:
            self._log_cambio_alarma("temp_amortiguador", False)

        # --- Verificar temperatura del reservorio ---
        if datos.temp_reservorio_c > self.umbral_temp_reservorio:
            alarma = Alarma(
                nombre="Temp Reservorio Alta",
                mensaje=(
                    f"Temperatura del reservorio {datos.temp_reservorio_c:.1f}°C "
                    f"supera el límite de {self.umbral_temp_reservorio:.1f}°C"
                ),
                nivel=NivelAlarma.CRITICO,
                sensor="temp_reservorio",
                valor_actual=datos.temp_reservorio_c,
                umbral=self.umbral_temp_reservorio,
            )
            alarmas_activas.append(alarma)
            self._log_cambio_alarma("temp_reservorio", True, alarma.mensaje)
        else:
            self._log_cambio_alarma("temp_reservorio", False)

        # --- Verificar fuerza ---
        if datos.fuerza_n > self.umbral_fuerza:
            alarma = Alarma(
                nombre="Fuerza Excesiva",
                mensaje=(
                    f"Fuerza {datos.fuerza_n:.1f} N "
                    f"supera el límite de {self.umbral_fuerza:.1f} N"
                ),
                nivel=NivelAlarma.ADVERTENCIA,
                sensor="fuerza",
                valor_actual=datos.fuerza_n,
                umbral=self.umbral_fuerza,
            )
            alarmas_activas.append(alarma)
            self._log_cambio_alarma("fuerza", True, alarma.mensaje)
        else:
            self._log_cambio_alarma("fuerza", False)

        # --- Verificar velocidad ---
        if datos.velocidad_rpm > self.umbral_velocidad:
            alarma = Alarma(
                nombre="Velocidad Excesiva",
                mensaje=(
                    f"Velocidad {datos.velocidad_rpm} RPM "
                    f"supera el límite de {self.umbral_velocidad:.0f} RPM"
                ),
                nivel=NivelAlarma.ADVERTENCIA,
                sensor="velocidad",
                valor_actual=float(datos.velocidad_rpm),
                umbral=self.umbral_velocidad,
            )
            alarmas_activas.append(alarma)
            self._log_cambio_alarma("velocidad", True, alarma.mensaje)
        else:
            self._log_cambio_alarma("velocidad", False)

        return alarmas_activas

    def _log_cambio_alarma(
        self, sensor: str, activa: bool, mensaje: str = ""
    ) -> None:
        """
        Registra en el log solo cuando cambia el estado de una alarma.

        Evita saturar el log con el mismo mensaje repetido en cada ciclo
        de 50ms. Solo registra cuando la alarma se activa o se desactiva.

        Args:
            sensor: Nombre del sensor para identificar la alarma.
            activa: True si la alarma está activa, False si está OK.
            mensaje: Mensaje a loguear cuando se activa la alarma.
        """
        estado_previo = self._alarmas_previas.get(sensor, False)

        if activa and not estado_previo:
            # Alarma se activó
            logger.warning(f"ALARMA ACTIVADA - {mensaje}")
        elif not activa and estado_previo:
            # Alarma se desactivó
            logger.info(f"Alarma resuelta: sensor '{sensor}' volvió a rango normal.")

        self._alarmas_previas[sensor] = activa

    def actualizar_umbrales(self, nuevos_umbrales: dict) -> None:
        """
        Actualiza los umbrales de alarma durante la ejecución.

        Permite cambiar los umbrales desde el diálogo de configuración
        sin necesidad de reiniciar la aplicación.

        Args:
            nuevos_umbrales: Diccionario con los nuevos umbrales:
                - temp_amortiguador_max: Nuevo umbral de temperatura del amortiguador.
                - temp_reservorio_max: Nuevo umbral de temperatura del reservorio.
                - fuerza_max: Nuevo umbral de fuerza.
                - velocidad_max: Nuevo umbral de velocidad.

        Ejemplo::

            gestor.actualizar_umbrales({
                "temp_amortiguador_max": 70.0,
                "fuerza_max": 2500.0,
            })
        """
        if "temp_amortiguador_max" in nuevos_umbrales:
            self.umbral_temp_amortiguador = float(
                nuevos_umbrales["temp_amortiguador_max"]
            )
        if "temp_reservorio_max" in nuevos_umbrales:
            self.umbral_temp_reservorio = float(
                nuevos_umbrales["temp_reservorio_max"]
            )
        if "fuerza_max" in nuevos_umbrales:
            self.umbral_fuerza = float(nuevos_umbrales["fuerza_max"])
        if "velocidad_max" in nuevos_umbrales:
            self.umbral_velocidad = float(nuevos_umbrales["velocidad_max"])

        logger.info(
            f"Umbrales actualizados: "
            f"T_Amo={self.umbral_temp_amortiguador}°C, "
            f"T_Res={self.umbral_temp_reservorio}°C, "
            f"F={self.umbral_fuerza}N, "
            f"V={self.umbral_velocidad}RPM"
        )
