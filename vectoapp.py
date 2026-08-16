import os
import sys
import re
import uuid
import json
import base64
import subprocess
import tempfile
import gc
import cv2
import numpy as np
from PIL import Image
import shutil

# Vérification présence de Potrace
if shutil.which("potrace") is None:
    print("❌ Erreur : 'potrace' n'est pas installé ou introuvable dans le PATH système.")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
session_id = uuid.uuid4().hex[:8]

palette_hex_exacte = []

if len(sys.argv) >= 3:
    imgName = sys.argv[1]
    param_b64 = sys.argv[2].strip()
    try:
        json_str = base64.b64decode(param_b64).decode('utf-8')
        palette_hex_exacte = json.loads(json_str)
    except Exception as e:
        palette_hex_exacte = ["#000000", "#ffffff"]
else:
    sys.exit(1)

chemin_entree = os.path.join(BASE_DIR, "img", "toBeVectorized", imgName)
if not os.path.exists(chemin_entree):
    print(f"❌ Erreur : Le fichier '{chemin_entree}' n'existe pas.")
    sys.exit(1)

POTRACE_ALPHACORNER = 0.8
POTRACE_OPTTOLERANCE = 0.2
POTRACE_TURDSIZE = 4

# Chargement Image
image_brute = cv2.imread(chemin_entree, cv2.IMREAD_UNCHANGED)
if image_brute is None:
    print("❌ Erreur : Impossible de lire l'image avec OpenCV.")
    sys.exit(1)

h_orig, w_orig = image_brute.shape[:2]
FACTEUR_ECHELLE = 4
PADDING = 20 * FACTEUR_ECHELLE

if len(image_brute.shape) == 3 and image_brute.shape[2] == 4:
    b, g, r, alpha_brut = cv2.split(image_brute)
    img_bgr_brut = cv2.merge([b, g, r])
else:
    img_bgr_brut = image_brute
    alpha_brut = np.ones((h_orig, w_orig), dtype=np.uint8) * 255

nouvelle_largeur = w_orig * FACTEUR_ECHELLE
nouvelle_hauteur = h_orig * FACTEUR_ECHELLE

img_bgr_hd = cv2.resize(img_bgr_brut, (nouvelle_largeur, nouvelle_hauteur), interpolation=cv2.INTER_CUBIC)
alpha_hd = cv2.resize(alpha_brut, (nouvelle_largeur, nouvelle_hauteur), interpolation=cv2.INTER_CUBIC)
_, alpha_hd = cv2.threshold(alpha_hd, 127, 255, cv2.THRESH_BINARY)

img_bgr = cv2.copyMakeBorder(img_bgr_hd, PADDING, PADDING, PADDING, PADDING, cv2.BORDER_CONSTANT, value=[0, 0, 0])
alpha = cv2.copyMakeBorder(alpha_hd, PADDING, PADDING, PADDING, PADDING, cv2.BORDER_CONSTANT, value=0)
hauteur, largeur = img_bgr.shape[:2]

def hex_to_bgr(hex_str):
    hex_str = hex_str.lstrip('#')
    return [int(hex_str[4:6], 16), int(hex_str[2:4], 16), int(hex_str[0:2], 16)]

def lisser_masque(masque_brut):
    flou = cv2.GaussianBlur(masque_brut, (5, 5), 0)
    _, masque_lisse = cv2.threshold(flou, 127, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(masque_lisse, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    masque_vectoriel = np.zeros_like(masque_lisse)
    for cnt in contours:
        cnt_simplifie = cv2.approxPolyDP(cnt, 1.2, closed=True)
        cv2.drawContours(masque_vectoriel, [cnt_simplifie], -1, 255, thickness=cv2.FILLED)
    return masque_vectoriel

donnees_calques = []
couleurs_bgr = np.array([hex_to_bgr(h) for h in palette_hex_exacte], dtype=np.float32)
pixels_flat = img_bgr.reshape(-1, 3).astype(np.float32)

distances = np.linalg.norm(pixels_flat[:, np.newaxis] - couleurs_bgr, axis=2)
labels_matrice = np.argmin(distances, axis=1).reshape(hauteur, largeur)

for i, hex_code in enumerate(palette_hex_exacte):
    masque_brut = np.uint8((labels_matrice == i) & (alpha > 0)) * 255
    if np.count_nonzero(masque_brut) > 50:
        masque_propre = lisser_masque(masque_brut)
        donnees_calques.append({"hex": hex_code, "masque": masque_propre})

def masque_vers_path_svg(masque_binaire):
    with tempfile.NamedTemporaryFile(suffix=".pbm", delete=False) as tmp_pbm, \
         tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp_svg:
        chemin_pbm, chemin_svg = tmp_pbm.name, tmp_svg.name

    try:
        Image.fromarray(255 - masque_binaire).convert("1").save(chemin_pbm)
        cmd = [
            "potrace",
            "-s",
            "-o", chemin_svg,
            "-a", str(POTRACE_ALPHACORNER),
            "-O", str(POTRACE_OPTTOLERANCE),
            "-t", str(POTRACE_TURDSIZE),
            chemin_pbm,
        ]
        resultat = subprocess.run(cmd, capture_output=True, text=True)
        if resultat.returncode != 0:
            return None

        with open(chemin_svg, "r", encoding="utf-8") as f:
            contenu = f.read()

        paths = re.findall(r'<path[^>]*\sd="([^"]+)"', contenu)
        return " ".join(paths) if paths else None
    finally:
        if os.path.exists(chemin_pbm): os.remove(chemin_pbm)
        if os.path.exists(chemin_svg): os.remove(chemin_svg)

lignes_svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{largeur}" height="{hauteur}" viewBox="0 0 {largeur} {hauteur}">']

for calque in donnees_calques:
    d_path = masque_vers_path_svg(calque["masque"])
    if d_path:
        code_hex = calque["hex"]
        lignes_svg.append(
            f'  <g transform="translate(0,{hauteur}) scale(0.1,-0.1)">'
            f'<path d="{d_path}" fill="{code_hex}" fill-rule="evenodd" /></g>'
        )

lignes_svg.append("</svg>")

if os.path.exists(chemin_entree):
    try: os.remove(chemin_entree)
    except Exception: pass

gc.collect()
print("\n".join(lignes_svg))