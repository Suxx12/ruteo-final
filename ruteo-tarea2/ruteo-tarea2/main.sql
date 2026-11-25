-- =====================================================================
-- main.sql  (pasos 6, 7 y 8)
-- Probabilidad de falla de cada enlace de red_edges ante el terremoto
-- Mw 8.8 del Maule (USGS official20100227063411530_30), cargado en la tabla sismo.
--
-- MODELO (supuesto de trabajo, no calibrado con datos de fibra):
--   Tasa de falla por km que decae exponencialmente con la distancia
--   hipocentral d al epicentro:
--        lambda(d) = LAM0 * exp(-d / D0)        [fallas por km]
--   Cada enlace se parte en tramos de <= 5 km; con falla tipo Poisson:
--        P(enlace) = 1 - exp( - SUM_i lambda(d_i) * largo_i )
--   Idea base: la probabilidad de falla es una funcion no creciente de la
--   distancia al epicentro (modelo de falla geografica probabilistica).
--   LAM0 y D0 son parametros; se evaluan 3 escenarios (analisis de sensibilidad).
--
-- LIMITACIONES (declararlas en el informe):
--   * Un sismo Mw 8.8 rompe cientos de km: medir distancia a un punto
--     (epicentro) subestima el dano lejos de el (ej. norte hacia Santiago).
--   * LAM0 y D0 son supuestos; no hay curvas de fragilidad para fibra.
--   * Se aplica la misma formula a todos los tipos de arista (fibra, poste,
--     camino, ferry).
-- Requiere PostGIS >= 3.2 (ST_DumpSegments).
-- =====================================================================

-- 1) Parametros de los escenarios
DROP TABLE IF EXISTS params_falla;
CREATE TABLE params_falla (
  escenario text PRIMARY KEY,
  lam0      double precision,   -- fallas/km en el hipocentro
  d0_km     double precision    -- longitud de decaimiento (km)
);
INSERT INTO params_falla VALUES
  ('bajo',  0.02, 150),
  ('medio', 0.05, 150),
  ('alto',  0.10, 200);

-- 2) Columnas de resultado
ALTER TABLE red_edges ADD COLUMN IF NOT EXISTS prob_bajo  double precision;
ALTER TABLE red_edges ADD COLUMN IF NOT EXISTS prob_medio double precision;
ALTER TABLE red_edges ADD COLUMN IF NOT EXISTS prob_alto  double precision;

-- 3) Calculo
WITH s AS (
  SELECT geom::geography AS epi, prof_km FROM sismo LIMIT 1
),
segs AS (
  SELECT e.id,
         (ST_DumpSegments(ST_Segmentize(e.geom::geography, 5000)::geometry)).geom AS seg
  FROM red_edges e
),
medidas AS (
  SELECT g.id,
         ST_Length(g.seg::geography) / 1000.0 AS len_km,
         SQRT( POWER(ST_Distance(ST_LineInterpolatePoint(g.seg, 0.5)::geography, s.epi) / 1000.0, 2)
             + POWER(s.prof_km, 2) ) AS d_km
  FROM segs g CROSS JOIN s
),
tasas AS (
  SELECT m.id, p.escenario,
         SUM(p.lam0 * EXP(-m.d_km / p.d0_km) * m.len_km) AS lam_total
  FROM medidas m CROSS JOIN params_falla p
  GROUP BY m.id, p.escenario
),
piv AS (
  SELECT id,
         1 - EXP(-MAX(lam_total) FILTER (WHERE escenario = 'bajo'))  AS p_bajo,
         1 - EXP(-MAX(lam_total) FILTER (WHERE escenario = 'medio')) AS p_medio,
         1 - EXP(-MAX(lam_total) FILTER (WHERE escenario = 'alto'))  AS p_alto
  FROM tasas
  GROUP BY id
)
UPDATE red_edges e
SET prob_bajo = piv.p_bajo, prob_medio = piv.p_medio, prob_alto = piv.p_alto
FROM piv
WHERE e.id = piv.id;

-- 4) Verificacion: resumen por tipo (escenario medio)
SELECT tipo,
       count(*)                                                 AS enlaces,
       round(avg(prob_medio)::numeric, 4)                       AS p_media,
       round(max(prob_medio)::numeric, 3)                       AS p_max,
       round((sum(prob_medio * length_m) / 1000)::numeric)      AS km_esperados_fallados,
       round((sum(length_m) / 1000)::numeric)                   AS km_total
FROM red_edges
GROUP BY tipo
ORDER BY tipo;

-- 5) Los 10 enlaces mas vulnerables (escenario medio)
SELECT id, tipo, round(length_m::numeric) AS largo_m, round(prob_medio::numeric, 3) AS p_medio
FROM red_edges
ORDER BY prob_medio DESC
LIMIT 10;
