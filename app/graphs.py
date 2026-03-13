from collections import deque
from typing import Optional

import pyqtgraph as pg
from PyQt5.QtWidgets import QTabWidget, QVBoxLayout, QWidget

_MAX_POINTS = 300  # ~30 seconds at 10 Hz


class GraphsWidget(QWidget):
    """Tabbed real-time plots: Fuerza vs Recorrido, Temperaturas vs Tiempo, Distancia vs Tiempo."""

    def __init__(self, parent=None):
        super().__init__(parent)

        pg.setConfigOptions(antialias=True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabBar::tab { background: #1a1a2e; color: #a0a0c0; padding: 6px 18px; border: 1px solid #333; }"
            "QTabBar::tab:selected { background: #2a2a4a; color: #ffffff; border-bottom: 2px solid #00e5ff; }"
            "QTabWidget::pane { border: 1px solid #2a2a3a; }"
        )
        layout.addWidget(self._tabs)

        # Shared sample counter
        self._n = 0
        self._xs: deque[int] = deque(maxlen=_MAX_POINTS)

        # ── Tab 1: Fuerza vs Recorrido (hysteresis / Lissajous loop) ──────
        self._fuerza_data: deque[float] = deque(maxlen=_MAX_POINTS)
        self._recorrido_data: deque[float] = deque(maxlen=_MAX_POINTS)
        self._pw_fvr = self._make_plot_widget("Fuerza vs Recorrido", "#00e5ff")
        self._pw_fvr.setLabel("bottom", "Recorrido (mm)")
        self._pw_fvr.setLabel("left", "Fuerza (N)")
        # Explicitly enable auto-range on both axes so the Y-axis can scale to thousands of
        # Newtons (e.g. a 2000 KG / ~20 000 N load cell) without being locked to a tiny range.
        self._pw_fvr.enableAutoRange()
        self._curve_fvr = self._pw_fvr.plot(pen=pg.mkPen("#00e5ff", width=2))
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.addWidget(self._pw_fvr)
        self._tabs.addTab(tab1, "Fuerza vs Recorrido")

        # ── Tab 2: Temperaturas vs Tiempo ─────────────────────────────────
        self._temp_amo_data: deque[float] = deque(maxlen=_MAX_POINTS)
        self._temp_res_data: deque[float] = deque(maxlen=_MAX_POINTS)
        self._pw_temp = self._make_plot_widget("Temperaturas vs Tiempo", "#ff9100")
        self._pw_temp.setLabel("bottom", "Muestras")
        self._pw_temp.setLabel("left", "Temperatura (°C)")
        self._pw_temp.addLegend()
        self._curve_temp_amo = self._pw_temp.plot(pen=pg.mkPen("#ff9100", width=2), name="Amortiguador")
        self._curve_temp_res = self._pw_temp.plot(pen=pg.mkPen("#ffee58", width=2), name="Reservorio")
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.addWidget(self._pw_temp)
        self._tabs.addTab(tab2, "Temperaturas vs Tiempo")

        # ── Tab 3: Distancia vs Tiempo ────────────────────────────────────
        self._pw_dist = self._make_plot_widget("Distancia vs Tiempo", "#69ff47")
        self._pw_dist.setLabel("bottom", "Muestras")
        self._pw_dist.setLabel("left", "Recorrido (mm)")
        self._curve_dist = self._pw_dist.plot(pen=pg.mkPen("#69ff47", width=2))
        tab3 = QWidget()
        tab3_layout = QVBoxLayout(tab3)
        tab3_layout.addWidget(self._pw_dist)
        self._tabs.addTab(tab3, "Distancia vs Tiempo")

    # ------------------------------------------------------------------
    def apply_graph_settings(self, settings: dict) -> None:
        """Apply axis limits from *settings*. A value of None means auto-range for that axis."""
        # ── Tab 1: Fuerza vs Recorrido ──
        x_min: Optional[float] = settings.get("fvr_x_min")
        x_max: Optional[float] = settings.get("fvr_x_max")
        y_min: Optional[float] = settings.get("fvr_y_min")
        y_max: Optional[float] = settings.get("fvr_y_max")

        if x_min is not None and x_max is not None:
            self._pw_fvr.setXRange(x_min, x_max, padding=0)
        else:
            self._pw_fvr.enableAutoRange(axis="x")

        if y_min is not None and y_max is not None:
            self._pw_fvr.setYRange(y_min, y_max, padding=0)
        else:
            self._pw_fvr.enableAutoRange(axis="y")

        # ── Tab 2: Temperaturas vs Tiempo ──
        temp_y_min: Optional[float] = settings.get("temp_y_min")
        temp_y_max: Optional[float] = settings.get("temp_y_max")

        self._pw_temp.enableAutoRange(axis="x")
        if temp_y_min is not None and temp_y_max is not None:
            self._pw_temp.setYRange(temp_y_min, temp_y_max, padding=0)
        else:
            self._pw_temp.enableAutoRange(axis="y")

        # ── Tab 3: Distancia vs Tiempo ──
        dist_y_min: Optional[float] = settings.get("dist_y_min")
        dist_y_max: Optional[float] = settings.get("dist_y_max")

        self._pw_dist.enableAutoRange(axis="x")
        if dist_y_min is not None and dist_y_max is not None:
            self._pw_dist.setYRange(dist_y_min, dist_y_max, padding=0)
        else:
            self._pw_dist.enableAutoRange(axis="y")

    # ------------------------------------------------------------------
    def _make_plot_widget(self, title: str, title_color: str) -> pg.PlotWidget:
        pw = pg.PlotWidget()
        pw.setBackground("#0d0d1a")
        pw.showGrid(x=True, y=True, alpha=0.25)
        pw.setTitle(title, color=title_color, size="11pt")
        pw.getAxis("left").setTextPen("w")
        pw.getAxis("bottom").setTextPen("w")
        pw.setMenuEnabled(False)
        return pw

    # ------------------------------------------------------------------
    def update_values(
        self,
        fuerza: float,
        recorrido: float,
        temp_amo: float,
        temp_res: float,
        rpm: int,  # noqa: ARG002  – not plotted but kept for uniform signature
    ):
        self._xs.append(self._n)
        self._n += 1

        self._fuerza_data.append(fuerza)
        self._recorrido_data.append(recorrido)
        self._temp_amo_data.append(temp_amo)
        self._temp_res_data.append(temp_res)

        xs = list(self._xs)

        # Tab 1: phase-space (Fuerza vs Recorrido)
        self._curve_fvr.setData(list(self._recorrido_data), list(self._fuerza_data))

        # Tab 2: temperatures over time
        self._curve_temp_amo.setData(xs, list(self._temp_amo_data))
        self._curve_temp_res.setData(xs, list(self._temp_res_data))

        # Tab 3: distance over time
        self._curve_dist.setData(xs, list(self._recorrido_data))

    def clear_plots(self):
        self._xs.clear()
        self._n = 0
        for buf in (
            self._fuerza_data,
            self._recorrido_data,
            self._temp_amo_data,
            self._temp_res_data,
        ):
            buf.clear()
        for curve in (
            self._curve_fvr,
            self._curve_temp_amo,
            self._curve_temp_res,
            self._curve_dist,
        ):
            curve.setData([], [])
