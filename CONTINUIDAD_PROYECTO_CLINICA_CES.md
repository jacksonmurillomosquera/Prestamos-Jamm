# Continuidad del proyecto — Préstamos de controles de TV Clínica CES

Fecha de inspección: 25 de octubre de 2026 (America/Bogota).

## Propósito

Aplicación interna para buscar pacientes hospitalizados, asignarles un control remoto de TV, gestionar devoluciones y traslados, y consultar el inventario de la Clínica CES. Este documento resume el estado observado en el espacio de trabajo para facilitar que otro agente continúe sin depender de conversaciones previas.

## Arquitectura y tecnologías

- Aplicación web Flask en Python (`app.py`), con plantillas Jinja/HTML, JavaScript y CSS.
- SQLite es la persistencia local para catálogo de ubicaciones, controles, préstamos y traslados. La ruta predeterminada es `prestamos_ces.sqlite3` en la raíz; `PRESTAMOS_DB_PATH` puede cambiarla.
- Oracle (`oracledb`) se usa para autenticación de Historia Clínica y consultas del censo de pacientes. `pyodbc` y SQL Server aparecen como integración opcional del catálogo/inventario.
- Las dependencias declaradas están en `requirements.txt`; configuración sensible se carga desde variables de entorno/`.env` mediante `python-dotenv`.
- El servidor de desarrollo arranca en `127.0.0.1`, puerto 5001 predeterminado (variable `PORT`). `debug=False`.

## Estructura principal

- `app.py`: rutas Flask, operaciones del inventario y préstamos, cálculo de tarifas e inicialización SQLite.
- `services/paciente_service.py`, `oracle_db.py`, `config.py`: acceso a Oracle y consultas de pacientes.
- `catalogo_controles.py`: catálogo de ubicaciones, camas y marcas requeridas.
- `seed_controles.py`: preparación del catálogo de ubicaciones en SQLite/SQL Server; no se ejecutó durante esta revisión.
- `dashboard_base.html`, `dashboard_inicio.html`, `buscar.html`, `historial.html`, `traslado.html`, `nuevo_prestamo.html`, `reportes.html`, `excedentes.html`: vistas principales.
- `dashboard_modular.js`, `dashboard.js`: lógica de interfaz. La aplicación actual carga `dashboard_modular.js` desde la plantilla base.
- `css/estilos.css`, `img/`: presentación, marca e imágenes del login/Pingüi.
- `database.sql`, `sqlserver_habitacion_control.sql`, `oracle_schema.sql`: esquemas y scripts SQL para distintos motores.
- `test_prestamos_workflow.py`: pruebas automatizadas del flujo con SQLite temporal; no se ejecutaron.

## Ejecución local (sin revelar secretos)

1. Usar un entorno virtual compatible con la versión de Python y las dependencias declaradas.
2. Instalar `requirements.txt`.
3. Configurar las variables requeridas para Oracle en el entorno o en un `.env` privado, sin copiarlo a respaldos compartidos.
4. Ejecutar `python app.py`; el servidor local usa el puerto 5001 por defecto.

No se verificó la instalación de dependencias de cada entorno virtual ni la conexión real a Oracle/SQL Server. Importar `app.py` ejecuta `ensure_local_inventory()` y sincroniza préstamos; por ello no se inició la app durante esta inspección.

## Persistencia y estado observado de datos

La base activa predeterminada es `prestamos_ces.sqlite3` en la raíz. El espacio de trabajo está bajo una carpeta de OneDrive, así que el archivo SQLite también queda bajo esa ubicación sincronizada; revisar el mecanismo institucional de sincronización/retención antes de usarlo con datos reales. Se consultó en modo de solo lectura, sin mostrar nombres, documentos ni filas personales. Al momento de la inspección los agregados fueron: 159 controles activos, 159 disponibles, 0 prestados, 0 pendientes de devolución; 29 préstamos en estado `DEVUELTO` y 5 traslados. Por tanto, hay historial persistido aunque no haya préstamos actualmente activos.

En el primer inicio, `ensure_local_inventory()` crea el esquema, aplica cambios aditivos, persiste ubicaciones y si la tabla de controles está vacía inserta 159 controles con códigos/seriales sintéticos `CTRL-*`/`SER-*` y marcas cíclicas. Esto no acredita que sean los códigos, seriales o marcas del inventario físico oficial. `seed_controles.py` crea/actualiza ubicaciones; su reporte indica que no crea ni modifica controles físicos. Evitar ejecutar inicializadores o scripts de seed sin revisar su efecto y respaldo de datos.

## Estado funcional y evidencia

