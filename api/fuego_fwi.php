<?php
/**
 * Devuelve en JSON los focos de calor de la tabla `firms`, con el valor FWI
 * (tabla `fwi`) correspondiente a cada foco.
 *
 * GET (ambos opcionales):
 *   fecha_desde=YYYY-MM-DD
 *   fecha_hasta=YYYY-MM-DD
 *
 * Si llega solo una, filtra desde/hasta esa fecha. Si no llega ninguna, no filtra.
 *
 * Cruce con FWI:
 *  - La fecha/hora de FIRMS (acq_date + acq_time, en UTC) se convierte a hora
 *    de Argentina (UTC-3) y se compara con fwi.fecha_hora_argentina.
 *  - Dentro de FWI_TOL_GRADOS en lat/lon, se toma el registro de fwi más
 *    cercano en tiempo (sin límite de diferencia horaria) y, ante igual hora,
 *    el más cercano en lat/lon.
 *  - Si no hay coincidencia, "fwi" es null.
 */
header('Content-Type: application/json; charset=utf-8');

// ---------- Configuración de la base de datos ----------
const DB_HOST = 'localhost';
const DB_NAME = 'flame';
const DB_USER = 'root';
const DB_PASS = '12345678';
const MAX_FILAS = 50000; // tope de seguridad

// ---------- Configuración de la tabla FWI (ajustar a tu esquema) ----------
const FWI_TABLA     = 'fwi';
const FWI_COL_LAT   = 'lat';
const FWI_COL_LON   = 'lon';
const FWI_COL_FECHA = 'fecha_hora_argentina'; // DATETIME (hora Argentina)
const FWI_COL_VALOR = 'FWI';
const FWI_TOL_GRADOS = 0.25; // máx. distancia en grados (lat y lon) al punto de grilla
const ARG_OFFSET_HORAS = 3;  // Argentina = UTC-3 (sin horario de verano)

function responder(int $codigo, array $data): void {
    http_response_code($codigo);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION);
    exit;
}

// Identificadores de la configuración: solo letras, números y guion bajo
function ident(string $n): string {
    if (!preg_match('/^[A-Za-z0-9_]+$/', $n)) {
        responder(500, ['error' => 'Configuracion invalida']);
    }
    return '`' . $n . '`';
}

// ---------- Parámetros (sin validación de formato; se usan con parámetros preparados) ----------
$desde = trim($_GET['fecha_desde'] ?? '');
$hasta = trim($_GET['fecha_hasta'] ?? '');

// ---------- Consulta ----------
try {
    $pdo = new PDO(
        'mysql:host=' . DB_HOST . ';dbname=' . DB_NAME . ';charset=utf8mb4',
        DB_USER,
        DB_PASS,
        [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]
    );

    $t   = ident(FWI_TABLA);
    $lat = ident(FWI_COL_LAT);
    $lon = ident(FWI_COL_LON);
    $fh  = ident(FWI_COL_FECHA);
    $val = ident(FWI_COL_VALOR);

    $where  = [];
    $params = [
        ':tol'   => FWI_TOL_GRADOS,
        ':off'   => ARG_OFFSET_HORAS,
    ];

    // acq_date es TEXT en formato YYYY-MM-DD, por lo que la comparación de strings es válida
    if ($desde !== '') { $where[] = 'acq_date >= :desde'; $params[':desde'] = $desde; }
    if ($hasta !== '') { $where[] = 'acq_date <= :hasta'; $params[':hasta'] = $hasta; }
    $whereSql = $where ? ' WHERE ' . implode(' AND ', $where) : '';

    // f: focos FIRMS con su fecha/hora convertida a hora Argentina.
    // La subconsulta busca el FWI más cercano en tiempo y, luego, en distancia.
    $sql = "
        SELECT f.latitude, f.longitude, f.brightness, f.acq_date, f.acq_time,
               f.satellite, f.instrument, f.confidence, f.bright_t31, f.frp,
               f.bright_ti4, f.bright_ti5,
               (SELECT w.$val
                  FROM $t w
                 WHERE w.$lat BETWEEN f.latitude  - :tol AND f.latitude  + :tol
                   AND w.$lon BETWEEN f.longitude - :tol AND f.longitude + :tol
                 ORDER BY ABS(TIMESTAMPDIFF(SECOND, w.$fh, f.fecha_hora_arg)),
                          POW(w.$lat - f.latitude, 2) + POW(w.$lon - f.longitude, 2)
                 LIMIT 1) AS fwi
          FROM (
                SELECT firms.*,
                       DATE_SUB(
                           STR_TO_DATE(CONCAT(acq_date, ' ', LPAD(acq_time, 4, '0')), '%Y-%m-%d %H%i'),
                           INTERVAL :off HOUR
                       ) AS fecha_hora_arg
                  FROM firms
                  $whereSql
                 ORDER BY acq_date, acq_time
                 LIMIT " . MAX_FILAS . "
               ) f
         ORDER BY f.acq_date, f.acq_time";

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);

    $datos = [];
    foreach ($stmt as $r) {
        $datos[] = [
            'latitud'    => $r['latitude']   !== null ? (float)$r['latitude']   : null,
            'longitud'   => $r['longitude']  !== null ? (float)$r['longitude']  : null,
            'brightness' => $r['brightness'] !== null ? (float)$r['brightness'] : null,
            'acq_date'   => $r['acq_date'],
            'acq_time'   => $r['acq_time']   !== null ? (int)$r['acq_time']     : null,
            'satellite'  => $r['satellite'],
            'instrument' => $r['instrument'],
            'confidence' => $r['confidence'] !== null ? (int)$r['confidence']   : null,
            'bright_t31' => $r['bright_t31'] !== null ? (float)$r['bright_t31'] : null,
            'frp'        => $r['frp']        !== null ? (float)$r['frp']        : null,
            'bright_ti4' => $r['bright_ti4'], // TEXT en la tabla
            'bright_ti5' => $r['bright_ti5'], // TEXT en la tabla
            'fwi'        => $r['fwi']        !== null ? (float)$r['fwi']        : null,
        ];
    }

    responder(200, $datos);

} catch (PDOException $e) {
    error_log('fuego.php: ' . $e->getMessage());
    responder(500, ['error' => 'Error al consultar la base de datos']);
}