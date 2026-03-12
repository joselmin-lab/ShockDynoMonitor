"""
Módulo: speeduino_protocol.py
Descripción: Implementación del protocolo de comunicación binario con CRC32
             para la ECU Speeduino 2025.01.4.

Protocolo validado mediante captura real el 2026-03-12.
Baudrate: 115200, 8N1, polling a 50ms (20Hz).

Secuencia de handshake:
    1. Enviar 'Q' (0x51) → Respuesta con firma "speeduino ...".
    2. Enviar 'F' (0x46) → Respuesta con versión del protocolo.

Estructura del comando TX Read Page ('p' / 0x70):
    Byte 0:    0x00       → Header
    Byte 1:    0x07       → Length (7 bytes de payload)
    Byte 2:    0x70       → Comando 'p' (Read Page)
    Byte 3:    0x00       → CanID
    Byte 4:    0x01       → Page (página 1 = datos en tiempo real)
    Bytes 5-6: 0x00 0x00  → Offset (16-bit little-endian)
    Bytes 7-8: 0x79 0x00  → Size (16-bit little-endian, 121 bytes)
    Bytes 9-12: CRC32 little-endian de los bytes 0-8

Estructura de la respuesta RX:
    Bytes 0-2: Header (00 XX 00, donde XX es el length)
    Bytes 3-N: Payload (121/122 bytes de datos de sensores)
    Bytes N+1-N+4: CRC32 little-endian
"""

import binascii
import struct
import logging
from typing import Optional, Tuple

# Logger del módulo
logger = logging.getLogger(__name__)


