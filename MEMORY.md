# Memory Nass Offer Checker

Fecha de corte: 2026-07-29.

## Objetivo

Construir una app Windows visual para comprobar si las ofertas de marketplaces siguen vivas, usando EANs de catalogos Shoppingfeed o entradas manuales.

La decision comercial se basa en:

- seller esperado;
- precio;
- disponibilidad;
- presencia/no presencia en el marketplace.

## Regla permanente de aislamiento por marketplace

Cuando el usuario pida un cambio para un marketplace concreto, ese cambio debe afectar solo a la gestion de ese marketplace.

Ejemplos:

- un ajuste de Leroy Merlin no debe cambiar Carrefour ni Worten;
- un ajuste de Carrefour no debe tocar warm-up, cache, perfiles o extraccion de Leroy/Worten;
- un ajuste de Worten debe quedarse dentro de la logica propia de Worten.

Antes de editar hay que identificar el limite afectado:

- config del marketplace en `marketplaces.py`;
- clase/metodos del checker correspondiente en `dashboard_leroy.py`;
- controles/estado de UI en `dashboard_leroy_modern.py`;
- cache/feed/perfil bajo `fase1/`.

Solo se debe tocar codigo compartido si el usuario pide un cambio global o si es imprescindible. En ese caso, documentar y verificar el impacto en todos los marketplaces.

## Como ejecutar

Ruta del proyecto:

```text
C:\Users\Usuario\Desktop\IT\ScraperV2
```

Arranque recomendado:

```bat
launch_dashboard.bat
```

Alternativa:

```powershell
python .\dashboard_leroy_modern.py
```

Acceso directo creado en escritorio:

```text
C:\Users\Usuario\Desktop\Nass Offer Checker.lnk
```

## Configuracion local no versionada

Archivo privado:

```text
local_settings.json
```

Contiene:

- URL viva de Shoppingfeed;
- webhook Slack;
- activacion/cooldown de alertas;
- configuracion local por worker.

No imprimir ni commitear este archivo.

Plantilla versionada:

```text
local_settings.example.json
```

## Estado implementado

- Dashboard moderno en `dashboard_leroy_modern.py`.
- Logica de scraping y clasificacion en `dashboard_leroy.py`.
- Configuracion multi-marketplace en `marketplaces.py`.
- Selector inicial `Leroy Merlin` / `Carrefour` / `Worten`.
- Selector incluye `Conforama`.
- Entrada manual por EAN.
- CSV manual.
- Catalogo vivo desde Shoppingfeed por marketplace.
- Cache diferencial SQLite separada por marketplace.
- Saltar productos con stock feed `<= 0`.
- Semaforos:
  - verde: correcto;
  - amarillo: revisar, perdida buybox o no disponible teniendo stock;
  - rojo: fuera, sin stock o no vendido;
  - gris: tecnico/challenge/timeout/incierto.
- Tarjetas de semaforo clicables para filtrar resultados.
- Tabla con columna `Producto` para titulo/modelo extraido del marketplace.
- Subfiltros rojos:
  - `NO_VIVA` / fuera marketplace;
  - `SIN_STOCK_FEED` / sin stock en feed.
- Reintentos por semaforo conservan la tabla y recalculan solo las filas seleccionadas, sin resetear todos los contadores.
- Boton `Reintentar pendientes`; si un EAN relanzado no devuelve resultado al terminar la ejecucion, vuelve a gris `INCIERTA` con motivo tecnico en vez de quedar colgado como pendiente.
- Boton y `Ctrl+C` para copiar EAN seleccionado.
- Chromium minimizado.
- Modo datos minimos para reducir carga de assets.
- Alertas Slack ante senales tecnicas.
- Fase 3 con hasta 10 workers.
- Cola compartida: cada worker toma el siguiente producto pendiente; no se duplican productos entre workers.
- Circuit breaker global por senales tecnicas consecutivas.
- Configuracion local por worker leida y mostrada en UI:
  - `enabled`;
  - proxy configurado si/no;
  - User-Agent propio si/no.
- Resumen agregado de workers en UI.
- Warm-up por worker antes de consumir productos:
  - estado `calentando`;
  - estado `activo` si la home esta sana;
  - estado `bloqueado` si aparece challenge;
  - worker bloqueado no toma productos de la cola.
