# Monitor EPP — Sistema de Monitoreo de Equipos de Proteccion Personal

**Materia:** IAS911 - Inteligencia Artificial en Sistemas Embebidos  
**Grupo:** 2 | **Integrante:** Jhonmer Mamani Loza | **Mayo 2026**

---

## Descripcion

Sistema en tiempo real que detecta si los trabajadores portan **casco** y **chaleco reflectante** usando vision por computadora. Identifica al trabajador infractor mediante OCR sobre el numero visible en su equipo, registra cada infraccion en SQLite y envia alertas automaticas al supervisor via Telegram.

---

## Arquitectura

```
Camara IP (IP Webcam Android)
        |
        v  HTTP/MJPEG/WiFi
   PC Central (Python 3.12)
   ├── YOLOv8 dual-model (casco + chaleco)
   ├── EasyOCR (identificacion por numero)
   ├── SQLite (base de datos infracciones)
   └── Telegram Bot (alertas supervisor)
        |
        v  UDP
   ESP32 (buzzer + LED fisico)
```

---

## Funcionalidades

- Deteccion de casco y chaleco con YOLOv8 (modelos fine-tuned)
- Anti-falsas alarmas: requiere 4 frames consecutivos para activar alerta
- Identificacion del trabajador por numero en casco/chaleco (EasyOCR)
- Notificaciones Telegram con foto y nombre del infractor (cooldown 30s)
- Base de datos SQLite con historial completo de infracciones
- App de escritorio tkinter para gestion de trabajadores
- Integracion fisica con ESP32 (buzzer + LED via UDP)
- Ejecutable Windows .exe generado con PyInstaller

---

## Estructura del proyecto

```
MonitorEPP/
  detector_epp.py            # Sistema principal de deteccion
  gestionar_trabajadores.py  # App GUI de gestion de trabajadores
  config.json                # Configuracion (IP camara, Telegram)
  best_casco.pt              # Modelo YOLOv8 casco (18 MB)
  best_vest.pt               # Modelo YOLOv8 chaleco (6 MB)
  esp32_alarma/
    esp32_alarma.ino         # Firmware ESP32 (Arduino)
  entrenamiento_epp.ipynb    # Notebook entrenamiento YOLOv8
  finetune_epp.ipynb         # Notebook fine-tuning
  requirements.txt           # Dependencias Python
```

---

## Instalacion

**Requisito: Python 3.12** (no compatible con 3.13 o 3.14 por TensorFlow)

```bash
pip install ultralytics easyocr opencv-python requests torch pillow
```

---

## Uso

```bash
# 1. Registrar trabajadores
python gestionar_trabajadores.py

# 2. Iniciar el monitor (con IP Webcam activo en el celular)
python detector_epp.py
```

Edita `config.json` con tu IP de camara y token de Telegram antes de ejecutar.

---

## Hardware requerido para ESP32

- ESP32 DevKit
- LED rojo + resistencia 220 ohm
- Buzzer pasivo
- Conexion al mismo WiFi que el PC

---

## Tecnologias

- Python 3.12, OpenCV, YOLOv8 (Ultralytics), EasyOCR
- SQLite, Tkinter, PyInstaller
- ESP32 + Arduino, IP Webcam (Android)
- Telegram Bot API
