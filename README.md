# es-reindexador

Reindexa un índice de Elasticsearch por lotes, con puntos de control para continuar donde se quedó y con enriquecimiento opcional desde una tabla de referencia.

> **In English:** a Python tool that reindexes an Elasticsearch index in batches using Point in Time + `search_after`, saves a checkpoint after every batch so a crashed run resumes where it stopped, and can enrich each document from a CSV lookup table on the way.

Es la versión genérica, con datos ficticios, del enfoque que usé para reindexar 2.624 millones de lecturas de cámaras de placas (LPR) en Medellín y enriquecer el 93,6 % con datos del registro de vehículos.

## Por qué no basta con `_reindex`

La API `_reindex` de Elasticsearch es cómoda, pero en reindexaciones de miles de millones de documentos:

- si el proceso se cae, no hay forma limpia de continuar desde donde iba;
- no permite cruzar cada documento con datos externos (un CSV, una base de datos) sin un pipeline de ingesta aparte;
- no deja un registro claro de qué documentos fallaron y por qué.

Este reindexador lee con Point in Time y `search_after` sobre campos de orden estables, escribe con la API bulk y guarda un punto de control atómico después de cada lote confirmado.

## Cómo funciona

```text
índice origen ──PIT + search_after──► lote ──enriquecer──► bulk ──► índice destino
                                         │
                                         └─► punto de control (JSON) después de cada lote
```

- **Orden estable:** el orden se define con campos que juntos son únicos (por defecto `fecha,id`). Por eso un punto de control sigue sirviendo aunque el PIT haya vencido.
- **Escritura atómica del control:** se escribe a un archivo temporal y se reemplaza; nunca queda un control a medias.
- **Idempotente:** cada documento conserva su `_id`, así que repetir un lote no crea duplicados.
- **Fallidos aparte:** los documentos que el destino rechaza (por ejemplo, por mapeo) quedan en `*.fallidos.jsonl` con el error, sin detener el proceso.

## Uso

```bash
pip install git+https://github.com/Davidgraciano/es-reindexador.git

reindexar lecturas lecturas-v2 \
  --es http://localhost:9200 \
  --orden fecha,id \
  --lote 5000 \
  --csv vehiculos.csv --llave-csv placa --campo placa --destino-enriquecimiento vehiculo
```

Si se interrumpe, vuelve a ejecutar el mismo comando: continúa desde el último lote. Para probar con pocos lotes usa `--max-lotes 3`, y para leer y enriquecer sin escribir, `--simulacion`.

Desde Python:

```python
from elasticsearch import Elasticsearch
from reindexador import Reindexador, TablaDeReferencia

es = Elasticsearch("http://localhost:9200")
vehiculos = TablaDeReferencia("vehiculos.csv", llave_csv="placa", campo_doc="placa", destino="vehiculo")
control = Reindexador(es, "lecturas", "lecturas-v2", ["fecha", "id"], "reindex.control.json", lote=5000, enriquecer=vehiculos).ejecutar()
print(control.indexados, f"{control.tasa_enriquecimiento:.1%}")
```

## Demo local

```bash
cd demo
docker compose up -d          # Elasticsearch de un nodo, sin seguridad
pip install -e ..
python sembrar.py             # 100.000 lecturas ficticias y vehiculos.csv
reindexar lecturas lecturas-v2 --csv vehiculos.csv --lote 10000
```

Las placas y los vehículos de la demo son aleatorios; no hay datos reales.

## Pruebas

Las pruebas usan un Elasticsearch falso en memoria, así que no necesitan Docker:

```bash
pip install -e ".[dev]"
pytest
```

Cubren la reindexación completa, la continuación después de una caída, la pausa por número de lotes, el registro de fallidos, el enriquecimiento y el modo simulación.

## Licencia

MIT
