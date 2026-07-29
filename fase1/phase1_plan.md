# Fase 1 - PoC Leroy Offer Watcher

## Objetivo

Validar si Apify puede detectar de forma fiable si una oferta de Leroy Merlin sigue viva buscando por EAN.

Esta fase no intenta crear el sistema completo. Intenta responder cuatro preguntas:

1. El buscador de Leroy devuelve resultados utiles al buscar por EAN.
2. Un Actor dedicado de Apify puede extraer esos resultados sin bloqueo.
3. La salida contiene senales suficientes para decidir `VIVA`, `NO_VIVA` o `INCIERTA`.
4. El coste/tiempo por EAN es aceptable para una ejecucion periodica.

## Lote de prueba

Archivo: `fase1/eans_poc.csv`

Contiene los EANs encontrados en `Referencias.csv`. Para aumentar la calidad del PoC conviene completar:

- `expected_seller`: vendedor esperado si se conoce.
- `expected_url`: URL esperada si existe.
- `notes`: contexto manual, por ejemplo "se que esta vivo" o "deberia estar muerto".

## Senales minimas

Para marcar una oferta como `VIVA`:

- El EAN buscado aparece como `gtin`, `ean`, especificacion tecnica o texto verificable.
- Hay una URL de producto accesible.
- Hay precio o disponibilidad.
- Si se conoce vendedor esperado, debe coincidir.
- Idealmente existe boton/estado de compra o disponibilidad.

Para marcar `NO_VIVA`:

- La busqueda no devuelve candidatos tras reintento.
- O el producto existe, pero el seller esperado no aparece.
- O la URL esperada devuelve no disponible/404/retirada.

Para marcar `INCIERTA`:

- Bloqueo, captcha, timeout, HTML incompleto o error del Actor.
- Resultado sin EAN verificable.
- Multiples candidatos ambiguos.

## Criterio de exito de fase 1

La fase 1 se considera valida si:

- Al menos 8 de 10 EANs terminan con estado no tecnico: `VIVA` o `NO_VIVA`.
- Los resultados incluyen evidencia suficiente: URL, titulo, seller/precio/disponibilidad o motivo de ausencia.
- La tasa de `INCIERTA` queda por debajo del 20% en una segunda ejecucion.

## Comando de prueba

PowerShell:

```powershell
$env:APIFY_TOKEN = "TU_TOKEN"
python .\fase1\run_apify_poc.py --actor abotapi --ean-file .\fase1\eans_poc.csv --max-results 5
```

Alternativa:

```powershell
$env:APIFY_TOKEN = "TU_TOKEN"
python .\fase1\run_apify_poc.py --actor studio-amba-es --ean-file .\fase1\eans_poc.csv --max-results 5
```

## Salidas esperadas

El runner guarda:

- `fase1/output/<timestamp>_<actor>_raw.json`
- `fase1/output/<timestamp>_<actor>_summary.csv`

El CSV resumen permite ver rapidamente:

- EAN buscado.
- Si hubo candidato.
- Cuantos items devolvio el Actor.
- Campos detectados: titulo, URL, precio, seller, disponibilidad, gtin/ean.
- Estado preliminar: `VIVA_CANDIDATA`, `NO_ENCONTRADA` o `INCIERTA`.
