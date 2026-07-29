# Dashboard Leroy Offer Watcher

## Arranque

Windows:

```bat
launch_dashboard.bat
```

Alternativa:

```powershell
python .\dashboard_leroy_modern.py
```

## Uso

1. Selecciona marketplace: `Leroy Merlin`.
2. Introduce un EAN manual o carga un CSV bulk.
3. Opcional: ajusta `Seller esperado`, por defecto `NEWLUX GROUP`.
4. Pulsa `Analizar`.

El CSV bulk puede tener:

```text
ean;reference;quantity;price
```

Tambien acepta columnas equivalentes:

```text
ean, sku/reference, stock/quantity, price/precio
```

## Semaforos

Verde:

- producto identificado;
- oferta comprable;
- seller esperado coincide si esta informado.

Amarillo:

- perdida de buybox;
- producto identificado pero no disponible aunque el feed tiene stock;
- caso comercial que requiere revision.

Rojo:

- stock feed menor o igual a cero;
- producto no vendido/no encontrado en marketplace.

Gris:

- fallo tecnico, challenge, timeout o HTML incompleto.
- No se debe usar como decision comercial.

## Salidas

Cada ejecucion crea:

```text
fase1/dashboard_runs/<timestamp>/summary_live.csv
```

Para ahorrar espacio, el HTML solo se guarda en casos no verdes.
