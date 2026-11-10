"""Un Elasticsearch en memoria con lo justo para probar el reindexador."""


class FalsoES:
    def __init__(self, docs, fallar_en_lote=None, ids_con_error=()):
        self.origen = sorted(docs, key=lambda d: (d["fecha"], d["id"]))
        self.destino = {}
        self.lotes_bulk = 0
        self.fallar_en_lote = fallar_en_lote
        self.ids_con_error = set(ids_con_error)
        self.pits_abiertos = 0

    def open_point_in_time(self, index, keep_alive):
        self.pits_abiertos += 1
        return {"id": f"pit-{self.pits_abiertos}"}

    def close_point_in_time(self, id):
        self.pits_abiertos -= 1

    def search(self, size, pit, sort, search_after=None):
        campos = [list(s)[0] for s in sort]
        clave = lambda d: tuple(d[c] for c in campos)
        restantes = [d for d in self.origen if search_after is None or clave(d) > tuple(search_after)]
        hits = [{"_id": d["id"], "_source": d, "sort": list(clave(d))} for d in restantes[:size]]
        return {"pit_id": pit["id"], "hits": {"hits": hits}}

    def bulk(self, operations, refresh=False):
        self.lotes_bulk += 1
        if self.fallar_en_lote == self.lotes_bulk:
            raise ConnectionError("se cayó la conexión")
        items = []
        for accion, doc in zip(operations[::2], operations[1::2]):
            _id = accion["index"]["_id"]
            if _id in self.ids_con_error:
                items.append({"index": {"_id": _id, "status": 400, "error": {"type": "mapper_parsing_exception"}}})
            else:
                self.destino[_id] = doc
                items.append({"index": {"_id": _id, "status": 201}})
        return {"errors": any("error" in i["index"] for i in items), "items": items}
