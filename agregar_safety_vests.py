"""
==============================================================
  AGREGAR SAFETY VESTS AL DATASET FUSIONADO
==============================================================
  Toma el dataset Safety Vests y lo agrega al EPP_merged
  existente, creando EPP_merged_v2 listo para fine-tuning.

  Remapeo de clases:
    NO-Safety Vest (0) → no-vest  (3)
    Safety Vest    (1) → vest     (2)
==============================================================
"""

import os
import shutil

# ============================================================
#  RUTAS
# ============================================================
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))

ORIGEN_EPP    = r"C:\EPP_merged"
ORIGEN_VESTS  = r"C:\Users\USUARIO\Downloads\SafetyVests_temp"
DESTINO       = r"E:\EPP_merged_v2"

# Remapeo: clase original Safety Vests → clase en nuestro modelo
REMAP = {
    0: 3,   # NO-Safety Vest → no-vest
    1: 2,   # Safety Vest    → vest
}

# ============================================================

def copiar_con_prefijo(src_img, src_lbl, dst_img, dst_lbl,
                       prefijo="", remap=None):
    """Copia imágenes y labels de src a dst con prefijo opcional y remapeo."""
    os.makedirs(dst_img, exist_ok=True)
    os.makedirs(dst_lbl, exist_ok=True)

    imagenes = [f for f in os.listdir(src_img)
                if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    copiadas = 0

    for img_name in imagenes:
        nombre_base = os.path.splitext(img_name)[0]
        ext         = os.path.splitext(img_name)[1]
        lbl_name    = nombre_base + ".txt"

        src_img_path = os.path.join(src_img, img_name)
        src_lbl_path = os.path.join(src_lbl, lbl_name)

        dst_img_name = prefijo + img_name
        dst_lbl_name = prefijo + lbl_name

        dst_img_path = os.path.join(dst_img, dst_img_name)
        dst_lbl_path = os.path.join(dst_lbl, dst_lbl_name)

        # Copiar imagen
        try:
            shutil.copy2(src_img_path, dst_img_path)
        except Exception:
            continue

        # Copiar/remap label
        if os.path.exists(src_lbl_path) and remap:
            try:
                with open(src_lbl_path, "r") as f:
                    lineas = f.read().splitlines()
                nuevas = []
                for linea in lineas:
                    partes = linea.strip().split()
                    if not partes:
                        continue
                    cid = int(partes[0])
                    if cid in remap:
                        partes[0] = str(remap[cid])
                        nuevas.append(" ".join(partes))
                with open(dst_lbl_path, "w") as f:
                    f.write("\n".join(nuevas))
            except Exception:
                open(dst_lbl_path, "w").close()
        elif os.path.exists(src_lbl_path):
            shutil.copy2(src_lbl_path, dst_lbl_path)
        else:
            open(dst_lbl_path, "w").close()

        copiadas += 1
        if copiadas % 500 == 0:
            print(f"    ... {copiadas}/{len(imagenes)}")

    return copiadas


def main():
    print("=" * 60)
    print("  CREANDO EPP_merged_v2")
    print("=" * 60)

    # Limpiar destino anterior
    if os.path.exists(DESTINO):
        print(f"\nBorrando destino anterior: {DESTINO}")
        shutil.rmtree(DESTINO)

    totales = {"train": 0, "valid": 0, "test": 0}

    for split in ["train", "valid", "test"]:
        print(f"\n[{split}]")

        dst_img = os.path.join(DESTINO, split, "images")
        dst_lbl = os.path.join(DESTINO, split, "labels")

        # --- Copiar EPP_merged original (sin remap, labels ya correctos) ---
        src_img = os.path.join(ORIGEN_EPP, split, "images")
        src_lbl = os.path.join(ORIGEN_EPP, split, "labels")

        if os.path.exists(src_img):
            n = copiar_con_prefijo(src_img, src_lbl, dst_img, dst_lbl,
                                   prefijo="epp_", remap=None)
            print(f"  EPP_merged:     {n} imagenes")
            totales[split] += n

        # --- Copiar Safety Vests con remapeo ---
        src_img_v = os.path.join(ORIGEN_VESTS, split, "images")
        src_lbl_v = os.path.join(ORIGEN_VESTS, split, "labels")

        if not os.path.exists(src_img_v):
            # valid puede llamarse "valid" o "val"
            alt = split.replace("valid", "val")
            src_img_v = os.path.join(ORIGEN_VESTS, alt, "images")
            src_lbl_v = os.path.join(ORIGEN_VESTS, alt, "labels")

        if os.path.exists(src_img_v):
            n = copiar_con_prefijo(src_img_v, src_lbl_v, dst_img, dst_lbl,
                                   prefijo="sv_", remap=REMAP)
            print(f"  Safety Vests:   {n} imagenes")
            totales[split] += n

    # Crear data.yaml
    yaml_content = f"""train: {DESTINO}/train/images
val: {DESTINO}/valid/images
test: {DESTINO}/test/images

nc: 4
names: ['helmet', 'no-helmet', 'vest', 'no-vest']
"""
    yaml_path = os.path.join(DESTINO, "data.yaml")
    with open(yaml_path, "w") as f:
        f.write(yaml_content)

    print("\n" + "=" * 60)
    print("  FUSION COMPLETADA")
    print("=" * 60)
    for split, n in totales.items():
        lbl_count = len(os.listdir(os.path.join(DESTINO, split, "labels")))
        print(f"  {split:6}: {n:6} imagenes | {lbl_count:6} labels")
    print(f"\nDestino: {DESTINO}")
    print("Siguiente paso: comprimir y subir a Google Drive.")


if __name__ == "__main__":
    main()
