# Resultado check Shoppingfeed

Fecha: 2026-07-29

## Feed

URL:

- feed privado de Shoppingfeed omitido por seguridad.

Archivo descargado:

- `fase1/shoppingfeed_latest.csv`

Columnas:

- `ean`
- `reference`
- `quantity`
- `price`

Conteo:

- filas totales: `1918`
- EANs validos: `1749`
- EANs unicos: `1749`

## Comando principal

```powershell
python .\fase1\run_playwright_bootstrap.py --ean-file .\fase1\shoppingfeed_latest.csv --limit 0 --delay 1 --bootstrap-home --wait-solved 120 --timeout 45 --networkidle-timeout 0 --skip-screenshot --skip-cookies --html-mode failures --suppress-final-json
```

## Resultado del primer tramo

Salida:

- `fase1/output_playwright/20260729_121103/summary_live.csv`

Resultado:

- completados: `1675 / 1749`
- duracion: `2567.9` segundos, aprox. `42m 48s`
- media: `1.53` segundos por EAN

Estados:

- `VIVA`: `1311`
- `NO_VIVA`: `363`
- `NO_ENCONTRADA_PRELIMINAR`: `1`

El proceso fallo en el EAN 1676 por error de Playwright:

```text
Page.goto: Frame was detached
```

Ese error aparecio tras varios avisos de challenge.

## Resultado del segundo tramo

Archivo de entrada:

- `fase1/shoppingfeed_remaining_20260729_121103.csv`

Salida:

- `fase1/output_playwright/20260729_125515/summary_live.csv`

Resultado:

- completados: `43 / 74`
- duracion: `778` segundos, aprox. `12m 58s`

Estados:

- `VIVA`: `34`
- `NO_VIVA`: `6`
- `INCIERTA`: `3`

El tramo se degrado porque DataDome volvio a mostrar challenge persistente. Sin resolucion manual, el proceso no puede producir una decision fiable para todos los restantes.

## Consolidado actual

Archivo consolidado:

- `fase1/shoppingfeed_check_final_20260729.csv`

Pendientes:

- `fase1/shoppingfeed_pending_final_20260729.csv`

Resultado consolidado final:

- EANs del feed: `1749`
- checkeados: `1749`
- pendientes: `0`

Estados:

- `VIVA`: `1363`
- `NO_VIVA`: `382`
- `INCIERTA`: `3`
- `NO_ENCONTRADA_PRELIMINAR`: `1`

## Tramo final tras limpiar perfil

Se limpio el perfil dedicado:

- `fase1/browser_profile_leroy/`

Despues se relanzaron los 31 pendientes:

```powershell
python .\fase1\run_playwright_bootstrap.py --ean-file .\fase1\shoppingfeed_pending_20260729.csv --limit 0 --delay 2 --bootstrap-home --wait-solved 600 --timeout 45 --networkidle-timeout 0 --skip-screenshot --skip-cookies --html-mode failures --suppress-final-json
```

Salida:

- `fase1/output_playwright/20260729_131820/summary.csv`

Resultado:

- completados: `31 / 31`
- duracion: `97.0` segundos
- `VIVA`: `18`
- `NO_VIVA`: `13`
- challenge: `0`

## Tiempo estimado

Sin challenges, el primer tramo indica una velocidad de:

```text
1.53 segundos / EAN
```

Para `1749` EANs:

```text
1749 * 1.53 = 2676 segundos = 44m 36s aprox.
```

Tiempo medido total de ejecuciones utiles:

```text
2567.9s + 778s + 97s = 3442.9s = 57m 23s aprox.
```

Con challenges persistentes, el tiempo real sube y puede quedar bloqueado esperando intervencion manual. Limpiar el perfil dedicado permitio completar los 31 pendientes en 97 segundos.

## Conclusion

El modo rapido funciona bien hasta que DataDome decide desafiar la sesion. Para una operacion diaria, el sistema debe:

- procesar por lotes;
- hacer checkpoint incremental;
- cortar automaticamente si aparecen varios challenges seguidos;
- reanudar desde pendientes despues de resolver manualmente la sesion;
- permitir limpiar/rotar perfil dedicado por lotes;
- no marcar `NO_VIVA` por challenge.
