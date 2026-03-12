"""
Módulo: dashboard_widget.py
Descripción: Widget del dashboard que muestra los 5 sensores del banco
             de pruebas en tiempo real.

Cada sensor se muestra con:
    - Valor actual (grande y destacado)
    - Unidad de medida
    - Barra de progreso
    - Valores máximo y mínimo de la sesión
    - Color de fondo según estado de alarma
"""

import logging
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.data_parser import ShockDynoData
from core.alarm_manager import AlarmManager, NivelAlarma

# Logger del módulo
logger = logging.getLogger(__name__)

# Colores del tema oscuro
COLOR_FONDO_NORMAL = "#2b2b2b"
COLOR_FONDO_ADVERTENCIA = "#5c4a00"
COLOR_FONDO_CRITICO = "#5c0000"
COLOR_TEXTO_VALOR = "#ffffff"
COLOR_TEXTO_UNIDAD = "#a0a0a0"
COLOR_TEXTO_MIN_MAX = "#808080"
COLOR_BARRA_NORMAL = "#00aa44"
COLOR_BARRA_ADVERTENCIA = "#ffaa00"
COLOR_BARRA_CRITICO = "#ff2222"

# Estilo base de cada tarjeta de sensor
ESTILO_TARJETA = """
    QFrame#TarjetaSensor {{
        background-color: {color_fondo};
        border: 1px solid #444444;
        border-radius: 8px;
        padding: 8px;
    }}
"""


