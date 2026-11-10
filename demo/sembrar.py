"""Crea un índice de lecturas de placas ficticias y un CSV de vehículos para la demo."""
import csv
import random
from datetime import datetime, timedelta

from elasticsearch import Elasticsearch, helpers

es = Elasticsearch("http://localhost:9200")
random.seed(7)
placas = [f"{random.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}{random.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}{random.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}{random.randint(100, 999)}" for _ in range(2000)]
with open("vehiculos.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["placa", "marca", "linea", "clase"])
    for p in placas[:1800]:  # el 90 % de las placas tiene datos de referencia
        w.writerow([p, random.choice(["Renault", "Chevrolet", "Mazda", "Kia", "Toyota"]), random.choice(["Sedán", "Hatchback", "Campero"]), random.choice(["Automóvil", "Camioneta", "Motocicleta"])])

es.options(ignore_status=404).indices.delete(index="lecturas")
inicio = datetime(2025, 1, 1)
docs = ({"_index": "lecturas", "_id": f"L{i:07d}", "id": f"L{i:07d}", "fecha": (inicio + timedelta(seconds=7 * i)).isoformat(), "placa": random.choice(placas), "camara": f"CAM-{random.randint(1, 40):02d}"} for i in range(100_000))
helpers.bulk(es, docs)
es.indices.refresh(index="lecturas")
es.options(ignore_status=404).indices.delete(index="lecturas-v2")
es.indices.create(index="lecturas-v2", mappings={"properties": {"id": {"type": "keyword"}, "fecha": {"type": "date"}, "placa": {"type": "keyword"}, "camara": {"type": "keyword"}, "vehiculo": {"properties": {"marca": {"type": "keyword"}, "linea": {"type": "keyword"}, "clase": {"type": "keyword"}}}}})
print("Listo: índice 'lecturas' con 100.000 documentos, índice 'lecturas-v2' vacío y vehiculos.csv")
