#!/usr/bin/env python3
"""
==============================================================
  DASHBOARD DE ESTADÍSTICAS — Monitor EPP
==============================================================
  Visualiza infracciones registradas en monitor_epp.db:
  · Tarjetas de resumen
  · Infracciones por trabajador (barras)
  · Tipos de infracción (torta)
  · Tendencia diaria (línea)
  · Historial reciente (tabla)
==============================================================
"""

import os
import sys
import sqlite3
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
from collections import Counter

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# ── Colores tema oscuro ──────────────────────────────────────
BG        = "#1e1e1e"
BG2       = "#2d2d2d"
BG3       = "#3a3a3a"
AZUL      = "#0078d4"
AZUL2     = "#1a8fe3"
VERDE     = "#27ae60"
ROJO      = "#e74c3c"
AMARILLO  = "#f39c12"
TEXTO     = "#e0e0e0"
TEXTO2    = "#aaaaaa"
BLANCO    = "#ffffff"


def _dir_base() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


DB_PATH = os.path.join(_dir_base(), "monitor_epp.db")

# ── Paleta para gráficas ─────────────────────────────────────
COLORES_BARRAS = ["#0078d4","#1a8fe3","#2ea8f0","#56c0f7","#84d4fb",
                  "#aae4ff","#c5edff","#daf3ff","#edf9ff","#f5fcff"]
COLORES_TORTA  = ["#e74c3c","#0078d4","#27ae60","#f39c12","#9b59b6"]

plt.rcParams.update({
    "axes.facecolor":   BG2,
    "figure.facecolor": BG2,
    "axes.edgecolor":   "#555555",
    "axes.labelcolor":  TEXTO,
    "xtick.color":      TEXTO2,
    "ytick.color":      TEXTO2,
    "text.color":       TEXTO,
    "grid.color":       "#3a3a3a",
    "grid.linestyle":   "--",
    "grid.alpha":       0.6,
    "font.family":      "sans-serif",
})


# ════════════════════════════════════════════════════════════
#  BASE DE DATOS — consultas
# ════════════════════════════════════════════════════════════

def _conn():
    return sqlite3.connect(DB_PATH)


def total_infracciones() -> int:
    try:
        c = _conn()
        n = c.execute("SELECT COUNT(*) FROM infracciones").fetchone()[0]
        c.close()
        return n
    except Exception:
        return 0


def total_trabajadores_activos() -> int:
    try:
        c = _conn()
        n = c.execute("SELECT COUNT(*) FROM trabajadores WHERE activo=1").fetchone()[0]
        c.close()
        return n
    except Exception:
        return 0


def trabajador_mas_infractor() -> tuple[str, int]:
    try:
        c = _conn()
        fila = c.execute(
            "SELECT trabajador_nombre, COUNT(*) AS cnt "
            "FROM infracciones "
            "WHERE trabajador_nombre != 'Desconocido' "
            "GROUP BY trabajador_nombre ORDER BY cnt DESC LIMIT 1"
        ).fetchone()
        c.close()
        return (fila[0], fila[1]) if fila else ("—", 0)
    except Exception:
        return ("—", 0)


