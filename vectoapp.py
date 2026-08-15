import os
import sys
import re
import uuid
import subprocess
import tempfile
import gc
import cv2
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from PIL import Image

# =========================================================
# 1. FIXATION DU DOSSIER DE TRAVAIL ABSOLU
# =========================================================
# Garantit que le script s'exécute toujours depuis son propre dossier,
# qu'il soit lancé par le terminal ou par un serveur Web (PHP).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

session_id = uuid.uuid4().hex[:8]

# =========================================================
# 2. RÉCUPÉRATION DES ARGUMENTS (PHP OU TERMINAL)
# =========================================================
if len(sys.argv) >= 3:
    imgName = sys.argv[1]
    try:
        NB_COULEURS_CLIENT = int(sys.argv[2])
    except ValueError:
        NB_COULEURS_CLIENT = 4
else:
    # Mode secours si le script est lancé manuellement dans le terminal
    imgName = input("Entrez le nom du fichier à vectoriser (ex: logo.png) : ").strip()
    saisie_couleurs = input("Combien de couleurs comporte votre logo ? (ex: 4) : ").strip()
    try:
        NB_COULEURS_CLIENT = int(saisie_couleurs)
    except ValueError:
        NB_COULEURS_CLIENT = 4

if NB_COULEURS_CLIENT < 1:
    NB_COULEURS_CLIENT = 4

chemin_entree = os.path.join(BASE_DIR, "img", "toBeVectorized", imgName)

if not os.path.exists(chemin_entree):
    print(f"❌ Erreur : Le fichier '{chemin_entree}' n'existe pas.")
    sys.exit(1)

dossier_sortie_png = os.path.join(BASE_DIR, "img", "calques_png", session_id)
dossier_sortie_svg = os.path.join(BASE_DIR, "img", "vectorized", session_id)
chemin_sortie_svg = os.path.join(dossier_sortie_svg, f"{os.path.splitext(imgName)[0]}_vectorise.svg")

# Paramètres globaux de Potrace
POTRACE_ALPHACORNER = 1.33
POTRACE_OPTTOLERANCE = 0.4
POTRACE_TURDSIZE = 10

os.makedirs(dossier_sortie_png, exist_ok=True)
os.makedirs(dossier_sortie_svg, exist_ok=True)

# =========================================================
# 3. CHARGEMENT ET FACTEUR D'ÉCHELLE DYNAMIQUE
# =========================================================
image_brute = cv2.imread(chemin_entree, cv2.IMREAD_UNCHANGED)

if image_brute is None:
    print(f"Erreur : Impossible de charger l'image {chemin_entree}")
    sys.exit(1)

# Extraction des dimensions initiales
h_orig, w_orig = image_brute.shape[:2]
dimension_max = max(h_orig, w_orig)

# Calcul du facteur d'échelle dynamique pour accélérer le traitement
if dimension_max < 500:
    FACTEUR_ECHELLE = 4
elif dimension_max < 1200:
    FACTEUR_ECHELLE = 2
else:
    FACTEUR_ECHELLE = 1

# Ajustement automatique des seuils d'anti-bruit
TAILLE_GRAIN_MIN = 80 * (FACTEUR_ECHELLE ** 2)      # Taille minimale d'un élément (px²)
SURFACE_CALQUE_MIN = 300 * (FACTEUR_ECHELLE ** 2)  # Surface minimale d'un calque (px²)
PADDING = 50 * FACTEUR_ECHELLE                      # Marge de sécurité (px)

# Séparation des canaux BGR et Alpha (transparence)
if len(image_brute.shape) == 3 and image_brute.shape[2] == 4:
    b, g, r, alpha_brut = cv2.split(image_brute)
    img_bgr_brut = cv2.merge([b, g, r])
else:
    img_bgr_brut = image_brute
    alpha_brut = np.ones((h_orig, w_orig), dtype=np.uint8) * 255

# Redimensionnement (Upscaling)
nouvelle_largeur = w_orig * FACTEUR_ECHELLE
nouvelle_hauteur = h_orig * FACTEUR_ECHELLE

if FACTEUR_ECHELLE > 1:
    img_bgr_4x = cv2.resize(img_bgr_brut, (nouvelle_largeur, nouvelle_hauteur), interpolation=cv2.INTER_LANCZOS4)
    alpha_4x = cv2.resize(alpha_brut, (nouvelle_largeur, nouvelle_hauteur), interpolation=cv2.INTER_LANCZOS4)
else:
    img_bgr_4x = img_bgr_brut.copy()
    alpha_4x = alpha_brut.copy()

_, alpha_4x = cv2.threshold(alpha_4x, 127, 255, cv2.THRESH_BINARY)

# =========================================================
# 4. ROGNAGE AUTOMATIQUE (CROP) ET MARGE DE SÉCURITÉ
# =========================================================
ys, xs = np.where(alpha_4x > 0)
if len(ys) > 0 and len(xs) > 0:
    min_y, max_y = np.min(ys), np.max(ys)
    min_x, max_x = np.min(xs), np.max(xs)
    img_bgr_4x = img_bgr_4x[min_y:max_y+1, min_x:max_x+1]
    alpha_4x = alpha_4x[min_y:max_y+1, min_x:max_x+1]

# Isolation des zones transparentes par une couleur neutre (Magenta ou Jaune)
masque_transparent = alpha_4x == 0
couleur_fond = np.array([255, 0, 255], dtype=np.uint8)

