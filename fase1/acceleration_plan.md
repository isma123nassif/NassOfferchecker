# Aceleracion del checkeo

## Cuello de botella actual

La prueba validada usa navegador real, un delay de 10 segundos entre EANs, espera `networkidle` y guarda HTML, screenshot y cookies redactadas por cada producto.

Eso es robusto para PoC, pero lento para operacion diaria.

## Modo rapido recomendado

```powershell
python .\fase1\run_playwright_bootstrap.py --ean-file .\Referencias.csv --limit 0 --delay 2 --bootstrap-home --wait-solved 120 --timeout 45 --networkidle-timeout 0 --skip-screenshot --skip-cookies
```

Cambios:

- `--delay 2`: reduce la pausa entre productos.
- `--networkidle-timeout 0`: no espera a que terminen todos los trackers/recursos secundarios.
- `--skip-screenshot`: no captura imagen en checks normales.
- `--skip-cookies`: no exporta cookies redactadas en checks normales.

Mantiene:

- perfil dedicado;
- HTML renderizado;
- EAN;
- disponibilidad;
- `VIVA`, `NO_VIVA`, `INCIERTA`;
- evidencia HTML por EAN.

## Medicion real

Prueba con 5 EANs:

- modo auditoria anterior: aproximadamente 57 segundos;
- modo rapido: aproximadamente 12 segundos;
- clasificacion mantenida: 4 `VIVA`, 1 `NO_VIVA`;
- challenge: 0.

## Modo auditoria

Para revisar cambios de estado o falsos positivos:

```powershell
python .\fase1\run_playwright_bootstrap.py --ean-file .\Referencias.csv --limit 0 --delay 10 --bootstrap-home --wait-solved 600 --timeout 90
```

Este modo conserva screenshots y cookies redactadas.

## Siguiente mejora

Usar cache de URL por EAN.

Una vez detectada la URL de producto:

- revisar URL directa en vez de buscar por EAN cada vez;
- usar busqueda por EAN solo si la URL falla, redirige o desaparece;
- esto reduce redirecciones y ambiguedad.

## Paralelismo

No empezar con paralelismo alto. Si hace falta, probar:

- concurrencia 2;
- delay con jitter;
- pausar automaticamente si aparece `challenge_detected=true`.

Mas concurrencia puede aumentar falsos `INCIERTA` por proteccion.