Clasificación basada en inspección estática y, donde se indica, conteos agregados de SQLite. No equivale a validación integral del comportamiento en navegador ni a prueba de los sistemas externos.

| Funcionalidad | Estado | Evidencia y límites |
|---|---|---|
| Inicio de sesión | Parcial | `POST /login_hc` valida contra Oracle y establece sesión. Depende de credenciales y conectividad Oracle, no verificadas. También hay rutas de registro/recuperación de prueba en memoria; no son persistencia institucional. Se detectaron credenciales de demostración codificadas en fuente/SQL: no se reproducen aquí; deben retirarse o rotarse antes de compartir/publicar el código. |
| Navegación | Implementada, pendiente de pruebas | Rutas Flask y enlaces a inicio, búsqueda, traslados, historial, excedentes y reportes. Acceso visual no se recorrió en navegador. |
| Dashboard e indicadores | Implementada, pendiente de pruebas | `/api/dashboard/resumen` cuenta por estados en SQLite; la plantilla muestra disponibles, en uso y pendientes. El API y base inspeccionados concuerdan en 159/159/0/0 en esta revisión. No se verificó refresco visual en navegador. |
| Búsqueda por identificación | Implementada, pendiente de pruebas | Consulta Oracle, valida sesión, fija el paciente validado en sesión y retorna información al flujo. Oracle no fue probado. La consulta de identificación limita el resultado a una fila. |
| Búsqueda por habitación/cama | Parcial | Hay consulta de habitación que devuelve candidatos y el dashboard contempla selección cuando hay varios pacientes. La consulta por cama devuelve como máximo un candidato; no se verificó que todos los formatos de cama compartida queden cubiertos. Censo y flujo real no se probaron. |
| Modal “Paciente encontrado” y selección | Implementada, pendiente de pruebas | El modal y lista de resultados existen en `dashboard_inicio.html`/`dashboard_modular.js`. No se validó en navegador ni con datos reales. |
| Formulario “Nuevo préstamo” y ubicación exacta | Parcial | Flujo principal abre el modal del dashboard; valida ubicación/cama, paciente y control, y filtra por marca requerida. `nuevo_prestamo.html` también existe como vista heredada; `/nuevo-prestamo` redirige al dashboard. La asignación visual de un equipo físico real por ubicación aún no está demostrada. |
| Catálogo físico oficial de 159 controles | Parcial / discrepancia crítica | El código incluye 159 registros sintéticos cuando el inventario está vacío, pero el catálogo de ubicaciones tiene 182 entradas (conteo estático de `CATALOGO_POR_SERVICIO`). No se acreditó el listado físico oficial, códigos/seriales reales ni correspondencia de cada equipo a habitación/cama/marca. La distribución cíclica de marcas no representa una comprobación del catálogo. |
| Disponibilidad y doble asignación | Implementada, pendiente de pruebas | La entrega reserva en transacción SQLite solo si está `DISPONIBLE`; hay índice único parcial para préstamo activo por control. Inspección de lógica, no prueba ejecutada en esta sesión. |
| Persistencia de préstamo/devolución | Implementada; evidencia parcial | Préstamo y devolución escriben en SQLite; devolución cambia control a `DISPONIBLE` y registra fecha/valor/recibidor. La base real contiene 29 préstamos devueltos y no tiene préstamos activos; se leyeron solo agregados. Persistencia histórica observada, sin simular transacción en esta revisión. |
| Cobro de $3.000 por cada 12 horas | Parcial / discrepancia crítica | `PRECIO_DIARIO=3000`, pero `calcular_total()` usa `ceil(horas / 24)`, es decir, bloques iniciados de 24 horas, con mínimo de $3.000. La ruta de consulta también estima días con `/24`. El archivo de pruebas contiene expectativas compatibles con bloques de 24 h, no con 12 h. No cambiar sin autorización; confirmar regla de negocio antes de implementar. |
| Traslados, devolución previa y nuevo control | Parcial / discrepancia | El endpoint registra los traslados y estados. El código y un caso de prueba existente permiten dejar el control anterior pendiente y asignar otro si se proporciona un nuevo control; esto no cumple la interpretación estricta de “devolver el anterior antes de habilitar el siguiente”. Casos no ejecutados en esta revisión. |
| Historial | Parcial | `/api/prestamos` retorna todos los préstamos y calcula valor provisional; la interfaz actual filtra los activos y pagina a 10 por página. La base observada tiene 29 devueltos y 0 activos, por lo que la vista aparece vacía según la modificación reciente, aunque permanece historial persistido. El filtrado oculta el historial devuelto en la UI. |
| Reportes | Pendiente | `reportes.html` contiene métricas fijas de demostración y un texto de “Próximamente”; no está conectado a datos reales. |
| Excedentes de habitación | Parcial | Se muestran rangos y tarifas estáticas en `app.py`/`excedentes.html`. No se confirmó vigencia de tarifas ni cálculo dinámico/conciliación con cobros. |
| SQLite | Implementada, evidencia de lectura | La base predeterminada existe, contiene las tablas de inventario/préstamos/traslados y se leyó en modo readonly. Las operaciones habituales escriben allí. La inicialización al importar app realiza cambios; no se ejecutó. |
| SQL Server | Bloqueada / no verificada | Hay cadena de conexión opcional, servicio de catálogo y scripts SQL. No se comprobó conectividad, estructura desplegada ni cuál servidor sería fuente autorizada frente a SQLite. |
| Oracle | Bloqueada / no verificada | Hay autenticación y consultas del censo. Faltan verificación de conectividad y validación con el esquema/datos reales. No exponer credenciales. |
| Diseño visual, Arial, marca y Pingüi | Parcial | `css/estilos.css` declara Arial/Helvetica; hay logo e imágenes Pingüi en `img/` y referencias desde login. No se hizo revisión visual de todas las pantallas. Hay texto con mojibake visible en varias salidas de archivos y CSS no se pudo leer como UTF-8 estricto; revisar la codificación antes de editar masivamente. No se verificó ausencia de scroll en todas las resoluciones. |

