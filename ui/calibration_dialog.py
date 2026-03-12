"""
Módulo: calibration_dialog.py
Descripción: Diálogo interactivo para calibración de sensores del banco de pruebas.

Permite calibrar:
    - Fuerza: tarar (poner a cero con la lectura actual)
    - Recorrido: capturar punto inferior y superior para mapear el rango físico
    - Temperatura amortiguador: ajuste de offset de corrección
    - Temperatura reservorio: ajuste de offset de corrección

Los cambios se aplican al aceptar el diálogo y se propagan al parser
a través del SerialManager para efecto inmediato.
"""

import logging
from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.data_parser import ShockDynoData

# Logger del módulo
logger = logging.getLogger(__name__)

ESTILO_DIALOGO = """
    QDialog {
        background-color: #2b2b2b;
        color: #ffffff;
    }
    QGroupBox {
        color: #ccc;
        border: 1px solid #555;
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 8px;
    }
    QGroupBox::title {
        color: #aaa;
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
    }
    QLabel {
        color: #ccc;
    }
    QDoubleSpinBox {
        background: #333;
        color: #fff;
        border: 1px solid #555;
        border-radius: 3px;
        padding: 3px;
    }
    QPushButton {
        background: #444;
        color: #fff;
        border: 1px solid #666;
        border-radius: 4px;
        padding: 5px 14px;
    }
    QPushButton:hover {
        background: #555;
    }
    QDialogButtonBox QPushButton {
        min-width: 80px;
    }
    QPushButton#btnTarar {
        background: #005599;
        color: #fff;
        font-weight: bold;
    }
    QPushButton#btnTarar:hover {
        background: #0066bb;
    }
    QPushButton#btnCapturar {
        background: #006633;
        color: #fff;
    }
    QPushButton#btnCapturar:hover {
        background: #008844;
    }
    QPushButton#btnReset {
        background: #553300;
        color: #fff;
    }
    QPushButton#btnReset:hover {
        background: #774400;
    }
"""


