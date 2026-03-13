# Shock Dyno Monitor

Aplicación Python de escritorio para monitoreo en tiempo real de banco de pruebas de amortiguadores, conectada a una ECU Speeduino vía puerto serial USB.

## Características

- Conexión a ECU Speeduino vía USB (protocolo binario con CRC32)
- 5 sensores monitoreados: Fuerza (N), Recorrido (mm), Temp. Amortiguador (°C), Temp. Reservorio (°C), Velocidad (RPM)
- Dashboard con indicadores en tiempo real y barras de progreso
- Gráficas en tiempo real con pyqtgraph:
  - Fuerza vs Tiempo
  - Recorrido vs Tiempo
  - Temperaturas vs Tiempo
  - Fuerza vs Recorrido (curva característica)
- Logging automático a CSV con timestamps en milisegundos
- Sistema de alarmas configurables con indicación visual
- Modo SIMULADOR para testing sin hardware
- Interfaz gráfica oscura con PyQt5
- Código completamente en español con documentación exhaustiva

## Estructura del Proyecto

```
ShockDynoMonitor/
├── README.md
├── requirements.txt
├── main.py
├── config/
│   └── default_config.json
├── core/
│   ├── __init__.py
│   ├── speeduino_protocol.py   # Protocolo CRC32 + parseo de respuestas
│   ├── serial_manager.py       # Conexión serial + threads TX/RX + simulador
│   ├── data_parser.py          # Conversión de bytes a valores físicos
│   ├── data_logger.py          # Logging CSV thread-safe
│   └── alarm_manager.py        # Gestión de alarmas configurables
├── ui/
│   ├── __init__.py
│   ├── main_window.py          # Ventana principal con tabs
│   ├── dashboard_widget.py     # Panel de 5 sensores
│   ├── graphs_widget.py        # 4 gráficas en tiempo real
│   └── config_dialog.py        # Diálogo de configuración
└── utils/
    ├── __init__.py
    ├── config_manager.py       # Carga/guardado de config JSON
    └── data_buffer.py          # Buffer circular thread-safe
```

## Requisitos

- Python 3.11+
- Windows 10/11 (recomendado) o Linux
- Puerto serial USB (o usar el modo SIMULADOR)

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
python main.py
```

Al iniciar, la aplicación muestra la ventana principal con:
1. Selector de puerto (incluye **SIMULADOR** para testing sin hardware)
2. Botón **Conectar** para iniciar la comunicación
3. Tabs: **Dashboard**, **Gráficas**
4. Botón **Iniciar Log** para guardar datos a CSV

## Protocolo Speeduino

Basado en captura validada el 2026-03-12.

- **ECU:** Speeduino 2025.01.4
- **Baudrate:** 115200, 8N1
- **Polling:** 50ms (20Hz)
- **Comando:** `0x41` con CRC32 little-endian
- **Respuesta:** Header `00 XX 00` + 128 bytes de payload + CRC32

### Offsets de Payload (Estándar Speeduino firmware 2025.01 / currentStatus)

| Offset | Sensor | Tipo | Conversión |
|--------|--------|------|------------|
| 4-5 | Fuerza (N) | uint16 Little-Endian | `raw / 2.0` |
| 6 | Temp. Reservorio (°C) | uint8 | `raw - 40` |
| 7 | Temp. Amortiguador (°C) | uint8 | `raw - 40` |
| 14-15 | Velocidad (RPM) | uint16 Little-Endian | valor directo |
| 24 | Recorrido (mm) | uint8 | `(raw / 255.0) * 100` |

## Configuración

Editar `config/default_config.json` o usar el menú **Archivo → Configuración**.

Los cambios del usuario se guardan en `config/config.json` (no modifica el archivo por defecto).

### Parámetros principales

```json
{
  "conexion": {
    "puerto": "SIMULADOR",
    "baudrate": 115200,
    "delay_conexion": 10
  },
  "alarmas": {
    "temp_amortiguador_max": 60.0,
    "temp_reservorio_max": 50.0,
    "fuerza_max": 2000.0
  },
  "logging": {
    "carpeta": "logs"
  }
}
```

## Modo Simulador

Seleccionar **SIMULADOR** en el combo de puertos para generar datos aleatorios realistas sin necesidad de hardware:

- Fuerza: 100–1500 N
- Recorrido: 10–80 mm
- Temperaturas: 25–55°C
- Velocidad: 50–400 RPM

## Troubleshooting

- **No aparece el puerto COM:** Instalar drivers USB de la ECU, verificar en el Administrador de Dispositivos.
- **Error de conexión:** Cerrar TunerStudio antes de conectar (solo un programa puede usar el puerto a la vez).
- **No llegan datos después de conectar:** La ECU necesita 10 segundos de inicialización (delay configurado).
- **Baudrate incorrecto:** Verificar que la ECU esté configurada a 115200 bps.
- **CRC errors en el log:** Ruido en el cable USB, intentar con un cable más corto o con ferrita.

## Alarmas

Las alarmas se muestran en la barra de estado y cambian el color de las tarjetas del dashboard:

| Alarma | Umbral Default | Nivel |
|--------|---------------|-------|
| Temp. Amortiguador | > 60°C | Crítico |
| Temp. Reservorio | > 50°C | Crítico |
| Fuerza Excesiva | > 2000 N | Advertencia |
| Velocidad Excesiva | > 5000 RPM | Advertencia |

## Logging CSV

Los archivos se generan automáticamente en la carpeta `logs/`:

```
logs/shock_test_20260312_153045.csv
```

Formato del CSV:

```
Timestamp,Fuerza_N,Recorrido_mm,Temp_Amortiguador_C,Temp_Reservorio_C,Velocidad_RPM
2026-03-12 15:30:45.123,1250.50,45.20,38.0,32.0,120
```
