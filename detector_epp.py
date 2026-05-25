#!/usr/bin/env python3
"""
==============================================================
  SISTEMA DE MONITOREO DE EPP - Cascos y Chalecos
==============================================================
  Arquitectura:
    Android (IP Webcam) --> Python/YOLOv8 local --> Telegram (supervisor)

  Dependencias:
    pip install ultralytics opencv-python numpy requests easyocr

  Modelos locales (dual-model especializado):
    best_casco.pt  modelo_epp_v3 — especialista en cascos
                   4 clases: helmet(0), no-helmet(1), vest(2), no-vest(3)
                   Se usan SOLO las detecciones de helmet / no-helmet
    best_vest.pt   modelo_epp_v4 — especialista en chalecos
                   4 clases: helmet(0), no-helmet(1), vest(2), no-vest(3)
                   mAP50: helmet 64% | no-helmet 40% | vest 67% | no-vest 88%
                   Se usan SOLO las detecciones de vest / no-vest
==============================================================
"""

import csv
import json
import os
import sys
import sqlite3
import cv2
import numpy as np
import time
import threading
import requests
import tkinter as tk
from tkinter import messagebox
from ultralytics import YOLO

try:
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context  # fix SSL en Windows
    import easyocr
    _ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    OCR_DISPONIBLE = True
except ImportError:
    _ocr_reader    = None
    OCR_DISPONIBLE = False
    print("  [Aviso] easyocr no instalado. Identificacion por numero desactivada.")
    print("  Instalar con: py -3.12 -m pip install easyocr")
except Exception as e:
    _ocr_reader    = None
    OCR_DISPONIBLE = False
    print(f"  [Aviso] EasyOCR no pudo cargar: {e}")

def _dir_base() -> str:
    """Devuelve la carpeta del .exe (o del script si se corre con Python)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# ============================================================
#  CONFIGURACION
# ============================================================

# --- Camara IP (app "IP Webcam" en Android) ---
CAMARA_URL = "http://192.168.0.3:8080/video"

# --- Modelos YOLOv8 locales (dual-model especializado) ---
MODELO_CASCO_PATH = os.path.join(_dir_base(), "best_casco.pt")  # v3 — experto en cascos
MODELO_VEST_PATH  = os.path.join(_dir_base(), "best_vest.pt")   # v4 — experto en chalecos

# --- Telegram ---
TELEGRAM_TOKEN   = "8727948475:AAEghAjN_FmC0xmCWpVpQaogWpMyI4g7fjs"
TELEGRAM_CHAT_ID = "5069724402"
TELEGRAM_URL     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# --- Umbrales de confianza por clase (modelo v4) ---
CONFIANZA_MIN      = 0.25   # umbral global YOLO (evita descartar no-helmet bajo)
CONFIANZA_HELMET   = 0.45   # helmet   — mAP50 64%
CONFIANZA_NO_CASCO = 0.30   # no-helmet — mAP50 40%, umbral bajo para más recall
CONFIANZA_VEST     = 0.45   # vest      — mAP50 67%
CONFIANZA_NO_VEST  = 0.50   # no-vest   — mAP50 88%, modelo muy confiado

# --- Anti-falsas alarmas ---
FRAMES_PARA_ALERTA = 4
FRAMES_PARA_OK     = 6

# --- Cooldown entre notificaciones Telegram ---
COOLDOWN_SEGUNDOS = 30.0

# --- Cada cuantos frames correr la IA ---
FRAMES_POR_INFERENCIA = 2

# --- Visualizacion ---
MOSTRAR_VIDEO = True
ANCHO_VENTANA = 960

# --- Logging de infracciones ---
LOG_DIR      = os.path.join(_dir_base(), "infracciones")
LOG_IMG_DIR  = os.path.join(LOG_DIR, "imagenes")
LOG_CSV      = os.path.join(LOG_DIR, "log_infracciones.csv")

# --- Base de datos e identificacion por numero ---
DB_PATH            = os.path.join(_dir_base(), "monitor_epp.db")

# ============================================================
#  BASE DE DATOS SQLite
# ============================================================

def inicializar_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Migración: si la tabla tiene foto_path (esquema viejo), recrearla
    try:
        cols = [col[1] for col in c.execute("PRAGMA table_info(trabajadores)").fetchall()]
        if "foto_path" in cols:
            c.execute("""
                CREATE TABLE trabajadores_nuevo (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre         TEXT    NOT NULL,
                    numero         TEXT    NOT NULL DEFAULT '',
                    activo         INTEGER DEFAULT 1,
                    fecha_registro TEXT    DEFAULT (datetime('now','localtime'))
                )
            """)
            if "numero" in cols:
                c.execute("""
                    INSERT INTO trabajadores_nuevo (id, nombre, numero, activo, fecha_registro)
                    SELECT id, nombre, COALESCE(numero,''), activo, fecha_registro
                    FROM trabajadores
                """)
            else:
                c.execute("""
                    INSERT INTO trabajadores_nuevo (id, nombre, activo, fecha_registro)
                    SELECT id, nombre, activo, fecha_registro FROM trabajadores
                """)
            c.execute("DROP TABLE trabajadores")
            c.execute("ALTER TABLE trabajadores_nuevo RENAME TO trabajadores")
            conn.commit()
    except Exception:
        pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS trabajadores (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre         TEXT    NOT NULL,
            numero         TEXT    NOT NULL DEFAULT '',
            activo         INTEGER DEFAULT 1,
            fecha_registro TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)
    try:
        c.execute("ALTER TABLE trabajadores ADD COLUMN numero TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except Exception:
        pass
    c.execute("""
        CREATE TABLE IF NOT EXISTS infracciones (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha              TEXT NOT NULL,
            hora               TEXT NOT NULL,
            tipo               TEXT NOT NULL,
            imagen_path        TEXT,
            trabajador_nombre  TEXT DEFAULT 'Desconocido',
            confianza_ocr      REAL,
            fecha_registro     TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    # Migracion: renombrar confianza_facial -> confianza_ocr si existe
    try:
        inf_cols = [col[1] for col in c.execute("PRAGMA table_info(infracciones)").fetchall()]
        if "confianza_facial" in inf_cols and "confianza_ocr" not in inf_cols:
            c.execute("ALTER TABLE infracciones RENAME COLUMN confianza_facial TO confianza_ocr")
            conn.commit()
    except Exception:
        pass
    conn.commit()
    conn.close()


def _guardar_infraccion_db(fecha: str, hora: str, tipo: str,
                            imagen_path: str, trabajador: str,
                            confianza: float | None) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO infracciones
           (fecha, hora, tipo, imagen_path, trabajador_nombre, confianza_ocr)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (fecha, hora, tipo, imagen_path, trabajador, confianza),
    )
    conn.commit()
    conn.close()


