<?php
set_time_limit(0);
ini_set('max_execution_time', 0);

$base_dir = __DIR__;
$dossier_reception = $base_dir . DIRECTORY_SEPARATOR . "img" . DIRECTORY_SEPARATOR . "toBeVectorized" . DIRECTORY_SEPARATOR;

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES['image'])) {
    
    $couleurs_b64 = isset($_POST['couleurs']) ? $_POST['couleurs'] : '';
    $fichier = $_FILES['image'];
    
    if (!is_dir($dossier_reception)) {
        mkdir($dossier_reception, 0777, true);
    }
    
    $nom_fichier = basename($fichier['name']);
    $chemin_destination = $dossier_reception . $nom_fichier;
    
    if (move_uploaded_file($fichier['tmp_name'], $chemin_destination)) {
        
        $chemin_script_python = $base_dir . DIRECTORY_SEPARATOR . "vectoapp.py";
        
        if (PHP_OS_FAMILY === 'Windows') {
            $commande = "python " . escapeshellarg($chemin_script_python) . " " . escapeshellarg($nom_fichier) . " " . escapeshellarg($couleurs_b64) . " 2>&1";
        } else {
            $commande = "export LC_ALL=C.UTF-8; python3 " . escapeshellarg($chemin_script_python) . " " . escapeshellarg($nom_fichier) . " " . escapeshellarg($couleurs_b64) . " 2>&1";
        }
        
        $resultat_python = trim(shell_exec($commande));
        
        if (!empty($resultat_python) && strpos($resultat_python, '<svg') !== false) {
            echo $resultat_python;
            exit();
        } else {
            http_response_code(500);
            echo "Erreur Python : " . $resultat_python;
            exit();
        }
    } else {
        http_response_code(500);
        echo "Erreur : Impossible de déplacer le fichier téléversé.";
        exit();
    }
}
?>