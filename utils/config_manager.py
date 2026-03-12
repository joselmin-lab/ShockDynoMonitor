"""
Módulo: config_manager.py
Descripción: Gestión de la configuración de la aplicación.

Carga la configuración desde config/default_config.json y permite
guardar cambios realizados desde el diálogo de configuración.

Hace merge de la configuración del usuario con los valores por defecto,
para que siempre existan todos los campos necesarios.
"""

import json
import logging
import os
from typing import Any, Optional

# Logger del módulo
logger = logging.getLogger(__name__)

# Rutas de configuración
DIRECTORIO_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_CONFIG_DEFAULT = os.path.join(DIRECTORIO_BASE, "config", "default_config.json")
RUTA_CONFIG_USUARIO = os.path.join(DIRECTORIO_BASE, "config", "config.json")


class ConfigManager:
    """
    Clase que gestiona la carga y guardado de la configuración de la aplicación.

    Flujo de carga:
    1. Carga default_config.json (siempre existe en el repositorio).
    2. Si existe config.json (modificado por el usuario), hace merge.
    3. Retorna la configuración resultante.

    Flujo de guardado:
    1. Guarda la configuración en config.json (no modifica default_config.json).

    Ejemplo de uso::

        manager = ConfigManager()
        config = manager.cargar_config()
        config["alarmas"]["fuerza_max"] = 2500.0
        manager.guardar_config(config)
    """

    def __init__(
        self,
        ruta_default: Optional[str] = None,
        ruta_usuario: Optional[str] = None,
    ) -> None:
        """
        Inicializa el ConfigManager.

        Args:
            ruta_default: Ruta al archivo de configuración por defecto.
                          Si es None, usa config/default_config.json.
            ruta_usuario: Ruta al archivo de configuración del usuario.
                          Si es None, usa config/config.json.
        """
        self._ruta_default = ruta_default or RUTA_CONFIG_DEFAULT
        self._ruta_usuario = ruta_usuario or RUTA_CONFIG_USUARIO
        self._config_actual: dict = {}
        logger.debug("ConfigManager inicializado.")

    def cargar_config(self) -> dict:
        """
        Carga la configuración haciendo merge de default + usuario.

        Primero carga el archivo de configuración por defecto, luego
        sobreescribe con los valores del archivo de usuario si existe.

        Returns:
            Diccionario con la configuración completa y validada.
            Retorna configuración por defecto si hay errores de lectura.

        Ejemplo::

            manager = ConfigManager()
            config = manager.cargar_config()
            baudrate = config["conexion"]["baudrate"]  # 115200
        """
        # Cargar configuración por defecto
        config_default = self._leer_json(self._ruta_default)
        if config_default is None:
            logger.error(
                f"No se pudo cargar la configuración por defecto: {self._ruta_default}"
            )
            config_default = {}

        # Cargar configuración del usuario (si existe)
        config_usuario = {}
        if os.path.exists(self._ruta_usuario):
            config_usuario = self._leer_json(self._ruta_usuario) or {}
            logger.info(f"Configuración de usuario cargada: {self._ruta_usuario}")
        else:
            logger.info("No existe config de usuario, usando valores por defecto.")

        # Hacer merge profundo (usuario sobreescribe default)
        self._config_actual = self._merge_profundo(config_default, config_usuario)

        # Validar configuración
        self._validar_config(self._config_actual)

        logger.debug("Configuración cargada correctamente.")
        return self._config_actual

    def guardar_config(self, config: dict) -> bool:
        """
        Guarda la configuración en el archivo de usuario (config.json).

        No modifica el archivo de configuración por defecto.

        Args:
            config: Diccionario con la configuración a guardar.

        Returns:
            True si se guardó correctamente, False si hubo error.

        Ejemplo::

            manager = ConfigManager()
            config = manager.cargar_config()
            config["conexion"]["puerto"] = "COM3"
            manager.guardar_config(config)
        """
        try:
            # Crear directorio si no existe
            directorio = os.path.dirname(self._ruta_usuario)
            if directorio and not os.path.exists(directorio):
                os.makedirs(directorio)

            with open(self._ruta_usuario, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            self._config_actual = config
            logger.info(f"Configuración guardada en: {self._ruta_usuario}")
            return True

        except OSError as e:
            logger.error(f"Error al guardar configuración: {e}")
            return False

    def obtener_valor(self, *claves: str, default: Any = None) -> Any:
        """
        Obtiene un valor de la configuración usando una ruta de claves.

        Args:
            *claves: Secuencia de claves para navegar el diccionario.
            default: Valor a retornar si la clave no existe.

        Returns:
            El valor en la ruta especificada, o default si no existe.

        Ejemplo::

            manager = ConfigManager()
            manager.cargar_config()
            baudrate = manager.obtener_valor("conexion", "baudrate", default=115200)
            fuerza_max = manager.obtener_valor("alarmas", "fuerza_max", default=2000.0)
        """
        valor = self._config_actual
        for clave in claves:
            if isinstance(valor, dict) and clave in valor:
                valor = valor[clave]
            else:
                return default
        return valor

    @staticmethod
    def _leer_json(ruta: str) -> Optional[dict]:
        """
        Lee y parsea un archivo JSON.

        Args:
            ruta: Ruta al archivo JSON a leer.

        Returns:
            Diccionario con el contenido del JSON, o None si hay error.
        """
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Error al leer {ruta}: {e}")
            return None

    @staticmethod
    def _merge_profundo(base: dict, sobreescritura: dict) -> dict:
        """
        Hace un merge profundo de dos diccionarios.

        Para claves que son diccionarios en ambos, hace merge recursivo.
        Para otros tipos, la sobreescritura tiene prioridad.

        Args:
            base: Diccionario base (valores por defecto).
            sobreescritura: Diccionario con valores a sobreescribir.

        Returns:
            Nuevo diccionario con los valores merged.
        """
        resultado = base.copy()
        for clave, valor in sobreescritura.items():
            if (
                clave in resultado
                and isinstance(resultado[clave], dict)
                and isinstance(valor, dict)
            ):
                resultado[clave] = ConfigManager._merge_profundo(
                    resultado[clave], valor
                )
            else:
                resultado[clave] = valor
        return resultado

    @staticmethod
    def _validar_config(config: dict) -> None:
        """
        Valida los valores críticos de la configuración.

        Verifica que los valores numéricos estén en rangos razonables
        y que los tipos de datos sean correctos. Registra advertencias
        para valores sospechosos pero no lanza excepciones.

        Args:
            config: Diccionario de configuración a validar.
        """
        # Validar baudrate
        baudrate = config.get("conexion", {}).get("baudrate", 115200)
        if baudrate not in [9600, 19200, 38400, 57600, 115200, 230400]:
            logger.warning(
                f"Baudrate inusual: {baudrate}. Valor esperado: 115200."
            )

        # Validar intervalo de polling
        intervalo = config.get("conexion", {}).get("intervalo_polling_ms", 50)
        if not (10 <= intervalo <= 1000):
            logger.warning(
                f"Intervalo de polling inusual: {intervalo}ms. "
                f"Rango recomendado: 10-1000ms."
            )

        # Validar umbrales de alarmas
        alarmas = config.get("alarmas", {})
        if alarmas.get("temp_amortiguador_max", 60) > 150:
            logger.warning("Umbral de temperatura del amortiguador muy alto.")
        if alarmas.get("fuerza_max", 2000) > 10000:
            logger.warning("Umbral de fuerza muy alto.")