# ============================================================
#  IDENTIFICACION POR NUMERO (OCR)
# ============================================================

def identificar_trabajador(frame: np.ndarray) -> tuple:
    """
    Lee el numero de identificacion del casco/chaleco usando EasyOCR
    y lo mapea al nombre del trabajador en la base de datos.
    Devuelve (nombre, confianza) o ("Desconocido", None) si no detecta.
    """
    if not OCR_DISPONIBLE:
        return "Desconocido", None

    try:
        # Solo leer digitos (numeros del 1 al 999)
        resultados = _ocr_reader.readtext(
            frame,
            allowlist='0123456789',
            min_size=15,
        )

        # Filtrar: solo aceptar 1-3 digitos con confianza razonable
        numeros = [
            (texto.strip(), float(conf))
            for (_, texto, conf) in resultados
            if texto.strip().isdigit()
            and 1 <= len(texto.strip()) <= 3
            and conf > 0.4
        ]

        if not numeros:
            print("  [OCR] No se detectaron numeros en el frame")
            return "Desconocido", None

        print(f"  [OCR] Numeros detectados: {numeros}")

        # Buscar el numero con mayor confianza en la BD
        conn = sqlite3.connect(DB_PATH)
        for numero, conf in sorted(numeros, key=lambda x: -x[1]):
            fila = conn.execute(
                "SELECT nombre FROM trabajadores WHERE numero=? AND activo=1",
                (numero,)
            ).fetchone()
            if fila:
                conn.close()
                print(f"  [OCR] Trabajador: {fila[0]} (N°{numero}, conf {conf:.0%})")
                return fila[0], round(conf, 2)
        conn.close()

        # Se vio un numero pero no esta registrado
        print(f"  [OCR] Numero {numeros[0][0]} no registrado en BD")
        return f"N°{numeros[0][0]} sin registrar", numeros[0][1]

    except Exception as e:
        print(f"  [OCR] Error: {e}")

    return "Desconocido", None


# ============================================================
#  CONFIGURACION DE CAMARA (pantalla de inicio)
# ============================================================

CONFIG_FILE = os.path.join(_dir_base(), "config.json")

