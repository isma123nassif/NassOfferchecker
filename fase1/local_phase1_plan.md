# Fase 1 local - Leroy Offer Watcher

## Objetivo

Validar si podemos detectar ofertas vivas en `leroymerlin.es` sin Apify, buscando por EAN y guardando evidencia tecnica suficiente para decidir si merece la pena pasar a Playwright.

## Alcance

Esta fase usa peticiones de bajo volumen y ritmo conservador. No intenta saltarse protecciones anti-bot. Si aparece bloqueo, captcha, 403, 429 o HTML incompleto, el resultado sera `INCIERTA` y se recomendara pasar a navegador real o reducir frecuencia.

## Entrada

Archivo base:

- `Referencias.csv`

El runner extrae la columna `ean`.

## Agentes logicos de fase 1

1. `orchestrator`: lee EANs, limita volumen y aplica pausas.
2. `search_fetcher`: consulta `https://www.leroymerlin.es/search?q=<EAN>`.
3. `candidate_extractor`: busca URLs de producto candidatas y senales del EAN en HTML.
4. `validator`: clasifica cada EAN como `VIVA_CANDIDATA`, `NO_ENCONTRADA_PRELIMINAR` o `INCIERTA`.
5. `evidence_writer`: guarda HTML, resumen CSV y JSON.

## Estados

`VIVA_CANDIDATA`:

- La pagina de busqueda responde correctamente.
- Aparece el EAN o aparecen URLs de producto candidatas para investigar.

`NO_ENCONTRADA_PRELIMINAR`:

- La busqueda responde correctamente.
- No aparece el EAN ni URLs candidatas.

`INCIERTA`:

- HTTP 403, 429, timeout, captcha, challenge, redireccion sospechosa o HTML demasiado pequeno.

## Uso

```powershell
python .\fase1\run_local_poc.py --ean-file .\Referencias.csv --limit 3
```

Tambien se puede probar HTTP simple con una cookie de sesion aportada manualmente:

```powershell
$env:LEROY_COOKIE_HEADER = "cookie1=valor1; cookie2=valor2"
python .\fase1\run_local_poc.py --ean-file .\Referencias.csv --limit 1
```

El runner no lee cookies de Edge/Chrome y no guarda el valor de la cookie en outputs.

Para usar un proxy corporativo o propio, se puede usar la configuracion estandar del entorno:

```powershell
$env:HTTPS_PROXY = "http://usuario:password@host:puerto"
python .\fase1\run_local_poc.py --ean-file .\Referencias.csv --limit 3
```

No se recomienda basar el sistema en VPNs o proxies gratuitos: suelen estar bloqueados, introducen ruido y pueden producir falsos negativos.

## Salidas

Directorio:

- `fase1/output_local/`

Archivos:

- `*_summary.csv`: resumen por EAN.
- `*_raw.json`: metadatos y URLs candidatas.
- `html/*.html`: evidencia HTML por busqueda.

## Criterio para pasar a fase 2

Pasar a Playwright si:

- Mas del 20% de EANs quedan `INCIERTA`.
- La pagina necesita JavaScript para exponer productos.
- Las URLs candidatas no aparecen en HTML estatico.

Mantener HTTP simple si:

- La mayoria de busquedas devuelven HTML util.
- Se pueden extraer candidatos y senales de EAN sin renderizado.
- Una sesion controlada mediante `LEROY_COOKIE_HEADER` evita el challenge de forma estable.
