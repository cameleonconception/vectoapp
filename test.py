import os
import re
import uuid
import subprocess
import cv2
import numpy as np
from sklearn.cluster import KMeans
from PIL import Image

# ---------------------------------------------------------
# PARAMÈTRES GÉNÉRAUX & ID UNIQUE
# ---------------------------------------------------------
session_id = uuid.uuid4().hex[:8]

imgName = "logo.png"
chemin_entree = f"img/toBeVectorized/{imgName}"

dossier_sortie_png = f"img/calques_png/{session_id}"
dossier_sortie_svg = f"img/vectorized/{session_id}"
chemin_sortie_svg = os.path.join(dossier_sortie_svg, "logo_final.svg")

# 🚀 DEMANDE DU NOMBRE DE COULEURS À L'UTILISATEUR
print("--- CONFIGURATION DU TRAITEMENT ---")
saisie_utilisateur = input("Combien de couleurs comporte votre logo ? (ex: 4) : ")

try:
    NB_COULEURS_CLIENT = int(saisie_utilisateur)
    if NB_COULEURS_CLIENT < 1:
        print("⚠️ Nombre invalide. Valeur par défaut appliquée : 4 couleurs.")
        NB_COULEURS_CLIENT = 4
except ValueError:
    print("⚠️ Entrée non numérique. Valeur par défaut appliquée : 4 couleurs.")
    NB_COULEURS_CLIENT = 4

# Facteur d'échelle & réglages anti-bruit
FACTEUR_ECHELLE = 4                                 # Agrandissement 4x standard
TAILLE_GRAIN_MIN = 50 * (FACTEUR_ECHELLE ** 2)      # Filtre anti-bruit local (pixels²)
SURFACE_CALQUE_MIN = 300 * (FACTEUR_ECHELLE ** 2)  # Surface minimale globale (pixels²)
PADDING = 50 * FACTEUR_ECHELLE                      # Marge de sécurité (pixels)

# 🎯 PARAMÈTRES POTRACE
POTRACE_ALPHACORNER = 1.33
POTRACE_OPTTOLERANCE = 0.4
POTRACE_TURDSIZE = 10

os.makedirs(dossier_sortie_png, exist_ok=True)
os.makedirs(dossier_sortie_svg, exist_ok=True)

print(f"\n🔑 Session ID unique généré : {session_id}")

# ---------------------------------------------------------
# 1. CHARGEMENT, UPSCALING STANDARD ET PADDING
# ---------------------------------------------------------
image_brute = cv2.imread(chemin_entree, cv2.IMREAD_UNCHANGED)

if image_brute is None:
    print(f"Erreur : Impossible de charger l'image {chemin_entree}")
    exit()

# Séparation BGR et Alpha
if len(image_brute.shape) == 3 and image_brute.shape[2] == 4:
    b, g, r, alpha_brut = cv2.split(image_brute)
    img_bgr_brut = cv2.merge([b, g, r])
else:
    img_bgr_brut = image_brute
    h_init, w_init = image_brute.shape[:2]
    alpha_brut = np.ones((h_init, w_init), dtype=np.uint8) * 255

h_orig, w_orig = img_bgr_brut.shape[:2]

# Upscaling standard avec interpolation Lanczos
nouvelle_largeur = w_orig * FACTEUR_ECHELLE
nouvelle_hauteur = h_orig * FACTEUR_ECHELLE

img_bgr_4x = cv2.resize(img_bgr_brut, (nouvelle_largeur, nouvelle_hauteur), interpolation=cv2.INTER_LANCZOS4)
alpha_4x = cv2.resize(alpha_brut, (nouvelle_largeur, nouvelle_hauteur), interpolation=cv2.INTER_LANCZOS4)
_, alpha_4x = cv2.threshold(alpha_4x, 127, 255, cv2.THRESH_BINARY)

print(f"📈 Image agrandie (Lanczos) : {w_orig}x{h_orig} px ➡️ {nouvelle_largeur}x{nouvelle_hauteur} px")

# Ajout du padding de sécurité
img_bgr = cv2.copyMakeBorder(
    img_bgr_4x, PADDING, PADDING, PADDING, PADDING, cv2.BORDER_CONSTANT, value=[0, 0, 0]
)
alpha = cv2.copyMakeBorder(
    alpha_4x, PADDING, PADDING, PADDING, PADDING, cv2.BORDER_CONSTANT, value=0
)

hauteur, largeur = img_bgr.shape[:2]
masque_visible = alpha > 0
pixels_visibles = img_bgr[masque_visible]

# --- 💡 CLUSTERING SELON LE NOMBRE DE COULEURS DEMANDÉ ---
NB_COULEURS = NB_COULEURS_CLIENT
print(f"🎯 Traitement configuré pour exactement {NB_COULEURS} couleur(s).")

# Clustering K-Means
kmeans = KMeans(n_clusters=NB_COULEURS, random_state=42, n_init=10).fit(pixels_visibles)
couleurs = np.uint8(kmeans.cluster_centers_)

pixels_tous = img_bgr.reshape(-1, 3)
labels_tous = kmeans.predict(pixels_tous)
labels_matrice = labels_tous.reshape(hauteur, largeur)

# ---------------------------------------------------------
# 2. GÉNÉRATION ET FILTRAGE DES CALQUES PNG
# ---------------------------------------------------------
print("\n📸 ÉTAPE 1 : Génération et filtrage des calques PNG...")

