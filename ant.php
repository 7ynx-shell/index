<?php
// PHPBypass - No Auth / No Login Shell

// URL target (ganti dengan URL login atau halaman yang ingin diakses)
$url = "http://target.com/login.php";

// Data POST (ganti sesuai kebutuhan)
$postData = [
    "username" => "admin",
    "password" => "admin123"
];

// Mengirim request POST ke URL target
$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, $url);
curl_setopt($ch, CURLOPT_POST, 1);
curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query($postData));
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
curl_setopt($ch, CURLOPT_HEADER, 0);

$response = curl_exec($ch);

if ($response === false) {
    echo "Error: " . curl_error($ch);
} else {
    echo "Response: " . $response;
}

curl_close($ch);
?>
