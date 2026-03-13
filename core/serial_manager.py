import logging
import threading
import time
from datetime import datetime
from typing import Callable, List, Optional

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_DISPONIBLE = True
except ImportError:
    PYSERIAL_DISPONIBLE = False

from core.data_parser import ShockDynoData

# Logger del módulo
logger = logging.getLogger(__name__)


class EstadisticasComunicacion:
    """
    Clase que almacena estadísticas de la comunicación serial.

    Attributes:
        paquetes_enviados: Número total de comandos TX enviados.
        paquetes_recibidos: Número total de respuestas RX recibidas.
        errores_crc: Número de respuestas con CRC inválido.
        errores_timeout: Número de timeouts de lectura.
        ultimo_dato: Último ShockDynoData recibido.
    """

    def __init__(self) -> None:
        """Inicializa todas las estadísticas a cero."""
        self.paquetes_enviados: int = 0
        self.paquetes_recibidos: int = 0
        self.errores_crc: int = 0
        self.errores_timeout: int = 0
        self.ultimo_dato: Optional[ShockDynoData] = None
        self._lock = threading.Lock()

    def incrementar_enviados(self) -> None:
        """Incrementa el contador de paquetes enviados de forma thread-safe."""
        with self._lock:
            self.paquetes_enviados += 1

    def incrementar_recibidos(self) -> None:
        """Incrementa el contador de paquetes recibidos de forma thread-safe."""
        with self._lock:
            self.paquetes_recibidos += 1

    def incrementar_errores_crc(self) -> None:
        """Incrementa el contador de errores CRC de forma thread-safe."""
        with self._lock:
            self.errores_crc += 1

    def incrementar_errores_timeout(self) -> None:
        """Incrementa el contador de timeouts de forma thread-safe."""
        with self._lock:
            self.errores_timeout += 1

    def porcentaje_exito(self) -> float:
        """
        Calcula el porcentaje de paquetes recibidos correctamente.

        Returns:
            Porcentaje de éxito (0.0 a 100.0).
        """
        with self._lock:
            if self.paquetes_enviados == 0:
                return 0.0
            return (self.paquetes_recibidos / self.paquetes_enviados) * 100.0

    def resumen(self) -> str:
        """
        Genera un resumen de las estadísticas para mostrar en la UI.

        Returns:
            Cadena de texto con el resumen de estadísticas.
        """
        with self._lock:
            return (
                f"TX:{self.paquetes_enviados} "
                f"RX:{self.paquetes_recibidos} "
                f"CRC_ERR:{self.errores_crc} "
                f"TIMEOUT:{self.errores_timeout} "
                f"({self.porcentaje_exito():.1f}%)"
            )


