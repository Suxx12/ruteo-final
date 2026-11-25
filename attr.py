"""
attr.py - ATTR (Average Two-Terminal Reliability) de la red de Internet chilena.

Definicion (Neumayer, tesis MIT 2013, sec. 2.6.2; misma expresion que la
"flow robustness" de Alenazi 2023, ec. 8):

    ATTR = sum_i k_i * (k_i - 1) / (K * (K - 1))

K = numero de nodos clave; k_i = nodos clave en la componente conexa i.
Es la fraccion de pares de nodos clave que siguen conectados.

  - determinista: ATTR de la red en operacion (sin fallas)        -> paso 4
  - Monte Carlo : ATTR esperado si cada arista falla con prob_falla -> pasos 7 y 9

Uso rapido:
  python attr.py --escenario A
  python attr.py --escenario B --prob-col prob_medio --n 1000 --seed 42
"""
import argparse
import os

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

DSN_DEFECTO = os.environ.get(
    "RESILIENCIA_DSN",
    "host=localhost port=5432 dbname=resiliencia user=postgres password=postgres",
)
# escenarios del modelo de falla -> columna de red_edges (ver main.sql)
PROB_COLS = {"bajo": "prob_bajo", "medio": "prob_medio", "alto": "prob_alto"}


def attr_desde_etiquetas(labels, key_idx):
    """ATTR dada la componente de cada vertice y los indices de los nodos clave.
    Si dos comunas comparten vertice, ambas cuentan (key_idx puede repetir indices)."""
    K = len(key_idx)
    if K < 2:
        return float("nan")
    k = np.bincount(labels[key_idx])
    return float(np.sum(k * (k - 1)) / (K * (K - 1)))


def attr_determinista(n_vertices, src, dst, key_idx):
    A = coo_matrix((np.ones(len(src)), (src, dst)), shape=(n_vertices, n_vertices))
    _, labels = connected_components(A, directed=False)
    return attr_desde_etiquetas(labels, key_idx)


def attr_montecarlo(n_vertices, src, dst, prob, key_idx, n_sim=1000, seed=42):
    """Monte Carlo: en cada simulacion la arista e sobrevive si un dado U(0,1) >= prob[e].
    Devuelve dict con media, sd, IC95 de la media, percentiles 5/50/95 y todos los valores."""
    rng = np.random.default_rng(seed)
    vals = np.empty(n_sim)
    for s in range(n_sim):
        vivo = rng.random(len(src)) >= prob
        A = coo_matrix((np.ones(int(vivo.sum())), (src[vivo], dst[vivo])),
                       shape=(n_vertices, n_vertices))
        _, labels = connected_components(A, directed=False)
        vals[s] = attr_desde_etiquetas(labels, key_idx)
    media = float(vals.mean())
    sd = float(vals.std(ddof=1)) if n_sim > 1 else 0.0
    h = 1.96 * sd / np.sqrt(n_sim)
    p5, p50, p95 = (float(x) for x in np.percentile(vals, [5, 50, 95]))
    return {"media": media, "sd": sd, "ic_lo": media - h, "ic_hi": media + h,
            "p5": p5, "p50": p50, "p95": p95, "vals": vals}


def cargar_desde_bd(dsn, escenario, prob_cols=()):
    """Lee aristas y nodos clave del escenario ('A' = solo fibra, 'B' = todas las capas).
    Devuelve (n_vertices, src, dst, {columna: probabilidades}, key_idx)."""
    import psycopg2  # import perezoso: solo hace falta al usar la BD
    cols = "".join(f", {c}" for c in prob_cols)
    filtro = "WHERE tipo = 'fibra'" if escenario == "A" else ""
    with psycopg2.connect(dsn) as con, con.cursor() as cur:
        cur.execute(f"SELECT source, target{cols} FROM red_edges {filtro}")
        filas = cur.fetchall()
        cur.execute("SELECT vertice FROM nodos_clave WHERE escenario = %s ORDER BY cod_comuna",
                    (escenario,))
        claves = [r[0] for r in cur.fetchall()]
    src = np.array([f[0] for f in filas], dtype=np.int64)
    dst = np.array([f[1] for f in filas], dtype=np.int64)
    probs = {c: np.array([f[2 + i] for f in filas], dtype=float) for i, c in enumerate(prob_cols)}
    ids = np.unique(np.concatenate([src, dst, np.array(claves, dtype=np.int64)]))
    mapa = {v: i for i, v in enumerate(ids)}
    src = np.array([mapa[v] for v in src])
    dst = np.array([mapa[v] for v in dst])
    key_idx = np.array([mapa[v] for v in claves])
    return len(ids), src, dst, probs, key_idx


def calcular_tabla(dsn=DSN_DEFECTO, n_sim=1000, seed=42):
    """Tabla de resultados: ATTR antes y despues, por red (A/B) y escenario del modelo."""
    filas = []
    for red in ("A", "B"):
        n, src, dst, probs, key_idx = cargar_desde_bd(dsn, red, tuple(PROB_COLS.values()))
        pre = attr_determinista(n, src, dst, key_idx)
        for modelo, col in PROB_COLS.items():
            r = attr_montecarlo(n, src, dst, probs[col], key_idx, n_sim, seed)
            filas.append({
                "red": red, "modelo": modelo, "nodos_clave": len(key_idx),
                "attr_antes": pre, "attr_despues": r["media"],
                "ic95_lo": r["ic_lo"], "ic95_hi": r["ic_hi"], "sd": r["sd"],
                "p5": r["p5"], "p50": r["p50"], "p95": r["p95"],
                "cambio_relativo": r["media"] / pre - 1 if pre > 0 else float("nan"),
            })
    return filas


def main():
    ap = argparse.ArgumentParser(description="ATTR antes/despues para un escenario de red")
    ap.add_argument("--dsn", default=DSN_DEFECTO)
    ap.add_argument("--escenario", choices=["A", "B"], required=True,
                    help="A = solo fibra, B = fibra + postes + caminos + ferry")
    ap.add_argument("--prob-col", default=None,
                    help="columna de probabilidad de red_edges (prob_bajo | prob_medio | prob_alto)")
    ap.add_argument("--n", type=int, default=1000, help="simulaciones Monte Carlo")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    cols = (a.prob_col,) if a.prob_col else ()
    n, src, dst, probs, key_idx = cargar_desde_bd(a.dsn, a.escenario, cols)
    print(f"Escenario {a.escenario}: {n} vertices, {len(src)} aristas, {len(key_idx)} nodos clave")
    print(f"ATTR en operacion (sin fallas): {attr_determinista(n, src, dst, key_idx):.4f}")
    if a.prob_col:
        r = attr_montecarlo(n, src, dst, probs[a.prob_col], key_idx, a.n, a.seed)
        print(f"ATTR post-sismo (Monte Carlo, N={a.n}): {r['media']:.4f}  "
              f"(IC95% {r['ic_lo']:.4f} - {r['ic_hi']:.4f}, sd {r['sd']:.4f})")
        print(f"  percentiles 5/50/95 de una realizacion: {r['p5']:.4f} / {r['p50']:.4f} / {r['p95']:.4f}")


if __name__ == "__main__":
    main()
