"""Valida el PBIP: JSON contra los esquemas oficiales y referencias al modelo.

No sustituye abrir el proyecto en Power BI Desktop; no evalua DAX ni dibuja.
Uso: python scripts/validar_pbip.py <clon de microsoft/json-schemas>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

RAIZ = Path(__file__).resolve().parent.parent / "powerbi"
ESQUEMAS = Path(sys.argv[1])
BASE = "https://developer.microsoft.com/json-schemas/"


def recuperar(uri: str) -> Resource:
    return Resource.from_contents(json.loads((ESQUEMAS / uri.removeprefix(BASE)).read_text()), default_specification=DRAFT7)


registro = Registry(retrieve=recuperar)
errores, n = [], 0
for f in [*RAIZ.rglob("*.json"), *RAIZ.rglob("*.pbir"), *RAIZ.rglob("*.pbism"), *RAIZ.rglob("*.pbip")]:
    if "StaticResources" in f.parts or "datos" in f.parts:
        continue
    doc = json.loads(f.read_text())
    uri = doc.get("$schema", "")
    if not uri.startswith(BASE):
        errores.append(f"{f}: sin $schema")
        continue
    esquema = json.loads((ESQUEMAS / uri.removeprefix(BASE)).read_text())
    n += 1
    for e in Draft7Validator(esquema, registry=registro).iter_errors(doc):
        errores.append(f"{f.relative_to(RAIZ)} {list(e.absolute_path)}: {e.message[:200]}")

# Cada campo usado por una visual debe existir en el modelo.
tablas: dict[str, set[str]] = {}
for f in (RAIZ / "Observatorio.SemanticModel/definition/tables").glob("*.tmdl"):
    nombres = set()
    for l in f.read_text().splitlines():
        m = re.match(r"\t(?:column|measure) ('(?:[^']|'')+'|\S+)", l)
        if m:
            nombres.add(m[1].strip("'").replace("''", "'"))
    tablas[f.stem] = nombres


def recorrer(o, f):
    if isinstance(o, dict):
        for k in ("Column", "Measure"):
            if k in o and isinstance(o[k], dict) and "Property" in o[k]:
                t, p = o[k]["Expression"]["SourceRef"]["Entity"], o[k]["Property"]
                if p not in tablas.get(t, ()):
                    errores.append(f"{f}: no existe {t}[{p}]")
        for v in o.values():
            recorrer(v, f)
    elif isinstance(o, list):
        for v in o:
            recorrer(v, f)


visuales = list(RAIZ.rglob("visual.json"))
for f in visuales:
    recorrer(json.loads(f.read_text()), f.parent.name)

# Referencias DAX Tabla[columna] y [medida].
medidas = tablas["Medidas"]
texto = (RAIZ / "Observatorio.SemanticModel/definition/tables/Medidas.tmdl").read_text().split("\tpartition")[0]
for t, c in re.findall(r"\b([A-Z][A-Za-z]+)\[([^\]]+)\]", texto):
    if c not in tablas.get(t, ()):
        errores.append(f"DAX: no existe {t}[{c}]")
for c in re.findall(r"(?<![A-Za-z\]])\[([^\]]+)\]", texto):
    if c not in medidas:
        errores.append(f"DAX: no existe la medida [{c}]")

graficas = [f for f in visuales if json.loads(f.read_text())["visual"]["visualType"] not in
            ("card", "slicer", "actionButton", "textbox", "tableEx")]
print(f"archivos validados: {n}; visuales: {len(visuales)}; graficas: {len(graficas)}; tablas: {len(tablas)}")
print("\n".join(errores[:60]) or "sin errores")
sys.exit(1 if errores else 0)
