"""
main.py - Resiliencia de la Internet chilena ante el terremoto Mw 8.8 del Maule (2010).

Subcomandos:
  python main.py cargar   Carga la BD: capas, comunas, sismo (GeoJSON USGS), red + topologia
                          (pgr_createTopology), nodos clave y probabilidades de falla (main.sql).
  python main.py attr     Calcula el ATTR antes y despues del sismo (Monte Carlo) y guarda un CSV.
  python main.py mapa     Genera output/mapa.html (Leaflet): enlaces, epicentro y dano.
  python main.py todo     cargar + attr + mapa.

Conexion: variable de entorno RESILIENCIA_DSN o --dsn
  (por defecto: host=localhost port=5432 dbname=resiliencia user=postgres password=postgres)
Requisitos: docker compose up -d   y   pip install -r requirements.txt
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.request

from attr import DSN_DEFECTO, calcular_tabla

RAIZ = os.path.dirname(os.path.abspath(__file__))
GEOJSON = os.path.join(RAIZ, "data", "sismo_maule.geojson")
URL_USGS = ("https://earthquake.usgs.gov/fdsnws/event/1/query"
            "?eventid=official20100227063411530_30&format=geojson")
# orden de carga; el sismo se carga en Python entre 02 y 03
PASOS_SQL_1 = ["sql/01_capas.sql", "sql/02_comunas.sql"]
PASOS_SQL_2 = ["sql/03_red.sql", "sql/04_nodos_clave.sql", "main.sql"]


def conectar(dsn):
    import psycopg2
    try:
        return psycopg2.connect(dsn)
    except psycopg2.OperationalError as e:
        sys.exit(f"No se pudo conectar a la base de datos.\n"
                 f"  Esta corriendo 'docker compose up -d'?  DSN: {dsn}\n  Detalle: {e}")


def ejecutar_sql(dsn, ruta_rel):
    ruta = os.path.join(RAIZ, ruta_rel)
    t0 = time.time()
    print(f"  -> {ruta_rel} ...", end=" ", flush=True)
    with open(ruta, encoding="utf-8") as f:
        sql = f.read()
    con = conectar(dsn)
    con.autocommit = True
    with con, con.cursor() as cur:
        cur.execute(sql)
    print(f"ok ({time.time() - t0:.0f} s)")


def cargar_sismo(dsn):
    """Carga el GeoJSON de USGS a la tabla sismo (titulo, mag, geom, prof_km)."""
    if not os.path.exists(GEOJSON):
        print(f"  (no existe {GEOJSON}; intentando descargarlo de USGS)")
        os.makedirs(os.path.dirname(GEOJSON), exist_ok=True)
        urllib.request.urlretrieve(URL_USGS, GEOJSON)
    with open(GEOJSON, encoding="utf-8") as f:
        j = json.load(f)
    feat = j["features"][0] if j.get("type") == "FeatureCollection" else j
    lon, lat, prof = feat["geometry"]["coordinates"][:3]
    titulo = feat["properties"].get("title")
    mag = feat["properties"].get("mag")
    con = conectar(dsn)
    with con, con.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS sismo")
        cur.execute("""CREATE TABLE sismo (titulo text, mag double precision,
                       geom geometry(Point, 4326), prof_km double precision)""")
        cur.execute("INSERT INTO sismo VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)",
                    (titulo, mag, lon, lat, prof))
    print(f"  -> sismo: {titulo} (prof. {prof} km) en ({lon}, {lat})")


def cmd_cargar(a):
    print("Cargando la base de datos ...")
    for p in PASOS_SQL_1:
        ejecutar_sql(a.dsn, p)
    cargar_sismo(a.dsn)
    for p in PASOS_SQL_2:
        ejecutar_sql(a.dsn, p)
    print("Listo.")


def imprimir_tabla(filas):
    print(f"\n{'red':>3} {'modelo':>7} {'K':>4} {'ATTR antes':>11} {'ATTR despues':>13} "
          f"{'IC95%':>17} {'p5-p95 (1 sismo)':>19} {'cambio':>8}")
    for r in filas:
        print(f"{r['red']:>3} {r['modelo']:>7} {r['nodos_clave']:>4} {r['attr_antes']:>11.4f} "
              f"{r['attr_despues']:>13.4f} {r['ic95_lo']:>8.4f}-{r['ic95_hi']:<8.4f} "
              f"{r['p5']:>8.4f}-{r['p95']:<8.4f} {100 * r['cambio_relativo']:>7.0f}%")


def guardar_csv(filas, ruta):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def cmd_attr(a):
    print(f"Calculando ATTR (Monte Carlo, N={a.n}, semilla {a.seed}) ...")
    filas = calcular_tabla(a.dsn, a.n, a.seed)
    imprimir_tabla(filas)
    ruta = os.path.join(RAIZ, "output", "attr_resultados.csv")
    guardar_csv(filas, ruta)
    print(f"\nGuardado en {ruta}")
    return filas


def cmd_mapa(a, filas=None):
    from mapa import exportar_datos, generar_mapa
    if filas is None:
        filas = calcular_tabla(a.dsn, a.n, a.seed)
    datos = exportar_datos(a.dsn)
    ruta = os.path.join(RAIZ, "output", "mapa.html")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    generar_mapa(datos, filas, ruta)
    print(f"Mapa generado: {ruta}  (abrelo en el navegador; necesita internet para Leaflet y el mapa base)")


def cmd_todo(a):
    cmd_cargar(a)
    filas = cmd_attr(a)
    cmd_mapa(a, filas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=DSN_DEFECTO)
    ap.add_argument("--n", type=int, default=1000, help="simulaciones Monte Carlo (por defecto 1000)")
    ap.add_argument("--seed", type=int, default=42)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nombre, fn in (("cargar", cmd_cargar), ("attr", cmd_attr), ("mapa", cmd_mapa), ("todo", cmd_todo)):
        sub.add_parser(nombre).set_defaults(fn=fn)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
