# Guía Rápida de Conexión de Pines — ESP32

## Diagrama de conexión

```
                     ESP32 Dev Module
                    ┌──────────────────┐
                    │                  │
  LED Rojo (+) ────►│ GPIO 2  (D2)     │
                    │                  │
  Buzzer (+) ──────►│ GPIO 4  (D4)     │
                    │                  │
  LED/Buzzer (-) ──►│ GND              │
                    │                  │
                    │ 3.3V / 5V ──────►│── VCC (alimentación)
                    └──────────────────┘
```

---

## Componentes necesarios

| Componente         | Cantidad | Observaciones                              |
|--------------------|----------|--------------------------------------------|
| ESP32 Dev Module   | 1        | Cualquier variante con WiFi                |
| LED rojo 5mm       | 1        | —                                          |
| Resistencia 220 Ω  | 1        | Para limitar corriente del LED             |
| Buzzer activo 5V   | 1        | Recomendado (más fácil de usar)            |
| Protoboard         | 1        | —                                          |
| Cables Dupont      | varios   | —                                          |

---

## Conexiones detalladas

### LED Rojo

```
GPIO 2 ──────────── Resistencia 220Ω ──────────── Ánodo (+) LED ──── Cátodo (-) LED ──── GND
```

> El pin GPIO 2 también es el LED incorporado en la mayoría de placas ESP32.
> Puedes usar ese LED directamente para pruebas (sin componentes externos).

### Buzzer Activo (recomendado)

```
GPIO 4 ──────────── Pin (+) Buzzer
GND    ──────────── Pin (-) Buzzer
```

> Un **buzzer activo** tiene oscilador interno: suena al aplicar 3.3V/5V directo.
> El código usa PWM (50% duty cycle) que también funciona, pero si tu buzzer
> activo suena raro, cambia `ledcWrite(CANAL_PWM, 128)` por `digitalWrite(PIN_BUZZER, HIGH)`.

### Buzzer Pasivo (alternativa)

```
GPIO 4 ──────────── Pin (+) Buzzer   (se controla por frecuencia PWM)
GND    ──────────── Pin (-) Buzzer
```

> Con buzzer pasivo el código PWM es necesario. Puedes cambiar `FREQ_BUZZER`
> en el .ino para ajustar el tono (1000–4000 Hz son los más audibles).

---

## Pasos para poner en marcha

### 1. ESP32

1. Abrir `esp32_alarma/esp32_alarma.ino` en Arduino IDE.
2. Editar las líneas:
   ```cpp
   const char* SSID     = "NombreDetuRed";
   const char* PASSWORD = "TuContraseña";
   ```
3. (Opcional) Asignar IP fija: descomentar el bloque de `WiFi.config()`.
4. Seleccionar placa: **Tools → Board → ESP32 Dev Module**.
5. Seleccionar puerto COM correcto.
6. Cargar el sketch (→ Upload).
7. Abrir **Serial Monitor** a 115200 baudios.
8. Verificar que imprime la IP asignada:
   ```
   IP del ESP32: 192.168.1.XXX
   ```

### 2. Celular Android (IP Webcam)

1. Instalar la app **IP Webcam** (Pavel Khlebovich) desde Play Store.
2. Bajar hasta **Start server**.
3. Anotar la URL que aparece, ej: `http://192.168.1.105:8080`.
4. Verificar en el navegador del PC que se ve el video.

### 3. PC — Script Python

1. Instalar dependencias:
   ```bash
   pip install ultralytics opencv-python numpy
   ```
2. Obtener un modelo YOLOv8 para PPE.
   - **Opción A** (descarga automática con ultralytics Hub):
     ```python
     # Reemplazar MODELO_PATH por el ID del modelo en Hub
     ```
   - **Opción B** (modelo pre-entrenado de HuggingFace):
     Buscar `yolov8 ppe detection` en [huggingface.co](https://huggingface.co)
     y descargar el `.pt`.
   - **Opción C** (dataset público):
     Dataset "Safety Helmet Detection" en Roboflow Universe,
     exportar como YOLOv8 y entrenar:
     ```bash
     yolo train data=ppe.yaml model=yolov8n.pt epochs=50 imgsz=640
     ```
3. Editar `detector_epp.py`:
   ```python
   CAMARA_URL  = "http://192.168.1.XXX:8080/video"   # IP del celular
   ESP32_IP    = "192.168.1.YYY"                      # IP del ESP32
   MODELO_PATH = "ruta/a/tu/modelo.pt"
   ```
4. Ejecutar:
   ```bash
   python detector_epp.py
   ```

### 4. Verificar el sistema

- Con el script corriendo, presiona **'t'** en la ventana de video para
  enviar una señal de prueba al ESP32 y confirmar que el buzzer/LED responden.
- Si el ESP32 no recibe, verificar que ambos dispositivos estén en la
  **misma red WiFi** y que el firewall de Windows no bloquee el puerto UDP 4210.

---

## Solución de problemas

| Problema                         | Solución                                                    |
|----------------------------------|-------------------------------------------------------------|
| ESP32 no se conecta al WiFi      | Verificar SSID/Password; usar 2.4 GHz (ESP32 no soporta 5 GHz) |
| Python no detecta casco/chaleco  | Ajustar `NOMBRES_CASCO` / `NOMBRES_CHALECO` con los nombres de clase exactos de tu modelo |
| Alarma suena por falsos positivos | Aumentar `FRAMES_PARA_ALERTA` y `CONFIANZA_MIN` en el script |
| Video lagueado                   | Reducir resolución en IP Webcam o bajar `ANCHO_VENTANA`     |
| UDP no llega al ESP32            | Agregar regla de entrada UDP en el Firewall de Windows      |
