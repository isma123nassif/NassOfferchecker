# Diagnostico DataDome en Leroy Merlin

## Que hemos visto

La peticion HTTP simple a:

```text
https://www.leroymerlin.es/search?q=8436579958152
```

devuelve:

- HTTP `403`
- HTML muy pequeno, `774` bytes
- Mensaje: `Please enable JS and disable any ad blocker`
- Variable JavaScript `dd`
- Script externo `https://ct.captcha-delivery.com/c.js`

Esto encaja con un challenge de DataDome.

## Que significa

Segun documentacion oficial de DataDome, su proteccion usa una combinacion de:

- integracion server-side que decide permitir, bloquear o desafiar una request;
- tag client-side JavaScript;
- comprobacion de dispositivo/navegador;
- fingerprinting de cliente, incluyendo senales HTTP, TLS y navegador;
- reputacion y comportamiento;
- captcha o device check cuando el riesgo no queda resuelto.

Fuentes:

- https://docs.datadome.co/docs/device-check
- https://docs.datadome.co/docs/bot-authentication
- https://docs.datadome.co/docs/threat-detection
- https://docs.datadome.co/docs/rule-responses

## Diagnostico probable

El bloqueo no se debe solo a falta de una cookie aislada. Una cookie `datadome` puede estar ligada a varias senales de contexto:

- IP o reputacion de red.
- User-Agent.
- fingerprint TLS/HTTP.
- cookies complementarias.
- ejecucion previa de JavaScript.
- coherencia entre navegador, cabeceras, idioma, zona y comportamiento.

Por eso copiar solo `pa_visitor_status_v5` no funciono. Copiar solo `datadome` puede funcionar temporalmente o seguir fallando si no encaja con el resto de senales.

## Datos que recogera el runner

El runner genera por EAN:

- HTTP status.
- bytes de HTML.
- URLs candidatas.
- si el EAN aparece en HTML.
- tipo de challenge detectado.
- marcadores tecnicos:
  - `datadome_var`
  - `captcha_delivery`
  - `please_enable_js`
  - `captcha`
  - `json_ld_present`
  - `next_data_present`
- fingerprint corto de cookie, nunca el valor.

## Solucion recomendada

Arquitectura de dos carriles:

1. HTTP simple con sesion controlada.
   - Usar `LEROY_COOKIE_HEADER` o `--cookie-prompt`.
   - Bajo volumen.
   - No guardar cookies.
   - Si devuelve `200` y HTML util, mantenerlo como carril rapido.

2. Playwright con perfil dedicado.
   - Perfil separado solo para Leroy.
   - Intervencion manual si aparece challenge.
   - Reutilizar sesion del perfil para comprobaciones posteriores.
   - Guardar screenshots y HTML renderizado.

No se debe marcar una oferta como `NO_VIVA` cuando el diagnostico indique `datadome_challenge`, `http_block` o `thin_html`.

## Criterio operativo

Mantener HTTP si:

- `challenge_type=none`
- HTTP `200`
- HTML suficientemente grande
- aparecen URLs de producto o el EAN

Pasar a Playwright si:

- `challenge_type=datadome_challenge`
- HTTP `403` o `429`
- HTML menor de `10000` bytes
- las cookies caducan o no son coherentes con la sesion
