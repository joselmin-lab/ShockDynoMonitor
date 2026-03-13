"""Dialog for configuring persistent graph axis limits for all three plots."""

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.calibration import load_graph_settings, save_graph_settings


class GraphSettingsDialog(QDialog):
    """Modal dialog to configure min/max axis limits for each graph.

    Each axis field has an 'Auto' checkbox; when checked the axis uses
    pyqtgraph's built-in auto-range and the spinbox is disabled.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar Gráficos")
        self.setMinimumWidth(430)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._settings = load_graph_settings()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel(
            "Define los límites de los ejes para cada gráfico.\n"
            "Marca 'Auto' para que el gráfico ajuste la escala automáticamente."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #a0a0c0; font-size: 12px;")
        layout.addWidget(hint)

        # ── Fuerza vs Recorrido ───────────────────────────────────────────
        grp_fvr = QGroupBox("Fuerza vs Recorrido")
        grp_fvr.setStyleSheet(
            "QGroupBox { color: #00e5ff; border: 1px solid #00e5ff; "
            "border-radius: 4px; margin-top: 6px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
        )
        fvr_form = QFormLayout(grp_fvr)
        fvr_form.setLabelAlignment(Qt.AlignRight)

        self._fvr_x_min_auto, self._fvr_x_min = self._make_pair(-9999.0, 9999.0, 1)
        self._fvr_x_max_auto, self._fvr_x_max = self._make_pair(-9999.0, 9999.0, 1)
        self._fvr_y_min_auto, self._fvr_y_min = self._make_pair(-99999.0, 99999.0, 0)
        self._fvr_y_max_auto, self._fvr_y_max = self._make_pair(-99999.0, 99999.0, 0)

        fvr_form.addRow("X Mín (mm):", self._row(self._fvr_x_min_auto, self._fvr_x_min))
        fvr_form.addRow("X Máx (mm):", self._row(self._fvr_x_max_auto, self._fvr_x_max))
        fvr_form.addRow("Y Mín  (N):", self._row(self._fvr_y_min_auto, self._fvr_y_min))
        fvr_form.addRow("Y Máx  (N):", self._row(self._fvr_y_max_auto, self._fvr_y_max))
        layout.addWidget(grp_fvr)

        self._load("fvr_x_min", self._fvr_x_min_auto, self._fvr_x_min)
        self._load("fvr_x_max", self._fvr_x_max_auto, self._fvr_x_max)
        self._load("fvr_y_min", self._fvr_y_min_auto, self._fvr_y_min)
        self._load("fvr_y_max", self._fvr_y_max_auto, self._fvr_y_max)

        # ── Temperaturas vs Tiempo ────────────────────────────────────────
        grp_temp = QGroupBox("Temperaturas vs Tiempo")
        grp_temp.setStyleSheet(
            "QGroupBox { color: #ff9100; border: 1px solid #ff9100; "
            "border-radius: 4px; margin-top: 6px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
        )
        temp_form = QFormLayout(grp_temp)
        temp_form.setLabelAlignment(Qt.AlignRight)

        self._temp_y_min_auto, self._temp_y_min = self._make_pair(-50.0, 999.0, 1)
        self._temp_y_max_auto, self._temp_y_max = self._make_pair(-50.0, 999.0, 1)

        temp_form.addRow("Y Mín (°C):", self._row(self._temp_y_min_auto, self._temp_y_min))
        temp_form.addRow("Y Máx (°C):", self._row(self._temp_y_max_auto, self._temp_y_max))
        layout.addWidget(grp_temp)

        self._load("temp_y_min", self._temp_y_min_auto, self._temp_y_min)
        self._load("temp_y_max", self._temp_y_max_auto, self._temp_y_max)

        # ── Distancia vs Tiempo ───────────────────────────────────────────
        grp_dist = QGroupBox("Distancia vs Tiempo")
        grp_dist.setStyleSheet(
            "QGroupBox { color: #69ff47; border: 1px solid #69ff47; "
            "border-radius: 4px; margin-top: 6px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
        )
        dist_form = QFormLayout(grp_dist)
        dist_form.setLabelAlignment(Qt.AlignRight)

        self._dist_y_min_auto, self._dist_y_min = self._make_pair(-100.0, 9999.0, 1)
        self._dist_y_max_auto, self._dist_y_max = self._make_pair(-100.0, 9999.0, 1)

        dist_form.addRow("Y Mín (mm):", self._row(self._dist_y_min_auto, self._dist_y_min))
        dist_form.addRow("Y Máx (mm):", self._row(self._dist_y_max_auto, self._dist_y_max))
        layout.addWidget(grp_dist)

        self._load("dist_y_min", self._dist_y_min_auto, self._dist_y_min)
        self._load("dist_y_max", self._dist_y_max_auto, self._dist_y_max)

        # ── Buttons ───────────────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Guardar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    @staticmethod
    def _make_pair(
        range_min: float, range_max: float, decimals: int
    ) -> tuple[QCheckBox, QDoubleSpinBox]:
        """Return an (Auto checkbox, spinbox) pair. Spinbox is disabled while Auto is checked."""
        chk = QCheckBox("Auto")
        chk.setChecked(True)
        sb = QDoubleSpinBox()
        sb.setRange(range_min, range_max)
        sb.setDecimals(decimals)
        sb.setSingleStep(1.0)
        sb.setEnabled(False)
        chk.toggled.connect(lambda checked: sb.setEnabled(not checked))
        return chk, sb

    @staticmethod
    def _row(chk: QCheckBox, sb: QDoubleSpinBox) -> QWidget:
        """Pack a checkbox and a spinbox side-by-side into a QWidget."""
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(chk)
        row.addWidget(sb)
        return w

    def _load(self, key: str, chk: QCheckBox, sb: QDoubleSpinBox) -> None:
        """Populate *chk* and *sb* from the loaded settings."""
        val: Optional[float] = self._settings.get(key)
        if val is None:
            chk.setChecked(True)
            sb.setEnabled(False)
        else:
            chk.setChecked(False)
            sb.setEnabled(True)
            sb.setValue(val)

    def _collect(self, key: str, chk: QCheckBox, sb: QDoubleSpinBox) -> None:
        """Write the widget values back to ``self._settings``."""
        self._settings[key] = None if chk.isChecked() else sb.value()

    # ------------------------------------------------------------------
    def _accept(self) -> None:
        self._collect("fvr_x_min", self._fvr_x_min_auto, self._fvr_x_min)
        self._collect("fvr_x_max", self._fvr_x_max_auto, self._fvr_x_max)
        self._collect("fvr_y_min", self._fvr_y_min_auto, self._fvr_y_min)
        self._collect("fvr_y_max", self._fvr_y_max_auto, self._fvr_y_max)
        self._collect("temp_y_min", self._temp_y_min_auto, self._temp_y_min)
        self._collect("temp_y_max", self._temp_y_max_auto, self._temp_y_max)
        self._collect("dist_y_min", self._dist_y_min_auto, self._dist_y_min)
        self._collect("dist_y_max", self._dist_y_max_auto, self._dist_y_max)
        save_graph_settings(self._settings)
        self.accept()

    def graph_settings(self) -> dict:
        """Return the settings dict (only valid after the dialog is accepted)."""
        return dict(self._settings)