def _cargar_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"ip": "192.168.0.3", "puerto": "8080"}

def _guardar_config(ip: str, puerto: str) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump({"ip": ip, "puerto": puerto}, f)

def mostrar_pantalla_configuracion() -> str:
    """Muestra ventana de configuración y devuelve la URL de la cámara."""
    cfg = _cargar_config()
    resultado = {"url": None}

    ventana = tk.Tk()
    ventana.title("Monitor EPP — Configuración")
    ventana.geometry("420x280")
    ventana.resizable(False, False)
    ventana.configure(bg="#1e1e1e")

    def estilo_label(text, row, col=0, colspan=1):
        lbl = tk.Label(ventana, text=text, bg="#1e1e1e", fg="#cccccc",
                       font=("Segoe UI", 10))
        lbl.grid(row=row, column=col, columnspan=colspan,
                 sticky="w", padx=20, pady=(10, 2))

    def estilo_entry(row, col=1, default=""):
        var = tk.StringVar(value=default)
        entry = tk.Entry(ventana, textvariable=var, width=28,
                         font=("Segoe UI", 10), bg="#2d2d2d", fg="white",
                         insertbackground="white", relief="flat", bd=5)
        entry.grid(row=row, column=col, padx=(0, 20), pady=(10, 2))
        return var

    tk.Label(ventana, text="  Sistema de Monitoreo EPP",
             bg="#0078d4", fg="white", font=("Segoe UI", 13, "bold"),
             anchor="w").grid(row=0, column=0, columnspan=2,
                              sticky="ew", ipady=10)

    estilo_label("IP de la cámara (celular):", 1)
    var_ip = estilo_entry(1, default=cfg["ip"])

    estilo_label("Puerto:", 2)
    var_puerto = estilo_entry(2, default=cfg["puerto"])

    tk.Label(ventana,
             text="  Abrí IP Webcam en tu celular y conectate al mismo WiFi.",
             bg="#1e1e1e", fg="#888888", font=("Segoe UI", 8),
             wraplength=380, justify="left"
             ).grid(row=3, column=0, columnspan=2, padx=20, pady=(6, 0))

    def conectar():
        ip     = var_ip.get().strip()
        puerto = var_puerto.get().strip()
        if not ip or not puerto:
            messagebox.showerror("Error", "Completá la IP y el puerto.")
            return
        _guardar_config(ip, puerto)
        resultado["url"] = f"http://{ip}:{puerto}/video"
        ventana.destroy()

    def salir():
        ventana.destroy()

    frame_btn = tk.Frame(ventana, bg="#1e1e1e")
    frame_btn.grid(row=4, column=0, columnspan=2, pady=20)

    tk.Button(frame_btn, text="  Conectar  ", command=conectar,
              bg="#0078d4", fg="white", font=("Segoe UI", 10, "bold"),
              relief="flat", padx=10, cursor="hand2"
              ).pack(side="left", padx=10)

    tk.Button(frame_btn, text="  Cancelar  ", command=salir,
              bg="#444", fg="white", font=("Segoe UI", 10),
              relief="flat", padx=10, cursor="hand2"
              ).pack(side="left", padx=10)

    ventana.mainloop()
    return resultado["url"]


# ============================================================
#  COLORES (BGR)
# ============================================================
COLOR_OK     = (0, 200, 0)
COLOR_ALERTA = (0, 0, 255)
COLOR_CASCO  = (0, 165, 255)
COLOR_CHALECO= (255, 165, 0)
COLOR_TEXTO  = (255, 255, 255)
COLOR_INFO   = (180, 180, 180)


# ============================================================
#  TELEGRAM
# ============================================================

def telegram_texto(mensaje: str) -> None:
    try:
        requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje},
            timeout=5,
        )
    except Exception as e:
        print(f"  [Telegram] Error texto: {e}")


def telegram_foto(frame: np.ndarray, caption: str) -> None:
    try:
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        requests.post(
            f"{TELEGRAM_URL}/sendPhoto",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            files={"photo": ("alerta.jpg", buf.tobytes(), "image/jpeg")},
            timeout=10,
        )
        print("  [Telegram] Foto enviada al supervisor.")
    except Exception as e:
        print(f"  [Telegram] Error foto: {e}")


# ============================================================
#  FUNCIONES AUXILIARES
# ============================================================