## Requisitos de negocio que deben conservarse y correspondencia

- **159 controles físicos oficiales:** requisito vigente; el sistema solo garantiza una carga inicial numérica de 159 sintéticos. Pendiente de sustituir/verificar con inventario físico oficial.
- **Estado inicial: todos en oficina de préstamos, sin préstamos:** la base leída muestra 159 disponibles, cero prestados y cero pendientes; no se identificó un atributo de ubicación “oficina” por control, por lo que esa parte no está demostrada.
- **Control asociado a habitación/cama y marca oficial:** existe catálogo ubicación→marca requerida, pero contiene 182 ubicaciones y no demuestra asignación individual del control real a cada ubicación. Discrepancia abierta.
- **Habitaciones compartidas con varias camas/pacientes:** hay flujo de búsqueda de habitación y selección. Requiere prueba integrada con censo Oracle.
- **Búsqueda por cama abre directamente “Paciente encontrado” con camas, identidad y ubicación exacta:** componentes existen; comportamiento integral, datos y tipo de identificación visibles requieren validación de aceptación.
- **Formulario debe reflejar paciente y control de ubicación seleccionada:** parte del flujo existe y el backend exige marca/ubicación compatibles; correspondencia con hardware físico real pendiente.
- **No asignar un control prestado a otro paciente:** controles de estado, transacción e índice parcial presentes; requiere pruebas de concurrencia.
- **Traslado: devolver control anterior antes de habilitar siguiente:** el comportamiento de permitir nuevo control mientras el anterior queda pendiente contradice este requisito. No se corrigió.
- **Dashboard con indicadores acordados:** presente para total/disponibles/en uso/pendientes; cifras verificadas solo por consulta readonly de la base en este momento.
- **Identidad Clínica CES, Arial, textos y diseños aprobados:** logos/imágenes y Arial presentes; inspección visual pendiente y codificación/textos requieren revisión.
- **Cobro $3.000 cada 12 horas:** requisito explícito no coincide con implementación por 24 horas. No se modificó.
- **Persistencia real:** préstamos, devoluciones y traslados están respaldados por SQLite. Hay evidencia de 29 préstamos devueltos y 5 traslados en la base actual, no se imprimieron datos personales.

## Cambios, archivos y guardado

- No hay repositorio Git detectable: el comando `git status` respondió que la carpeta no es repositorio; no existe estado de rama, remotos, commits ni comparación confiable con una versión anterior. Por eso no puede hacerse un inventario exhaustivo de cambios pendientes o eliminados frente a un baseline.
- Cambios de fuente identificados en esta colaboración antes de este informe: `dashboard_base.html`, `dashboard_modular.js`, `historial.html` y `css/estilos.css` (ajustes de navegación, tabla/paginación, modal de devolución, filtrado de préstamos activos y estilos del historial). No se descartaron ni sobrescribieron intencionalmente archivos.
- Nuevo archivo creado para continuidad: `CONTINUIDAD_PROYECTO_CLINICA_CES.md`.
- No se detectaron eliminaciones en las operaciones de esta revisión. Sin Git no es posible determinar eliminaciones o cambios anteriores no documentados.
- El entorno de herramientas no expone buffers abiertos del editor; no puedo afirmar si existen cambios sin guardar en VS Code u otro editor. Guardar manualmente cualquier pestaña marcada como modificada antes de cambiar de cuenta.

