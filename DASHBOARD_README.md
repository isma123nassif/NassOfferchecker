# Dashboard Leroy Offer Watcher

## Arranque

Windows:

```bat
launch_dashboard.bat
```

Alternativa:

```powershell
python .\dashboard_leroy_modern.py
```

## Uso

1. Selecciona marketplace: `Leroy Merlin`, `Carrefour` o `Worten`.
2. Pulsa `Cargar catalogo Shoppingfeed` para recuperar el feed vivo del marketplace elegido.
3. Alternativas: introduce un EAN manual o carga un CSV manual.
4. Opcional: ajusta `Seller esperado`, por defecto `NEWLUX GROUP`.
5. Pulsa `Analizar`.

## Filtros visuales

Las tarjetas de semaforo son clicables:

- `Correctos`: muestra solo verdes.
- `Revisar`: muestra solo amarillos.
- `Fuera`: muestra solo rojos.
- `Tecnico`: muestra solo grises.

Pulsa la misma tarjeta otra vez o el boton `Todos` para quitar el filtro.

## Fase 1: aceleracion diferencial

La app evita abrir Chromium cuando puede resolver el producto antes:

- `Stock` del feed menor o igual a cero: se marca rojo `Sin stock feed`.
- `Cache diferencial` activada: si `EAN`, `reference`, `quantity`, `price` y `Seller esperado` no han cambiado y el resultado no ha vencido, reutiliza el ultimo resultado.
- Resultados `INCIERTA` o tecnicos no se reutilizan desde cache.

Configuracion visual:

- `Cache diferencial`: activada por defecto.
- `TTL cache horas`: por defecto `24`.

Las caches locales se guardan por marketplace:

```text
fase1/offer_cache_leroy.sqlite
fase1/offer_cache_carrefour.sqlite
fase1/offer_cache_conforama.sqlite
fase1/offer_cache_worten.sqlite
```

Este archivo no se versiona.

## Fase 2: navegador ligero

La app reduce el coste de cada producto que si necesita Chromium:

- `Timeout navegador`: por defecto `18` segundos en el primer intento.
- Reintento automatico mas largo si la primera navegacion falla.
- `Modo datos minimos`: activado por defecto.
- `Render ms`: espera corta antes de cortar cargas tardias, por defecto `700`.

Se bloquean recursos no necesarios para la decision comercial:

- imagenes;
- video/media;
- fuentes;
- CSS;
- analitica/tracking conocido.

Tambien se bloquean dominios externos no esenciales. Se conserva JavaScript general y componentes de sesion/challenge.

Sube `Render ms` a `1000-1500` si ves muchos `INCIERTA` por HTML incompleto.

## Fase 3: workers controlados

Controles junto a la barra de progreso:

- `Workers`: navegadores paralelos, limitado de `1` a `10`.
- `Corte tecnico`: numero de senales tecnicas consecutivas antes de parar el lote.

Cada worker usa un perfil Chromium separado:

```text
fase1/browser_profile_leroy_worker_<n>
fase1/browser_profile_carrefour_worker_<n>
fase1/browser_profile_worten_worker_<n>
```

Estos perfiles no se versionan.

Recomendacion operativa:

- empezar en `10` para medir capacidad maxima;
- bajar a `7`, `5`, `3` o `1` si aparecen bloqueos o lentitud local;
- mantener el corte tecnico en `3-5`.

## Fase 3.1/3.2: configuracion y visibilidad de workers

El archivo local `local_settings.json` puede incluir:

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

La UI muestra chips por worker:

- `activo`;
- `cerrado`;
- `desactivado`;
- `pausado`;
- `P:si/no` para proxy configurado;
- `UA:def/custom` para User-Agent configurado.

No se muestran credenciales ni URLs de proxy.

La UI muestra un resumen agregado de workers y, debajo, los chips individuales:

```text
2/10 workers activos | Proxy 0/10 | UA 0/10
W1 activo | P:no | UA:def
W2 activo | P:no | UA:def
```

Estados principales:

- `calentando`: el worker esta abriendo la home antes de trabajar.
- `activo`: warm-up sano, puede consumir productos.
- `bloqueado`: challenge detectado en warm-up, no consume cola.

Pendiente de mejora:

