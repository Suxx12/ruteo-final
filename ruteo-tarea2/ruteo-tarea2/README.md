# Resiliencia de la Internet chilena ante el terremoto Mw 8.8 del Maule (2010)

Tarea de Algoritmos de Ruteo (UDP). Calcula el **ATTR** (Average Two-Terminal Reliability) de la
infraestructura de Internet chilena **antes y después** del terremoto del Maule, a partir de un modelo
de falla probabilístico centrado en el epicentro, y muestra el daño en un mapa Leaflet.

## Cómo ejecutarlo

Requisitos: Docker Desktop, Python 3.10+.

```powershell
docker compose up -d                 # PostgreSQL 15 + PostGIS 3.5 + pgRouting 3.8
pip install -r requirements.txt
# opcional: copiar sismo_maule.geojson a data/ (si no está, main.py intenta bajarlo de USGS)
python main.py todo                  # cargar BD + ATTR antes/después + mapa
```

Subcomandos: `python main.py cargar | attr | mapa | todo`. Conexión por `--dsn` o la variable
`RESILIENCIA_DSN` (por defecto `localhost:5432`, base `resiliencia`, usuario/clave `postgres`).
Salidas: `output/attr_resultados.csv` y `output/mapa.html` (el mapa necesita internet al abrirse).

## Estructura

| Archivo | Paso de la tarea |
|---|---|
| `sql/01_capas.sql` | 1. Infraestructura (4 capas de `Respuesta_T5610.zip`: fibra, postación, caminos sin postación, ferry) |
| `sql/02_comunas.sql` | Comunas (346), reproyectadas a WGS84 y simplificadas (~50 m) |
| `main.py` (`cargar_sismo`) | 5. Sismo M 8.8 desde el GeoJSON de USGS |
| `sql/03_red.sql` | 3. Unión de capas, nodado (`ST_Node`) y topología con `pgr_createTopology` |
| `sql/04_nodos_clave.sql` | 2. Nodos clave (comunas asignadas a vértices de la red) |
| `main.sql` | 6, 7 y 8. Modelo de falla y probabilidades por enlace |
| `attr.py` | 4 y 9. ATTR en operación (determinista) y post-sismo (Monte Carlo) |
| `mapa.py` | 10. Mapa Leaflet |

## Definición de ATTR

ATTR = Σ kᵢ(kᵢ−1) / (K(K−1)), con K = nodos clave y kᵢ = nodos clave de la componente conexa i
(fracción de pares de nodos clave conectados; Neumayer, tesis MIT 2013; misma expresión que la
"flow robustness" del paper ENRN). Con fallas probabilísticas se estima por Monte Carlo
(1.000 simulaciones: cada enlace sobrevive si un número U(0,1) ≥ su probabilidad de falla).

## Redes evaluadas

- **A – solo fibra** (288 nodos clave): lo más cercano a "infraestructura en operación".
- **B – fibra + postes + caminos + ferry** (314 nodos clave): red *potencial*; supone fibra en los
  postes y caminos de las capas entregadas.

Nodos clave: una comuna = un nodo (el vértice de la red dentro de la comuna más cercano a su punto
interior). Comunas sin red en el escenario quedan fuera (58 sin fibra, 32 sin ninguna capa).

## Modelo de falla (supuesto de trabajo)

Tasa de falla por km decreciente con la distancia hipocentral *d* al epicentro (USGS: 36,122°S
72,898°W, 22,9 km): λ(d) = λ₀·exp(−d/d₀). Cada enlace se parte en tramos de ≤ 5 km y
P(enlace) = 1 − exp(−Σ λ(dᵢ)·largoᵢ). Se evalúan tres escenarios:

| escenario | λ₀ (fallas/km) | d₀ (km) |
|---|---|---|
| bajo | 0,02 | 150 |
| medio | 0,05 | 150 |
| alto | 0,10 | 200 |

**λ₀ y d₀ son supuestos, no están calibrados con datos de fibra.** La forma "probabilidad de falla
no creciente con la distancia al epicentro" corresponde a los modelos de fallas geográficas
probabilísticas de la literatura (Agarwal et al., citados en ENRN y en Neumayer); no se replicó su
función exacta.

## Resultados de referencia (Monte Carlo N = 1000, semilla 42)

| Red | ATTR en operación | bajo | medio | alto |
|---|---|---|---|---|
| A (solo fibra) | 0,0484 | 0,0306 (−37 %) | 0,0206 (−57 %) | 0,0085 (−82 %) |
| B (todas las capas) | 0,5546 | 0,2706 (−51 %) | 0,1371 (−75 %) | 0,0503 (−91 %) |

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

## Pendiente de confirmar con el profesor

1. Si los nodos clave son comunas.
2. Si "infraestructura en operación" es solo fibra (red A) o incluye postes, caminos y ferry (red B).
3. Si `main.sql` debe contener solo la lógica de cálculo o también los valores resultantes.

## Fuentes

- Estudio y Recomendaciones sobre la Resiliencia de la infraestructura de la Internet chilena (SUBTEL / Yafun).
- ENRN: A System for Evaluating Network Resilience against Natural Disasters (paper del módulo de Canvas).
- Neumayer, S. (2013). Tesis doctoral, MIT (definición de ATTR).
- USGS: evento `official20100227063411530_30` (M 8.8, Maule, 2010).
- Montalva, Bastías y Rodriguez-Marek (2017), BSSA 107(2): GMPE para la zona de subducción chilena
  (revisada como alternativa; no se usa en el modelo).
