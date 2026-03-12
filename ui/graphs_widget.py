"""
Módulo: graphs_widget.py
Descripción: Widget de gráficas en tiempo real usando pyqtgraph.

Muestra 4 gráficas:
    1. Fuerza vs Tiempo
    2. Recorrido vs Tiempo
    3. Temperaturas vs Tiempo (Amortiguador + Reservorio)
    4. Fuerza vs Recorrido (curva característica del amortiguador)

El buffer de datos se mantiene en utils/data_buffer.py.
"""

import logging
from typing import Optional, List

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.data_parser import ShockDynoData
from utils.data_buffer import DataBuffer

# Logger del módulo
logger = logging.getLogger(__name__)

# Colores de las líneas de las gráficas
COLOR_FUERZA = (0, 200, 83)        # Verde
COLOR_RECORRIDO = (0, 150, 255)    # Azul
COLOR_TEMP_AMO = (255, 100, 0)     # Naranja
COLOR_TEMP_RES = (255, 200, 0)     # Amarillo
COLOR_FUERZA_VS_REC = (200, 0, 200)  # Magenta

# Fondo de las gráficas
COLOR_FONDO_GRAFICA = "#1e1e1e"
COLOR_TEXTO_GRAFICA = "#cccccc"


class GraphsWidget(QWidget):
    """
    Widget que contiene 4 gráficas en tiempo real del banco de pruebas.

    Las gráficas se actualizan con cada nuevo dato recibido de la ECU.
    Soporta zoom, pan y reset de vista.

    Datos que grafica:
        - Fuerza (N) vs tiempo (s)
        - Recorrido (mm) vs tiempo (s)
        - Temperaturas (°C) vs tiempo (s): 2 líneas
        - Fuerza (N) vs Recorrido (mm): curva característica

    Ejemplo de uso::

        graficas = GraphsWidget(config=config)
        graficas.agregar_dato(ShockDynoData(...))
        graficas.limpiar_graficas()
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Inicializa el widget de gráficas.

        Args:
            config: Configuración de la aplicación.
            parent: Widget padre de Qt.
        """
        super().__init__(parent)
        self._config = config or {}
        self._cfg_ui = self._config.get("ui", {})

        # Duración del buffer en segundos
        segundos_buffer = self._cfg_ui.get("buffer_graficas_segundos", 30)
        # A 20Hz, 30s = 600 muestras
        capacidad_buffer = segundos_buffer * 20

        # Buffer de datos
        self._buffer = DataBuffer(capacidad_maxima=capacidad_buffer)

        # Configurar estilo oscuro de pyqtgraph
        pg.setConfigOption("background", COLOR_FONDO_GRAFICA)
        pg.setConfigOption("foreground", COLOR_TEXTO_GRAFICA)

        self._construir_ui()
        logger.debug("GraphsWidget inicializado.")

    def _construir_ui(self) -> None:
        """Construye el layout del widget con las 4 gráficas."""
        self.setStyleSheet("background-color: #1e1e1e;")

        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(8, 8, 8, 8)
        layout_principal.setSpacing(8)

        # Barra de controles superior
        layout_controles = QHBoxLayout()
        lbl_titulo = QLabel("Gráficas en Tiempo Real")
        lbl_titulo.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #ffffff;"
        )
        layout_controles.addWidget(lbl_titulo)
        layout_controles.addStretch()

        # Botón resetear vistas
        btn_reset = QPushButton("Resetear Vista")
        btn_reset.setStyleSheet(
            "QPushButton { background: #333; color: #fff; border: 1px solid #555; "
            "border-radius: 4px; padding: 4px 12px; } "
            "QPushButton:hover { background: #444; }"
        )
        btn_reset.clicked.connect(self._resetear_vistas)
        layout_controles.addWidget(btn_reset)

        # Botón limpiar
        btn_limpiar = QPushButton("Limpiar")
        btn_limpiar.setStyleSheet(
            "QPushButton { background: #333; color: #fff; border: 1px solid #555; "
            "border-radius: 4px; padding: 4px 12px; } "
            "QPushButton:hover { background: #444; }"
        )
        btn_limpiar.clicked.connect(self.limpiar_graficas)
        layout_controles.addWidget(btn_limpiar)

        layout_principal.addLayout(layout_controles)

        # Contenedor de gráficas (2x2)
        self._layout_graficas = pg.GraphicsLayoutWidget()
        layout_principal.addWidget(self._layout_graficas)

        # Crear las 4 gráficas
        self._crear_graficas()

    def _crear_graficas(self) -> None:
        """Crea y configura las 4 gráficas de pyqtgraph."""
        lw = self._layout_graficas

        # --- Gráfica 1: Fuerza vs Tiempo ---
        self._plot_fuerza = lw.addPlot(row=0, col=0, title="Fuerza vs Tiempo")
        self._plot_fuerza.setLabel("left", "Fuerza", units="N")
        self._plot_fuerza.setLabel("bottom", "Tiempo", units="s")
        self._plot_fuerza.showGrid(x=True, y=True, alpha=0.3)
        self._plot_fuerza.addLegend()
        self._curva_fuerza = self._plot_fuerza.plot(
            pen=pg.mkPen(color=COLOR_FUERZA, width=2),
            name="Fuerza (N)",
        )

        # --- Gráfica 2: Recorrido vs Tiempo ---
        self._plot_recorrido = lw.addPlot(row=0, col=1, title="Recorrido vs Tiempo")
        self._plot_recorrido.setLabel("left", "Recorrido", units="mm")
        self._plot_recorrido.setLabel("bottom", "Tiempo", units="s")
        self._plot_recorrido.showGrid(x=True, y=True, alpha=0.3)
        self._curva_recorrido = self._plot_recorrido.plot(
            pen=pg.mkPen(color=COLOR_RECORRIDO, width=2),
            name="Recorrido (mm)",
        )

        # --- Gráfica 3: Temperaturas vs Tiempo ---
        self._plot_temp = lw.addPlot(row=1, col=0, title="Temperaturas vs Tiempo")
        self._plot_temp.setLabel("left", "Temperatura", units="°C")
        self._plot_temp.setLabel("bottom", "Tiempo", units="s")
        self._plot_temp.showGrid(x=True, y=True, alpha=0.3)
        self._plot_temp.addLegend()
        self._curva_temp_amo = self._plot_temp.plot(
            pen=pg.mkPen(color=COLOR_TEMP_AMO, width=2),
            name="Amortiguador (°C)",
        )
        self._curva_temp_res = self._plot_temp.plot(
            pen=pg.mkPen(color=COLOR_TEMP_RES, width=2),
            name="Reservorio (°C)",
        )

        # --- Gráfica 4: Fuerza vs Recorrido ---
        self._plot_fvsr = lw.addPlot(row=1, col=1, title="Fuerza vs Recorrido")
        self._plot_fvsr.setLabel("left", "Fuerza", units="N")
        self._plot_fvsr.setLabel("bottom", "Recorrido", units="mm")
        self._plot_fvsr.showGrid(x=True, y=True, alpha=0.3)
        self._curva_fvsr = self._plot_fvsr.plot(
            pen=pg.mkPen(color=COLOR_FUERZA_VS_REC, width=2),
            name="Fuerza vs Recorrido",
        )

    def agregar_dato(self, dato: ShockDynoData) -> None:
        """
        Agrega un nuevo dato al buffer y actualiza todas las gráficas.

        Args:
            dato: ShockDynoData con los valores actuales de los sensores.
        """
        if not dato.valido:
            return

        self._buffer.push(dato)
        self._actualizar_curvas()

    def _actualizar_curvas(self) -> None:
        """
        Obtiene los datos del buffer y actualiza las curvas de las gráficas.

        Calcula el eje de tiempo relativo basado en los timestamps de los datos.
        """
        datos = self._buffer.obtener_todos()
        if not datos:
            return

        try:
            # Calcular eje de tiempo relativo en segundos desde el primer dato
            t0 = datos[0].timestamp.timestamp()
            tiempos = np.array([d.timestamp.timestamp() - t0 for d in datos])

            fuerzas = np.array([d.fuerza_n for d in datos])
            recorridos = np.array([d.recorrido_mm for d in datos])
            temps_amo = np.array([d.temp_amortiguador_c for d in datos])
            temps_res = np.array([d.temp_reservorio_c for d in datos])

            # Actualizar curvas
            self._curva_fuerza.setData(tiempos, fuerzas)
            self._curva_recorrido.setData(tiempos, recorridos)
            self._curva_temp_amo.setData(tiempos, temps_amo)
            self._curva_temp_res.setData(tiempos, temps_res)
            self._curva_fvsr.setData(recorridos, fuerzas)

        except Exception as e:
            logger.error(f"Error al actualizar gráficas: {e}")

    def limpiar_graficas(self) -> None:
        """
        Limpia el buffer de datos y todas las gráficas.

        Útil para iniciar una nueva sesión de pruebas.
        """
        self._buffer.limpiar()
        self._curva_fuerza.setData([], [])
        self._curva_recorrido.setData([], [])
        self._curva_temp_amo.setData([], [])
        self._curva_temp_res.setData([], [])
        self._curva_fvsr.setData([], [])
        logger.info("Gráficas limpiadas.")

    def _resetear_vistas(self) -> None:
        """Resetea el zoom y pan de todas las gráficas a vista automática."""
        self._plot_fuerza.enableAutoRange()
        self._plot_recorrido.enableAutoRange()
        self._plot_temp.enableAutoRange()
        self._plot_fvsr.enableAutoRange()
