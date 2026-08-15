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
TAILLE_GRAIN_MIN = 25  # Filtre les petits bruits isolés (en pixels²)

# Paramètres Potrace (les vrais leviers pour courbes vs lignes droites)
POTRACE_ALPHACORNER = 1.0   # 0 = tout en angles droits, 1.33 (défaut) = très arrondi.
                             # Baisse-le (ex: 0.5-0.8) pour préserver plus de coins nets.
POTRACE_OPTTOLERANCE = 0.2  # Tolérance d'optimisation des courbes (0.2 = défaut, plus bas = plus fidèle/plus de points)
POTRACE_TURDSIZE = 2        # Ignore les taches < N pixels (bruit), séparé de TAILLE_GRAIN_MIN

os.makedirs(dossier_sortie_png, exist_ok=True)
os.makedirs(dossier_sortie_svg, exist_ok=True)

print(f"🔑 Session ID unique généré : {session_id}")

# ---------------------------------------------------------
# 1. CHARGEMENT ET DÉCOUPAGE EN CALQUES PNG EXACTS
#    (Inchangé : c'est la partie qui marche bien)
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

print("\n📸 ÉTAPE 1 : Génération des calques PNG nettoyés...")

kernel_fermeture = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
kernel_dilatation = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))

for i in range(NB_COULEURS):
    couleur_b, couleur_g, couleur_r = couleurs[i]

    if couleur_r > 245 and couleur_g > 245 and couleur_b > 245:
        continue

    masque_couleur = np.uint8((labels_matrice == i) & (alpha > 0)) * 255
    masque_propre = cv2.morphologyEx(masque_couleur, cv2.MORPH_CLOSE, kernel_fermeture)
    masque_flou = cv2.GaussianBlur(masque_propre, (3, 3), 0)
    _, masque_lisse = cv2.threshold(masque_flou, 127, 255, cv2.THRESH_BINARY)
    masque_final = cv2.dilate(masque_lisse, kernel_dilatation, iterations=1)

    calque_png = np.zeros((hauteur, largeur, 4), dtype=np.uint8)
    pixels_valides = masque_final > 0
    calque_png[pixels_valides, 0:3] = img_bgr[pixels_valides]
    calque_png[pixels_valides, 3] = 255

    code_hex = f"{couleur_r:02x}{couleur_g:02x}{couleur_b:02x}"
    chemin_sauvegarde = os.path.join(dossier_sortie_png, f"calque_{i+1}_#{code_hex}.png")

    cv2.imwrite(chemin_sauvegarde, calque_png)
    print(f"  └─ Calque {i+1} lissé et étendu enregistré : '{chemin_sauvegarde}'")

# ---------------------------------------------------------
# 2. TRI PAR SURFACE DÉCROISSANTE (inchangé)
# ---------------------------------------------------------
print("\n✒️ ÉTAPE 2 : Analyse et tri par surface...")

fichiers_png = [f for f in os.listdir(dossier_sortie_png) if f.endswith(".png") and "#" in f]
donnees_calques = []

for fichier in fichiers_png:
    chemin_calque = os.path.join(dossier_sortie_png, fichier)
    calque_img = cv2.imread(chemin_calque, cv2.IMREAD_UNCHANGED)

    if calque_img is None or calque_img.shape[2] < 4:
        continue

    alpha_calque = calque_img[:, :, 3]
    masque_binaire = np.uint8(alpha_calque > 0) * 255

    surface_totale = np.count_nonzero(masque_binaire)
    code_hex = "#" + fichier.split("#")[1].split(".")[0]

    donnees_calques.append({
        "fichier": fichier,
        "hex": code_hex,
        "surface": surface_totale,
        "masque": masque_binaire,
    })

donnees_calques.sort(key=lambda x: x["surface"], reverse=True)

# ---------------------------------------------------------
# 3. VECTORISATION AVEC VRAIES COURBES / LIGNES / COINS (POTRACE)
# ---------------------------------------------------------
print("\n🖊️  ÉTAPE 3 : Vectorisation Potrace (courbes de Bézier + coins nets)...")


