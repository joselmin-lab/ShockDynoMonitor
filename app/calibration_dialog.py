"""Calibration dialog – lets the user adjust sensor offsets and multipliers."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from app.calibration import load_calibration, save_calibration


class CalibrationDialog(QDialog):
    """Modal dialog for editing calibration parameters."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibración de sensores")
        self.setMinimumWidth(360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._cal = load_calibration()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Description ──────────────────────────────────────────────────
        hint = QLabel(
            "Ajusta los valores hasta que las lecturas coincidan con referencias conocidas.\n"
            "Los cambios se guardan automáticamente al aceptar."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #a0a0c0; font-size: 12px;")
        layout.addWidget(hint)

        # ── Form fields ───────────────────────────────────────────────────
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(10)

        def _spinbox(min_val: float, max_val: float, decimals: int, value: float) -> QDoubleSpinBox:
            sb = QDoubleSpinBox()
            sb.setRange(min_val, max_val)
            sb.setDecimals(decimals)
            sb.setSingleStep(0.1)
            sb.setValue(value)
            return sb

        self._sb_temp_amo = _spinbox(-50.0, 50.0, 1, self._cal["temp_amo_offset"])
        self._sb_temp_res = _spinbox(-50.0, 50.0, 1, self._cal["temp_res_offset"])
        self._sb_dist_mul = _spinbox(0.01, 10.0, 3, self._cal["dist_multiplier"])
        self._sb_dist_off = _spinbox(-500.0, 500.0, 1, self._cal["dist_offset"])

        form.addRow("Offset Temp. Amortiguador (°C):", self._sb_temp_amo)
        form.addRow("Offset Temp. Reservorio (°C):", self._sb_temp_res)
        form.addRow("Multiplicador Recorrido:", self._sb_dist_mul)
        form.addRow("Offset Recorrido (mm):", self._sb_dist_off)

        layout.addLayout(form)

        # ── Buttons ───────────────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _accept(self):
        self._cal["temp_amo_offset"] = self._sb_temp_amo.value()
        self._cal["temp_res_offset"] = self._sb_temp_res.value()
        self._cal["dist_multiplier"] = self._sb_dist_mul.value()
        self._cal["dist_offset"] = self._sb_dist_off.value()
        save_calibration(self._cal)
        self.accept()

    def calibration_values(self) -> dict:
        """Return the calibration dict (only valid after the dialog is accepted)."""
        return dict(self._cal)
