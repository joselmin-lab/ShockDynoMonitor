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

    Usa un único hilo de comunicación síncrono (Master-Slave) que envía el
    comando y lee la respuesta en el mismo ciclo mediante lecturas bloqueantes 
    (sin in_waiting).
    Esto elimina la competencia por locks entre hilos independientes.

    Realiza handshake automático ('Q' → firma, 'F' → versión, 'S' → firma extendida) antes de
    iniciar el polling de datos. Soporta modo SIMULADOR para testing sin
    hardware.
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
        self.extended_signature: Optional[bytes] = None

        # Puerto serial (solo en modo real)
        self._serial: Optional[serial.Serial] = None

        # Hilo de comunicación síncrono (envío + recepción en un solo ciclo)
        self._hilo_comunicacion: Optional[threading.Thread] = None
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
        """
        if not PYSERIAL_DISPONIBLE:
            logger.error("pyserial no está instalado.")
            return False

        try:
            baudrate = self._cfg_conexion.get("baudrate", 115200)
            delay = self._cfg_conexion.get("delay_conexion", 10)

            logger.info(f"Conectando a {puerto} a {baudrate} baudios...")

            self._serial = serial.Serial(
                port=puerto,
                baudrate=baudrate,
                bytesize=self._cfg_conexion.get("bits_datos", 8),
                parity=self._cfg_conexion.get("paridad", "N"),
                stopbits=self._cfg_conexion.get("bits_parada", 1),
                timeout=self._cfg_conexion.get("timeout", 2.0),
                write_timeout=0.5,
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
        Espera el delay de inicialización, realiza el handshake y luego
        arranca los threads TX/RX.
        """
        # Esperar en pequeños intervalos para poder cancelar si se desconecta
        for _ in range(delay_segundos * 10):
            if self._evento_detener.is_set():
                return
            time.sleep(0.1)

        if self._evento_detener.is_set():
            return

        logger.info("Delay de inicialización completado. Realizando handshake...")
        if self._realizar_handshake():
            logger.info("Handshake exitoso. Iniciando comunicación.")
            self._arrancar_hilo_comunicacion()
        else:
            logger.error(
                "Handshake fallido: no se recibió firma de Speeduino. "
                "Verifica el puerto y que la ECU esté encendida."
            )
            self._conectado = False

    def _realizar_handshake(self) -> bool:
        """
        Realiza la secuencia de handshake con la ECU Speeduino.

        Envía el comando 'Q' y verifica que la respuesta contenga la firma
        "speeduino". Luego envía 'F' para consultar la versión del protocolo.
        Finalmente envía 'S' para leer la firma extendida.
        """
        try:
            timeout_handshake = self._cfg_conexion.get("timeout_handshake", 2.0)

            # Paso 1: Limpiar buffer y enviar 'Q', capturando referencia local
            ser = None
            with self._lock_serial:
                if not (self._serial and self._serial.is_open):
                    logger.error("Puerto serial no disponible para handshake.")
                    return False
                self._serial.reset_input_buffer()
                logger.debug("Handshake: enviando 'Q'...")
                self._serial.write(self._protocolo.construir_comando_handshake_q())
                ser = self._serial

            # Esperar al menos 500ms para dar tiempo a la ECU a responder
            time.sleep(max(timeout_handshake * 0.25, 0.5))

            # Leer con referencia local, fuera del lock
            respuesta_q = ser.read(32)

            logger.debug(f"Respuesta 'Q': {respuesta_q!r}")

            if b"speeduino" not in respuesta_q.lower():
                logger.warning(
                    f"Firma Speeduino no encontrada en respuesta 'Q': {respuesta_q!r}"
                )
                return False

            logger.info(f"Firma recibida: {respuesta_q.decode('ascii', errors='replace').strip()!r}")

            # Paso 2: Enviar 'F' para consultar versión del protocolo
            with self._lock_serial:
                if not (self._serial and self._serial.is_open):
                    return False
                logger.debug("Handshake: enviando 'F'...")
                self._serial.write(self._protocolo.construir_comando_handshake_f())
                ser = self._serial

            time.sleep(0.3)  # 300ms para dar tiempo a la respuesta F

            # Leer con referencia local, fuera del lock
            # La ECU responde exactamente 3 bytes: "002"
            respuesta_f = ser.read(3)

            logger.info(
                f"Versión de protocolo: {respuesta_f.decode('ascii', errors='replace').strip()!r}"
            )

            # Paso 3: Enviar 'S' para solicitar Extended Signature
            with self._lock_serial:
                if not (self._serial and self._serial.is_open):
                    return False
                logger.debug("Handshake: enviando 'S'...")
                
                comando_s = self._protocolo.construir_comando_handshake_s()
                # Asegurarse de que el comando sea de tipo bytes
                if isinstance(comando_s, str):
                    comando_s = comando_s.encode()
                    
                self._serial.write(comando_s)
                self._serial.flush()
                ser = self._serial

            time.sleep(0.1)
            
            # Leer los bytes disponibles en el buffer usando in_waiting
            bytes_disponibles = ser.in_waiting
            if bytes_disponibles > 0:
                self.extended_signature = ser.read(bytes_disponibles)
            else:
                self.extended_signature = b""
                
            logger.info(f"Extended signature recibida: {self.extended_signature!r}")

            # Limpiar cualquier dato residual del buffer antes de iniciar polling
            with self._lock_serial:
                if self._serial and self._serial.is_open:
                    self._serial.reset_input_buffer()
                    logger.debug("Buffer RX limpiado tras handshake completado.")

            # Pequeño delay para que la ECU procese y esté lista para el primer Read Page
            time.sleep(0.2)

            return True

        except Exception as e:
            logger.error(f"Error durante handshake: {e}")
            return False

    def _arrancar_hilo_comunicacion(self) -> None:
        """
        Arranca el hilo único de comunicación síncrona (Master-Slave).
        """
        # Limpiar buffer RX antes de iniciar el polling
        with self._lock_serial:
            if self._serial and self._serial.is_open:
                self._serial.reset_input_buffer()
                logger.debug("Buffer RX limpiado antes de iniciar polling.")

        self._hilo_comunicacion = threading.Thread(
            target=self._worker_comunicacion,
            name="ComunicacionThread",
            daemon=True,
        )
        self._hilo_comunicacion.start()
        logger.debug("Hilo de comunicación iniciado.")

    def _worker_comunicacion(self) -> None:
        """
        Worker del hilo de comunicación síncrona (Master-Slave).
        """
        # AQUI HACEMOS EL CAMBIO: en lugar de read_page() enviamos read_realtime()
        comando = self._protocolo.construir_comando_read_realtime()
        logger.debug(f"Comando listo: {comando.hex(' ').upper()}")

        while not self._evento_detener.is_set():
            inicio = time.time()
            try:
                # 1. Verificar puerto y enviar comando
                ser = None
                with self._lock_serial:
                    if self._serial and self._serial.is_open:
                        self._serial.write(comando)
                        self.estadisticas.incrementar_enviados()
                        ser = self._serial

                if ser is None:
                    time.sleep(0.01)
                    continue

                # 2. Leer header
                header = ser.read(3)

                if len(header) < 3:
                    logger.warning(
                        f"Timeout leyendo header: recibidos {len(header)}/3 bytes"
                    )
                    with self._lock_serial:
                        if self._serial and self._serial.is_open:
                            self._serial.reset_input_buffer()
                    continue

                # 3. Validar header
                header_valido, length = self._protocolo.validar_header_respuesta(
                    header
                )
                if not header_valido:
                    logger.warning(
                        f"Header inválido: {header.hex(' ').upper()}, intentando resync..."
                    )
                    if header[0] != 0x00:
                        with self._lock_serial:
                            if self._serial and self._serial.is_open:
                                self._serial.reset_input_buffer()
                        time.sleep(0.05)
                    continue

                # 4. Calcular bytes restantes
                bytes_needed = (
                    self._protocolo.calcular_tamano_respuesta_esperada(length) - 3
                )
                resto = ser.read(bytes_needed)

                if len(resto) < bytes_needed:
                    logger.warning(
                        f"Timeout leyendo payload: recibidos {len(resto)}/{bytes_needed} bytes"
                    )
                    with self._lock_serial:
                        if self._serial and self._serial.is_open:
                            self._serial.reset_input_buffer()
                    continue

                # 5. Combinar y parsear
                mensaje_completo = header + resto
                valido, payload = self._protocolo.parsear_respuesta(mensaje_completo)

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

            except Exception as e:
                if self._evento_detener.is_set():
                    break
                logger.error(f"Error en comunicación: {e}")
                self.estadisticas.incrementar_errores_timeout()
                time.sleep(0.1)

            # 6. Dormir el tiempo restante del intervalo
            transcurrido = time.time() - inicio
            tiempo_espera = max(0, self._intervalo - transcurrido)
            self._evento_detener.wait(tiempo_espera)

    def _procesar_buffer(self, buffer: bytearray) -> bytearray:
        """
        Procesa el buffer RX buscando mensajes completos de la ECU.
        """
        while len(buffer) >= self._protocolo.TAMANO_HEADER_RX:
            header_valido, length = self._protocolo.validar_header_respuesta(
                bytes(buffer[:3])
            )

            if not header_valido:
                buffer = buffer[1:]
                continue

            tamano_total = self._protocolo.calcular_tamano_respuesta_esperada(length)

            if len(buffer) < tamano_total:
                break

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

            buffer = buffer[tamano_total:]

        return buffer

    def _worker_simulador(self) -> None:
        """
        Worker del thread del simulador.
        """
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

                datos = ShockDynoData(
                    timestamp=dt.now(),
                    fuerza_n=round(fuerza_actual, 2),
                    recorrido_mm=round(recorrido_actual, 2),
                    temp_amortiguador_c=round(temp_amo_actual, 1),
                    temp_reservorio_c=round(temp_res_actual, 1),
                    velocidad_rpm=int(vel_actual),
                    valido=True,
                )

                if self._callback_datos:
                    try:
                        self._callback_datos(datos)
                    except Exception as e:
                        logger.error(f"Error en callback del simulador: {e}")

            except Exception as e:
                logger.error(f"Error en worker simulador: {e}")

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
        """
        variacion = random.uniform(-paso, paso)
        nuevo_valor = valor_actual + variacion
        return max(minimo, min(maximo, nuevo_valor))

    def desconectar(self) -> None:
        """
        Detiene los threads y cierra la conexión serial.
        """
        if not self._conectado:
            return

        logger.info(f"Desconectando de {self._puerto_actual}...")

        self._evento_detener.set()

        for hilo in [self._hilo_comunicacion, self._hilo_simulador]:
            if hilo and hilo.is_alive():
                hilo.join(timeout=2.0)

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
        self._hilo_comunicacion = None
        self._hilo_simulador = None

        logger.info("Desconectado correctamente.")

    def actualizar_calibracion(self, nueva_config: dict) -> None:
        """
        Actualiza la configuración de calibración del parser en tiempo real.
        """
        self._config = nueva_config
        self._parser.actualizar_config(nueva_config)
        logger.info("Calibración del SerialManager actualizada.")

    @property
    def esta_conectado(self) -> bool:
        """Indica si hay una conexión activa."""
        return self._conectado

    @property
    def es_simulador(self) -> bool:
        """Indica si la conexión activa es el modo simulador."""
        return self._modo_simulador

    @property
    def puerto(self) -> str:
        """Retorna el nombre del puerto actualmente conectado."""
        return self._puerto_actual
