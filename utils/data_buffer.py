"""
Módulo: data_buffer.py
Descripción: Buffer circular thread-safe para almacenamiento de datos
             de sensores en tiempo real.

El buffer mantiene los últimos N datos (FIFO) con acceso concurrente
seguro para múltiples threads (RX thread escribe, UI thread lee).
"""

import logging
import threading
from collections import deque
from typing import List, Optional

from core.data_parser import ShockDynoData

# Logger del módulo
logger = logging.getLogger(__name__)


class DataBuffer:
    """
    Buffer circular thread-safe para datos de ShockDynoData.

    Utiliza collections.deque con maxlen para implementar el comportamiento
    circular: cuando el buffer está lleno, los datos más antiguos se descartan
    automáticamente al agregar nuevos.

    Es seguro para uso concurrente con threading.Lock.

    Ejemplo de uso::

        buffer = DataBuffer(capacidad_maxima=600)  # 30 segundos a 20Hz
        buffer.push(ShockDynoData(...))
        ultimos = buffer.obtener_ultimos_n(100)
        todos = buffer.obtener_todos()
        buffer.limpiar()
    """

    def __init__(self, capacidad_maxima: int = 600) -> None:
        """
        Inicializa el buffer circular.

        Args:
            capacidad_maxima: Número máximo de elementos que puede almacenar.
                              Al superarse, el elemento más antiguo se descarta.
                              Default: 600 (30 segundos a 20Hz).
        """
        self._capacidad = capacidad_maxima
        self._buffer: deque = deque(maxlen=capacidad_maxima)
        self._lock = threading.Lock()
        logger.debug(f"DataBuffer inicializado con capacidad {capacidad_maxima}.")

    def push(self, dato: ShockDynoData) -> None:
        """
        Agrega un dato al final del buffer (FIFO).

        Si el buffer está lleno, el dato más antiguo se descarta
        automáticamente gracias a deque con maxlen.

        Args:
            dato: ShockDynoData a agregar al buffer.

        Ejemplo::

            buffer.push(ShockDynoData(fuerza_n=500.0, ...))
        """
        with self._lock:
            self._buffer.append(dato)

    def obtener_ultimos_n(self, n: int) -> List[ShockDynoData]:
        """
        Retorna los últimos N datos del buffer (los más recientes).

        Si el buffer tiene menos de N elementos, retorna todos los
        elementos disponibles.

        Args:
            n: Número de datos recientes a retornar.

        Returns:
            Lista de los últimos N ShockDynoData, ordenados del más
            antiguo al más reciente.

        Ejemplo::

            ultimos_100 = buffer.obtener_ultimos_n(100)
            for dato in ultimos_100:
                print(dato.fuerza_n)
        """
        with self._lock:
            datos = list(self._buffer)

        # Retornar los últimos N elementos
        if n >= len(datos):
            return datos
        return datos[-n:]

    def obtener_todos(self) -> List[ShockDynoData]:
        """
        Retorna todos los datos actuales en el buffer.

        Returns:
            Lista completa de ShockDynoData en el buffer,
            ordenados del más antiguo al más reciente.
        """
        with self._lock:
            return list(self._buffer)

    def obtener_ultimo(self) -> Optional[ShockDynoData]:
        """
        Retorna el dato más reciente del buffer.

        Returns:
            El ShockDynoData más reciente, o None si el buffer está vacío.
        """
        with self._lock:
            if self._buffer:
                return self._buffer[-1]
        return None

    def limpiar(self) -> None:
        """
        Elimina todos los datos del buffer.

        Útil para reiniciar la captura de datos o limpiar
        los datos de una sesión anterior.
        """
        with self._lock:
            self._buffer.clear()
        logger.debug("DataBuffer limpiado.")

    @property
    def tamanio(self) -> int:
        """
        Retorna el número actual de elementos en el buffer.

        Returns:
            Número de elementos almacenados actualmente.
        """
        with self._lock:
            return len(self._buffer)

    @property
    def esta_lleno(self) -> bool:
        """
        Indica si el buffer ha alcanzado su capacidad máxima.

        Returns:
            True si el buffer está lleno.
        """
        with self._lock:
            return len(self._buffer) >= self._capacidad

    @property
    def capacidad(self) -> int:
        """
        Retorna la capacidad máxima del buffer.

        Returns:
            Número máximo de elementos que puede almacenar.
        """
        return self._capacidad
