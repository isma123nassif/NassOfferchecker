# Fase 1 - Actors candidatos Apify

Fecha de preparacion: 2026-07-29

## Candidato A: abotapi/leroymerlin-es-scraper

URL: https://apify.com/abotapi/leroymerlin-es-scraper

Motivo para probarlo primero:
- Actor dedicado a Leroy Merlin Espana (`leroymerlin.es`).
- Acepta `mode=search` con `searchTerm`, por lo que permite probar EANs como busquedas.
- Con `fetchDetails=true` declara salida con `ean`, `sku`, `price`, `sellerName`, `sellerType`, `stock`, `stockStatus`, `deliveryTime`, `otherOffers`, `url` y datos de producto.
- Declara proxy residencial espanol por defecto/requerido.

Riesgo:
- Pocos usuarios y sin rating publico todavia.
- Hay que validar que la busqueda por EAN devuelve el producto correcto, no solo busquedas por keyword.

Input PoC recomendado:

```json
{
  "mode": "search",
  "searchTerm": "8436579958152",
  "sortBy": "relevance",
  "sellerFilter": "any",
  "fetchDetails": true,
  "fetchReviews": false,
  "maxItems": 5,
  "proxy": {
    "useApifyProxy": true,
    "apifyProxyGroups": ["RESIDENTIAL"],
    "apifyProxyCountry": "ES"
  }
}
```

## Candidato B: studio-amba/leroymerlin-es-scraper

URL: https://apify.com/studio-amba/leroymerlin-es-scraper

Motivo para probarlo:
- Actor dedicado a Leroy Merlin Espana.
- Acepta `searchQuery`, `categoryUrl` y `startUrls`.
- Puede servir como comparativa si `abotapi` falla.

Riesgo:
- Puede requerir Bright Data Web Unlocker ademas de proxy residencial.
- La busqueda puede ser menos fiable que URL/categoria segun el propio patron de estos Actors.

Input PoC recomendado:

```json
{
  "searchQuery": "8436579958152",
  "maxResults": 5,
  "proxyConfiguration": {
    "useApifyProxy": true,
    "apifyProxyGroups": ["RESIDENTIAL"],
    "apifyProxyCountry": "ES"
  }
}
```

## Candidato C: sian.agency/leroy-merlin-product-scraper

URL: https://apify.com/sian.agency/leroy-merlin-product-scraper

Motivo para tenerlo como referencia:
- Actor dedicado a Leroy Merlin con salida rica en `gtin`, seller, precio y disponibilidad.
- Puede ayudar a entender esquema de datos si necesitamos construir Actor propio.

Riesgo:
- Es para `leroymerlin.fr`, no para Espana.
- No debe ser la primera prueba para ofertas de `leroymerlin.es`.

## Candidato D: Actor propio o generico sobre leroymerlin.es

Uso:
- Si A y B no funcionan por busqueda EAN, fase 1 debe pasar a prueba con navegador real sobre `leroymerlin.es`.
- Puede implementarse con Apify Web Scraper, Puppeteer Scraper, Playwright/Crawlee o un Actor privado.

Ventaja:
- Control total sobre buscador de Espana, selectores, evidencias y reglas.

Riesgo:
- Mas trabajo inicial que usar un Actor Store ya mantenido.

## Decision de fase 1

1. Probar primero `abotapi/leroymerlin-es-scraper` con `mode=search`, `searchTerm=<EAN>`, `fetchDetails=true`.
2. Si no devuelve resultados para EANs espanoles, probar `studio-amba/leroymerlin-es-scraper`.
3. Si la busqueda EAN falla pero tenemos URLs, probar `abotapi` con `mode=url`.
4. Si ambos fallan por bloqueo o ambiguedad, construir Actor privado orientado a `leroymerlin.es`.
