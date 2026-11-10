"""Línea de comandos del reindexador."""
from __future__ import annotations

import argparse
import logging
import os

from .core import Reindexador
from .enriquecimiento import TablaDeReferencia


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="reindexar", description="Reindexa un índice de Elasticsearch por lotes, con puntos de control.")
    p.add_argument("origen")
    p.add_argument("destino")
    p.add_argument("--es", default=os.environ.get("ES_URL", "http://localhost:9200"), help="URL de Elasticsearch (o ES_URL)")
    p.add_argument("--orden", default="fecha,id", help="Campos de orden estables, separados por coma (por defecto fecha,id)")
    p.add_argument("--lote", type=int, default=5000)
    p.add_argument("--control", default="reindex.control.json", help="Archivo del punto de control")
    p.add_argument("--csv", help="CSV de referencia para enriquecer")
    p.add_argument("--llave-csv", default="placa")
    p.add_argument("--campo", default="placa", help="Campo del documento que se cruza con la llave del CSV")
    p.add_argument("--destino-enriquecimiento", default="vehiculo")
    p.add_argument("--max-lotes", type=int, help="Detenerse después de N lotes (útil para probar)")
    p.add_argument("--simulacion", action="store_true", help="Lee y enriquece, pero no escribe")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from elasticsearch import Elasticsearch  # importación tardía: el núcleo no depende del cliente

    es = Elasticsearch(args.es, api_key=os.environ.get("ES_API_KEY"), request_timeout=120)
    enriquecer = TablaDeReferencia(args.csv, args.llave_csv, args.campo, args.destino_enriquecimiento) if args.csv else None
    control = Reindexador(
        es, args.origen, args.destino, args.orden.split(","), args.control, args.lote,
        enriquecer=enriquecer, simulacion=args.simulacion,
    ).ejecutar(args.max_lotes)
    estado = "terminado" if control.terminado else "pausado (vuelve a ejecutar para continuar)"
    print(f"{estado}: {control.leidos} leídos, {control.indexados} indexados, {control.fallidos} fallidos, "
          f"{control.tasa_enriquecimiento:.1%} enriquecidos")
    return 0 if control.fallidos == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