- Base Carrefour:
  - feed Shoppingfeed propio;
  - cache propia;
  - perfil Edge manual/CDP por worker propio;
  - busqueda batch de hasta 7 EAN por URL `https://www.carrefour.es/?query=EAN1%20EAN2`;
  - navegador Carrefour con mas carga permitida que Leroy: sin rutas ligeras agresivas y con espera extra de carga;
  - extraccion desde busqueda de EAN, precio, seller, URL de ficha y boton de compra;
  - verde si seller esperado coincide y hay boton de compra;
  - amarillo si seller no coincide, seller no se extrae o falta boton de compra;
  - rojo `NO_VIVA` si Carrefour muestra banner de no coincidencia exacta para el EAN y sugiere otro producto.
- Base Conforama:
  - feed Shoppingfeed propio;
  - cache propia;
  - busqueda por referencia interna `MKP...`, no por EAN;
  - mapa local no versionado `fase1/conforama_ean_mkp.xlsx`;
  - columna `EAN` asociada a columna `SKU de producto`;
  - consulta directa al endpoint Empathy `skusearch`;
  - verde si devuelve el `MKP` exacto;
  - rojo `NO_VIVA` si el `MKP` no aparece;
  - gris `INCIERTA` si falta asociacion EAN -> MKP o falla la API.
- Base Worten:
  - feed Shoppingfeed propio;
  - cache propia;
  - perfil Edge manual/CDP por worker propio;
  - `WortenChecker` separado;
  - dominio `https://www.worten.pt/`;
  - seller dedicado `Mark JV shop`, equivalente operativo de `NEWLUX GROUP`;
  - seller_id `e5dae97c-401c-456a-be59-56a4f73b0bb5`;
  - busqueda batch abriendo la pagina del seller solo en warm-up, esperando fichas y encadenando tandas de 10 EANs desde el buscador actual, sin volver al seller entre tandas salvo recuperacion si se pierde el input;
  - extraccion desde tarjetas visibles: `EAN`, titulo, precio, seller y URL; los agrupados de Worten pueden generar varios nodos internos y se conserva esa evidencia;
  - perfil Edge manual/CDP limpio por worker en `fase1/edge_manual_worten_clean_worker_<n>`, sin extensiones ni cuenta;
  - si aparece challenge anti-bot, Edge manual/CDP queda visible, la UI marca `pendiente challenge`, espera resolucion manual y despues intenta aceptar el popup de cookies antes de seguir;
  - el estado de cookies queda cacheado por worker para no repetir el cierre pesado en cada tanda.

## Ultimo avance

El 2026-07-31 se corrigio Carrefour:

- El banner `No hemos encontrado coincidencias para <EAN>` ya invalida las tarjetas sugeridas para otro EAN. Caso validado: `8435544806788` queda rojo `NO_VIVA`, no amarillo por perdida de buybox.
- La perdida de buybox queda reservada para EAN exacto con seller distinto. Caso validado: `8436616280192` queda amarillo `BUYBOX_PERDIDA` con seller `ElectroMGD`.
- Si una busqueda batch devuelve HTML con resultados pero no permite mapear una tarjeta al EAN, Carrefour reintenta esos EANs individualmente antes de devolver gris tecnico.
- El warm-up Carrefour usa Chromium persistente por worker con `--disable-quic`, reintento ante errores de navegacion y cierre aislado del worker que falle, sin parar automaticamente el resto.
- Se anadio `fase1/simulate_carrefour_worker.py` para reproducir ejecuciones visibles, maximizadas o minimizadas, con uno o dos workers y EANs concretos.

Tambien se anadio Conforama. El archivo `offers (3).xlsx` de Descargas se copio localmente como `fase1/conforama_ean_mkp.xlsx` y queda ignorado por Git. Validacion real: EAN `8435544893344` se mapea a `MKP1716081` y Conforama devuelve verde `OK`, precio `119,60 €`, URL `https://www.conforama.es/colchon-viscoelastico-one-15-nalui-mkpv255951-blanco-mkp1716081`.

Se archivo la logica compleja de Worten en `archive/dashboard_leroy_worten_legacy_20260730.py` y se reactivo Worten con el flujo simple validado: seller page solo como warm-up/recuperacion, busquedas encadenadas por input en tandas de 10 EAN y extraccion desde tarjetas visibles. La UI ahora separa rojos por `NO_VIVA` y `SIN_STOCK_FEED`, muestra columna `Producto` y mantiene contadores al reintentar filtros.

Anteriormente se corrigio la confusion visual del texto `Worker 1 activo`, se anadio warm-up por worker y se sento la base Carrefour.

