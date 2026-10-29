# Versiones

La versión aparece al pie de la página: **Página** es la versión de `docs/index.html` y **Buscador** la del script que hizo el último chequeo (`buscador/__init__.py`). Cada cambio sube el número en ambos lados.

## 1.8.0 · 2026-10-29
- Se registra, por palabra clave y por sitio, cada aviso encontrado y si resultó útil (afín o prioritario) o se descartó, en `docs/data/estadisticas.json`. Sirve para medir qué palabras aportan avisos útiles.

## 1.7.0 · 2026-10-29
- Palabras clave basadas en el CV: resonancia, imagenología, scanner, radiología, especialista de aplicaciones, coordinación y jefatura de imagenología.
- Perfil objetivo: cada aviso se clasifica como ⭐ prioritario (resonancia) o afín (imagenología, TC, radiología, fabricantes de equipos). Con `solo_afines: true` se descarta el resto. La página los ordena primero y tiene la pestaña "Prioritarios"; el issue también los marca.
- Zona de interés de Santiago a Valdivia (RM, O'Higgins, Maule, Ñuble, Biobío, Araucanía y Los Ríos). Los avisos que solo indican comuna o "Chile" se mantienen.
- La configuración se vuelve a aplicar al historial en cada chequeo, y los datos de cada aviso se refrescan con lo último que muestra el sitio.
- Computrabajo: la ubicación ya no se confunde con la nota de la empresa ("4,2").
- Las ciudades fuera de zona también se detectan en el título ("…para Calama").
- Los fabricantes de equipos (Siemens, GE, Philips…) cuentan como afines solo para cargos técnico-clínicos.
- Nuevas exclusiones: técnico en imagen*, técnico radiólogo, administrativ*, ginecolog*.

## 1.6.0 · 2026-10-29
- Palabras clave definitivas (8 términos en 4 grupos: resonancia, imagenología y TC, especialista de aplicaciones, jefatura).
- Exclusiones: TENS, técnico en enfermería, auxiliar, laboratorio, banco de sangre, oftalmología, otorrino. Se comparan por palabra completa ("TENS" ya no descarta "intensivo"), aceptan * como prefijo y también limpian el historial.

## 1.5.0 · 2026-10-29
- Chequeo cada hora entre 7:00 y 22:00 hora de Chile (antes cada 2 horas, día y noche). Se ajusta solo al horario de verano e invierno.

## 1.4.0 · 2026-10-29
- Nuevo sitio: Indeed Chile (cl.indeed.com), mediante la librería JobSpy.
- Trabajando.cl: si el servicio JSON no trae ofertas, se buscan en el sitemap de ofertas vigentes (últimos 30 días); si tampoco hay, en la página de búsqueda. Cuando todo falla, la página muestra qué se intentó.

## 1.3.0 · 2026-10-29
- La página ya no hace scroll: encabezado, filtros y pie quedan fijos y solo se desplaza la lista de avisos.
- "Qué se está buscando" se puede plegar; parte abierto solo en pantallas grandes.

## 1.2.0 · 2026-10-29
- Número de versión al pie de la página.

## 1.1.0 · 2026-10-29
- Trabajando.cl: los avisos se leen desde su servicio JSON interno.
- Diagnóstico manual para Trabajando.cl (Actions → Diagnóstico Trabajando).

## 1.0.0 · 2026-10-29
- Primera versión: LinkedIn, Computrabajo, Chiletrabajos y Trabajando.cl cada 2 horas, página en GitHub Pages e issue con los avisos nuevos.
