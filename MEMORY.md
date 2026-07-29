# Memory Nass Offer Checker

Fecha de corte: 2026-07-29.

## Objetivo

Construir una app Windows visual para comprobar si las ofertas de Leroy Merlin siguen vivas, usando EANs del catalogo Shoppingfeed o entradas manuales.

La decision comercial se basa en:

- seller esperado;
- precio;
- disponibilidad;
- presencia/no presencia en el marketplace.

## Como ejecutar

Ruta del proyecto:

```text
C:\Users\Usuario\Desktop\IT\ScraperV2
```

Arranque recomendado:

```bat
launch_dashboard.bat
```

Alternativa:

```powershell
python .\dashboard_leroy_modern.py
```

Acceso directo creado en escritorio:

```text
C:\Users\Usuario\Desktop\Nass Offer Checker.lnk
```

## Configuracion local no versionada

Archivo privado:

```text
local_settings.json
```

Contiene:

- URL viva de Shoppingfeed;
- webhook Slack;
- activacion/cooldown de alertas;
- configuracion local por worker.

No imprimir ni commitear este archivo.

Plantilla versionada:

```text
local_settings.example.json
```

## Estado implementado

- Dashboard moderno en `dashboard_leroy_modern.py`.
- Logica de scraping y clasificacion en `dashboard_leroy.py`.
- Entrada manual por EAN.
- CSV manual.
- Catalogo vivo desde Shoppingfeed.
- Cache diferencial SQLite en `fase1/offer_cache.sqlite`.
- Saltar productos con stock feed `<= 0`.
- Semaforos:
  - verde: correcto;
  - amarillo: revisar, perdida buybox o no disponible teniendo stock;
  - rojo: fuera, sin stock o no vendido;
  - gris: tecnico/challenge/timeout/incierto.
- Tarjetas de semaforo clicables para filtrar resultados.
- Boton y `Ctrl+C` para copiar EAN seleccionado.
- Chromium minimizado.
- Modo datos minimos para reducir carga de assets.
- Alertas Slack ante senales tecnicas.
- Fase 3 con hasta 10 workers.
- Cola compartida: cada worker toma el siguiente producto pendiente; no se duplican productos entre workers.
- Circuit breaker global por senales tecnicas consecutivas.
- Configuracion local por worker leida y mostrada en UI:
  - `enabled`;
  - proxy configurado si/no;
  - User-Agent propio si/no.

## Punto exacto pendiente

El texto superior que puede decir `Worker 1 activo` es solo el ultimo evento recibido por la UI, no un resumen global.

El estado real esta en los chips inferiores de workers, por ejemplo:

```text
W1 activo | P:no | UA:def
W2 activo | P:no | UA:def
```

Pendiente recomendado:

- Cambiar ese subtitulo por un resumen agregado, por ejemplo `2 workers activos`.
- Mantener `Salida: ...` separado del estado de workers.

## Fase 3 siguiente

Orden recomendado:

1. Corregir UI de resumen de workers.
2. Warm-up por worker:
   - abrir home;
   - comprobar challenge;
   - marcar worker como sano o bloqueado;
   - solo workers sanos consumen cola.
3. Pausa individual:
   - si un worker recibe captcha/DataDome/challenge, pausarlo sin cerrar todos inmediatamente.
4. Corte global:
   - si varios workers fallan o hay racha tecnica, parar lote.
5. Aplicar proxy/User-Agent por worker en Playwright:
   - usar solo proxies estables/autorizados;
   - User-Agent persistente por worker;
   - no rotar por request.

## Observaciones de bloqueo

Prueba reciente con varios workers:

- No fue un crash de la app.
- Los workers recibieron respuestas DataDome/challenge.
- El circuit breaker corto el lote tras la racha tecnica.
- Con muchos workers en la misma IP/perfiles nuevos aumenta el riesgo de challenge.

## Git

Remoto:

```text
https://github.com/isma123nassif/NassOfferchecker.git
```

Rama:

```text
main
```

Antes de commitear:

```powershell
git status --short
```

Comprobar que no aparecen:

- `local_settings.json`;
- webhooks reales;
- cookies/storage;
- perfiles Chromium;
- CSVs completos del feed;
- outputs de ejecucion.