if np.any(masque_transparent):
    pixels_utilises = img_bgr_4x[alpha_4x > 0]
    if len(pixels_utilises) > 0 and np.any(np.all(pixels_utilises == couleur_fond, axis=1)):
        couleur_fond = np.array([0, 255, 255], dtype=np.uint8)
    img_bgr_4x[masque_transparent] = couleur_fond

couleur_padding = couleur_fond.tolist() if np.any(masque_transparent) else [0, 0, 0]

# Ajout du Padding
img_bgr = cv2.copyMakeBorder(img_bgr_4x, PADDING, PADDING, PADDING, PADDING, cv2.BORDER_CONSTANT, value=couleur_padding)
alpha = cv2.copyMakeBorder(alpha_4x, PADDING, PADDING, PADDING, PADDING, cv2.BORDER_CONSTANT, value=0)

hauteur, largeur = img_bgr.shape[:2]

# =========================================================
# 5. PRÉ-TRAITEMENT ET CLUSTERING DES COULEURS
# =========================================================
# Lissage pour éliminer les artefacts d'anti-aliasing aux bordures
img_lisse = cv2.medianBlur(img_bgr, 9)
img_lisse = cv2.bilateralFilter(img_lisse, d=11, sigmaColor=80, sigmaSpace=80)

masque_visible = alpha > 0
pixels_visibles = img_lisse[masque_visible]

# Échantillonnage pour accélérer MiniBatchKMeans
pixels_echantillon = pixels_visibles[::5]

kmeans = MiniBatchKMeans(
    n_clusters=NB_COULEURS_CLIENT, 
    random_state=42, 
    batch_size=2048, 
    n_init=3
).fit(pixels_echantillon)

couleurs = np.uint8(kmeans.cluster_centers_)

pixels_tous = img_lisse.reshape(-1, 3)
labels_tous = kmeans.predict(pixels_tous)
labels_matrice = labels_tous.reshape(hauteur, largeur)

# =========================================================
# 6. FILTRAGE MORPHOLOGIQUE DES CALQUES PNG
# =========================================================
taille_noyau_ouverture = 2 * FACTEUR_ECHELLE + 1
kernel_ouverture = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (taille_noyau_ouverture, taille_noyau_ouverture))
kernel_fermeture = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

donnees_calques = []

for i in range(NB_COULEURS_CLIENT):
    couleur_b, couleur_g, couleur_r = couleurs[i]
    masque_brut = np.uint8((labels_matrice == i) & (alpha > 0)) * 255

    # Nettoyage des contours
    masque_sans_lignes = cv2.morphologyEx(masque_brut, cv2.MORPH_OPEN, kernel_ouverture)
    masque_propre = cv2.morphologyEx(masque_sans_lignes, cv2.MORPH_CLOSE, kernel_fermeture)

    # Filtrage des petites imperfections
    nb_labels, labels_obj, stats, _ = cv2.connectedComponentsWithStats(masque_propre)
    masque_final = np.zeros_like(masque_propre)

    for obj_i in range(1, nb_labels):
        if stats[obj_i, cv2.CC_STAT_AREA] >= TAILLE_GRAIN_MIN:
            masque_final[labels_obj == obj_i] = 255

    surface_reelle = np.count_nonzero(masque_final)

    if surface_reelle < SURFACE_CALQUE_MIN:
        continue

    code_hex = f"#{couleur_r:02x}{couleur_g:02x}{couleur_b:02x}"
    donnees_calques.append({
        "hex": code_hex,
        "surface": surface_reelle,
        "masque": masque_final
    })

donnees_calques.sort(key=lambda x: x["surface"], reverse=True)

# =========================================================
# 7. VECTORISATION VIA POTRACE
# =========================================================
def masque_vers_path_svg_hd(masque_binaire):
    """
    Convertit un masque binaire en tracé SVG à l'aide de Potrace.
    Utilise des fichiers temporaires système sécurisés.
    """
    with tempfile.NamedTemporaryFile(suffix=".pbm", delete=False) as tmp_pbm, \
         tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp_svg:
        
        chemin_pbm = tmp_pbm.name
        chemin_svg = tmp_svg.name

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

        correspondances = re.findall(r'<path[^>]*\sd="([^"]+)"', contenu)
        return " ".join(correspondances) if correspondances else None

    finally:
        # Supprime toujours les fichiers temporaires après utilisation
        if os.path.exists(chemin_pbm): os.remove(chemin_pbm)
        if os.path.exists(chemin_svg): os.remove(chemin_svg)


lignes_svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{largeur}" height="{hauteur}" viewBox="0 0 {largeur} {hauteur}">'
]

for calque in donnees_calques:
    d_path = masque_vers_path_svg_hd(calque["masque"])
    if d_path:
        code_hex = calque["hex"]
        lignes_svg.append(
            f'  <g transform="translate(0,{hauteur}) scale(0.1,-0.1)">'
            f'<path d="{d_path}" fill="{code_hex}" fill-rule="evenodd" '
            f'stroke="{code_hex}" stroke-width="0.5" stroke-linejoin="round" stroke-linecap="round" /></g>'
        )

lignes_svg.append("</svg>")

# =========================================================
# 8. SAUVEGARDE ET NETTOYAGE MÉMOIRE
# =========================================================
with open(chemin_sortie_svg, "w", encoding="utf-8") as f:
    f.write("\n".join(lignes_svg))

# Libération explicite de la mémoire
gc.collect()

# Seule cette ligne est imprimée sur stdout pour que PHP la récupère
print(chemin_sortie_svg)