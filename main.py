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
PASOS_SQL_2 = ["sql/03_red.sql", "sql/04_nodos_clave.sql", "sql/05_probabilidades.sql"]


def _reemplazar_dbname(dsn, nueva_db="postgres"):
    import re
    if "dbname=" in dsn:
        return re.sub(r"dbname=\S+", f"dbname={nueva_db}", dsn)
    return dsn + f" dbname={nueva_db}"


def asegurar_bd(dsn, intentos=15):
    """Espera a que PostgreSQL acepte conexiones y crea la BD si aun no existe."""
    import psycopg2
    from psycopg2 import sql as psql
    ultimo_error = None
    for i in range(intentos):
        try:
            con = psycopg2.connect(dsn)
            con.close()
            return
        except psycopg2.OperationalError as e:
            msg = str(e).lower()
            if "does not exist" in msg or "no existe" in msg:
                break
            ultimo_error = e
            if i == 0:
                print("  -> Esperando a que PostgreSQL termine de iniciar ...", flush=True)
            time.sleep(1)
    else:
        sys.exit(f"No se pudo conectar a la base de datos.\n"
                 f"  Esta corriendo 'docker compose up -d'?  DSN: {dsn}\n  Detalle: {ultimo_error}")
    import re
    m = re.search(r"dbname=(\S+)", dsn)
    dbname = m.group(1) if m else "resiliencia"
    dsn_admin = _reemplazar_dbname(dsn, "postgres")
    try:
        con = psycopg2.connect(dsn_admin)
        con.autocommit = True
        with con.cursor() as cur:
            cur.execute(psql.SQL("CREATE DATABASE {}").format(psql.Identifier(dbname)))
        con.close()
        print(f"  -> Base de datos '{dbname}' creada automaticamente.")
    except Exception as e:
        sys.exit(f"No se pudo crear la base de datos '{dbname}': {e}")


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


def imprimir_resumen_bd(dsn):
    """Imprime verificacion de topologia, conectividad y enlaces mas/menos afectados."""
    con = conectar(dsn)
    with con, con.cursor() as cur:
        cur.execute("SELECT count(*) FROM red_edges")
        n_edges = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM red_edges_vertices_pgr")
        n_verts = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM red_edges WHERE es_sintetico")
        n_sint = cur.fetchone()[0]
        print(f"  -> Topologia: {n_verts} vertices, {n_edges} aristas ({n_sint} sinteticas).")
        cur.execute("""SELECT id, tipo, es_sintetico, round(length_m::numeric), round(prob_medio::numeric, 4)
                       FROM red_edges ORDER BY prob_medio DESC LIMIT 5""")
        print("  -> Top 5 enlaces mas vulnerables (escenario medio):")
        for r in cur.fetchall():
            print(f"     id={r[0]} tipo={r[1]} sintetico={r[2]} largo={r[3]}m p={r[4]}")
        cur.execute("""SELECT id, tipo, es_sintetico, round(length_m::numeric), round(prob_medio::numeric, 6)
                       FROM red_edges ORDER BY prob_medio ASC LIMIT 5""")
        print("  -> Top 5 enlaces menos vulnerables (escenario medio):")
        for r in cur.fetchall():
            print(f"     id={r[0]} tipo={r[1]} sintetico={r[2]} largo={r[3]}m p={r[4]}")


def cmd_cargar(a):
    print("Cargando la base de datos ...")
    asegurar_bd(a.dsn)
    for p in PASOS_SQL_1:
        ejecutar_sql(a.dsn, p)
    cargar_sismo(a.dsn)
    for p in PASOS_SQL_2:
        ejecutar_sql(a.dsn, p)
    imprimir_resumen_bd(a.dsn)
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
    import webbrowser
    from mapa import exportar_datos, generar_mapa
    if filas is None:
        filas = calcular_tabla(a.dsn, a.n, a.seed)
    datos = exportar_datos(a.dsn)
    ruta = os.path.join(RAIZ, "output", "mapa.html")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    generar_mapa(datos, filas, ruta)
    print(f"Mapa generado: {ruta}  (necesita internet para Leaflet y el mapa base)")
    if not getattr(a, "no_open", False):
        webbrowser.open(f"file://{os.path.abspath(ruta)}")


def cmd_todo(a):
    cmd_cargar(a)
    filas = cmd_attr(a)
    cmd_mapa(a, filas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=DSN_DEFECTO)
    ap.add_argument("--n", type=int, default=1000, help="simulaciones Monte Carlo (por defecto 1000)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-open", action="store_true", help="no abrir mapa.html en el navegador")
    sub = ap.add_subparsers(dest="cmd")
    for nombre, fn in (("cargar", cmd_cargar), ("attr", cmd_attr), ("mapa", cmd_mapa), ("todo", cmd_todo)):
        sub.add_parser(nombre).set_defaults(fn=fn)
    a = ap.parse_args()
    (a.fn if hasattr(a, "fn") else cmd_todo)(a)


if __name__ == "__main__":
    main()
