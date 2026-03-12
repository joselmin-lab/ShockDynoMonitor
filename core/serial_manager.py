"""
Módulo: serial_manager.py
Descripción: Gestión de la conexión serial con la ECU Speeduino.

Implementa dos threads:
  - _hilo_tx: Envía el comando 0x41 cada 50ms (20Hz).
  - _hilo_rx: Lee y parsea las respuestas de la ECU.

También incluye un modo SIMULADOR que genera datos aleatorios realistas
sin necesidad de hardware real, útil para desarrollo y testing.

Threading:
  - Se usa threading.Lock para proteger el acceso a recursos compartidos.
  - Los threads son daemons (se limpian automáticamente al cerrar la app).
"""

import logging
import random
import struct
import threading
import time
from typing import Callable, List, Optional

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_DISPONIBLE = True
except ImportError:
    PYSERIAL_DISPONIBLE = False

from core.speeduino_protocol import SpeeduinoProtocol
from core.data_parser import SpeeduinoDataParser, ShockDynoData

# Logger del módulo
logger = logging.getLogger(__name__)

# Nombre especial para el modo simulador
NOMBRE_SIMULADOR = "SIMULADOR"


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
    Gestiona la conexión serial con la ECU Speeduino.

    Coordina dos threads:
      - Thread TX: Envía comando 0x41 cada 50ms.
      - Thread RX: Lee respuestas y parsea datos.

    Soporta modo SIMULADOR para testing sin hardware.

    Ejemplo de uso::

        def mi_callback(datos: ShockDynoData) -> None:
            print(f"Fuerza: {datos.fuerza_n} N")

        manager = SerialManager(config=mi_config, callback_datos=mi_callback)
        manager.conectar("COM3")
        # ... esperar datos ...
        manager.desconectar()
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        callback_datos: Optional[Callable[[ShockDynoData], None]] = None,
    ) -> None:
        """
        Inicializa el SerialManager.

        Args:
            config: Diccionario de configuración de la conexión y sensores.
            callback_datos: Función que se llama con cada nuevo ShockDynoData.
                            Se llama desde el thread RX (o simulador).
        """
        self._config = config or {}
        self._cfg_conexion = self._config.get("conexion", {})
        self._cfg_simulador = self._config.get("simulador", {})

        # Callback para notificar datos nuevos a la UI
        self._callback_datos = callback_datos

        # Protocolo y parser
        self._protocolo = SpeeduinoProtocol()
        self._parser = SpeeduinoDataParser(config=self._config)

        # Estado de conexión
        self._conectado: bool = False
        self._modo_simulador: bool = False
        self._puerto_actual: str = ""

        # Puerto serial (solo en modo real)
        self._serial: Optional[serial.Serial] = None

        # Threads de comunicación
        self._hilo_tx: Optional[threading.Thread] = None
        self._hilo_rx: Optional[threading.Thread] = None
        self._hilo_simulador: Optional[threading.Thread] = None

        # Evento para detener threads
        self._evento_detener = threading.Event()

        # Lock para acceso al puerto serial
        self._lock_serial = threading.Lock()

        # Estadísticas
        self.estadisticas = EstadisticasComunicacion()

        # Intervalo de polling en segundos
        self._intervalo = self._cfg_conexion.get("intervalo_polling_ms", 50) / 1000.0

        logger.debug("SerialManager inicializado.")

    def listar_puertos_disponibles(self) -> List[str]:
        """
        Lista los puertos seriales disponibles en el sistema más el SIMULADOR.

        Incluye siempre "SIMULADOR" como primera opción para testing.

        Returns:
            Lista de cadenas con nombres de puertos (ej: ["SIMULADOR", "COM3", "COM5"]).

        Ejemplo::

            manager = SerialManager()
            puertos = manager.listar_puertos_disponibles()
            # ["SIMULADOR", "COM3", "COM4"]
        """
        puertos = [NOMBRE_SIMULADOR]

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
        Establece la conexión con la ECU Speeduino o inicia el simulador.

        Si el puerto es "SIMULADOR", inicia el modo simulador con datos
        aleatorios realistas. Para puertos COM reales, abre la conexión
        serial y espera el delay de inicialización configurado.

        Args:
            puerto: Nombre del puerto ("SIMULADOR" o "COMx" en Windows,
                    "/dev/ttyUSB0" en Linux).

        Returns:
            True si la conexión se estableció correctamente, False si hubo error.

        Ejemplo::

            manager = SerialManager()
            if manager.conectar("SIMULADOR"):
                print("Simulador activo")
            if manager.conectar("COM3"):
                print("Conectado a ECU real")
        """
        if self._conectado:
            logger.warning("Ya existe una conexión activa. Desconectar primero.")
            return False

        self._puerto_actual = puerto
        self._evento_detener.clear()

        if puerto == NOMBRE_SIMULADOR:
            return self._iniciar_simulador()
        else:
            return self._iniciar_conexion_real(puerto)

    def _iniciar_simulador(self) -> bool:
        """
        Inicia el modo simulador con generación de datos aleatorios realistas.

        Genera datos dentro de los rangos configurados en config["simulador"].

        Returns:
            True siempre (el simulador no puede fallar).
        """
        self._modo_simulador = True
        self._conectado = True

        # Iniciar thread del simulador
        self._hilo_simulador = threading.Thread(
            target=self._worker_simulador,
            name="SimuladorThread",
            daemon=True,
        )
        self._hilo_simulador.start()

        logger.info("Modo SIMULADOR iniciado.")
        return True

    def _iniciar_conexion_real(self, puerto: str) -> bool:
        """
        Abre la conexión serial real con la ECU Speeduino.

        Configura el puerto a 115200 baudios, 8N1, y espera el delay
        de inicialización (por defecto 10 segundos) antes de empezar
        a enviar comandos.

        Args:
            puerto: Nombre del puerto COM (ej: "COM3").

        Returns:
            True si la conexión se abrió correctamente, False si hubo error.
        """
        if not PYSERIAL_DISPONIBLE:
            logger.error("pyserial no está instalado.")
            return False

        try:
            baudrate = self._cfg_conexion.get("baudrate", 115200)
            timeout = self._cfg_conexion.get("timeout", 1.0)
            delay = self._cfg_conexion.get("delay_conexion", 10)

            logger.info(f"Conectando a {puerto} a {baudrate} baudios...")

            self._serial = serial.Serial(
                port=puerto,
                baudrate=baudrate,
                bytesize=self._cfg_conexion.get("bits_datos", 8),
                parity=self._cfg_conexion.get("paridad", "N"),
                stopbits=self._cfg_conexion.get("bits_parada", 1),
                timeout=timeout,
            )

            self._modo_simulador = False
            self._conectado = True

            # Delay obligatorio después de conectar (la ECU necesita inicializarse)
            logger.info(
                f"Conexión establecida. Esperando {delay}s para inicialización de ECU..."
            )
            # El delay se hace en un thread para no bloquear la UI
            hilo_delay = threading.Thread(
                target=self._delay_y_arrancar_threads,
                args=(delay,),
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
        Espera el delay de inicialización y luego arranca los threads TX/RX.

        Este método corre en su propio thread para no bloquear la UI durante
        el delay obligatorio de 10 segundos después de conectar a la ECU.

        Args:
            delay_segundos: Segundos a esperar antes de iniciar comunicación.
        """
        # Esperar en pequeños intervalos para poder cancelar si se desconecta
        for _ in range(delay_segundos * 10):
            if self._evento_detener.is_set():
                return
            time.sleep(0.1)

        if not self._evento_detener.is_set():
            logger.info("Delay de inicialización completado. Iniciando comunicación.")
            self._arrancar_threads_tx_rx()

    def _arrancar_threads_tx_rx(self) -> None:
        """
        Arranca los threads TX y RX para comunicación bidireccional.

        Thread TX: Envía comando 0x41 cada 50ms.
        Thread RX: Lee respuestas y las parsea.
        """
        self._hilo_tx = threading.Thread(
            target=self._worker_tx,
            name="TxThread",
            daemon=True,
        )
        self._hilo_rx = threading.Thread(
            target=self._worker_rx,
            name="RxThread",
            daemon=True,
        )
        self._hilo_tx.start()
        self._hilo_rx.start()
        logger.debug("Threads TX y RX iniciados.")

    def _worker_tx(self) -> None:
        """
        Worker del thread de transmisión (TX).

        Envía el comando de datos en tiempo real (0x41 con CRC32) cada 50ms.
        Se ejecuta hasta que _evento_detener sea señalado.
        """
        comando = self._protocolo.construir_comando_realtime()
        logger.debug(f"Comando TX listo: {comando.hex(' ').upper()}")

        while not self._evento_detener.is_set():
            inicio = time.time()
            try:
                with self._lock_serial:
                    if self._serial and self._serial.is_open:
                        self._serial.write(comando)
                        self.estadisticas.incrementar_enviados()
            except Exception as e:
                logger.error(f"Error en TX: {e}")

            # Esperar el tiempo restante del intervalo de polling
            transcurrido = time.time() - inicio
            tiempo_espera = max(0, self._intervalo - transcurrido)
            self._evento_detener.wait(tiempo_espera)

    def _worker_rx(self) -> None:
        """
        Worker del thread de recepción (RX).

        Lee bytes del puerto serial, detecta el header de respuesta (00 XX 00),
        acumula el payload completo y verifica el CRC32.
        Cuando recibe un mensaje válido, parsea los datos y llama al callback.
        """
        buffer_rx = bytearray()

        while not self._evento_detener.is_set():
            try:
                with self._lock_serial:
                    if not (self._serial and self._serial.is_open):
                        time.sleep(0.01)
                        continue
                    bytes_disponibles = self._serial.in_waiting

                if bytes_disponibles > 0:
                    with self._lock_serial:
                        nuevos_bytes = self._serial.read(bytes_disponibles)
                    buffer_rx.extend(nuevos_bytes)

                    # Intentar parsear mensajes completos del buffer
                    buffer_rx = self._procesar_buffer(buffer_rx)
                else:
                    time.sleep(0.005)  # 5ms de espera si no hay datos

            except Exception as e:
                logger.error(f"Error en RX: {e}")
                self.estadisticas.incrementar_errores_timeout()
                time.sleep(0.1)

    def _procesar_buffer(self, buffer: bytearray) -> bytearray:
        """
        Procesa el buffer RX buscando mensajes completos de la ECU.

        Busca el patrón de header (00 XX 00), extrae mensajes completos
        y los parsea. Descarta bytes corruptos al principio del buffer.

        Args:
            buffer: Buffer de bytes recibidos.

        Returns:
            Buffer con los bytes no procesados (parte restante).
        """
        while len(buffer) >= self._protocolo.TAMANO_HEADER_RX:
            # Verificar si los primeros bytes forman un header válido
            header_valido, length = self._protocolo.validar_header_respuesta(
                bytes(buffer[:3])
            )

            if not header_valido:
                # Descartar el primer byte y buscar el inicio del siguiente mensaje
                buffer = buffer[1:]
                continue

            # Calcular cuántos bytes necesitamos en total
            tamano_total = self._protocolo.calcular_tamano_respuesta_esperada(length)

            if len(buffer) < tamano_total:
                # No tenemos el mensaje completo todavía
                break

            # Tenemos suficientes bytes, intentar parsear
            mensaje = bytes(buffer[:tamano_total])
            valido, payload = self._protocolo.parsear_respuesta(mensaje)

            if valido and payload:
                self.estadisticas.incrementar_recibidos()
                datos = self._parser.parsear(payload)
                if datos.valido and self._callback_datos:
                    try:
                        self._callback_datos(datos)
                    except Exception as e:
                        logger.error(f"Error en callback de datos: {e}")
            else:
                self.estadisticas.incrementar_errores_crc()
                logger.warning("Mensaje recibido con CRC inválido, descartando.")

            # Remover el mensaje procesado del buffer
            buffer = buffer[tamano_total:]

        return buffer

    def _worker_simulador(self) -> None:
        """
        Worker del thread del simulador.

        Genera datos aleatorios realistas dentro de los rangos configurados
        y los envía al callback cada 50ms, simulando el comportamiento
        de la ECU Speeduino.

        Los datos se generan con variación suave para simular movimiento real
        del amortiguador.
        """
        # Obtener rangos del simulador desde la config
        cfg_sim = self._cfg_simulador

        fuerza_min = cfg_sim.get("fuerza_min", 100.0)
        fuerza_max = cfg_sim.get("fuerza_max", 1500.0)
        recorrido_min = cfg_sim.get("recorrido_min", 10.0)
        recorrido_max = cfg_sim.get("recorrido_max", 80.0)
        temp_amo_min = cfg_sim.get("temp_amortiguador_min", 25.0)
        temp_amo_max = cfg_sim.get("temp_amortiguador_max", 55.0)
        temp_res_min = cfg_sim.get("temp_reservorio_min", 20.0)
        temp_res_max = cfg_sim.get("temp_reservorio_max", 50.0)
        vel_min = cfg_sim.get("velocidad_min", 50.0)
        vel_max = cfg_sim.get("velocidad_max", 400.0)

        # Valores iniciales del simulador (punto de partida centrado)
        fuerza_actual = (fuerza_min + fuerza_max) / 2
        recorrido_actual = (recorrido_min + recorrido_max) / 2
        temp_amo_actual = temp_amo_min + 5.0
        temp_res_actual = temp_res_min + 5.0
        vel_actual = (vel_min + vel_max) / 2

        from datetime import datetime as dt

        logger.info("Worker del simulador iniciado.")

        while not self._evento_detener.is_set():
            inicio = time.time()

            try:
                # Generar variaciones suaves usando random walk
                fuerza_actual = self._random_walk(
                    fuerza_actual, fuerza_min, fuerza_max, paso=50.0
                )
                recorrido_actual = self._random_walk(
                    recorrido_actual, recorrido_min, recorrido_max, paso=5.0
                )
                temp_amo_actual = self._random_walk(
                    temp_amo_actual, temp_amo_min, temp_amo_max, paso=0.5
                )
                temp_res_actual = self._random_walk(
                    temp_res_actual, temp_res_min, temp_res_max, paso=0.3
                )
                vel_actual = self._random_walk(
                    vel_actual, vel_min, vel_max, paso=20.0
                )

                self.estadisticas.incrementar_enviados()
                self.estadisticas.incrementar_recibidos()

                # Crear ShockDynoData simulado
                datos = ShockDynoData(
                    timestamp=dt.now(),
                    fuerza_n=round(fuerza_actual, 2),
                    recorrido_mm=round(recorrido_actual, 2),
                    temp_amortiguador_c=round(temp_amo_actual, 1),
                    temp_reservorio_c=round(temp_res_actual, 1),
                    velocidad_rpm=int(vel_actual),
                    valido=True,
                )

                # Llamar al callback con los datos simulados
                if self._callback_datos:
                    try:
                        self._callback_datos(datos)
                    except Exception as e:
                        logger.error(f"Error en callback del simulador: {e}")

            except Exception as e:
                logger.error(f"Error en worker simulador: {e}")

            # Esperar el intervalo de polling
            transcurrido = time.time() - inicio
            tiempo_espera = max(0, self._intervalo - transcurrido)
            self._evento_detener.wait(tiempo_espera)

        logger.info("Worker del simulador detenido.")

    @staticmethod
    def _random_walk(
        valor_actual: float,
        minimo: float,
        maximo: float,
        paso: float,
    ) -> float:
        """
        Genera un nuevo valor con variación aleatoria suave (random walk).

        El valor nuevo se mantiene dentro de los límites [minimo, maximo].

        Args:
            valor_actual: Valor actual del parámetro.
            minimo: Límite inferior permitido.
            maximo: Límite superior permitido.
            paso: Máxima variación por paso.

        Returns:
            Nuevo valor con variación aleatoria, dentro de [minimo, maximo].
        """
        variacion = random.uniform(-paso, paso)
        nuevo_valor = valor_actual + variacion
        return max(minimo, min(maximo, nuevo_valor))

    def desconectar(self) -> None:
        """
        Detiene los threads y cierra la conexión serial.

        Señala el evento de detención, espera a que los threads terminen
        y cierra el puerto serial si estaba abierto.

        Ejemplo::

            manager.desconectar()
            print("Desconectado")
        """
        if not self._conectado:
            return

        logger.info(f"Desconectando de {self._puerto_actual}...")

        # Señalar a los threads que deben detenerse
        self._evento_detener.set()

        # Esperar a que los threads terminen (máximo 2 segundos cada uno)
        for hilo in [self._hilo_tx, self._hilo_rx, self._hilo_simulador]:
            if hilo and hilo.is_alive():
                hilo.join(timeout=2.0)

        # Cerrar el puerto serial si estaba abierto
        with self._lock_serial:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                    logger.info("Puerto serial cerrado.")
                except Exception as e:
                    logger.error(f"Error al cerrar puerto serial: {e}")
            self._serial = None

        self._conectado = False
        self._modo_simulador = False
        self._hilo_tx = None
        self._hilo_rx = None
        self._hilo_simulador = None

        logger.info("Desconectado correctamente.")

    @property
    def esta_conectado(self) -> bool:
        """
        Indica si hay una conexión activa (real o simulador).

        Returns:
            True si hay conexión activa.
        """
        return self._conectado

    @property
    def es_simulador(self) -> bool:
        """
        Indica si la conexión activa es el modo simulador.

        Returns:
            True si está en modo simulador.
        """
        return self._modo_simulador

    @property
    def puerto(self) -> str:
        """
        Retorna el nombre del puerto actualmente conectado.

        Returns:
            Nombre del puerto o cadena vacía si no hay conexión.
        """
        return self._puerto_actual
