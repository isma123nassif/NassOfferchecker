# Fase 1b - HTTP simple con sesion controlada

## Objetivo

Mantener HTTP simple como opcion, pero usando una sesion aportada de forma explicita y controlada.

No se debe leer automaticamente la base de datos de cookies de Edge/Chrome. Esas cookies son credenciales personales y pueden incluir sesiones de otros sitios. Tambien suelen estar cifradas por el sistema operativo, pueden estar bloqueadas mientras el navegador esta abierto y no conviene copiarlas completas a un scraper.

## Enfoque permitido para fase 1b

El runner acepta una cookie HTTP ya preparada mediante variable de entorno:

```powershell
$env:LEROY_COOKIE_HEADER = "cookie1=valor1; cookie2=valor2"
python .\fase1\run_local_poc.py --ean-file .\Referencias.csv --limit 1
```

Para no dejar la cookie en el historial de PowerShell, usar prompt oculto:

```powershell
python .\fase1\run_local_poc.py --ean-file .\Referencias.csv --limit 1 --cookie-prompt
```

Cuando pregunte, pegar:

```text
datadome=valor; pa_visitor_status_v5=%22exempt%22
```

El valor de `LEROY_COOKIE_HEADER` no se escribe en `summary.csv`, `raw.json` ni en logs. Solo se guarda:

- `session_mode=anonymous_http`
- `session_mode=cookie_env_http`
- `cookie_fingerprint`, un hash corto para distinguir sesiones sin exponer la cookie

Opcionalmente se puede fijar el User-Agent de la misma sesion:

```powershell
$env:LEROY_USER_AGENT = "Mozilla/5.0 ..."
```

## Como obtener una cookie de forma controlada

Recomendacion:

1. Crear un perfil de navegador dedicado solo para Leroy.
2. Abrir `https://www.leroymerlin.es/`.
3. Aceptar cookies o resolver pasos manuales normales si aparecen.
4. Copiar solo las cookies necesarias para `leroymerlin.es` desde DevTools.
5. Pegar el header en `LEROY_COOKIE_HEADER` para una prueba de bajo volumen.

No usar el perfil personal principal de Edge para automatizacion.

## Criterio de exito

HTTP con cookie sigue siendo viable si:

- El HTTP pasa de `403` a `200`.
- El HTML supera el umbral minimo.
- Aparecen URLs de producto o el EAN buscado.
- La prueba se mantiene estable con 3-5 EANs y pausas.

## Criterio de abandono

Pasar a Playwright dedicado si:

- La cookie no elimina el challenge.
- El HTML depende de JavaScript para renderizar resultados.
- La sesion caduca con frecuencia.
- Hay mas de 20% de `INCIERTA`.

## Nota sobre proxies y VPNs

La fase 1b puede usar `HTTPS_PROXY` si existe un proxy propio o corporativo:

```powershell
$env:HTTPS_PROXY = "http://usuario:password@host:puerto"
```

No se recomienda usar VPNs/proxies gratuitos como base: suelen estar bloqueados, degradan estabilidad y pueden convertir productos vivos en falsos `NO_VIVA`.
