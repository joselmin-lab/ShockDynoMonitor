# Shock Dyno Monitor

A modern, real-time dashboard for monitoring shock-absorber dynamometer data sent by an Arduino over a serial (USB) connection.

## Features

- **Real-time LCD-style readouts** for all 5 sensor channels.
- **Live scrolling graphs** (Force, Distance, Temperatures) powered by pyqtgraph.
- **Dark theme** UI built with PyQt5.
- **Crash-free serial reading** using QThread – no stdlib `threading` module.

## Arduino Data Format

The Arduino must send one CSV line per measurement at any baud-rate (default 115 200):

```
Fuerza_N,Recorrido_mm,Temp_Amo_C,Temp_Res_C,RPM\r\n
```

Example:
```
12.50,45.30,28.4,26.1,120
```

## Project Structure

```
ShockDynoMonitor/
├── main.py               # Entry point
├── requirements.txt
├── README.md
└── app/
    ├── __init__.py
    ├── serial_worker.py  # QThread serial reader
    ├── dashboard.py      # LCD-style numeric readouts
    ├── graphs.py         # Real-time pyqtgraph scrolling plots
    └── main_window.py    # Main PyQt5 window
```

## Installation

```bash
pip install -r requirements.txt
```

## Running

```bash
python main.py
```

1. Select the correct COM port from the dropdown.
2. Click **Conectar** – the app waits 2 seconds for the Arduino to reset, then starts displaying data.
3. Click **Detener** to disconnect.
