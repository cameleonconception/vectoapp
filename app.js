document.addEventListener('DOMContentLoaded', () => {
    // ÉLÉMENTS DE L'INTERFACE
    const stepDropzone = document.getElementById('step-dropzone');
    const stepPreview = document.getElementById('step-preview');
    const stepLoading = document.getElementById('step-loading');
    const stepResult = document.getElementById('step-result');

    const dropzone = document.getElementById('dropzone');
    


        // 1. Déclarer la variable en haut de app.js avec les autres éléments
        const btnBack = document.getElementById('btn-back');
        const fileInput = document.getElementById('file-input'); // Assure-toi qu'il est bien déclaré

        // 2. Ajouter cet événement dans le fichier app.js
        btnBack.addEventListener('click', () => {
            // Reinitialise la sélection de fichier
            fileInput.value = '';
            
            // Vider le conteneur SVG
            document.getElementById('svg-container').innerHTML = '';
            
            // Revenir à l'étape 1 (Dropzone)
            switchStep(document.getElementById('step-dropzone'));
        });

    const imgPreview = document.getElementById('img-preview');
    const inputCouleurs = document.getElementById('input-couleurs');
    const btnVectoriser = document.getElementById('btn-vectoriser');

    const loadingText = document.getElementById('loading-status-text');
    const svgContainer = document.getElementById('svg-container');
    const btnDownload = document.getElementById('btn-download');

    
    let selectedFile = null;

    // 1. GESTION DU DROPZONE
    dropzone.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFile(e.target.files[0]);
        }
    });

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.style.backgroundColor = '#1a1a1a';
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.style.backgroundColor = 'transparent';
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        if (e.dataTransfer.files.length > 0) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    function handleFile(file) {
        selectedFile = file;
        const reader = new FileReader();
        reader.onload = (e) => {
            imgPreview.src = e.target.result;
            switchStep(stepPreview);
        };
        reader.readAsDataURL(file);
    }

    // 2. LANCEMENT DE LA VECTORISATION
    btnVectoriser.addEventListener('click', () => {
        if (!selectedFile) return;

        switchStep(stepLoading);
        animateLoadingMessages();

        const formData = new FormData();
        formData.append('image', selectedFile);
        formData.append('couleurs', inputCouleurs.value);

        fetch('traitement.php', {
            method: 'POST',
            body: formData
        })
        .then(response => response.text())
        .then(html => {
            // Injection directe du SVG au centre
            svgContainer.innerHTML = html;
            
            // Configuration du bouton de téléchargement
            const svgElement = svgContainer.querySelector('svg');
            if (svgElement) {
                const blob = new Blob([svgElement.outerHTML], { type: 'image/svg+xml' });
                btnDownload.href = URL.createObjectURL(blob);
            }
            
            switchStep(stepResult);
        })
        .catch(err => {
            alert("Erreur lors du traitement de l'image.");
            switchStep(stepPreview);
        });
    });

    // 3. MESSAGES DYNAMIQUES DE CHARGEMENT
    function animateLoadingMessages() {
        const messages = [
            "Séparation des couleurs en cours...",
            "Affinage des courbes...",
            "Vectorisation avec Potrace...",
            "Génération du fichier SVG final..."
        ];
        let index = 0;
        loadingText.innerText = messages[0];

        const interval = setInterval(() => {
            index++;
            if (index < messages.length) {
                loadingText.innerText = messages[index];
            } else {
                clearInterval(interval);
            }
        }, 1200);
    }

    // UTILITAIRE : CHANGEMENT DE VUE
    function switchStep(targetStep) {
        document.querySelectorAll('.step-view').forEach(step => step.classList.remove('active'));
        targetStep.classList.add('active');
    }
});
