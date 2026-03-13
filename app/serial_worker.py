import serial
import serial.tools.list_ports
from PyQt5.QtCore import QThread, pyqtSignal


class SerialWorker(QThread):
    """QThread that reads CSV lines from an Arduino and emits a signal per line.

    Expected Arduino format (one line per measurement):
        Fuerza_N,Recorrido_mm,Temp_Amo_C,Temp_Res_C,RPM
    """

    # fuerza_n, recorrido_mm, temp_amo, temp_res, rpm
    data_received = pyqtSignal(float, float, float, float, int)
    error_occurred = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int = 115200, parent=None):
        super().__init__(parent)
        self._port = port
        self._baudrate = baudrate
        self._running = False

    def run(self):
        self._running = True
        try:
            with serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=1,
            ) as ser:
                # Wait for Arduino auto-reset (2 s), checking stop flag every 100 ms
                for _ in range(20):
                    if not self._running:
                        return
                    QThread.msleep(100)
                ser.reset_input_buffer()

                while self._running:
                    try:
                        raw = ser.readline()
                        if not raw:
                            continue
                        line = raw.decode("ascii", errors="ignore").strip()
                        if not line:
                            continue
                        parts = line.split(",")
                        if len(parts) != 5:
                            continue
                        fuerza = float(parts[0])
                        recorrido = float(parts[1])
                        temp_amo = float(parts[2])
                        temp_res = float(parts[3])
                        rpm = int(float(parts[4]))
                        self.data_received.emit(fuerza, recorrido, temp_amo, temp_res, rpm)
                    except ValueError:
                        # Malformed line – skip silently
                        pass
        except serial.SerialException as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self._running = False

    def stop(self):
        """Request the worker to stop and wait for the thread to finish."""
        self._running = False
        self.wait(3000)
