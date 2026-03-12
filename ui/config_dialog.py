"""
Módulo: config_dialog.py
Descripción: Diálogo de configuración de la aplicación.

Permite editar:
    - Conexión (puerto, baudrate, intervalo de polling)
    - Alarmas (umbrales de temperatura, fuerza y velocidad)
    - Logging (carpeta, prefijo de archivo)

Los cambios se guardan en config/config.json mediante ConfigManager.
"""

import logging
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from utils.config_manager import ConfigManager

# Logger del módulo
logger = logging.getLogger(__name__)

ESTILO_DIALOGO = """
    QDialog {
        background-color: #2b2b2b;
        color: #ffffff;
    }
    QTabWidget::pane {
        background-color: #2b2b2b;
        border: 1px solid #444;
    }
    QTabBar::tab {
        background: #333;
        color: #ccc;
        padding: 6px 16px;
        border: 1px solid #444;
    }
    QTabBar::tab:selected {
        background: #444;
        color: #fff;
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
    QLineEdit, QSpinBox, QDoubleSpinBox {
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
"""


class ConfigDialog(QDialog):
    """
    Diálogo modal para editar la configuración de la aplicación.

    Organizado en tabs:
        - Conexión: Puerto, baudrate, intervalo de polling, delay de inicio.
        - Alarmas: Umbrales de temperatura, fuerza y velocidad.
        - Logging: Carpeta y prefijo del archivo CSV.

    Ejemplo de uso::

        dialog = ConfigDialog(config_manager=config_manager, parent=ventana_principal)
        if dialog.exec_() == QDialog.Accepted:
            nueva_config = dialog.obtener_config()
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Inicializa el diálogo de configuración.

        Args:
            config_manager: Instancia de ConfigManager para cargar/guardar config.
            parent: Widget padre de Qt.
        """
        super().__init__(parent)
        self._config_manager = config_manager
        self._config = config_manager._config_actual.copy()

        self.setWindowTitle("Configuración - Shock Dyno Monitor")
        self.setMinimumWidth(500)
        self.setStyleSheet(ESTILO_DIALOGO)

        self._construir_ui()
        self._cargar_valores()
        logger.debug("ConfigDialog inicializado.")

    def _construir_ui(self) -> None:
        """Construye la interfaz del diálogo con tabs."""
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(12, 12, 12, 12)
        layout_principal.setSpacing(8)

        # Widget de tabs
        self._tabs = QTabWidget()

        # Tab: Conexión
        self._tab_conexion = self._crear_tab_conexion()
        self._tabs.addTab(self._tab_conexion, "Conexión")

        # Tab: Alarmas
        self._tab_alarmas = self._crear_tab_alarmas()
        self._tabs.addTab(self._tab_alarmas, "Alarmas")

        # Tab: Logging
        self._tab_logging = self._crear_tab_logging()
        self._tabs.addTab(self._tab_logging, "Logging")

        layout_principal.addWidget(self._tabs)

        # Botones OK/Cancelar
        botones = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        layout_principal.addWidget(botones)

    def _crear_tab_conexion(self) -> QWidget:
        """
        Crea el tab de configuración de conexión serial.

        Returns:
            Widget con los controles de conexión.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Grupo: Puerto y baudrate
        grupo = QGroupBox("Parámetros de Conexión")
        form = QFormLayout(grupo)
        form.setSpacing(8)

        self._input_puerto = QLineEdit()
        self._input_puerto.setPlaceholderText("Ej: COM3, SIMULADOR")
        form.addRow("Puerto:", self._input_puerto)

        self._spin_baudrate = QSpinBox()
        self._spin_baudrate.setRange(9600, 230400)
        self._spin_baudrate.setSingleStep(4800)
        form.addRow("Baudrate:", self._spin_baudrate)

        self._spin_intervalo = QSpinBox()
        self._spin_intervalo.setRange(10, 1000)
        self._spin_intervalo.setSuffix(" ms")
        form.addRow("Intervalo Polling:", self._spin_intervalo)

        self._spin_delay = QSpinBox()
        self._spin_delay.setRange(0, 60)
        self._spin_delay.setSuffix(" s")
        form.addRow("Delay de Inicio:", self._spin_delay)

        layout.addWidget(grupo)
        layout.addStretch()
        return widget

    def _crear_tab_alarmas(self) -> QWidget:
        """
        Crea el tab de configuración de umbrales de alarma.

        Returns:
            Widget con los controles de alarmas.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        grupo = QGroupBox("Umbrales de Alarma")
        form = QFormLayout(grupo)
        form.setSpacing(8)

        self._spin_temp_amo_max = QDoubleSpinBox()
        self._spin_temp_amo_max.setRange(0, 300)
        self._spin_temp_amo_max.setDecimals(1)
        self._spin_temp_amo_max.setSuffix(" °C")
        form.addRow("Temp. Amortiguador Máx:", self._spin_temp_amo_max)

        self._spin_temp_res_max = QDoubleSpinBox()
        self._spin_temp_res_max.setRange(0, 200)
        self._spin_temp_res_max.setDecimals(1)
        self._spin_temp_res_max.setSuffix(" °C")
        form.addRow("Temp. Reservorio Máx:", self._spin_temp_res_max)

        self._spin_fuerza_max = QDoubleSpinBox()
        self._spin_fuerza_max.setRange(0, 20000)
        self._spin_fuerza_max.setDecimals(0)
        self._spin_fuerza_max.setSuffix(" N")
        form.addRow("Fuerza Máxima:", self._spin_fuerza_max)

        self._spin_velocidad_max = QDoubleSpinBox()
        self._spin_velocidad_max.setRange(0, 20000)
        self._spin_velocidad_max.setDecimals(0)
        self._spin_velocidad_max.setSuffix(" RPM")
        form.addRow("Velocidad Máxima:", self._spin_velocidad_max)

        layout.addWidget(grupo)
        layout.addStretch()
        return widget

    def _crear_tab_logging(self) -> QWidget:
        """
        Crea el tab de configuración del logging CSV.

        Returns:
            Widget con los controles de logging.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        grupo = QGroupBox("Configuración de Registro CSV")
        form = QFormLayout(grupo)
        form.setSpacing(8)

        layout_carpeta = QHBoxLayout()
        self._input_carpeta = QLineEdit()
        self._input_carpeta.setPlaceholderText("Ej: logs, C:\\datos")
        layout_carpeta.addWidget(self._input_carpeta)
        form.addRow("Carpeta:", layout_carpeta)

        self._input_prefijo = QLineEdit()
        self._input_prefijo.setPlaceholderText("Ej: shock_test")
        form.addRow("Prefijo del Archivo:", self._input_prefijo)

        lbl_info = QLabel(
            "Los archivos se nombran:\n"
            "{prefijo}_{YYYYMMDD}_{HHMMSS}.csv"
        )
        lbl_info.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("Formato:", lbl_info)

        layout.addWidget(grupo)
        layout.addStretch()
        return widget

    def _cargar_valores(self) -> None:
        """Carga los valores actuales de la configuración en los controles."""
        cfg_conexion = self._config.get("conexion", {})
        self._input_puerto.setText(cfg_conexion.get("puerto", "SIMULADOR"))
        self._spin_baudrate.setValue(cfg_conexion.get("baudrate", 115200))
        self._spin_intervalo.setValue(
            cfg_conexion.get("intervalo_polling_ms", 50)
        )
        self._spin_delay.setValue(cfg_conexion.get("delay_conexion", 10))

        cfg_alarmas = self._config.get("alarmas", {})
        self._spin_temp_amo_max.setValue(
            cfg_alarmas.get("temp_amortiguador_max", 60.0)
        )
        self._spin_temp_res_max.setValue(
            cfg_alarmas.get("temp_reservorio_max", 50.0)
        )
        self._spin_fuerza_max.setValue(cfg_alarmas.get("fuerza_max", 2000.0))
        self._spin_velocidad_max.setValue(
            cfg_alarmas.get("velocidad_max", 5000.0)
        )

        cfg_logging = self._config.get("logging", {})
        self._input_carpeta.setText(cfg_logging.get("carpeta", "logs"))
        self._input_prefijo.setText(
            cfg_logging.get("prefijo_archivo", "shock_test")
        )

    def _aceptar(self) -> None:
        """Valida y guarda la configuración al aceptar el diálogo."""
        try:
            # Recoger valores de la UI
            nueva_config = self._config.copy()

            # Conexión
            if "conexion" not in nueva_config:
                nueva_config["conexion"] = {}
            nueva_config["conexion"]["puerto"] = self._input_puerto.text().strip()
            nueva_config["conexion"]["baudrate"] = self._spin_baudrate.value()
            nueva_config["conexion"]["intervalo_polling_ms"] = (
                self._spin_intervalo.value()
            )
            nueva_config["conexion"]["delay_conexion"] = self._spin_delay.value()

            # Alarmas
            if "alarmas" not in nueva_config:
                nueva_config["alarmas"] = {}
            nueva_config["alarmas"]["temp_amortiguador_max"] = (
                self._spin_temp_amo_max.value()
            )
            nueva_config["alarmas"]["temp_reservorio_max"] = (
                self._spin_temp_res_max.value()
            )
            nueva_config["alarmas"]["fuerza_max"] = self._spin_fuerza_max.value()
            nueva_config["alarmas"]["velocidad_max"] = (
                self._spin_velocidad_max.value()
            )

            # Logging
            if "logging" not in nueva_config:
                nueva_config["logging"] = {}
            nueva_config["logging"]["carpeta"] = self._input_carpeta.text().strip()
            nueva_config["logging"]["prefijo_archivo"] = (
                self._input_prefijo.text().strip()
            )

            # Guardar
            if self._config_manager.guardar_config(nueva_config):
                self._config = nueva_config
                logger.info("Configuración guardada desde el diálogo.")
                self.accept()
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    "No se pudo guardar la configuración.\n"
                    "Verifique los permisos de escritura.",
                )

        except Exception as e:
            logger.error(f"Error al guardar configuración: {e}")
            QMessageBox.critical(self, "Error", f"Error al guardar: {e}")

    def obtener_config(self) -> dict:
        """
        Retorna la configuración editada en el diálogo.

        Returns:
            Diccionario con la configuración actualizada.
        """
        return self._config
