# Resultado prueba 2

Fecha: 2026-07-29

## Entrada

Archivo:

- `fase1/eans_prueba2.csv`

EANs probados:

- `8436616281335`
- `8436616281373`
- `8436616281380`
- `8436616281342`
- `8436616281311`

## Ejecucion

Comando:

```powershell
python .\fase1\run_playwright_bootstrap.py --ean-file .\fase1\eans_prueba2.csv --limit 0 --delay 10 --bootstrap-home --wait-solved 600 --timeout 90
```

Evidencia:

- `fase1/output_playwright/20260729_115158/summary.csv`
- `fase1/output_playwright/20260729_115158/*.html`
- `fase1/output_playwright/20260729_115158/*.png`
- `fase1/output_playwright/20260729_115158/*_cookies_redacted.json`

## Resultado

| EAN | Estado | Disponibilidad | Evidencia |
|---|---|---|---|
| 8436616281335 | VIVA | `http://schema.org/OnlineOnly` | `add_to_cart_availability=true` |
| 8436616281373 | VIVA | `http://schema.org/OnlineOnly` | `add_to_cart_availability=true` |
| 8436616281380 | VIVA | `http://schema.org/OnlineOnly` | `add_to_cart_availability=true` |
| 8436616281342 | NO_VIVA | `https://schema.org/Discontinued` | `jsonld availability=https://schema.org/Discontinued` |
| 8436616281311 | VIVA | `http://schema.org/OnlineOnly` | `add_to_cart_availability=true` |

## Conclusion

El producto no disponible es:

```text
8436616281342
```

Motivo:

```text
EAN encontrado pero oferta no disponible (https://schema.org/Discontinued; jsonld availability=https://schema.org/Discontinued)
```

La correccion aplicada tras el falso positivo anterior funciona en esta prueba: presencia de EAN no implica oferta viva; la disponibilidad se decide por senales de oferta comprable.
