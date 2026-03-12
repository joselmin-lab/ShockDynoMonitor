"""
Protocolo de comunicación Speeduino.

Este módulo implementa el protocolo binario de Speeduino con:
- Construcción de comandos con CRC32
- Validación de respuestas
- Parsing de headers y payloads
"""

import struct
import binascii
from typing import Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# ========== DATACLASS DE RESPUESTA ==========

@dataclass
class SpeeduinoResponse:
    """
    Estructura de una respuesta Speeduino validada.
    
    Attributes:
        header: Tupla de 3 bytes (0x00, length, 0x00)
        payload: Bytes de datos (128 bytes para real-time)
        crc: CRC32 recibido
        is_valid: Si el CRC es válido
    """
    header: tuple
    payload: bytes
    crc: int
    is_valid: bool


# ========== CONSTANTES DEL PROTOCOLO ==========

HEADER_BYTE_0 = 0x00
HEADER_BYTE_2 = 0x00
CMD_REALTIME_DATA = 0x41
RESPONSE_HEADER_SIZE = 3
CRC_SIZE = 4
REALTIME_PAYLOAD_SIZE = 128


# ========== CLASE PRINCIPAL ==========

class SpeeduinoProtocol:
    """
    Implementación del protocolo Speeduino.
    
    Maneja la construcción de comandos y validación de respuestas
    según el protocolo binario de Speeduino con CRC32.
    """
    
    def __init__(self):
        """Inicializar protocolo Speeduino."""
        logger.debug("SpeeduinoProtocol inicializado.")
    
    @staticmethod
    def calculate_crc32(data: bytes) -> int:
        """
        Calcular CRC32 compatible con Speeduino.
        
        Args:
            data: Bytes sobre los que calcular CRC
            
        Returns:
            CRC32 como entero sin signo de 32 bits
        """
        return binascii.crc32(data) & 0xFFFFFFFF
    
    @staticmethod
    def build_command(command_byte: int, payload: bytes = b'') -> bytes:
        """
        Construir comando Speeduino completo con CRC32.
        
        Estructura: [Header(1)] [Length(1)] [Command(1)] [Payload(N)] [CRC32(4)]
        
        Args:
            command_byte: Byte de comando (ej: 0x41 para real-time)
            payload: Bytes de payload opcionales
            
        Returns:
            Comando completo listo para enviar por serial
        """
        length = len(payload) + 1
        command = bytearray([HEADER_BYTE_0, length, command_byte])
        
        if payload:
            command.extend(payload)
        
        crc = SpeeduinoProtocol.calculate_crc32(bytes(command))
        command.extend(struct.pack('<I', crc))
        
        return bytes(command)
    
    @staticmethod
    def build_realtime_data_command() -> bytes:
        """
        Construir comando de solicitud de datos en tiempo real (0x41).
        
        Returns:
            Comando completo: 00 01 41 [CRC32]
        """
        return SpeeduinoProtocol.build_command(CMD_REALTIME_DATA)
    
    @staticmethod
    def validate_response_header(data: bytes) -> bool:
        """
        Validar que los primeros 3 bytes sean un header válido: 00 XX 00
        
        Args:
            data: Buffer de datos recibidos
            
        Returns:
            True si el header es válido
        """
        if len(data) < 3:
            return False
        
        return data[0] == HEADER_BYTE_0 and data[2] == HEADER_BYTE_2
    
    @staticmethod
    def parse_response(data: bytes) -> Optional[SpeeduinoResponse]:
        """
        Parsear respuesta completa de Speeduino.
        
        Valida header, extrae payload y verifica CRC32.
        
        Args:
            data: Buffer completo de respuesta
            
        Returns:
            SpeeduinoResponse si válido, None si error
        """
        if len(data) < RESPONSE_HEADER_SIZE + CRC_SIZE:
            logger.warning(f"Respuesta muy corta: {len(data)} bytes")
            return None
        
        if not SpeeduinoProtocol.validate_response_header(data):
            logger.warning("Header inválido")
            return None
        
        header = (data[0], data[1], data[2])
        payload_length = data[1]
        
        total_expected = RESPONSE_HEADER_SIZE + payload_length + CRC_SIZE
        if len(data) < total_expected:
            logger.warning(f"Respuesta incompleta: {len(data)} < {total_expected}")
            return None
        
        payload_start = RESPONSE_HEADER_SIZE
        payload_end = payload_start + payload_length
        payload = data[payload_start:payload_end]
        
        crc_bytes = data[payload_end:payload_end + CRC_SIZE]
        if len(crc_bytes) < CRC_SIZE:
            logger.warning("CRC incompleto")
            return None
        
        crc_received = struct.unpack('<I', crc_bytes)[0]
        
        crc_data = data[:payload_end]
        crc_calculated = SpeeduinoProtocol.calculate_crc32(crc_data)
        
        is_valid = (crc_received == crc_calculated)
        
        if not is_valid:
            logger.warning(f"CRC inválido: recibido={hex(crc_received)}, calculado={hex(crc_calculated)}")
        
        return SpeeduinoResponse(
            header=header,
            payload=payload,
            crc=crc_received,
            is_valid=is_valid
        )
    
    # ✅ MÉTODO AGREGADO: Alias por compatibilidad
    def construir_comando_realtime(self) -> bytes:
        """
        Construir comando de solicitud de datos en tiempo real (0x41).
        
        Alias para build_realtime_data_command() por compatibilidad con serial_manager.
        
        Returns:
            Comando completo: 00 01 41 [CRC32]
        """
        return self.build_realtime_data_command()