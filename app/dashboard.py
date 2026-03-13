from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGridLayout, QLabel, QWidget

_FIELDS = [
    ("Fuerza", "N"),
    ("Recorrido", "mm"),
    ("Temp Amortiguador", "°C"),
    ("Temp Reservorio", "°C"),
    ("RPM", ""),
]

_LABEL_STYLE = """
    QLabel {{
        color: {color};
        font-size: 42px;
        font-weight: bold;
        font-family: 'Courier New', monospace;
        background: #1a1a2e;
        border: 1px solid #333;
        border-radius: 6px;
        padding: 6px 14px;
        min-width: 160px;
    }}
"""

_TITLE_STYLE = """
    QLabel {
        color: #a0a0c0;
        font-size: 13px;
        font-weight: bold;
        letter-spacing: 1px;
    }
"""

_UNIT_STYLE = """
    QLabel {
        color: #606080;
        font-size: 13px;
    }
"""


class DashboardWidget(QWidget):
    """Displays the 5 sensor values as large LCD-style numeric readouts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value_labels: list[QLabel] = []

        layout = QGridLayout(self)
        layout.setSpacing(12)

        colors = ["#00e5ff", "#69ff47", "#ff9100", "#ff9100", "#e040fb"]

        for col, (title, unit) in enumerate(_FIELDS):
            title_lbl = QLabel(title.upper())
            title_lbl.setStyleSheet(_TITLE_STYLE)
            title_lbl.setAlignment(Qt.AlignCenter)

            val_lbl = QLabel("—")
            val_lbl.setStyleSheet(_LABEL_STYLE.format(color=colors[col]))
            val_lbl.setAlignment(Qt.AlignCenter)

            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet(_UNIT_STYLE)
            unit_lbl.setAlignment(Qt.AlignCenter)

            layout.addWidget(title_lbl, 0, col)
            layout.addWidget(val_lbl, 1, col)
            layout.addWidget(unit_lbl, 2, col)

            self._value_labels.append(val_lbl)

    def update_values(
        self,
        fuerza: float,
        recorrido: float,
        temp_amo: float,
        temp_res: float,
        rpm: int,
    ):
        values = [f"{fuerza:.1f}", f"{recorrido:.1f}", f"{temp_amo:.1f}", f"{temp_res:.1f}", str(rpm)]
        for lbl, val in zip(self._value_labels, values):
            lbl.setText(val)