- pausar solo el worker que reciba challenge durante el analisis;
- afinar el corte global cuando fallen varios workers;
- aplicar proxy/User-Agent persistente por worker en Playwright.

## Alertas Slack

Canal recomendado: Slack Incoming Webhook.

Configuracion:

```json
{
  "slack_webhook_url": "https://hooks.slack.com/services/...",
  "alerts_enabled": true,
  "alert_cooldown_minutes": 15
}
```

Tambien puedes usar variables de entorno:

```powershell
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
$env:ALERTS_ENABLED = "true"
$env:ALERT_COOLDOWN_MINUTES = "15"
```

La alerta se envia cuando aparece una senal tecnica como:

- `INCIERTA`;
- challenge/captcha/reCAPTCHA/hCaptcha;
- DataDome;
- `access denied`;
- bloqueo o timeout de navegacion.

El webhook es secreto y debe quedarse en `local_settings.json` o variables de entorno. No se versiona.

## Shoppingfeed vivo

La URL privada del catalogo no se guarda en codigo. Configurala de una de estas formas:

```powershell
$env:SHOPPINGFEED_CATALOG_URL = "https://export.shopping-feed.com/stream/..."
$env:CARREFOUR_SHOPPINGFEED_URL = "https://export.shopping-feed.com/stream/..."
$env:CONFORAMA_SHOPPINGFEED_URL = "https://export.shopping-feed.com/stream/..."
$env:WORTEN_SHOPPINGFEED_URL = "https://export.shopping-feed.com/stream/..."
```

O crea un archivo local no versionado:

```text
local_settings.json
```

Con este formato:

```json
{
  "marketplaces": {
    "leroy": {
      "shoppingfeed_url": "https://export.shopping-feed.com/stream/..."
    },
    "carrefour": {
      "shoppingfeed_url": "https://export.shopping-feed.com/stream/..."
    },
    "conforama": {
      "shoppingfeed_url": "https://export.shopping-feed.com/stream/..."
    },
    "worten": {
      "shoppingfeed_url": "https://export.shopping-feed.com/stream/...",
      "seller_id": "e5dae97c-401c-456a-be59-56a4f73b0bb5",
      "seller_name": "Mark JV shop",
      "search_batch_size": 10
    }
  }
}
```

La app descarga el feed y lo cachea localmente en:

```text
fase1/shoppingfeed_leroy_latest.csv
fase1/shoppingfeed_carrefour_latest.csv
fase1/shoppingfeed_conforama_latest.csv
fase1/shoppingfeed_worten_latest.csv
```

## Worten

`WortenChecker` usa la pagina dedicada del seller `Mark JV shop`, equivalente operativo de `NEWLUX GROUP`.

URL base:

```text
https://www.worten.pt/search?query=*&facetFilters=seller_id:e5dae97c-401c-456a-be59-56a4f73b0bb5&utm_source=sellerpage_redirect
```

Worten abre la pagina del seller en el warm-up, espera la carga real de fichas, pega tandas de 10 EANs separados por espacios reales en la lupa y encadena una busqueda tras otra desde el buscador actual. Solo vuelve a la pagina del seller si pierde el cuadro de busqueda y necesita recuperarse. Tras buscar, espera a que la URL ya contenga los EAN solicitados y extrae desde las tarjetas visibles `EAN`, titulo, precio, seller y URL. Si hay tarjeta con seller/precio, se marca verde; si no hay resultado claro, se marca rojo o gris segun la evidencia. Los productos agrupados pueden renderizar varios nodos internos y esa evidencia se conserva. Si aparece el aviso de cookies tras resolver el challenge, la app intenta aceptarlo y cachea ese estado por worker para no repetir el cierre pesado en cada tanda.

Worten usa por defecto modo Edge manual/CDP porque Cloudflare puede rechazar navegadores creados directamente por Playwright. El worker abre un Edge externo con perfil limpio dedicado en `fase1/edge_manual_worten_clean_worker_<n>`, sin extensiones ni cuenta, y puerto CDP local. Si aparece challenge, se resuelve en esa ventana; al quedar validada, la app continua con la misma sesion.

## Filtros y Reintentos

La tabla incluye columna `Producto` para mostrar el titulo/modelo recuperado del marketplace.

Los resultados rojos tienen subfiltros dentro de `Fuera`:

- `Fuera marketplace` corresponde a `NO_VIVA`.
- `Sin stock feed` corresponde a `SIN_STOCK_FEED`.

