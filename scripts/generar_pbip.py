"""Genera el proyecto de Power BI (PBIP: modelo TMDL + reporte PBIR).

Power BI Desktop abre `powerbi/Observatorio.pbip`; desde ahi se guarda el .pbix.
Uso: python scripts/generar_pbip.py
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PBI = RAIZ / "powerbi"
DATOS = PBI / "datos"
SM = PBI / "Observatorio.SemanticModel"
RP = PBI / "Observatorio.Report"
RUTA_POR_DEFECTO = r"C:\Lab-12-powerbi\powerbi\datos"
BASE_ESQUEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"

AZUL, NARANJA, VERDE, ROSA, MORADO, VIOLETA, CELESTE, SALMON = (
    "#4361EE", "#FFA630", "#60A125", "#F72585", "#A2158D", "#4D0A99", "#4CC9F0", "#FFA5A3")
TINTA, TINTA2, LINEA, FONDO2 = "#2E3B73", "#5A6798", "#DFE3F2", "#F5F6FD"

# ---------------------------------------------------------------------------
# Modelo semantico
# ---------------------------------------------------------------------------
FUENTES = {  # tabla: (csv, columnas que se quitan)
    "Mensual": ("origen/turismo_mensual.csv", ["region", "perfil", "lat", "lon", "capacidad_carga", "trimestre", "anio", "mes"]),
    "LlegadasMercado": ("origen/mercados.csv", ["region", "anio", "mes"]),
    "Visitantes": ("origen/visitantes.csv", ["region", "anio", "mes"]),
    "PredSerie": ("modelos/predicciones_serie.csv", []),
    "MetricasSerie": ("modelos/metricas_serie.csv", []),
    "PredClase": ("modelos/predicciones_clasificacion.csv", []),
    "MetricasClase": ("modelos/metricas_clasificacion.csv", []),
    "CurvaROC": ("modelos/curvas_roc.csv", []),
    "Importancia": ("modelos/importancia_variables.csv", []),
    "CurvaAprendizaje": ("modelos/curvas_aprendizaje.csv", []),
}

RELACIONES = [
    ("Mensual", "fecha", "Calendario", "Fecha"), ("Mensual", "destino", "Destinos", "destino"),
    ("LlegadasMercado", "fecha", "Calendario", "Fecha"), ("LlegadasMercado", "destino", "Destinos", "destino"),
    ("LlegadasMercado", "mercado", "Mercados", "mercado"),
    ("Visitantes", "fecha", "Calendario", "Fecha"), ("Visitantes", "destino", "Destinos", "destino"),
    ("GastoCategoria", "fecha", "Calendario", "Fecha"), ("GastoCategoria", "destino", "Destinos", "destino"),
    ("PredClase", "id_visitante", "Visitantes", "id_visitante"),
    ("PredClase", "modelo", "ModeloClase", "modelo"), ("MetricasClase", "modelo", "ModeloClase", "modelo"),
    ("CurvaROC", "modelo", "ModeloClase", "modelo"), ("Importancia", "modelo", "ModeloClase", "modelo"),
    ("CurvaAprendizaje", "modelo", "ModeloClase", "modelo"),
    ("PredSerie", "modelo", "ModeloSerie", "modelo"), ("MetricasSerie", "modelo", "ModeloSerie", "modelo"),
]

MES_TXT = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun", 7: "Jul", 8: "Ago",
           9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}
TODOS = "Todos los destinos"

# Medidas: nombre -> (DAX, formato). Reproducen las reglas de agregacion del Lab 10.
_ponderada = "DIVIDE(SUMX(Mensual, Mensual[{c}] * Mensual[llegadas]), [Visitantes])"
_alc = 'VAR a = SELECTEDVALUE(Alcance[alcance], "' + TODOS + '")'
_mod = 'VAR m = SELECTEDVALUE(ModeloSerie[modelo], "Suavizamiento (Holt-Winters)")'
_prueba, _futuro = "Prueba (ultimos 12 meses)", "Pronostico (12 meses futuros)"


def _serie(col, conj, modelo=None):
    filtro_m = f'PredSerie[modelo] = "{modelo}"' if modelo else "PredSerie[modelo] = m"
    previo = "" if modelo else _mod + "\n"
    return (f'{_alc}\n{previo}RETURN CALCULATE(AVERAGE(PredSerie[{col}]), REMOVEFILTERS(ModeloSerie), '
            f'PredSerie[alcance] = a, {filtro_m}, PredSerie[conjunto] = "{conj}")')


def _metrica_serie(nombre):
    return f'{_alc}\nRETURN CALCULATE(AVERAGE(MetricasSerie[valor]), MetricasSerie[alcance] = a, MetricasSerie[metrica] = "{nombre}")'


MEDIDAS = {
    "Visitantes": ("SUM(Mensual[llegadas])", "#,0"),
    "Derrama USD": ("SUM(Mensual[gasto_total_usd])", '"US$" #,0'),
    "Visitantes periodo anterior": (
        "VAR i = MIN(Calendario[Anio]) VAR f = MAX(Calendario[Anio]) VAR n = f - i + 1\n"
        "RETURN CALCULATE([Visitantes], REMOVEFILTERS(Calendario), Calendario[Anio] >= i - n, Calendario[Anio] <= i - 1)", "#,0"),
    "Derrama periodo anterior": (
        "VAR i = MIN(Calendario[Anio]) VAR f = MAX(Calendario[Anio]) VAR n = f - i + 1\n"
        "RETURN CALCULATE([Derrama USD], REMOVEFILTERS(Calendario), Calendario[Anio] >= i - n, Calendario[Anio] <= i - 1)", '"US$" #,0'),
    "Variacion visitantes": ("DIVIDE([Visitantes], [Visitantes periodo anterior]) - 1", "0.0%"),
    "Variacion derrama": ("DIVIDE([Derrama USD], [Derrama periodo anterior]) - 1", "0.0%"),
    "Estancia promedio": (_ponderada.format(c="estancia_promedio"), "0.00"),
    "Satisfaccion ponderada": (_ponderada.format(c="satisfaccion_promedio"), "0.00"),
    "Gasto por visitante": ("DIVIDE([Derrama USD], [Visitantes])", '"US$" #,0'),
    "Satisfaccion media": ("AVERAGE(Mensual[satisfaccion_promedio])", "0.00"),
    "Ocupacion": ("AVERAGE(Mensual[ocupacion_hotelera])", "0.0"),
    "Gasto diario": ("AVERAGE(Mensual[gasto_diario_usd])", '"US$" #,0'),
    "Presion turistica": ("AVERAGE(Mensual[presion_turistica])", "0.00"),
    "Estado de presion": ('IF(ISBLANK([Presion turistica]), BLANK(), SWITCH(TRUE(), [Presion turistica] >= 1, "Saturacion", [Presion turistica] >= 0.85, "Al limite", "Holgura"))', ""),
    "Color de presion": (f'SWITCH(TRUE(), [Presion turistica] >= 1, "{ROSA}", [Presion turistica] >= 0.85, "{NARANJA}", "{VERDE}")', ""),
    "CO2 toneladas": ("SUM(Mensual[co2_ton])", "#,0"),
    "Empleo local": ("AVERAGE(Mensual[empleo_local_pct])", "0.0"),
    "Empresas certificadas": ("AVERAGE(Mensual[empresas_certificadas_pct])", "0.0"),
    "Holgura de carga": ("100 * (1 - MIN(MAX([Presion turistica], 0), 1.4) / 1.4)", "0"),
    "Satisfaccion 0-100": ("([Satisfaccion media] - 1) / 4 * 100", "0"),
    "CO2 por noche": ("DIVIDE(SUM(Mensual[co2_ton]), SUM(Mensual[noches_totales])) * 1000", "0.0"),
    "Residuos por noche": ("DIVIDE(SUM(Mensual[residuos_ton]), SUM(Mensual[noches_totales])) * 1000", "0.0"),
    "Eficiencia en CO2": ("100 * (1 - DIVIDE([CO2 por noche], MAXX(ALLSELECTED(Destinos[destino]), [CO2 por noche])))", "0"),
    "Eficiencia en residuos": ("100 * (1 - DIVIDE([Residuos por noche], MAXX(ALLSELECTED(Destinos[destino]), [Residuos por noche])))", "0"),
    "Llegadas por mercado": ("SUM(LlegadasMercado[llegadas])", "#,0"),
    "Participacion de mercado": ("DIVIDE([Llegadas por mercado], CALCULATE([Llegadas por mercado], ALLSELECTED(Mercados)))", "0.0%"),
    "Derrama por categoria": ("SUM(GastoCategoria[gasto_usd])", '"US$" #,0'),
    "Encuestas": ("COUNTROWS(Visitantes)", "#,0"),
    "Gasto mediano": ("MEDIAN(Visitantes[gasto_total_usd])", '"US$" #,0'),
    "Gasto P25": ("PERCENTILE.INC(Visitantes[gasto_total_usd], 0.25)", '"US$" #,0'),
    "Gasto P75": ("PERCENTILE.INC(Visitantes[gasto_total_usd], 0.75)", '"US$" #,0'),
    "Observado prueba": (_serie("real", _prueba), "#,0"),
    "Estimado futuro": (_serie("estimado", _futuro), "#,0"),
    "Limite inferior": (_serie("inferior", _futuro), "#,0"),
    "Limite superior": (_serie("superior", _futuro), "#,0"),
    "Tendencia + estacionalidad (prueba)": (_serie("estimado", _prueba, "Tendencia + estacionalidad"), "#,0"),
    "Holt-Winters (prueba)": (_serie("estimado", _prueba, "Suavizamiento (Holt-Winters)"), "#,0"),
    "SARIMA (prueba)": (_serie("estimado", _prueba, "SARIMA"), "#,0"),
    "Error absoluto medio": (_metrica_serie("MAE"), "#,0"),
    "RMSE": (_metrica_serie("RMSE"), "#,0"),
    "Error porcentual (MAPE)": (_metrica_serie("MAPE"), "0.00"),
    "Casos evaluados": ("COUNTROWS(PredClase)", "#,0"),
    "Probabilidad media": ("AVERAGE(PredClase[prob_promotor])", "0.0%"),
    "Valor de metrica": ("AVERAGE(MetricasClase[valor])", "0.000"),
    "Tasa de aciertos": ("AVERAGE(CurvaROC[tasa_aciertos])", "0.00"),
    "AUC validacion": ("AVERAGE(CurvaAprendizaje[validacion])", "0.000"),
    "Peso del factor": (
        'VAR m = SELECTEDVALUE(ModeloClase[modelo], "Regresion logistica")\n'
        "RETURN CALCULATE(SUM(Importancia[peso]), REMOVEFILTERS(ModeloClase), Importancia[modelo] = m)", "0.000"),
    "Seleccion activa": (
        'VAR i = MIN(Calendario[Anio]) VAR f = MAX(Calendario[Anio])\n'
        'VAR d = IF(ISFILTERED(Destinos[destino]) || ISFILTERED(Destinos[region]), '
        'CONCATENATEX(VALUES(Destinos[destino]), Destinos[destino], ", "), "Todos los destinos")\n'
        'RETURN "Viendo: " & i & "-" & f & " | " & d', ""),
    "Mensaje sin datos": (
        'IF(ISBLANK([Visitantes]) && ISBLANK([Encuestas]), '
        '"No hay datos para esta seleccion. Amplie el periodo o pulse Restablecer.", " ")', ""),
}


def tipos_csv(ruta: Path) -> pd.Series:
    return pd.read_csv(ruta, low_memory=False, nrows=None).dtypes


def m_csv(rel: str, tipos: dict[str, str], quitar: list[str], extra: str = "", ultimo: str = "Tipos") -> str:
    m_tipo = {"int64": "Int64.Type", "double": "type number", "dateTime": "type date", "string": "type text"}
    pares = ", ".join(f'{{"{c}", {m_tipo[t]}}}' for c, t in tipos.items())
    lineas = [
        "let",
        f'    Fuente = Csv.Document(File.Contents(RutaDatos & "\\{rel.replace("/", chr(92))}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Encabezados = Table.PromoteHeaders(Fuente, [PromoteAllScalars = true]),",
        f'    Tipos = Table.TransformColumnTypes(Encabezados, {{{pares}}}, "en-US")' + ("," if quitar or extra else ""),
    ]
    if quitar:
        lista = ", ".join(f'"{c}"' for c in quitar)
        lineas.append(f"    Quitadas = Table.RemoveColumns(Tipos, {{{lista}}})" + ("," if extra else ""))
        ultimo = "Quitadas"
    if extra:
        lineas.append(extra)
        ultimo = "Final"
    lineas += ["in", f"    {ultimo}"]
    return "\n".join(lineas)


def tipo_tmdl(col: str, dt) -> str:
    if col == "fecha":
        return "dateTime"
    return {"i": "int64", "f": "double"}.get(dt.kind, "string")


def q(n: str) -> str:
    return n if n.replace("_", "").isalnum() and n.isascii() and not n[0].isdigit() else "'" + n.replace("'", "''") + "'"


def tabla_tmdl(nombre: str, columnas: list[tuple], m: str, oculta=False, medidas=None) -> str:
    out = [f"table {q(nombre)}"]
    if oculta:
        pass
    for med, (dax, fmt) in (medidas or {}).items():
        if "\n" in dax:
            cuerpo = "\n".join("\t\t\t" + l for l in dax.split("\n"))
            out += [f"\tmeasure {q(med)} = ```", cuerpo, "\t\t\t```"]
        else:
            out.append(f"\tmeasure {q(med)} = {dax}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out.append("")
    for c in columnas:
        col, tipo, *resto = c
        ops = resto[0] if resto else {}
        out += [f"\tcolumn {q(col)}", f"\t\tdataType: {tipo}"]
        if tipo == "dateTime":
            out.append("\t\tformatString: yyyy-mm")
        if ops.get("oculta"):
            out.append("\t\tisHidden")
        out += [f"\t\tsummarizeBy: none", f"\t\tsourceColumn: {col}"]
        if ops.get("sortBy"):
            out.append(f"\t\tsortByColumn: {ops['sortBy']}")
        out.append("")
    out += [f"\tpartition {q(nombre)} = m", "\t\tmode: import", "\t\tsource ="]
    out += ["\t\t\t\t" + l for l in m.split("\n")]
    return "\n".join(out) + "\n"


def modelo() -> None:
    (SM / "definition" / "tables").mkdir(parents=True)
    d = SM / "definition"
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1601\n")
    (d / "model.tmdl").write_text(
        "model Model\n\tculture: es-ES\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: en-US\n\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n")
    (d / "expressions.tmdl").write_text(
        f'expression RutaDatos = "{RUTA_POR_DEFECTO}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n')
    rel = []
    for f, fc, t, tc in RELACIONES:
        rel += [f"relationship {uuid.uuid5(uuid.NAMESPACE_DNS, f+fc+t)}", f"\tfromColumn: {f}.{fc}", f"\ttoColumn: {t}.{tc}", ""]
    (d / "relationships.tmdl").write_text("\n".join(rel))

    tablas: dict[str, str] = {}
    for nombre, (rel_csv, quitar) in FUENTES.items():
        dts = tipos_csv(DATOS / rel_csv)
        tipos = {c: tipo_tmdl(c, t) for c, t in dts.items()}
        cols = [(c, t) for c, t in tipos.items() if c not in quitar]
        tablas[nombre] = tabla_tmdl(nombre, cols, m_csv(rel_csv, tipos, quitar))

    # Dimensiones derivadas del CSV: una fila por clave, sin inventar datos.
    mens = "origen/turismo_mensual.csv"
    dts = tipos_csv(DATOS / mens)
    tipos = {c: tipo_tmdl(c, t) for c, t in dts.items()}
    extra = ('    Sel = Table.SelectColumns(Tipos, {"destino", "region", "perfil", "lat", "lon", "capacidad_carga"}),\n'
             '    Final = Table.Distinct(Sel, {"destino"})')
    cols = [("destino", "string"), ("region", "string"), ("perfil", "string"), ("lat", "double"),
            ("lon", "double"), ("capacidad_carga", "int64")]
    tablas["Destinos"] = tabla_tmdl("Destinos", cols, m_csv(mens, tipos, [], extra))

    extra_g = ('    Sel = Table.SelectColumns(Tipos, {"fecha", "destino", "gasto_alojamiento_usd", "gasto_alimentacion_usd", '
               '"gasto_transporte_usd", "gasto_actividades_usd", "gasto_artesanias_usd"}),\n'
               '    Largo = Table.UnpivotOtherColumns(Sel, {"fecha", "destino"}, "columna", "gasto_usd"),\n'
               '    Nombres = #table(type table [columna = text, categoria = text], {{"gasto_alojamiento_usd", "Alojamiento"}, '
               '{"gasto_alimentacion_usd", "Alimentacion"}, {"gasto_transporte_usd", "Transporte"}, '
               '{"gasto_actividades_usd", "Actividades y tours"}, {"gasto_artesanias_usd", "Artesanias y compras"}}),\n'
               '    Unida = Table.ExpandTableColumn(Table.NestedJoin(Largo, "columna", Nombres, "columna", "n", JoinKind.Inner), "n", {"categoria"}),\n'
               '    Final = Table.TransformColumnTypes(Table.RemoveColumns(Unida, {"columna"}), {{"gasto_usd", type number}, {"categoria", type text}})')
    cols = [("fecha", "dateTime"), ("destino", "string"), ("gasto_usd", "double"), ("categoria", "string")]
    tablas["GastoCategoria"] = tabla_tmdl("GastoCategoria", cols, m_csv(mens, tipos, [], extra_g))

    merc = "origen/mercados.csv"
    tm = {c: tipo_tmdl(c, t) for c, t in tipos_csv(DATOS / merc).items()}
    tablas["Mercados"] = tabla_tmdl("Mercados", [("mercado", "string")], m_csv(
        merc, tm, [], '    Final = Table.Distinct(Table.SelectColumns(Tipos, {"mercado"}))'))

    def lista(nombre, col, valores):
        filas = ", ".join('{"' + v + '"}' for v in valores)
        m = f'let\n    Final = #table(type table [{col} = text], {{{filas}}})\nin\n    Final'
        tablas[nombre] = tabla_tmdl(nombre, [(col, "string")], m)

    ps = pd.read_csv(DATOS / "modelos/metricas_serie.csv")
    pc = pd.read_csv(DATOS / "modelos/metricas_clasificacion.csv")
    lista("ModeloSerie", "modelo", list(ps.modelo.unique()))
    lista("ModeloClase", "modelo", list(pc.modelo.unique()))
    lista("Alcance", "alcance", list(ps.alcance.unique()))

    meses = ", ".join(f'{{{k}, "{v}"}}' for k, v in MES_TXT.items())
    cal = ("let\n    Fechas = List.Generate(() => #date(2017, 1, 1), each _ <= #date(2026, 12, 1), each Date.AddMonths(_, 1)),\n"
           '    Tabla = Table.FromList(Fechas, Splitter.SplitByNothing(), type table [Fecha = date]),\n'
           '    Anio = Table.AddColumn(Tabla, "Anio", each Date.Year([Fecha]), Int64.Type),\n'
           '    Trim = Table.AddColumn(Anio, "Trimestre", each "T" & Text.From(Date.QuarterOfYear([Fecha])), type text),\n'
           '    Num = Table.AddColumn(Trim, "MesNum", each Date.Month([Fecha]), Int64.Type),\n'
           f'    Nombres = #table(type table [MesNum = Int64.Type, Mes = text], {{{meses}}}),\n'
           '    Final = Table.ExpandTableColumn(Table.NestedJoin(Num, "MesNum", Nombres, "MesNum", "n", JoinKind.Inner), "n", {"Mes"})\n'
           "in\n    Final")
    tablas["Calendario"] = tabla_tmdl("Calendario", [
        ("Fecha", "dateTime"), ("Anio", "int64"), ("Trimestre", "string"),
        ("MesNum", "int64", {"oculta": True}), ("Mes", "string", {"sortBy": "MesNum"})], cal)
    # Jerarquia para bajar y subir de nivel.
    tablas["Calendario"] = tablas["Calendario"].replace(
        "\tpartition Calendario", "\thierarchy 'Periodo'\n\t\tlevel Anio\n\t\t\tcolumn: Anio\n\t\tlevel Trimestre\n\t\t\tcolumn: Trimestre\n\t\tlevel Mes\n\t\t\tcolumn: Mes\n\n\tpartition Calendario", 1)
    tablas["Medidas"] = tabla_tmdl("Medidas", [("Auxiliar", "int64", {"oculta": True})],
                                   'let\n    Final = #table(type table [Auxiliar = Int64.Type], {{1}})\nin\n    Final', medidas=MEDIDAS)
    for n, txt in tablas.items():
        (d / "tables" / f"{n}.tmdl").write_text(txt)
    (SM / "definition.pbism").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}}, indent=2))


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------
def lit(v) -> dict:
    return {"expr": {"Literal": {"Value": v}}}


def texto(v: str) -> dict:
    return lit("'" + v.replace("'", "''") + "'")


def color(hexa: str) -> dict:
    return {"solid": {"color": texto(hexa)}}


def C(t, c):
    return ("Column", t, c)


def M(c):
    return ("Measure", "Medidas", c)


def campo(f) -> dict:
    kind, t, c = f
    return {kind: {"Expression": {"SourceRef": {"Entity": t}}, "Property": c}}


def proyeccion(f, activa=False) -> dict:
    p = {"field": campo(f), "queryRef": f"{f[1]}.{f[2]}", "nativeQueryRef": f[2]}
    if activa:
        p["active"] = True
    return p


SEL_TODO = {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}


class Pagina:
    def __init__(self, id_, nombre, alto):
        self.id, self.nombre, self.alto, self.visuales, self.z = id_, nombre, alto, [], 0

    def agregar(self, tipo, x, y, w, h, roles=None, titulo=None, objetos=None, sync=None, sub=None, link=None, jerarquia=()):
        self.z += 1
        vis = {"visualType": tipo, "drillFilterOtherVisuals": True}
        if roles:
            vis["query"] = {"queryState": {r: {"projections": [
                proyeccion(f, activa=(r in jerarquia and i == 0)) for i, f in enumerate(fs)]} for r, fs in roles.items()}}
        if objetos:
            vis["objects"] = objetos
        cont = {}
        if titulo:
            cont["title"] = [{"properties": {"show": lit("true"), "text": texto(titulo), "fontColor": color(TINTA), "fontSize": lit("12D"), "bold": lit("true")}}]
            if sub:
                cont["subTitle"] = [{"properties": {"show": lit("true"), "text": texto(sub), "fontColor": color(TINTA2), "fontSize": lit("10D")}}]
            cont["border"] = [{"properties": {"show": lit("true"), "color": color(LINEA), "radius": lit("8D")}}]
        if link:
            cont["visualLink"] = [{"properties": link}]
        if cont:
            vis["visualContainerObjects"] = cont
        if sync:
            vis["syncGroup"] = {"groupName": sync, "fieldChanges": True, "filterChanges": True}
        nombre = uuid.uuid5(uuid.NAMESPACE_DNS, f"{self.id}-{self.z}").hex[:20]
        self.visuales.append({
            "$schema": f"{BASE_ESQUEMA}/visualContainer/2.4.0/schema.json", "name": nombre,
            "position": {"x": x, "y": y, "z": self.z * 100, "height": h, "width": w, "tabOrder": self.z * 100},
            "visual": vis})

    def caja_texto(self, x, y, w, h, txt, tam="11pt", col=TINTA, negrita=False):
        run = {"value": txt, "textStyle": {"fontSize": tam, "color": col, "fontWeight": "bold" if negrita else "normal"}}
        self.agregar("textbox", x, y, w, h, objetos={"general": [{"properties": {"paragraphs": [{"textRuns": [run]}]}}]})


PAGINAS = [("panorama", "Panorama"), ("explorar", "Explorar"), ("sostenibilidad", "Sostenibilidad"),
           ("pronostico", "Pronostico"), ("clasificacion", "Promotores"), ("guia", "Guia")]


def boton(p: Pagina, x, y, w, etiqueta, link, relleno, tinta):
    obj = {"text": [{"properties": {"show": lit("true"), "text": texto(etiqueta), "fontColor": color(tinta), "fontSize": lit("11D"), "bold": lit("true")}, "selector": {"id": "default"}}],
           "fill": [{"properties": {"show": lit("true"), "fillColor": color(relleno), "transparency": lit("0D")}, "selector": {"id": "default"}}],
           "outline": [{"properties": {"show": lit("true"), "lineColor": color(VIOLETA), "roundEdge": lit("8D")}, "selector": {"id": "default"}}],
           "icon": [{"properties": {"show": lit("false")}, "selector": {"id": "default"}}]}
    p.agregar("actionButton", x, y, w, 36, objetos=obj, link=link)


def encabezado(p: Pagina, subtitulo: str, filtros=True):
    p.caja_texto(16, 6, 900, 34, f"Observatorio de Turismo Sostenible | {p.nombre}", "18pt", VIOLETA, True)
    p.caja_texto(16, 40, 1240, 24, subtitulo, "11pt", TINTA2)
    for i, (pid, nom) in enumerate(PAGINAS):
        act = pid == p.id
        boton(p, 16 + i * 150, 68, 142, nom,
              {"show": lit("true"), "type": texto("PageNavigation"), "navigationSection": texto(pid)},
              VIOLETA if act else "#FFFFFF", "#FFFFFF" if act else VIOLETA)
    if filtros:
        boton(p, 1136, 68, 128, "Restablecer", {"show": lit("true"), "type": texto("ClearAllSlicers")}, "#FFFFFF", ROSA)
        slicer(p, 16, 112, 240, 66, C("Calendario", "Anio"), "Periodo (anos)", "sinc_anio")
        slicer(p, 264, 112, 200, 66, C("Destinos", "region"), "Region", "sinc_region")
        slicer(p, 472, 112, 240, 66, C("Destinos", "destino"), "Destino", "sinc_destino")
        tarjeta(p, 720, 112, 544, 34, M("Seleccion activa"), tam="11D")
        tarjeta(p, 720, 146, 544, 32, M("Mensaje sin datos"), tam="11D", col=ROSA)


def slicer(p, x, y, w, h, f, titulo, sync=None, unico=False):
    obj = {"data": [{"properties": {"mode": texto("Dropdown")}}]}
    if unico:
        obj["selection"] = [{"properties": {"singleSelect": lit("true"), "strictSingleSelect": lit("true")}}]
    p.agregar("slicer", x, y, w, h, {"Values": [f]}, objetos=obj, sync=sync,
              titulo=None)
    p.visuales[-1]["visual"]["objects"]["header"] = [{"properties": {"show": lit("true"), "text": texto(titulo), "fontColor": color(TINTA)}}]


def tarjeta(p, x, y, w, h, f, tam="22D", col=TINTA, titulo=None):
    obj = {"labels": [{"properties": {"fontSize": lit(tam), "color": color(col)}}],
           "categoryLabels": [{"properties": {"show": lit("true" if titulo else "false")}}]}
    p.agregar("card", x, y, w, h, {"Values": [f]}, objetos=obj)


def colores(*pares):
    return [{"properties": {"fill": color(c)}, "selector": {"metadata": f"Medidas.{m}"}} for m, c in pares]


def unico(c):
    return [{"properties": {"fill": color(c)}}]


def rotulos():
    return [{"properties": {"show": lit("true")}}]


def calor(*medidas, minimo="#EDEFFA", maximo="#0B2183"):
    reglas = []
    for m in medidas:
        regla = {"FillRule": {"Input": campo(M(m)), "FillRule": {"linearGradient2": {
            "min": {"color": {"Literal": {"Value": f"'{minimo}'"}}},
            "max": {"color": {"Literal": {"Value": f"'{maximo}'"}}},
            "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}}}}}}
        reglas.append({"properties": {"backColor": {"solid": {"color": {"expr": regla}}}},
                       "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"Medidas.{m}"}})
    return reglas


GR = 16  # margen


def paginas() -> list[Pagina]:
    d = C("Destinos", "destino")
    # ---- Panorama -----------------------------------------------------------
    p1 = Pagina("panorama", "Panorama", 1000)
    encabezado(p1, "Que esta pasando en los destinos: cuanta visita hay, donde y cuanto deja.")
    for i, (m, t) in enumerate([("Visitantes", "Visitantes"), ("Variacion visitantes", "vs periodo anterior"),
                                ("Derrama USD", "Derrama"), ("Variacion derrama", "vs periodo anterior"),
                                ("Estancia promedio", "Noches por visitante"), ("Satisfaccion ponderada", "Satisfaccion (1 a 5)")]):
        tarjeta(p1, GR + i * 208, 186, 200, 72, M(m), titulo=t)
    p1.agregar("scatterChart", GR, 266, 620, 350, {"Category": [d], "X": [C("Destinos", "lon")], "Y": [C("Destinos", "lat")], "Size": [M("Visitantes")], "Series": [C("Destinos", "region")]},
               "V1. Donde esta la visita (longitud y latitud)", sub="Burbuja mayor = mas visitantes. Pase el cursor para ver la presion.", objetos={"categoryLabels": rotulos()})
    p1.agregar("lineChart", 644, 266, 620, 350, {"Category": [C("Calendario", "Anio"), C("Calendario", "Trimestre"), C("Calendario", "Mes")], "Y": [M("Visitantes")]},
               "V2. Evolucion de la visita", sub="Use las flechas de la grafica para bajar a trimestre y mes, y para subir.", objetos={"dataPoint": colores(("Visitantes", AZUL))}, jerarquia=("Category",))
    p1.agregar("clusteredBarChart", GR, 624, 620, 360, {"Category": [d], "Y": [M("Visitantes")], "Tooltips": [M("Estado de presion")]},
               "V3. Ranking de destinos", sub="Haga clic en una barra para filtrar V1, V2 y V4.", objetos={"dataPoint": unico(AZUL), "labels": rotulos()})
    p1.agregar("scatterChart", 644, 624, 620, 360, {"Category": [d], "X": [M("Visitantes")], "Y": [M("Gasto por visitante")], "Size": [M("Estancia promedio")]},
               "V4. Volumen frente a valor", sub="Derecha: mas visitantes. Arriba: cada visitante gasta mas. Es descriptivo, no causal.", objetos={"categoryLabels": rotulos()})
    # ---- Explorar -----------------------------------------------------------
    p2 = Pagina("explorar", "Explorar", 1240)
    encabezado(p2, "De donde viene el visitante, cuando llega y en que gasta.")
    p2.agregar("clusteredBarChart", GR, 186, 500, 340, {"Category": [C("Mercados", "mercado")], "Y": [M("Llegadas por mercado")], "Tooltips": [M("Participacion de mercado")]},
               "V5. De donde viene el visitante", sub="Haga clic en un mercado para filtrar el calendario V6.", objetos={"dataPoint": unico(AZUL), "labels": rotulos()})
    p2.agregar("pivotTable", 524, 186, 740, 340, {"Rows": [C("Calendario", "Anio")], "Columns": [C("Calendario", "Mes")], "Values": [M("Llegadas por mercado")]},
               "V6. Calendario de la demanda", sub="Mas oscuro = mas llegadas.", objetos={"values": calor("Llegadas por mercado")})
    p2.agregar("treemap", GR, 534, 620, 340, {"Group": [C("Destinos", "region"), d, C("GastoCategoria", "categoria")], "Values": [M("Derrama por categoria")]},
               "V7. En que se gasta", sub="Baje de region a destino y a categoria con las flechas.", jerarquia=("Group",))
    p2.agregar("scatterChart", 644, 534, 620, 340, {"Category": [C("Mensual", "fecha"), d], "X": [M("Ocupacion")], "Y": [M("Gasto diario")]},
               "V8. Ocupacion frente a gasto diario", sub="Cada punto es un destino en un mes. Asociacion, no causa.", objetos={"trend": [{"properties": {"show": lit("true")}}]})
    p2.agregar("clusteredColumnChart", GR, 882, 620, 340, {"Category": [C("Visitantes", "grupo_viaje")], "Y": [M("Gasto P25"), M("Gasto mediano"), M("Gasto P75")]},
               "V9. Gasto total segun con quien viaja", sub="Mediana y rango central (P25 a P75) de la encuesta 2023-2025.",
               objetos={"dataPoint": colores(("Gasto P25", "#FFD79B"), ("Gasto mediano", NARANJA), ("Gasto P75", "#B56A00"))})
    p2.agregar("hundredPercentStackedBarChart", 644, 882, 620, 340, {"Category": [d], "Series": [C("Visitantes", "tipo_alojamiento")], "Y": [M("Encuestas")]},
               "V10. Donde se hospeda cada destino", sub="Porcentaje de personas encuestadas (2023-2025).")
    # ---- Sostenibilidad -----------------------------------------------------
    p3 = Pagina("sostenibilidad", "Sostenibilidad", 1000)
    encabezado(p3, "A que costo: presion, huella ambiental y beneficio local.")
    p3.agregar("lineClusteredColumnComboChart", GR, 186, 620, 380, {"Category": [C("Calendario", "Anio"), C("Calendario", "Trimestre"), C("Calendario", "Mes")], "Y": [M("Visitantes")], "Y2": [M("CO2 toneladas")]},
               "V11. Crecimiento frente a huella (CO2)", sub="Compare pendientes, no alturas: los ejes tienen unidades distintas.",
               objetos={"dataPoint": colores(("Visitantes", AZUL), ("CO2 toneladas", ROSA))}, jerarquia=("Category",))
    p3.agregar("clusteredColumnChart", 644, 186, 620, 380, {"Category": [d], "Y": [M("Presion turistica")], "Tooltips": [M("Estado de presion")]},
               "V12. Semaforo de presion turistica", sub="1.0 = capacidad de carga estimada. Haga clic para filtrar V13 y V14.",
               objetos={"dataPoint": [{"properties": {"fill": {"solid": {"color": {"expr": campo(M("Color de presion"))}}}}, "selector": SEL_TODO}],
                        "labels": rotulos(),
                        "y1AxisReferenceLine": [{"properties": {"show": lit("true"), "value": lit("1D"), "lineColor": color(ROSA), "displayName": texto("Capacidad de carga")}, "selector": {"id": "1"}}]})
    ejes = ["Holgura de carga", "Empleo local", "Empresas certificadas", "Satisfaccion 0-100", "Eficiencia en CO2", "Eficiencia en residuos"]
    p3.agregar("pivotTable", GR, 574, 620, 410, {"Rows": [d], "Values": [M(e) for e in ejes]},
               "V13. Perfil de sostenibilidad (0 a 100, mas es mejor)", sub="Mas oscuro = mejor posicion en esa dimension.", objetos={"values": calor(*ejes)})
    p3.agregar("scatterChart", 644, 574, 620, 410, {"Category": [d], "X": [M("Empresas certificadas")], "Y": [M("Empleo local")], "Size": [M("Derrama USD")]},
               "V14. Beneficio local y certificacion", sub="Burbuja mayor = mas derrama. Es descriptivo, no causal.", objetos={"categoryLabels": rotulos()})
    # ---- Pronostico ---------------------------------------------------------
    p4 = Pagina("pronostico", "Pronostico", 1000)
    encabezado(p4, "Estimaciones, no datos observados. Evaluacion: ultimos 12 meses (2025). Entrenamiento desde 2022.", filtros=False)
    boton(p4, 1136, 68, 128, "Restablecer", {"show": lit("true"), "type": texto("ClearAllSlicers")}, "#FFFFFF", ROSA)
    slicer(p4, GR, 112, 320, 66, C("Alcance", "alcance"), "Serie a pronosticar", unico=True)
    slicer(p4, 344, 112, 320, 66, C("ModeloSerie", "modelo"), "Modelo para V15", unico=True)
    p4.caja_texto(680, 112, 584, 66, "Si no elige, se usa Todos los destinos y Holt-Winters (el de menor MAPE en el total). Las metricas de pronostico no son comparables con las de clasificacion.", "10pt", TINTA2)
    p4.agregar("lineChart", GR, 186, 1248, 370, {"Category": [C("PredSerie", "fecha")], "Y": [M("Observado prueba"), M("Estimado futuro"), M("Limite inferior"), M("Limite superior")]},
               "V15. Visitantes esperados en los proximos 12 meses", sub="Azul: observado en 2025. Morado: estimado para 2026, con su margen.",
               objetos={"dataPoint": colores(("Observado prueba", AZUL), ("Estimado futuro", MORADO), ("Limite inferior", "#D27BF4"), ("Limite superior", "#D27BF4"))})
    p4.agregar("lineChart", GR, 564, 800, 420, {"Category": [C("PredSerie", "fecha")], "Y": [M("Observado prueba"), M("Tendencia + estacionalidad (prueba)"), M("Holt-Winters (prueba)"), M("SARIMA (prueba)")]},
               "V16. Prueba contra la realidad (2025)", sub="Observado y estimacion de los tres modelos en meses que no vieron al entrenar.",
               objetos={"dataPoint": colores(("Observado prueba", AZUL), ("Tendencia + estacionalidad (prueba)", NARANJA), ("Holt-Winters (prueba)", MORADO), ("SARIMA (prueba)", CELESTE))})
    p4.agregar("clusteredBarChart", 824, 564, 440, 240, {"Category": [C("ModeloSerie", "modelo")], "Y": [M("Error porcentual (MAPE)")]},
               "V16b. Error porcentual por modelo (MAPE)", sub="Menor es mejor. Clic en una barra para enfatizar ese modelo.", objetos={"dataPoint": unico(MORADO), "labels": rotulos()})
    p4.agregar("tableEx", 824, 812, 440, 172, {"Values": [C("ModeloSerie", "modelo"), M("Error absoluto medio"), M("RMSE"), M("Error porcentual (MAPE)")]},
               "Tabla comparativa (visitantes y %)")
    # ---- Clasificacion ------------------------------------------------------
    p5 = Pagina("clasificacion", "Promotores", 1420)
    encabezado(p5, "Quien recomendara el destino. Evaluacion: 25% de la encuesta reservado (2 250 visitantes).", filtros=False)
    boton(p5, 1136, 68, 128, "Restablecer", {"show": lit("true"), "type": texto("ClearAllSlicers")}, "#FFFFFF", ROSA)
    mc = C("ModeloClase", "modelo")
    slicer(p5, GR, 112, 300, 66, C("Destinos", "destino"), "Destino (solo V17 y V21)", "sinc_destino")
    slicer(p5, 324, 112, 300, 66, mc, "Modelo (V20)", unico=True)
    p5.caja_texto(640, 112, 624, 66, "Falsa alarma: se predijo promotor y no lo fue. Oportunidad perdida: era promotor y no se detecto. Las metricas globales usan todo el conjunto de prueba y no cambian con el destino.", "10pt", TINTA2)
    p5.agregar("pivotTable", GR, 186, 620, 360, {"Rows": [mc, C("PredClase", "real")], "Columns": [C("PredClase", "predicho")], "Values": [M("Casos evaluados")]},
               "V17. Aciertos y errores (matriz de confusion)", sub="Filas: lo que paso. Columnas: lo que dijo el modelo.", objetos={"values": calor("Casos evaluados")})
    p5.agregar("clusteredColumnChart", 644, 186, 620, 360, {"Category": [C("MetricasClase", "metrica")], "Series": [mc], "Y": [M("Valor de metrica")]},
               "V17b. Desempeno de los tres modelos", sub="De 0 a 1: mas alto es mejor. Clic en un modelo para enfatizarlo en V18.", objetos={"labels": rotulos()})
    p5.agregar("lineChart", GR, 554, 620, 390, {"Category": [C("CurvaROC", "tasa_falsas_alarmas")], "Series": [mc], "Y": [M("Tasa de aciertos")]},
               "V18. Capacidad de distinguir (curva ROC)", sub="Mas pegada a la esquina superior izquierda es mejor.")
    p5.agregar("lineChart", 644, 554, 620, 390, {"Category": [C("CurvaAprendizaje", "tamano")], "Series": [mc], "Y": [M("AUC validacion")]},
               "V19. Sirve seguir encuestando?", sub="Si la curva se aplana, mas encuestas iguales aportan poco.")
    p5.agregar("clusteredBarChart", GR, 952, 620, 450, {"Category": [C("Importancia", "variable")], "Y": [M("Peso del factor")]},
               "V20. Que mueve la recomendacion", sub="Asociacion en la encuesta. Solo la regresion logistica tiene signo.", objetos={"dataPoint": unico(VERDE)})
    p5.agregar("tableEx", 644, 952, 620, 450, {"Values": [C("PredClase", "id_visitante"), mc, C("PredClase", "real"), C("PredClase", "predicho"), C("PredClase", "resultado"), M("Probabilidad media")]},
               "V21. Prediccion por visitante", sub="Cada visitante aparece una vez por modelo.")
    # ---- Guia ---------------------------------------------------------------
    p6 = Pagina("guia", "Guia", 720)
    encabezado(p6, "Como leer este informe, que significa cada color y que no puede responder.", filtros=False)
    filas = [("Colores", TINTA, True), ("Azul: demanda. Naranja: economia. Verde: resultado favorable. Rosa: presion o alerta. Morado: estimaciones de modelos. Violeta: navegacion.", TINTA, False),
             ("Terminos", TINTA, True), ("Derrama: gasto total de los visitantes. Presion turistica: visitantes entre capacidad de carga; 1.0 es el limite estimado. Promotor: visitante que recomendaria el destino. MAPE: error promedio en porcentaje. AUC: capacidad de distinguir promotores; 0.5 equivale al azar.", TINTA, False),
             ("Limitaciones", TINTA, True), ("Los datos son sinteticos y no son cifras oficiales. El informe muestra asociaciones, no causas. La capacidad de carga es una estimacion. Los pronosticos suponen que el patron historico continua y no incluyen crisis, rutas nuevas ni campanas.", TINTA, False),
             ("Como navegar", TINTA, True), ("Use los botones superiores para cambiar de seccion; el boton violeta indica donde esta. Haga clic en una barra para filtrar las otras graficas. Use las flechas de V2, V7 y V11 para bajar o subir de nivel. Restablecer limpia los segmentadores.", TINTA, False)]
    y = 120
    for t, c, b in filas:
        h = 34 if b else 72
        p6.caja_texto(GR, y, 1248, h, t, "14pt" if b else "12pt", VIOLETA if b else c, b)
        y += h + 4
    return [p1, p2, p3, p4, p5, p6]


def escribe(ruta: Path, obj) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


def reporte() -> None:
    d = RP / "definition"
    escribe(d / "version.json", {"$schema": f"{BASE_ESQUEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    escribe(RP / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": "../Observatorio.SemanticModel"}}})
    tema = "Observatorio.json"
    version_tema = {"visual": "2.4.0", "report": "3.0.0", "page": "2.0.0"}
    escribe(d / "report.json", {
        "$schema": f"{BASE_ESQUEMA}/report/3.0.0/schema.json",
        "themeCollection": {"customTheme": {"name": tema, "reportVersionAtImport": version_tema, "type": "RegisteredResources"}},
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": tema, "path": tema, "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True}})
    escribe(RP / "StaticResources/RegisteredResources" / tema, {
        "name": "Observatorio", "dataColors": [AZUL, VERDE, NARANJA, CELESTE, MORADO, ROSA, VIOLETA, SALMON],
        "background": "#FFFFFF", "foreground": TINTA, "tableAccent": AZUL,
        "good": VERDE, "neutral": NARANJA, "bad": ROSA, "maximum": "#0B2183", "center": "#7487DB", "minimum": "#EDEFFA",
        "textClasses": {"label": {"fontFace": "Segoe UI", "fontSize": 10, "color": TINTA},
                        "callout": {"fontFace": "Segoe UI", "fontSize": 24, "color": TINTA},
                        "title": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": TINTA},
                        "header": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": TINTA}}})
    ps = paginas()
    escribe(d / "pages/pages.json", {"$schema": f"{BASE_ESQUEMA}/pagesMetadata/1.0.0/schema.json",
                                     "pageOrder": [p.id for p in ps], "activePageName": ps[0].id})
    for p in ps:
        escribe(d / "pages" / p.id / "page.json", {
            "$schema": f"{BASE_ESQUEMA}/page/2.0.0/schema.json", "name": p.id, "displayName": p.nombre,
            "displayOption": "FitToWidth", "height": p.alto, "width": 1280,
            "objects": {"background": [{"properties": {"color": color(FONDO2), "transparency": lit("0D")}}]}})
        for v in p.visuales:
            escribe(d / "pages" / p.id / "visuals" / v["name"] / "visual.json", v)


def plataforma(carpeta: Path, tipo: str, nombre: str) -> None:
    escribe(carpeta / ".platform", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": tipo, "displayName": nombre},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_DNS, tipo + nombre))}})


if __name__ == "__main__":
    for c in (SM, RP):
        if c.exists():
            shutil.rmtree(c)
    modelo()
    reporte()
    plataforma(SM, "SemanticModel", "Observatorio")
    plataforma(RP, "Report", "Observatorio")
    escribe(PBI / "Observatorio.pbip", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": "Observatorio.Report"}}], "settings": {"enableAutoRecovery": True}})
    print("PBIP generado en", PBI)
