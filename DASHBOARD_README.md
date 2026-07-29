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

1. Selecciona marketplace: `Leroy Merlin`.
2. Pulsa `Cargar catalogo Shoppingfeed` para recuperar el feed vivo.
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

La cache local se guarda en:

```text
fase1/offer_cache.sqlite
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
```

O crea un archivo local no versionado:

```text
local_settings.json
```

Con este formato:

```json
{
  "shoppingfeed_url": "https://export.shopping-feed.com/stream/..."
}
```

La app descarga el feed y lo cachea localmente en:

```text
fase1/shoppingfeed_latest.csv
```

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
