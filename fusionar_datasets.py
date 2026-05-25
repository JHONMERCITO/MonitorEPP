"""
Fusiona construction-safety-monitor (11 clases) con Hard Hats (2 clases).
Remapea:  Hardhat(0) -> helmet(3)   |   NO-Hardhat(1) -> no-helmet(7)
Resultado: C:/EPP_merged/  lista para comprimir y subir a Colab.
"""

import os
import shutil

# Prefijo \\?\ para saltear el limite MAX_PATH de Windows (260 chars)
def wp(path: str) -> str:
    p = os.path.abspath(path)
    if not p.startswith("\\\\?\\"):
        p = "\\\\?\\" + p
    return p

# ============================================================
#  RUTAS
# ============================================================
BASE              = os.path.dirname(os.path.abspath(__file__))
DATASET_PRINCIPAL = os.path.join(BASE, "construction-safety-monitor.v2-v2-ppe-5170img-11cls-640px.yolov8")
DATASET_CASCOS    = os.path.join(BASE, "Hard Hats.v1-raw-images.yolov8")
DESTINO           = "C:\\EPP_merged"

MAPEO_CLASES = {0: 3, 1: 7}   # Hardhat->helmet, NO-Hardhat->no-helmet
SPLITS = ["train", "valid", "test"]

# ============================================================
#  FUNCIONES
# ============================================================

def copiar_split(origen: str, destino: str, prefijo: str, remap: dict = None):
    for split in SPLITS:
        img_src = os.path.join(origen, split, "images")
        lbl_src = os.path.join(origen, split, "labels")
        img_dst = os.path.join(destino, split, "images")
        lbl_dst = os.path.join(destino, split, "labels")

        os.makedirs(wp(img_dst), exist_ok=True)
        os.makedirs(wp(lbl_dst), exist_ok=True)

        if not os.path.exists(wp(img_src)):
            print(f"  [SKIP] {img_src} no existe")
            continue

        archivos = [f for f in os.listdir(wp(img_src))
                    if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        print(f"  {split}: {len(archivos)} imágenes desde {os.path.basename(origen)}")

        for i, nombre_img in enumerate(archivos):
            src_img = os.path.join(img_src, nombre_img)
            dst_img = os.path.join(img_dst, prefijo + nombre_img)
            shutil.copy2(wp(src_img), wp(dst_img))

            stem = os.path.splitext(nombre_img)[0]
            src_lbl = os.path.join(lbl_src, stem + ".txt")
            dst_lbl = os.path.join(lbl_dst, prefijo + stem + ".txt")

            if os.path.exists(wp(src_lbl)):
                if remap:
                    with open(wp(src_lbl), "r") as f:
                        lineas = f.read().splitlines()
                    lines_out = []
                    for linea in lineas:
                        partes = linea.strip().split()
                        if not partes:
                            continue
                        cls_id = int(partes[0])
                        cls_id = remap.get(cls_id, cls_id)
                        lines_out.append(f"{cls_id} {' '.join(partes[1:])}")
                    with open(wp(dst_lbl), "w") as f:
                        f.write("\n".join(lines_out))
                else:
                    shutil.copy2(wp(src_lbl), wp(dst_lbl))
            else:
                open(wp(dst_lbl), "w").close()

            if (i + 1) % 1000 == 0:
                print(f"    ... {i+1}/{len(archivos)}")

# ============================================================
#  MAIN
# ============================================================

if os.path.exists(DESTINO):
    print(f"Borrando destino anterior: {DESTINO}")
    shutil.rmtree(wp(DESTINO))
os.makedirs(wp(DESTINO))

print("\n[1/2] Copiando dataset principal (construction-safety-monitor)...")
copiar_split(DATASET_PRINCIPAL, DESTINO, prefijo="csm_", remap=None)

print("\n[2/2] Copiando Hard Hats con remapeo de clases...")
copiar_split(DATASET_CASCOS, DESTINO, prefijo="hh_", remap=MAPEO_CLASES)

# ============================================================
#  data.yaml
# ============================================================
yaml_content = """\
train: ./train/images
val:   ./valid/images
test:  ./test/images

nc: 11
names: ['boots', 'gloves', 'goggles', 'helmet', 'no-boots',
        'no-gloves', 'no-goggles', 'no-helmet', 'no-vest', 'person', 'vest']
"""
with open(wp(os.path.join(DESTINO, "data.yaml")), "w") as f:
    f.write(yaml_content)

# ============================================================
#  Resumen
# ============================================================
print("\n=== FUSION COMPLETADA ===")
for split in SPLITS:
    n_img = len([f for f in os.listdir(wp(os.path.join(DESTINO, split, "images")))
                 if f.lower().endswith(('.jpg','.jpeg','.png'))])
    n_lbl = len([f for f in os.listdir(wp(os.path.join(DESTINO, split, "labels")))
                 if f.endswith('.txt')])
    print(f"  {split:5s}: {n_img:6d} imágenes  |  {n_lbl:6d} labels")

print(f"\nDestino: {DESTINO}")
print("Siguiente paso: comprimir C:\\EPP_merged y subir a Google Drive.")
