# Operación del backend

## Estado y alcance

La imagen y Compose permiten ejecutar la API localmente. CI tiene un job para
construir la imagen, aplicar las migraciones en PostgreSQL con pgvector y
comprobar el proceso HTTP. Ese job utiliza una base desechable y credenciales
ficticias; no llama a Anthropic ni Voyage y no se conecta a Supabase.

El proveedor de alojamiento, el dominio y el mecanismo de CD siguen pendientes.
Este documento describe el procedimiento operativo que deberá adaptar el
despliegue. No hay publicación de imágenes ni despliegue automático configurados.

## Mantenimiento del job de CI

El job `container` espera la revisión `0003` y ocho tablas con RLS, incluida
`alembic_version`. Al añadir una migración, revisar ambas expectativas y actualizar
las que cambien en el mismo PR. Estos valores hacen fallar CI si el esquema no
coincide con el esperado.

El job usa `--network host` en el runner Linux `ubuntu-latest` para conectar la
imagen con PostgreSQL. Esa configuración pertenece a CI; la ejecución local usa
la red y el puerto publicados por Compose.

## Configuración del servidor

- Inyectar las variables de `.env.example` desde la configuración privada del
  alojamiento. No incluir secretos en imágenes, argumentos de build o Git.
- Conservar `API_ACCESS_SECRET` entre reinicios y actualizaciones. Rotarlo invalida
  todos los tokens de conversación anteriores.
- Usar la conexión SSL de Supabase. Distinguir el destino de pruebas del destino
  de producción antes de aplicar migraciones.
- Configurar `CORS_ALLOW_ORIGINS` con los orígenes del frontend. CORS no sustituye
  los tokens de conversación ni el limitador de solicitudes.
- Terminar HTTPS en el alojamiento o proxy. Resolver la IP del cliente antes de
  publicar la API: el comando actual usa `--no-proxy-headers` y el limitador toma
  la IP que recibe Uvicorn. El despliegue deberá aceptar cabeceras reenviadas solo
  desde los proxies de confianza identificados para ese alojamiento.
- Mantener el streaming SSE sin buffering y establecer los tiempos de espera del
  proxy para que una generación pueda completarse.
- Definir si `/docs` y `/openapi.json` se expondrán. Actualmente son públicos.

## Migraciones y permisos

Usar la misma imagen de la versión que se va a desplegar para ejecutar
`python -m alembic upgrade head`. Ejecutarlo en una tarea única antes de cambiar
la versión de la API, sin lanzarlo desde cada worker ni desde el `CMD`.
Un fallo de migración debe detener la actualización del servicio.

La migración inicial presupone el esquema `extensions` de Supabase. CI lo crea
en su PostgreSQL desechable y configura `search_path` para incluirlo antes de
aplicar las migraciones. Esto comprueba el esquema de la aplicación; no reproduce
todos los roles ni servicios de Supabase.

Todas las tablas tienen RLS. El backend actual funciona con el propietario de
las tablas, que evita esas restricciones. Si se separan los roles de migración y
ejecución, definir y probar los permisos y políticas necesarios antes del cambio:
no basta con conceder permisos de tabla cuando RLS no permite las operaciones.
No entregar las credenciales de PostgreSQL al frontend.

En un entorno local, los comandos concretos están en la sección
[Docker y Compose del README](../README.md#docker-y-compose). Su ejecución aplica
cambios a la base configurada; no son comprobaciones de solo lectura.

## Actualización de una versión

1. Identificar el commit y la imagen que se desplegarán; conservar la identificación
   de la versión anterior para poder volver a ella.
2. Exigir CI correcto, incluida la construcción y prueba de la imagen. Revisar las
   migraciones y comprobar su compatibilidad con la versión anterior de la API.
3. Verificar que existe un respaldo recuperable de la base antes de modificar su
   esquema, según las capacidades del alojamiento de PostgreSQL.
4. Ejecutar las migraciones una sola vez con la imagen nueva y confirmar su éxito.
5. Actualizar la API y comprobar `/health`, el estado del proceso y sus logs.
6. Ejecutar las comprobaciones funcionales del apartado siguiente. Si fallan,
   detener la publicación y aplicar el procedimiento de recuperación.

## Comprobaciones tras el despliegue

`GET /health` comprueba únicamente que el proceso HTTP responde. No confirma que
las migraciones estén aplicadas, que PostgreSQL esté disponible ni que las claves
de los proveedores sean válidas.

En una conversación de prueba, comprobar:

- Una consulta relevante devuelve respuesta, fuentes, UUID y token. Esta prueba
  consume APIs reales y requiere autorización y credenciales válidas.
- Con el token, la continuación, el historial y una calificación funcionan. Sin
  token o con el token de otra conversación, el acceso devuelve 403.
- El streaming entrega `delta` y termina en `complete` con los IDs del turno
  guardado. Una desconexión durante generación libera el stream.
- El proxy entrega a la API la IP del cliente prevista. Comprobar los límites en
  un entorno de prueba sin agotar el cupo de usuarios reales.

Separar en el registro de validación lo comprobado en CI con datos desechables,
lo probado en Supabase y lo generado con proveedores reales. No registrar tokens
de conversación, cabeceras de autorización, secretos ni texto completo de consultas
en logs operativos.

## Recuperación

Si una versión de la API falla, volver a la imagen anterior solo si es compatible
con el esquema que quedó aplicado. Conservar el mismo secreto de conversación.
No ejecutar `alembic downgrade` automáticamente al revertir una imagen: algunas
reversiones eliminan tablas y datos.

Si el esquema o los datos requieren recuperación, detener las escrituras, evaluar
una migración correctiva o restaurar un respaldo verificado y comprobar su
integridad antes de reabrir el servicio. La restauración y los cambios sobre datos
reales necesitan autorización explícita.

## Conversaciones y retención

Antes de exponer el servicio, el responsable debe definir el plazo de retención,
la información que se dará al ciudadano y quién puede administrar los datos.
No hay borrado automático implementado. El token permite acceder a la conversación
a quien lo posea; el cliente debe conservarlo y evitar incluirlo en URLs o logs.

Las claves foráneas con `RESTRICT` preservan relaciones entre mensajes,
calificaciones, referencias y chunks. Una futura eliminación administrativa debe
respetar esas dependencias y el alcance autorizado. No vaciar documentos o chunks
para actualizar una versión: usar el reemplazo explícito de documentos.

## Pendientes para cerrar despliegue

- Elegir alojamiento, dominio, entorno y mecanismo de publicación de la imagen.
- Configurar los secretos, HTTPS, proxies de confianza y comportamiento SSE allí.
- Implementar CD con migraciones únicas, bloqueo de despliegues simultáneos y
  detención ante errores de migración.
- Definir retención, acceso administrativo, respaldo y recuperación.
- Ejecutar y registrar una validación real en el destino elegido.