## Pruebas ejecutadas y resultados

- No se ejecutaron pruebas automatizadas ni se inició Flask. Evité importar/iniciar la aplicación y correr `test_prestamos_workflow.py` porque la inicialización de `app.py` puede escribir/migrar la base local real. Las pruebas existentes usan SQLite temporal una vez iniciadas, pero el módulo importa la app antes de sustituir la ruta; no se consideró seguro sin revisar/aislar más el setup.
- Inspección estática de rutas, lógica, plantillas, JS, SQL y dependencias: realizada.
- Conteo estático del catálogo Python: 182 ubicaciones.
- Lectura SQLite de solo lectura: 159 controles disponibles, 0 prestados, 0 pendientes; 29 préstamos devueltos y 5 traslados. No se consultaron campos de pacientes.
- No se verificaron Oracle, SQL Server, navegación en navegador, adaptación responsive ni equipo físico.

## Riesgos, archivos a excluir y respaldo

No existe Git configurado en esta carpeta, así que no hay historial ni remoto que permita restaurar el estado. No se hizo commit, push, cambio de rama ni publicación. No se creó un respaldo adicional; antes de respaldar, crear una copia local nueva con fecha y sin sobrescribir otra copia, previa autorización operativa si el almacenamiento incluye datos clínicos.

**Excluir de respaldos compartidos/subidas:** `.env`, bases SQLite (`*.sqlite3`, `*.db`, incluida `prestamos_ces.sqlite3`), entornos `.venv/`, `.venv-flask/`, `venv/`, cachés `__pycache__/`, archivos `*.pyc`, logs `flask*.log` y cualquier exportación con información de pacientes. Mantener la base activa fuera de sincronizaciones o respaldos no cifrados. `.env.example` puede compartirse solo tras comprobar que no contiene valores reales.

Riesgos detectados:

1. Credenciales de demostración escritas en `app.py` y sentencias semilla de `database.sql`; no se copian aquí. Antes de cambiar de cuenta o compartir repositorio, rotar/eliminar esos secretos y revisar todo el árbol por claves.
2. Códigos/seriales sintéticos y catálogo de 182 ubicaciones no verifican el inventario oficial de 159 ni su correspondencia física.
3. Regla de cobro codificada para 24 horas contradice el requisito de 12 horas.
4. Traslados permiten caso de nuevo control con el anterior pendiente, contrario al requisito de devolución previa.
5. Reportes muestran datos fijos de prueba; no usarlos como cifras operativas.
6. Oracle/SQL Server dependen de configuración y red institucional; no probados.
7. Sin Git no hay historial de cambios ni reversión sencilla; backups deberán excluir secretos y datos personales.
8. Archivos con caracteres mojibake/codificaciones distintas pueden corromperse al editar con herramientas que asumen UTF-8.

## Próximas tareas recomendadas (prioridad)

1. Proteger el estado de datos y asegurar que existe un respaldo institucional cifrado y autorizado; no copiar la SQLite con datos clínicos a un medio compartido.
2. Eliminar/rotar credenciales de demostración y auditar secretos antes de compartir el proyecto con otra cuenta.
3. Confirmar con el responsable de negocio el catálogo físico oficial de 159, códigos/seriales, ubicación de bodega y mapeo cama/marca; conciliar las 182 ubicaciones.
4. Resolver, con autorización, la discrepancia de cobro 12 h vs. implementación 24 h y actualizar pruebas/ayuda solo después de decisión aprobada.
5. Acordar y hacer cumplir la política de traslados: bloqueo del siguiente control hasta devolución física, o registrar formalmente una excepción si negocio la permite.
6. Definir si la página “Historial” debe listar solo préstamos activos o también préstamos devueltos; la vista ahora filtra activos aunque la API entrega todo el historial.
7. Reemplazar reportes de demostración por métricas de base de datos.
8. Probar login/búsquedas/modal/préstamo/devolución/traslado contra un entorno de QA aislado y Oracle/SQL Server accesibles; añadir pruebas de concurrencia y persistencia sin tocar la base productiva.
9. Revisar textos, codificación UTF-8 y diseño responsive en navegador; aclarar la fuente maestra entre SQLite y SQL Server.
10. Inicializar Git local con `.gitignore` revisado y sin bases, secretos, logs ni entornos; crear commits solo con autorización del propietario.
