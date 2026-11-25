# Resiliencia de la Internet chilena (ATTR - Terremoto del Maule 2010)

Cálculo del ATTR (*Average Two-Terminal Reliability*) antes y después del terremoto Mw 8,8 del Maule usando PostGIS, pgRouting, Monte Carlo (N = 1.000, semilla 42) y visualización en Leaflet.

## Ejecución
Requisitos: Docker Desktop y Python 3.10+.

```bash
docker compose up -d
pip install -r requirements.txt
python main.py
```

`python main.py` ejecuta todo el flujo en un solo comando: crea y carga la BD, construye la topología, calcula las probabilidades de falla (Youngs et al. 1997 + ALA 2001), obtiene los ATTR y abre el mapa en `output/mapa.html` (requiere internet para cargar el mapa base). También guarda los resultados en `output/attr_resultados.csv`.

*(Subcomandos opcionales: `cargar`, `attr`, `mapa`, `todo`. Conexión por `--dsn` o variable `RESILIENCIA_DSN`; por defecto `localhost:5432`, BD `resiliencia`, usuario/clave `postgres`).*

## Estructura del repositorio
| Archivo | Descripción |
| :--- | :--- |
| `main.py` | Orquesta el flujo completo en un solo comando. |
| `main.sql` | Script autocontenido (infraestructura, sismo, topología y probabilidades; carga en BD vacía). |
| `sql/01_capas.sql` a `05_probabilidades.sql` | Scripts modulares ejecutados por `main.py` (capas SAIP, comunas, `pgr_createTopology`, nodos clave y modelo de falla). |
| `attr.py` | Cálculo de ATTR determinista (en operación) y post-sismo (Monte Carlo). |
| `mapa.py` | Generación del mapa interactivo en Leaflet (`output/mapa.html`). |

## Dependencias y librerías
* **Docker (`pgrouting/pgrouting:15-3.5-3.8`):** PostgreSQL 15 + PostGIS 3.5 + pgRouting 3.8 para geometrías WGS84, distancias geodésicas (`ST_Distance`) y topología (`pgr_createTopology`, `pgr_connectedComponents`).
* **psycopg2-binary:** Conexión de Python a PostgreSQL para carga de SQL, ingesta del GeoJSON de USGS y consultas.
* **numpy:** Generación vectorizada de números aleatorios U(0,1) y conteo por componente en Monte Carlo.
* **scipy (`csgraph.connected_components`):** Cálculo rápido de componentes conexas sobre grafos dispersos.
* **Leaflet 1.9.4 (CDN):** Renderizado del mapa web con fibra real, enlaces sintéticos, nodos clave y epicentro.

## Resultados de referencia
| Red | ATTR en operación | Bajo (K1 = 0,3) | Medio (K1 = 0,5) | Alto (K1 = 1,0) |
| :--- | :---: | :---: | :---: | :---: |
| **A** (solo fibra, K = 288) | 0,0484 | 0,0244 (−50 %) | 0,0178 (−63 %) | 0,0104 (−79 %) |
| **B** (todas las capas, K = 314) | 0,5546 | 0,1912 (−66 %) | 0,1130 (−80 %) | 0,0509 (−91 %) |