kernel_fermeture = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
kernel_dilatation = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

for i in range(NB_COULEURS):
    couleur_b, couleur_g, couleur_r = couleurs[i]

    # Ignorer le fond blanc / quasi-blanc
    if couleur_r > 245 and couleur_g > 245 and couleur_b > 245:
        continue

    masque_brut = np.uint8((labels_matrice == i) & (alpha > 0)) * 255

    masque_propre = cv2.morphologyEx(masque_brut, cv2.MORPH_CLOSE, kernel_fermeture)
    masque_flou = cv2.GaussianBlur(masque_propre, (5, 5), 0)
    _, masque_lisse = cv2.threshold(masque_flou, 127, 255, cv2.THRESH_BINARY)
    masque_dilate = cv2.dilate(masque_lisse, kernel_dilatation, iterations=1)

    # Filtrage des isolats de bruit (placé après dilatation)
    nb_labels, labels_obj, stats, _ = cv2.connectedComponentsWithStats(masque_dilate)
    masque_final = np.zeros_like(masque_dilate)

    for obj_i in range(1, nb_labels):
        if stats[obj_i, cv2.CC_STAT_AREA] >= TAILLE_GRAIN_MIN:
            masque_final[labels_obj == obj_i] = 255

    surface_reelle = np.count_nonzero(masque_final)

    if surface_reelle < SURFACE_CALQUE_MIN:
        print(f"  └─ ⚠️ Calque {i+1} ignoré (surface trop faible: {surface_reelle}px²).")
        continue

    calque_png = np.zeros((hauteur, largeur, 4), dtype=np.uint8)
    pixels_valides = masque_final > 0
    calque_png[pixels_valides, 0:3] = img_bgr[pixels_valides]
    calque_png[pixels_valides, 3] = 255

    code_hex = f"{couleur_r:02x}{couleur_g:02x}{couleur_b:02x}"
    chemin_sauvegarde = os.path.join(dossier_sortie_png, f"calque_{i+1}_#{code_hex}.png")

    cv2.imwrite(chemin_sauvegarde, calque_png)
    print(f"  └─ Calque {i+1} enregistré : '{chemin_sauvegarde}' (Surface: {surface_reelle}px²)")

# ---------------------------------------------------------
# 3. TRI PAR SURFACE
# ---------------------------------------------------------
print("\n🧹 ÉTAPE 2 : Tri des calques...")

fichiers_png = [f for f in os.listdir(dossier_sortie_png) if f.endswith(".png") and "#" in f]
donnees_calques = []

for fichier in fichiers_png:
    chemin_calque = os.path.join(dossier_sortie_png, fichier)
    calque_img = cv2.imread(chemin_calque, cv2.IMREAD_UNCHANGED)

    if calque_img is None or calque_img.shape[2] < 4:
        continue

    alpha_calque = calque_img[:, :, 3]
    masque_binaire = np.uint8(alpha_calque > 0) * 255

    donnees_calques.append({
        "fichier": fichier,
        "hex": "#" + fichier.split("#")[1].split(".")[0],
        "surface": np.count_nonzero(masque_binaire),
        "masque": masque_binaire,
    })

donnees_calques.sort(key=lambda x: x["surface"], reverse=True)

# ---------------------------------------------------------
# 4. VECTORISATION
# ---------------------------------------------------------
print("\n🖊️ ÉTAPE 3 : Vectorisation Potrace...")

def masque_vers_path_svg_hd(masque_binaire, dossier_tmp):
    tmp_id = uuid.uuid4().hex[:6]
    chemin_pbm = os.path.join(dossier_tmp, f"_tmp_{tmp_id}.pbm")
    chemin_svg = os.path.join(dossier_tmp, f"_tmp_{tmp_id}.svg")

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
        if os.path.exists(chemin_pbm): os.remove(chemin_pbm)
        return None

    with open(chemin_svg, "r") as f:
        contenu = f.read()

    correspondances = re.findall(r'<path[^>]*\sd="([^"]+)"', contenu)

    if os.path.exists(chemin_pbm): os.remove(chemin_pbm)
    if os.path.exists(chemin_svg): os.remove(chemin_svg)

    return " ".join(correspondances) if correspondances else None


lignes_svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{largeur}" height="{hauteur}" viewBox="0 0 {largeur} {hauteur}">'
]

for calque in donnees_calques:
    fichier = calque["fichier"]
    code_hex = calque["hex"]
    masque_binaire = calque["masque"]

    d_path = masque_vers_path_svg_hd(masque_binaire, dossier_sortie_png)

    if d_path is None:
        continue

    lignes_svg.append(
        f'  <g transform="translate(0,{hauteur}) scale(0.1,-0.1)">'
        f'<path d="{d_path}" fill="{code_hex}" fill-rule="evenodd" '
        f'stroke="{code_hex}" stroke-width="0.5" stroke-linejoin="round" stroke-linecap="round" /></g>'
    )
    print(f"  └─ ✅ Vectorisé : '{fichier}'")

lignes_svg.append("</svg>")

# ---------------------------------------------------------
# 5. SAUVEGARDE
# ---------------------------------------------------------
with open(chemin_sortie_svg, "w") as f:
    f.write("\n".join(lignes_svg))

print(f"\n🎉 Vectorisation finale terminée avec succès !")
print(f" 📄 SVG disponible ici : {chemin_sortie_svg}")