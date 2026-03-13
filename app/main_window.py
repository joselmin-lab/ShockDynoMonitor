import serial.tools.list_ports
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.dashboard import DashboardWidget
from app.graphs import GraphsWidget
from app.serial_worker import SerialWorker

_DARK_QSS = """
QMainWindow, QWidget {
    background-color: #0d0d1a;
    color: #d0d0e0;
}
QComboBox {
    background: #1a1a2e;
    color: #d0d0e0;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 4px 8px;
    min-width: 110px;
}
QComboBox QAbstractItemView {
    background: #1a1a2e;
    color: #d0d0e0;
    selection-background-color: #2a2a4a;
}
QPushButton {
    background: #1e3a5f;
    color: #d0d0e0;
    border: 1px solid #3a6a9f;
    border-radius: 5px;
    padding: 6px 18px;
    font-weight: bold;
}
QPushButton:hover  { background: #2a5080; }
QPushButton:pressed { background: #16304f; }
QPushButton#btn_stop {
    background: #5f1e1e;
    border-color: #9f3a3a;
}
QPushButton#btn_stop:hover  { background: #802a2a; }
QPushButton#btn_stop:pressed { background: #4f1616; }
QStatusBar {
    background: #0d0d1a;
    color: #808099;
}
QSplitter::handle { background: #2a2a3a; }
QLabel#lbl_port {
    color: #a0a0c0;
    font-size: 13px;
}
"""


class MainWindow(QMainWindow):
    """Main application window for the Shock Dyno Monitor."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shock Dyno Monitor")
        self.resize(1200, 800)
        self.setStyleSheet(_DARK_QSS)

        self._worker: SerialWorker | None = None

        # ── Central widget ───────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setSpacing(8)
        root_layout.setContentsMargins(10, 10, 10, 6)

        # ── Toolbar row ──────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        lbl_port = QLabel("Puerto COM:")
        lbl_port.setObjectName("lbl_port")
        toolbar.addWidget(lbl_port)

        self._combo_port = QComboBox()
        self._refresh_ports()
        toolbar.addWidget(self._combo_port)

        self._btn_refresh = QPushButton("↺")
        self._btn_refresh.setFixedWidth(32)
        self._btn_refresh.setToolTip("Refrescar puertos")
        self._btn_refresh.clicked.connect(self._refresh_ports)
        toolbar.addWidget(self._btn_refresh)

        self._btn_start = QPushButton("▶  Conectar")
        self._btn_start.clicked.connect(self._start)
        toolbar.addWidget(self._btn_start)

        self._btn_stop = QPushButton("■  Detener")
        self._btn_stop.setObjectName("btn_stop")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop)
        toolbar.addWidget(self._btn_stop)

        toolbar.addStretch()
        root_layout.addLayout(toolbar)

        # ── Dashboard (LCD values) ───────────────────────────────────────
        self._dashboard = DashboardWidget()
        root_layout.addWidget(self._dashboard)

        # ── Graphs ──────────────────────────────────────────────────────
        self._graphs = GraphsWidget()
        root_layout.addWidget(self._graphs, stretch=1)

        # ── Status bar ──────────────────────────────────────────────────
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Desconectado")

    # ------------------------------------------------------------------
    def _refresh_ports(self):
        self._combo_port.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if ports:
            self._combo_port.addItems(ports)
        else:
            self._combo_port.addItem("(ninguno)")

    def _start(self):
        port = self._combo_port.currentText()
        if not port or port == "(ninguno)":
            QMessageBox.warning(self, "Puerto inválido", "Selecciona un puerto COM válido.")
            return

        self._graphs.clear_plots()

        self._worker = SerialWorker(port)
        self._worker.data_received.connect(self._on_data)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._combo_port.setEnabled(False)
        self._btn_refresh.setEnabled(False)
        self._status.showMessage(f"Conectado a {port} — esperando datos…")

    def _stop(self):
        if self._worker:
            self._worker.stop()
            self._worker = None
        self._set_disconnected_ui()

    def _on_data(self, fuerza: float, recorrido: float, temp_amo: float, temp_res: float, rpm: int):
        self._dashboard.update_values(fuerza, recorrido, temp_amo, temp_res, rpm)
        self._graphs.update_values(fuerza, recorrido, temp_amo, temp_res, rpm)
        self._status.showMessage(
            f"Fuerza: {fuerza:.1f} N  |  Recorrido: {recorrido:.1f} mm  |  "
            f"T.Amo: {temp_amo:.1f} °C  |  T.Res: {temp_res:.1f} °C  |  {rpm} RPM"
        )

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "Error serie", msg)
        self._set_disconnected_ui()

    def _on_worker_finished(self):
        self._set_disconnected_ui()

    def _set_disconnected_ui(self):
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._combo_port.setEnabled(True)
        self._btn_refresh.setEnabled(True)
        self._status.showMessage("Desconectado")

    def closeEvent(self, event):
        if self._worker:
            self._worker.stop()
        event.accept()
