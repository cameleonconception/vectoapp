document.addEventListener('DOMContentLoaded', () => {
    // --- ÉLÉMENTS DE L'INTERFACE ---
    const stepDropzone = document.getElementById('step-dropzone');
    const stepPreview = document.getElementById('step-preview');
    const stepLoading = document.getElementById('step-loading');
    const stepResult = document.getElementById('step-result');

    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    const btnBack = document.getElementById('btn-back');
    const imgPreview = document.getElementById('img-preview');
    const inputCouleurs = document.getElementById('input-couleurs');
    const btnVectoriser = document.getElementById('btn-vectoriser');
    const btnDownload = document.getElementById('btn-download');
    const svgContainer = document.getElementById('svg-container');

    // --- VARIABLES D'ÉTAT ---
    let selectedFile = null; // Fix: Variable globale déclarée pour le FormData
    let selectedImage = new Image();
    let currentPalette = [];

    // Masquer l'ancien input numérique s'il existe
    if (inputCouleurs) inputCouleurs.style.display = 'none';
    const labelCouleurs = document.querySelector('label[for="input-couleurs"]');
    if (labelCouleurs) labelCouleurs.style.display = 'none';

    // --- 1. GESTION DU DROPZONE ---
    dropzone.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleFile(e.target.files[0]);
    });

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.style.backgroundColor = 'rgba(99, 102, 241, 0.1)';
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.style.backgroundColor = 'transparent';
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.style.backgroundColor = 'transparent';
        if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
    });

    btnBack.addEventListener('click', () => {
        fileInput.value = '';
        selectedFile = null; // Réinitialisation
        svgContainer.innerHTML = '';
        switchStep(stepDropzone);
    });

    // --- 2. TRAITEMENT DU FICHIER ET ANALYSE CHROMATIQUE ---
    function handleFile(file) {
        selectedFile = file; // Fix: Sauvegarde du fichier pour le FormData
        
        const reader = new FileReader();
        reader.onload = (e) => {
            imgPreview.src = e.target.result;
            selectedImage.src = e.target.result;

            selectedImage.onload = () => {
                const palette = extraireCouleursVisuelles(selectedImage, 45, 0.008);
                currentPalette = palette.map(c => c.hex);
                renderPalette();
                switchStep(stepPreview);
            };
        };
        reader.readAsDataURL(file);
    }

    // --- 3. GESTION DES PASTILLES ---
    function renderPalette() {
        let paletteContainer = document.getElementById('palette-container');
        
        if (!paletteContainer) {
            paletteContainer = document.createElement('div');
            paletteContainer.id = 'palette-container';
            paletteContainer.className = 'palette-container';
            const popupModal = document.querySelector('.popup-modal');
            popupModal.insertBefore(paletteContainer, popupModal.firstChild);
        }

        paletteContainer.innerHTML = '';

        currentPalette.forEach((colorHex, index) => {
            const swatchWrapper = document.createElement('div');
            swatchWrapper.className = 'swatch-wrapper';

            const colorInput = document.createElement('input');
            colorInput.type = 'color';
            colorInput.value = colorHex;
            colorInput.className = 'color-swatch-input';

            colorInput.addEventListener('input', (e) => {
                currentPalette[index] = e.target.value;
            });

            const btnDelete = document.createElement('button');
            btnDelete.className = 'btn-delete-swatch';
            btnDelete.innerHTML = '&times;';
            btnDelete.type = 'button';

            btnDelete.addEventListener('click', (e) => {
                e.stopPropagation();
                currentPalette.splice(index, 1);
                renderPalette();
            });

            swatchWrapper.appendChild(colorInput);
            swatchWrapper.appendChild(btnDelete);
            paletteContainer.appendChild(swatchWrapper);
        });

        const btnAdd = document.createElement('button');
        btnAdd.className = 'btn-add-swatch';
        btnAdd.innerHTML = '+';
        btnAdd.type = 'button';

        btnAdd.addEventListener('click', () => {
            currentPalette.push('#6366f1');
            renderPalette();

            const swatches = paletteContainer.querySelectorAll('.color-swatch-input');
            const dernierePastille = swatches[swatches.length - 1];
            if (dernierePastille) dernierePastille.click();
        });

        paletteContainer.appendChild(btnAdd);
        btnVectoriser.style.display = currentPalette.length >= 1 ? 'inline-block' : 'none';
    }

    // --- 4. ENVOI AU SERVEUR POUR VECTORISATION ---
    btnVectoriser.addEventListener('click', () => {
    if (!selectedFile) {
        alert("Veuillez d'abord sélectionner une image.");
        return;
    }

    switchStep(stepLoading);

    const formData = new FormData();
    formData.append('image', selectedFile);
    // Encodage Base64 pour éviter que PHP/Windows n'altère le JSON
    formData.append('couleurs', btoa(JSON.stringify(currentPalette)));

    fetch('traitement.php', {
        method: 'POST',
        body: formData
    })
    .then(async response => {
        const text = await response.text();
        if (!response.ok) throw new Error(text);
        return text;
    })
    .then(html => {
        svgContainer.innerHTML = html;
        const svgElement = svgContainer.querySelector('svg');
        if (svgElement) {
            const blob = new Blob([svgElement.outerHTML], { type: 'image/svg+xml' });
            btnDownload.href = URL.createObjectURL(blob);
        }
        switchStep(stepResult);
    })
    .catch(err => {
        alert("Erreur Serveur :\n" + err.message);
        switchStep(stepPreview);
    });
});

    function switchStep(targetStep) {
        document.querySelectorAll('.step-view').forEach(step => step.classList.remove('active'));
        targetStep.classList.add('active');
    }
});

