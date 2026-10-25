from src.evaluate import compare, load_gold


def test_distingue_ok_null_y_error():
    gold = load_gold("Factura_04_imagen")
    pred = {"campos": {**gold["campos"], "iban": None, "emisor_nombre": "Papeleria Taller Demo"},
            "lineas": gold["lineas"][:4]}
    ev = compare(pred, gold)
    assert (ev["ok"], ev["null"], ev["error"]) == (13, 1, 1)
    assert ev["errores"] == {"emisor_nombre": {"pred": "Papeleria Taller Demo", "gold": "Papelería Taller Demo"}}
    assert (ev["lineas_celdas_ok"], ev["lineas_celdas"]) == (28, 35)


def test_gold_completo():
    for stem in ["Factura_01_texto", "Factura_02_texto", "Factura_03_texto", "Factura_04_imagen", "Factura_05_imagen"]:
        g = load_gold(stem)
        assert len(g["campos"]) == 15 and None not in g["campos"].values() and len(g["lineas"]) == 5