Al reintentar un semaforo, la app conserva la tabla completa y solo pone como `Pendiente` los EAN del filtro reintentado. Los contadores se descuentan y recalculan solo para esas filas.

La accion `Reintentar pendientes` relanza filas que quedaron en `Pendiente`. Si el worker termina sin devolver resultado para alguna fila en vuelo, la UI la marca como gris `INCIERTA` con motivo tecnico para que pueda volver a reintentarse desde `Tecnico`.

Configuracion local opcional:

```json
{
  "marketplaces": {
    "worten": {
      "manual_cdp": true,
      "manual_cdp_port_base": 9330,
      "challenge_timeout_seconds": 600
    }
  }
}
```

Si se quiere volver al modo Playwright directo, poner `"manual_cdp": false`.

## Carrefour

Carrefour queda preparado con busqueda batch de hasta 7 EAN por navegacion. La URL se construye con EANs separados por espacios, por ejemplo:

```text
https://www.carrefour.es/?query=8435544806788%208435544888012
```

La clasificacion Carrefour se hace desde la propia busqueda:

- verde: EAN encontrado, seller esperado coincide y hay boton de compra;
- amarillo: EAN encontrado con seller distinto, seller no extraido o tarjeta sin boton de compra;
- rojo: EAN no encontrado;
- gris: challenge, timeout o HTML insuficiente.

Para Carrefour se relaja la carga del navegador respecto a Leroy: no se aplican las rutas ligeras agresivas y se espera a carga/actividad de red antes de leer resultados.

Carrefour tiene una excepcion importante: cuando la pagina muestra el banner `No hemos encontrado coincidencias para <EAN>` y debajo propone productos para otro EAN, esa tarjeta sugerida no se trata como perdida de buybox. El producto pedido se clasifica como rojo `NO_VIVA`. La perdida de buybox se reserva para casos donde la tarjeta corresponde al EAN exacto y el seller no es el esperado.

Si una tanda batch trae resultados parciales y algun EAN queda sin tarjeta mapeable, Carrefour reintenta ese EAN individualmente antes de clasificarlo como gris tecnico.

Simulador de diagnostico:

```powershell
python .\fase1\simulate_carrefour_worker.py --ean 8435544806788 --ean 8436616280192 --max-batches 1 --workers 1 --hold-seconds 5 --window-state minimized
```

## Conforama

Conforama busca por referencia interna `MKP...`, no por EAN. La app usa este archivo local no versionado:

```text
fase1/conforama_ean_mkp.xlsx
```

Columnas esperadas:

- `EAN`;
- `SKU de producto`, con valores `MKP...`.

El checker traduce el EAN a MKP y consulta el `skusearch` de Conforama. Si devuelve el `MKP` exacto, marca verde `OK`; si no lo devuelve, marca rojo `NO_VIVA`; si no existe relacion EAN -> MKP en el Excel, marca gris `INCIERTA`.

## CSV manual

El CSV manual puede tener:

```text
ean;reference;quantity;price
```

Tambien acepta columnas equivalentes:

```text
ean, sku/reference, stock/quantity, price/precio
```

## Semaforos

Verde:

- producto identificado;
- oferta comprable;
- seller esperado coincide si esta informado.

Amarillo:

- perdida de buybox;
- producto identificado pero no disponible aunque el feed tiene stock;
- caso comercial que requiere revision.

Rojo:

- stock feed menor o igual a cero;
- producto no vendido/no encontrado en marketplace.

Gris:

- fallo tecnico, challenge, timeout o HTML incompleto.
- No se debe usar como decision comercial.

## Salidas

Cada ejecucion crea:

```text
fase1/dashboard_runs/<timestamp>/summary_live.csv
```

Para ahorrar espacio, el HTML solo se guarda en casos no verdes.

## Nota operativa Leroy

Si Leroy muestra `challenge en warm-up`, el fallo ocurre antes de analizar EANs. Revisar el ultimo directorio:

```text
fase1/dashboard_runs/<timestamp>/worker_01_warmup_challenge.html
```

Puede ser challenge real o falso positivo por referencias tecnicas de DataDome en una home normal. Antes de cambiar extraccion de productos, comprobar `title`, URL final, longitud HTML y texto visible de ese archivo.
