# Resiliencia de la Internet chilena ante el terremoto Mw 8.8 del Maule (2010)

Tarea de Algoritmos de Ruteo (UDP). Calcula el **ATTR** (Average Two-Terminal Reliability) de la
infraestructura de Internet chilena **antes y después** del terremoto del Maule, a partir de un modelo
de falla probabilístico centrado en el epicentro, y muestra el daño en un mapa Leaflet.

## Cómo ejecutarlo

Requisitos: Docker Desktop, Python 3.10+.

```powershell
docker compose up -d                 # PostgreSQL 15 + PostGIS 3.5 + pgRouting 3.8
pip install -r requirements.txt
python main.py                       # crea/carga BD + topología + probabilidades + ATTR + abre mapa Leaflet
```

Subcomandos opcionales: `python main.py cargar | attr | mapa | todo` (sin argumentos ejecuta `todo`). Conexión por `--dsn` o la variable
`RESILIENCIA_DSN` (por defecto `localhost:5432`, base `resiliencia`, usuario/clave `postgres`).
Salidas: `output/attr_resultados.csv` y `output/mapa.html` (el mapa necesita internet al abrirse).

## Estructura

| Archivo | Paso de la tarea |
|---|---|
| `sql/01_capas.sql` | 1. Infraestructura (4 capas de `Respuesta_T5610.zip`: fibra, postación, caminos sin postación, ferry) |
| `sql/02_comunas.sql` | Comunas (346), reproyectadas a WGS84 y simplificadas (~50 m) |
| `main.py` (`cargar_sismo`) | 5. Sismo M 8.8 desde el GeoJSON de USGS |
| `sql/03_red.sql` | 3. Unión de capas, nodado (`ST_Node`), marca de enlaces sintéticos, `prob_falla=0` y `pgr_createTopology` |
| `sql/04_nodos_clave.sql` | 2. Nodos clave (comunas asignadas a vértices de la red) |
| `sql/05_probabilidades.sql` | 6, 7 y 8. Modelo de falla y probabilidades por enlace (usado por `main.py`) |
| `main.sql` | Script SQL autocontenido completo (infraestructura + topología + sismo + probabilidades; carga en BD vacía) |
| `attr.py` | 4 y 9. ATTR en operación (determinista) y post-sismo (Monte Carlo) |
| `mapa.py` | 10. Mapa Leaflet |

## Dependencias y librerías

- **Docker (`pgrouting/pgrouting:15-3.5-3.8`)**: PostgreSQL 15 + PostGIS 3.5 + pgRouting 3.8 para almacenar geometrías WGS84, calcular distancias geodésicas (`ST_Distance`) y construir la topología (`pgr_createTopology`, `pgr_connectedComponents`).
- **`psycopg2-binary`**: conector de Python a PostgreSQL para automatizar la carga de SQL, la ingesta del GeoJSON y las consultas de enlaces/nodos.
- **`numpy`**: generación vectorizada de números aleatorios `U(0, 1)` y conteo de nodos clave por componente (`np.bincount`) en las simulaciones de Monte Carlo.
- **`scipy` (`scipy.sparse.csgraph.connected_components`)**: cálculo eficiente de componentes conexas sobre grafos dispersos en cada iteración de Monte Carlo (1.000 corridas en segundos).
- **Leaflet 1.9.4 (CDN `unpkg.com`)**: renderizado interactivo del mapa web en `output/mapa.html` con capas de fibra real, enlaces sintéticos, nodos clave y epicentro.

## Definición de ATTR

ATTR = Σ kᵢ(kᵢ−1) / (K(K−1)), con K = nodos clave y kᵢ = nodos clave de la componente conexa i
(fracción de pares de nodos clave conectados; Neumayer, tesis MIT 2013; misma expresión que la
"flow robustness" del paper ENRN). Con fallas probabilísticas se estima por Monte Carlo
(**N = 1.000** simulaciones: cada enlace sobrevive si un número U(0,1) ≥ su probabilidad de falla).
Se elige N = 1.000 porque acota el error estándar teórico a `SE ≤ 1/(2√N) ≈ 0,0158` y en la práctica
produce semi-anchos de IC 95 % ≤ 0,0053, equilibrando precisión estadística y tiempo de cómputo.

## Redes evaluadas

