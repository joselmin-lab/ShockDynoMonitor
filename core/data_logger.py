"""
Módulo: data_logger.py
Descripción: Registro de datos de sensores en archivos CSV con timestamps.

Formato del CSV:
    Timestamp,Fuerza_N,Recorrido_mm,Temp_Amortiguador_C,Temp_Reservorio_C,Velocidad_RPM

Los archivos se nombran automáticamente con fecha y hora:
    shock_test_YYYYMMDD_HHMMSS.csv

El logging es thread-safe usando threading.Lock.
"""

import csv
import logging
import os
import threading
from datetime import datetime
from typing import Optional

from core.data_parser import ShockDynoData

# Logger del módulo
logger = logging.getLogger(__name__)

# Encabezados del CSV
ENCABEZADOS_CSV = [
    "Timestamp",
    "Fuerza_N",
    "Recorrido_mm",
    "Temp_Amortiguador_C",
    "Temp_Reservorio_C",
    "Velocidad_RPM",
]


class DataLogger:
    """
    Clase que gestiona el registro de datos de sensores en archivos CSV.

    Crea archivos CSV con nombre automático basado en fecha y hora,
    y permite iniciar/detener el logging durante la sesión de pruebas.

    Es thread-safe: puede ser llamada desde el thread RX mientras la UI
    corre en el thread principal.

    Ejemplo de uso::

        config = {"logging": {"carpeta": "logs", "prefijo_archivo": "shock_test"}}
        logger_datos = DataLogger(config=config)

        logger_datos.iniciar()
        logger_datos.registrar_dato(ShockDynoData(...))
        logger_datos.detener()
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        """
        Inicializa el DataLogger.

        Args:
            config: Diccionario de configuración. Se usa config["logging"] con:
                - carpeta: Carpeta donde guardar los CSV (default: "logs").
                - prefijo_archivo: Prefijo del nombre del archivo (default: "shock_test").
                - separador: Separador de columnas del CSV (default: ",").
        """
        self._config = config or {}
        self._cfg_logging = self._config.get("logging", {})

        self._carpeta = self._cfg_logging.get("carpeta", "logs")
        self._prefijo = self._cfg_logging.get("prefijo_archivo", "shock_test")
        self._separador = self._cfg_logging.get("separador", ",")

        # Estado del logger
        self._activo: bool = False
        self._archivo: Optional[object] = None  # File handle
        self._escritor_csv: Optional[csv.DictWriter] = None
        self._ruta_archivo_actual: str = ""
        self._filas_escritas: int = 0

        # Lock para acceso thread-safe al archivo
        self._lock = threading.Lock()

        logger.debug("DataLogger inicializado.")

    def iniciar(self) -> bool:
        """
        Inicia el logging creando un nuevo archivo CSV.

        El archivo se nombra automáticamente con fecha y hora:
        ``{prefijo}_{YYYYMMDD}_{HHMMSS}.csv``

        Crea la carpeta de destino si no existe.

        Returns:
            True si el archivo se creó correctamente, False si hubo error.

        Ejemplo::

            logger_datos = DataLogger()
            if logger_datos.iniciar():
                print(f"Guardando en: {logger_datos.ruta_archivo_actual}")
        """
        if self._activo:
            logger.warning("El logging ya está activo.")
            return True

        try:
            # Crear carpeta si no existe
            if not os.path.exists(self._carpeta):
                os.makedirs(self._carpeta)
                logger.info(f"Carpeta de logs creada: {self._carpeta}")

            # Generar nombre de archivo con timestamp
            ahora = datetime.now()
            nombre_archivo = (
                f"{self._prefijo}_{ahora.strftime('%Y%m%d_%H%M%S')}.csv"
            )
            self._ruta_archivo_actual = os.path.join(self._carpeta, nombre_archivo)

            # Abrir archivo y crear escritor CSV
            with self._lock:
                self._archivo = open(
                    self._ruta_archivo_actual,
                    mode="w",
                    newline="",
                    encoding="utf-8",
                )
                self._escritor_csv = csv.DictWriter(
                    self._archivo,
                    fieldnames=ENCABEZADOS_CSV,
                    delimiter=self._separador,
                )
                self._escritor_csv.writeheader()
                self._filas_escritas = 0
                self._activo = True

            logger.info(f"Log iniciado: {self._ruta_archivo_actual}")
            return True

        except OSError as e:
            logger.error(f"Error al crear archivo de log: {e}")
            return False

    def detener(self) -> None:
        """
        Detiene el logging y cierra el archivo CSV.

        Hace flush del buffer antes de cerrar para asegurar que todos
        los datos estén escritos en disco.

        Ejemplo::

            logger_datos.detener()
            print(f"Log guardado con {logger_datos.filas_escritas} filas")
        """
        if not self._activo:
            return

        with self._lock:
            try:
                if self._archivo:
                    self._archivo.flush()
                    self._archivo.close()
                    self._archivo = None
                    self._escritor_csv = None
            except OSError as e:
                logger.error(f"Error al cerrar archivo de log: {e}")
            finally:
                self._activo = False

        logger.info(
            f"Log detenido: {self._filas_escritas} filas guardadas en "
            f"{self._ruta_archivo_actual}"
        )

    def registrar_dato(self, dato: ShockDynoData) -> bool:
        """
        Registra una fila de datos en el archivo CSV.

        Thread-safe: puede ser llamado desde cualquier thread.

        Args:
            dato: ShockDynoData con los valores de los sensores a registrar.

        Returns:
            True si la fila se escribió correctamente, False si hubo error
            o si el logging no está activo.

        Ejemplo::

            dato = ShockDynoData(
                fuerza_n=500.0,
                recorrido_mm=45.0,
                temp_amortiguador_c=38.0,
                temp_reservorio_c=32.0,
                velocidad_rpm=120
            )
            logger_datos.registrar_dato(dato)
        """
        if not self._activo or not dato.valido:
            return False

        fila = dato.to_dict()

        try:
            with self._lock:
                if self._escritor_csv:
                    self._escritor_csv.writerow(fila)
                    self._filas_escritas += 1
                    # Flush periódico para no perder datos ante cierre inesperado
                    if self._filas_escritas % 100 == 0:
                        self._archivo.flush()
            return True
        except OSError as e:
            logger.error(f"Error al escribir en log: {e}")
            return False

    @property
    def esta_activo(self) -> bool:
        """
        Indica si el logging está activo.

        Returns:
            True si hay un archivo CSV abierto y recibiendo datos.
        """
        return self._activo

    @property
    def ruta_archivo_actual(self) -> str:
        """
        Retorna la ruta del archivo CSV actual.

        Returns:
            Ruta completa del archivo, o cadena vacía si no hay log activo.
        """
        return self._ruta_archivo_actual

    @property
    def filas_escritas(self) -> int:
        """
        Retorna el número de filas escritas en el archivo actual.

        Returns:
            Número de filas de datos registradas.
        """
        return self._filas_escritas
