"""Enriquecimiento de documentos a partir de una tabla de referencia en CSV."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


class TablaDeReferencia:
    """Agrega a cada documento los datos de una fila del CSV que coincide por una llave.

    Por ejemplo, con un CSV de vehículos indexado por `placa`, cada lectura de cámara
    recibe un objeto `vehiculo` con la marca, la línea y la clase.
    """

    def __init__(self, ruta_csv: str | Path, llave_csv: str, campo_doc: str, destino: str):
        self.campo_doc = campo_doc
        self.destino = destino
        with open(ruta_csv, newline="", encoding="utf-8") as f:
            self.tabla = {self._normalizar(fila.pop(llave_csv)): fila for fila in csv.DictReader(f)}

    @staticmethod
    def _normalizar(valor: Any) -> str:
        return str(valor).strip().upper().replace(" ", "").replace("-", "")

    def __call__(self, doc: dict[str, Any]) -> bool:
        valor = doc.get(self.campo_doc)
        if valor is None:
            return False
        fila = self.tabla.get(self._normalizar(valor))
        if fila is None:
            return False
        doc[self.destino] = dict(fila)
        return True

    def __len__(self) -> int:
        return len(self.tabla)
