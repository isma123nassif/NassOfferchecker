# Diagnostico de bloqueo Leroy Merlin / DataDome

Fecha: 2026-07-29

## Sintoma observado

URL aportada:

```text
https://www.leroymerlin.es/productos/?msockid=308ade457d9a65390e14c9577c7664bc
```

Durante el check completo del feed Shoppingfeed:

- la sesion dedicada de Playwright funciono correctamente durante cientos de EANs;
- el primer tramo completo llego a `1675 / 1749` EANs;
- a partir de cierto punto aparecieron challenges persistentes;
- cambiar de IP, navegador o sesion no garantiza desbloqueo inmediato.

## Resultado medido

Primer tramo:

```text
1675 EANs en 2567.9 segundos
velocidad limpia aproximada: 1.53 segundos/EAN
```

Estados primer tramo:

```text
VIVA: 1311
NO_VIVA: 363
NO_ENCONTRADA_PRELIMINAR: 1
```

Consolidado parcial tras reintento:

```text
checkeados: 1718 / 1749
pendientes: 31
VIVA: 1345
NO_VIVA: 369
INCIERTA: 3
NO_ENCONTRADA_PRELIMINAR: 1
```

## Como se produce probablemente el bloqueo

DataDome no decide solo por IP o cookie. Segun su documentacion, combina senales server-side y client-side:

- IP, reputacion y origen geografico.
- Cabeceras HTTP.
- Fingerprint TLS/JA3/JA4 cuando esta disponible.
- Fingerprint de navegador y dispositivo.
- Ejecucion de JavaScript.
- Cookies y storage propios, como `datadome`.
- Comportamiento y ritmo de navegacion.
- Patrones repetitivos de acceso.

Fuentes oficiales:

- https://docs.datadome.co/docs/device-check
- https://docs.datadome.co/reference/validate-request
- https://docs.datadome.co/docs/threat-detection
- https://docs.datadome.co/docs/cookie-session-storage
- https://docs.datadome.co/docs/bot-authentication

## Por que cambiar de IP/navegador/sesion puede no bastar

Cambiar una sola pieza no reinicia necesariamente la evaluacion:

- Una IP nueva puede tener mala reputacion o parecer proxy/VPN.
- Un perfil nuevo sin historial puede ser mas sospechoso que uno persistente.
- El `datadome` cookie esta cifrado y ligado a contexto; copiarlo fuera de contexto puede no funcionar.
- La cadencia de cientos o miles de busquedas EAN consecutivas no se parece a navegacion humana normal.
- Un challenge reciente puede elevar la sensibilidad temporalmente.

## Sobre `msockid`

`msockid` parece un parametro de tracking asociado a enlaces de Microsoft/Bing. No debe usarse como base del scraper.

Recomendacion:

- usar URLs limpias;
- quitar parametros no necesarios;
- preferir `https://www.leroymerlin.es/search?q=<EAN>` o URL de producto canonica.

## Soluciones operativas recomendadas

### 1. Dividir en lotes

No ejecutar `1749` busquedas seguidas.

Configuracion inicial:

```text
lotes de 100-200 EANs
delay: 2-5 segundos
cooldown entre lotes: 10-30 minutos
```

Si aparecen challenges consecutivos:

```text
parar lote
guardar pendientes
reanudar mas tarde
```

### 2. Cachear URL por EAN

La busqueda por EAN es mas cara y repetitiva que abrir la URL canonica.

Flujo recomendado:

```text
1. Si EAN tiene URL cacheada, abrir URL directa.
2. Validar EAN + disponibilidad en PDP.
3. Si URL falla, redirige o no contiene EAN, usar busqueda por EAN.
4. Actualizar cache.
```

Esto reduce:

- numero de busquedas;
- redirecciones;
- paginas de resultados;
- ambiguedad;
- probabilidad de challenge.

### 3. Evidencia selectiva

Modo normal:

```text
guardar CSV + HTML solo para NO_VIVA / INCIERTA
sin screenshots
sin cookies
```

Modo auditoria:

```text
guardar HTML + screenshot + cookies redactadas
solo cuando haya cambio de estado o falso positivo
```

### 4. Sesion dedicada persistente

Mantener:

- `fase1/browser_profile_leroy/`
- resolucion manual cuando aparezca challenge;
- no usar perfil personal de Edge;
- no extraer cookies personales.

### 5. Via oficial

Para produccion robusta:

- pedir acceso/whitelist/API a Leroy Merlin si el objetivo es monitorizar ofertas propias;
- explorar canal oficial de marketplace/seller;
- usar identificacion de agente autorizada si Leroy/DataDome lo admite.

DataDome documenta mecanismos de autenticacion de bots/agentes mediante User-Agent dedicado y mecanismos de verificacion.

## Decision tecnica

El enfoque actual funciona, pero no debe ejecutarse como una sola tirada enorme.

Siguiente paso tecnico:

- implementar cache `ean -> url`;
- implementar lotes reanudables;
- parar automaticamente tras N challenges consecutivos;
- generar CSV de pendientes sin esperar 120s por cada challenge repetido.
