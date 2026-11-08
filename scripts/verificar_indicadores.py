"""Comprueba las llaves del modelo y calcula los indicadores de referencia (ejercicio 5.5)."""
from pathlib import Path

import pandas as pd

D = Path(__file__).resolve().parent.parent / "powerbi" / "datos"
men = pd.read_csv(D / "origen/turismo_mensual.csv")
mer = pd.read_csv(D / "origen/mercados.csv")
vis = pd.read_csv(D / "origen/visitantes.csv")
pc = pd.read_csv(D / "modelos/predicciones_clasificacion.csv")
ps = pd.read_csv(D / "modelos/predicciones_serie.csv")
ms = pd.read_csv(D / "modelos/metricas_serie.csv")
mc = pd.read_csv(D / "modelos/metricas_clasificacion.csv")

pruebas = {
    "id_visitante es unico en Visitantes": vis.id_visitante.is_unique,
    "visitante + modelo es unico en PredClase": not pc.duplicated(["id_visitante", "modelo"]).any(),
    "toda prediccion tiene visitante": pc.id_visitante.isin(vis.id_visitante).all(),
    "cada modelo evalua 2250 visitantes": (pc.groupby("modelo").size() == 2250).all(),
    "los tres modelos usan los mismos visitantes": pc.groupby("modelo").id_visitante.apply(lambda s: tuple(sorted(s))).nunique() == 1,
    "alcance + modelo + fecha + conjunto es unico en PredSerie": not ps.duplicated(["alcance", "modelo", "fecha", "conjunto"]).any(),
    "un destino tiene un solo perfil": men[["destino", "region", "perfil", "lat", "lon", "capacidad_carga"]].drop_duplicates().destino.is_unique,
    # El generador del Lab 10 redondea por mercado: se admite +-3 visitantes por destino-mes.
    "mercados suma las llegadas mensuales (+-3 por redondeo)": (mer.groupby(["fecha", "destino"]).llegadas.sum().sort_index() - men.set_index(["fecha", "destino"]).llegadas.sort_index()).abs().max() <= 3,
}
for k, v in pruebas.items():
    print("OK " if v else "FALLA", k)


def periodo(df, a, b, destino=None):
    s = df[df.anio.between(a, b)]
    return s[s.destino == destino] if destino else s


filas = []
for etq, dest in (("Todos los destinos", None), ("Antigua Guatemala", "Antigua Guatemala")):
    act, ant = periodo(men, 2022, 2025, dest), periodo(men, 2018, 2021, dest)
    filas += [
        (f"Visitantes 2022-2025 | {etq}", act.llegadas.sum()),
        (f"Derrama USD 2022-2025 | {etq}", act.gasto_total_usd.sum()),
        (f"Variacion visitantes vs 2018-2021 (%) | {etq}", (act.llegadas.sum() / ant.llegadas.sum() - 1) * 100),
        (f"Estancia ponderada | {etq}", (act.estancia_promedio * act.llegadas).sum() / act.llegadas.sum()),
    ]
for m, g in ms[(ms.alcance == "Todos los destinos") & (ms.metrica == "MAPE")].groupby("modelo"):
    filas.append((f"MAPE (%) | {m}", g.valor.iloc[0]))
for m, g in mc[mc.metrica == "AUC"].groupby("modelo"):
    filas.append((f"AUC | {m}", g.valor.iloc[0]))
for (m, r), g in pc.groupby(["modelo", "resultado"]):
    filas.append((f"Casos {r} | {m}", len(g)))
t = pd.DataFrame(filas, columns=["indicador", "valor_lab10"])
t.to_csv(D / "indicadores_referencia.csv", index=False)
print(t.to_string())
a = men[men.anio.between(2022, 2025)].groupby("destino").presion_turistica.mean().sort_values()
print(a.round(3).to_string())
