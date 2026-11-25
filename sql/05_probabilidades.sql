-- =====================================================================
-- 05_probabilidades.sql  (pasos 6, 7 y 8)
-- Probabilidad de falla de cada enlace de red_edges ante el terremoto
-- Mw 8.8 del Maule (USGS official20100227063411530_30), cargado en la tabla sismo.
--
-- MODELO DE FALLA (respaldado en literatura sismica y de redes vitales):
--   1) Atenuacion GMPE para subduccion interplaca en suelo (Youngs et al., 1997,
--      SRL 68(1), Z_T = 0):
--        ln(PGA) = -0.6687 + 1.438*Mw - 2.329*ln(d + 1.097*exp(0.617*Mw)) + 0.00648*H
--      donde PGA esta en g, d es la distancia hipocentral en km y H = prof_km.
--   2) Conversion PGA -> PGV en suelo (Newmark & Hall, 1982 / HAZUS-MH):
--        PGV [cm/s] = 100 * PGA [g]
--   3) Curva de fragilidad para redes lineales (ALA, 2001):
--        RR(d) = K1 * 0.00187 * PGV(d)   [fallas por km]
--      donde K1 es el factor de material/ductilidad:
--        bajo: K1 = 0.3 (ductos ductiles HDPE/protegidos)
--        medio: K1 = 0.5 (referencia ductos ductiles/fibra troncal)
--        alto: K1 = 1.0 (tendido estandar/mayor vulnerabilidad)
--   4) Probabilidad de falla del enlace (proceso de Poisson por tramos <= 5 km):
--        P(enlace) = 1 - exp( - SUM_i RR(d_i) * largo_i )
--
-- Requiere PostGIS >= 3.2 (ST_DumpSegments).
-- =====================================================================

-- 1) Parametros de los escenarios (factor K1 de ALA, 2001)
DROP TABLE IF EXISTS params_falla;
CREATE TABLE params_falla (
  escenario text PRIMARY KEY,
  k1        double precision    -- factor de vulnerabilidad/material (ALA, 2001)
);
INSERT INTO params_falla VALUES
  ('bajo',  0.3),
  ('medio', 0.5),
  ('alto',  1.0);

-- 2) Columnas de resultado
ALTER TABLE red_edges ADD COLUMN IF NOT EXISTS prob_bajo  double precision;
ALTER TABLE red_edges ADD COLUMN IF NOT EXISTS prob_medio double precision;
ALTER TABLE red_edges ADD COLUMN IF NOT EXISTS prob_alto  double precision;

-- 3) Calculo (Youngs et al. 1997 -> Newmark & Hall 1982 -> ALA 2001)
WITH s AS (
  SELECT geom::geography AS epi, mag, prof_km FROM sismo LIMIT 1
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
             + POWER(s.prof_km, 2) ) AS d_km,
         s.mag,
         s.prof_km
  FROM segs g CROSS JOIN s
),
movimiento AS (
  SELECT m.id,
         m.len_km,
         100.0 * EXP(
           -0.6687
           + 1.438 * m.mag
           - 2.329 * LN(m.d_km + 1.097 * EXP(0.617 * m.mag))
           + 0.00648 * m.prof_km
         ) AS pgv_cms
  FROM medidas m
),
tasas AS (
  SELECT mv.id, p.escenario,
         SUM(p.k1 * 0.00187 * mv.pgv_cms * mv.len_km) AS rr_total
  FROM movimiento mv CROSS JOIN params_falla p
  GROUP BY mv.id, p.escenario
),
piv AS (
  SELECT id,
         1 - EXP(-MAX(rr_total) FILTER (WHERE escenario = 'bajo'))  AS p_bajo,
         1 - EXP(-MAX(rr_total) FILTER (WHERE escenario = 'medio')) AS p_medio,
         1 - EXP(-MAX(rr_total) FILTER (WHERE escenario = 'alto'))  AS p_alto
  FROM tasas
  GROUP BY id
)
UPDATE red_edges e
SET prob_bajo = piv.p_bajo,
    prob_medio = piv.p_medio,
    prob_alto = piv.p_alto,
    prob_falla = piv.p_medio
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
SELECT id, tipo, es_sintetico, round(length_m::numeric) AS largo_m, round(prob_medio::numeric, 4) AS p_medio
FROM red_edges
ORDER BY prob_medio DESC
LIMIT 10;

-- 6) Los 10 enlaces menos vulnerables (escenario medio)
SELECT id, tipo, es_sintetico, round(length_m::numeric) AS largo_m, round(prob_medio::numeric, 6) AS p_medio
FROM red_edges
ORDER BY prob_medio ASC
LIMIT 10;