- **A – solo fibra** (288 nodos clave): lo más cercano a "infraestructura en operación".
- **B – fibra + postes + caminos + ferry** (314 nodos clave): red *potencial*; supone fibra en los
  postes y caminos de las capas entregadas.

Nodos clave: una comuna = un nodo (el vértice de la red dentro de la comuna más cercano a su punto
interior). Comunas sin red en el escenario quedan fuera (58 sin fibra, 32 sin ninguna capa).

## Modelo de falla sísmica

Cadena estándar de dos pasos respaldada en literatura sísmica y de redes vitales (sin parámetros inventados):

1. **Atenuación GMPE (Youngs et al., 1997)** para sismos de subducción interplaca en suelo ($Z_T = 0$, $M_w = 8{,}8$, $H = 22{,}9\text{ km}$):
   `ln(PGA) = -0.6687 + 1.438*Mw - 2.329*ln(d + 1.097*exp(0.617*Mw)) + 0.00648*H` (con `d` distancia hipocentral en km y `PGA` en *g*).
2. **Conversión PGA → PGV (Newmark & Hall, 1982 / HAZUS-MH)**: `PGV [cm/s] = 100 * PGA [g]`.
3. **Curva de fragilidad para redes lineales (ALA, 2001)**: `RR(d) = K1 * 0.00187 * PGV(d)` [fallas/km].
4. **Probabilidad por enlace (Poisson)**: cada enlace se segmenta en tramos ≤ 5 km y `P(enlace) = 1 − exp(−Σ RR(dᵢ)·largoᵢ)`.

Escenarios variando el factor de ductilidad/material `K1` de ALA (2001):

| escenario | K1 (ALA, 2001) | Interpretación |
|---|---|---|
| bajo | 0,3 | Ductos dúctiles HDPE / tendido protegido |
| medio | 0,5 | Referencia estándar para ductos dúctiles / fibra troncal |
| alto | 1,0 | Tendido estándar / mayor vulnerabilidad |

## Resultados de referencia (Monte Carlo N = 1000, semilla 42)

| Red | ATTR en operación | bajo | medio | alto |
|---|---|---|---|---|
| A (solo fibra) | 0,0484 | 0,0244 (−50 %) | 0,0178 (−63 %) | 0,0104 (−79 %) |
| B (todas las capas) | 0,5546 | 0,1912 (−66 %) | 0,1130 (−80 %) | 0,0509 (−91 %) |

La caída es grande en todos los escenarios porque la red es casi una cadena norte-sur sin caminos
alternos; la **magnitud** depende de los parámetros supuestos, la **dirección** no. Los intervalos de
confianza miden solo el error de la simulación, no la incertidumbre del modelo.

## Limitaciones

- El Maule rompió cientos de km; medir distancia a un punto (epicentro, como pide el enunciado)
  subestima el daño lejos de él. En un caso profesional se usaría el modelo de falla finita.
- λ₀ y d₀ son supuestos (ver arriba); no hay curvas de fragilidad publicadas para fibra aérea.
- Monte Carlo sortea cada enlace de forma independiente; en un sismo las fallas están correlacionadas
  espacialmente (la geometría importa).
- Solo se modelan fallas de enlaces; el informe del estudio atribuye la caída de Internet de 2010 a la
  interconexión en Santiago (fallas de nodos), que no se modela.
- La red A está muy fragmentada (muchas componentes aisladas), por eso su ATTR base es bajo (≈ 5 %).
- `ST_Node` conecta cruces de líneas que podrían no estar unidas físicamente.
- La misma fórmula se aplica a todos los tipos de arista (incluido el ferry).
- `pgr_createTopology` está marcada como obsoleta desde pgRouting 3.8 (aquí sigue funcionando).
- El punto de cada comuna es el vértice de red más cercano a su punto interior (el informe usó la
  plaza de armas): en comunas muy grandes puede quedar lejos del casco urbano.

## Fuentes

- Estudio y Recomendaciones sobre la Resiliencia de la infraestructura de la Internet chilena (SUBTEL / Yafun).
- ENRN: A System for Evaluating Network Resilience against Natural Disasters (paper del módulo de Canvas).
- Neumayer, S. (2013). Tesis doctoral, MIT (definición de ATTR).
- USGS: evento `official20100227063411530_30` (M 8.8, Maule, 2010).
- Montalva, Bastías y Rodriguez-Marek (2017), BSSA 107(2): GMPE para la zona de subducción chilena
  (revisada como alternativa; no se usa en el modelo).
