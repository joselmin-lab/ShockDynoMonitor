"""
Módulo: main_window.py
Descripción: Ventana principal de la aplicación Shock Dyno Monitor.

La ventana contiene:
    - Tabs: Dashboard, Gráficas, Configuración
    - Barra de herramientas con selector de puerto y botón conectar/desconectar
    - Status bar con estadísticas de comunicación y estado del log
    - Menú: Archivo, Conexión, Ayuda

La actualización de la UI ocurre cada 50ms mediante QTimer.

Threading:
    - El hilo principal (Qt) maneja la UI.
    - El SerialManager usa threads daemon para TX/RX.
    - Se usa Qt signals/slots para comunicación segura entre threads.
"""

import logging
from typing import Optional, List

from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAction,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.data_parser import ShockDynoData
from core.serial_manager import SerialManager
from core.data_logger import DataLogger
from core.alarm_manager import AlarmManager, Alarma
from ui.dashboard_widget import DashboardWidget
from ui.graphs_widget import GraphsWidget
from ui.config_dialog import ConfigDialog
from ui.calibration_dialog import CalibrationDialog
from utils.config_manager import ConfigManager

# Logger del módulo
logger = logging.getLogger(__name__)

TITULO_APP = "Shock Dyno Monitor"
VERSION_APP = "1.0.0"

ESTILO_VENTANA = """
    QMainWindow {
        background-color: #1e1e1e;
    }
    QTabWidget::pane {
        background-color: #1e1e1e;
        border: 1px solid #333;
    }
    QTabBar::tab {
        background: #2b2b2b;
        color: #aaa;
        padding: 8px 20px;
        border: 1px solid #333;
        border-bottom: none;
    }
    QTabBar::tab:selected {
        background: #1e1e1e;
        color: #fff;
        font-weight: bold;
    }
    QToolBar {
        background-color: #2b2b2b;
        border-bottom: 1px solid #444;
        spacing: 6px;
        padding: 4px;
    }
    QStatusBar {
        background-color: #2b2b2b;
        color: #aaa;
        border-top: 1px solid #444;
    }
    QComboBox {
        background: #333;
        color: #fff;
        border: 1px solid #555;
        border-radius: 3px;
        padding: 3px 8px;
        min-width: 140px;
    }
    QComboBox::drop-down {
        border: none;
    }
    QPushButton#btnConectar {
        background: #00aa44;
        color: #fff;
        border: none;
        border-radius: 4px;
        padding: 5px 16px;
        font-weight: bold;
    }
    QPushButton#btnConectar:hover {
        background: #00cc55;
    }
    QPushButton#btnConectar:disabled {
        background: #555;
        color: #888;
    }
    QPushButton#btnDesconectar {
        background: #cc2222;
        color: #fff;
        border: none;
        border-radius: 4px;
        padding: 5px 16px;
        font-weight: bold;
    }
    QPushButton#btnDesconectar:hover {
        background: #ee3333;
    }
    QPushButton#btnLog {
        background: #0055cc;
        color: #fff;
        border: none;
        border-radius: 4px;
        padding: 5px 16px;
        font-weight: bold;
    }
    QPushButton#btnLog:hover {
        background: #0066ee;
    }
    QPushButton#btnLog:checked {
        background: #cc7700;
    }
"""


class _SeñalizadorDatos(QObject):
    """
    Objeto QObject para emitir señales Qt desde threads externos.

    Se usa para pasar datos del thread RX al hilo principal de Qt
    de forma segura.
    """
    dato_recibido = pyqtSignal(object)