class CalibrationDialog(QDialog):
    """
    Diálogo interactivo de calibración de sensores del banco de pruebas.

    Permite calibrar cuatro magnitudes:

    **Fuerza (N)**
        - Muestra la lectura actual.
        - Botón *Tarar Fuerza*: ajusta el offset para que la lectura sea 0 N.
        - Campo de offset manual y factor de escala.

    **Recorrido (mm)**
        - Muestra la lectura actual.
        - Botón *Capturar Punto Inferior*: guarda el raw actual como mínimo (0 mm).
        - Botón *Capturar Punto Superior*: guarda el raw actual como máximo.
        - Campo de recorrido total en mm y botón *Calcular* que deriva
          la escala y el offset a partir de los dos puntos.

    **Temperatura Amortiguador y Reservorio (°C)**
        - Muestra la lectura actual.
        - Campo de corrección de offset (se suma al valor calculado).
        - Botón *Corregir con referencia*: pide la temperatura real medida
          con un termómetro de referencia y calcula la corrección automáticamente.

    Los valores editados se guardan en la configuración al pulsar *Aceptar*
    y se aplican al :class:`~core.data_parser.SpeeduinoDataParser` sin
    necesidad de reconectar.

    Ejemplo de uso::

        dialogo = CalibrationDialog(
            config=config,
            ultimo_dato=dato_actual,
            callback_lectura=serial_manager.obtener_ultimo_dato,
            parent=ventana_principal,
        )
        if dialogo.exec_() == QDialog.Accepted:
            nueva_config = dialogo.obtener_config_actualizada()
    """

    def __init__(
        self,
        config: dict,
        ultimo_dato: Optional[ShockDynoData] = None,
        callback_lectura: Optional[Callable[[], Optional[ShockDynoData]]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Inicializa el diálogo de calibración.

        Args:
            config: Configuración actual de la aplicación.
            ultimo_dato: Último :class:`~core.data_parser.ShockDynoData` recibido
                         para mostrar lecturas actuales.
            callback_lectura: Función sin argumentos que retorna el dato más reciente.
                              Se llama cuando el usuario pulsa un botón de captura.
            parent: Widget padre de Qt.
        """
        super().__init__(parent)
        self._config = config.copy()
        self._cfg_sensores = self._config.get("sensores", {})
        self._ultimo_dato = ultimo_dato
        self._callback_lectura = callback_lectura

        # Valores raw capturados para calibración de recorrido
        self._raw_inferior: Optional[float] = None
        self._raw_superior: Optional[float] = None

        # Correcciones iniciales de temperatura al abrir el diálogo.
        # Se usan como base para calcular la corrección con referencia,
        # evitando acumulación si se pulsa el botón varias veces en la misma sesión.
        self._correccion_inicial_amo: float = 0.0
        self._correccion_inicial_res: float = 0.0

        self.setWindowTitle("Calibración de Sensores - Shock Dyno Monitor")
        self.setMinimumWidth(500)
        self.setStyleSheet(ESTILO_DIALOGO)

        self._construir_ui()
        self._cargar_valores_actuales()

        logger.debug("CalibrationDialog inicializado.")

    # ─── Helpers ───────────────────────────────────────────────────────────

    def _obtener_dato_actual(self) -> Optional[ShockDynoData]:
        """Obtiene el dato más reciente del callback o del último almacenado."""
        if self._callback_lectura:
            dato = self._callback_lectura()
            if dato and dato.valido:
                self._ultimo_dato = dato
        return self._ultimo_dato

    # ─── Construcción de la UI ─────────────────────────────────────────────

    def _construir_ui(self) -> None:
        """Construye la interfaz del diálogo de calibración."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Nota informativa
        lbl_info = QLabel(
            "Calibre los sensores antes de iniciar una sesión de prueba.\n"
            "Los cambios se aplican al pulsar Aceptar."
        )
        lbl_info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(lbl_info)

        layout.addWidget(self._crear_grupo_fuerza())
        layout.addWidget(self._crear_grupo_recorrido())
        layout.addWidget(self._crear_grupo_temperaturas())

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

    def _crear_grupo_fuerza(self) -> QGroupBox:
        """Crea el grupo de calibración de fuerza."""
        grupo = QGroupBox("⚖ Fuerza")
        layout = QVBoxLayout(grupo)
        layout.setSpacing(6)

        # Lectura actual
        fila_lectura = QHBoxLayout()
        fila_lectura.addWidget(QLabel("Lectura actual:"))
        self._lbl_fuerza_actual = QLabel("— N")
        self._lbl_fuerza_actual.setStyleSheet(
            "color: #00cc44; font-weight: bold; font-size: 14px;"
        )
        fila_lectura.addWidget(self._lbl_fuerza_actual)
        fila_lectura.addStretch()
        layout.addLayout(fila_lectura)

        # Escala y offset
        form = QFormLayout()
        form.setSpacing(6)

        self._spin_fuerza_escala = QDoubleSpinBox()
        self._spin_fuerza_escala.setRange(0.001, 100.0)
        self._spin_fuerza_escala.setDecimals(4)
        self._spin_fuerza_escala.setToolTip(
            "Factor de escala: fuerza (N) = raw × escala + offset\n"
            "Valor por defecto: 0.5"
        )
        form.addRow("Escala:", self._spin_fuerza_escala)

        self._spin_fuerza_offset = QDoubleSpinBox()
        self._spin_fuerza_offset.setRange(-5000.0, 5000.0)
        self._spin_fuerza_offset.setDecimals(2)
        self._spin_fuerza_offset.setSuffix(" N")
        self._spin_fuerza_offset.setToolTip(
            "Offset de calibración de fuerza.\n"
            "El valor final es: raw × escala + offset"
        )
        form.addRow("Offset (N):", self._spin_fuerza_offset)

        layout.addLayout(form)

        # Botones
        fila_botones = QHBoxLayout()

        btn_tarar = QPushButton("⬛ Tarar Fuerza (→ 0 N)")
        btn_tarar.setObjectName("btnTarar")
        btn_tarar.setToolTip(
            "Ajusta el offset para que la lectura actual sea exactamente 0 N.\n"
            "Use cuando no haya carga aplicada (celda de carga en reposo)."
        )
        btn_tarar.clicked.connect(self._tarar_fuerza)
        fila_botones.addWidget(btn_tarar)

        btn_reset_fuerza = QPushButton("↺ Restablecer")
        btn_reset_fuerza.setObjectName("btnReset")
        btn_reset_fuerza.setToolTip("Restablecer calibración de fuerza a valores por defecto.")
        btn_reset_fuerza.clicked.connect(self._reset_fuerza)
        fila_botones.addWidget(btn_reset_fuerza)

        layout.addLayout(fila_botones)
        return grupo

    def _crear_grupo_recorrido(self) -> QGroupBox:
        """Crea el grupo de calibración de recorrido (distancia)."""
        grupo = QGroupBox("📏 Recorrido")
        layout = QVBoxLayout(grupo)
        layout.setSpacing(6)

        # Lectura actual
        fila_lectura = QHBoxLayout()
        fila_lectura.addWidget(QLabel("Lectura actual:"))
        self._lbl_recorrido_actual = QLabel("— mm")
        self._lbl_recorrido_actual.setStyleSheet(
            "color: #00cc44; font-weight: bold; font-size: 14px;"
        )
        fila_lectura.addWidget(self._lbl_recorrido_actual)
        fila_lectura.addStretch()
        layout.addLayout(fila_lectura)

        # Instrucciones
        lbl_instrucciones = QLabel(
            "Procedimiento de calibración de rango:\n"
            "  1. Mueva el amortiguador al punto más bajo y pulse ↓ Capturar Inferior\n"
            "  2. Mueva el amortiguador al punto más alto y pulse ↑ Capturar Superior\n"
            "  3. Ingrese el recorrido físico total y pulse ⚙ Calcular"
        )
        lbl_instrucciones.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(lbl_instrucciones)

        # Estado de puntos capturados
        fila_puntos = QHBoxLayout()
        self._lbl_punto_inf = QLabel("Punto inferior: no capturado")
        self._lbl_punto_inf.setStyleSheet("color: #aaa;")
        fila_puntos.addWidget(self._lbl_punto_inf)
        self._lbl_punto_sup = QLabel("Punto superior: no capturado")
        self._lbl_punto_sup.setStyleSheet("color: #aaa;")
        fila_puntos.addWidget(self._lbl_punto_sup)
        layout.addLayout(fila_puntos)

        # Botones de captura
        fila_captura = QHBoxLayout()

        btn_capturar_inf = QPushButton("↓ Capturar Punto Inferior")
        btn_capturar_inf.setObjectName("btnCapturar")
        btn_capturar_inf.setToolTip("Captura la posición actual como punto inferior (0 mm)")
        btn_capturar_inf.clicked.connect(self._capturar_punto_inferior)
        fila_captura.addWidget(btn_capturar_inf)

        btn_capturar_sup = QPushButton("↑ Capturar Punto Superior")
        btn_capturar_sup.setObjectName("btnCapturar")
        btn_capturar_sup.setToolTip("Captura la posición actual como punto superior (= recorrido total mm)")
        btn_capturar_sup.clicked.connect(self._capturar_punto_superior)
        fila_captura.addWidget(btn_capturar_sup)

        layout.addLayout(fila_captura)

        # Recorrido total + Calcular
        form = QFormLayout()
        form.setSpacing(6)

        fila_recorrido = QHBoxLayout()
        self._spin_recorrido_total = QDoubleSpinBox()
        self._spin_recorrido_total.setRange(1.0, 500.0)
        self._spin_recorrido_total.setDecimals(1)
        self._spin_recorrido_total.setSuffix(" mm")
        self._spin_recorrido_total.setValue(100.0)
        self._spin_recorrido_total.setToolTip("Recorrido físico total del amortiguador en mm")
        fila_recorrido.addWidget(self._spin_recorrido_total)

        btn_calcular = QPushButton("⚙ Calcular")
        btn_calcular.setToolTip("Calcula escala y offset a partir de los puntos capturados")
        btn_calcular.clicked.connect(self._calcular_calibracion_recorrido)
        fila_recorrido.addWidget(btn_calcular)

        form.addRow("Recorrido total:", fila_recorrido)

        self._spin_recorrido_escala = QDoubleSpinBox()
        self._spin_recorrido_escala.setRange(0.001, 10.0)
        self._spin_recorrido_escala.setDecimals(6)
        self._spin_recorrido_escala.setToolTip(
            "Factor de escala calculado: recorrido (mm) = raw × escala + offset"
        )
        form.addRow("Escala calculada:", self._spin_recorrido_escala)

        self._spin_recorrido_offset = QDoubleSpinBox()
        self._spin_recorrido_offset.setRange(-500.0, 500.0)
        self._spin_recorrido_offset.setDecimals(3)
        self._spin_recorrido_offset.setSuffix(" mm")
        self._spin_recorrido_offset.setToolTip(
            "Offset calculado: recorrido (mm) = raw × escala + offset"
        )
        form.addRow("Offset calculado:", self._spin_recorrido_offset)

        layout.addLayout(form)

        btn_reset = QPushButton("↺ Restablecer")
        btn_reset.setObjectName("btnReset")
        btn_reset.setToolTip("Restablecer calibración de recorrido a valores por defecto.")
        btn_reset.clicked.connect(self._reset_recorrido)
        layout.addWidget(btn_reset)

        return grupo

    def _crear_grupo_temperaturas(self) -> QGroupBox:
        """Crea el grupo de calibración de temperaturas."""
        grupo = QGroupBox("🌡 Temperaturas")
        layout = QVBoxLayout(grupo)
        layout.setSpacing(8)

        # ── Amortiguador ──────────────────────────────────────────────────
        lbl_amo = QLabel("Temperatura Amortiguador")
        lbl_amo.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_amo)

        fila_amo = QHBoxLayout()
        fila_amo.addWidget(QLabel("Lectura actual:"))
        self._lbl_temp_amo_actual = QLabel("— °C")
        self._lbl_temp_amo_actual.setStyleSheet(
            "color: #00cc44; font-weight: bold; font-size: 13px;"
        )
        fila_amo.addWidget(self._lbl_temp_amo_actual)
        fila_amo.addStretch()
        layout.addLayout(fila_amo)

        form_amo = QFormLayout()
        form_amo.setSpacing(4)

        self._spin_temp_amo_correccion = QDoubleSpinBox()
        self._spin_temp_amo_correccion.setRange(-100.0, 100.0)
        self._spin_temp_amo_correccion.setDecimals(1)
        self._spin_temp_amo_correccion.setSuffix(" °C")
        self._spin_temp_amo_correccion.setToolTip(
            "Corrección de temperatura: se suma a la lectura del sensor.\n"
            "Positivo si el sensor lee por debajo de la temperatura real."
        )
        form_amo.addRow("Corrección (°C):", self._spin_temp_amo_correccion)

        layout.addLayout(form_amo)

        btn_ref_amo = QPushButton("🎯 Corregir con temperatura de referencia...")
        btn_ref_amo.setToolTip(
            "Ingrese la temperatura real medida con un termómetro de referencia\n"
            "y el sistema calculará la corrección automáticamente."
        )
        btn_ref_amo.clicked.connect(lambda: self._corregir_con_referencia("amortiguador"))
        layout.addWidget(btn_ref_amo)

        # ── Reservorio ────────────────────────────────────────────────────
        lbl_res = QLabel("Temperatura Reservorio")
        lbl_res.setStyleSheet("font-weight: bold; margin-top: 6px;")
        layout.addWidget(lbl_res)

        fila_res = QHBoxLayout()
        fila_res.addWidget(QLabel("Lectura actual:"))
        self._lbl_temp_res_actual = QLabel("— °C")
        self._lbl_temp_res_actual.setStyleSheet(
            "color: #00cc44; font-weight: bold; font-size: 13px;"
        )
        fila_res.addWidget(self._lbl_temp_res_actual)
        fila_res.addStretch()
        layout.addLayout(fila_res)

        form_res = QFormLayout()
        form_res.setSpacing(4)

        self._spin_temp_res_correccion = QDoubleSpinBox()
        self._spin_temp_res_correccion.setRange(-100.0, 100.0)
        self._spin_temp_res_correccion.setDecimals(1)
        self._spin_temp_res_correccion.setSuffix(" °C")
        self._spin_temp_res_correccion.setToolTip(
            "Corrección de temperatura: se suma a la lectura del sensor.\n"
            "Positivo si el sensor lee por debajo de la temperatura real."
        )
        form_res.addRow("Corrección (°C):", self._spin_temp_res_correccion)

        layout.addLayout(form_res)

        btn_ref_res = QPushButton("🎯 Corregir con temperatura de referencia...")
        btn_ref_res.setToolTip(
            "Ingrese la temperatura real medida con un termómetro de referencia\n"
            "y el sistema calculará la corrección automáticamente."
        )
        btn_ref_res.clicked.connect(lambda: self._corregir_con_referencia("reservorio"))
        layout.addWidget(btn_ref_res)

        btn_reset_temp = QPushButton("↺ Restablecer Temperaturas")
        btn_reset_temp.setObjectName("btnReset")
        btn_reset_temp.setToolTip("Elimina todas las correcciones de temperatura.")
        btn_reset_temp.clicked.connect(self._reset_temperaturas)
        layout.addWidget(btn_reset_temp)

        return grupo

    # ─── Carga de valores actuales ─────────────────────────────────────────

    def _cargar_valores_actuales(self) -> None:
        """Carga los valores de calibración actuales desde la configuración."""
        cfg_fuerza = self._cfg_sensores.get("fuerza", {})
        self._spin_fuerza_escala.setValue(cfg_fuerza.get("escala", 0.5))
        self._spin_fuerza_offset.setValue(cfg_fuerza.get("offset_valor", 0.0))

        cfg_recorrido = self._cfg_sensores.get("recorrido", {})
        self._spin_recorrido_escala.setValue(cfg_recorrido.get("escala", 0.392157))
        self._spin_recorrido_offset.setValue(cfg_recorrido.get("offset_valor", 0.0))

        # Las correcciones de temperatura son el delta sobre el offset base -40.
        # Se guardan como valores iniciales para que el cálculo de referencia
        # no acumule incorrectamente si el usuario pulsa el botón varias veces.
        cfg_temp_amo = self._cfg_sensores.get("temp_amortiguador", {})
        offset_amo = cfg_temp_amo.get("offset_valor", -40.0)
        self._correccion_inicial_amo = offset_amo + 40.0
        self._spin_temp_amo_correccion.setValue(self._correccion_inicial_amo)

        cfg_temp_res = self._cfg_sensores.get("temp_reservorio", {})
        offset_res = cfg_temp_res.get("offset_valor", -40.0)
        self._correccion_inicial_res = offset_res + 40.0
        self._spin_temp_res_correccion.setValue(self._correccion_inicial_res)

        self._actualizar_lecturas()

    def _actualizar_lecturas(self) -> None:
        """Actualiza las etiquetas de lectura actual con el último dato disponible."""
        dato = self._obtener_dato_actual()
        if dato and dato.valido:
            self._lbl_fuerza_actual.setText(f"{dato.fuerza_n:.2f} N")
            self._lbl_recorrido_actual.setText(f"{dato.recorrido_mm:.2f} mm")
            self._lbl_temp_amo_actual.setText(f"{dato.temp_amortiguador_c:.1f} °C")
            self._lbl_temp_res_actual.setText(f"{dato.temp_reservorio_c:.1f} °C")
        else:
            sin_datos = "sin datos"
            self._lbl_fuerza_actual.setText(sin_datos)
            self._lbl_recorrido_actual.setText(sin_datos)
            self._lbl_temp_amo_actual.setText(sin_datos)
            self._lbl_temp_res_actual.setText(sin_datos)

    # ─── Acciones de calibración de fuerza ────────────────────────────────

    def _tarar_fuerza(self) -> None:
        """Ajusta el offset de fuerza para que la lectura actual sea 0 N."""
        dato = self._obtener_dato_actual()
        if not dato or not dato.valido:
            QMessageBox.warning(
                self,
                "Sin datos",
                "No hay lectura de fuerza disponible.\n"
                "Asegúrese de estar conectado al equipo.",
            )
            return

        escala = self._spin_fuerza_escala.value()
        offset_actual = self._spin_fuerza_offset.value()

        # fuerza_leida = raw × escala + offset_actual
        # raw = (fuerza_leida - offset_actual) / escala
        # Para que fuerza = 0: nuevo_offset = -raw × escala
        fuerza_leida = dato.fuerza_n
        if escala != 0:
            raw = (fuerza_leida - offset_actual) / escala
            nuevo_offset = -(raw * escala)
        else:
            nuevo_offset = 0.0

        self._spin_fuerza_offset.setValue(round(nuevo_offset, 2))
        self._lbl_fuerza_actual.setText("0.00 N (tarado)")
        logger.info(
            f"Tara de fuerza aplicada: offset={nuevo_offset:.2f} N "
            f"(lectura previa: {fuerza_leida:.2f} N)"
        )

    def _reset_fuerza(self) -> None:
        """Restablece la calibración de fuerza a los valores por defecto."""
        self._spin_fuerza_escala.setValue(0.5)
        self._spin_fuerza_offset.setValue(0.0)
        self._actualizar_lecturas()
        logger.debug("Calibración de fuerza restablecida.")

    # ─── Acciones de calibración de recorrido ─────────────────────────────

    def _obtener_raw_recorrido(self) -> Optional[float]:
        """Calcula el valor raw del recorrido a partir de la lectura actual."""
        dato = self._obtener_dato_actual()
        if not dato or not dato.valido:
            return None
        escala = self._spin_recorrido_escala.value()
        offset = self._spin_recorrido_offset.value()
        if escala == 0:
            return None
        raw = (dato.recorrido_mm - offset) / escala
        return max(0.0, min(255.0, raw))

    def _capturar_punto_inferior(self) -> None:
        """Captura la posición actual como punto inferior del recorrido (0 mm)."""
        dato = self._obtener_dato_actual()
        if not dato or not dato.valido:
            QMessageBox.warning(
                self,
                "Sin datos",
                "No hay lectura de recorrido disponible.\n"
                "Asegúrese de estar conectado al equipo.",
            )
            return

        raw = self._obtener_raw_recorrido()
        if raw is None:
            QMessageBox.warning(self, "Error", "No se pudo calcular el valor raw del recorrido.")
            return

        self._raw_inferior = raw
        self._lbl_punto_inf.setText(
            f"Punto inferior: raw={raw:.1f}  ({dato.recorrido_mm:.1f} mm)"
        )
        self._lbl_punto_inf.setStyleSheet("color: #00cc44;")
        logger.info(f"Punto inferior capturado: raw={raw:.1f}, mm={dato.recorrido_mm:.1f}")

    def _capturar_punto_superior(self) -> None:
        """Captura la posición actual como punto superior del recorrido (= recorrido total)."""
        dato = self._obtener_dato_actual()
        if not dato or not dato.valido:
            QMessageBox.warning(
                self,
                "Sin datos",
                "No hay lectura de recorrido disponible.\n"
                "Asegúrese de estar conectado al equipo.",
            )
            return

        raw = self._obtener_raw_recorrido()
        if raw is None:
            QMessageBox.warning(self, "Error", "No se pudo calcular el valor raw del recorrido.")
            return

        self._raw_superior = raw
        self._lbl_punto_sup.setText(
            f"Punto superior: raw={raw:.1f}  ({dato.recorrido_mm:.1f} mm)"
        )
        self._lbl_punto_sup.setStyleSheet("color: #00cc44;")
        logger.info(f"Punto superior capturado: raw={raw:.1f}, mm={dato.recorrido_mm:.1f}")

    def _calcular_calibracion_recorrido(self) -> None:
        """Calcula escala y offset de recorrido a partir de los puntos capturados."""
        if self._raw_inferior is None or self._raw_superior is None:
            QMessageBox.warning(
                self,
                "Puntos no capturados",
                "Capture el punto inferior y el punto superior antes de calcular.",
            )
            return

        raw_inf = self._raw_inferior
        raw_sup = self._raw_superior
        mm_total = self._spin_recorrido_total.value()

        if abs(raw_sup - raw_inf) < 1.0:
            QMessageBox.warning(
                self,
                "Rango insuficiente",
                "Los puntos inferior y superior son demasiado cercanos.\n"
                "Asegúrese de mover el amortiguador hasta los extremos físicos reales.",
            )
            return

        # recorrido_mm = raw × escala + offset
        # En punto inferior (0 mm): 0 = raw_inf × escala + offset → offset = -raw_inf × escala
        # En punto superior (mm_total): mm_total = (raw_sup - raw_inf) × escala
        escala = mm_total / (raw_sup - raw_inf)
        offset = -(raw_inf * escala)

        self._spin_recorrido_escala.setValue(round(escala, 6))
        self._spin_recorrido_offset.setValue(round(offset, 3))

        logger.info(
            f"Calibración de recorrido calculada: escala={escala:.6f}, "
            f"offset={offset:.3f} mm, raw_inf={raw_inf:.1f}, "
            f"raw_sup={raw_sup:.1f}, mm_total={mm_total:.1f}"
        )

        QMessageBox.information(
            self,
            "Calibración calculada",
            f"Calibración de recorrido calculada correctamente:\n\n"
            f"  Escala: {escala:.6f} mm / raw\n"
            f"  Offset: {offset:.3f} mm\n\n"
            "Pulse Aceptar para aplicar la calibración.",
        )

    def _reset_recorrido(self) -> None:
        """Restablece la calibración de recorrido a valores por defecto."""
        self._raw_inferior = None
        self._raw_superior = None
        self._lbl_punto_inf.setText("Punto inferior: no capturado")
        self._lbl_punto_inf.setStyleSheet("color: #aaa;")
        self._lbl_punto_sup.setText("Punto superior: no capturado")
        self._lbl_punto_sup.setStyleSheet("color: #aaa;")
        self._spin_recorrido_escala.setValue(0.392157)
        self._spin_recorrido_offset.setValue(0.0)
        self._actualizar_lecturas()
        logger.debug("Calibración de recorrido restablecida.")

    # ─── Acciones de calibración de temperatura ────────────────────────────

    def _corregir_con_referencia(self, sensor: str) -> None:
        """
        Calcula la corrección de temperatura a partir de un valor de referencia.

        Muestra un diálogo para que el usuario ingrese la temperatura real
        medida con un termómetro de referencia externo. El sistema calcula
        automáticamente la corrección necesaria.

        Args:
            sensor: ``"amortiguador"`` o ``"reservorio"``.
        """
        dato = self._obtener_dato_actual()
        if not dato or not dato.valido:
            QMessageBox.warning(
                self,
                "Sin datos",
                "No hay lectura disponible.\n"
                "Asegúrese de estar conectado al equipo.",
            )
            return

        if sensor == "amortiguador":
            lectura_actual = dato.temp_amortiguador_c
            correccion_spin = self._spin_temp_amo_correccion
            label = self._lbl_temp_amo_actual
            nombre = "amortiguador"
        else:
            lectura_actual = dato.temp_reservorio_c
            correccion_spin = self._spin_temp_res_correccion
            label = self._lbl_temp_res_actual
            nombre = "reservorio"

        # Usamos un QDoubleSpinBox en un mini-diálogo para pedir la referencia
        dialogo_ref = QDialog(self)
        dialogo_ref.setWindowTitle(f"Temperatura de referencia - {nombre.capitalize()}")
        dialogo_ref.setStyleSheet(self.styleSheet())
        dialogo_ref.setMinimumWidth(320)

        layout_ref = QVBoxLayout(dialogo_ref)
        layout_ref.addWidget(
            QLabel(
                f"Lectura actual del sensor: {lectura_actual:.1f} °C\n\n"
                "Ingrese la temperatura real medida con un termómetro de referencia:"
            )
        )

        spin_ref = QDoubleSpinBox()
        spin_ref.setRange(-50.0, 300.0)
        spin_ref.setDecimals(1)
        spin_ref.setSuffix(" °C")
        spin_ref.setValue(lectura_actual)
        spin_ref.setStyleSheet(
            "background: #333; color: #fff; border: 1px solid #555; "
            "border-radius: 3px; padding: 3px;"
        )
        layout_ref.addWidget(spin_ref)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialogo_ref.accept)
        btns.rejected.connect(dialogo_ref.reject)
        layout_ref.addWidget(btns)

        if dialogo_ref.exec_() == QDialog.Accepted:
            temp_referencia = spin_ref.value()
            # Usar la corrección inicial (al abrir el diálogo) como base, no el valor
            # actual del spin, para evitar acumulación incorrecta si el botón se
            # pulsa varias veces en la misma sesión del diálogo.
            correccion_inicial = (
                self._correccion_inicial_amo
                if sensor == "amortiguador"
                else self._correccion_inicial_res
            )
            correccion_nueva = correccion_inicial + (temp_referencia - lectura_actual)
            correccion_spin.setValue(round(correccion_nueva, 1))
            label.setText(f"{temp_referencia:.1f} °C (corregido)")
            logger.info(
                f"Corrección de temperatura {nombre} calculada: "
                f"{correccion_nueva:.1f} °C "
                f"(sensor={lectura_actual:.1f}, referencia={temp_referencia:.1f})"
            )

    def _reset_temperaturas(self) -> None:
        """Elimina todas las correcciones de temperatura."""
        self._spin_temp_amo_correccion.setValue(0.0)
        self._spin_temp_res_correccion.setValue(0.0)
        self._actualizar_lecturas()
        logger.debug("Correcciones de temperatura eliminadas.")

    # ─── Aceptar ──────────────────────────────────────────────────────────

    def _aceptar(self) -> None:
        """Valida los valores y acepta el diálogo."""
        if self._spin_recorrido_escala.value() <= 0:
            QMessageBox.warning(self, "Valor inválido", "La escala de recorrido debe ser mayor que 0.")
            return
        if self._spin_fuerza_escala.value() <= 0:
            QMessageBox.warning(self, "Valor inválido", "La escala de fuerza debe ser mayor que 0.")
            return
        self.accept()

    # ─── Resultado ────────────────────────────────────────────────────────

    def obtener_config_actualizada(self) -> dict:
        """
        Retorna la configuración con los valores de calibración aplicados.

        Returns:
            Copia del diccionario de configuración con los nuevos valores
            de escala y offset para cada sensor calibrado.
        """
        config_nueva = self._config.copy()
        sensores = {k: v.copy() for k, v in config_nueva.get("sensores", {}).items()}

        # Fuerza
        if "fuerza" not in sensores:
            sensores["fuerza"] = {}
        sensores["fuerza"]["escala"] = self._spin_fuerza_escala.value()
        sensores["fuerza"]["offset_valor"] = self._spin_fuerza_offset.value()

        # Recorrido
        if "recorrido" not in sensores:
            sensores["recorrido"] = {}
        sensores["recorrido"]["escala"] = self._spin_recorrido_escala.value()
        sensores["recorrido"]["offset_valor"] = self._spin_recorrido_offset.value()

        # Temperaturas: offset_config = base(-40) + corrección_usuario
        if "temp_amortiguador" not in sensores:
            sensores["temp_amortiguador"] = {}
        sensores["temp_amortiguador"]["offset_valor"] = (
            -40.0 + self._spin_temp_amo_correccion.value()
        )

        if "temp_reservorio" not in sensores:
            sensores["temp_reservorio"] = {}
        sensores["temp_reservorio"]["offset_valor"] = (
            -40.0 + self._spin_temp_res_correccion.value()
        )

        config_nueva["sensores"] = sensores
        return config_nueva
