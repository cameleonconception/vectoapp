import os
import uuid
import cv2
import numpy as np
from sklearn.cluster import KMeans

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
TAILLE_GRAIN_MIN = 25  # Filtre les petits bruits isolés

# Création des répertoires uniques
os.makedirs(dossier_sortie_png, exist_ok=True)
os.makedirs(dossier_sortie_svg, exist_ok=True)

print(f"🔑 Session ID unique généré : {session_id}")

# ---------------------------------------------------------
# 1. CHARGEMENT ET DÉCOUPAGE EN CALQUES PNG EXACTS
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

# Noyau pour la fermeture et la dilatation morphologique
kernel_fermeture = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
kernel_dilatation = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))

for i in range(NB_COULEURS):
    couleur_b, couleur_g, couleur_r = couleurs[i]

    # Ignorer le fond blanc pur
    if couleur_r > 245 and couleur_g > 245 and couleur_b > 245:
        continue

    masque_couleur = np.uint8((labels_matrice == i) & (alpha > 0)) * 255

    # A. Combler les micro-trous internes à la couleur
    masque_propre = cv2.morphologyEx(masque_couleur, cv2.MORPH_CLOSE, kernel_fermeture)

    # B. Lisse la bordure via un léger flou gaussien et re-seuillage
    masque_flou = cv2.GaussianBlur(masque_propre, (3, 3), 0)
    _, masque_lisse = cv2.threshold(masque_flou, 127, 255, cv2.THRESH_BINARY)

    # C. Dilatation pour supprimer les trous entre formes adjacentes (bleed inter-calques)
    masque_final = cv2.dilate(masque_lisse, kernel_dilatation, iterations=1)

    # Construction du calque PNG
    calque_png = np.zeros((hauteur, largeur, 4), dtype=np.uint8)
    pixels_valides = masque_final > 0
    calque_png[pixels_valides, 0:3] = img_bgr[pixels_valides]
    calque_png[pixels_valides, 3] = 255

    code_hex = f"{couleur_r:02x}{couleur_g:02x}{couleur_b:02x}"
    chemin_sauvegarde = os.path.join(dossier_sortie_png, f"calque_{i+1}_#{code_hex}.png")

    cv2.imwrite(chemin_sauvegarde, calque_png)
    print(f"  └─ Calque {i+1} lissé et étendu enregistré : '{chemin_sauvegarde}'")

# ---------------------------------------------------------
# 2. TRI ET PRÉPARATION DES CALQUES (SURFACE DÉCROISSANTE)
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
        "masque": masque_binaire
    })

# Tri décroissant pour empiler les fonds larges en dessous des détails
donnees_calques.sort(key=lambda x: x["surface"], reverse=True)

# ---------------------------------------------------------
# 3. VECTORISATION SVG ULTRA-FLUIDE
# ---------------------------------------------------------
lignes_svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{largeur}" height="{hauteur}" viewBox="0 0 {largeur} {hauteur}">'
]

for calque in donnees_calques:
    fichier = calque["fichier"]
    code_hex = calque["hex"]
    masque_binaire = calque["masque"]

    contours, hierarchie = cv2.findContours(masque_binaire, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    if contours is None or hierarchie is None:
        continue

    sub_paths = []
    
    for idx, cnt in enumerate(contours):
        aire = cv2.contourArea(cnt)
        
        if aire < TAILLE_GRAIN_MIN:
            continue

        # Lissage de haute précision : epsilon très faible pour préserver la rondeur sans angles durs
        epsilon = 0.0006 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)

        d_sub = []
        for i_pt, point in enumerate(approx):
            x, y = point[0]
            cmd = "M" if i_pt == 0 else "L"
            d_sub.append(f"{cmd} {x} {y}")
        d_sub.append("Z")
        
        sub_paths.append(" ".join(d_sub))

    if sub_paths:
        path_complet = " ".join(sub_paths)
        lignes_svg.append(f'  <path d="{path_complet}" fill="{code_hex}" fill-rule="evenodd" stroke="{code_hex}" stroke-width="0.5" stroke-linejoin="round" />')
        print(f"  └─ ✅ Vectorisé et raccordé : '{fichier}'")

lignes_svg.append('</svg>')

# ---------------------------------------------------------
# 4. SAUVEGARDE DU FICHIER FINAL
# ---------------------------------------------------------
with open(chemin_sortie_svg, "w") as f:
    f.write("\n".join(lignes_svg))

print(f"\n🎉 Vectorisation ultra-lisse terminée ! Fichiers de la session '{session_id}' :")
print(f" 📂 PNG : {dossier_sortie_png}")
print(f" 📄 SVG : {chemin_sortie_svg}")