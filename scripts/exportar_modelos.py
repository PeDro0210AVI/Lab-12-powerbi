"""Exporta a CSV los datos y resultados de los modelos del Laboratorio 10.

No define modelos: importa `app/modelos.py` del Lab 10 y usa sus funciones,
hiperparametros, division 75/25 y semilla. Los resultados de clasificacion por
visitante no los guardaba el Lab 10, asi que se reconstruyen con esas mismas
definiciones y se comprueba que den la misma matriz de confusion.

Uso: python scripts/exportar_modelos.py [ruta/a/Laboratorio-10-Dashboard]
"""
from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.disable(logging.WARNING)  # avisos de cache de Streamlit fuera de `streamlit run`

RAIZ = Path(__file__).resolve().parent.parent
LAB10 = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else RAIZ.parent / "Laboratorio-10-Dashboard"
ORIGEN = RAIZ / "powerbi" / "datos" / "origen"
RESULTADOS = RAIZ / "powerbi" / "datos" / "modelos"
ANIO_INICIO = 2022  # valor por defecto del selector "Entrenar con datos desde" (V15)
TODOS = "Todos los destinos"

sys.path.insert(0, str(LAB10 / "app"))
import datos as dt  # noqa: E402
import modelos as mo  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import confusion_matrix  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.neighbors import KNeighborsClassifier  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.tree import DecisionTreeClassifier  # noqa: E402

SEMILLA = 42


def exportar_serie(mensual: pd.DataFrame) -> pd.DataFrame:
    """Un pronostico por modelo para el total y para cada destino, como en V15/V16."""
    historia = mensual[mensual["anio"] >= ANIO_INICIO]
    alcances = {TODOS: historia, **{d: g for d, g in historia.groupby("destino")}}
    filas, metricas = [], []
    for alcance, sub in alcances.items():
        for nombre, r in mo.pronosticar(dt.serie_nacional(sub)).items():
            p = r.prueba.assign(modelo=nombre, conjunto="Prueba (ultimos 12 meses)",
                                inferior=np.nan, superior=np.nan)
            f = r.futuro.assign(modelo=nombre, conjunto="Pronostico (12 meses futuros)", real=np.nan)
            filas += [p.assign(alcance=alcance), f.assign(alcance=alcance)]
            metricas += [{"alcance": alcance, "modelo": nombre, "metrica": k, "valor": v,
                          "conjunto_evaluacion": "Ultimos 12 meses observados (2025)"}
                         for k, v in r.metricas.items()]
    salida = pd.concat(filas, ignore_index=True)
    salida["id_pred_serie"] = np.arange(1, len(salida) + 1)
    salida["error"] = salida["real"] - salida["estimado"]
    columnas = ["id_pred_serie", "alcance", "modelo", "fecha", "conjunto", "real", "estimado",
                "error", "inferior", "superior"]
    salida[columnas].to_csv(RESULTADOS / "predicciones_serie.csv", index=False, date_format="%Y-%m-%d")
    pd.DataFrame(metricas).to_csv(RESULTADOS / "metricas_serie.csv", index=False)
    return pd.DataFrame(metricas)


def exportar_clase(visitantes: pd.DataFrame) -> pd.DataFrame:
    res = mo.clasificar(visitantes)
    columnas_x = mo.VARIABLES_CLASE_NUM + mo.VARIABLES_CLASE_CAT
    df = visitantes.dropna(subset=columnas_x + ["promotor"])
    y = df["promotor"].astype(int)
    X_tr, X_te, y_tr, y_te = train_test_split(df[columnas_x], y, test_size=0.25,
                                              random_state=SEMILLA, stratify=y)
    definiciones = {
        "Regresion logistica": LogisticRegression(max_iter=2000, C=1.0),
        "Arbol de decision": DecisionTreeClassifier(max_depth=5, min_samples_leaf=40,
                                                    random_state=SEMILLA),
        "K vecinos cercanos": KNeighborsClassifier(n_neighbors=35, weights="distance"),
    }
    preds, mets, confs, rocs, imps, curvas = [], [], [], [], [], []
    etiqueta = {0: "No promotor", 1: "Promotor"}
    for nombre, est in definiciones.items():
        tub = Pipeline([("prep", mo._preprocesador()), ("modelo", est)]).fit(X_tr, y_tr)
        pred = tub.predict(X_te)
        r = res[nombre]
        if not np.array_equal(confusion_matrix(y_te, pred), r.matriz):
            raise SystemExit(f"{nombre}: la matriz no coincide con la del Lab 10")
        preds.append(pd.DataFrame({
            "id_visitante": df.loc[X_te.index, "id_visitante"].to_numpy(), "modelo": nombre,
            "real": y_te.map(etiqueta).to_numpy(), "predicho": pd.Series(pred).map(etiqueta).to_numpy(),
            "prob_promotor": tub.predict_proba(X_te)[:, 1]}))
        mets += [{"modelo": nombre, "metrica": k, "valor": v,
                  "conjunto_evaluacion": "25% de la encuesta reservado (estratificado)"}
                 for k, v in r.metricas.items()]
        for i, real in enumerate(("No promotor", "Promotor")):
            for j, dicho in enumerate(("No promotor", "Promotor")):
                confs.append({"modelo": nombre, "real": real, "predicho": dicho,
                              "casos": int(r.matriz[i, j])})
        rocs.append(pd.DataFrame({"modelo": nombre, "tasa_falsas_alarmas": r.roc[0],
                                  "tasa_aciertos": r.roc[1]}))
        imps.append(r.importancia.assign(modelo=nombre, tipo=r.tipo_importancia))
        curvas.append(r.curva_aprendizaje.assign(modelo=nombre))
    p = pd.concat(preds, ignore_index=True)
    p["id_pred_clase"] = np.arange(1, len(p) + 1)
    p["resultado"] = np.select(
        [(p.real == "Promotor") & (p.predicho == "Promotor"),
         (p.real == "No promotor") & (p.predicho == "No promotor"),
         (p.real == "No promotor") & (p.predicho == "Promotor")],
        ["Acierto: promotor", "Acierto: no promotor", "Falsa alarma"], "Oportunidad perdida")
    p[["id_pred_clase", "id_visitante", "modelo", "real", "predicho", "resultado",
       "prob_promotor"]].to_csv(RESULTADOS / "predicciones_clasificacion.csv", index=False)
    pd.DataFrame(mets).to_csv(RESULTADOS / "metricas_clasificacion.csv", index=False)
    pd.DataFrame(confs).to_csv(RESULTADOS / "matrices_confusion.csv", index=False)
    pd.concat(rocs).to_csv(RESULTADOS / "curvas_roc.csv", index=False)
    pd.concat(imps).to_csv(RESULTADOS / "importancia_variables.csv", index=False)
    pd.concat(curvas).to_csv(RESULTADOS / "curvas_aprendizaje.csv", index=False)
    return pd.DataFrame(mets)


if __name__ == "__main__":
    ORIGEN.mkdir(parents=True, exist_ok=True)
    RESULTADOS.mkdir(parents=True, exist_ok=True)
    for f in dt.ARCHIVOS.values():
        shutil.copy2(f, ORIGEN / f.name)
    base = dt.cargar()
    m = exportar_serie(base["mensual"])
    print(m[m.alcance == TODOS].pivot(index="modelo", columns="metrica", values="valor"))
    print(exportar_clase(base["visitantes"]).pivot(index="modelo", columns="metrica", values="valor"))