class SerialManager:
    """
    Gestiona la conexión serial con un Arduino que transmite datos en formato
    ASCII separados por comas.

    El Arduino envía líneas de texto con el siguiente formato::

        Fuerza_N,Recorrido_mm,Temp_Amortiguador_C,Temp_Reservorio_C,Velocidad_RPM

    Un único hilo de comunicación lee las líneas con ``readline()`` y llama al
    callback de datos para cada lectura válida.
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        callback_datos: Optional[Callable[[ShockDynoData], None]] = None,
    ) -> None:
        """
        Inicializa el SerialManager.

        Args:
            config: Diccionario de configuración de la conexión.
            callback_datos: Función que se llama con cada nuevo ShockDynoData.
                            Se llama desde el thread de comunicación.
        """
        self._config = config or {}
        self._cfg_conexion = self._config.get("conexion", {})

        # Callback para notificar datos nuevos a la UI
        self._callback_datos = callback_datos

        # Estado de conexión
        self._conectado: bool = False
        self._puerto_actual: str = ""

        # Puerto serial
        self._serial: Optional[serial.Serial] = None

        # Hilo de comunicación
        self._hilo_comunicacion: Optional[threading.Thread] = None

        # Evento para detener threads
        self._evento_detener = threading.Event()

        # Lock para acceso al puerto serial
        self._lock_serial = threading.Lock()

        # Estadísticas
        self.estadisticas = EstadisticasComunicacion()

        logger.debug("SerialManager inicializado.")

    def listar_puertos_disponibles(self) -> List[str]:
        """
        Lista los puertos seriales disponibles en el sistema.
        """
        puertos = []

        if PYSERIAL_DISPONIBLE:
            try:
                puertos_sistema = serial.tools.list_ports.comports()
                for puerto in sorted(puertos_sistema):
                    puertos.append(puerto.device)
            except Exception as e:
                logger.error(f"Error listando puertos: {e}")

        return puertos

    def conectar(self, puerto: str) -> bool:
        """
        Establece la conexión con el Arduino.
        """
        if self._conectado:
            logger.warning("Ya existe una conexión activa. Desconectar primero.")
            return False

        self._puerto_actual = puerto
        self._evento_detener.clear()

        return self._iniciar_conexion_real(puerto)

    def _iniciar_conexion_real(self, puerto: str) -> bool:
        """
        Abre la conexión serial con el Arduino.
        """
        if not PYSERIAL_DISPONIBLE:
            logger.error("pyserial no está instalado.")
            return False

        try:
            baudrate = self._cfg_conexion.get("baudrate", 115200)

            logger.info(f"Conectando a {puerto} a {baudrate} baudios...")

            self._serial = serial.Serial(
                port=puerto,
                baudrate=baudrate,
                bytesize=self._cfg_conexion.get("bits_datos", 8),
                parity=self._cfg_conexion.get("paridad", "N"),
                stopbits=self._cfg_conexion.get("bits_parada", 1),
                timeout=1.0,
                write_timeout=0.5,
            )

            self._conectado = True

            # Delay en un thread para no bloquear la UI mientras el Arduino reinicia
            logger.info("Conexión establecida. Esperando reinicio del Arduino (2 s)...")
            hilo_delay = threading.Thread(
                target=self._delay_y_arrancar_threads,
                args=(2,),
                name="DelayThread",
                daemon=True,
            )
            hilo_delay.start()
            return True

        except serial.SerialException as e:
            logger.error(f"Error al abrir puerto {puerto}: {e}")
            self._conectado = False
            return False

    def _delay_y_arrancar_threads(self, delay_segundos: int) -> None:
        """
        Espera el delay de inicialización (para el auto-reset del Arduino) y
        luego arranca el hilo de comunicación.
        """
        for _ in range(delay_segundos * 10):
            if self._evento_detener.is_set():
                return
            time.sleep(0.1)

        if self._evento_detener.is_set():
            return

        with self._lock_serial:
            if self._serial and self._serial.is_open:
                self._serial.reset_input_buffer()

        logger.info("Iniciando lectura de datos del Arduino.")
        self._arrancar_hilo_comunicacion()

    def _arrancar_hilo_comunicacion(self) -> None:
        """
        Arranca el hilo de comunicación que lee las líneas del Arduino.
        """
        self._hilo_comunicacion = threading.Thread(
            target=self._worker_comunicacion,
            name="ComunicacionThread",
            daemon=True,
        )
        self._hilo_comunicacion.start()
        logger.debug("Hilo de comunicación iniciado.")

    def _worker_comunicacion(self) -> None:
        """
        Worker que lee líneas ASCII separadas por comas desde el Arduino.

        Formato esperado por línea::

            Fuerza_N,Recorrido_mm,Temp_Amortiguador_C,Temp_Reservorio_C,Velocidad_RPM
        """
        logger.info("Worker de comunicación serie (Arduino ASCII) iniciado.")

        while not self._evento_detener.is_set():
            try:
                linea_bytes = b""
                with self._lock_serial:
                    if self._serial and self._serial.is_open:
                        linea_bytes = self._serial.readline()

                if not linea_bytes:
                    continue

                texto = linea_bytes.decode("ascii", errors="ignore").strip()

                if not texto:
                    continue

                partes = texto.split(",")

                if len(partes) == 5:
                    try:
                        datos = ShockDynoData(
                            timestamp=datetime.now(),
                            fuerza_n=float(partes[0]),
                            recorrido_mm=float(partes[1]),
                            temp_amortiguador_c=float(partes[2]),
                            temp_reservorio_c=float(partes[3]),
                            velocidad_rpm=int(partes[4]),
                            valido=True,
                        )
                        self.estadisticas.incrementar_recibidos()
                        if self._callback_datos:
                            try:
                                self._callback_datos(datos)
                            except Exception as e:
                                logger.error(f"Error en callback de datos: {e}")
                    except ValueError as ve:
                        logger.warning(f"Error parseando valores: {texto!r} -> {ve}")
                        self.estadisticas.incrementar_errores_crc()
                else:
                    logger.warning(f"Línea con formato incorrecto ({len(partes)} campos): {texto!r}")
                    self.estadisticas.incrementar_errores_crc()

            except Exception as e:
                if self._evento_detener.is_set():
                    break
                logger.error(f"Error en comunicación serie: {e}")
                self.estadisticas.incrementar_errores_timeout()
                time.sleep(0.1)

        logger.info("Worker de comunicación serie detenido.")

    def desconectar(self) -> None:
        """
        Detiene el hilo de comunicación y cierra la conexión serial.
        """
        if not self._conectado:
            return

        logger.info(f"Desconectando de {self._puerto_actual}...")

        self._evento_detener.set()

        if self._hilo_comunicacion and self._hilo_comunicacion.is_alive():
            self._hilo_comunicacion.join(timeout=2.0)

        with self._lock_serial:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                    logger.info("Puerto serial cerrado.")
                except Exception as e:
                    logger.error(f"Error al cerrar puerto serial: {e}")
            self._serial = None

        self._conectado = False
        self._hilo_comunicacion = None

        logger.info("Desconectado correctamente.")

    def actualizar_calibracion(self, nueva_config: dict) -> None:
        """
        Actualiza la configuración en tiempo real.
        """
        self._config = nueva_config
        logger.info("Configuración del SerialManager actualizada.")

    @property
    def esta_conectado(self) -> bool:
        """Indica si hay una conexión activa."""
        return self._conectado

    @property
    def puerto(self) -> str:
        """Retorna el nombre del puerto actualmente conectado."""
        return self._puerto_actual
