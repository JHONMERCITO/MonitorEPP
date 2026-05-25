#!/usr/bin/env python3
"""
==============================================================
  GESTOR DE TRABAJADORES — Monitor EPP
==============================================================
  Registra, visualiza y elimina trabajadores.
  Identificacion por numero en casco/chaleco (OCR).
==============================================================
"""

import os
import sys
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk


def _dir_base() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


DB_PATH = os.path.join(_dir_base(), "monitor_epp.db")


def inicializar_db() -> None:
    conn = sqlite3.connect(DB_PATH)

    # Migracion: si la tabla tiene foto_path (esquema viejo), recrearla limpia
    try:
        cols = [c[1] for c in conn.execute("PRAGMA table_info(trabajadores)").fetchall()]
        if "foto_path" in cols:
            print("[DB] Migrando tabla trabajadores al nuevo esquema...")
            conn.execute("""
                CREATE TABLE trabajadores_nuevo (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre         TEXT    NOT NULL,
                    numero         TEXT    NOT NULL DEFAULT '',
                    activo         INTEGER DEFAULT 1,
                    fecha_registro TEXT    DEFAULT (datetime('now','localtime'))
                )
            """)
            if "numero" in cols:
                conn.execute("""
                    INSERT INTO trabajadores_nuevo (id, nombre, numero, activo, fecha_registro)
                    SELECT id, nombre, COALESCE(numero,''), activo, fecha_registro
                    FROM trabajadores
                """)
            else:
                conn.execute("""
                    INSERT INTO trabajadores_nuevo (id, nombre, activo, fecha_registro)
                    SELECT id, nombre, activo, fecha_registro FROM trabajadores
                """)
            conn.execute("DROP TABLE trabajadores")
            conn.execute("ALTER TABLE trabajadores_nuevo RENAME TO trabajadores")
            conn.commit()
            print("[DB] Migracion completada.")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS trabajadores (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre         TEXT    NOT NULL,
            numero         TEXT    NOT NULL DEFAULT '',
            activo         INTEGER DEFAULT 1,
            fecha_registro TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS infracciones (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha             TEXT NOT NULL,
            hora              TEXT NOT NULL,
            tipo              TEXT NOT NULL,
            imagen_path       TEXT,
            trabajador_nombre TEXT DEFAULT 'Desconocido',
            confianza_ocr     REAL,
            fecha_registro    TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    try:
        conn.execute("ALTER TABLE trabajadores ADD COLUMN numero TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    conn.commit()
    conn.close()


# ============================================================
#  INTERFAZ PRINCIPAL
# ============================================================

class GestorTrabajadores:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Monitor EPP — Gestión de Trabajadores")
        self.root.geometry("720x480")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e1e")

        self._construir_ui()
        self._cargar_tabla_trabajadores()
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    # ----------------------------------------------------------
    def _construir_ui(self) -> None:
        # Encabezado
        tk.Label(self.root, text="  Gestión de Trabajadores — Monitor EPP",
                 bg="#0078d4", fg="white", font=("Segoe UI", 13, "bold"),
                 anchor="w").pack(fill="x", ipady=8)

        contenido = tk.Frame(self.root, bg="#1e1e1e")
        contenido.pack(fill="both", expand=True, padx=10, pady=10)

        # ---- Panel izquierdo: lista ----
        panel_izq = tk.Frame(contenido, bg="#2d2d2d")
        panel_izq.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(panel_izq, text="Trabajadores registrados",
                 bg="#2d2d2d", fg="#cccccc",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 4))

        frame_tree = tk.Frame(panel_izq, bg="#2d2d2d")
        frame_tree.pack(fill="both", expand=True, padx=10)

        self.tabla = ttk.Treeview(
            frame_tree,
            columns=("numero", "nombre", "fecha"),
            show="headings",
            height=14,
        )
        self.tabla.heading("numero", text="N°")
        self.tabla.heading("nombre", text="Nombre")
        self.tabla.heading("fecha",  text="Registrado")
        self.tabla.column("numero", width=50,  anchor="center")
        self.tabla.column("nombre", width=200)
        self.tabla.column("fecha",  width=130)

        scroll = ttk.Scrollbar(frame_tree, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        frame_btns = tk.Frame(panel_izq, bg="#2d2d2d")
        frame_btns.pack(pady=8)

        tk.Button(frame_btns, text="Ver infracciones",
                  command=self._ver_infracciones,
                  bg="#444", fg="white", font=("Segoe UI", 9),
                  relief="flat", padx=8, cursor="hand2"
                  ).pack(side="left", padx=4)

        tk.Button(frame_btns, text="Eliminar trabajador",
                  command=self._eliminar_trabajador,
                  bg="#c0392b", fg="white", font=("Segoe UI", 9),
                  relief="flat", padx=8, cursor="hand2"
                  ).pack(side="left", padx=4)

        # ---- Panel derecho: agregar ----
        panel_der = tk.Frame(contenido, bg="#2d2d2d", width=240)
        panel_der.pack(side="right", fill="y", padx=(6, 0))
        panel_der.pack_propagate(False)

        tk.Label(panel_der, text="Agregar trabajador",
                 bg="#2d2d2d", fg="#cccccc",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(14, 6))

        tk.Label(panel_der, text="Nombre completo:",
                 bg="#2d2d2d", fg="#aaaaaa",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=14)

        self.var_nombre = tk.StringVar()
        tk.Entry(panel_der, textvariable=self.var_nombre, width=26,
                 font=("Segoe UI", 10), bg="#3d3d3d", fg="white",
                 insertbackground="white", relief="flat", bd=5,
                 ).pack(padx=14, pady=(2, 14))

        tk.Label(panel_der, text="Número en casco/chaleco:",
                 bg="#2d2d2d", fg="#aaaaaa",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=14)

        tk.Label(panel_der, text="(ej: 01, 02, 03...)",
                 bg="#2d2d2d", fg="#666666",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=14)

        self.var_numero = tk.StringVar()
        tk.Entry(panel_der, textvariable=self.var_numero, width=8,
                 font=("Segoe UI", 18, "bold"), bg="#3d3d3d", fg="#f0c040",
                 insertbackground="white", relief="flat", bd=5, justify="center",
                 ).pack(anchor="w", padx=14, pady=(4, 20))

        tk.Label(panel_der,
                 text="El numero debe estar escrito\ngrande y visible en el\ncasco o chaleco fisico.",
                 bg="#2d2d2d", fg="#666666",
                 font=("Segoe UI", 8), justify="left"
                 ).pack(anchor="w", padx=14, pady=(0, 16))

        tk.Button(panel_der, text="Registrar trabajador",
                  command=self._registrar_trabajador,
                  bg="#27ae60", fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=10, cursor="hand2"
                  ).pack(padx=14, pady=4, fill="x")

    # ----------------------------------------------------------
    #  CRUD
    # ----------------------------------------------------------

    def _registrar_trabajador(self) -> None:
        try:
            nombre = self.var_nombre.get().strip()
            numero = self.var_numero.get().strip()

            if not nombre:
                messagebox.showerror("Error", "Ingresa el nombre del trabajador.",
                                     parent=self.root)
                return
            if not numero or not numero.isdigit():
                messagebox.showerror("Error", "Ingresa un número válido (solo dígitos, ej: 01).",
                                     parent=self.root)
                return

            conn = sqlite3.connect(DB_PATH)
            existe = conn.execute(
                "SELECT nombre FROM trabajadores WHERE numero=? AND activo=1", (numero,)
            ).fetchone()
            if existe:
                conn.close()
                messagebox.showerror("Error",
                                     f"El número {numero} ya está asignado a '{existe[0]}'.",
                                     parent=self.root)
                return

            conn.execute(
                "INSERT INTO trabajadores (nombre, numero) VALUES (?, ?)",
                (nombre, numero),
            )
            conn.commit()
            conn.close()

            messagebox.showinfo("Registrado",
                                f"'{nombre}' registrado con el número {numero}.\n\n"
                                f"Recordá colocar el número '{numero}' bien visible\n"
                                f"en el casco o chaleco del trabajador.",
                                parent=self.root)
            self.var_nombre.set("")
            self.var_numero.set("")
            self._cargar_tabla_trabajadores()

        except Exception as e:
            messagebox.showerror("Error inesperado", str(e), parent=self.root)
            print(f"[ERROR] _registrar_trabajador: {e}")

    def _eliminar_trabajador(self) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Selección", "Selecciona un trabajador de la lista.",
                                   parent=self.root)
            return

        valores = self.tabla.item(seleccion[0])["values"]
        numero  = str(valores[0])
        nombre  = str(valores[1])

        if not messagebox.askyesno("Confirmar", f"¿Eliminar a '{nombre}' (N°{numero})?",
                                   parent=self.root):
            return

        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "UPDATE trabajadores SET activo=0 WHERE nombre=? AND activo=1", (nombre,)
            )
            conn.commit()
            conn.close()
            self._cargar_tabla_trabajadores()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.root)
            print(f"[ERROR] _eliminar_trabajador: {e}")

    def _cargar_tabla_trabajadores(self) -> None:
        for item in self.tabla.get_children():
            self.tabla.delete(item)

        conn  = sqlite3.connect(DB_PATH)
        filas = conn.execute(
            "SELECT numero, nombre, fecha_registro FROM trabajadores "
            "WHERE activo=1 ORDER BY CAST(numero AS INTEGER)"
        ).fetchall()
        conn.close()

        for numero, nombre, fecha in filas:
            fecha_corta = fecha[:16] if fecha else ""
            self.tabla.insert("", "end", values=(numero, nombre, fecha_corta))

    # ----------------------------------------------------------
    #  VER INFRACCIONES
    # ----------------------------------------------------------

    def _ver_infracciones(self) -> None:
        ventana = tk.Toplevel(self.root)
        ventana.title("Historial de infracciones")
        ventana.geometry("860x420")
        ventana.configure(bg="#1e1e1e")

        tk.Label(ventana, text="  Historial de infracciones",
                 bg="#0078d4", fg="white", font=("Segoe UI", 11, "bold"),
                 anchor="w").pack(fill="x", ipady=6)

        frame_tree = tk.Frame(ventana, bg="#1e1e1e")
        frame_tree.pack(fill="both", expand=True, padx=10, pady=10)

        cols = ("fecha", "hora", "tipo", "trabajador", "confianza", "imagen")
        tabla = ttk.Treeview(frame_tree, columns=cols, show="headings", height=16)
        tabla.heading("fecha",      text="Fecha")
        tabla.heading("hora",       text="Hora")
        tabla.heading("tipo",       text="Tipo de infracción")
        tabla.heading("trabajador", text="Trabajador")
        tabla.heading("confianza",  text="Confianza OCR")
        tabla.heading("imagen",     text="Imagen")
        tabla.column("fecha",      width=90)
        tabla.column("hora",       width=75)
        tabla.column("tipo",       width=165)
        tabla.column("trabajador", width=160)
        tabla.column("confianza",  width=100)
        tabla.column("imagen",     width=220)

        scroll = ttk.Scrollbar(frame_tree, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=scroll.set)
        tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        conn  = sqlite3.connect(DB_PATH)
        filas = conn.execute(
            "SELECT fecha, hora, tipo, trabajador_nombre, confianza_ocr, imagen_path "
            "FROM infracciones ORDER BY id DESC LIMIT 200"
        ).fetchall()
        conn.close()

        for fila in filas:
            fecha, hora, tipo, trab, conf, img = fila
            conf_str = f"{conf:.0%}" if conf is not None else "—"
            tabla.insert("", "end", values=(fecha, hora, tipo, trab, conf_str, img or ""))


# ============================================================
#  PUNTO DE ENTRADA
# ============================================================

if __name__ == "__main__":
    inicializar_db()
    root = tk.Tk()
    app  = GestorTrabajadores(root)
    root.mainloop()
