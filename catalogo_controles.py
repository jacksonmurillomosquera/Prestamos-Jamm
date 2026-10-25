"""Catálogo oficial de ubicaciones y marca de control requerida."""

from collections import Counter

# servicio: (piso, ((codigo de cama, marca), ...))
CATALOGO_POR_SERVICIO = {
    "3T3": (
        "3",
        (
            ("301", "SONY"), ("302", "SONY"), ("303", "SONY"), ("304", "SONY"),
            ("305", "SAMSUNG"), ("306", "SONY"), ("307", "PANASONIC"),
            ("308-1", "SAMSUNG"), ("308-2", "SONY"), ("309-1", "KALLEY"),
            ("309-2", "SAMSUNG"), ("310-1", "SONY"), ("310-2", "KALLEY"),
            ("311-1", "SONY"), ("311-2", "PANASONIC"), ("312", "SONY"),
            ("313", "SONY"), ("315", "KALLEY"), ("316", "SONY"),
            ("317-1", "KALLEY"), ("317-2", "KALLEY"), ("318", "SONY"),
            ("319", "SAMSUNG"), ("320", "PANASONIC"), ("321", "SONY"),
            ("322", "SAMSUNG"), ("323", "SONY"), ("324", "KALLEY"),
            ("325", "SAMSUNG"), ("326-1", "SONY"), ("326-2", "SONY"),
            ("327-1", "LG"), ("327-2", "LG"), ("328-1", "SAMSUNG"),
            ("328-2", "SAMSUNG"), ("329-1", "SONY"), ("329-2", "SONY"),
            ("330-1", "SONY"), ("330-2", "SONY"), ("331-1", "SONY"),
            ("331-2", "SONY"), ("332-1", "SONY"), ("332-2", "SONY"),
            ("333-1", "KALLEY"), ("333-2", "KALLEY"), ("334", "SONY"),
            ("335-1", "PANASONIC"), ("335-2", "PANASONIC"), ("336-1", "SONY"),
            ("336-2", "SONY"), ("337-1", "SAMSUNG"), ("337-2", "SAMSUNG"),
            ("338-1", "SONY"), ("338-2", "SONY"), ("339-1", "SONY"),
            ("339-2", "SONY"), ("340-1", "SONY"), ("340-2", "SONY"),
            ("341-1", "SONY"), ("341-2", "SONY"), ("342", "SAMSUNG"),
            ("343", "SONY"), ("344", "SAMSUNG"), ("345", "SONY"),
            ("346", "SAMSUNG"), ("347", "SONY"),
        ),
    ),
    "4T1": (
        "4",
        (
            ("401-1", "SONY"), ("401-2", "SONY"), ("402-1", "LG"),
            ("402-2", "SONY"), ("403-1", "SONY"), ("403-2", "SONY"),
            ("404-1", "SONY"), ("404-2", "SONY"), ("405", "SONY"),
            ("406", "SONY"), ("407", "SONY"), ("408", "PANASONIC"),
            ("409", "KALLEY"), ("410", "SONY"), ("411", "SONY"),
            ("412-1", "PANASONIC"), ("412-2", "SONY"), ("413-1", "SONY"),
            ("413-2", "SONY"), ("414-1", "PANASONIC"), ("414-2", "SONY"),
            ("415-1", "SAMSUNG"), ("415-2", "KALLEY"), ("416-1", "SONY"),
            ("416-2", "SONY"), ("417-1", "PANASONIC"), ("417-2", "PANASONIC"),
            ("418", "SAMSUNG"), ("419", "KALLEY"), ("420", "SONY"),
            ("421", "SONY"), ("4221", "SONY"), ("4222", "SONY"),
            ("4231", "SONY"), ("4232", "SONY"), ("4241", "KALLEY"),
            ("4242", "KALLEY"), ("4251", "SONY"), ("4252", "SONY"),
            ("426", "SONY"), ("4271", "SONY"), ("4272", "SONY"),
            ("4281", "SAMSUNG"), ("4282", "SAMSUNG"), ("4291", "KALLEY"),
            ("4292", "KALLEY"), ("4301", "LG"), ("4302", "LG"),
            ("4311", "SONY"), ("4312", "SONY"), ("4322", "SONY"),
            ("4331", "SAMSUNG"), ("4332", "SAMSUNG"),
        ),
    ),
    "4T2": (
        "4",
        tuple(
            (f"{room}{bed}", "SONY")
            for room in range(434, 440)
            for bed in (1, 2, 3)
        ),
    ),
    "5T3": (
        "5",
        (
            ("501", "SONY"), ("502", "SONY"), ("503", "SAMSUNG"),
            ("504", "SAMSUNG"), ("505", "SAMSUNG"), ("506", "SAMSUNG"),
            ("507", "SAMSUNG"), ("508", "SONY"), ("509", "KALLEY"),
            ("510", "SONY"), ("5111", "SONY"), ("5112", "KALLEY"),
            ("512", "SAMSUNG"), ("513", "SONY"), ("514", "SONY"),
            ("515", "SONY"), ("516", "SAMSUNG"), ("517", "KALLEY"),
        ),
    ),
    "6T3": (
        "6",
        (
            ("UCE-1", "SAMSUNG"), ("UCE-2", "SONY"), ("UCE-3", "PANASONIC"),
            ("UCE-4", "SONY"), ("UCE-5", "SONY"), ("UCE-6", "LG"),
            ("UCE-7", "PANASONIC"), ("UCE-8", "KALLEY"), ("UCE-9", "SONY"),
            ("UCE-10", "SAMSUNG"), ("UCE-11", "SAMSUNG"), ("UCE-12", "SAMSUNG"),
            ("UCE-13", "SAMSUNG"), ("UCE-14", "SAMSUNG"), ("UCE-15", "SAMSUNG"),
            ("UCE-16", "SAMSUNG"), ("UCE-17", "PANASONIC"), ("UCE-18", "SAMSUNG"),
            ("UCE-19", "SONY"),
        ),
    ),
    "UCE-PISO 5": (
        "5",
        (
            ("UCE-23", "SAMSUNG"), ("UCE-24", "SAMSUNG"), ("UCE-25", "SAMSUNG"),
            ("UCE-26", "SONY"), ("UCE-27", "SAMSUNG"), ("UCE-28", "SAMSUNG"),
            ("UCE-29", "SAMSUNG"), ("UCE-30", "SAMSUNG"),
        ),
    ),
}

