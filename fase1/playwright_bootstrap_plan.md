# Fase 2 - Playwright con perfil dedicado

## Objetivo

Usar un navegador real con perfil aislado para comprobar busquedas por EAN en Leroy Merlin cuando HTTP simple devuelve `datadome_challenge`.

## Perfil

Ruta:

```text
fase1/browser_profile_leroy/
```

Este perfil es dedicado para Leroy. No lee cookies de Edge/Chrome y no toca sesiones personales.

## Ejecucion

```powershell
python .\fase1\run_playwright_bootstrap.py --ean-file .\Referencias.csv --limit 1 --wait-solved 600
```

Flujo:

1. Se abre Chromium con perfil persistente.
2. El script navega a la busqueda del primer EAN.
3. Si aparece challenge, lo resuelves manualmente en la ventana.
4. El script revisa cada 5 segundos si el challenge desaparecio.
5. El script guarda HTML, screenshot, resumen y cookies redactadas.

## Evidencia

Directorio:

```text
fase1/output_playwright/<timestamp>/
```

Archivos:

- `summary.csv`
- `<ean>.html`
- `<ean>.png`
- `<ean>_cookies_redacted.json`

Las cookies se guardan redactadas: valor oculto y hash corto.

## Criterio de avance

Si el perfil dedicado consigue cargar resultados:

- fase 2 valida extraccion de URLs candidatas;
- fase 3 abre cada URL candidata y extrae seller, precio, stock y EAN;
- HTTP simple puede quedar como carril rapido cuando la sesion sea reutilizable.

Si Playwright tambien queda en challenge:

- el estado sigue siendo `INCIERTA`;
- no se marca oferta como muerta;
- se requiere resolucion manual, menor frecuencia o proveedor autorizado.
