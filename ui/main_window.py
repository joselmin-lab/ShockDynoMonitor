"""
Ventana principal de la aplicación Shock Dyno Monitor.

Este módulo contiene la interfaz gráfica principal con tabs,
toolbar, menú y status bar. Coordina todos los componentes de la UI.
"""


import logging
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QComboBox, QLabel,
    QStatusBar, QMessageBox, QToolBar, QAction, QMenu
)
from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QIcon

from core.data_parser import ShockDynoData
from ui.dashboard_widget import DashboardWidget
from ui.graphs_widget import GraphsWidget
from ui.config_dialog import ConfigDialog

# Intentar importar calibration_dialog si existe
try:
    from ui.calibration_dialog import CalibrationDialog
    CALIBRATION_AVAILABLE = True
except ImportError:
    CALIBRATION_AVAILABLE = False

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Ventana principal de la aplicación Shock Dyno Monitor.
    
    Coordina la conexión serial, actualización de UI,
    logging de datos y gestión de alarmas.
    """
    
    # Signal para comunicación thread-safe entre workers y UI
    datos_recibidos_signal = pyqtSignal(object)
    
    def __init__(self, config: dict):
        """
        Inicializar ventana principal.
        
        Args:
            config: Diccionario de configuración global
        """
        super().__init__()
        
        self.config = config
        self.conectado = False
        self.datos_recibidos = 0
        self.ultimo_dato = None  # Para calibración
        
        # Conectar signal para thread-safe UI updates
        self.datos_recibidos_signal.connect(self._actualizar_ui_con_datos)
        
        # Inicializar componentes (inyectados desde main.py)
        self.serial_manager = None
        self.data_parser = None
        self.data_logger = None
        self.alarm_manager = None
        self.data_buffer = None
        self.config_manager = None
        
        # Widgets de UI
        self.dashboard_widget = None
        self.graphs_widget = None
        
        # Timer para estadísticas (no para datos, esos vienen por callback)
        self.timer_estadisticas = QTimer()
        self.timer_estadisticas.timeout.connect(self.actualizar_status_bar)
        self.timer_estadisticas.start(1000)  # Actualizar status cada 1 segundo
        
        # Configurar UI
        self._configurar_ui()
        
        logger.info(f"Shock Dyno Monitor v{self.config['ui']['version']} iniciado.")
    
    def _configurar_ui(self):
        """Configurar interfaz de usuario."""
        # Configurar ventana
        self.setWindowTitle(self.config['ui']['window_title'])
        self.resize(
            self.config['ui']['window_width'],
            self.config['ui']['window_height']
        )
        
        # Crear widgets principales
        self._crear_toolbar()
        self._crear_menu()
        self._crear_widgets_centrales()
        self._crear_status_bar()
    
    def _crear_toolbar(self):
        """Crear barra de herramientas."""
        toolbar = QToolBar("Herramientas Principales")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # Selector de puerto
        self.combo_puerto = QComboBox()
        self.combo_puerto.setMinimumWidth(150)
        toolbar.addWidget(QLabel("Puerto:"))
        toolbar.addWidget(self.combo_puerto)
        
        toolbar.addSeparator()
        
        # Botones de conexión
        self.btn_conectar = QPushButton("🔌 Conectar")
        self.btn_conectar.clicked.connect(self.conectar)
        toolbar.addWidget(self.btn_conectar)
        
        self.btn_desconectar = QPushButton("⏹ Desconectar")
        self.btn_desconectar.clicked.connect(self.desconectar)
        self.btn_desconectar.setEnabled(False)
        toolbar.addWidget(self.btn_desconectar)
        
        toolbar.addSeparator()
        
        # Botones de logging
        self.btn_iniciar_log = QPushButton("📝 Iniciar Log")
        self.btn_iniciar_log.clicked.connect(self.iniciar_logging)
        self.btn_iniciar_log.setEnabled(False)
        toolbar.addWidget(self.btn_iniciar_log)
        
        self.btn_detener_log = QPushButton("⏸ Detener Log")
        self.btn_detener_log.clicked.connect(self.detener_logging)
        self.btn_detener_log.setEnabled(False)
        toolbar.addWidget(self.btn_detener_log)
        
        toolbar.addSeparator()
        
        # Botón de calibración (si está disponible)
        if CALIBRATION_AVAILABLE:
            self.btn_calibrar = QPushButton("⚖ Calibrar")
            self.btn_calibrar.clicked.connect(self._abrir_calibracion)
            self.btn_calibrar.setEnabled(False)
            toolbar.addWidget(self.btn_calibrar)
        
        # Indicador de estado
        self.label_estado = QLabel("⚫ Desconectado")
        self.label_estado.setStyleSheet("color: gray; font-weight: bold;")
        toolbar.addWidget(self.label_estado)
    
    def _crear_menu(self):
        """Crear barra de menú."""
        menubar = self.menuBar()
        
        # Menú Archivo
        menu_archivo = menubar.addMenu("&Archivo")
        
        accion_config = QAction("⚙ Configuración", self)
        accion_config.triggered.connect(self.abrir_configuracion)
        menu_archivo.addAction(accion_config)
        
        menu_archivo.addSeparator()
        
        accion_salir = QAction("❌ Salir", self)
        accion_salir.triggered.connect(self.close)
        menu_archivo.addAction(accion_salir)
        
        # Menú Ayuda
        menu_ayuda = menubar.addMenu("&Ayuda")
        
        accion_acerca = QAction("ℹ Acerca de", self)
        accion_acerca.triggered.connect(self.mostrar_acerca_de)
        menu_ayuda.addAction(accion_acerca)
    
    def _crear_widgets_centrales(self):
        """Crear widgets centrales con tabs."""
        widget_central = QWidget()
        self.setCentralWidget(widget_central)
        
        layout = QVBoxLayout(widget_central)
        
        # Crear tabs
        self.tabs = QTabWidget()
        
        # Tab Dashboard
        self.dashboard_widget = DashboardWidget(self.config)
        self.tabs.addTab(self.dashboard_widget, "📊 Dashboard")
        
        # Tab Gráficas
        self.graphs_widget = GraphsWidget(self.config)
        self.tabs.addTab(self.graphs_widget, "📈 Gráficas")
        
        layout.addWidget(self.tabs)
    
    def _crear_status_bar(self):
        """Crear barra de estado."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.label_status_puerto = QLabel("Puerto: -")
        self.label_status_datos = QLabel("Datos: 0")
        self.label_status_errores = QLabel("Errores: 0")
        
        self.status_bar.addWidget(self.label_status_puerto)
        self.status_bar.addWidget(self.label_status_datos)
        self.status_bar.addWidget(self.label_status_errores)
    
    def actualizar_lista_puertos(self):
        """Actualizar lista de puertos disponibles."""
        if not self.serial_manager:
            return
        
        puertos = self.serial_manager.listar_puertos_disponibles()
        self.combo_puerto.clear()
        self.combo_puerto.addItems(puertos)
        
        # Seleccionar puerto por defecto si existe
        puerto_default = self.config.get('connection', {}).get('port', '')
        if puerto_default in puertos:
            self.combo_puerto.setCurrentText(puerto_default)
    
    def conectar(self):
        """Conectar al puerto seleccionado."""
        if not self.serial_manager:
            logger.error("SerialManager no inicializado.")
            return
        
        puerto = self.combo_puerto.currentText()
        
        if not puerto:
            QMessageBox.warning(
                self,
                "Puerto no seleccionado",
                "Por favor seleccione un puerto antes de conectar."
            )
            return
        
        logger.info(f"Intentando conectar a: {puerto}")
        
        # Configurar callback ANTES de conectar
        self.serial_manager._callback_datos = self._on_data_received
        
        # Intentar conectar
        try:
            exito = self.serial_manager.conectar(puerto)
            
            if exito:
                self.conectado = True
                self.datos_recibidos = 0
                
                # Actualizar UI
                self.btn_conectar.setEnabled(False)
                self.btn_desconectar.setEnabled(True)
                self.combo_puerto.setEnabled(False)
                self.btn_iniciar_log.setEnabled(True)
                
                if CALIBRATION_AVAILABLE:
                    self.btn_calibrar.setEnabled(True)
                
                self.label_estado.setText("🟢 Conectado")
                self.label_estado.setStyleSheet("color: green; font-weight: bold;")
                
                baudrate = self.config.get('conexion', {}).get('baudrate', 115200)
                logger.info(f"Conectado a {puerto} ({baudrate} baud)")
            else:
                QMessageBox.critical(
                    self,
                    "Error de Conexión",
                    f"No se pudo conectar al puerto {puerto}.\n\n"
                    "Verifique que:\n"
                    "- El puerto esté disponible\n"
                    "- No esté siendo usado por otra aplicación\n"
                    "- El dispositivo esté conectado"
                )
        
        except Exception as e:
            logger.error(f"Error al conectar: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Error al conectar:\n{str(e)}"
            )
    
    def desconectar(self):
        """Desconectar del puerto."""
        if not self.serial_manager:
            return
        
        logger.info("Desconectando...")
        
        try:
            # Detener logging si está activo
            if self.data_logger and self.data_logger.esta_activo:
                self.data_logger.detener()
            
            # Desconectar serial manager
            self.serial_manager.desconectar()
            
            self.conectado = False
            
            # Actualizar UI
            self.btn_conectar.setEnabled(True)
            self.btn_desconectar.setEnabled(False)
            self.combo_puerto.setEnabled(True)
            self.btn_iniciar_log.setEnabled(False)
            self.btn_detener_log.setEnabled(False)
            
            if CALIBRATION_AVAILABLE:
                self.btn_calibrar.setEnabled(False)
            
            self.label_estado.setText("⚫ Desconectado")
            self.label_estado.setStyleSheet("color: gray; font-weight: bold;")
            
            logger.info("Desconectado exitosamente.")
        
        except Exception as e:
            logger.error(f"Error al desconectar: {e}", exc_info=True)
    
    def _on_data_received(self, datos: ShockDynoData):
        """
        Callback invocado desde thread del serial manager.
        
        IMPORTANTE: NO actualizar UI directamente desde aquí.
        Usar signal para thread-safe communication.
        
        Args:
            datos: Datos parseados del banco de pruebas (ShockDynoData)
        """
        if not datos.valido:
            logger.warning("Datos inválidos, ignorando.")
            return
        
        try:
            # Guardar último dato para calibración
            self.ultimo_dato = datos
            
            # Emitir signal para actualizar UI (thread-safe)
            self.datos_recibidos_signal.emit(datos)
        
        except Exception as e:
            logger.error(f"Error en callback de datos: {e}", exc_info=True)
    
    def _actualizar_ui_con_datos(self, datos: ShockDynoData):
        """
        Actualizar UI de forma thread-safe.
        
        Este método es llamado por el signal desde el main thread de Qt.
        
        Args:
            datos: Datos parseados del banco de pruebas
        """
        try:
            # Incrementar contador
            self.datos_recibidos += 1
            
            # Actualizar dashboard
            if self.dashboard_widget:
                self.dashboard_widget.actualizar_datos(datos)
            
            # Actualizar gráficas
            if self.graphs_widget:
                self.graphs_widget.agregar_dato(datos)
            
            # Agregar a buffer
            if self.data_buffer:
                self.data_buffer.push(datos)
            
            # Logging si está activo
            if self.data_logger and self.data_logger.esta_activo:
                self.data_logger.registrar_dato(datos)
            
            # Verificar alarmas
            if self.alarm_manager:
                alarmas = self.alarm_manager.check(datos)
                if alarmas:
                    self._mostrar_alarmas(alarmas)
        
        except Exception as e:
            logger.error(f"Error actualizando UI con datos: {e}", exc_info=True)
    
    def _mostrar_alarmas(self, alarmas: list):
        """
        Mostrar alarmas activas.
        
        Args:
            alarmas: Lista de mensajes de alarma
        """
        # Por ahora solo log, después agregar notificaciones visuales
        for alarma in alarmas:
            logger.warning(f"ALARMA: {alarma}")
    
    def actualizar_status_bar(self):
        """Actualizar barra de estado con estadísticas."""
        if self.conectado and self.serial_manager:
            puerto = self.serial_manager.puerto
            self.label_status_puerto.setText(f"Puerto: {puerto}")
            self.label_status_datos.setText(f"Datos: {self.datos_recibidos}")
            
            # Errores si están disponibles
            if hasattr(self.serial_manager, 'errores'):
                self.label_status_errores.setText(f"Errores: {self.serial_manager.errores}")
        else:
            self.label_status_puerto.setText("Puerto: -")
            self.label_status_datos.setText(f"Datos: {self.datos_recibidos}")
            self.label_status_errores.setText("Errores: 0")
    
    def iniciar_logging(self):
        """Iniciar logging de datos a CSV."""
        if not self.data_logger:
            return
        
        try:
            self.data_logger.iniciar()
            
            self.btn_iniciar_log.setEnabled(False)
            self.btn_detener_log.setEnabled(True)
            
            logger.info("Logging iniciado.")
            QMessageBox.information(
                self,
                "Logging Iniciado",
                f"Datos guardándose en:\n{self.data_logger.ruta_archivo_actual}"
            )
        
        except Exception as e:
            logger.error(f"Error iniciando logging: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Error al iniciar logging:\n{str(e)}"
            )
    
    def detener_logging(self):
        """Detener logging de datos."""
        if not self.data_logger:
            return
        
        try:
            archivo = self.data_logger.ruta_archivo_actual
            self.data_logger.detener()
            
            self.btn_iniciar_log.setEnabled(True)
            self.btn_detener_log.setEnabled(False)
            
            logger.info("Logging detenido.")
            QMessageBox.information(
                self,
                "Logging Detenido",
                f"Datos guardados en:\n{archivo}"
            )
        
        except Exception as e:
            logger.error(f"Error deteniendo logging: {e}", exc_info=True)
    
    def _abrir_calibracion(self):
        """Abrir diálogo de calibración."""
        if not CALIBRATION_AVAILABLE:
            QMessageBox.warning(
                self,
                "No Disponible",
                "El módulo de calibración no está disponible."
            )
            return
        
        if not self.conectado:
            QMessageBox.warning(
                self,
                "No Conectado",
                "Debe estar conectado para calibrar."
            )
            return
        
        try:
            dialog = CalibrationDialog(
                config=self.config,
                ultimo_dato=self.ultimo_dato,
                callback_lectura=None,  # Opcional: puedes pasar un callback si quieres
                parent=self
            )
            dialog.exec_()
        
        except Exception as e:
            logger.error(f"Error abriendo diálogo de calibración: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Error al abrir calibración:\n{str(e)}"
            )
    
    def abrir_configuracion(self):
        """Abrir diálogo de configuración."""
        try:
            dialog = ConfigDialog(config=self.config, parent=self)
            
            if dialog.exec_():
                # Usuario aceptó, guardar configuración
                if self.config_manager:
                    self.config_manager.save_config(self.config)
                    logger.info("Configuración guardada.")
        
        except Exception as e:
            logger.error(f"Error abriendo configuración: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Error al abrir configuración:\n{str(e)}"
            )
    
    def mostrar_acerca_de(self):
        """Mostrar diálogo Acerca de."""
        QMessageBox.about(
            self,
            "Acerca de Shock Dyno Monitor",
            f"<h2>Shock Dyno Monitor</h2>"
            f"<p>Versión {self.config['ui']['version']}</p>"
            f"<p>Sistema de monitoreo para banco de pruebas de amortiguadores.</p>"
            f"<p><b>Protocolo:</b> Speeduino 2025.01.4</p>"
            f"<p><b>Autor:</b> Desarrollado con GitHub Copilot</p>"
        )
    
    def closeEvent(self, event):
        """Manejar cierre de ventana."""
        if self.conectado:
            respuesta = QMessageBox.question(
                self,
                "Confirmar Salida",
                "¿Está seguro de salir?\n\nSe desconectará del puerto serial.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if respuesta == QMessageBox.Yes:
                self.desconectar()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()