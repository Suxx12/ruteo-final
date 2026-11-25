"""
attr.py - ATTR (Average Two-Terminal Reliability) de la red de fibra chilena.

Definición usada (Neumayer, tesis MIT 2013, sec. 2.6.2; misma expresión que la
"flow robustness" de Alenazi 2023, ec. 8):

    ATTR = sum_i k_i * (k_i - 1) / (K * (K - 1))

donde K = nº de nodos clave y k_i = nº de nodos clave en la componente conexa i.
Es la fracción de pares de nodos clave que siguen conectados.

Dos modos:
  - determinista: ATTR de la red tal como está (sin fallas)  -> paso 4
  - Monte Carlo:  ATTR esperado cuando cada arista falla con probabilidad
                  prob_falla (columna de la tabla)           -> pasos 7 y 9

Requisitos:  pip install numpy scipy psycopg2-binary
Uso:
  python attr.py --escenario A
  python attr.py --escenario A --prob-col prob_falla --n 1000 --seed 42
"""
import argparse
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

DSN_DEFECTO = "host=localhost port=5432 dbname=resiliencia user=postgres password=postgres"


def attr_desde_etiquetas(labels, key_idx):
    """ATTR dada la etiqueta de componente de cada vértice y los índices de nodos clave.
    Si dos comunas comparten vértice, ambas cuentan (key_idx puede repetir índices)."""
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
    """Devuelve (media, desv_est, IC95_bajo, IC95_alto, vector de ATTR por simulación)."""
    rng = np.random.default_rng(seed)
    vals = np.empty(n_sim)
    for s in range(n_sim):
        vivo = rng.random(len(src)) >= prob          # la arista sobrevive si el dado >= prob_falla
        A = coo_matrix((np.ones(vivo.sum()), (src[vivo], dst[vivo])),
                       shape=(n_vertices, n_vertices))
        _, labels = connected_components(A, directed=False)
        vals[s] = attr_desde_etiquetas(labels, key_idx)
    m, sd = vals.mean(), vals.std(ddof=1)
    h = 1.96 * sd / np.sqrt(n_sim)
    return m, sd, m - h, m + h, vals


def cargar_desde_bd(dsn, escenario, prob_col=None):
    """Lee aristas y nodos clave del escenario ('A' = solo fibra, 'B' = todas las capas)."""
    import psycopg2
    with psycopg2.connect(dsn) as con, con.cursor() as cur:
        filtro = "WHERE tipo = 'fibra'" if escenario == "A" else ""
        col = f", {prob_col}" if prob_col else ""
        cur.execute(f"SELECT source, target{col} FROM red_edges {filtro}")
        filas = cur.fetchall()
        cur.execute("SELECT vertice FROM nodos_clave WHERE escenario = %s ORDER BY cod_comuna",
                    (escenario,))
        claves = [r[0] for r in cur.fetchall()]
    src = np.array([f[0] for f in filas], dtype=np.int64)
    dst = np.array([f[1] for f in filas], dtype=np.int64)
    prob = np.array([f[2] for f in filas], dtype=float) if prob_col else None
    # reindexar ids de vértice a 0..n-1
    ids = np.unique(np.concatenate([src, dst, np.array(claves, dtype=np.int64)]))
    mapa = {v: i for i, v in enumerate(ids)}
    src = np.array([mapa[v] for v in src]); dst = np.array([mapa[v] for v in dst])
    key_idx = np.array([mapa[v] for v in claves])
    return len(ids), src, dst, prob, key_idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=DSN_DEFECTO)
    ap.add_argument("--escenario", choices=["A", "B"], required=True)
    ap.add_argument("--prob-col", default=None, help="columna de probabilidad de falla de red_edges")
    ap.add_argument("--n", type=int, default=1000, help="simulaciones Monte Carlo")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    n, src, dst, prob, key_idx = cargar_desde_bd(a.dsn, a.escenario, a.prob_col)
    print(f"Escenario {a.escenario}: {n} vértices, {len(src)} aristas, {len(key_idx)} nodos clave")
    print(f"ATTR en operación (sin fallas): {attr_determinista(n, src, dst, key_idx):.4f}")
    if prob is not None:
        m, sd, lo, hi, _ = attr_montecarlo(n, src, dst, prob, key_idx, a.n, a.seed)
        print(f"ATTR post-sismo (Monte Carlo, N={a.n}): {m:.4f}  (IC95% {lo:.4f} - {hi:.4f}, sd {sd:.4f})")


if __name__ == "__main__":
    main()
