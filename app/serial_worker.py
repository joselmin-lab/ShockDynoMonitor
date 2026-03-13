import serial
import serial.tools.list_ports
import threading
from PyQt5.QtCore import QThread, pyqtSignal

from app.calibration import load_calibration


class SerialWorker(QThread):
    """QThread that reads CSV lines from an Arduino and emits a signal per line.

    Expected Arduino format (one line per measurement):
        Fuerza_N,Recorrido_raw,Temp_Amo_C,Temp_Res_C,RPM

    The distance field is the RAW analog integer (0-1023) from the potentiometer.
    Calibration uses PMI/PMS (Bottom/Top Dead Center) raw values and the physical
    stroke length to convert to mm:
        mm = (raw - raw_pmi) * (stroke_length_mm / (raw_pms - raw_pmi))

    Temperature calibration offsets are applied before the signal is emitted:
        calibrated_temp = raw_temp + offset
    """

    # fuerza_n, recorrido_mm, temp_amo, temp_res, rpm
    data_received = pyqtSignal(float, float, float, float, int)
    error_occurred = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int = 115200, calibration: dict | None = None, parent=None):
        super().__init__(parent)
        self._port = port
        self._baudrate = baudrate
        self._cal = calibration if calibration is not None else load_calibration()
        self._cal_lock = threading.Lock()
        self._running = False
        self._last_raw_distance: int | None = None
        self._raw_lock = threading.Lock()

    @property
    def last_raw_distance(self) -> int | None:
        """Return the most recently received raw distance value (thread-safe)."""
        with self._raw_lock:
            return self._last_raw_distance

    def set_calibration(self, calibration: dict) -> None:
        """Update calibration values while the worker is running (thread-safe)."""
        with self._cal_lock:
            self._cal = dict(calibration)

    def _raw_to_mm(self, raw: int, cal: dict) -> float:
        """Convert raw potentiometer value (0-1023) to mm using PMI/PMS calibration."""
        raw_pmi = cal.get("raw_pmi", 0.0)
        raw_pms = cal.get("raw_pms", 1023.0)
        stroke = cal.get("stroke_length_mm", 150.0)
        span = raw_pms - raw_pmi
        if span == 0:
            return 0.0
        return (raw - raw_pmi) * (stroke / span)

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
                        raw_dist = int(float(parts[1]))
                        temp_amo = float(parts[2])
                        temp_res = float(parts[3])
                        rpm = int(float(parts[4]))

                        # Store latest raw distance for calibration capture
                        with self._raw_lock:
                            self._last_raw_distance = raw_dist

                        # Apply calibration (take a snapshot to minimise lock hold time)
                        with self._cal_lock:
                            cal = dict(self._cal)
                        temp_amo = temp_amo + cal.get("temp_amo_offset", 0.0)
                        temp_res = temp_res + cal.get("temp_res_offset", 0.0)
                        recorrido = self._raw_to_mm(raw_dist, cal)

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
