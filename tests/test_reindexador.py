import csv

import pytest

from reindexador import PuntoDeControl, Reindexador, TablaDeReferencia

from falso_es import FalsoES


def lecturas(n):
    return [{"id": f"L{i:05d}", "fecha": f"2025-01-01T00:{i // 60:02d}:{i % 60:02d}", "placa": f"ABC{i % 10:03d}"} for i in range(n)]


@pytest.fixture
def control(tmp_path):
    return tmp_path / "control.json"


def test_reindexa_todo(control):
    es = FalsoES(lecturas(23))
    r = Reindexador(es, "origen", "destino", ["fecha", "id"], control, lote=5).ejecutar()
    assert r.terminado and r.leidos == 23 and r.indexados == 23
    assert len(es.destino) == 23
    assert es.pits_abiertos == 0


def test_continua_despues_de_una_caida(control):
    docs = lecturas(23)
    es = FalsoES(docs, fallar_en_lote=3)
    with pytest.raises(ConnectionError):
        Reindexador(es, "origen", "destino", ["fecha", "id"], control, lote=5).ejecutar()
    guardado = PuntoDeControl.cargar(control, "origen", "destino")
    assert guardado.leidos == 10 and not guardado.terminado
    assert es.pits_abiertos == 0  # el PIT se cierra aunque falle

    es.fallar_en_lote = None
    r = Reindexador(es, "origen", "destino", ["fecha", "id"], control, lote=5).ejecutar()
    assert r.terminado and r.indexados == 23
    # Solo se reenvió el lote que falló: 2 lotes buenos + 1 fallido + 3 restantes.
    assert es.lotes_bulk == 6


def test_pausa_por_numero_de_lotes(control):
    es = FalsoES(lecturas(20))
    r = Reindexador(es, "origen", "destino", ["fecha", "id"], control, lote=5).ejecutar(max_lotes=2)
    assert r.leidos == 10 and not r.terminado
    r = Reindexador(es, "origen", "destino", ["fecha", "id"], control, lote=5).ejecutar()
    assert r.leidos == 20 and r.terminado


def test_no_repite_una_reindexacion_terminada(control):
    es = FalsoES(lecturas(5))
    Reindexador(es, "origen", "destino", ["fecha", "id"], control, lote=5).ejecutar()
    lotes = es.lotes_bulk
    Reindexador(es, "origen", "destino", ["fecha", "id"], control, lote=5).ejecutar()
    assert es.lotes_bulk == lotes


def test_registra_documentos_fallidos(control):
    es = FalsoES(lecturas(10), ids_con_error={"L00003", "L00007"})
    r = Reindexador(es, "origen", "destino", ["fecha", "id"], control, lote=4).ejecutar()
    assert r.indexados == 8 and r.fallidos == 2
    fallidos = control.with_suffix(".fallidos.jsonl").read_text().splitlines()
    assert len(fallidos) == 2


def test_enriquece_con_tabla_de_referencia(control, tmp_path):
    ruta = tmp_path / "vehiculos.csv"
    with ruta.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["placa", "marca", "clase"])
        for i in range(8):  # 8 de 10 placas conocidas
            w.writerow([f"abc-{i:03d}", f"Marca{i}", "Automóvil"])
    tabla = TablaDeReferencia(ruta, "placa", "placa", "vehiculo")
    es = FalsoES(lecturas(20))
    r = Reindexador(es, "origen", "destino", ["fecha", "id"], control, lote=6, enriquecer=tabla).ejecutar()
    assert r.enriquecidos == 16
    assert r.tasa_enriquecimiento == pytest.approx(0.8)
    assert es.destino["L00001"]["vehiculo"] == {"marca": "Marca1", "clase": "Automóvil"}
    assert "vehiculo" not in es.destino["L00009"]


def test_simulacion_no_escribe(control):
    es = FalsoES(lecturas(10))
    r = Reindexador(es, "origen", "destino", ["fecha", "id"], control, lote=5, simulacion=True).ejecutar()
    assert r.leidos == 10 and es.destino == {}


def test_control_de_otra_reindexacion(control):
    Reindexador(FalsoES(lecturas(3)), "a", "b", ["fecha", "id"], control, lote=5).ejecutar()
    with pytest.raises(ValueError):
        Reindexador(FalsoES(lecturas(3)), "x", "y", ["fecha", "id"], control, lote=5).ejecutar()