/* =========================================================
   EXTRACTION DES COULEURS
   ========================================================= */
function extraireCouleursVisuelles(imageElement, tolerance = 45, pourcentageMin = 0.008) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    const maxDim = 200;
    const ratio = Math.min(maxDim / imageElement.naturalWidth, maxDim / imageElement.naturalHeight, 1);
    const width = Math.round(imageElement.naturalWidth * ratio);
    const height = Math.round(imageElement.naturalHeight * ratio);

    canvas.width = width;
    canvas.height = height;
    ctx.drawImage(imageElement, 0, 0, width, height);

    const imgData = ctx.getImageData(0, 0, width, height).data;
    let totalPixelsOpaques = 0;
    const clusters = [];

    for (let i = 0; i < imgData.length; i += 4) {
        const r = imgData[i], g = imgData[i + 1], b = imgData[i + 2], a = imgData[i + 3];
        if (a < 128) continue;
        totalPixelsOpaques++;

        let estAbsorbe = false;

        for (const cluster of clusters) {
            const dR = r - cluster.r, dG = g - cluster.g, dB = b - cluster.b;
            const dist = Math.sqrt(dR * dR * 0.3 + dG * dG * 0.59 + dB * dB * 0.11);

            if (dist < tolerance) {
                const total = cluster.count + 1;
                cluster.r = Math.round((cluster.r * cluster.count + r) / total);
                cluster.g = Math.round((cluster.g * cluster.count + g) / total);
                cluster.b = Math.round((cluster.b * cluster.count + b) / total);
                cluster.count = total;
                estAbsorbe = true;
                break;
            }
        }

        if (!estAbsorbe) clusters.push({ r, g, b, count: 1 });
    }

    if (totalPixelsOpaques === 0) return [];

    const seuilPixel = totalPixelsOpaques * pourcentageMin;
    const paletteFiltree = clusters
        .filter(c => c.count >= seuilPixel)
        .sort((a, b) => b.count - a.count);

    if (paletteFiltree.length === 0 && clusters.length > 0) {
        paletteFiltree.push(clusters.sort((a, b) => b.count - a.count)[0]);
    }

    return paletteFiltree.map(c => ({
        hex: `#${((1 << 24) + (c.r << 16) + (c.g << 8) + c.b).toString(16).slice(1)}`,
        rgb: [c.r, c.g, c.b]
    }));
}