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

NB_COULEURS = 6
TAILLE_GRAIN_MIN = 30  # Filtre anti-bruit (en pixels²)

# 🎯 PARAMÈTRES POTRACE AJUSTÉS POUR CORRIGER LES POINTES
POTRACE_ALPHACORNER = 1.33  # > 1.0 = Force des courbes ultra-lisses et élimine les angles inutiles
POTRACE_OPTTOLERANCE = 0.4  # Tolérance accrue pour fusionner les segments hachés
POTRACE_TURDSIZE = 5        # Élimine davantage le micro-bruit de bordure

os.makedirs(dossier_sortie_png, exist_ok=True)
os.makedirs(dossier_sortie_svg, exist_ok=True)

print(f"🔑 Session ID unique généré : {session_id}")

# ---------------------------------------------------------
# 1. CHARGEMENT ET DÉCOUPAGE EN CALQUES PNG
# ---------------------------------------------------------
image = cv2.imread(chemin_entree, cv2.IMREAD_UNCHANGED)

if image is None:
    print(f"Erreur : Impossible de charger l'image {chemin_entree}")
    exit()

hauteur, largeur = image.shape[:2]

if len(image.shape) == 3 and image.shape[2] == 4:
    b, g, r, alpha = cv2.split(image)
    img_bgr = cv2.merge([b, g, r])
else:
    img_bgr = image
    alpha = np.ones((hauteur, largeur), dtype=np.uint8) * 255

masque_visible = alpha > 0
pixels_visibles = img_bgr[masque_visible]

kmeans = KMeans(n_clusters=NB_COULEURS, random_state=42, n_init=10).fit(pixels_visibles)
couleurs = np.uint8(kmeans.cluster_centers_)

pixels_tous = img_bgr.reshape(-1, 3)
labels_tous = kmeans.predict(pixels_tous)
labels_matrice = labels_tous.reshape(hauteur, largeur)

print("\n📸 ÉTAPE 1 : Génération et filtrage des calques PNG...")

kernel_fermeture = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
kernel_dilatation = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

for i in range(NB_COULEURS):
    couleur_b, couleur_g, couleur_r = couleurs[i]

    if couleur_r > 245 and couleur_g > 245 and couleur_b > 245:
        continue

    masque_couleur = np.uint8((labels_matrice == i) & (alpha > 0)) * 255
    
    # Suppression du bruit isolé via composantes connexes
    nb_labels, labels_obj, stats, _ = cv2.connectedComponentsWithStats(masque_couleur)
    masque_sans_bruit = np.zeros_like(masque_couleur)
    
    for obj_i in range(1, nb_labels):
        if stats[obj_i, cv2.CC_STAT_AREA] >= TAILLE_GRAIN_MIN:
            masque_sans_bruit[labels_obj == obj_i] = 255

    if np.count_nonzero(masque_sans_bruit) == 0:
        continue

    # 🧼 NETTOYAGE & LISSAGE DES BORDS (Aplatissement des pointes)
    masque_propre = cv2.morphologyEx(masque_sans_bruit, cv2.MORPH_CLOSE, kernel_fermeture)
    masque_flou = cv2.GaussianBlur(masque_propre, (5, 5), 0)
    _, masque_lisse = cv2.threshold(masque_flou, 127, 255, cv2.THRESH_BINARY)
    masque_final = cv2.dilate(masque_lisse, kernel_dilatation, iterations=1)

    calque_png = np.zeros((hauteur, largeur, 4), dtype=np.uint8)
    pixels_valides = masque_final > 0
    calque_png[pixels_valides, 0:3] = img_bgr[pixels_valides]
    calque_png[pixels_valides, 3] = 255

    code_hex = f"{couleur_r:02x}{couleur_g:02x}{couleur_b:02x}"
    chemin_sauvegarde = os.path.join(dossier_sortie_png, f"calque_{i+1}_#{code_hex}.png")

    cv2.imwrite(chemin_sauvegarde, calque_png)
    print(f"  └─ Calque {i+1} nettoyé enregistré : '{chemin_sauvegarde}'")

# ---------------------------------------------------------
# 2. TRI PAR SURFACE DÉCROISSANTE
# ---------------------------------------------------------
print("\n✒️ ÉTAPE 2 : Tri par surface...")

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
# 3. VECTORISATION HAUTE DÉFINITION LISSE
# ---------------------------------------------------------
print("\n🖊️ ÉTAPE 3 : Vectorisation Potrace Lisse...")

def masque_vers_path_svg_hd(masque_binaire, dossier_tmp):
    tmp_id = uuid.uuid4().hex[:6]
    chemin_pbm = os.path.join(dossier_tmp, f"_tmp_{tmp_id}.pbm")
    chemin_svg = os.path.join(dossier_tmp, f"_tmp_{tmp_id}.svg")

    # 🚀 UPSCALING ET LISSAGE : Utilisation d'un redimensionnement Bilinéaire + Flou anti-crénelage
    masque_hd = cv2.resize(masque_binaire, (largeur * 2, hauteur * 2), interpolation=cv2.INTER_LINEAR)
    masque_hd = cv2.GaussianBlur(masque_hd, (3, 3), 0)
    _, masque_hd = cv2.threshold(masque_hd, 127, 255, cv2.THRESH_BINARY)

    Image.fromarray(255 - masque_hd).convert("1").save(chemin_pbm)

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

    if np.count_nonzero(masque_binaire) < TAILLE_GRAIN_MIN:
        continue

    d_path = masque_vers_path_svg_hd(masque_binaire, dossier_sortie_png)

    if d_path is None:
        continue

    lignes_svg.append(
        f'  <g transform="translate(0,{hauteur}) scale(0.05,-0.05)">'
        f'<path d="{d_path}" fill="{code_hex}" fill-rule="evenodd" '
        f'stroke="{code_hex}" stroke-width="0.5" stroke-linejoin="round" stroke-linecap="round" /></g>'
    )
    print(f"  └─ ✅ Vectorisé avec courbes lisses : '{fichier}'")

lignes_svg.append("</svg>")

# ---------------------------------------------------------
# 4. SAUVEGARDE DU FICHIER FINAL
# ---------------------------------------------------------
with open(chemin_sortie_svg, "w") as f:
    f.write("\n".join(lignes_svg))

print(f"\n🎉 Vectorisation finale terminée avec succès !")
print(f" 📂 PNG : {dossier_sortie_png}")
print(f" 📄 SVG : {chemin_sortie_svg}")