class MainWindow(QMainWindow):
    """
    Ventana principal de la aplicación Shock Dyno Monitor.

    Coordina todos los componentes:
    - SerialManager para la comunicación con la ECU
    - DataLogger para el registro CSV
    - AlarmManager para las alarmas
    - DashboardWidget y GraphsWidget para la visualización

    Ejemplo de uso (desde main.py)::

        app = QApplication(sys.argv)
        config_manager = ConfigManager()
        config = config_manager.cargar_config()
        ventana = MainWindow(config=config, config_manager=config_manager)
        ventana.show()
        sys.exit(app.exec_())
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        config_manager: Optional[ConfigManager] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Inicializa la ventana principal.

        Args:
            config: Configuración de la aplicación.
            config_manager: Instancia de ConfigManager para guardar cambios.
            parent: Widget padre de Qt.
        """
        super().__init__(parent)
        self._config = config or {}
        self._config_manager = config_manager or ConfigManager()
        self._config_manager._config_actual = self._config

        self._cfg_ui = self._config.get("ui", {})

        # Señalizador para comunicación thread-safe entre RX y Qt
        self._señalizador = _SeñalizadorDatos()
        self._señalizador.dato_recibido.connect(self._en_dato_recibido)

        # Módulos principales
        self._serial_manager = SerialManager(
            config=self._config,
            callback_datos=self._callback_dato,
        )
        self._data_logger = DataLogger(config=self._config)
        self._alarm_manager = AlarmManager(config=self._config)

        # Estado de la aplicación
        self._conectado = False
        self._logging_activo = False

        # Último dato recibido (para calibración)
        self._ultimo_dato: Optional[ShockDynoData] = None

        # Construir UI
        self._construir_ui()

        # Timer de actualización de status bar
        self._timer_status = QTimer(self)
        self._timer_status.timeout.connect(self._actualizar_status_bar)
        self._timer_status.start(1000)  # Actualizar status bar cada 1 segundo

        # Configurar ventana
        ancho = self._cfg_ui.get("ventana_ancho", 1200)
        alto = self._cfg_ui.get("ventana_alto", 800)
        self.resize(ancho, alto)
        self.setWindowTitle(f"{TITULO_APP} v{VERSION_APP}")
        self.setStyleSheet(ESTILO_VENTANA)

        logger.info(f"{TITULO_APP} v{VERSION_APP} iniciado.")

    def _construir_ui(self) -> None:
        """Construye todos los elementos de la interfaz de usuario."""
        # Widget central
        widget_central = QWidget()
        self.setCentralWidget(widget_central)
        layout_central = QVBoxLayout(widget_central)
        layout_central.setContentsMargins(0, 0, 0, 0)
        layout_central.setSpacing(0)

        # Barra de herramientas
        self._construir_toolbar()

        # Menú
        self._construir_menu()

        # Tabs principales
        self._tabs = QTabWidget()
        layout_central.addWidget(self._tabs)

        # Tab Dashboard
        self._dashboard = DashboardWidget(
            config=self._config,
            gestor_alarmas=self._alarm_manager,
        )
        self._tabs.addTab(self._dashboard, "📊 Dashboard")

        # Tab Gráficas
        self._graficas = GraphsWidget(config=self._config)
        self._tabs.addTab(self._graficas, "📈 Gráficas")

        # Status bar
        self._construir_status_bar()

    def _construir_toolbar(self) -> None:
        """Construye la barra de herramientas superior."""
        toolbar = QToolBar("Conexión")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Etiqueta Puerto
        toolbar.addWidget(QLabel("  Puerto: "))

        # Combo de puertos disponibles
        self._combo_puertos = QComboBox()
        self._combo_puertos.setMinimumWidth(160)
        self._actualizar_lista_puertos()
        toolbar.addWidget(self._combo_puertos)

        # Botón refrescar puertos
        btn_refrescar = QPushButton("↺")
        btn_refrescar.setFixedWidth(30)
        btn_refrescar.setStyleSheet(
            "QPushButton { background: #333; color: #fff; border: 1px solid #555; "
            "border-radius: 3px; } QPushButton:hover { background: #444; }"
        )
        btn_refrescar.setToolTip("Refrescar lista de puertos")
        btn_refrescar.clicked.connect(self._actualizar_lista_puertos)
        toolbar.addWidget(btn_refrescar)

        toolbar.addSeparator()

        # Botón Conectar
        self._btn_conectar = QPushButton("Conectar")
        self._btn_conectar.setObjectName("btnConectar")
        self._btn_conectar.clicked.connect(self._accion_conectar)
        toolbar.addWidget(self._btn_conectar)

        # Botón Desconectar
        self._btn_desconectar = QPushButton("Desconectar")
        self._btn_desconectar.setObjectName("btnDesconectar")
        self._btn_desconectar.setEnabled(False)
        self._btn_desconectar.clicked.connect(self._accion_desconectar)
        toolbar.addWidget(self._btn_desconectar)

        toolbar.addSeparator()

        # Botón Log CSV
        self._btn_log = QPushButton("▶ Iniciar Log")
        self._btn_log.setObjectName("btnLog")
        self._btn_log.setEnabled(False)
        self._btn_log.clicked.connect(self._accion_toggle_log)
        toolbar.addWidget(self._btn_log)

        toolbar.addSeparator()

        # Botón Calibración (solo activo cuando está conectado)
        self._btn_calibrar = QPushButton("⚖ Calibrar")
        self._btn_calibrar.setEnabled(False)
        self._btn_calibrar.setStyleSheet(
            "QPushButton { background: #225599; color: #fff; border: none; "
            "border-radius: 4px; padding: 5px 12px; font-weight: bold; } "
            "QPushButton:hover { background: #3366bb; } "
            "QPushButton:disabled { background: #555; color: #888; }"
        )
        self._btn_calibrar.setToolTip(
            "Calibrar sensores: tarar fuerza, ajustar rango de recorrido y temperatura."
        )
        self._btn_calibrar.clicked.connect(self._abrir_calibracion)
        toolbar.addWidget(self._btn_calibrar)

        toolbar.addSeparator()

        # Botón limpiar gráficas
        btn_limpiar = QPushButton("🗑 Limpiar")
        btn_limpiar.setStyleSheet(
            "QPushButton { background: #555; color: #fff; border: none; "
            "border-radius: 4px; padding: 5px 12px; } "
            "QPushButton:hover { background: #666; }"
        )
        btn_limpiar.clicked.connect(self._accion_limpiar)
        toolbar.addWidget(btn_limpiar)

    def _construir_menu(self) -> None:
        """Construye el menú principal de la ventana."""
        barra_menu = self.menuBar()
        barra_menu.setStyleSheet(
            "QMenuBar { background: #2b2b2b; color: #ccc; }"
            "QMenuBar::item:selected { background: #444; }"
            "QMenu { background: #2b2b2b; color: #ccc; border: 1px solid #555; }"
            "QMenu::item:selected { background: #444; }"
        )

        # Menú Archivo
        menu_archivo = barra_menu.addMenu("Archivo")

        accion_config = QAction("Configuración...", self)
        accion_config.setShortcut("Ctrl+,")
        accion_config.triggered.connect(self._abrir_config)
        menu_archivo.addAction(accion_config)

        menu_archivo.addSeparator()

        accion_salir = QAction("Salir", self)
        accion_salir.setShortcut("Ctrl+Q")
        accion_salir.triggered.connect(self.close)
        menu_archivo.addAction(accion_salir)

        # Menú Conexión
        menu_conexion = barra_menu.addMenu("Conexión")

        self._accion_conectar_menu = QAction("Conectar", self)
        self._accion_conectar_menu.triggered.connect(self._accion_conectar)
        menu_conexion.addAction(self._accion_conectar_menu)

        self._accion_desconectar_menu = QAction("Desconectar", self)
        self._accion_desconectar_menu.triggered.connect(self._accion_desconectar)
        self._accion_desconectar_menu.setEnabled(False)
        menu_conexion.addAction(self._accion_desconectar_menu)

        # Menú Ayuda
        menu_ayuda = barra_menu.addMenu("Ayuda")

        accion_acerca = QAction("Acerca de...", self)
        accion_acerca.triggered.connect(self._mostrar_acerca)
        menu_ayuda.addAction(accion_acerca)

    def _construir_status_bar(self) -> None:
        """Construye la barra de estado inferior."""
        barra = QStatusBar()
        self.setStatusBar(barra)

        self._lbl_estado = QLabel("Desconectado")
        self._lbl_estado.setStyleSheet("color: #ff4444;")
        barra.addWidget(self._lbl_estado)

        barra.addWidget(QLabel("  |  "))

        self._lbl_estadisticas = QLabel("TX:0 RX:0 CRC_ERR:0")
        barra.addWidget(self._lbl_estadisticas)

        barra.addWidget(QLabel("  |  "))

        self._lbl_log_status = QLabel("Log: Inactivo")
        barra.addWidget(self._lbl_log_status)

        barra.addWidget(QLabel("  |  "))

        self._lbl_alarmas = QLabel("Alarmas: OK")
        self._lbl_alarmas.setStyleSheet("color: #00cc44;")
        barra.addWidget(self._lbl_alarmas)

    # ─── Acciones de la Toolbar/Menú ───────────────────────────────────────

    def _actualizar_lista_puertos(self) -> None:
        """Actualiza el combo de puertos disponibles."""
        puerto_actual = self._combo_puertos.currentText()
        self._combo_puertos.clear()
        puertos = self._serial_manager.listar_puertos_disponibles()
        self._combo_puertos.addItems(puertos)

        # Restaurar selección anterior si sigue disponible
        idx = self._combo_puertos.findText(puerto_actual)
        if idx >= 0:
            self._combo_puertos.setCurrentIndex(idx)

    def _accion_conectar(self) -> None:
        """Conecta al puerto seleccionado en el combo."""
        if self._conectado:
            return

        puerto = self._combo_puertos.currentText()
        if not puerto:
            QMessageBox.warning(self, "Sin puerto", "Seleccione un puerto primero.")
            return

        logger.info(f"Intentando conectar a: {puerto}")
        self._lbl_estado.setText(f"Conectando a {puerto}...")
        self._lbl_estado.setStyleSheet("color: #ffaa00;")

        exito = self._serial_manager.conectar(puerto)

        if exito:
            self._conectado = True
            self._btn_conectar.setEnabled(False)
            self._btn_desconectar.setEnabled(True)
            self._btn_log.setEnabled(True)
            self._btn_calibrar.setEnabled(True)
            self._accion_conectar_menu.setEnabled(False)
            self._accion_desconectar_menu.setEnabled(True)
            self._combo_puertos.setEnabled(False)

            self._lbl_estado.setText(f"Conectado (Arduino): {puerto}")
            self._lbl_estado.setStyleSheet("color: #00cc44;")
            logger.info(f"Conectado a {puerto} (Arduino)")
        else:
            self._lbl_estado.setText(f"Error al conectar a {puerto}")
            self._lbl_estado.setStyleSheet("color: #ff4444;")
            QMessageBox.critical(
                self,
                "Error de Conexión",
                f"No se pudo conectar al puerto {puerto}.\n"
                "Verifique que el puerto esté disponible y no esté en uso.",
            )

    def _accion_desconectar(self) -> None:
        """Desconecta del puerto serial activo."""
        if not self._conectado:
            return

        # Detener logging si está activo
        if self._logging_activo:
            self._data_logger.detener()
            self._logging_activo = False
            self._btn_log.setText("▶ Iniciar Log")

        self._serial_manager.desconectar()
        self._conectado = False

        self._btn_conectar.setEnabled(True)
        self._btn_desconectar.setEnabled(False)
        self._btn_log.setEnabled(False)
        self._btn_calibrar.setEnabled(False)
        self._accion_conectar_menu.setEnabled(True)
        self._accion_desconectar_menu.setEnabled(False)
        self._combo_puertos.setEnabled(True)

        self._lbl_estado.setText("Desconectado")
        self._lbl_estado.setStyleSheet("color: #ff4444;")
        logger.info("Desconectado.")

    def _accion_toggle_log(self) -> None:
        """Inicia o detiene el logging CSV."""
        if not self._logging_activo:
            if self._data_logger.iniciar():
                self._logging_activo = True
                self._btn_log.setText("⏹ Detener Log")
                nombre = self._data_logger.ruta_archivo_actual
                self._lbl_log_status.setText(f"Log: {nombre}")
                self._lbl_log_status.setStyleSheet("color: #00cc44;")
                logger.info(f"Logging iniciado: {nombre}")
            else:
                QMessageBox.critical(
                    self, "Error", "No se pudo iniciar el logging CSV."
                )
        else:
            self._data_logger.detener()
            self._logging_activo = False
            self._btn_log.setText("▶ Iniciar Log")
            filas = self._data_logger.filas_escritas
            self._lbl_log_status.setText(
                f"Log guardado ({filas} filas): {self._data_logger.ruta_archivo_actual}"
            )
            self._lbl_log_status.setStyleSheet("color: #aaa;")
            logger.info(f"Logging detenido. {filas} filas guardadas.")

    def _accion_limpiar(self) -> None:
        """Limpia las gráficas y resetea los min/max del dashboard."""
        self._graficas.limpiar_graficas()
        self._dashboard.resetear_sesion()

    def _abrir_config(self) -> None:
        """Abre el diálogo de configuración."""
        dialogo = ConfigDialog(
            config_manager=self._config_manager, parent=self
        )
        if dialogo.exec_():
            nueva_config = dialogo.obtener_config()
            self._config = nueva_config
            # Actualizar umbrales de alarmas
            self._alarm_manager.actualizar_umbrales(
                nueva_config.get("alarmas", {})
            )
            logger.info("Configuración actualizada desde el diálogo.")

    def _mostrar_acerca(self) -> None:
        """Muestra el diálogo de información de la aplicación."""
        QMessageBox.about(
            self,
            f"Acerca de {TITULO_APP}",
            f"<h3>{TITULO_APP}</h3>"
            f"<p>Versión: {VERSION_APP}</p>"
            "<p>Sistema de monitoreo en tiempo real para banco "
            "de pruebas de amortiguadores.</p>"
            "<p>ECU: Speeduino 2025.01.4<br>"
            "Protocolo: Binario con CRC32<br>"
            "Baudrate: 115200 bps</p>"
            "<p>Desarrollado en Python con PyQt5 y pyqtgraph.</p>",
        )

    # ─── Callback de datos (hilo RX → hilo Qt) ─────────────────────────────

    def _callback_dato(self, dato: ShockDynoData) -> None:
        """
        Callback llamado por el SerialManager cuando llegan nuevos datos.

        IMPORTANTE: Este método se llama desde el thread RX (no el hilo Qt).
        Por seguridad, emitimos una señal Qt para procesar en el hilo principal.

        Args:
            dato: ShockDynoData con los datos recibidos del serial.
        """
        self._señalizador.dato_recibido.emit(dato)

    def _en_dato_recibido(self, dato: ShockDynoData) -> None:
        """
        Procesa un nuevo dato en el hilo principal de Qt.

        Actualiza el dashboard, las gráficas, el logger y las alarmas.

        Args:
            dato: ShockDynoData con los datos a procesar.
        """
        if not dato.valido:
            return

        # Guardar último dato para calibración y otras funciones
        self._ultimo_dato = dato

        # Verificar alarmas
        alarmas_activas: List[Alarma] = self._alarm_manager.verificar_alarmas(dato)

        # Actualizar Dashboard
        self._dashboard.actualizar_datos(dato, alarmas_activas)

        # Actualizar Gráficas
        self._graficas.agregar_dato(dato)

        # Registrar en CSV si el logging está activo
        if self._logging_activo:
            self._data_logger.registrar_dato(dato)

        # Actualizar indicador de alarmas en el status bar
        if alarmas_activas:
            nombres = ", ".join(a.nombre for a in alarmas_activas)
            self._lbl_alarmas.setText(f"⚠ ALARMA: {nombres}")
            self._lbl_alarmas.setStyleSheet("color: #ff4444; font-weight: bold;")
        else:
            self._lbl_alarmas.setText("Alarmas: OK")
            self._lbl_alarmas.setStyleSheet("color: #00cc44;")

    # ─── Calibración de sensores ───────────────────────────────────────────

    def _abrir_calibracion(self) -> None:
        """
        Abre el diálogo de calibración de sensores.

        Pasa el último dato recibido y un callback para obtener el dato
        más reciente en el momento en que el usuario pulse un botón de captura.
        El diálogo es modal. Si el usuario acepta, la nueva calibración se
        aplica inmediatamente al parser del SerialManager y se guarda en la
        configuración.
        """
        dialogo = CalibrationDialog(
            config=self._config,
            ultimo_dato=self._ultimo_dato,
            callback_lectura=lambda: self._ultimo_dato,
            parent=self,
        )
        if dialogo.exec_():
            nueva_config = dialogo.obtener_config_actualizada()
            self._config = nueva_config

            # Aplicar calibración al parser en tiempo real
            self._serial_manager.actualizar_calibracion(nueva_config)

            # Guardar en disco (también actualiza _config_actual internamente)
            self._config_manager.guardar_config(nueva_config)

            logger.info("Calibración aplicada y guardada.")

    def _actualizar_status_bar(self) -> None:
        """
        Actualiza las estadísticas de la barra de estado.

        Se llama cada 1 segundo desde el QTimer.
        """
        if self._conectado:
            stats = self._serial_manager.estadisticas.resumen()
            self._lbl_estadisticas.setText(stats)

            if self._logging_activo:
                filas = self._data_logger.filas_escritas
                self._lbl_log_status.setText(
                    f"Log activo: {filas} filas | "
                    f"{self._data_logger.ruta_archivo_actual}"
                )

    # ─── Ciclo de vida de la ventana ───────────────────────────────────────

    def closeEvent(self, event) -> None:
        """
        Maneja el evento de cierre de la ventana.

        Detiene el logging y desconecta limpiamente antes de cerrar.

        Args:
            event: QCloseEvent del sistema.
        """
        respuesta = QMessageBox.question(
            self,
            "Confirmar Salida",
            "¿Desea salir de la aplicación?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if respuesta == QMessageBox.Yes:
            # Detener logging si está activo
            if self._logging_activo:
                self._data_logger.detener()

            # Desconectar si está conectado
            if self._conectado:
                self._serial_manager.desconectar()

            self._timer_status.stop()
            logger.info("Aplicación cerrada correctamente.")
            event.accept()
        else:
            event.ignore()
