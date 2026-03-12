"""
Entry point de la aplicación Shock Dyno Monitor.

Este módulo inicializa todos los componentes y lanza la interfaz gráfica.
"""

import sys
import logging
from PyQt5.QtWidgets import QApplication

from utils.config_manager import ConfigManager
from utils.data_buffer import DataBuffer
from core.speeduino_protocol import SpeeduinoProtocol
from core.serial_manager import SerialManager
from core.data_parser import SpeeduinoDataParser
from core.data_logger import DataLogger
from core.alarm_manager import AlarmManager
from ui.main_window import MainWindow


def configurar_logging():
    """Configurar sistema de logging."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(levelname)-8s %(asctime)s - %(name)s - %(message)s',
        datefmt='%H:%M:%S'
    )


def main():
    """Función principal."""
    # Configurar logging
    configurar_logging()
    
    logger = logging.getLogger(__name__)
    logger.info("Iniciando Shock Dyno Monitor...")
    
    try:
        # Cargar configuración
        config_manager = ConfigManager()
        config = config_manager.cargar_configuracion()
        logger.info("Configuración cargada correctamente.")
        
        # Inicializar componentes core
        protocol = SpeeduinoProtocol()
        data_parser = SpeeduinoDataParser(config)
        serial_manager = SerialManager(protocol, config)
        data_logger = DataLogger(config)
        alarm_manager = AlarmManager(config)
        data_buffer = DataBuffer(config)
        
        # Crear aplicación Qt
        app = QApplication(sys.argv)
        app.setApplicationName("Shock Dyno Monitor")
        app.setOrganizationName("ShockDyno")
        
        # Crear ventana principal
        window = MainWindow(config=config)
        
        # Inyectar dependencias
        window.config_manager = config_manager
        window.serial_manager = serial_manager
        window.data_parser = data_parser
        window.data_logger = data_logger
        window.alarm_manager = alarm_manager
        window.data_buffer = data_buffer
        
        # Actualizar lista de puertos disponibles
        window.actualizar_lista_puertos()
        
        # Mostrar ventana
        window.show()
        logger.info("Ventana principal mostrada.")
        
        # Ejecutar aplicación
        sys.exit(app.exec_())
    
    except Exception as e:
        logger.critical(f"Error fatal al iniciar la UI: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()