class TarjetaSensor(QFrame):
    """
    Widget que muestra los datos de un sensor individual.

    Incluye:
    - Título del sensor
    - Valor actual (texto grande)
    - Unidad
    - Barra de progreso (min a max del rango)
    - Etiquetas de mínimo y máximo de la sesión

    Ejemplo de uso::

        tarjeta = TarjetaSensor(
            nombre="Fuerza",
            unidad="N",
            min_rango=0,
            max_rango=3000,
        )
        tarjeta.actualizar(1250.5, alarma=False, nivel_alarma=None)
    """

    def __init__(
        self,
        nombre: str,
        unidad: str,
        min_rango: float,
        max_rango: float,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Inicializa la tarjeta del sensor.

        Args:
            nombre: Nombre del sensor (ej: "Fuerza").
            unidad: Unidad de medida (ej: "N", "mm", "°C", "RPM").
            min_rango: Valor mínimo del rango del sensor.
            max_rango: Valor máximo del rango del sensor.
            parent: Widget padre de Qt.
        """
        super().__init__(parent)
        self.setObjectName("TarjetaSensor")

        self._nombre = nombre
        self._unidad = unidad
        self._min_rango = min_rango
        self._max_rango = max_rango
        self._min_sesion: Optional[float] = None
        self._max_sesion: Optional[float] = None

        self._construir_ui()
        self._aplicar_estilo_normal()

    def _construir_ui(self) -> None:
        """Construye los elementos de la interfaz de la tarjeta."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Título del sensor
        self._lbl_titulo = QLabel(self._nombre)
        self._lbl_titulo.setAlignment(Qt.AlignCenter)
        self._lbl_titulo.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #a0a0a0;"
        )
        layout.addWidget(self._lbl_titulo)

        # Valor actual (grande)
        self._lbl_valor = QLabel("---")
        self._lbl_valor.setAlignment(Qt.AlignCenter)
        self._lbl_valor.setStyleSheet(
            "font-size: 32px; font-weight: bold; color: #ffffff;"
        )
        layout.addWidget(self._lbl_valor)

        # Unidad
        self._lbl_unidad = QLabel(self._unidad)
        self._lbl_unidad.setAlignment(Qt.AlignCenter)
        self._lbl_unidad.setStyleSheet("font-size: 14px; color: #a0a0a0;")
        layout.addWidget(self._lbl_unidad)

        # Barra de progreso
        self._barra = QProgressBar()
        self._barra.setMinimum(0)
        self._barra.setMaximum(1000)  # Escala interna de 0 a 1000
        self._barra.setValue(0)
        self._barra.setTextVisible(False)
        self._barra.setFixedHeight(8)
        self._barra.setStyleSheet(
            f"QProgressBar {{ border: none; background: #444; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {COLOR_BARRA_NORMAL}; border-radius: 4px; }}"
        )
        layout.addWidget(self._barra)

        # Min/Max de la sesión
        layout_min_max = QHBoxLayout()
        layout_min_max.setSpacing(0)

        self._lbl_min = QLabel("Min: ---")
        self._lbl_min.setStyleSheet("font-size: 10px; color: #808080;")
        layout_min_max.addWidget(self._lbl_min)

        layout_min_max.addStretch()

        self._lbl_max = QLabel("Max: ---")
        self._lbl_max.setStyleSheet("font-size: 10px; color: #808080;")
        layout_min_max.addWidget(self._lbl_max)

        layout.addLayout(layout_min_max)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(140)

    def actualizar(
        self,
        valor: float,
        en_alarma: bool = False,
        nivel_alarma: Optional[NivelAlarma] = None,
    ) -> None:
        """
        Actualiza el display de la tarjeta con un nuevo valor.

        Args:
            valor: Nuevo valor a mostrar.
            en_alarma: True si el sensor está en estado de alarma.
            nivel_alarma: Nivel de la alarma (ADVERTENCIA o CRITICO).
        """
        # Formatear valor según la magnitud
        if abs(valor) >= 1000:
            texto_valor = f"{valor:.0f}"
        elif abs(valor) >= 100:
            texto_valor = f"{valor:.1f}"
        else:
            texto_valor = f"{valor:.2f}"

        self._lbl_valor.setText(texto_valor)

        # Actualizar min/max de la sesión
        if self._min_sesion is None or valor < self._min_sesion:
            self._min_sesion = valor
        if self._max_sesion is None or valor > self._max_sesion:
            self._max_sesion = valor

        if self._min_sesion is not None:
            self._lbl_min.setText(f"Min: {self._min_sesion:.1f}")
        if self._max_sesion is not None:
            self._lbl_max.setText(f"Max: {self._max_sesion:.1f}")

        # Actualizar barra de progreso
        rango = self._max_rango - self._min_rango
        if rango > 0:
            porcentaje = max(0, min(1000, int(
                (valor - self._min_rango) / rango * 1000
            )))
            self._barra.setValue(porcentaje)

        # Aplicar estilo según alarma
        if en_alarma:
            if nivel_alarma == NivelAlarma.CRITICO:
                self._aplicar_estilo_critico()
            else:
                self._aplicar_estilo_advertencia()
        else:
            self._aplicar_estilo_normal()

    def resetear_min_max(self) -> None:
        """Resetea los valores mínimo y máximo de la sesión."""
        self._min_sesion = None
        self._max_sesion = None
        self._lbl_min.setText("Min: ---")
        self._lbl_max.setText("Max: ---")

    def _aplicar_estilo_normal(self) -> None:
        """Aplica el estilo visual para estado normal (sin alarma)."""
        self.setStyleSheet(ESTILO_TARJETA.format(color_fondo=COLOR_FONDO_NORMAL))
        self._barra.setStyleSheet(
            "QProgressBar { border: none; background: #444; border-radius: 4px; }"
            f"QProgressBar::chunk {{ background: {COLOR_BARRA_NORMAL}; border-radius: 4px; }}"
        )

    def _aplicar_estilo_advertencia(self) -> None:
        """Aplica el estilo visual para estado de advertencia."""
        self.setStyleSheet(ESTILO_TARJETA.format(color_fondo=COLOR_FONDO_ADVERTENCIA))
        self._barra.setStyleSheet(
            "QProgressBar { border: none; background: #444; border-radius: 4px; }"
            f"QProgressBar::chunk {{ background: {COLOR_BARRA_ADVERTENCIA}; border-radius: 4px; }}"
        )

    def _aplicar_estilo_critico(self) -> None:
        """Aplica el estilo visual para estado crítico."""
        self.setStyleSheet(ESTILO_TARJETA.format(color_fondo=COLOR_FONDO_CRITICO))
        self._barra.setStyleSheet(
            "QProgressBar { border: none; background: #444; border-radius: 4px; }"
            f"QProgressBar::chunk {{ background: {COLOR_BARRA_CRITICO}; border-radius: 4px; }}"
        )


