# RAG Backend

Backend de un sistema **RAG (Retrieval-Augmented Generation)** para responder consultas en lenguaje natural usando como fuente una base de conocimiento documental propia, con respuestas fundamentadas y trazables a sus fuentes.

Este proyecto es una **reescritura desde cero** de un sistema RAG que ya fue validado en producción y publicado en una investigación científica (ver [Origen](#origen)). Conserva el problema. El stack, los modelos y el diseño son nuevos.

---

## Tabla de contenidos

- [Origen](#origen)
- [Objetivos](#objetivos)
- [Stack](#stack)
- [Arquitectura](#arquitectura)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Variables de entorno](#variables-de-entorno)
- [Base de datos](#base-de-datos)
- [Ejecución](#ejecución)
- [Tests](#tests)
- [Calidad de código](#calidad-de-código)
- [Convenciones](#convenciones)
- [Roadmap](#roadmap)
- [Investigación](#investigación)
- [Autores](#autores)

---

## Origen

La primera versión fue un asistente de trámites municipales para la Municipalidad de Carabayllo (Lima, Perú). Se evaluó con un diseño experimental con grupo de control (n = 30 por grupo) y obtuvo mejoras estadísticamente significativas (p < 0.001) en los cuatro indicadores:

| Indicador | Canal tradicional | Asistente RAG |
| --- | --- | --- |
| Consultas atendidas / día | 64.53 | **94.20** |
| Exactitud de respuesta | 86.50 % | **92.97 %** |
| Tiempo de espera | ~4.5 días | **~22 min** |
| Satisfacción del usuario | Mayoría en desacuerdo | Mayoría de acuerdo |

Los resultados están publicados en el artículo citado en [Investigación](#investigación).

---

## Objetivos

- Respuestas **fundamentadas** solo en la base de conocimiento, con **citas a la fuente**.
- Pipeline de ingesta y recuperación **configurable y reemplazable** (modelos, chunking, vector store).
- **Evaluación medible** de la calidad del RAG, no solo feedback manual.
- Código tipado, testeado y desacoplado de proveedores.

---

## Stack

| Componente | Tecnología |
| --- | --- |
| Lenguaje | Python 3.10+ |
| Framework HTTP | FastAPI |
| LLM | claude-sonnet-5-5 |
| Embeddings | Voyage AI (`voyage-4`, 1024 dimensiones) |
| Lectura de PDF | pypdf |
| Vector store | PostgreSQL + pgvector (Supabase) |
| Persistencia | SQLAlchemy async + asyncpg, migraciones con Alembic |
| Contenedores | Docker + Docker Compose |
| Testing | Pytest, pytest-asyncio, pytest-cov |
| Calidad | Ruff, mypy, pre-commit, GitHub Actions |

---

## Arquitectura

El código se organiza en capas. **Las dependencias apuntan hacia adentro** y los proveedores externos quedan detrás de interfaces.

| Capa | Responsabilidad | Depende de |
| --- | --- | --- |
| `domain` | Entidades e interfaces (puertos). Python puro, sin frameworks ni SDKs. | Nada |
| `application` | Casos de uso que orquestan el dominio. | `domain` |
| `infrastructure` | Adaptadores concretos: LLM, embeddings, vector store, base de datos, loaders. | `domain` |
| `container` | Raíz de composición: crea adaptadores, los inyecta en los casos de uso y administra recursos (p. ej. el engine). | `application`, `domain`, `infrastructure`, `config` |
| `interfaces` | Adaptadores de entrada: API HTTP, CLI, schemas y el puente `Depends` de FastAPI. | `application`, `domain`, `container` |

`container` centraliza la construcción de adaptadores y casos de uso. Los adaptadores de entrada obtienen desde allí los casos de uso ya configurados. `interfaces` no importa `infrastructure` ni `config`.

---

## Estructura del proyecto

```
rag/
├── src/
│   ├── domain/            # entities, ports, exceptions
│   ├── application/
│   │   ├── answer/        # respuesta RAG y conversación
│   │   └── ingest/        # IngestDocuments y chunking semántico
│   ├── infrastructure/
│   │   ├── db/            # conexión, modelos ORM y repositorio de documentos
│   │   ├── embeddings/    # adaptador de Voyage AI
│   │   ├── llm/           # adaptador de Anthropic
│   │   └── pdf/           # lector de PDF (pypdf)
│   ├── container/         # raíz de composición (arma casos de uso)
│   ├── interfaces/
│   │   ├── cli/           # comando de ingesta
│   │   ├── routers/
│   │   ├── schemas/
│   │   └── dependencies/  # puente FastAPI → container
│   ├── config.py
│   └── main.py
├── migrations/            # migraciones de Alembic
├── tests/
├── requirements/
│   ├── requirements.txt   # producción
│   └── tests.txt          # desarrollo: lint, tipos, tests
├── .env.example
├── .pre-commit-config.yaml
├── alembic.ini
├── docker-compose.yml
├── dockerfile
└── pyproject.toml
```

---

## Requisitos

- Python 3.10+
- API key de Anthropic creada **dentro de un workspace** ([platform.claude.com](https://platform.claude.com))
- Proyecto de [Supabase](https://supabase.com) (PostgreSQL con pgvector)
- Docker y Docker Compose (opcional)

---

## Instalación

```bash
git clone https://github.com/Kev-1729/RAG-Backend-Carabayllo.git
cd RAG-Backend-Carabayllo

python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -r requirements/tests.txt
pre-commit install
cp .env.example .env   # completa las variables (ver abajo)
alembic upgrade head   # crea el esquema en tu base de datos
```

Cada desarrollador usa su propio proyecto de Supabase. Después de un `git pull` que traiga migraciones nuevas, vuelve a ejecutar `alembic upgrade head`.

---

## Variables de entorno

Copia `.env.example` a `.env` y completa los valores. **Nunca subas `.env` al repositorio.**

| Variable | Requerida | Descripción |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Sí | API key de Anthropic (scoped a un workspace) |
| `LLM_MODEL` | Sí | Modelo a usar, p. ej. `claude-sonnet-5-5` |
| `DATABASE_URL` | Sí | Conexión a PostgreSQL. En Supabase: **Connect → Direct → Session pooler**, cambiando `postgresql://` por `postgresql+asyncpg://` y agregando `?ssl=require` |
| `CORS_ALLOW_ORIGINS` | No | Orígenes permitidos separados por coma |
| `VOYAGE_API_KEY` | Sí | API key de Voyage AI ([dashboard.voyageai.com](https://dashboard.voyageai.com)). Sin método de pago el límite es de 3 peticiones por minuto |
| `EMBEDDING_MODEL` | No | Modelo de embeddings. Por defecto `voyage-4`; debe generar vectores de 1024 dimensiones |
| `CHUNK_SIZE` | No | Tope en caracteres para un grupo de varios párrafos. Por defecto `1000`. Un párrafo solo no se corta |
| `RETRIEVAL_MAX_DISTANCE` | No | Distancia coseno máxima aceptada, entre 0 y 2. Por defecto `0.5`, valor inicial pendiente de calibración con preguntas reales |

---

## Base de datos

| Tabla | Propósito |
| --- | --- |
| `documents` | Un registro por PDF ingerido. El `sha256` del archivo evita ingerir el mismo documento dos veces. Si una versión nueva lo reemplaza, se conserva y `superseded_by_id` apunta a la nueva. |
| `chunks` | Fragmentos de cada documento con su página inicial (para las citas) y su embedding (`vector(1024)`), indexado con HNSW para la búsqueda por similitud. |
| `conversations` | Una fila por conversación. Agrupa los mensajes para la memoria conversacional. |
| `messages` | Una fila por pregunta (`user`) o respuesta (`assistant`), en orden por `created_at`. Las nuevas respuestas guardan latencia y, cuando interviene el LLM, modelo y tokens reportados por el proveedor. |
| `ratings` | Calificación de 1 a 5 estrellas de una respuesta. Opcional y una sola por respuesta. |
| `message_references` | Chunks del contexto de respuestas sin abstención, con su puesto (`rank`) y similitud coseno (`score`). No certifican citas utilizadas por el modelo. |

El detalle de columnas está en [`src/infrastructure/db/models.py`](src/infrastructure/db/models.py) y en [`migrations/versions/`](migrations/versions/). Todas las tablas tienen **RLS activado** para que la Data API de Supabase no pueda acceder a ellas; el backend se conecta directo a PostgreSQL.

```bash
alembic upgrade head                                  # aplica las migraciones pendientes
alembic downgrade -1                                  # revierte la última
alembic revision --autogenerate -m "descripción"      # crea una migración a partir de los modelos
alembic check                                         # verifica que modelos y base estén sincronizados
```

**Reglas**

- El esquema **nunca** se modifica desde el dashboard de Supabase: todo cambio es una migración nueva en un PR.
- Las migraciones autogeneradas se revisan antes de commitear (extensiones y RLS se agregan a mano).
- Una migración ya aplicada en otra base no se edita; se corrige con una nueva.
- Las claves foráneas usan `RESTRICT`: no se borran conversaciones con mensajes ni chunks que ya fueron citados.

---

## Ejecución

```bash
uvicorn src.main:app --reload --port 8000
```

Documentación interactiva: http://localhost:8000/docs

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Qué necesito para sacar una licencia de funcionamiento?"}'
```

### Consultas RAG

`POST /query` genera el embedding de la pregunta, busca hasta cinco fragmentos de documentos vigentes y conserva únicamente aquellos cuya distancia es menor o igual a `RETRIEVAL_MAX_DISTANCE`. Claude recibe la pregunta y ese contexto, con instrucciones de responder solo a partir de los documentos y citar las fuentes numeradas.

Toda respuesta exitosa incluye `answer`, `sources`, `conversation_id` y `message_id`, también cuando el asistente se abstiene. Por ejemplo:

```json
{
  "answer": "Presenta el formulario indicado [1].",
  "sources": [{"document": "Licencias", "page": 2}],
  "conversation_id": "e35e2d73-9f02-4a35-9cba-7febdc995238",
  "message_id": "7a1c6d84-3741-4f8b-9b27-c7a4d0e03a25"
}
```

Las fuentes describen el contexto enviado al modelo y se deduplican por identificador de documento y página inicial. El número `[1]` corresponde al primer elemento de `sources`; `page` indica dónde empieza el fragmento. La lista no certifica que el modelo haya utilizado todos los fragmentos ni valida automáticamente cada afirmación.

Sin fragmentos relevantes, se devuelve una respuesta fija en español con `sources: []`, sin llamar a Claude. Si el modelo considera insuficiente el contexto, se le indica devolver la misma abstención. Las preguntas vacías devuelven 422; la indisponibilidad de Voyage, de la búsqueda o de Claude devuelve 503 sin detalles internos.

El [lifespan de FastAPI](https://fastapi.tiangolo.com/advanced/events/) obtiene el caso de uso desde `container`, crea el engine y los adaptadores una vez por instancia de aplicación y cierra el engine y el cliente LLM al apagarla. Cada búsqueda usa su propia sesión de base de datos.

### Streaming interno (en desarrollo)

`LLM.stream(system, prompt)` entrega fragmentos `str` y una única `Generation`
final con el texto completo, modelo y tokens reportados por el proveedor.
`AnswerQuery.stream(query, history=...)` entrega texto provisional y termina con
un `Answer` que aplica las mismas reglas de contexto, fuentes, referencias y
abstención que `execute`. Sin contexto relevante, devuelve la abstención sin
invocar al LLM. Las fuentes definitivas se conocen al finalizar: el modelo puede
abstenerse después de recibir contexto.

Un stream truncado, un límite de salida o un error no producen resultado final.
Al consumir parcialmente estos generadores se debe usar `contextlib.aclosing`
o llamar a `aclose()` para liberar la conexión del proveedor. Los fragmentos
anteriores a un error son provisionales. Los tokens se obtienen del resultado
final, no se estiman contando fragmentos.

`ConversationQuery.stream(query)` carga el historial y entrega texto provisional.
Tras completar la generación, guarda el turno con sus referencias y métricas
en la transacción habitual. El `Answer` final se emite después del guardado e
incluye los identificadores de conversación y mensaje. Un error o una
cancelación durante la generación descartan el turno parcial.

### Conversaciones y memoria

`POST /query` acepta `conversation_id` opcional. Sin él, guarda una conversación
nueva; con él, recupera los últimos diez mensajes y continúa la conversación.
Devuelve `conversation_id` y `message_id` (identificador de la respuesta), además
de `answer` y `sources`.

```json
{"question": "¿Qué necesito para una licencia de bodega?"}
```

Para continuar, usa el `conversation_id` devuelto:

```json
{"question": "¿Y cuánto cuesta?", "conversation_id": "UUID recibido"}
```

`GET /conversations/{conversation_id}?limit=50` devuelve los mensajes recientes en
orden cronológico (`limit`: 1–100). Un UUID inválido devuelve 422; una conversación
inexistente devuelve 404; la indisponibilidad del almacenamiento devuelve 503.

Cada pregunta y respuesta se guardan juntas en una transacción, incluidas las
abstenciones. Si falla la generación, no se guarda un turno incompleto. Un error
de disponibilidad al guardar devuelve 503 aunque la generación haya terminado; reenviar crea una
nueva ejecución (no hay idempotencia). No se modifica el esquema de base de datos.

Para la búsqueda se combinan las preguntas del historial reciente con la actual.
El modelo recibe también los mensajes recientes, limitados a 2000 caracteres por
mensaje, solo para interpretar referencias; las fuentes factuales siguen siendo
los fragmentos recuperados. Es contexto limitado, no memoria ilimitada ni una
reescritura inteligente de consultas: un cambio de tema puede introducir ruido en
la búsqueda. Iniciar otra conversación permite separar temas.

Cada respuesta con contexto y sin abstención conserva en `message_references` los UUID de los chunks
enviados al modelo, su posición desde 1 entre los fragmentos aceptados y su similitud
coseno (`score = 1 - distance`, entre -1 y 1, no una probabilidad). Un valor negativo
es válido si el umbral configurado admite distancias mayores que 1. Se guardan en la misma
transacción que los mensajes. Dos chunks de una página conservan referencias
distintas aunque aparezcan como una sola fuente HTTP. Las abstenciones no guardan
referencias. Esto registra el contexto proporcionado; no certifica qué afirmaciones
utilizó el modelo ni reconstruye referencias para mensajes anteriores.

El historial recuperado contiene texto, rol, fecha e identificador; las referencias
se conservan en base de datos y no se agregan al contrato HTTP del historial. No hay listado
público de conversaciones: el cliente debe conservar su UUID. El UUID no sustituye
la protección de acceso; la aplicación sigue sin login y la política de retención
y protección de conversaciones debe definirse antes del despliegue.

### Reemplazo de documentos

La ingesta habitual sigue omitiendo archivos cuyo SHA-256 ya existe, incluso si
pertenece a una versión histórica reemplazada; no reactiva versiones anteriores.
Para reemplazar
una versión, coloca solamente el PDF nuevo en una carpeta y pasa el UUID del
documento vigente explícitamente:

```powershell
.\.venv\Scripts\python.exe -m src.interfaces.cli.ingest "ruta/carpeta-nueva-version" --replace UUID_DEL_DOCUMENTO_VIGENTE
```

El UUID se obtiene de `documents.id` en la base de desarrollo. No se deducen
reemplazos por nombre ni título. La versión nueva y sus chunks se guardan junto
con `superseded_by_id` de la anterior en una sola transacción, bloqueando la fila
anterior para impedir reemplazos simultáneos. Una versión inexistente, ya
reemplazada o un contenido que ya existe se reportan como fallo. Si la extracción,
el chunking, los embeddings o el guardado fallan, la versión anterior sigue vigente.
Los errores de proveedores interrumpen la ejecución como en la ingesta habitual.

Se conservan todos los documentos, chunks y referencias históricos. Las búsquedas
nuevas excluyen las versiones reemplazadas; el historial existente no se reescribe.
Una cadena A → B → C conserva sus versiones; para el siguiente reemplazo se indica
el UUID de C. No requiere migración ni reingesta de los documentos existentes.

### Calificaciones de respuestas

Usa el `message_id` devuelto por `/query` para registrar una única calificación:

```http
POST /messages/{message_id}/rating
Content-Type: application/json

{"stars": 4}
```

Devuelve **201** con `message_id` y `stars`. Se aceptan enteros de 1 a 5; no se
convierten cadenas, booleanos ni decimales. Un UUID inválido, estrellas inválidas
o un mensaje del usuario devuelven **422**; un mensaje inexistente, **404**; una
respuesta ya calificada, **409**; y la indisponibilidad de almacenamiento, **503**.
La calificación no se modifica ni se elimina. La restricción de una por respuesta
también se aplica a solicitudes simultáneas mediante la clave primaria existente.

Se reutiliza `ratings`, sin migraciones ni llamadas a Voyage o Claude. Calificar no
modifica el consumo ni la latencia de la respuesta. La regla es una calificación por
mensaje, no por persona; no se añade autenticación en este cambio.

### Consumo y latencia de respuestas

Se guardan los campos existentes de la fila `assistant` en `messages`:

| Campo | Qué registra |
| --- | --- |
| `model` | Modelo devuelto por Anthropic, no solo el alias configurado. |
| `input_tokens` | Tokens de entrada informados en `usage.input_tokens`. |
| `output_tokens` | Tokens de salida informados en `usage.output_tokens`. |
| `latency_ms` | Tiempo de procesamiento de la consulta, en milisegundos. |

La latencia se mide con un reloj monotónico desde antes de cargar el historial
hasta obtener la respuesta: incluye historial, Voyage, búsqueda y generación,
con las esperas/reintentos del SDK que ocurran dentro de esas etapas. Excluye el
guardado final de los mensajes, la serialización HTTP y la red del navegador.

Si no hay contexto relevante y no se llama al LLM, se guarda `model = null` y
ambos contadores de tokens en `0`, además de la latencia. Eso no significa que
Voyage haya sido gratuito. Si Claude responde con abstención, se conserva el
consumo que reportó. Los mensajes `user` mantienen estos campos en `null`.
No se rellenan retrospectivamente los registros antiguos ni se persisten métricas
de solicitudes fallidas. Si falla el guardado, también se pierden las métricas
de esa solicitud, aunque el proveedor haya consumido tokens.

Estos datos permiten estimar el costo de la generación con las tarifas del modelo,
pero no constituyen una factura ni incluyen consumo de Voyage, ingesta o solicitudes
fallidas. Tampoco desglosan tarifas especiales de caché. No se guarda un importe
monetario ni se fijan precios en el código. No se requieren migraciones y el JSON
público de `/query` y del historial mantiene su contrato.

Puedes consultar una respuesta en Supabase, tabla `messages`, usando su `message_id`:

```sql
SELECT id, model, input_tokens, output_tokens, latency_ms
FROM messages
WHERE id = 'UUID de la respuesta';
```

### Ingesta por CLI

```bash
python -m src.interfaces.cli.ingest "ruta/a/la/carpeta"
```

Lee los PDF de la carpeta, extrae párrafos (pypdf en modo layout) y pide al LLM que los agrupe por significado. El modelo solo devuelve rangos JSON; el texto de cada chunk es el original. Un chunk puede abarcar varias páginas si pertenecen al mismo grupo semántico. `CHUNK_SIZE` limita grupos de varios párrafos; un párrafo individual no se corta. El campo `page` guarda la página del primer párrafo de cada fragmento, por lo que las referencias indican su página inicial y el contenido puede continuar en páginas posteriores. Luego Voyage genera los embeddings y se guardan en `documents` y `chunks`.

El reporte indica, por archivo ingerido, cuántas páginas y fragmentos quedaron. Los documentos ya ingeridos se omiten (por su `sha256`). Un archivo ilegible, un PDF dañado o un agrupado inválido se reporta sin detener el resto. Si Voyage o el LLM no responden, el comando se detiene; al volver a correrlo se omiten los que ya estaban guardados.

Si cambias el chunking, el `sha256` no cambia: hay que vaciar `chunks` y `documents` en la base de desarrollo antes de reingerir.

---

### Componentes de búsqueda vectorial

`Embedder.embed_query` genera el vector de una pregunta con `input_type="query"`, usando el modelo y la dimensión configurados en el mismo adaptador que genera los embeddings de documentos. El puerto `ChunkRetriever` permite buscar hasta `k` fragmentos (5 por defecto); su adaptador SQLAlchemy ordena por distancia coseno ascendente y excluye documentos con `superseded_by_id` no nulo. Cada resultado contiene texto, identificador, título y nombre de archivo del documento, página inicial y distancia (menor significa más parecido).

La consulta es compatible con el índice HNSW de distancia coseno existente. HNSW es aproximado: los filtros pueden reducir la cantidad de resultados; el uso efectivo del índice y la calidad de recuperación requieren validación con PostgreSQL y datos reales. Referencias: [embeddings de Voyage](https://docs.voyageai.com/docs/embeddings) y [filtrado en pgvector](https://github.com/pgvector/pgvector#filtering).

`POST /query` ejecuta `ConversationQuery`, que recupera y guarda el historial y delega la respuesta RAG a `AnswerQuery` mediante el protocolo `Answerer`. La selección por umbral, las fuentes y la abstención pertenecen a `AnswerQuery`. Una búsqueda sin filas devuelve una lista vacía; los fallos de conexión o timeout generan `RetrievalUnavailableError`, que HTTP traduce a 503.

## Tests

### Evaluación de recuperación

El comando `python -m evaluations.evaluate --corpus-label fixed-1000-overlap-200`
evalúa preguntas etiquetadas con Voyage y Supabase reales, sin llamar a Claude.
Guarda un `report.json` por ejecución en `evaluations/results/<fecha-hora>/`,
ignorado por Git. El set revisado y las métricas se describen en
[`evaluations/README.md`](evaluations/README.md). Es una medición a nivel de documento;
no valida la calidad de las respuestas del LLM.

```bash
pytest
```

Los proveedores externos se mockean en los tests unitarios. Se exige una cobertura mínima del **80 %** sobre `src/application`.

Las pruebas de búsqueda verifican el SQL compilado para PostgreSQL, el mapeo de resultados y los errores con sesiones simuladas. Las de Voyage comprueban los parámetros enviados al SDK, los lotes y los errores. No consumen APIs ni acceden a Supabase; no sustituyen una prueba de integración con pgvector.

---

## Calidad de código

```bash
pre-commit run --all-files
```

| Herramienta | Uso |
| --- | --- |
| Ruff | Linter, orden de imports y formateo (88 columnas) |
| mypy | Tipado estático; toda función debe estar anotada |

Estas mismas verificaciones, más `pytest`, corren en GitHub Actions en cada pull request.

---

## Convenciones

**Ramas**: `main` · `feat/*` · `fix/*` · `chore/*` · `refactor/*` · `docs/*`

**Commits**: [Conventional Commits](https://www.conventionalcommits.org/)

**Reglas de arquitectura**

- `domain` no importa frameworks ni SDKs externos.
- Los casos de uso reciben sus dependencias por constructor, dependen de los puertos del dominio y no consultan `container`.
- Solo `container` construye adaptadores concretos y los inyecta en los casos de uso.
- `interfaces` no importa `infrastructure` ni `config`; obtiene los casos de uso desde `container`.
- Los routers validan la entrada, llaman a un caso de uso y mapean la respuesta.
- Ningún endpoint expone errores internos al cliente.

---

## Roadmap

- [x] Estructura base y tooling
- [x] Configuración con `pydantic-settings`
- [x] Dominio: entidades y puertos
- [x] Endpoint de consulta conectado al LLM
- [x] Base de datos: PostgreSQL + pgvector con migraciones (Alembic)
- [x] Ingesta de documentos PDF con chunking semántico
- [ ] Ingesta de otros formatos
- [ ] OCR para documentos escaneados
- [x] Flujo de consulta RAG con fuentes y abstención (pendiente de validación con servicios reales)
- [x] Memoria conversacional con historial limitado (pendiente de validación con servicios reales)
- [x] Calificación de respuestas de 1 a 5 estrellas (pendiente de validación con Supabase real)
- [ ] Métricas de exactitud de las respuestas
- [x] Registro de consumo de tokens y latencia para estimar costos (consumo real de Claude pendiente de validación)
- [ ] Evaluación automática del pipeline
- [ ] Streaming de respuestas
- [ ] Autenticación
- [x] CI (GitHub Actions)
- [ ] Despliegue (CD)

---

## Investigación

> Collado, J., & Tupac-Agüero, K. (`2026`). _Efectos del uso de un Asistente Inteligente con RAG para el Acceso a Información y Consultas sobre Servicios Públicos: Un estudio de caso en Lima, Perú_.

---

## Autores

- **Kevin Tupac-Agüero** · Universidad Nacional Mayor de San Marcos · [@Kev-1729](https://github.com/Kev-1729)
- **Jhair Collado** · Universidad Nacional Mayor de San Marcos
