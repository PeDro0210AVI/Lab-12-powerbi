# Observatorio de Turismo Sostenible — Laboratorio 12 (Power BI)

Segunda version, en Power BI, del cuadro de mando del
[Laboratorio 10](https://github.com/jlope384/Laboratorio-10-Dashboard). CC3066, UVG.

**Version de Power BI Desktop usada:** [PENDIENTE: Ayuda > Acerca de]

## Estado

`powerbi/Observatorio.pbip` esta generado y validado fuera de Desktop, pero **aun no
se ha abierto en Power BI Desktop**, que solo existe para Windows. Falta:

1. Abrirlo en Windows y activar, si se pide, *Opciones > Caracteristicas de vista
   previa > Almacenar informes con formato PBIR* y *Serializacion TMDL*.
2. Cambiar `RutaDatos`, actualizar y revisar cada pagina.
3. *Archivo > Guardar como* `.pbix`.
4. Ejecutar las pruebas y completar los campos `[PENDIENTE]` de `docs/documento_diseno.md`.

## Abrir el informe y cambiar las rutas

1. Copie el repositorio a una carpeta de Windows.
2. Abra `powerbi/Observatorio.pbip`, o el `.pbix` una vez guardado.
3. *Transformar datos > Editar parametros*: en `RutaDatos`, escriba la ruta absoluta
   de `powerbi\datos`, sin barra final.
4. Pulse *Actualizar*.

Para cambiar los datos, reemplace los CSV respetando los nombres de columna y actualice.

## Estructura

```
powerbi/
  Observatorio.pbip              punto de entrada
  Observatorio.SemanticModel/    modelo en TMDL (tablas, relaciones, DAX)
  Observatorio.Report/           reporte en PBIR (paginas, visuales, tema)
  datos/origen/                  CSV del Lab 10, sin cambios
  datos/modelos/                 predicciones y metricas exportadas
  datos/indicadores_referencia.csv  valores de la prueba de consistencia
scripts/
  exportar_modelos.py            exporta resultados con modelos.py del Lab 10
  generar_pbip.py                genera el proyecto de Power BI
  validar_pbip.py                valida contra los esquemas de Microsoft
  verificar_indicadores.py       comprueba llaves y calcula indicadores
docs/
  Laboratorio_12_PowerBI_2026-1.pdf  instrucciones
  documento_diseno.md / .pdf     ejercicios 4 y 5
```

`notebooks/`, `data/` y los archivos sueltos de `reports/` son del Laboratorio 5 y no
forman parte de esta entrega.

## Tablas de predicciones y metricas

| Tabla | Archivo | Contenido | Llave |
|---|---|---|---|
| `PredSerie` | `predicciones_serie.csv` | Prueba 2025 y pronostico 2026 por alcance y modelo | `id_pred_serie` |
| `MetricasSerie` | `metricas_serie.csv` | MAE, RMSE, MAPE | alcance + modelo + metrica |
| `PredClase` | `predicciones_clasificacion.csv` | Prediccion por visitante y modelo | `id_pred_clase` |
| `MetricasClase` | `metricas_clasificacion.csv` | Exactitud, Precision, Exhaustividad, F1, AUC | modelo + metrica |
| `CurvaROC`, `CurvaAprendizaje`, `Importancia` | homonimos | Resultados adicionales | modelo + punto o variable |

`matrices_confusion.csv` se conserva como referencia; V17 cuenta directamente sobre
`PredClase`, para responder al filtro por destino.

## Regenerar

Todo corre con el `flake.nix`. Las predicciones usan el flake bloqueado del Lab 10, para
conservar sus versiones de scikit-learn y statsmodels:

```bash
nix develop ../Laboratorio-10-Dashboard --command python scripts/exportar_modelos.py
nix develop --command python scripts/generar_pbip.py
nix develop --command python scripts/verificar_indicadores.py
nix develop --command python scripts/validar_pbip.py <clon de microsoft/json-schemas>
```

Generar de nuevo **sobrescribe** los cambios hechos en Desktop dentro del PBIP.

PDF del documento:

```bash
nix develop --command pandoc docs/documento_diseno.md --from markdown --to html5 -s \
  --metadata lang=es --metadata-file docs/pdf/portada.yaml --embed-resources \
  --lua-filter docs/pdf/portada.lua --css docs/pdf/estilo.css \
  --pdf-engine weasyprint -o docs/documento_diseno.pdf
```

## Reproducir las tres pruebas

Protocolo y valores esperados en la seccion 5.3 de `docs/documento_diseno.md`.
Registre resultados, clics, tiempos y dificultades en la seccion 5.4.

## Consultar la version del Laboratorio 10

```bash
cd ../Laboratorio-10-Dashboard && nix run
```

Datos sinteticos: no son cifras oficiales.
