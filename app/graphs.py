from collections import deque

import pyqtgraph as pg
from PyQt5.QtWidgets import QVBoxLayout, QWidget

_MAX_POINTS = 300  # ~30 seconds at 10 Hz


class GraphsWidget(QWidget):
    """Real-time scrolling plots for Force, Distance and Temperatures."""

    def __init__(self, parent=None):
        super().__init__(parent)

        pg.setConfigOptions(antialias=True)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Shared x-axis sample counter
        self._n = 0
        self._xs: deque[int] = deque(maxlen=_MAX_POINTS)

        # --- Force plot ---
        self._fuerza_data: deque[float] = deque(maxlen=_MAX_POINTS)
        pw_f = self._make_plot_widget("Fuerza (N)", "#00e5ff")
        self._curve_fuerza = pw_f.plot(pen=pg.mkPen("#00e5ff", width=2))
        layout.addWidget(pw_f)

        # --- Distance plot ---
        self._recorrido_data: deque[float] = deque(maxlen=_MAX_POINTS)
        pw_r = self._make_plot_widget("Recorrido (mm)", "#69ff47")
        self._curve_recorrido = pw_r.plot(pen=pg.mkPen("#69ff47", width=2))
        layout.addWidget(pw_r)

        # --- Temperature plot (both on same axes) ---
        self._temp_amo_data: deque[float] = deque(maxlen=_MAX_POINTS)
        self._temp_res_data: deque[float] = deque(maxlen=_MAX_POINTS)
        pw_t = self._make_plot_widget("Temperatura (°C)", "#ff9100")
        self._curve_temp_amo = pw_t.plot(pen=pg.mkPen("#ff9100", width=2), name="Amortiguador")
        self._curve_temp_res = pw_t.plot(pen=pg.mkPen("#ffee58", width=2), name="Reservorio")
        pw_t.addLegend()
        layout.addWidget(pw_t)

    # ------------------------------------------------------------------
    def _make_plot_widget(self, title: str, title_color: str) -> pg.PlotWidget:
        pw = pg.PlotWidget()
        pw.setBackground("#0d0d1a")
        pw.showGrid(x=True, y=True, alpha=0.25)
        pw.setTitle(title, color=title_color, size="11pt")
        pw.setLabel("bottom", "Muestras")
        pw.getAxis("left").setTextPen("w")
        pw.getAxis("bottom").setTextPen("w")
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
        self._curve_fuerza.setData(xs, list(self._fuerza_data))
        self._curve_recorrido.setData(xs, list(self._recorrido_data))
        self._curve_temp_amo.setData(xs, list(self._temp_amo_data))
        self._curve_temp_res.setData(xs, list(self._temp_res_data))

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
            self._curve_fuerza,
            self._curve_recorrido,
            self._curve_temp_amo,
            self._curve_temp_res,
        ):
            curve.setData([], [])
