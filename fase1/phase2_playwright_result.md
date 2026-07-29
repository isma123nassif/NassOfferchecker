# Resultado fase 2 - Playwright con perfil dedicado

Fecha: 2026-07-29

## Objetivo

Validar si un navegador real con perfil dedicado puede consultar `leroymerlin.es` por EAN cuando HTTP simple anonimo devuelve DataDome challenge.

## Implementacion

Script:

- `fase1/run_playwright_bootstrap.py`

Perfil dedicado:

- `fase1/browser_profile_leroy/`

No se uso el perfil personal de Edge/Chrome.

## Ejecucion validada

Comando:

```powershell
python .\fase1\run_playwright_bootstrap.py --ean-file .\Referencias.csv --limit 0 --delay 10 --bootstrap-home --wait-solved 600 --timeout 90
```

Resultado inicial:

- Home de Leroy cargada sin challenge visible.
- Busqueda por EAN funcional.
- 10 de 10 EANs clasificados como `VIVA_CANDIDATA`.
- 0 de 10 con `challenge_detected=true`.
- Todos los HTML renderizados superaron 550 KB.
- Todos los EANs aparecieron en HTML renderizado.

## Correccion posterior

La clasificacion inicial tuvo un falso positivo: `8436579958121` aparecia por EAN, pero la oferta no estaba disponible.

Evidencia:

- JSON-LD: `availability=https://schema.org/Discontinued`
- Banner: `El producto no está disponible`
- Bloque de recomendaciones: `Te recomendamos en su lugar`
- Sin oferta comprable: no aparece `add_to_cart_availability=true` para el producto principal

Regla corregida:

- `ean_in_html=true` confirma identidad, no disponibilidad.
- Para `VIVA` debe existir senal de oferta comprable.
- Si el producto existe pero esta discontinuado/no disponible, el estado correcto es `NO_VIVA`.

Ejecucion final corregida:

- `fase1/output_playwright/20260729_114858/summary.csv`

Resultado corregido:

- 9 de 10 EANs: `VIVA`
- 1 de 10 EANs: `NO_VIVA`
- `8436579958121`: `NO_VIVA`

Evidencia:

- `fase1/output_playwright/20260729_114019/summary.csv`
- `fase1/output_playwright/20260729_114019/*.html`
- `fase1/output_playwright/20260729_114019/*.png`
- `fase1/output_playwright/20260729_114019/*_cookies_redacted.json`

## EANs detectados

| EAN | Estado | Producto |
|---|---|---|
| 8436579958152 | VIVA_CANDIDATA | Newlux Perchero Burro Hangy Wood 100 Negro |
| 8436579958169 | VIVA_CANDIDATA | Newlux Perchero Burro Hangy Wood 100 Blanco |
| 8436579958176 | VIVA_CANDIDATA | Newlux Perchero Burro Hangy Wood 400 Negro |
| 8436579958183 | VIVA_CANDIDATA | Newlux Perchero Burro Hangy Wood 400 Blanco |
| 8436579958138 | VIVA_CANDIDATA | Newlux Perchero Burro Hangy Duo 30 Negro |
| 8436579958145 | VIVA_CANDIDATA | Newlux Perchero Burro Hangy Duo 30 Blanco |
| 8436579958091 | VIVA_CANDIDATA | Newlux Perchero Burro Hangy One 15 Negro |
| 8436579958107 | VIVA_CANDIDATA | Newlux Perchero Burro Hangy One 15 Blanco |
| 8436579958114 | VIVA_CANDIDATA | Newlux Perchero Burro Hangy One 20 Negro |
| 8436579958121 | NO_VIVA | Newlux Perchero Burro Hangy One 20 Blanco |

## Conclusion

La solucion operativa viable es Playwright con perfil dedicado. HTTP anonimo falla por DataDome, pero el navegador persistente dedicado carga busquedas por EAN y permite guardar evidencia suficiente.

## Siguiente fase

Fase 3: validador de oferta real.

La fase 2 solo confirma que el producto aparece por EAN. La fase 3 debe extraer y normalizar:

- seller esperado;
- precio;
- stock/disponibilidad;
- boton o estado de compra;
- URL canonica;
- EAN confirmado;
- motivo exacto de `VIVA`, `NO_VIVA` o `INCIERTA`.