def masque_vers_path_svg(masque_binaire, dossier_tmp):
    """
    Convertit un masque binaire en un fragment de path SVG (attribut `d`)
    contenant de vraies courbes de Bézier cubiques (c) pour les zones
    lisses et de vraies lignes droites (l/m) pour les angles, via Potrace.
    Potrace travaille en coordonnées Y-inversées et à l'échelle 1/10pt,
    donc on renormalise ensuite le `d` dans le repère image (pixels, Y vers le bas).
    """
    tmp_id = uuid.uuid4().hex[:6]
    chemin_pbm = os.path.join(dossier_tmp, f"_tmp_{tmp_id}.pbm")
    chemin_svg = os.path.join(dossier_tmp, f"_tmp_{tmp_id}.svg")

    # Potrace lit un bitmap 1-bit (PBM) où les pixels "noirs" sont tracés.
    # PIL/PBM : blanc (255) -> bit 0 (non-encre), donc il FAUT inverser
    # notre masque (255=forme) pour que la forme soit bien "noire" = tracée.
    Image.fromarray(255 - masque_binaire).convert("1").save(chemin_pbm)

    cmd = [
        "potrace",
        "-s",                              # sortie SVG
        "-o", chemin_svg,
        "-a", str(POTRACE_ALPHACORNER),
        "-O", str(POTRACE_OPTTOLERANCE),
        "-t", str(POTRACE_TURDSIZE),
        chemin_pbm,
    ]
    resultat = subprocess.run(cmd, capture_output=True, text=True)
    if resultat.returncode != 0:
        print(f"    ⚠️  Potrace a échoué : {resultat.stderr}")
        os.remove(chemin_pbm)
        return None

    with open(chemin_svg, "r") as f:
        contenu = f.read()

    # Extrait le(s) attribut(s) d="..." du path généré par potrace
    correspondances = re.findall(r'<path[^>]*\sd="([^"]+)"', contenu)

    os.remove(chemin_pbm)
    os.remove(chemin_svg)

    if not correspondances:
        return None

    # Potrace émet dans un <g transform="translate(0,H) scale(0.1,-0.1)">.
    # On applique cette transform directement au <path> plutôt que de
    # ré-écrire les coordonnées à la main : plus simple et zéro perte de précision.
    return " ".join(correspondances)


lignes_svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{largeur}" height="{hauteur}" viewBox="0 0 {largeur} {hauteur}">'
]

for calque in donnees_calques:
    fichier = calque["fichier"]
    code_hex = calque["hex"]
    masque_binaire = calque["masque"]

    if np.count_nonzero(masque_binaire) < TAILLE_GRAIN_MIN:
        continue

    d_path = masque_vers_path_svg(masque_binaire, dossier_sortie_png)

    if d_path is None:
        print(f"  └─ ⚠️  Aucun contour exploitable pour : '{fichier}'")
        continue

    # Potrace: origine en bas-gauche, échelle 1/10pt -> on remet à l'échelle
    # pixel (x10) et on inverse Y (translate(0,H) scale(1,-1)) pour retrouver
    # le repère SVG standard (Y vers le bas, origine en haut-gauche).
    lignes_svg.append(
        f'  <g transform="translate(0,{hauteur}) scale(0.1,-0.1)">'
        f'<path d="{d_path}" fill="{code_hex}" fill-rule="evenodd" '
        f'stroke="{code_hex}" stroke-width="5" stroke-linejoin="round" /></g>'
    )
    print(f"  └─ ✅ Vectorisé (courbes+coins réels) : '{fichier}'")

lignes_svg.append("</svg>")

# ---------------------------------------------------------
# 4. SAUVEGARDE DU FICHIER FINAL
# ---------------------------------------------------------
with open(chemin_sortie_svg, "w") as f:
    f.write("\n".join(lignes_svg))

print(f"\n🎉 Vectorisation terminée ! Fichiers de la session '{session_id}' :")
print(f" 📂 PNG : {dossier_sortie_png}")
print(f" 📄 SVG : {chemin_sortie_svg}")