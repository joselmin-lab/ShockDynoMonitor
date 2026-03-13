"""
Módulo: speeduino_protocol.py
Descripción: Implementación del protocolo de comunicación binario con CRC32
             para la ECU Speeduino 2025.01.4.

Protocolo validado mediante captura real el 2026-03-12.
Baudrate: 115200, 8N1, polling a 50ms (20Hz).

Secuencia de handshake:
    1. Enviar 'Q' (0x51) → Respuesta con firma "speeduino ...".
    2. Enviar 'F' (0x46) → Respuesta con versión del protocolo.
    3. Enviar 'S' encapsulado (0x53) → Respuesta con firma extendida.

Estructura del comando TX Read Realtime ('p' / 0x70), replicando exactamente
lo que hace TunerStudio en la captura del 2026-03-12:
    Byte 0:    0x00       → Header
    Byte 1:    0x07       → Length (7 bytes de payload)
    Byte 2:    0x70       → Comando 'p' (Read Page)
    Byte 3:    0x00       → CanID
    Byte 4:    0x01       → Page 1 (telemetría realtime)
    Bytes 5-6: 0x00 0x00  → Offset (16-bit little-endian)
    Bytes 7-8: 0x79 0x00  → Size (16-bit little-endian, 121 bytes solicitados)
    Bytes 9-12: CRC32 big-endian (MSB primero) calculado sobre los bytes 2-8 (payload)
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
    """

    # Constantes del protocolo
    COMANDO_REALTIME = 0x41          # Comando legacy 'A' para datos en tiempo real
    COMANDO_READ_PAGE = 0x70         # Comando 'p' para leer una página de la ECU
    COMANDO_READ_REALTIME = 0x72     # Comando 'r' para datos en tiempo real (CRC protocol)
    COMANDO_HANDSHAKE_Q = 0x51       # Comando 'Q' de handshake (consulta de firma)
    COMANDO_HANDSHAKE_F = 0x46       # Comando 'F' de handshake (consulta de versión)
    COMANDO_HANDSHAKE_S = 0x53       # Comando 'S' encapsulado de firma extendida
    HEADER_BYTE_0 = 0x00             # Primer byte del header TX/RX
    HEADER_TX_LENGTH = 0x01          # Length del payload TX legacy (1 byte)

    # Parámetros por defecto del comando Read Page / Read Realtime
    READ_PAGE_CAN_ID = 0x00       # CanID (0 = local)
    READ_PAGE_PAGE = 0x01         # Página por defecto
    READ_REALTIME_PAGE = 0x30     # Página 48 (legacy, no usada por TunerStudio)
    READ_REALTIME_PAGE_TS = 0x01  # Página 1 usada por TunerStudio para telemetría
    READ_PAGE_OFFSET = 0          # Offset dentro de la página
    READ_PAGE_SIZE = 121          # Cantidad de bytes a leer (0x79)

    # Tamaño del header de respuesta: 3 bytes (00 XX 00)
    TAMANO_HEADER_RX = 3
    # Tamaño del CRC32 en bytes
    TAMANO_CRC = 4

    def __init__(self) -> None:
        """Inicializa el protocolo Speeduino."""
        logger.debug("SpeeduinoProtocol inicializado.")

    def calcular_crc32(self, datos: bytes) -> int:
        return binascii.crc32(datos) & 0xFFFFFFFF

    def construir_comando_realtime(self) -> bytes:
        payload = bytearray([self.COMANDO_REALTIME])
        crc = self.calcular_crc32(bytes(payload))
        cuerpo = bytearray([self.HEADER_BYTE_0, self.HEADER_TX_LENGTH])
        cuerpo += payload
        cuerpo.extend(struct.pack('>I', crc))
        logger.debug(f"Comando realtime construido: {cuerpo.hex(' ').upper()}")
        return bytes(cuerpo)

    def construir_comando_handshake_q(self) -> bytes:
        logger.debug("Comando handshake Q construido.")
        return bytes([self.COMANDO_HANDSHAKE_Q])

    def construir_comando_handshake_q_encapsulado(self) -> bytes:
        """Construye el comando 'Q' encapsulado con CRC32 (firma extendida)."""
        payload = bytearray([self.COMANDO_HANDSHAKE_Q])
        crc = self.calcular_crc32(bytes(payload))
        cuerpo = bytearray([self.HEADER_BYTE_0, self.HEADER_TX_LENGTH])
        cuerpo += payload
        cuerpo.extend(struct.pack('>I', crc))
        logger.debug(f"Comando handshake Q encapsulado construido: {cuerpo.hex(' ').upper()}")
        return bytes(cuerpo)

    def construir_comando_handshake_f(self) -> bytes:
        logger.debug("Comando handshake F construido.")
        return bytes([self.COMANDO_HANDSHAKE_F])

    def construir_comando_handshake_s(self) -> bytes:
        """Construye el comando 'S' encapsulado (firma extendida del nuevo protocolo)."""
        payload = bytearray([self.COMANDO_HANDSHAKE_S])
        crc = self.calcular_crc32(bytes(payload))
        cuerpo = bytearray([self.HEADER_BYTE_0, self.HEADER_TX_LENGTH])
        cuerpo += payload
        cuerpo.extend(struct.pack('>I', crc))
        logger.debug(f"Comando handshake S construido: {cuerpo.hex(' ').upper()}")
        return bytes(cuerpo)

    def construir_comando_read_page(
        self,
        can_id: int = READ_PAGE_CAN_ID,
        page: int = READ_PAGE_PAGE,
        offset: int = READ_PAGE_OFFSET,
        size: int = READ_PAGE_SIZE,
    ) -> bytes:
        payload = struct.pack(
            '<BBBHH',
            self.COMANDO_READ_PAGE,  # 0x70 'p'
            can_id,                  # CanID
            page,                    # Page
            offset,                  # Offset (16-bit LE)
            size,                    # Size  (16-bit LE)
        )
        crc = self.calcular_crc32(bytes(payload))
        cuerpo = bytearray([self.HEADER_BYTE_0, len(payload)])
        cuerpo += bytearray(payload)
        cuerpo.extend(struct.pack('>I', crc))
        logger.debug(f"Comando read_page construido: {cuerpo.hex(' ').upper()}")
        return bytes(cuerpo)

    def construir_comando_read_realtime(
        self,
        can_id: int = READ_PAGE_CAN_ID,
        page: int = READ_REALTIME_PAGE_TS,  # page=0x01, igual que TunerStudio
        offset: int = READ_PAGE_OFFSET,
        size: int = READ_PAGE_SIZE,
    ) -> bytes:
        """
        Construye el comando 'p' (0x70) para solicitar telemetría en tiempo real.

        Replica exactamente el comando que usa TunerStudio según la captura
        del 2026-03-12: comando 0x70 (Read Page) con page=0x01, offset=0,
        size=121 bytes.

        TX resultante: 00 07 70 00 01 00 00 79 00 [CRC32 big-endian]
        """
        payload = struct.pack(
            '<BBBHH',
            self.COMANDO_READ_PAGE,  # 0x70 'p'
            can_id,                  # CanID
            page,                    # Page (0x01 por defecto, igual que TunerStudio)
            offset,                  # Offset (16-bit LE)
            size,                    # Size  (16-bit LE)
        )
        crc = self.calcular_crc32(bytes(payload))
        cuerpo = bytearray([self.HEADER_BYTE_0, len(payload)])
        cuerpo += bytearray(payload)
        cuerpo.extend(struct.pack('>I', crc))
        logger.debug(f"Comando read_realtime construido: {cuerpo.hex(' ').upper()}")
        return bytes(cuerpo)

    def validar_header_respuesta(self, datos: bytes) -> Tuple[bool, int]:
        if len(datos) < self.TAMANO_HEADER_RX:
            logger.warning(
                f"Header demasiado corto: {len(datos)} bytes "
                f"(esperado >= {self.TAMANO_HEADER_RX})"
            )
            return False, 0

        byte_0 = datos[0]
        length = datos[1]
        byte_2 = datos[2]

        if byte_0 != 0x00 or byte_2 != 0x00:
            logger.warning(
                f"Header inválido: {datos[:3].hex(' ').upper()} "
                f"(esperado: 00 XX 00)"
            )
            return False, 0

        if length == 0:
            logger.warning("Header inválido: length=0")
            return False, 0

        # Speeduino protocolo bug: reporta length = payload real + 1
        actual_length = length - 1

        logger.debug(f"Header válido: length indicado={length}, length real={actual_length} bytes")
        return True, actual_length

    def validar_crc_respuesta(self, frame: bytes) -> bool:
        """
        Valida el CRC32 de un frame de respuesta recibido.

        El CRC se calcula sobre los bytes desde el índice 2 hasta len-4
        (es decir, el payload del envelope incluyendo el byte de código de
        respuesta 0x00), y se compara con los 4 bytes finales del frame.

        Args:
            frame: Frame completo recibido (mínimo 7 bytes).

        Returns:
            True si el CRC es válido, False en caso contrario.
        """
        if len(frame) < 7:
            return False
        payload_for_crc = frame[2:-4]
        crc_recibido = int.from_bytes(frame[-4:], 'big')
        crc_calculado = self.calcular_crc32(payload_for_crc)
        return crc_recibido == crc_calculado

    def parsear_respuesta(self, datos: bytes) -> Tuple[bool, Optional[bytes]]:
        header_valido, actual_length = self.validar_header_respuesta(datos)
        if not header_valido:
            return False, None

        tamano_esperado = self.TAMANO_HEADER_RX + actual_length + self.TAMANO_CRC

        if len(datos) < tamano_esperado:
            logger.warning(
                f"Respuesta incompleta: {len(datos)} bytes "
                f"(esperado {tamano_esperado})"
            )
            return False, None

        # Los datos reales empiezan en el byte 3 (después del header 00 XX 00)
        payload = datos[self.TAMANO_HEADER_RX: self.TAMANO_HEADER_RX + actual_length]

        # El CRC se calcula sobre los bytes 2...(len-4) del frame, que incluye
        # el byte de código de respuesta (0x00 en posición 2) más los datos.
        # Esto corresponde a datos[2:2+length_raw] donde length_raw = actual_length + 1.
        if not self.validar_crc_respuesta(datos[:tamano_esperado]):
            length_raw = datos[1]
            crc_recibido_bytes = datos[tamano_esperado - self.TAMANO_CRC: tamano_esperado]
            crc_recibido = struct.unpack('>I', crc_recibido_bytes)[0]
            payload_for_crc = datos[2: 2 + length_raw]
            crc_calculado = self.calcular_crc32(payload_for_crc)
            logger.warning(
                f"CRC32 inválido: recibido=0x{crc_recibido:08X}, "
                f"calculado=0x{crc_calculado:08X}"
            )
            return False, None

        logger.debug(f"Respuesta válida: {actual_length} bytes de payload, CRC OK")
        return True, bytes(payload)

    def calcular_tamano_respuesta_esperada(self, length_payload_real: int) -> int:
        return self.TAMANO_HEADER_RX + length_payload_real + self.TAMANO_CRC