class DashboardWidget(QWidget):
    """
    Widget principal del dashboard con las 5 tarjetas de sensores.

    Muestra Fuerza, Recorrido, Temp Amortiguador, Temp Reservorio y Velocidad
    en un grid de 2 columnas con indicación visual de alarmas.

    Ejemplo de uso::

        dashboard = DashboardWidget(config=config)
        datos = ShockDynoData(fuerza_n=1250.0, ...)
        alarmas = gestor_alarmas.verificar_alarmas(datos)
        dashboard.actualizar_datos(datos, alarmas)
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        gestor_alarmas: Optional[AlarmManager] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Inicializa el dashboard.

        Args:
            config: Configuración de la aplicación (para rangos de sensores).
            gestor_alarmas: Gestor de alarmas para evaluar estados.
            parent: Widget padre de Qt.
        """
        super().__init__(parent)
        self._config = config or {}
        self._gestor_alarmas = gestor_alarmas
        self._cfg_sensores = self._config.get("sensores", {})

        self._tarjetas: dict = {}
        self._construir_ui()
        logger.debug("DashboardWidget inicializado.")

    def _construir_ui(self) -> None:
        """Construye el layout del dashboard con las 5 tarjetas de sensores."""
        # Layout principal con fondo oscuro
        self.setStyleSheet("background-color: #1e1e1e;")

        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(16, 16, 16, 16)
        layout_principal.setSpacing(12)

        # Título del panel
        lbl_titulo = QLabel("Panel de Monitoreo")
        lbl_titulo.setAlignment(Qt.AlignCenter)
        lbl_titulo.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #ffffff; "
            "padding: 8px; background-color: #333;"
        )
        layout_principal.addWidget(lbl_titulo)

        # Grid de tarjetas de sensores (2 columnas)
        grid = QGridLayout()
        grid.setSpacing(12)

        # Definición de los 5 sensores
        definicion_sensores = [
            {
                "clave": "fuerza",
                "nombre": "Fuerza",
                "unidad": "N",
                "min_rango": 0,
                "max_rango": self._cfg_sensores.get("fuerza", {}).get("max_rango", 3000),
                "fila": 0, "columna": 0,
            },
            {
                "clave": "recorrido",
                "nombre": "Recorrido",
                "unidad": "mm",
                "min_rango": 0,
                "max_rango": self._cfg_sensores.get("recorrido", {}).get("max_rango", 100),
                "fila": 0, "columna": 1,
            },
            {
                "clave": "temp_amortiguador",
                "nombre": "Temp Amortiguador",
                "unidad": "°C",
                "min_rango": -40,
                "max_rango": self._cfg_sensores.get("temp_amortiguador", {}).get("max_rango", 150),
                "fila": 1, "columna": 0,
            },
            {
                "clave": "temp_reservorio",
                "nombre": "Temp Reservorio",
                "unidad": "°C",
                "min_rango": -40,
                "max_rango": self._cfg_sensores.get("temp_reservorio", {}).get("max_rango", 100),
                "fila": 1, "columna": 1,
            },
            {
                "clave": "velocidad",
                "nombre": "Velocidad",
                "unidad": "RPM",
                "min_rango": 0,
                "max_rango": self._cfg_sensores.get("velocidad", {}).get("max_rango", 9999),
                "fila": 2, "columna": 0,
            },
        ]

        # Crear e insertar las tarjetas
        for sensor_def in definicion_sensores:
            tarjeta = TarjetaSensor(
                nombre=sensor_def["nombre"],
                unidad=sensor_def["unidad"],
                min_rango=sensor_def["min_rango"],
                max_rango=sensor_def["max_rango"],
            )
            self._tarjetas[sensor_def["clave"]] = tarjeta
            grid.addWidget(tarjeta, sensor_def["fila"], sensor_def["columna"])

        # La tarjeta de velocidad ocupa 2 columnas (última fila)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        layout_principal.addLayout(grid)
        layout_principal.addStretch()

    def actualizar_datos(
        self,
        datos: ShockDynoData,
        alarmas_activas: Optional[list] = None,
    ) -> None:
        """
        Actualiza todas las tarjetas de sensores con nuevos datos.

        Args:
            datos: ShockDynoData con los valores actuales de los sensores.
            alarmas_activas: Lista de Alarma activas (puede ser None o vacía).

        Ejemplo::

            dashboard.actualizar_datos(datos, alarmas)
        """
        if not datos.valido:
            return

        alarmas_activas = alarmas_activas or []

        # Construir set de sensores en alarma para lookup rápido
        sensores_en_alarma = {a.sensor: a for a in alarmas_activas}

        # Mapa sensor → valor
        valores = {
            "fuerza": datos.fuerza_n,
            "recorrido": datos.recorrido_mm,
            "temp_amortiguador": datos.temp_amortiguador_c,
            "temp_reservorio": datos.temp_reservorio_c,
            "velocidad": float(datos.velocidad_rpm),
        }

        # Actualizar cada tarjeta
        for clave, tarjeta in self._tarjetas.items():
            valor = valores.get(clave, 0.0)
            alarma = sensores_en_alarma.get(clave)
            en_alarma = alarma is not None
            nivel = alarma.nivel if alarma else None
            tarjeta.actualizar(valor, en_alarma=en_alarma, nivel_alarma=nivel)

    def resetear_sesion(self) -> None:
        """Resetea los valores mínimo y máximo de todas las tarjetas."""
        for tarjeta in self._tarjetas.values():
            tarjeta.resetear_min_max()
