"""Calibration dialog – lets the user adjust sensor offsets and PMI/PMS for distance,
as well as tare and known-weight calibration for the force sensor (AD623 or HX711)."""

from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.calibration import load_calibration, save_calibration


class CalibrationDialog(QDialog):
    """Modal dialog for editing calibration parameters."""

    def __init__(
        self,
        parent=None,
        get_raw_distance: Optional[Callable[[], Optional[int]]] = None,
        get_raw_force: Optional[Callable[[], Optional[int]]] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Calibración de sensores")
        self.setMinimumWidth(450)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._cal = load_calibration()
        self._get_raw_distance = get_raw_distance
        self._get_raw_force = get_raw_force

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

        # Temperature offsets
        self._sb_temp_amo = _spinbox(-50.0, 50.0, 1, self._cal["temp_amo_offset"])
        self._sb_temp_res = _spinbox(-50.0, 50.0, 1, self._cal["temp_res_offset"])
        form.addRow("Offset Temp. Amortiguador (°C):", self._sb_temp_amo)
        form.addRow("Offset Temp. Reservorio (°C):", self._sb_temp_res)

        # Stroke length
        self._sb_stroke = _spinbox(1.0, 1000.0, 1, self._cal["stroke_length_mm"])
        form.addRow("Longitud de recorrido (mm):", self._sb_stroke)

        layout.addLayout(form)

        # ── PMI / PMS capture ─────────────────────────────────────────────
        pmi_pms_hint = QLabel(
            "Mueve el amortiguador hasta el punto deseado y pulsa 'Capturar'.\n"
            "Requiere conexión activa con el Arduino."
        )
        pmi_pms_hint.setWordWrap(True)
        pmi_pms_hint.setStyleSheet("color: #a0a0c0; font-size: 12px;")
        layout.addWidget(pmi_pms_hint)

        # PMI row
        pmi_row = QHBoxLayout()
        self._lbl_pmi = QLabel(f"PMI (0 mm) — raw actual: {int(self._cal['raw_pmi'])}")
        self._lbl_pmi.setStyleSheet("color: #69ff47;")
        pmi_row.addWidget(self._lbl_pmi)
        pmi_row.addStretch()
        btn_pmi = QPushButton("Capturar PMI (0 mm)")
        btn_pmi.clicked.connect(self._capture_pmi)
        pmi_row.addWidget(btn_pmi)
        layout.addLayout(pmi_row)

        # PMS row
        pms_row = QHBoxLayout()
        self._lbl_pms = QLabel(f"PMS ({int(self._cal['stroke_length_mm'])} mm) — raw actual: {int(self._cal['raw_pms'])}")
        self._lbl_pms.setStyleSheet("color: #ff9100;")
        pms_row.addWidget(self._lbl_pms)
        pms_row.addStretch()
        btn_pms = QPushButton("Capturar PMS (máx. mm)")
        btn_pms.clicked.connect(self._capture_pms)
        pms_row.addWidget(btn_pms)
        layout.addLayout(pms_row)

        # ── Force calibration (AD623 / analog 0-1023) ─────────────────────
        force_section_lbl = QLabel("— Calibración de Fuerza (AD623) —")
        force_section_lbl.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px; margin-top: 6px;")
        force_section_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(force_section_lbl)

        force_hint = QLabel(
            "1. Sin ninguna carga, pulsa 'Capturar Tara (Cero)'.\n"
            "2. Aplica una fuerza conocida y pulsa 'Capturar Peso Conocido'.\n"
            "3. Introduce la fuerza fisica en Newtons.\n"
            "Formula: F(N) = (raw - tara) * (F_conocida / (raw_conocido - tara))"
        )
        force_hint.setWordWrap(True)
        force_hint.setStyleSheet("color: #a0a0c0; font-size: 12px;")
        layout.addWidget(force_hint)

        # Tare (zero) row
        tare_row = QHBoxLayout()
        self._lbl_force_tare = QLabel(f"Tara — raw actual: {int(self._cal['force_zero_raw'])}")
        self._lbl_force_tare.setStyleSheet("color: #69ff47;")
        tare_row.addWidget(self._lbl_force_tare)
        tare_row.addStretch()
        btn_tare = QPushButton("Capturar Tara (Cero)")
        btn_tare.clicked.connect(self._capture_force_tare)
        tare_row.addWidget(btn_tare)
        layout.addLayout(tare_row)

        # Known weight row
        known_row = QHBoxLayout()
        self._lbl_force_known = QLabel(f"Peso conocido — raw actual: {int(self._cal['force_known_raw'])}")
        self._lbl_force_known.setStyleSheet("color: #ff9100;")
        known_row.addWidget(self._lbl_force_known)
        known_row.addStretch()
        btn_known = QPushButton("Capturar Peso Conocido")
        btn_known.clicked.connect(self._capture_force_known)
        known_row.addWidget(btn_known)
        layout.addLayout(known_row)

        # Physical force value
        force_form = QFormLayout()
        force_form.setLabelAlignment(Qt.AlignRight)
        self._sb_force_known_n = _spinbox(0.1, 100000.0, 1, self._cal["force_known_physical_n"])
        force_form.addRow("Fuerza conocida (N):", self._sb_force_known_n)
        layout.addLayout(force_form)

        # ── Buttons ───────────────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _get_current_raw(self) -> Optional[int]:
        """Return the current raw distance value, or None if unavailable."""
        if self._get_raw_distance is None:
            return None
        return self._get_raw_distance()

    def _get_current_raw_force(self) -> Optional[int]:
        """Return the current raw force value, or None if unavailable."""
        if self._get_raw_force is None:
            return None
        return self._get_raw_force()

    def _capture_pmi(self):
        raw = self._get_current_raw()
        if raw is None:
            self._lbl_pmi.setText("PMI — sin conexión activa")
            return
        self._cal["raw_pmi"] = float(raw)
        self._lbl_pmi.setText(f"PMI (0 mm) — raw capturado: {raw}")

    def _capture_pms(self):
        raw = self._get_current_raw()
        if raw is None:
            self._lbl_pms.setText("PMS — sin conexión activa")
            return
        self._cal["raw_pms"] = float(raw)
        stroke = int(self._sb_stroke.value())
        self._lbl_pms.setText(f"PMS ({stroke} mm) — raw capturado: {raw}")

    def _capture_force_tare(self):
        raw = self._get_current_raw_force()
        if raw is None:
            self._lbl_force_tare.setText("Tara — sin conexión activa")
            return
        self._cal["force_zero_raw"] = float(raw)
        self._lbl_force_tare.setText(f"Tara — raw capturado: {raw}")

    def _capture_force_known(self):
        raw = self._get_current_raw_force()
        if raw is None:
            self._lbl_force_known.setText("Peso conocido — sin conexión activa")
            return
        self._cal["force_known_raw"] = float(raw)
        self._lbl_force_known.setText(f"Peso conocido — raw capturado: {raw}")

    # ------------------------------------------------------------------
    def _accept(self):
        self._cal["temp_amo_offset"] = self._sb_temp_amo.value()
        self._cal["temp_res_offset"] = self._sb_temp_res.value()
        self._cal["stroke_length_mm"] = self._sb_stroke.value()
        self._cal["force_known_physical_n"] = self._sb_force_known_n.value()
        save_calibration(self._cal)
        self.accept()

    def calibration_values(self) -> dict:
        """Return the calibration dict (only valid after the dialog is accepted)."""
        return dict(self._cal)
