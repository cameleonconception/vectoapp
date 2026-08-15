<?php
// 🚀 SUPPRESSION DE LA LIMITE DE TEMPS D'EXÉCUTION PHP (Permet les traitements longs)
set_time_limit(0);
ini_set('max_execution_time', 0);

// ---------------------------------------------------------
// CONFIGURATION DES CHEMINS ABSOLUS (PORTABLE LINUX / WINDOWS)
// ---------------------------------------------------------
$base_dir = __DIR__;
$dossier_reception = $base_dir . DIRECTORY_SEPARATOR . "img" . DIRECTORY_SEPARATOR . "toBeVectorized" . DIRECTORY_SEPARATOR;

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES['image'])) {
    
    $nombre_couleurs = intval($_POST['couleurs']);
    $fichier = $_FILES['image'];
    
    if (!is_dir($dossier_reception)) {
        mkdir($dossier_reception, 0777, true);
    }
    
    $nom_fichier = basename($fichier['name']);
    $chemin_destination = $dossier_reception . $nom_fichier;
    
    if (move_uploaded_file($fichier['tmp_name'], $chemin_destination)) {
        
        $chemin_script_python = $base_dir . DIRECTORY_SEPARATOR . "vectoapp.py";
        
        // Détection automatique du système d'exploitation
        if (PHP_OS_FAMILY === 'Windows') {
            $commande = "python " . escapeshellarg($chemin_script_python) . " " . escapeshellarg($nom_fichier) . " " . escapeshellarg($nombre_couleurs) . " 2>&1";
        } else {
            $commande = "export LC_ALL=C.UTF-8; python3 " . escapeshellarg($chemin_script_python) . " " . escapeshellarg($nom_fichier) . " " . escapeshellarg($nombre_couleurs) . " 2>&1";
        }
        
        // Exécution de la commande
        $chemin_svg_genere = trim(shell_exec($commande));
        
        // Vérification et renvoi du SVG
        if (!empty($chemin_svg_genere) && file_exists($chemin_svg_genere)) {
            echo file_get_contents($chemin_svg_genere);
            exit();
        } else {
            http_response_code(500);
            echo "Erreur lors de la génération. Console : " . $chemin_svg_genere;
            exit();
        }
    } else {
        http_response_code(500);
        echo "Erreur : Impossible de déplacer le fichier téléversé.";
        exit();
    }
}
?>