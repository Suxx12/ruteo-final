# Resiliencia de la Internet chilena (ATTR - Terremoto del Maule 2010)

Cálculo del ATTR (*Average Two-Terminal Reliability*) antes y después del terremoto Mw 8,8 del Maule usando PostGIS, pgRouting, Monte Carlo ($N=1000$, semilla 42) y visualización en Leaflet.

## Ejecución
Requisitos: Docker Desktop y Python 3.10+.

```bash
docker compose up -d
pip install -r requirements.txt
python main.py
