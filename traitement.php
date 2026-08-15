<?php
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES['image'])) {
    
    $nombre_couleurs = intval($_POST['couleurs']);
    $fichier = $_FILES['image'];
    
    $dossier_reception = "img/toBeVectorized/";
    if (!is_dir($dossier_reception)) {
        mkdir($dossier_reception, 0777, true);
    }
    
    $nom_fichier = basename($fichier['name']);
    $chemin_destination = $dossier_reception . $nom_fichier;
    
    if (move_uploaded_file($fichier['tmp_name'], $chemin_destination)) {
        
        // Exécution de Python en capturant aussi les erreurs système (2>&1)
        $commande = "python vectoapp.py " . escapeshellarg($nom_fichier) . " " . escapeshellarg($nombre_couleurs) . " 2>&1";
        $output = shell_exec($commande);
        
        // Recherche du fichier SVG généré dans le dossier img/vectorized/
        $nom_svg_attendu = pathinfo($nom_fichier, PATHINFO_FILENAME) . "_vectorise.svg";
        
        // Recherche récursive dans les sous-dossiers de session
        $fichiers_trouves = glob("img/vectorized/*/" . $nom_svg_attendu);
        
        if (!empty($fichiers_trouves) && file_exists($fichiers_trouves[0])) {
            $chemin_svg = $fichiers_trouves[0];
            echo "<div>" . file_get_contents($chemin_svg) . "</div>";
        } else {
            echo "❌ Erreur lors de la génération du fichier SVG.<br>";
            echo "<strong>Détail de la console :</strong><pre>$output</pre>";
        }
    } else {
        echo "❌ Échec du téléversement de l'image.";
    }
}
?>