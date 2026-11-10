"""Reindexación por lotes con puntos de control y enriquecimiento opcional.

Lee el índice de origen con un Point in Time (PIT) y `search_after` sobre campos de
orden estables, escribe cada lote en el índice de destino con la API bulk y guarda
un punto de control después de cada lote. Si el proceso se detiene, al volver a
ejecutarlo continúa desde el último lote confirmado, sin repetir trabajo.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

log = logging.getLogger(__name__)

Documento = dict[str, Any]


class Enriquecedor(Protocol):
    def __call__(self, doc: Documento) -> bool:
        """Modifica el documento en sitio y devuelve True si lo pudo enriquecer."""


@dataclass
class PuntoDeControl:
    origen: str
    destino: str
    search_after: list[Any] | None = None
    leidos: int = 0
    indexados: int = 0
    enriquecidos: int = 0
    fallidos: int = 0
    terminado: bool = False
    actualizado: float = field(default_factory=time.time)

    @classmethod
    def cargar(cls, ruta: Path, origen: str, destino: str) -> "PuntoDeControl":
        if ruta.exists():
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            if (datos["origen"], datos["destino"]) != (origen, destino):
                raise ValueError(f"El punto de control {ruta} es de {datos['origen']} → {datos['destino']}, no de {origen} → {destino}")
            return cls(**datos)
        return cls(origen, destino)

    def guardar(self, ruta: Path) -> None:
        self.actualizado = time.time()
        temporal = ruta.with_suffix(ruta.suffix + ".tmp")
        temporal.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, ruta)  # escritura atómica: nunca queda un archivo a medias

    @property
    def tasa_enriquecimiento(self) -> float:
        return self.enriquecidos / self.leidos if self.leidos else 0.0


class Reindexador:
    def __init__(
        self,
        es: Any,
        origen: str,
        destino: str,
        orden: list[str],
        ruta_control: str | Path,
        lote: int = 5_000,
        enriquecer: Enriquecedor | None = None,
        transformar: Callable[[Documento], Documento] | None = None,
        simulacion: bool = False,
        ruta_fallidos: str | Path | None = None,
    ):
        if not orden:
            raise ValueError("Indica al menos un campo de orden estable y único en conjunto (por ejemplo fecha e id)")
        self.es = es
        self.origen, self.destino = origen, destino
        self.orden = orden
        self.ruta_control = Path(ruta_control)
        self.lote = lote
        self.enriquecer = enriquecer
        self.transformar = transformar
        self.simulacion = simulacion
        self.ruta_fallidos = Path(ruta_fallidos) if ruta_fallidos else self.ruta_control.with_suffix(".fallidos.jsonl")

    def ejecutar(self, max_lotes: int | None = None) -> PuntoDeControl:
        control = PuntoDeControl.cargar(self.ruta_control, self.origen, self.destino)
        if control.terminado:
            log.info("La reindexación %s → %s ya había terminado", self.origen, self.destino)
            return control
        pit = self.es.open_point_in_time(index=self.origen, keep_alive="5m")["id"]
        lotes = 0
        try:
            while max_lotes is None or lotes < max_lotes:
                cuerpo: dict[str, Any] = {
                    "size": self.lote,
                    "pit": {"id": pit, "keep_alive": "5m"},
                    "sort": [{campo: "asc"} for campo in self.orden],
                }
                if control.search_after is not None:
                    cuerpo["search_after"] = control.search_after
                respuesta = self.es.search(**cuerpo)
                pit = respuesta.get("pit_id", pit)
                hits = respuesta["hits"]["hits"]
                if not hits:
                    control.terminado = True
                    control.guardar(self.ruta_control)
                    break
                self._procesar(hits, control)
                control.search_after = hits[-1]["sort"]
                control.guardar(self.ruta_control)
                lotes += 1
                log.info("Lote %d: %d leídos, %d indexados, %d fallidos", lotes, control.leidos, control.indexados, control.fallidos)
        finally:
            self.es.close_point_in_time(id=pit)
        return control

    def _procesar(self, hits: list[dict[str, Any]], control: PuntoDeControl) -> None:
        operaciones: list[dict[str, Any]] = []
        for hit in hits:
            doc = dict(hit["_source"])
            if self.transformar:
                doc = self.transformar(doc)
            if self.enriquecer and self.enriquecer(doc):
                control.enriquecidos += 1
            operaciones.append({"index": {"_index": self.destino, "_id": hit["_id"]}})
            operaciones.append(doc)
        control.leidos += len(hits)
        if self.simulacion:
            return
        respuesta = self.es.bulk(operations=operaciones, refresh=False)
        fallidos = []
        for item in respuesta["items"]:
            resultado = item.get("index", {})
            if resultado.get("error"):
                fallidos.append({"_id": resultado.get("_id"), "error": resultado["error"]})
        control.indexados += len(hits) - len(fallidos)
        control.fallidos += len(fallidos)
        if fallidos:
            with self.ruta_fallidos.open("a", encoding="utf-8") as f:
                for fallo in fallidos:
                    f.write(json.dumps(fallo, ensure_ascii=False) + "\n")
