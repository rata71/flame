<?php $hoy = date('Y-m-d'); ?>
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Monitoreo de fuego</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
<div class="layout">

  <aside class="panel">
    <div class="tabs" role="tablist">
      <button class="tab active" data-tab="fuego" role="tab">Información de fuego</button>
      <button class="tab" data-tab="alertas" role="tab">Alertas enviadas</button>
    </div>

    <!-- TAB 1: FUEGO -->
    <section id="tab-fuego" class="tab-content active">
      <div class="row">
        <button type="button" id="btnHoy" class="btn btn-accent">HOY</button>
      </div>
      <div class="row two">
        <label>Fecha desde
          <input type="date" id="fuegoDesde" value="<?= $hoy ?>">
        </label>
        <label>Fecha hasta
          <input type="date" id="fuegoHasta" value="<?= $hoy ?>">
        </label>
      </div>
      <div class="row">
        <button type="button" id="btnFuego" class="btn">Mostrar resultados</button>
      </div>
      <div id="fuegoEstado" class="estado"></div>
    </section>

    <!-- TAB 2: ALERTAS -->
    <section id="tab-alertas" class="tab-content">
      <div class="row two">
        <label>Fecha desde
          <input type="date" id="alertaDesde" value="<?= $hoy ?>">
        </label>
        <label>Fecha hasta
          <input type="date" id="alertaHasta" value="<?= $hoy ?>">
        </label>
      </div>
      <div class="row">
        <button type="button" id="btnAlertas" class="btn">Buscar alertas</button>
      </div>
      <div id="alertaEstado" class="estado"></div>
      <div class="tabla-wrap">
        <table id="tablaAlertas">
          <thead>
            <tr><th>Fecha</th><th>Hora</th><th>Alerta</th><th>Coordenadas</th></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </section>
  </aside>

  <main id="map"></main>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="assets/app.js"></script>
</body>
</html>
