"""
Módulo: serial_manager.py
Descripción: Gestión de la conexión serial con la ECU Speeduino.

Implementa un único hilo de comunicación síncrono (Master-Slave):
  - _hilo_comunicacion: Realiza el ciclo completo enviar → leer → procesar
    cada 50ms (20Hz). Elimina la competencia por locks entre hilos TX y RX.

Secuencia de conexión:
  1. Abrir puerto serial.
  2. Esperar delay de inicialización.
  3. Realizar handshake: enviar 'Q' → verificar firma "speeduino", enviar 'F'.
  4. Iniciar hilo de comunicación.

También incluye un modo SIMULADOR que genera datos aleatorios realistas
sin necesidad de hardware real, útil para desarrollo y testing.

Threading:
  - El hilo de comunicación es el único que accede al puerto serial durante
    el polling, eliminando la necesidad de un Lock para ese propósito.
  - Se mantiene threading.Lock solo para proteger el cierre del puerto desde
    el hilo principal (desconectar).
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

    Usa un único hilo de comunicación síncrono (Master-Slave) que envía el
    comando Read Page ('p' / 0x70) y lee la respuesta en el mismo ciclo
    mediante lecturas bloqueantes (sin in_waiting).
    Esto elimina la competencia por locks entre hilos independientes.

    Realiza handshake automático ('Q' → firma, 'F' → versión) antes de
    iniciar el polling de datos. Soporta modo SIMULADOR para testing sin
    hardware.

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
                write_timeout=0.1,  # Reducido para evitar bloqueos largos y liberar el lock más rápido
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

        Este método corre en su propio thread para no bloquear la UI durante
        el delay obligatorio después de conectar a la ECU. Tras el delay,
        envía los comandos de handshake 'Q' y 'F' para confirmar que la ECU
        está operativa antes de iniciar el polling de datos.

        Args:
            delay_segundos: Segundos a esperar antes de iniciar comunicación.
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

        Returns:
            True si el handshake fue exitoso, False en caso contrario.
        """
        try:
            timeout_handshake = self._cfg_conexion.get("timeout_handshake", 2.0)

            with self._lock_serial:
                if not (self._serial and self._serial.is_open):
                    logger.error("Puerto serial no disponible para handshake.")
                    return False

                # Limpiar buffer antes del handshake
                self._serial.reset_input_buffer()

                # Paso 1: Enviar 'Q' y verificar firma
                logger.debug("Handshake: enviando 'Q'...")
                self._serial.write(self._protocolo.construir_comando_handshake_q())

            # Esperar ~10% del timeout antes de leer para dar tiempo a la ECU
            time.sleep(timeout_handshake * 0.1)
            with self._lock_serial:
                if not (self._serial and self._serial.is_open):
                    return False
                respuesta_q = self._serial.read(32)

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

            time.sleep(0.1)
            with self._lock_serial:
                if not (self._serial and self._serial.is_open):
                    return False
                respuesta_f = self._serial.read(4)

            logger.info(
                f"Versión de protocolo: {respuesta_f.decode('ascii', errors='replace').strip()!r}"
            )
            return True

        except Exception as e:
            logger.error(f"Error durante handshake: {e}")
            return False

    def _arrancar_hilo_comunicacion(self) -> None:
        """
        Arranca el hilo único de comunicación síncrona (Master-Slave).

        El hilo realiza el ciclo completo: enviar comando Read Page,
        leer respuesta y procesar datos, cada 50ms (20Hz).
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
        Worker del hilo de comunicación síncrona (Master-Slave).

        Realiza el ciclo completo en cada iteración usando lecturas bloqueantes:
          1. Verificar puerto y enviar comando (bajo lock, brevemente).
          2. ser.read(3) bloqueante para obtener el header.
          3. Si el header es inválido o incompleto, limpiar buffer y reintentar.
          4. Calcular bytes restantes y hacer ser.read(bytes_needed) bloqueante.
          5. Combinar y parsear la respuesta completa.
          6. Dormir el tiempo restante para mantener 20Hz.

        Las lecturas bloqueantes se realizan fuera del lock para no impedir
        que desconectar() pueda actuar. El lock solo se toma brevemente para
        el envío del comando y para detectar si el puerto sigue abierto.
        """
        comando = self._protocolo.construir_comando_read_page()
        logger.debug(f"Comando listo: {comando.hex(' ').upper()}")

        while not self._evento_detener.is_set():
            inicio = time.time()
            try:
                # 1. Verificar puerto y enviar comando (lock breve)
                puerto_disponible = False
                with self._lock_serial:
                    if self._serial and self._serial.is_open:
                        self._serial.write(comando)
                        self.estadisticas.incrementar_enviados()
                        puerto_disponible = True

                if not puerto_disponible:
                    # Puerto cerrado: esperar fuera del lock
                    time.sleep(0.01)
                    continue

                # 2. Leer header (3 bytes) con lectura bloqueante (sin lock)
                header = self._serial.read(3)

                if len(header) < 3:
                    # Timeout leyendo header: limpiar buffer y reintentar
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
                        f"Header inválido: {header.hex(' ').upper()}, limpiando buffer..."
                    )
                    with self._lock_serial:
                        if self._serial and self._serial.is_open:
                            self._serial.reset_input_buffer()
                    continue

                # 4. Calcular bytes restantes (payload + CRC) y leer bloqueante
                bytes_needed = (
                    self._protocolo.calcular_tamano_respuesta_esperada(length) - 3
                )
                resto = self._serial.read(bytes_needed)

                if len(resto) < bytes_needed:
                    logger.warning(
                        f"Timeout leyendo payload: recibidos {len(resto)}/{bytes_needed} bytes"
                    )
                    with self._lock_serial:
                        if self._serial and self._serial.is_open:
                            self._serial.reset_input_buffer()
                    continue

                # 5. Combinar y parsear la respuesta completa
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

            # 6. Dormir el tiempo restante del intervalo para mantener 20Hz
            transcurrido = time.time() - inicio
            tiempo_espera = max(0, self._intervalo - transcurrido)
            self._evento_detener.wait(tiempo_espera)

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
        for hilo in [self._hilo_comunicacion, self._hilo_simulador]:
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
        self._hilo_comunicacion = None
        self._hilo_simulador = None

        logger.info("Desconectado correctamente.")

    def actualizar_calibracion(self, nueva_config: dict) -> None:
        """
        Actualiza la configuración de calibración del parser en tiempo real.

        Permite cambiar escalas y offsets de los sensores sin desconectar
        ni reiniciar la comunicación. Los cambios se aplican a partir del
        próximo dato recibido.

        Args:
            nueva_config: Diccionario con la nueva configuración completa.
                          Se usa la clave ``"sensores"`` para los parámetros
                          de calibración.

        Ejemplo::

            manager.actualizar_calibracion({
                "sensores": {
                    "fuerza": {"escala": 0.5, "offset_valor": -150.0},
                    "recorrido": {"escala": 0.45, "offset_valor": -5.0},
                }
            })
        """
        self._config = nueva_config
        self._parser.actualizar_config(nueva_config)
        logger.info("Calibración del SerialManager actualizada.")

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
