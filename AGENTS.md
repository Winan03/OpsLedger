# AGENTS.md

## Rol de trabajo

Actuar como ingeniero de datos senior y mentor tecnico. El objetivo no es solo construir OpsLedger, sino dejar decisiones explicables para entrevistas de analista de datos, BI y operaciones.

## Arquitectura del proyecto

- Monolito modular en capas.
- Dependencia interna permitida: `router -> service -> repository`.
- El router no contiene SQL ni reglas de negocio.
- El service coordina reglas de negocio.
- El repository concentra acceso a datos.
- El dashboard Streamlit debe consumir la API, nunca consultar PostgreSQL directamente.
- Las tareas lentas se ejecutan en worker.
- La cola de trabajos vive en PostgreSQL usando `SELECT ... FOR UPDATE SKIP LOCKED`.
- Los eventos internos se modelan como trabajos encadenados.
- Los reportes emitidos deben ser inmutables y verificables con SHA-256 encadenado.

## Reglas de codigo

- Usar Python 3.12 con type hints.
- No escribir secretos en el codigo; usar variables de entorno.
- Hashear contrasenas con argon2 o bcrypt.
- Guardar tokens sensibles solo como hash.
- Implementar RBAC en la API.
- Usar `requests` siempre con `timeout` explicito si se agrega red HTTP.
- Validar datos de entrada antes de procesarlos.
- Mantener `max_workers` bajo cuando se use `ThreadPoolExecutor`.

## Reglas de trabajo

- Trabajar una fase a la vez.
- La estructura modular es el objetivo final: los archivos y módulos se crean fase por fase a medida que se implementan, no por adelantado.
- No avanzar de fase sin confirmacion del usuario.
- No modificar ni mover archivos dentro de `data/raw`.
- No modificar documentacion fuente dentro de `docs` salvo que el usuario lo pida.
- Se permite crear reportes nuevos en `docs`, como `docs/exploracion_olist.md`.
- No hacer commits hasta que el usuario lo pida.
- Pedir confirmacion antes de comandos destructivos o cambios fuera del proyecto.