## Handoff 2026-07-30 - Leroy roto en warm-up

Estado actual reportado por el usuario:

- Al lanzar Leroy aparece `challenge en warm-up`.
- No llega a arrancar el worker ni a consumir productos.
- El problema esta antes del checkeo de EANs: en `LeroyChecker.launch_worker_context()` tras abrir `https://www.leroymerlin.es/`.

Diagnostico hecho:

- Las ultimas ejecuciones revisadas (`fase1/dashboard_runs/20260730_160322` y `20260730_160311`) solo contenian `worker_01_warmup_challenge.html`, sin `summary_live.csv`.
- El HTML `fase1/dashboard_runs/20260730_160322/worker_01_warmup_challenge.html` tenia titulo normal de home:

```text
Bricolaje, Decoracion, Jardin y Construccion - Leroy Merlin
```

- Ese HTML parecia home usable, no challenge real. Contenia referencias tecnicas a DataDome/captcha en scripts/CSP, por ejemplo `captcha-delivery.com`, y eso provocaba falso positivo en `challenge_detected()`.
- Se aplico un ajuste local en `dashboard_leroy.py` para que `challenge_detected()`:
  - extraiga texto visible;
  - reconozca senales de home normal de Leroy;
  - no marque challenge solo por referencias tecnicas a `captcha-delivery.com`;
  - siga marcando challenge si la URL es de captcha o hay textos/estructuras visibles de bloqueo.
- Verificacion local sobre el HTML guardado:

```text
challenge_detected= False
```

Pero despues del ajuste el usuario sigue viendo `challenge en warm-up`, por lo que manana hay que confirmar si:

- se esta generando un HTML nuevo distinto al revisado;
- el contenido live contiene `var dd=` real de DataDome y no solo CSP;
- el worker esta usando un perfil/cookie de Leroy bloqueado;
- el modo `minimal_data_mode` esta bloqueando algun recurso necesario para que Leroy complete la validacion.

Siguiente paso recomendado:

1. Lanzar una prueba Leroy con 1 worker y revisar el nuevo directorio `fase1/dashboard_runs/<timestamp>`.
2. Si aparece `worker_01_warmup_challenge.html`, extraer solo:
   - `title`;
   - `page.url`;
   - longitud HTML;
   - conteo de marcadores `datadome`, `captcha`, `var dd=`, `access denied`, `blocked`, `leroy merlin`;
   - primeras lineas de texto visible sin scripts.
3. No tocar Carrefour/Worten.
4. Si vuelve a ser falso positivo, endurecer `challenge_detected()` solo para Leroy.
5. Si es challenge real, revisar perfil `fase1/browser_profile_leroy` y recursos permitidos en `install_lightweight_routes()`.

Ahora la UI mantiene el subtitulo superior para salida/catalogo y muestra un resumen agregado de workers junto a los chips:

```text
2/10 workers activos | Proxy 0/10 | UA 0/10
W1 activo | P:no | UA:def
W2 activo | P:no | UA:def
```

## Fase 3 siguiente

Orden recomendado:

1. Pausa individual durante analisis:
   - si un worker recibe captcha/DataDome/challenge, pausarlo sin cerrar todos inmediatamente.
2. Corte global mas fino:
   - si varios workers fallan o hay racha tecnica, parar lote.
3. Completar precision Carrefour:
   - detectar senales explicitas de sin resultados para reducir grises;
   - detectar disponibilidad sin boton si Carrefour cambia UI;
   - comparar precio Carrefour contra precio feed si se decide usar margen/tolerancia.
4. Aplicar proxy/User-Agent por worker en Playwright:
   - usar solo proxies estables/autorizados;
   - User-Agent persistente por worker;
   - no rotar por request.

## Observaciones de bloqueo

Prueba reciente con varios workers:

- No fue un crash de la app.
- Los workers recibieron respuestas DataDome/challenge.
- El circuit breaker corto el lote tras la racha tecnica.
- Con muchos workers en la misma IP/perfiles nuevos aumenta el riesgo de challenge.

## Git

Remoto:

```text
https://github.com/isma123nassif/NassOfferchecker.git
```

Rama:

```text
main
```

Antes de commitear:

```powershell
git status --short
```

Comprobar que no aparecen:

- `local_settings.json`;
- webhooks reales;
- cookies/storage;
- perfiles Chromium;
- CSVs completos del feed;
- outputs de ejecucion.
