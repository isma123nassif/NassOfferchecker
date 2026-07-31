# Nass Offer Checker

Dashboard Windows/Python para revisar disponibilidad de ofertas en marketplaces a partir de EANs o de feeds vivos de Shoppingfeed.

La app usa navegadores Chromium persistentes mediante Playwright, clasifica cada producto con semaforos comerciales y guarda resultados locales para acelerar ejecuciones posteriores.

## Estado actual

- Marketplaces soportados:
  - `Leroy Merlin`, con clasificacion comercial completa.
  - `Carrefour`, base inicial con feed propio y busqueda batch de hasta 7 EAN.
  - `Worten`, checker separado sobre pagina dedicada de seller.
  - `Conforama`, busqueda por referencia interna `MKP...` usando mapa local EAN -> MKP.
- Entrada manual por EAN.
- Entrada CSV manual.
- Entrada directa desde catalogo vivo de Shoppingfeed.
- Dashboard visual con semaforos.
- Filtros clicables por semaforo.
- Copia rapida de EAN seleccionado.
- Cache diferencial SQLite.
- Navegador ligero con bloqueo de assets pesados.
- Alertas Slack ante senales tecnicas de bloqueo/challenge.

## Instalacion

Requisitos:

- Windows.
- Python 3.11 o superior.
- Navegador Playwright Chromium instalado.

Instalar dependencias:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Arranque

Opcion recomendada en Windows:

```bat
launch_dashboard.bat
```

Alternativa:

```powershell
python .\dashboard_leroy_modern.py
```

## Configuracion privada

Los secretos no se guardan en el repositorio. Usa `local_settings.json`, que esta ignorado por Git.

Ejemplo:

```json
{
  "shoppingfeed_url": "https://export.shopping-feed.com/stream/PRIVATE_LEROY_TOKEN",
  "carrefour_shoppingfeed_url": "https://export.shopping-feed.com/stream/PRIVATE_CARREFOUR_TOKEN",
  "worten_shoppingfeed_url": "https://export.shopping-feed.com/stream/PRIVATE_WORTEN_TOKEN",
  "marketplaces": {
    "leroy": {
      "shoppingfeed_url": "https://export.shopping-feed.com/stream/PRIVATE_LEROY_TOKEN"
    },
    "carrefour": {
      "shoppingfeed_url": "https://export.shopping-feed.com/stream/PRIVATE_CARREFOUR_TOKEN",
      "search_batch_size": 7
    },
    "worten": {
      "shoppingfeed_url": "https://export.shopping-feed.com/stream/PRIVATE_WORTEN_TOKEN",
      "seller_id": "e5dae97c-401c-456a-be59-56a4f73b0bb5",
      "seller_name": "Mark JV shop",
      "search_batch_size": 10
    }
  },
  "slack_webhook_url": "https://hooks.slack.com/services/PRIVATE/WEBHOOK/URL",
  "alerts_enabled": true,
  "alert_cooldown_minutes": 15
}
```

Tambien puedes usar variables de entorno:

```powershell
$env:SHOPPINGFEED_CATALOG_URL = "https://export.shopping-feed.com/stream/..."
$env:CARREFOUR_SHOPPINGFEED_URL = "https://export.shopping-feed.com/stream/..."
$env:WORTEN_SHOPPINGFEED_URL = "https://export.shopping-feed.com/stream/..."
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
$env:ALERTS_ENABLED = "true"
$env:ALERT_COOLDOWN_MINUTES = "15"
```

## Uso

1. Abre el dashboard.
2. Selecciona `Leroy Merlin`, `Carrefour` o `Worten`.
3. Pulsa `Cargar catalogo Shoppingfeed` o introduce EANs manualmente.
4. Ajusta `Seller esperado`, normalmente `NEWLUX GROUP`.
5. Deja activa la cache diferencial salvo que necesites un chequeo completo.
6. Pulsa `Analizar`.

## Formato CSV

Formato principal:

```text
ean;reference;quantity;price
```

Tambien acepta equivalentes:

```text
ean, gtin, barcode
reference, sku, ref
quantity, stock, qty
price, precio
```

## Semaforos

- Verde: oferta correcta, producto disponible y seller esperado coincide si aplica.
- Amarillo: requiere revision, perdida de buybox o no disponible aun teniendo stock feed.
- Rojo: sin stock feed, no encontrado o no vendido en marketplace.
- Gris: fallo tecnico, timeout, challenge, captcha o HTML incompleto.

Las tarjetas superiores son filtros:

- `Correctos`: solo verdes.
- `Revisar`: solo amarillos.
- `Fuera`: solo rojos.
- `Tecnico`: solo grises.
- `Todos`: limpia el filtro.

## Fase 1: cache diferencial

La app evita abrir Chromium cuando puede decidir antes:

- Si el stock del feed es `0` o menor, marca rojo `SIN_STOCK_FEED`.
- Si `EAN + reference + quantity + price + seller esperado` no cambia, reutiliza el ultimo resultado dentro del TTL.
- Resultados `INCIERTA` o tecnicos no se reutilizan desde cache.

