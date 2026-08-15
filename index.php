<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vectorisateur d'Images</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>

    <!-- ÉTAPE 1 : DROPZONE PLEINE PAGE -->
    <section id="step-dropzone" class="step-view active">
        <div class="dropzone" id="dropzone">
            <input type="file" id="file-input" accept="image/png, image/jpeg" hidden>
            <p class="dropzone-text">Téléverser votre image ici</p>
        </div>
    </section>

    <!-- ÉTAPE 2 : APERÇU + POPUP DU NOMBRE DE COULEURS -->
    <section id="step-preview" class="step-view">
        <div class="preview-container">
            <img id="img-preview" src="" alt="Aperçu de l'image">
        </div>
        <!-- Popup modal en bas au centre -->
        <div class="popup-modal">
            <label for="input-couleurs">Combien de couleurs ?</label>
            <input type="number" id="input-couleurs" value="4" min="1" max="20">
            <button id="btn-vectoriser">Vectoriser</button>
        </div>
    </section>

    <!-- ÉTAPE 3 : ÉCRAN DE CHARGEMENT ANIMÉ -->
    <section id="step-loading" class="step-view">
        <div class="loading-content">
            <div class="spinner"></div>
            <p id="loading-status-text">Separation des couleurs en cours...</p>
        </div>
    </section>

    <!-- ÉTAPE 4 : AFFICHAGE DU SVG + BOUTONS ACTION -->
    <section id="step-result" class="step-view">
        <div class="svg-result-container">
            <!-- Le SVG sera injecté directement ici -->
            <div id="svg-container"></div>
        </div>

        <div class="action-bar">
            <!-- ➕ NOUVEAU BOUTON RETOUR SITIÉ À GAUCHE -->
            <button id="btn-back" class="btn-back" title="Revenir au début">←</button>
            <a id="btn-download" href="#" download="logo_vectorise.svg" class="btn-download">Télécharger le SVG</a>
        </div>
    </section>

    <script src="app.js"></script>
</body>
</html>