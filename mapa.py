"""
mapa.py - Mapa Leaflet (HTML autocontenido) con la red, el epicentro y el dano esperado.

  - Enlaces coloreados por su probabilidad de falla (selector de escenario bajo/medio/alto)
  - Boton para sortear UNA realizacion del terremoto y ver que enlaces fallan
  - Epicentro (USGS) con circulos de 100/300/500 km
  - Nodos clave (comunas) de cada escenario de red
  - Tabla de ATTR antes y despues

El HTML carga Leaflet desde unpkg.com y el mapa base (Esri; el selector permite cambiarlo):
necesita internet al ABRIR el archivo.
"""
import json
import math

SQL_ENLACES = """
SELECT jsonb_build_object('type','FeatureCollection','features', COALESCE(jsonb_agg(f), '[]'::jsonb))
FROM (
  SELECT jsonb_build_object(
    'type','Feature',
    'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.001), 5)::jsonb,
    'properties', jsonb_build_object(
      'id', id, 'tipo', tipo, 'sintetico', es_sintetico,
      'km', round((length_m/1000)::numeric, 1),
      'p_bajo',  round(prob_bajo::numeric, 4),
      'p_medio', round(prob_medio::numeric, 4),
      'p_alto',  round(prob_alto::numeric, 4))) AS f
  FROM red_edges
) t
"""
SQL_NODOS = "SELECT escenario, cod_comuna, comuna, ST_X(the_geom), ST_Y(the_geom) FROM nodos_clave"
SQL_SISMO = "SELECT titulo, mag, prof_km, ST_X(geom), ST_Y(geom) FROM sismo LIMIT 1"


def exportar_datos(dsn):
    """Lee de la BD lo que necesita el mapa."""
    import psycopg2
    with psycopg2.connect(dsn) as con, con.cursor() as cur:
        cur.execute(SQL_ENLACES)
        enlaces = cur.fetchone()[0]
        cur.execute(SQL_NODOS)
        nodos = [{"esc": r[0], "cod": r[1], "comuna": r[2], "lon": r[3], "lat": r[4]}
                 for r in cur.fetchall()]
        cur.execute(SQL_SISMO)
        t, mag, prof, lon, lat = cur.fetchone()
    return {"enlaces": enlaces, "nodos": nodos,
            "sismo": {"titulo": t, "mag": mag, "prof_km": prof, "lon": lon, "lat": lat}}


PLANTILLA = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Resiliencia de la Internet chilena - terremoto del Maule 2010</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  html, body, #map { height: 100%; margin: 0; }
  body { font-family: system-ui, sans-serif; }
  .panel { background: rgba(255,255,255,.95); padding: 10px 12px; border-radius: 6px;
           box-shadow: 0 1px 6px rgba(0,0,0,.3); font-size: 12px; line-height: 1.4; max-width: 330px; }
  .panel h4 { margin: 0 0 6px; font-size: 13px; }
  .panel table { border-collapse: collapse; width: 100%; margin-top: 4px; }
  .panel th, .panel td { border-bottom: 1px solid #ddd; padding: 2px 4px; text-align: right; }
  .panel th:first-child, .panel td:first-child { text-align: left; }
  .leyenda i { display: inline-block; width: 22px; height: 6px; margin-right: 6px; vertical-align: middle; }
  .panel button, .panel select { margin: 4px 4px 0 0; }
  .nota { color: #555; margin-top: 6px; }
</style>
</head>
<body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const DATOS = __DATOS__;
const TABLA = __TABLA__;

const map = L.map('map').setView([-36, -71.5], 5);
const ESRI = 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ, USGS, NOAA';
const bases = {
  'Esri - gris claro': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    { maxNativeZoom: 16, maxZoom: 18, attribution: ESRI }),
  'Esri - calles': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    { maxNativeZoom: 19, maxZoom: 19, attribution: ESRI }),
  'Esri - satelite': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { maxNativeZoom: 18, maxZoom: 18, attribution: ESRI })
};
bases['Esri - gris claro'].addTo(map);

// ---- color por probabilidad de falla ----
const BINS = [
  [0.01, '#4575b4', 'p < 1 %'],
  [0.05, '#fee090', '1 - 5 %'],
  [0.15, '#fc8d59', '5 - 15 %'],
  [0.30, '#d73027', '15 - 30 %'],
  [1.01, '#7f0000', '>= 30 %']
];
function color(p) { for (const b of BINS) { if (p < b[0]) return b[1]; } return BINS[BINS.length - 1][1]; }

let escenario = 'medio';
const llave = () => 'p_' + escenario;
const ESTILO = {
  fibra:  { weight: 3,   opacity: 0.95, dashArray: null },
  poste:  { weight: 2,   opacity: 0.6,  dashArray: null },
  camino: { weight: 2,   opacity: 0.5,  dashArray: '4 4' },
  ferry:  { weight: 2,   opacity: 0.6,  dashArray: '1 6' }
};
function estilo(f) {
  const e = ESTILO[f.properties.tipo] || ESTILO.camino;
  return { color: color(f.properties[llave()]), weight: e.weight, opacity: e.opacity, dashArray: e.dashArray };
}
function popup(f) {
  const p = f.properties;
  const tag = p.sintetico ? ' <i>(enlace sintetico)</i>' : ' <i>(fibra real)</i>';
  return '<b>' + p.tipo + '</b> #' + p.id + tag + '<br>' + p.km + ' km<br>' +
    'P(falla): bajo ' + (100 * p.p_bajo).toFixed(1) + ' % | medio ' + (100 * p.p_medio).toFixed(1) +
    ' % | alto ' + (100 * p.p_alto).toFixed(1) + ' %';
}
const capas = {};
const overlays = {};
for (const tipo of ['fibra', 'poste', 'camino', 'ferry']) {
  capas[tipo] = L.geoJSON(DATOS.enlaces, {
    filter: f => f.properties.tipo === tipo, style: estilo,
    onEachFeature: (f, l) => l.bindPopup(popup(f))
  });
  overlays[{ fibra: 'Fibra optica (real)', poste: 'Postacion electrica [sintetico]', camino: 'Caminos sin postacion [sintetico]', ferry: 'Ferry [sintetico]' }[tipo]] = capas[tipo];
  if (tipo === 'fibra' || tipo === 'poste') capas[tipo].addTo(map);
}
function recolorear() { Object.values(capas).forEach(c => c.setStyle(estilo)); }

