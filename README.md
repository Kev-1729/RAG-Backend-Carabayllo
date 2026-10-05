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
| Embeddings | _Por definir_ |
| Vector store | _Por definir_ |
| Persistencia | _Por definir_ |
| Contenedores | Docker + Docker Compose |
| Testing | Pytest, pytest-asyncio, pytest-cov |
| Calidad | Ruff, Black, isort, mypy, pre-commit |

---

## Arquitectura

El código se organiza en capas. **Las dependencias apuntan hacia adentro** y los proveedores externos quedan detrás de interfaces.

| Capa | Responsabilidad | Depende de |
| --- | --- | --- |
| `domain` | Entidades e interfaces (puertos). Python puro, sin frameworks ni SDKs. | Nada |
| `application` | Casos de uso que orquestan el dominio. | `domain` |
| `infrastructure` | Adaptadores concretos: LLM, embeddings, vector store, base de datos, loaders. | `domain`, `application` |
| `interfaces` | API HTTP: routers, schemas e inyección de dependencias. | `application`, `domain` |

---

## Estructura del proyecto

```
rag/
├── src/
│   ├── domain/            # entities, ports, exceptions
│   ├── application/
│   │   └── answer/        # caso de uso AnswerQuery
│   ├── infrastructure/
│   │   ├── db/
│   │   └── llm/           # adaptador de Anthropic
│   ├── interfaces/
│   │   ├── routers/
│   │   ├── schemas/
│   │   └── dependencies/
│   ├── config.py
│   └── main.py
├── tests/
├── requeriments/
│   ├── requirements.txt   # producción
│   └── tests.txt          # desarrollo: lint, tipos, tests
├── .env.example
├── .pre-commit-config.yaml
├── docker-compose.yml
├── dockerfile
└── pyproject.toml
```

---

## Requisitos

- Python 3.10+
- API key de Anthropic creada **dentro de un workspace** ([platform.claude.com](https://platform.claude.com))
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

pip install -r requeriments/tests.txt
pre-commit install
cp .env.example .env
```

---

## Variables de entorno

Copia `.env.example` a `.env` y completa los valores. **Nunca subas `.env` al repositorio.**

| Variable | Requerida | Descripción |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Sí | API key de Anthropic (scoped a un workspace) |
| `LLM_MODEL` | Sí | Modelo a usar, p. ej. `claude-sonnet-5-5` |
| `CORS_ALLOW_ORIGINS` | No | Orígenes permitidos separados por coma |

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

---

## Tests

```bash
pytest
```

Los proveedores externos se mockean en los tests unitarios. Se exige una cobertura mínima del **80 %** sobre `src/application`.

---

## Calidad de código

```bash
pre-commit run --all-files
```

| Herramienta | Uso |
| --- | --- |
| Ruff | Linter |
| Black | Formateo (88 columnas) |
| isort | Orden de imports |
| mypy | Tipado estático; toda función debe estar anotada |

---

## Convenciones

**Ramas**: `main` · `feat/*` · `fix/*` · `chore/*` · `refactor/*` · `docs/*`

**Commits**: [Conventional Commits](https://www.conventionalcommits.org/)

**Reglas de arquitectura**

- `domain` no importa frameworks ni SDKs externos.
- Los casos de uso reciben interfaces por constructor, nunca implementaciones.
- Los routers validan la entrada, llaman a un caso de uso y mapean la respuesta.
- Ningún endpoint expone errores internos al cliente.

---

## Roadmap

- [x] Estructura base y tooling
- [x] Configuración con `pydantic-settings`
- [x] Dominio: entidades y puertos
- [x] Endpoint de consulta conectado al LLM (sin retrieval)
- [ ] Definir embeddings y vector store
- [ ] Ingesta de documentos (PDF y otros formatos) con chunking configurable
- [ ] OCR para documentos escaneados
- [ ] Consulta RAG con citas a la fuente
- [ ] Memoria conversacional
- [ ] Feedback de usuarios y métricas de exactitud
- [ ] Evaluación automática del pipeline
- [ ] Streaming de respuestas
- [ ] Autenticación
- [ ] CI/CD

---

## Investigación

> Collado, J., & Tupac-Agüero, K. (`2026`). _Efectos del uso de un Asistente Inteligente con RAG para el Acceso a Información y Consultas sobre Servicios Públicos: Un estudio de caso en Lima, Perú_.

---

## Autores

- **Kevin Tupac-Agüero** · Universidad Nacional Mayor de San Marcos · [@Kev-1729](https://github.com/Kev-1729)
- **Jhair Collado** · Universidad Nacional Mayor de San Marcos
