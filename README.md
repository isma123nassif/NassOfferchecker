# Nass Offer Checker

Dashboard Windows/Python para revisar disponibilidad de ofertas en Leroy Merlin a partir de EANs o de un feed vivo de Shoppingfeed.

La app usa un navegador Chromium persistente mediante Playwright para consultar Leroy Merlin, clasifica cada producto con semaforos comerciales y guarda resultados locales para acelerar ejecuciones posteriores.

## Estado actual

- Marketplace soportado: `Leroy Merlin`.
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
  "shoppingfeed_url": "https://export.shopping-feed.com/stream/PRIVATE_TOKEN",
  "slack_webhook_url": "https://hooks.slack.com/services/PRIVATE/WEBHOOK/URL",
  "alerts_enabled": true,
  "alert_cooldown_minutes": 15
}
```

Tambien puedes usar variables de entorno:

```powershell
$env:SHOPPINGFEED_CATALOG_URL = "https://export.shopping-feed.com/stream/..."
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
$env:ALERTS_ENABLED = "true"
$env:ALERT_COOLDOWN_MINUTES = "15"
```

## Uso

1. Abre el dashboard.
2. Selecciona `Leroy Merlin`.
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

Cache local:

```text
fase1/offer_cache.sqlite
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

El texto superior de la ventana puede mostrar el ultimo evento recibido, por ejemplo `Worker 1 activo`. Ese texto no representa el estado agregado de todos los workers. El estado real de cada worker esta en los chips inferiores:

```text
W1 activo | P:no | UA:def
W2 activo | P:no | UA:def
```

Pendiente recomendado antes de avanzar:

- mostrar un resumen agregado tipo `2 workers activos`;
- separar la ruta de salida del estado de workers;
- anadir warm-up por worker antes de consumir la cola;
- pausar workers individualmente cuando reciban challenge;
- aplicar proxy/User-Agent persistente por worker en Playwright.

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