class SpeeduinoProtocol:
    """
    Clase que encapsula el protocolo de comunicación con la ECU Speeduino.

    Provee métodos para construir comandos de handshake, solicitar páginas
    de datos y validar respuestas con CRC32.

    Ejemplo de uso::

        protocolo = SpeeduinoProtocol()
        # Handshake
        ser.write(protocolo.construir_comando_handshake_q())
        # Leer página de datos en tiempo real
        comando = protocolo.construir_comando_read_page()
        # Enviar 'comando' por el puerto serial
        # Recibir 'respuesta' del puerto serial
        valido, payload = protocolo.parsear_respuesta(respuesta)
    """

    # Constantes del protocolo
    COMANDO_REALTIME = 0x41          # Comando legacy 'A' para datos en tiempo real
    COMANDO_READ_PAGE = 0x70         # Comando 'p' para leer una página de la ECU
    COMANDO_HANDSHAKE_Q = 0x51      # Comando 'Q' de handshake (consulta de firma)
    COMANDO_HANDSHAKE_F = 0x46      # Comando 'F' de handshake (consulta de versión)
    HEADER_BYTE_0 = 0x00             # Primer byte del header TX/RX
    HEADER_TX_LENGTH = 0x01          # Length del payload TX legacy (1 byte)
    LONGITUD_PAYLOAD_ESPERADA = 121  # Bytes de payload solicitados en read_page

    # Parámetros por defecto del comando Read Page (validados en captura 2026-03-12)
    READ_PAGE_CAN_ID = 0x00   # CanID (0 = local)
    READ_PAGE_PAGE = 0x01     # Página de datos en tiempo real (página 1)
    READ_PAGE_OFFSET = 0      # Offset dentro de la página
    READ_PAGE_SIZE = 121      # Cantidad de bytes a leer (0x79)

    # Tamaño del header de respuesta: 3 bytes (00 XX 00)
    TAMANO_HEADER_RX = 3
    # Tamaño del CRC32 en bytes
    TAMANO_CRC = 4

    def __init__(self) -> None:
        """Inicializa el protocolo Speeduino."""
        logger.debug("SpeeduinoProtocol inicializado.")

    def calcular_crc32(self, datos: bytes) -> int:
        """
        Calcula el CRC32 usando el mismo algoritmo que la ECU Speeduino.

        Utiliza binascii.crc32 con resultado enmascarado a 32 bits sin signo,
        que es lo que espera la ECU Speeduino.

        Args:
            datos: Bytes sobre los cuales calcular el CRC32.

        Returns:
            Entero de 32 bits sin signo con el CRC32 calculado.

        Ejemplo::

            protocolo = SpeeduinoProtocol()
            datos = bytes([0x00, 0x01, 0x41])
            crc = protocolo.calcular_crc32(datos)
            # crc == 0xEF8E6ECE (little-endian: CE 6E 8E EF)
        """
        return binascii.crc32(datos) & 0xFFFFFFFF

    def construir_comando_realtime(self) -> bytes:
        """
        Construye el comando de solicitud de datos en tiempo real (0x41).

        El comando tiene la estructura:
            [0x00, 0x01, 0x41, CRC32_byte0, CRC32_byte1, CRC32_byte2, CRC32_byte3]

        El CRC32 se calcula sobre los primeros 3 bytes y se agrega en
        formato little-endian.

        Returns:
            Bytes del comando completo (7 bytes) listo para enviar por serial.

        Ejemplo::

            protocolo = SpeeduinoProtocol()
            cmd = protocolo.construir_comando_realtime()
            # cmd == bytes([0x00, 0x01, 0x41, 0xCE, 0x6E, 0x8E, 0xEF])
        """
        # Construir los 3 bytes base del comando
        cuerpo = bytearray([
            self.HEADER_BYTE_0,        # 0x00 - Header
            self.HEADER_TX_LENGTH,     # 0x01 - Length
            self.COMANDO_REALTIME,     # 0x41 - Comando 'A'
        ])

        # Calcular CRC32 sobre el cuerpo del comando
        crc = self.calcular_crc32(bytes(cuerpo))

        # Agregar CRC32 en formato little-endian (4 bytes)
        cuerpo.extend(struct.pack('<I', crc))

        logger.debug(f"Comando realtime construido: {cuerpo.hex(' ').upper()}")
        return bytes(cuerpo)

    def construir_comando_handshake_q(self) -> bytes:
        """
        Construye el comando de handshake 'Q' (consulta de firma de firmware).

        Envía el byte 'Q' (0x51) de forma raw (sin encapsular en el protocolo
        binario) para despertar la ECU y solicitar su firma de identificación.

        Returns:
            Bytes del comando (1 byte: ``b'Q'``).

        Ejemplo::

            protocolo = SpeeduinoProtocol()
            cmd = protocolo.construir_comando_handshake_q()
            # Esperado: b'Q'  →  La ECU responde con "speeduino XXXXXX"
        """
        logger.debug("Comando handshake Q construido.")
        return bytes([self.COMANDO_HANDSHAKE_Q])

    def construir_comando_handshake_f(self) -> bytes:
        """
        Construye el comando de handshake 'F' (consulta de versión de protocolo).

        Envía el byte 'F' (0x46) de forma raw para que la ECU devuelva
        la versión del protocolo serial que soporta.

        Returns:
            Bytes del comando (1 byte: ``b'F'``).

        Ejemplo::

            protocolo = SpeeduinoProtocol()
            cmd = protocolo.construir_comando_handshake_f()
            # Esperado: b'F'  →  La ECU responde con "002" (versión de protocolo)
        """
        logger.debug("Comando handshake F construido.")
        return bytes([self.COMANDO_HANDSHAKE_F])

    def construir_comando_read_page(
        self,
        can_id: int = READ_PAGE_CAN_ID,
        page: int = READ_PAGE_PAGE,
        offset: int = READ_PAGE_OFFSET,
        size: int = READ_PAGE_SIZE,
    ) -> bytes:
        """
        Construye el comando 'p' (Read Page) con el nuevo protocolo serial.

        La estructura del comando es:
            [0x00, 0x07, 0x70, can_id, page, offset_lo, offset_hi,
             size_lo, size_hi, CRC32_b0, CRC32_b1, CRC32_b2, CRC32_b3]

        Offset y size se codifican en 16 bits little-endian.
        El CRC32 se calcula sobre los 9 bytes del comando (header + payload).

        Args:
            can_id: Identificador de CAN bus (por defecto 0x00 = local).
            page:   Número de página a leer (por defecto 0x01 = realtime data).
            offset: Offset dentro de la página en bytes (por defecto 0).
            size:   Cantidad de bytes a leer (por defecto 121).

        Returns:
            Bytes del comando completo (13 bytes) listo para enviar por serial.

        Ejemplo::

            protocolo = SpeeduinoProtocol()
            cmd = protocolo.construir_comando_read_page()
            # cmd == bytes([0x00, 0x07, 0x70, 0x00, 0x01,
            #               0x00, 0x00, 0x79, 0x00, ...CRC...])
        """
        # Payload: cmd 'p' (B) + canid (B) + page (B) + offset 16-bit LE (H) + size 16-bit LE (H)
        payload = struct.pack(
            '<BBBHH',
            self.COMANDO_READ_PAGE,  # 0x70 'p'
            can_id,                  # CanID
            page,                    # Page
            offset,                  # Offset (16-bit LE)
            size,                    # Size  (16-bit LE)
        )

        # Construir cabecera + payload (sin CRC)
        cuerpo = bytearray([self.HEADER_BYTE_0, len(payload)]) + bytearray(payload)

        # Calcular CRC32 sobre el cuerpo completo y agregar en little-endian
        crc = self.calcular_crc32(bytes(cuerpo))
        cuerpo.extend(struct.pack('<I', crc))

        logger.debug(f"Comando read_page construido: {cuerpo.hex(' ').upper()}")
        return bytes(cuerpo)

    def validar_header_respuesta(self, datos: bytes) -> Tuple[bool, int]:
        """
        Valida el header de la respuesta de la ECU Speeduino.

        El header esperado tiene el formato: 00 XX 00
        Donde XX es el length del payload en bytes.

        Nota: La ECU reporta 122 bytes (0x7A) en el header, pero el frame
        total es de 128 bytes (3 header + 121 payload + 4 CRC). El byte
        extra nunca llega, por lo que se corrige el length a 121 cuando
        el header indica 122.

        Args:
            datos: Bytes recibidos (mínimo 3 bytes de header).

        Returns:
            Tupla (valido: bool, length: int) donde:
            - valido: True si el header tiene el formato correcto
            - length: Cantidad de bytes del payload (0 si header inválido)

        Ejemplo::

            protocolo = SpeeduinoProtocol()
            # Respuesta real: 00 7A 00 ...
            valido, length = protocolo.validar_header_respuesta(bytes([0x00, 0x7A, 0x00]))
            # valido == True, length == 121  (corregido de 122)
        """
        if len(datos) < self.TAMANO_HEADER_RX:
            logger.warning(
                f"Header demasiado corto: {len(datos)} bytes "
                f"(esperado >= {self.TAMANO_HEADER_RX})"
            )
            return False, 0

        # Verificar patrón 00 XX 00
        byte_0 = datos[0]
        length = datos[1]
        byte_2 = datos[2]

        if byte_0 != 0x00 or byte_2 != 0x00:
            logger.warning(
                f"Header inválido: {datos[:3].hex(' ').upper()} "
                f"(esperado: 00 XX 00)"
            )
            return False, 0

        # La ECU reporta 122 bytes (0x7A) pero el frame real contiene solo
        # 121 bytes de payload. Corregir para evitar esperar un byte que
        # nunca llega y que cause un timeout indefinido.
        if length == 0x7A:
            length = 121

        logger.debug(f"Header válido: length={length} bytes")
        return True, length

    def parsear_respuesta(self, datos: bytes) -> Tuple[bool, Optional[bytes]]:
        """
        Parsea la respuesta completa de la ECU Speeduino.

        Valida el header, extrae el payload y verifica el CRC32 al final.

        Args:
            datos: Bytes completos de la respuesta recibida del serial.

        Returns:
            Tupla (valido: bool, payload: Optional[bytes]) donde:
            - valido: True si la respuesta es válida (header + CRC correctos)
            - payload: Bytes del payload (128 bytes) si válido, None si inválido

        Ejemplo::

            protocolo = SpeeduinoProtocol()
            # datos = bytes recibidos por serial (header + payload + CRC)
            valido, payload = protocolo.parsear_respuesta(datos)
            if valido and payload:
                # Procesar payload de 128 bytes
                fuerza_raw = payload[1]
        """
        # Validar header
        header_valido, length = self.validar_header_respuesta(datos)
        if not header_valido:
            return False, None

        # Calcular tamaño total esperado de la respuesta
        tamano_esperado = self.TAMANO_HEADER_RX + length + self.TAMANO_CRC

        if len(datos) < tamano_esperado:
            logger.warning(
                f"Respuesta incompleta: {len(datos)} bytes "
                f"(esperado {tamano_esperado})"
            )
            return False, None

        # Extraer payload (bytes después del header, antes del CRC)
        payload = datos[self.TAMANO_HEADER_RX: self.TAMANO_HEADER_RX + length]

        # Extraer CRC32 recibido (últimos 4 bytes, little-endian)
        crc_recibido_bytes = datos[
            self.TAMANO_HEADER_RX + length:
            self.TAMANO_HEADER_RX + length + self.TAMANO_CRC
        ]
        crc_recibido = struct.unpack('<I', crc_recibido_bytes)[0]

        # Calcular CRC32 esperado sobre header + payload
        datos_para_crc = datos[:self.TAMANO_HEADER_RX + length]
        crc_calculado = self.calcular_crc32(datos_para_crc)

        # Verificar CRC32
        if crc_recibido != crc_calculado:
            logger.warning(
                f"CRC32 inválido: recibido=0x{crc_recibido:08X}, "
                f"calculado=0x{crc_calculado:08X}"
            )
            return False, None

        logger.debug(f"Respuesta válida: {length} bytes de payload, CRC OK")
        return True, bytes(payload)

    def calcular_tamano_respuesta_esperada(self, length_payload: int) -> int:
        """
        Calcula el tamaño total de la respuesta esperada dado un length de payload.

        Args:
            length_payload: Cantidad de bytes del payload indicada en el header.

        Returns:
            Tamaño total en bytes (header + payload + CRC32).
        """
        return self.TAMANO_HEADER_RX + length_payload + self.TAMANO_CRC
