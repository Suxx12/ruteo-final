-- Paso 2: nodos clave = una comuna por nodo ("reciben" informacion).
-- Cada comuna se asigna al vertice de la red mas cercano a su punto interior, entre los
-- vertices que caen DENTRO de la comuna. Una comuna sin vertices no es nodo clave de ese escenario.
-- Escenario A: solo vertices de aristas de fibra.  Escenario B: cualquier vertice de la red.
DROP TABLE IF EXISTS nodos_clave;
CREATE TABLE nodos_clave AS
WITH v_tipo AS (
  SELECT source AS v, tipo FROM red_edges
  UNION ALL SELECT target, tipo FROM red_edges
),
esc AS (
  SELECT 'A'::text AS escenario, v FROM v_tipo WHERE tipo = 'fibra' GROUP BY v
  UNION ALL
  SELECT 'B', v FROM v_tipo GROUP BY v
)
SELECT DISTINCT ON (e.escenario, c.cod_comuna)
       e.escenario, c.cod_comuna, c.comuna, vv.id AS vertice,
       ST_Distance(vv.the_geom::geography, ST_PointOnSurface(c.geom)::geography) AS dist_m,
       vv.the_geom
FROM comunas c
JOIN red_edges_vertices_pgr vv ON ST_Within(vv.the_geom, c.geom)
JOIN esc e ON e.v = vv.id
ORDER BY e.escenario, c.cod_comuna, vv.the_geom <-> ST_PointOnSurface(c.geom);