// ---- epicentro ----
const S = DATOS.sismo;
const epic = L.circleMarker([S.lat, S.lon], { radius: 8, color: '#000', weight: 2, fillColor: '#ff0', fillOpacity: 1 })
  .bindPopup('<b>' + S.titulo + '</b><br>Mw ' + S.mag + ' - prof. ' + S.prof_km + ' km').addTo(map);
const circulos = L.layerGroup([100, 300, 500].map(r =>
  L.circle([S.lat, S.lon], { radius: r * 1000, color: '#444', weight: 1, dashArray: '6 6', fill: false })
    .bindTooltip(r + ' km'))).addTo(map);
overlays['Epicentro: circulos 100/300/500 km'] = circulos;

// ---- nodos clave ----
for (const esc of ['A', 'B']) {
  const g = L.layerGroup(DATOS.nodos.filter(n => n.esc === esc).map(n =>
    L.circleMarker([n.lat, n.lon], { radius: 3, color: '#222', weight: 1, fillColor: esc === 'A' ? '#2ca25f' : '#9e9ac8', fillOpacity: 0.9 })
      .bindTooltip(n.comuna)));
  overlays['Nodos clave - red ' + esc + (esc === 'A' ? ' (solo fibra)' : ' (todas las capas)')] = g;
  if (esc === 'A') g.addTo(map);
}

// ---- una realizacion simulada ----
let capaFallos = L.layerGroup().addTo(map);
function sortear() {
  capaFallos.clearLayers();
  let n = 0, km = 0;
  for (const f of DATOS.enlaces.features) {
    if (Math.random() < f.properties[llave()]) {
      n++; km += f.properties.km;
      L.geoJSON(f, { style: { color: '#000', weight: 6, opacity: 0.9 } }).bindPopup(popup(f)).addTo(capaFallos);
    }
  }
  document.getElementById('resultado').textContent =
    'Realizacion: ' + n + ' enlaces caidos (' + km.toFixed(0) + ' km) - escenario ' + escenario;
}
overlays['Enlaces caidos (realizacion)'] = capaFallos;
L.control.layers(bases, overlays, { collapsed: false, position: 'topleft' }).addTo(map);

// ---- panel de control ----
const panel = L.control({ position: 'topright' });
panel.onAdd = function () {
  const d = L.DomUtil.create('div', 'panel');
  const fp = x => x == null ? '-' : (100 * x).toFixed(1) + ' %';
  const f4 = x => x == null ? '-' : x.toFixed(4);
  let filas = TABLA.map(r => '<tr><td>' + r.red + ' / ' + r.modelo + '</td><td>' + f4(r.attr_antes) +
    '</td><td>' + f4(r.attr_despues) + '</td><td>' + fp(r.cambio_relativo) + '</td></tr>').join('');
  d.innerHTML =
    '<h4>Terremoto del Maule 2010 - dano esperado</h4>' +
    'Escenario del modelo: <select id="sel"><option>bajo</option><option selected>medio</option><option>alto</option></select>' +
    '<button id="btn">Sortear una realizacion</button><div id="resultado" class="nota"></div>' +
    '<div class="leyenda" style="margin-top:6px"><b>P(falla) del enlace</b><br>' +
    BINS.map(b => '<i style="background:' + b[1] + '"></i>' + b[2]).join('<br>') + '</div>' +
    '<table><tr><th>Red / modelo</th><th>ATTR antes</th><th>ATTR despues</th><th>Cambio</th></tr>' + filas + '</table>' +
    '<div class="nota">Red A = solo fibra; red B = fibra + postes + caminos + ferry. ' +
    'ATTR despues = promedio Monte Carlo. Modelo: Youngs et al. (1997) + ALA (2001) (ver README).</div>';
  L.DomEvent.disableClickPropagation(d);
  return d;
};
panel.addTo(map);
document.getElementById('sel').addEventListener('change', e => { escenario = e.target.value; recolorear(); capaFallos.clearLayers(); });
document.getElementById('btn').addEventListener('click', sortear);
</script>
</body>
</html>
"""


def _limpiar(o):
    """NaN/inf no son JSON valido: se reemplazan por null."""
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _limpiar(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_limpiar(v) for v in o]
    return o


def construir_html(datos, tabla):
    """Devuelve el HTML del mapa a partir de datos (exportar_datos) y la tabla de ATTR."""
    def js(o):  # JSON seguro para incrustar en <script>
        return json.dumps(_limpiar(o), ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    return PLANTILLA.replace("__DATOS__", js(datos)).replace("__TABLA__", js(tabla))


def generar_mapa(datos, tabla, ruta):
    html = construir_html(datos, tabla)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)
    return ruta