def _datos_ubicacion(servicio, piso, codigo, marca):
    if codigo.startswith("UCE-"):
        if servicio == "UCE-PISO 5":
            habitacion = "UCE-PISO 5"
            cama = codigo.removeprefix("UCE-")
            torre = "3"
        else:
            habitacion = "UCE"
            cama = codigo.removeprefix("UCE-")
            torre = "3"
    elif "-" in codigo:
        habitacion, cama = codigo.rsplit("-", 1)
        torre = service_tower(servicio)
    elif len(codigo) == 4 and servicio in {"4T1", "4T2", "5T3"}:
        habitacion, cama = codigo[:-1], codigo[-1]
        torre = servicio[-1]
    else:
        habitacion, cama = codigo, None
        torre = service_tower(servicio)

    return {
        "servicio": servicio,
        "piso": piso,
        "torre": torre,
        "habitacion": habitacion,
        "cama": cama,
        "ubicacion_codigo": codigo,
        "marca_control_requerida": marca,
        "activo": True,
    }


def service_tower(servicio):
    return servicio[-1] if servicio.endswith("T1") or servicio.endswith("T2") or servicio.endswith("T3") else None


DUPLICADOS_CATALOGO = tuple(sorted(
    codigo
    for codigo, count in Counter(
        codigo
        for _, (_, habitaciones) in CATALOGO_POR_SERVICIO.items()
        for codigo, _ in habitaciones
    ).items()
    if count > 1
))

CATALOGO_UBICACIONES = {
    codigo: _datos_ubicacion(servicio, piso, codigo, marca)
    for servicio, (piso, habitaciones) in CATALOGO_POR_SERVICIO.items()
    for codigo, marca in habitaciones
}

# Compatibility for existing display code; this is location metadata, not physical stock.
CATALOGO_HABITACIONES = {
    codigo: {
        "marca": ubicacion["marca_control_requerida"],
        "piso": ubicacion["piso"],
        "torre": ubicacion["servicio"],
        **ubicacion,
    }
    for codigo, ubicacion in CATALOGO_UBICACIONES.items()
}

assert len(CATALOGO_HABITACIONES) == sum(
    len(habitaciones) for _, habitaciones in CATALOGO_POR_SERVICIO.values()
)

assert len(CATALOGO_UBICACIONES) == len(set(CATALOGO_UBICACIONES))
assert CATALOGO_UBICACIONES["402-1"]["marca_control_requerida"] == "LG"
assert CATALOGO_UBICACIONES["402-2"]["marca_control_requerida"] == "SONY"
assert CATALOGO_UBICACIONES["UCE-1"]["marca_control_requerida"] == "SAMSUNG"
assert CATALOGO_UBICACIONES["310-2"]["marca_control_requerida"] == "KALLEY"
