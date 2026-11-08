# Evaluacion de recuperacion

Una herramienta de desarrollo: `evaluate.py` consulta Voyage y PostgreSQL usando
los adaptadores del backend. No llama a Claude ni necesita Uvicorn.

Desde la raiz del repositorio:

```powershell
.\.venv\Scripts\python.exe -m evaluations.evaluate --corpus-label fixed-1000-overlap-200
```

El set por defecto, `datasets/retrieval_reference_v2.json`, conserva las 71 preguntas
revisadas (64 positivas y 7 negativas). Varias fuentes validas pueden figurar en
`expected_documents`; una lista vacia representa una pregunta ajena.

Cada corrida crea `results/<fecha-hora-UTC>/report.json`, ignorado por Git, con el
set usado, modelo, umbral, resultados y metricas. Se conserva lo completado ante
fallos; solo `status: complete` representa una corrida completa. No hay reanudacion
ni regulacion automatica del limite de Voyage. Cada ejecucion consume su API.
Las corridas y CSV anteriores se conservan; las nuevas generan un unico JSON.

Hit@5 mide si aparece un PDF esperado entre los primeros cinco chunks. MRR@5 mide
1/posicion del primer PDF esperado (0 si falta). Se calculan antes y despues del
umbral solo sobre positivas. El rechazo correcto se calcula solo sobre negativas.
No se verifica que el fragmento contenga la respuesta completa ni se mide a Claude.

Para comparar chunkings, conservar el mismo set, modelo y umbral. La etiqueta del
corpus es declarada por quien ejecuta: no se deduce del CHUNK_SIZE actual. No cambiar
la base durante una corrida. Este comando no reingiere ni modifica documentos.
La configuracion compartida sigue requiriendo los campos de Anthropic aunque no
los usa para llamar al proveedor.

El seed anterior y el registro detallado de revision se archivaron localmente en
`../evaluaciones_archivo/`. Los informes historicos incluyen sus propios datasets.
