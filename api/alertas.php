<?php
/**
 * Endpoint de ejemplo: devuelve CSV con alertas enviadas.
 * GET: fecha_desde=YYYY-MM-DD & fecha_hasta=YYYY-MM-DD
 * Columnas: fecha,hora,alerta,latitud,longitud
 *
 * REEMPLAZAR el bloque "DATOS DE DEMO" por la consulta real.
 */
header('Content-Type: text/csv; charset=utf-8');

$desde = $_GET['fecha_desde'] ?? '';
$hasta = $_GET['fecha_hasta'] ?? '';
$ok = fn($f) => preg_match('/^\d{4}-\d{2}-\d{2}$/', $f) && strtotime($f) !== false;

if (!$ok($desde) || !$ok($hasta) || $desde > $hasta) {
    http_response_code(400);
    echo "error\nParametros invalidos";
    exit;
}

$out = fopen('php://output', 'w');
fputcsv($out, ['fecha', 'hora', 'alerta', 'latitud', 'longitud']);

// ---------- DATOS DE DEMO ----------
$tipos = ['Alerta amarilla', 'Alerta roja'];
$ini = new DateTime($desde);
$fin = new DateTime($hasta);
$dias = 0;
for ($d = clone $ini; $d <= $fin && $dias < 31; $d->modify('+1 day'), $dias++) {
    mt_srand(crc32($d->format('Y-m-d') . 'alerta'));
    for ($i = 0; $i < 4; $i++) {
        fputcsv($out, [
            $d->format('Y-m-d'),
            sprintf('%02d:%02d', mt_rand(0, 23), mt_rand(0, 59)),
            $tipos[mt_rand(0, 1)],
            round(-33.3 + (mt_rand(-200, 200) / 100), 5),
            round(-66.3 + (mt_rand(-200, 200) / 100), 5),
        ]);
    }
}
// ---------- FIN DEMO ----------
fclose($out);
