    # Existing code
    self._protocolo.enviar_comando('F')
    # New logic added after sending 'F'
    self._protocolo.enviar_comando(self._protocolo.construir_comando_handshake_s())
    self._puerto_serial.write(self._protocolo.construir_comando_handshake_s().encode())
    self._puerto_serial.flush()
    time.sleep(0.1)
    respuesta = self._puerto_serial.read(self._puerto_serial.inWaiting())
    self.extended_signature = respuesta
    # Remaining code