Caches locales:

```text
fase1/offer_cache_leroy.sqlite
fase1/offer_cache_carrefour.sqlite
fase1/offer_cache_conforama.sqlite
fase1/offer_cache_worten.sqlite
```

Este archivo no se versiona.

## Fase 2: navegador ligero

Para los productos que si requieren navegador:

- Timeout inicial configurable, por defecto `18` segundos.
- Reintento automatico mas largo.
- `Modo datos minimos`: activado por defecto.
- Bloqueo de recursos pesados: imagenes, media, fuentes, CSS y tracking conocido.
- Bloqueo de dominios externos no esenciales.
- Corte de cargas tardias con `window.stop()` tras una ventana corta de render.
- Chromium se abre minimizado para no molestar al usuario.

La decision comercial solo necesita seller, precio y disponibilidad. Por eso el modo minimo intenta conservar HTML/JSON-LD, JavaScript necesario de Leroy, senales de challenge/DataDome y endpoints propios de Leroy.

Control `Render ms`:

- defecto: `700`;
- bajar si la pagina ya trae los datos en HTML;
- subir a `1000-1500` si aparecen demasiados `INCIERTA` por HTML incompleto.

No se bloquea JavaScript general ni mecanismos de sesion/challenge, para no degradar la precision del diagnostico.

## Fase 3: workers controlados

La fase 3 permite revisar en paralelo con varios navegadores, cada uno con perfil Chromium separado.

Controles:

- `Workers`: numero de navegadores paralelos. Rango permitido: `1` a `10`.
- `Corte tecnico`: numero de senales tecnicas consecutivas antes de parar el lote.

Valores recomendados:

- empezar con `10` para medir capacidad maxima;
- bajar a `7`, `5`, `3` o `1` si aparecen bloqueos o lentitud local;
- mantener `Corte tecnico` entre `3` y `5`.

Si aparecen varios `INCIERTA`, captchas, DataDome, timeouts o errores seguidos, se activa el circuit breaker y se deja de tomar trabajo nuevo.

### Configuracion local por worker

`local_settings.json` puede definir workers concretos. Esta configuracion no se versiona.

```json
{
  "workers": [
    {
      "id": 1,
      "enabled": true,
      "proxy_server": "",
      "proxy_username": "",
      "proxy_password": "",
      "user_agent": ""
    }
  ]
}
```

En la fase 3.1/3.2 la app ya lee esta configuracion y la muestra saneada en UI:

- `P:si/no`: indica si el worker tiene proxy configurado, sin mostrar host ni credenciales.
- `UA:def/custom`: indica si el worker tiene User-Agent propio, sin imprimirlo.
- `enabled=false`: el worker aparece como desactivado y no se lanza.

La aplicacion de proxy/User-Agent dentro de Playwright se deja para la siguiente fase, tras validar que la visibilidad y el estado por worker funcionan correctamente.

### Estado actual de la fase 3

La cola de trabajo es compartida: cada worker toma el siguiente producto pendiente y no repite productos ya tomados por otros workers.

La UI muestra un resumen agregado de workers y, debajo, el estado individual de cada uno:

```text
2/10 workers activos | Proxy 0/10 | UA 0/10
W1 activo | P:no | UA:def
W2 activo | P:no | UA:def
```

Antes de consumir productos, cada worker hace un warm-up abriendo la home. Si aparece challenge, se marca como `bloqueado`, se envia alerta tecnica si esta configurada y ese worker no toma productos de la cola.

Pendiente recomendado antes de avanzar:

- pausar workers individualmente cuando reciban challenge durante el analisis;
- afinar el corte global cuando fallen varios workers;
- aplicar proxy/User-Agent persistente por worker en Playwright.

## Carrefour

Carrefour usa un flujo de busqueda batch: hasta 7 EAN por navegacion, pegados separados por espacios en la query.

Ejemplo:

```text
https://www.carrefour.es/?query=8435544806788%208435544888012%208435544894204
```

En esta base inicial:

- el feed Carrefour se configura separado del feed Leroy;
- la cache Carrefour se guarda separada;
- los perfiles Chromium Carrefour se guardan separados;
- Carrefour no usa el modo minimo agresivo de Leroy: deja cargar JS/XHR/CSS/recursos necesarios y espera mas antes de leer el HTML;
- desde la busqueda Carrefour se extraen EAN, precio, seller, URL de ficha y boton de compra;
- si seller esperado coincide y hay boton de compra, se marca verde `Correcto`;
- si seller no coincide o falta boton de compra, se marca amarillo;
- si Carrefour muestra el banner `No hemos encontrado coincidencias para <EAN>` y propone productos para otro EAN, se marca rojo `NO_VIVA` aunque haya una tarjeta visible;
- si una busqueda batch devuelve resultados pero no se puede mapear una tarjeta al EAN pedido, Carrefour reintenta ese EAN de forma individual antes de dejarlo como tecnico.

Ejemplos validados:

