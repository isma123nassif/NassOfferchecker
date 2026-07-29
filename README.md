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
- Bloqueo de recursos pesados: imagenes, media, fuentes y tracking conocido.
- Chromium se abre minimizado para no molestar al usuario.

No se bloquea JavaScript general ni mecanismos de sesion, para no degradar la precision del diagnostico.

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
- `fase1/*.md`: analisis, decisiones tecnicas y resultados de pruebas previas.
- `fase1/run_playwright_bootstrap.py`: runner Playwright de fase 1.
- `fase1/run_local_poc.py`: prueba HTTP local.
- `fase1/run_apify_poc.py`: prueba Apify historica, mantenida como referencia.