def dibujar_bbox(frame, x1, y1, x2, y2, color, etiqueta, conf):
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    texto = f"{etiqueta} {conf:.0%}"
    (tw, th), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
    cv2.putText(frame, texto, (x1 + 2, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_TEXTO, 1, cv2.LINE_AA)


def overlay_estado(frame, en_alerta, contador, fps,
                   sin_casco, sin_chaleco, trabajador=""):
    overlay = frame.copy()
    alto_panel = 138 if trabajador else 115
    cv2.rectangle(overlay, (0, 0), (420, alto_panel), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    estado = "!! INFRACCION DETECTADA !!" if en_alerta else "  ZONA SEGURA"
    color  = COLOR_ALERTA if en_alerta else COLOR_OK
    cv2.putText(frame, estado, (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.72, color, 2, cv2.LINE_AA)

    faltantes = []
    if sin_casco:   faltantes.append("SIN CASCO")
    if sin_chaleco: faltantes.append("SIN CHALECO")
    detalle = " | ".join(faltantes) if faltantes else "Todo en orden"
    cv2.putText(frame, detalle, (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, COLOR_TEXTO, 1)
    cv2.putText(frame, f"Frames consecutivos: {contador}/{FRAMES_PARA_ALERTA}",
                (10, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.48, COLOR_TEXTO, 1)
    cv2.putText(frame, f"FPS: {fps:.1f}   'q'=salir  't'=test",
                (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_TEXTO, 1)

    if trabajador:
        cv2.putText(frame, f"Trabajador: {trabajador}",
                    (10, 122), cv2.FONT_HERSHEY_SIMPLEX, 0.48, COLOR_INFO, 1)


# ============================================================
#  CLASE PRINCIPAL
# ============================================================

class MonitorEPP:

    def __init__(self):
        print("=" * 60)
        print("  SISTEMA DE MONITOREO DE EPP  (modelo local YOLOv8)")
        print("=" * 60)

        print(f"\n[1/4] Cargando modelo CASCOS: {MODELO_CASCO_PATH} ...")
        self.model_casco = YOLO(MODELO_CASCO_PATH)
        print(f"      Clases: {self.model_casco.names}")

        print(f"\n[2/4] Cargando modelo CHALECOS: {MODELO_VEST_PATH} ...")
        self.model_vest = YOLO(MODELO_VEST_PATH)
        print(f"      Clases: {self.model_vest.names}")

        print(f"\n[3/4] Telegram listo -> chat {TELEGRAM_CHAT_ID}")

        print(f"\n[4/4] Inicializando base de datos: {DB_PATH}")
        inicializar_db()
        self._inicializar_log_csv()
        print(f"      Log CSV: {LOG_CSV}")
        if OCR_DISPONIBLE:
            print("      Identificacion por numero (OCR): ACTIVO")
        else:
            print("      Identificacion por numero (OCR): INACTIVO (instalar easyocr)")

        # Estado alarma
        self.contador_infracciones = 0
        self.contador_ok           = 0
        self.en_alerta             = False
        self.ultimo_envio          = 0.0

        # Resultados compartidos con el hilo de inferencia
        self._lock              = threading.Lock()
        self._detecciones       = []
        self._sin_casco         = False
        self._sin_chaleco       = False
        self._infer_ocupada     = False
        self._trabajador_actual = ""   # nombre del último trabajador identificado

    # ----------------------------------------------------------
    def _inicializar_log_csv(self) -> None:
        os.makedirs(LOG_IMG_DIR, exist_ok=True)
        if not os.path.exists(LOG_CSV):
            with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(
                    ["fecha", "hora", "tipo", "imagen", "trabajador"])

    def _guardar_infraccion(self, sin_casco: bool, sin_chaleco: bool,
                             frame: np.ndarray,
                             trabajador: str = "Desconocido",
                             confianza: float | None = None) -> None:
        tipo       = " | ".join(filter(None, [
                        "Sin casco"   if sin_casco   else "",
                        "Sin chaleco" if sin_chaleco else ""]))
        timestamp  = time.strftime("%Y-%m-%d_%H-%M-%S")
        nombre_img = f"{timestamp}_{tipo.replace(' | ','_').replace(' ','_')}.jpg"
        ruta_img   = os.path.join(LOG_IMG_DIR, nombre_img)
        fecha      = time.strftime("%d/%m/%Y")
        hora       = time.strftime("%H:%M:%S")

        cv2.imwrite(ruta_img, frame)

        # SQLite
        _guardar_infraccion_db(fecha, hora, tipo, nombre_img, trabajador, confianza)

        # CSV (backup / compatibilidad)
        with open(LOG_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([fecha, hora, tipo, nombre_img, trabajador])

        print(f"  [Log] Infraccion guardada: {nombre_img}  |  Trabajador: {trabajador}")

    # ----------------------------------------------------------
    def _inferir(self, frame: np.ndarray) -> None:
        """
        Dual-model: corre ambos modelos especializados y fusiona resultados.
          model_casco (v3) → solo se toman detecciones de helmet / no-helmet
          model_vest  (v4) → solo se toman detecciones de vest   / no-vest
        Corre en hilo aparte.
        """
        UMBRAL_BBOX = {
            "helmet":    CONFIANZA_HELMET,
            "no-helmet": CONFIANZA_NO_CASCO,
            "vest":      CONFIANZA_VEST,
            "no-vest":   CONFIANZA_NO_VEST,
        }
        CLASES_CASCO = {"helmet", "no-helmet"}
        CLASES_VEST  = {"vest", "no-vest"}

        detecciones = []
        sin_casco   = False
        sin_chaleco = False

        def _procesar_resultados(resultados, model_names, clases_validas):
            filas   = []
            s_casco = False
            s_vest  = False
            for box in resultados.boxes:
                cls_id = int(box.cls[0])
                conf   = float(box.conf[0])
                nombre = model_names[cls_id]
                if nombre not in clases_validas:
                    continue
                if conf < UMBRAL_BBOX.get(nombre, 0.45):
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                filas.append({"nombre": nombre, "conf": conf,
                               "x1": x1, "y1": y1, "x2": x2, "y2": y2})
                if nombre == "no-helmet":
                    s_casco = True
                elif nombre == "no-vest":
                    s_vest = True
            return filas, s_casco, s_vest

        try:
            res_casco = self.model_casco(frame, conf=CONFIANZA_MIN, verbose=False)[0]
            filas_c, sc, _ = _procesar_resultados(
                res_casco, self.model_casco.names, CLASES_CASCO)
            detecciones.extend(filas_c)
            sin_casco = sc
        except Exception as e:
            print(f"  [YOLO-casco] Error: {e}")

        try:
            res_vest = self.model_vest(frame, conf=CONFIANZA_MIN, verbose=False)[0]
            filas_v, _, sv = _procesar_resultados(
                res_vest, self.model_vest.names, CLASES_VEST)
            detecciones.extend(filas_v)
            sin_chaleco = sv
        except Exception as e:
            print(f"  [YOLO-vest] Error: {e}")

        with self._lock:
            self._detecciones   = detecciones
            self._sin_casco     = sin_casco
            self._sin_chaleco   = sin_chaleco
            self._infer_ocupada = False

    def _disparar_inferencia(self, frame: np.ndarray) -> None:
        with self._lock:
            if self._infer_ocupada:
                return
            self._infer_ocupada = True
        hilo = threading.Thread(target=self._inferir, args=(frame.copy(),), daemon=True)
        hilo.start()

    # ----------------------------------------------------------
    def _actualizar_estado(self, hay_infraccion: bool) -> None:
        if hay_infraccion:
            self.contador_infracciones += 1
            self.contador_ok = 0
        else:
            self.contador_ok += 1
            self.contador_infracciones = 0

        if not self.en_alerta and self.contador_infracciones >= FRAMES_PARA_ALERTA:
            self.en_alerta = True
            print("\n  *** ALERTA: Infraccion EPP confirmada ***")

        if self.en_alerta and self.contador_ok >= FRAMES_PARA_OK:
            self.en_alerta = False
            self.contador_infracciones = 0
            with self._lock:
                self._trabajador_actual = ""
            print("  --- Zona segura. Alerta desactivada ---")

    # ----------------------------------------------------------
    def _notificar_y_guardar(self, sin_casco: bool, sin_chaleco: bool,
                              frame: np.ndarray) -> None:
        """
        Corre en hilo aparte:
          1. Identifica al trabajador por reconocimiento facial
          2. Envia foto + datos a Telegram
          3. Guarda la infraccion en SQLite y CSV
        """
        def _tarea():
            frame_copia = frame.copy()

            # 1. Identificacion facial
            print("  [Facial] Identificando trabajador...")
            trabajador, confianza = identificar_trabajador(frame_copia)
            with self._lock:
                self._trabajador_actual = trabajador
            if confianza is not None:
                print(f"  [Facial] Trabajador: {trabajador} (confianza {confianza:.0%})")
            else:
                print(f"  [Facial] Trabajador: {trabajador}")

            # 2. Notificacion Telegram
            faltantes = []
            if sin_casco:   faltantes.append("Sin casco")
            if sin_chaleco: faltantes.append("Sin chaleco")

            caption = (
                "INFRACCION EPP DETECTADA\n"
                f"Fecha: {time.strftime('%d/%m/%Y')}  Hora: {time.strftime('%H:%M:%S')}\n"
                f"Infraccion: {' | '.join(faltantes)}\n"
                f"Trabajador: {trabajador}\n"
                "Tomar accion inmediata."
            )
            telegram_foto(frame_copia, caption)

            # 3. Guardar en DB y CSV
            self._guardar_infraccion(sin_casco, sin_chaleco, frame_copia,
                                     trabajador, confianza)

        hilo = threading.Thread(target=_tarea, daemon=True)
        hilo.start()

    # ----------------------------------------------------------
    def ejecutar(self) -> None:
        cap = cv2.VideoCapture(CAMARA_URL)
        if not cap.isOpened():
            print(f"\n  ERROR: No se pudo conectar a {CAMARA_URL}")
            print("  Verifica que IP Webcam este corriendo en el celular.")
            return

        print(f"\n  Camara conectada: {CAMARA_URL}")
        print("  Presiona 'q' para salir, 't' para enviar alerta de prueba\n")

        telegram_texto("Sistema Monitor EPP iniciado. Vigilando zona de trabajo.")

        fps_timer  = time.time()
        fps_frames = 0
        ultimo_fps = 0.0
        frame_cnt  = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            frame_cnt += 1
            ratio     = ANCHO_VENTANA / frame.shape[1]
            frame_vis = cv2.resize(frame, (ANCHO_VENTANA, int(frame.shape[0] * ratio)))

            if frame_cnt % FRAMES_POR_INFERENCIA == 0:
                self._disparar_inferencia(frame_vis)

            with self._lock:
                detecciones     = list(self._detecciones)
                sin_casco       = self._sin_casco
                sin_chaleco     = self._sin_chaleco
                trabajador_vis  = self._trabajador_actual

            # Dibujar bounding boxes
            for d in detecciones:
                nombre = d["nombre"]
                conf   = d["conf"]
                x1, y1, x2, y2 = d["x1"], d["y1"], d["x2"], d["y2"]

                if nombre == "helmet":
                    dibujar_bbox(frame_vis, x1, y1, x2, y2, COLOR_OK,     "Casco OK",    conf)
                elif nombre == "no-helmet":
                    dibujar_bbox(frame_vis, x1, y1, x2, y2, COLOR_ALERTA, "SIN CASCO",   conf)
                elif nombre == "vest":
                    dibujar_bbox(frame_vis, x1, y1, x2, y2, COLOR_OK,     "Chaleco OK",  conf)
                elif nombre == "no-vest":
                    dibujar_bbox(frame_vis, x1, y1, x2, y2, COLOR_ALERTA, "SIN CHALECO", conf)

            self._actualizar_estado(sin_casco or sin_chaleco)

            # Notificar y guardar con cooldown
            ahora = time.time()
            if self.en_alerta and (ahora - self.ultimo_envio) >= COOLDOWN_SEGUNDOS:
                self._notificar_y_guardar(sin_casco, sin_chaleco, frame_vis)
                self.ultimo_envio = ahora

            # FPS
            fps_frames += 1
            if time.time() - fps_timer >= 1.0:
                ultimo_fps = fps_frames / (time.time() - fps_timer)
                fps_frames = 0
                fps_timer  = time.time()

            if MOSTRAR_VIDEO:
                overlay_estado(frame_vis, self.en_alerta,
                               self.contador_infracciones, ultimo_fps,
                               sin_casco, sin_chaleco, trabajador_vis)
                cv2.imshow("Monitor EPP", frame_vis)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('t'):
                    print("  [TEST] Enviando alerta de prueba a Telegram...")
                    self._notificar_y_guardar(True, True, frame_vis)

        cap.release()
        cv2.destroyAllWindows()
        telegram_texto("Sistema Monitor EPP detenido.")
        print("\n  Sistema detenido.")


# ============================================================
#  PUNTO DE ENTRADA
# ============================================================

if __name__ == "__main__":
    url = mostrar_pantalla_configuracion()
    if url is None:
        print("  Configuración cancelada. Cerrando.")
    else:
        CAMARA_URL = url
        monitor = MonitorEPP()
        monitor.ejecutar()