- `8435544806788`: Carrefour muestra una sugerencia para otro EAN, por tanto queda rojo `NO_VIVA`.
- `8436616280192`: Carrefour encuentra el EAN exacto con seller `ElectroMGD`, por tanto queda amarillo `BUYBOX_PERDIDA` si el seller esperado es `NEWLUX GROUP`.

Diagnostico local:

```powershell
python .\fase1\simulate_carrefour_worker.py --ean 8435544806788 --ean 8436616280192 --max-batches 1 --workers 1 --hold-seconds 5 --window-state minimized
```

## Conforama

Conforama no localiza los productos por EAN en la busqueda publica. Para este marketplace la app usa el archivo local:

```text
fase1/conforama_ean_mkp.xlsx
```

Ese Excel no se versiona. Debe contener una columna `EAN` y una columna `SKU de producto` con referencias `MKP...`.

Flujo:

- antes de buscar, el checker convierte cada EAN a su referencia `MKP...`;
- al cargar catalogo, Conforama usa el mismo feed Shoppingfeed configurado para Leroy Merlin, salvo que se defina una URL propia `CONFORAMA_SHOPPINGFEED_URL` o `marketplaces.conforama.shoppingfeed_url`;
- la URL visual equivalente es `https://www.conforama.es/?query=MKP1716081`;
- la comprobacion real usa el endpoint `skusearch` de Conforama/Empathy para confirmar que vuelve el `MKP` exacto;
- verde `OK`: el `MKP` exacto aparece visible en Conforama;
- rojo `NO_VIVA`: el `MKP` no aparece en Conforama;
- gris `INCIERTA`: falta la relacion EAN -> MKP o falla la API.

## Worten

Worten usa la pagina dedicada del seller `Mark JV shop`, equivalente operativo de `NEWLUX GROUP`:

```text
https://www.worten.pt/search?query=*&facetFilters=seller_id:e5dae97c-401c-456a-be59-56a4f73b0bb5&utm_source=sellerpage_redirect
```

Worten no depende de URL directa para multi-EAN: abre la pagina del seller en el warm-up, espera la carga real de fichas, pega tandas de 10 EANs separados por espacios reales en la lupa y encadena una busqueda tras otra desde el buscador actual. Solo vuelve a la pagina del seller si pierde el cuadro de busqueda y necesita recuperarse. Tras buscar, espera a que la URL ya contenga los EAN solicitados y extrae desde las tarjetas visibles `EAN`, titulo, precio, seller y URL. Los productos agrupados pueden renderizar varios nodos internos; se conserva esa evidencia y la clasificacion se mapea por `mrkean-<EAN>`. Si aparece un challenge anti-bot visible, la ventana se maximiza para resolucion manual y luego continua con la misma sesion. Si aparece el aviso de cookies tras el challenge, la app intenta aceptarlo y cachea ese estado por worker para no repetir el cierre pesado en cada tanda.

## UI de Resultados

La tabla muestra una columna `Producto` con el titulo/modelo extraido del marketplace cuando esta disponible.

El semaforo rojo se mantiene como categoria comercial `Fuera`, pero al filtrar rojo aparecen subfiltros:

- `Fuera marketplace`: productos que no se encuentran o no se venden en el marketplace.
- `Sin stock feed`: productos saltados porque el feed indica stock `<= 0`.

Al usar `Reintentar` desde un semaforo, la UI conserva el resto de resultados y solo recalcula los EAN del filtro seleccionado, evitando resetear todos los contadores.

La barra de resultados incluye `Reintentar pendientes`. Si una ejecucion o reintento termina sin devolver resultado para algun EAN, la app lo devuelve automaticamente a gris `INCIERTA` con motivo tecnico, en vez de dejarlo colgado como pendiente sin estado.

## Alertas Slack

La app puede enviar una alerta a Slack cuando detecta senales tecnicas:

- `INCIERTA`.
- captcha/reCAPTCHA/hCaptcha.
- DataDome/challenge.
- `access denied`.
- timeout o error de navegacion.

El cooldown por defecto es de `15` minutos para evitar spam.

## Salidas locales

Cada ejecucion crea:

```text
fase1/dashboard_runs/<timestamp>/summary_live.csv
```

El HTML solo se guarda en casos no verdes para reducir espacio.

## Seguridad Git

El repositorio ignora:

- `local_settings.json`
- perfiles Chromium;
- perfiles Edge manual/CDP de Worten;
- cookies/storage;
- caches SQLite;
- CSVs completos de Shoppingfeed;
- outputs, HTML, imagenes y logs;
- `__pycache__`.

Antes de publicar se debe comprobar que no aparecen URLs privadas ni webhooks reales en archivos versionados.

## Documentacion adicional

- `DASHBOARD_README.md`: guia de uso del dashboard.
- `MEMORY.md`: memoria operativa para retomar el proyecto.
- `fase1/*.md`: analisis, decisiones tecnicas y resultados de pruebas previas.
- `fase1/run_playwright_bootstrap.py`: runner Playwright de fase 1.
- `fase1/run_local_poc.py`: prueba HTTP local.
- `fase1/run_apify_poc.py`: prueba Apify historica, mantenida como referencia.
