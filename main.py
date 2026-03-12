"""
main.py - Punto de entrada de la aplicación Shock Dyno Monitor.

Inicializa el logging de la aplicación, carga la configuración
y lanza la ventana principal de PyQt5.

Uso:
    python main.py

Requisitos:
    pip install -r requirements.txt

Plataforma:
    Windows 10/11 con Python 3.11+
"""

import logging
import sys
import os

# Asegurarse de que el directorio raíz del proyecto esté en el path de Python,
# para que los imports relativos funcionen correctamente al ejecutar desde cualquier
# directorio de trabajo.
DIRECTORIO_RAIZ = os.path.dirname(os.path.abspath(__file__))
if DIRECTORIO_RAIZ not in sys.path:
    sys.path.insert(0, DIRECTORIO_RAIZ)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from utils.config_manager import ConfigManager
from ui.main_window import MainWindow


def configurar_logging() -> None:
    """
    Configura el sistema de logging de la aplicación.

    Envía los mensajes a consola (stdout) con formato:
    [NIVEL] timestamp - nombre_modulo - mensaje

    Los niveles van desde DEBUG (más detallado) hasta CRITICAL (solo errores críticos).
    """
    formato = "%(levelname)-8s %(asctime)s - %(name)s - %(message)s"
    logging.basicConfig(
        level=logging.DEBUG,
        format=formato,
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # Silenciar logs muy verbosos de módulos de terceros
    logging.getLogger("PyQt5").setLevel(logging.WARNING)
    logging.getLogger("pyqtgraph").setLevel(logging.WARNING)


def main() -> None:
    """
    Función principal de la aplicación.

    Flujo de inicialización:
    1. Configurar el sistema de logging.
    2. Crear la aplicación Qt (QApplication).
    3. Cargar la configuración desde config/default_config.json.
    4. Crear y mostrar la ventana principal.
    5. Ejecutar el loop de eventos de Qt.

    La aplicación se cierra cuando el usuario cierra la ventana principal
    o presiona Ctrl+Q.
    """
    # Inicializar logging
    configurar_logging()
    logger = logging.getLogger(__name__)
    logger.info("Iniciando Shock Dyno Monitor...")

    # Habilitar escalado de DPI alto para pantallas 4K/HiDPI (Windows)
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Crear la aplicación Qt
    app = QApplication(sys.argv)
    app.setApplicationName("Shock Dyno Monitor")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("ShockDynoMonitor")

    # Cargar configuración
    try:
        config_manager = ConfigManager()
        config = config_manager.cargar_config()
        logger.info("Configuración cargada correctamente.")
    except Exception as e:
        logger.error(f"Error al cargar configuración: {e}")
        config = {}
        config_manager = ConfigManager()

    # Crear y mostrar la ventana principal
    try:
        ventana = MainWindow(config=config, config_manager=config_manager)
        ventana.show()
        logger.info("Ventana principal mostrada.")
    except Exception as e:
        logger.critical(f"Error fatal al iniciar la UI: {e}")
        sys.exit(1)

    # Ejecutar el loop de eventos de Qt
    codigo_salida = app.exec_()
    logger.info(f"Aplicación terminada con código {codigo_salida}.")
    sys.exit(codigo_salida)


if __name__ == "__main__":
    main()
