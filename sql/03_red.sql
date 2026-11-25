-- Paso 3: unir las 4 capas en una sola red, nodar y crear la topologia (pgRouting).
-- La columna tipo permite calcular el escenario A (solo fibra) o B (todas las capas).
-- NOTA: pgr_createTopology esta marcada como obsoleta desde pgRouting 3.8 (sigue funcionando).
CREATE EXTENSION IF NOT EXISTS pgrouting;
DROP TABLE IF EXISTS red_edges_vertices_pgr;
DROP TABLE IF EXISTS red_edges;
DROP TABLE IF EXISTS red_lineas;

CREATE TABLE red_lineas AS
SELECT 'fibra'::text AS tipo, (ST_Dump(ST_Force2D(geom))).geom AS geom FROM fibra
UNION ALL SELECT 'poste',  (ST_Dump(ST_Force2D(geom))).geom FROM postacion
UNION ALL SELECT 'camino', (ST_Dump(ST_Force2D(geom))).geom FROM caminos_sin_postacion
UNION ALL SELECT 'ferry',  (ST_Dump(ST_Force2D(geom))).geom FROM ferry;
CREATE INDEX red_lineas_gix ON red_lineas USING GIST (geom);

-- Nodado (ST_Node) y asignacion de tipo; prioridad fibra > poste > camino > ferry donde se superponen
CREATE TABLE red_edges AS
WITH noded AS (SELECT (ST_Dump(ST_Node(ST_Collect(geom)))).geom AS geom FROM red_lineas)
SELECT row_number() OVER () AS id, n.geom::geometry(LineString,4326) AS geom,
  COALESCE((SELECT r.tipo FROM red_lineas r
            WHERE ST_DWithin(r.geom, ST_LineInterpolatePoint(n.geom,0.5), 0.000001)
            ORDER BY CASE r.tipo WHEN 'fibra' THEN 1 WHEN 'poste' THEN 2
                                 WHEN 'camino' THEN 3 ELSE 4 END LIMIT 1),'desconocido') AS tipo
FROM noded n;

ALTER TABLE red_edges
  ADD source int,
  ADD target int,
  ADD length_m double precision,
  ADD es_sintetico boolean DEFAULT false,
  ADD prob_falla double precision DEFAULT 0;

UPDATE red_edges
SET length_m = ST_Length(geom::geography),
    es_sintetico = (tipo <> 'fibra');

SELECT pgr_createTopology('red_edges', 0.00001, 'geom', 'id');

-- Verificacion de conectividad base (componentes conexas y vertices)
SELECT count(*) AS total_vertices FROM red_edges_vertices_pgr;
SELECT count(DISTINCT component) AS componentes_red_b
FROM pgr_connectedComponents(
  'SELECT id, source, target, 1.0 AS cost, 1.0 AS reverse_cost FROM red_edges'
);
SELECT count(DISTINCT component) AS componentes_red_a_fibra
FROM pgr_connectedComponents(
  'SELECT id, source, target, 1.0 AS cost, 1.0 AS reverse_cost FROM red_edges WHERE tipo = ''fibra'''
);
