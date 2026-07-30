# Memory Nass Offer Checker

Fecha de corte: 2026-07-29.

## Objetivo

Construir una app Windows visual para comprobar si las ofertas de marketplaces siguen vivas, usando EANs de catalogos Shoppingfeed o entradas manuales.

La decision comercial se basa en:

- seller esperado;
- precio;
- disponibilidad;
- presencia/no presencia en el marketplace.

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
  - amarillo si seller no coincide, seller no se extrae o falta boton de compra.
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

Se archivo la logica compleja de Worten en `archive/dashboard_leroy_worten_legacy_20260730.py` y se reactivo Worten con el flujo simple validado: seller page solo como warm-up/recuperacion, busquedas encadenadas por input en tandas de 10 EAN y extraccion desde tarjetas visibles. La UI ahora separa rojos por `NO_VIVA` y `SIN_STOCK_FEED`, muestra columna `Producto` y mantiene contadores al reintentar filtros.

Anteriormente se corrigio la confusion visual del texto `Worker 1 activo`, se anadio warm-up por worker y se sento la base Carrefour.

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
