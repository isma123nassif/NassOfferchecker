# Resultado fase 1 local

Fecha: 2026-07-29

## Prueba ejecutada

Comando:

```powershell
python .\fase1\run_local_poc.py --ean-file .\Referencias.csv --limit 1 --delay 8 --timeout 30
```

EAN probado:

- `8436579958152`

URL:

- `https://www.leroymerlin.es/search?q=8436579958152`

## Resultado

Estado preliminar:

- `INCIERTA`

Motivo:

- HTTP `403`
- HTML de solo `774` bytes
- Respuesta con challenge/captcha de DataDome
- Mensaje visible: `Please enable JS and disable any ad blocker`
- Script externo: `https://ct.captcha-delivery.com/c.js`

Evidencia:

- `fase1/output_local/20260729_111425/summary.csv`
- `fase1/output_local/20260729_111425/raw.json`
- `fase1/output_local/20260729_111425/html/8436579958152_a8a67de6a2.html`

## Conclusion tecnica

El enfoque HTTP simple anonimo queda bloqueado para detectar ofertas en Leroy Merlin Espana. La web exige JavaScript y activa proteccion anti-bot antes de entregar contenido util de busqueda.

HTTP simple no queda descartado definitivamente: se abre una fase 1b para probar una cookie de sesion controlada mediante `LEROY_COOKIE_HEADER`. No se leeran automaticamente cookies de Edge/Chrome ni se guardaran cookies en evidencias.

Si fase 1b sigue devolviendo `403` o challenge, la fase 2 debe usar navegador real controlado, con ritmo bajo, persistencia de sesion, capturas de evidencia y clasificacion `INCIERTA` cuando aparezca challenge. No se debe marcar una oferta como muerta por un bloqueo tecnico.

## Siguiente fase recomendada

Fase 1b: HTTP simple con sesion controlada.

Objetivo:

- Probar `LEROY_COOKIE_HEADER`.
- Mantener bajo volumen.
- Confirmar si la respuesta pasa de `403` a `200`.
- No guardar credenciales de sesion en outputs.

### Prueba fase 1b con cookie parcial

Se probo una cookie aislada de visitante:

- `session_mode`: `cookie_env_http`
- `cookie_fingerprint`: `080836540c9e`
- HTTP: `403`
- HTML: `774` bytes
- Estado: `INCIERTA`

Evidencia:

- `fase1/output_local/20260729_112117/summary.csv`
- `fase1/output_local/20260729_112117/raw.json`
- `fase1/output_local/20260729_112117/html/8436579958152_a8a67de6a2.html`

Conclusion: esa cookie parcial no basta para superar el challenge. Para seguir con HTTP simple hace falta el header `Cookie` completo de una sesion valida de `leroymerlin.es`, o pasar al perfil Playwright dedicado.

Si no funciona:

Fase 2: Playwright local.

Objetivo:

- Abrir busqueda por EAN con Chromium real.
- Esperar carga de resultados.
- Capturar screenshot y HTML renderizado.
- Extraer URLs candidatas.
- Clasificar sin asumir `NO_VIVA` ante bloqueo.

Reglas:

- Bajo volumen.
- Pausas entre EANs.
- Reintento diferido.
- Sin dependencia de VPNs/proxies gratuitos como base del sistema.