def infracciones_por_trabajador() -> list[tuple]:
    try:
        c = _conn()
        rows = c.execute(
            "SELECT trabajador_nombre, COUNT(*) AS cnt "
            "FROM infracciones "
            "GROUP BY trabajador_nombre ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        c.close()
        return rows
    except Exception:
        return []


def infracciones_por_tipo() -> list[tuple]:
    try:
        c = _conn()
        rows = c.execute(
            "SELECT tipo, COUNT(*) FROM infracciones GROUP BY tipo"
        ).fetchall()
        c.close()
        return rows
    except Exception:
        return []


def infracciones_por_dia(dias: int = 14) -> list[tuple]:
    try:
        fecha_min = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
        c = _conn()
        rows = c.execute(
            "SELECT fecha, COUNT(*) FROM infracciones "
            "WHERE fecha >= ? GROUP BY fecha ORDER BY fecha",
            (fecha_min,)
        ).fetchall()
        c.close()
        # Rellenar días sin infracciones
        resultado = {}
        for i in range(dias + 1):
            d = (datetime.now() - timedelta(days=dias - i)).strftime("%Y-%m-%d")
            resultado[d] = 0
        for fecha, cnt in rows:
            resultado[fecha] = cnt
        return list(resultado.items())
    except Exception:
        return []


def ultimas_infracciones(n: int = 30) -> list[tuple]:
    try:
        c = _conn()
        rows = c.execute(
            "SELECT fecha, hora, tipo, trabajador_nombre, confianza_ocr "
            "FROM infracciones ORDER BY id DESC LIMIT ?",
            (n,)
        ).fetchall()
        c.close()
        return rows
    except Exception:
        return []


# ════════════════════════════════════════════════════════════
#  WIDGETS AUXILIARES
# ════════════════════════════════════════════════════════════

class Tarjeta(tk.Frame):
    """Tarjeta de resumen con icono, valor y etiqueta."""

    def __init__(self, parent, icono: str, valor: str, etiqueta: str,
                 color: str = AZUL, **kwargs):
        super().__init__(parent, bg=BG2, bd=0, **kwargs)
        self.configure(padx=16, pady=12)

        tk.Label(self, text=icono, bg=BG2, fg=color,
                 font=("Segoe UI", 22)).pack(anchor="w")
        self._lbl_valor = tk.Label(self, text=valor, bg=BG2, fg=BLANCO,
                                   font=("Segoe UI", 26, "bold"))
        self._lbl_valor.pack(anchor="w")
        tk.Label(self, text=etiqueta, bg=BG2, fg=TEXTO2,
                 font=("Segoe UI", 9)).pack(anchor="w")

        # Borde de color en la parte superior
        self._borde = tk.Frame(self, bg=color, height=3)
        self._borde.place(x=0, y=0, relwidth=1)

    def actualizar(self, valor: str):
        self._lbl_valor.configure(text=valor)


# ════════════════════════════════════════════════════════════
#  VENTANA PRINCIPAL
# ════════════════════════════════════════════════════════════

class Dashboard:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Monitor EPP — Dashboard de Estadísticas")
        self.root.geometry("1100x700")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(900, 600)

        self._construir_ui()
        self._actualizar_todo()
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    # ──────────────────────────────────────────────────────
    def _construir_ui(self):
        # Encabezado
        hdr = tk.Frame(self.root, bg=AZUL)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  📊  Monitor EPP — Dashboard de Estadísticas",
                 bg=AZUL, fg=BLANCO, font=("Segoe UI", 13, "bold"),
                 anchor="w").pack(side="left", ipady=9)
        tk.Button(hdr, text="↻  Actualizar",
                  command=self._actualizar_todo,
                  bg="#005fa3", fg=BLANCO, font=("Segoe UI", 9),
                  relief="flat", padx=12, cursor="hand2",
                  activebackground="#004c82", activeforeground=BLANCO
                  ).pack(side="right", padx=10, pady=6)
        self._lbl_hora = tk.Label(hdr, text="", bg=AZUL, fg="#cce4f7",
                                  font=("Segoe UI", 9))
        self._lbl_hora.pack(side="right", padx=4)

        # Notebook con pestañas
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook",       background=BG,  borderwidth=0)
        style.configure("TNotebook.Tab",   background=BG2, foreground=TEXTO2,
                        padding=[16, 6],   font=("Segoe UI", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", BG3)],
                  foreground=[("selected", BLANCO)])

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=0, pady=0)

        self._tab_resumen()
        self._tab_tendencia()
        self._tab_historial()

    # ──────────────────────────────────────────────────────
    #  PESTAÑA 1 — RESUMEN
    # ──────────────────────────────────────────────────────
    def _tab_resumen(self):
        frame = tk.Frame(self.nb, bg=BG)
        self.nb.add(frame, text="  Resumen  ")

        # ── Tarjetas ──
        fila_tarjetas = tk.Frame(frame, bg=BG)
        fila_tarjetas.pack(fill="x", padx=14, pady=(14, 6))

        self.t_total = Tarjeta(fila_tarjetas, "⚠", "0",
                               "Total infracciones", ROJO)
        self.t_total.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.t_trab = Tarjeta(fila_tarjetas, "👷", "0",
                              "Trabajadores registrados", AZUL)
        self.t_trab.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.t_top = Tarjeta(fila_tarjetas, "🏆", "—",
                             "Mayor infractor", AMARILLO)
        self.t_top.pack(side="left", fill="x", expand=True)

        # ── Gráficas ──
        fila_graficas = tk.Frame(frame, bg=BG)
        fila_graficas.pack(fill="both", expand=True, padx=14, pady=(6, 14))

        # Barras — infracciones por trabajador
        self.fig_barras = Figure(figsize=(5, 3.4), dpi=96)
        self.ax_barras  = self.fig_barras.add_subplot(111)
        self.canvas_barras = FigureCanvasTkAgg(self.fig_barras, fila_graficas)
        self.canvas_barras.get_tk_widget().pack(
            side="left", fill="both", expand=True, padx=(0, 6))

        # Torta — por tipo
        self.fig_torta = Figure(figsize=(3.6, 3.4), dpi=96)
        self.ax_torta  = self.fig_torta.add_subplot(111)
        self.canvas_torta = FigureCanvasTkAgg(self.fig_torta, fila_graficas)
        self.canvas_torta.get_tk_widget().pack(
            side="left", fill="both", expand=True)

    # ──────────────────────────────────────────────────────
    #  PESTAÑA 2 — TENDENCIA
    # ──────────────────────────────────────────────────────
    def _tab_tendencia(self):
        frame = tk.Frame(self.nb, bg=BG)
        self.nb.add(frame, text="  Tendencia diaria  ")

        self.fig_linea = Figure(figsize=(9, 4.5), dpi=96)
        self.ax_linea  = self.fig_linea.add_subplot(111)
        self.canvas_linea = FigureCanvasTkAgg(self.fig_linea, frame)
        self.canvas_linea.get_tk_widget().pack(
            fill="both", expand=True, padx=14, pady=14)

    # ──────────────────────────────────────────────────────
    #  PESTAÑA 3 — HISTORIAL
    # ──────────────────────────────────────────────────────
    def _tab_historial(self):
        frame = tk.Frame(self.nb, bg=BG)
        self.nb.add(frame, text="  Historial reciente  ")

        tk.Label(frame, text="Últimas 30 infracciones registradas",
                 bg=BG, fg=TEXTO2, font=("Segoe UI", 9)
                 ).pack(anchor="w", padx=14, pady=(10, 4))

        ft = tk.Frame(frame, bg=BG)
        ft.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        cols = ("fecha", "hora", "tipo", "trabajador", "confianza")
        self.tabla_hist = ttk.Treeview(ft, columns=cols,
                                       show="headings", height=20)
        self.tabla_hist.heading("fecha",      text="Fecha")
        self.tabla_hist.heading("hora",       text="Hora")
        self.tabla_hist.heading("tipo",       text="Tipo de infracción")
        self.tabla_hist.heading("trabajador", text="Trabajador")
        self.tabla_hist.heading("confianza",  text="Confianza OCR")
        self.tabla_hist.column("fecha",      width=95)
        self.tabla_hist.column("hora",       width=75)
        self.tabla_hist.column("tipo",       width=190)
        self.tabla_hist.column("trabajador", width=180)
        self.tabla_hist.column("confianza",  width=110, anchor="center")

        sc = ttk.Scrollbar(ft, orient="vertical",
                           command=self.tabla_hist.yview)
        self.tabla_hist.configure(yscrollcommand=sc.set)
        self.tabla_hist.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

    # ──────────────────────────────────────────────────────
    #  ACTUALIZAR TODO
    # ──────────────────────────────────────────────────────
    def _actualizar_todo(self):
        self._lbl_hora.configure(
            text="Actualizado: " + datetime.now().strftime("%H:%M:%S"))
        self._actualizar_tarjetas()
        self._dibujar_barras()
        self._dibujar_torta()
        self._dibujar_linea()
        self._cargar_historial()

    def _actualizar_tarjetas(self):
        total = total_infracciones()
        trab  = total_trabajadores_activos()
        top_nombre, top_cnt = trabajador_mas_infractor()

        self.t_total.actualizar(str(total))
        self.t_trab.actualizar(str(trab))
        self.t_top.actualizar(
            f"{top_nombre}\n({top_cnt} infr.)" if top_cnt else "—")

    # ──────────────────────────────────────────────────────
    #  GRÁFICA BARRAS
    # ──────────────────────────────────────────────────────
    def _dibujar_barras(self):
        datos = infracciones_por_trabajador()
        ax = self.ax_barras
        ax.clear()

        if not datos:
            ax.text(0.5, 0.5, "Sin datos", ha="center", va="center",
                    color=TEXTO2, fontsize=12, transform=ax.transAxes)
        else:
            nombres = [d[0] if len(d[0]) <= 14 else d[0][:13] + "…"
                       for d in datos]
            valores = [d[1] for d in datos]
            colores = [COLORES_BARRAS[i % len(COLORES_BARRAS)]
                       for i in range(len(datos))]

            barras = ax.barh(nombres[::-1], valores[::-1],
                             color=colores[::-1], height=0.6)
            ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
            ax.set_xlabel("Cantidad de infracciones")
            ax.grid(axis="x")
            ax.spines[["top","right","left"]].set_visible(False)

            # Etiquetas en las barras
            for b, v in zip(barras, valores[::-1]):
                ax.text(b.get_width() + 0.1, b.get_y() + b.get_height() / 2,
                        str(v), va="center", color=TEXTO, fontsize=9)

        ax.set_title("Infracciones por trabajador", color=TEXTO,
                     fontsize=11, fontweight="bold", pad=10)
        self.fig_barras.tight_layout()
        self.canvas_barras.draw()

    # ──────────────────────────────────────────────────────
    #  GRÁFICA TORTA
    # ──────────────────────────────────────────────────────
    def _dibujar_torta(self):
        datos = infracciones_por_tipo()
        ax = self.ax_torta
        ax.clear()

        if not datos:
            ax.text(0.5, 0.5, "Sin datos", ha="center", va="center",
                    color=TEXTO2, fontsize=12, transform=ax.transAxes)
        else:
            etiquetas = [d[0] for d in datos]
            valores   = [d[1] for d in datos]
            colores   = COLORES_TORTA[:len(datos)]

            wedges, texts, autotexts = ax.pie(
                valores,
                labels=None,
                autopct="%1.0f%%",
                colors=colores,
                startangle=90,
                wedgeprops=dict(edgecolor=BG, linewidth=1.5),
                pctdistance=0.75,
            )
            for at in autotexts:
                at.set_color(BLANCO)
                at.set_fontsize(9)
                at.set_fontweight("bold")

            ax.legend(wedges, etiquetas,
                      loc="lower center",
                      bbox_to_anchor=(0.5, -0.22),
                      ncol=1, fontsize=8,
                      framealpha=0, labelcolor=TEXTO)

        ax.set_title("Por tipo de infracción", color=TEXTO,
                     fontsize=11, fontweight="bold", pad=10)
        self.fig_torta.tight_layout()
        self.canvas_torta.draw()

    # ──────────────────────────────────────────────────────
    #  GRÁFICA LÍNEA
    # ──────────────────────────────────────────────────────
    def _dibujar_linea(self):
        datos = infracciones_por_dia(14)
        ax = self.ax_linea
        ax.clear()

        if not datos:
            ax.text(0.5, 0.5, "Sin datos", ha="center", va="center",
                    color=TEXTO2, fontsize=12, transform=ax.transAxes)
        else:
            fechas  = [d[0][-5:] for d in datos]   # MM-DD
            valores = [d[1] for d in datos]

            ax.plot(fechas, valores, color=AZUL2, linewidth=2.5,
                    marker="o", markersize=7, markerfacecolor=BLANCO,
                    markeredgecolor=AZUL2, markeredgewidth=2)
            ax.fill_between(fechas, valores, alpha=0.15, color=AZUL2)

            # Etiquetas encima de cada punto
            for i, (f, v) in enumerate(zip(fechas, valores)):
                if v > 0:
                    ax.text(i, v + 0.15, str(v), ha="center",
                            color=TEXTO, fontsize=9)

            ax.set_xticks(range(len(fechas)))
            ax.set_xticklabels(fechas, rotation=35, ha="right", fontsize=8)
            ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
            ax.set_ylabel("Infracciones")
            ax.grid(axis="y")
            ax.spines[["top","right"]].set_visible(False)

        ax.set_title("Infracciones por día — últimas 2 semanas",
                     color=TEXTO, fontsize=11, fontweight="bold", pad=10)
        self.fig_linea.tight_layout()
        self.canvas_linea.draw()

    # ──────────────────────────────────────────────────────
    #  TABLA HISTORIAL
    # ──────────────────────────────────────────────────────
    def _cargar_historial(self):
        for item in self.tabla_hist.get_children():
            self.tabla_hist.delete(item)

        for fila in ultimas_infracciones(30):
            fecha, hora, tipo, trab, conf = fila
            conf_str = f"{conf:.0%}" if conf is not None else "—"
            self.tabla_hist.insert("", "end",
                                   values=(fecha, hora, tipo, trab, conf_str))


# ════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    root = tk.Tk()
    app  = Dashboard(root)
    root.mainloop()
