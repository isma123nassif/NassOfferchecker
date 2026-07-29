# Correccion de falso positivo - EAN 8436579958121

Fecha: 2026-07-29

## Error detectado

El EAN `8436579958121` fue clasificado inicialmente como `VIVA_CANDIDATA` porque:

- la pagina existia;
- la busqueda por EAN redirigia a una PDP;
- el EAN aparecia en HTML renderizado.

Ese criterio era insuficiente. Un producto puede existir y conservar EAN/SKU, pero no tener oferta comprable.

## Evidencia real

Archivo original:

- `fase1/output_playwright/20260729_114019/010_8436579958121.html`

Senales encontradas:

```json
"offers" : {
  "@type" : "Offer",
  "availability" : "https://schema.org/Discontinued"
}
```

```json
"gtin" : "8436579958121"
```

```html
<p class="recommendation-no-offer-banner">El producto no está disponible</p>
```

Tambien se detecto en el bloque principal del producto:

- `total_offer_count=0`
- sin `offer` comprable;
- sin `add_to_cart_availability=true`;
- recomendaciones alternativas bajo "Te recomendamos en su lugar".

## Nueva regla

`ean_in_html=true` solo confirma identidad. No confirma oferta viva.

Para marcar `VIVA` se exige:

- EAN presente o producto identificado;
- y senal de oferta comprable, por ejemplo `add_to_cart_availability=true`;
- y ausencia de senales negativas como `schema.org/Discontinued` o banner `recommendation-no-offer-banner`.

Para marcar `NO_VIVA`:

- EAN/producto existe;
- pero `availability=Discontinued`, `recommendation-no-offer-banner`, `total_offer_count=0` o no hay oferta comprable.

## Resultado corregido

Con el validador actualizado:

```text
8436579958121 -> NO_VIVA
Motivo: EAN encontrado pero oferta no disponible (https://schema.org/Discontinued)
```

Ejecucion corregida:

- `fase1/output_playwright/20260729_114858/summary.csv`
- `fase1/output_playwright/20260729_114858/010_8436579958121.html`
- `fase1/output_playwright/20260729_114858/010_8436579958121.png`

Fila corregida:

```text
status=NO_VIVA
ean_in_html=True
product_availability=https://schema.org/Discontinued
offer_available=False
availability_evidence=jsonld availability=https://schema.org/Discontinued
```

## Cambio de implementacion

Archivo:

- `fase1/run_playwright_bootstrap.py`

Campos nuevos en salida:

- `product_availability`
- `offer_available`
- `availability_evidence`

Estados actualizados:

- `VIVA`
- `NO_VIVA`
- `INCIERTA`
- `NO_ENCONTRADA_PRELIMINAR`
