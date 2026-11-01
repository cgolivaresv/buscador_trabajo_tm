# Versiones

La versión aparece al pie de la página: **Página** es la versión de `docs/index.html` y **Buscador** la del script que hizo el último chequeo (`buscador/__init__.py`). Cada cambio sube el número en ambos lados.

## 1.15.0 · 2026-10-29
- Antigüedad máxima de 48 horas al encontrar un aviso (`antiguedad_maxima_horas`). LinkedIn y Trabajando filtran a 48 h al buscar; Indeed y Google, a su opción más cercana; en todas las fuentes se revisa además la fecha de publicación ("Hace 3 días", "13 de octubre", "2026-10-28"…). Los avisos sin fecha reconocible se admiten.
- Un aviso admitido no desaparece al cumplir 48 horas: sigue visible mientras esté abierto.

## 1.20.0 · 2026-11-01
- Nueva fuente: Bolsa Nacional de Empleo (BNE, SENCE), mediante su búsqueda pública. Trae cargo, empresa, comuna y región, rango de renta, jornada, fecha y descripción. Ahí publican hospitales, Servicios de Salud y centros vía OMIL.

## 1.19.0 · 2026-11-01
- Descripción completa: se lee la ficha de cada aviso nuevo (hasta 20 por chequeo, respetando el robots.txt de cada sitio) con Trafilatura o los datos estructurados del aviso. Si la descripción menciona resonancia, un aviso de título genérico pasa a ⭐ prioritario ("por descripción"). También completa renta, jornada, contrato y fecha de cierre. La tarjeta muestra la descripción.
- Chiletrabajos: barrido completo cada 4 horas con su RSS público (todos los avisos del sitio, con fecha exacta); en los demás chequeos, la búsqueda normal. El feed pesa ~19 MB, por eso no se descarga cada hora.
- LinkedIn desactivado: su robots.txt prohíbe el acceso automatizado sin permiso, y no había aportado avisos que pasaran el perfil y la zona.

## 1.18.0 · 2026-10-30
Revisión de integridad: desde el 29-oct 18:54 no entraba ningún aviso nuevo.
- Trabajando.cl: los avisos se piden ordenados por fecha de publicación (antes, por relevancia: siempre los mismos, algunos de septiembre).
- Chiletrabajos: no encuentra frases de 3 palabras y mostraba su listado general (choferes, guardias…). Se agrega la palabra clave amplia "tecnólogo médico", que sí trae avisos frescos aquí y en Computrabajo; el perfil filtra el resto. Además, ahora se lee la fecha de cada aviso.
- Perfil: "Tecnólogo/a Médico/a" y "Tecnólogo(a) Médico(a)" ahora calzan con "tecnólogo médico" (antes se descartaban por el "/a").

## 1.17.1 · 2026-10-30
- Google Empleos desactivado: desde los servidores de GitHub responde sin el panel de empleos (0 resultados en todos los chequeos del 29 y 30 de octubre).

## 1.17.0 · 2026-10-30
- Celular: desliza un aviso hacia la izquierda para descartarlo al instante. Aparece "Aviso descartado · Deshacer" por 6 segundos. El desplazamiento vertical de la lista sigue funcionando normal.
- Al descartar desde la tarjeta (Descartar o Descartar empresa), la tarjeta se cierra sola; en el computador se pasa al siguiente aviso de la cola.
- "RM" ya no marca un aviso como prioritario: en los títulos suele significar Región Metropolitana (por ejemplo, un aviso de kinesiólogos). Siguen siendo prioritarios resonancia, resonador, RMN, MRI y MR.

## 1.16.0 · 2026-10-29
- Panel de fuentes: el número es ahora cuántos avisos de esa fuente hay en tu lista (antes era lo que trajo el sitio, aunque se descartara todo). Al pasar el cursor se ven los resultados del sitio y por qué se descartaron.
- El buscador registra por fuente los descartes por motivo (perfil, zona, exclusión, empresa descartada, antigüedad) y una muestra de títulos descartados. Si filtras por una fuente sin avisos, la página explica por qué y muestra ejemplos.
- El filtro por fuente incluye los avisos que también aparecen en ella ("También en…").

## 1.15.1 · 2026-10-29
- El límite de 48 horas solo se aplica a los avisos nuevos: los ya guardados no se borran por antigüedad, tengan o no alguna marca.

## 1.14.1 · 2026-10-29
- Google Empleos: la consulta usa el formato que espera JobSpy ("… jobs near Chile in the last week"). Si falla, el error indica si Google bloqueó la consulta o pidió aceptar cookies.
- Trabajando.cl: una búsqueda sin avisos ya no se muestra como error.

## 1.14.0 · 2026-10-29
- Seguimiento de postulaciones: etapas Postulé, Entrevista y Oferta (vista "En proceso"), nota por aviso e historial de cambios con fecha.
- Sincronización entre dispositivos: las marcas se guardan en `docs/data/marcas.json` del repositorio, mediante un token de GitHub que se conecta una vez por dispositivo (botón en la barra inferior). Sin token, la página funciona igual y guarda las marcas en el navegador; al conectar, se suben.
- "Descartar empresa": deja de mostrar y notificar avisos de esa empresa; se puede restaurar desde el panel Programa.
- El buscador usa las marcas: no notifica republicaciones (mismo cargo y empresa) de avisos descartados, conserva los avisos en proceso aunque ya no aparezcan en los sitios, y abre un issue "📌 Seguimiento" cuando una postulación lleva 7 días sin cambios.

## 1.13.0 · 2026-10-29
- Cada palabra clave con tildes se busca también sin tildes ("tecnologo medico") en Computrabajo, Chiletrabajos, Trabajando.cl y Laborum, por si su buscador las distingue. Configurable en `sin_tildes_en`. En LinkedIn, Indeed y Google no se duplica, porque ya ignoran las tildes.

## 1.12.0 · 2026-10-29
- Nueva interfaz estilo consola de resonancia: tonos negros, grises y naranjo. Barra superior de estado (último chequeo, nuevos, zona, fuentes activas y hora), panel "Programa" con vistas, fuentes, palabras clave y páginas vigiladas, "Cola de avisos" al centro y "Tarjeta del aviso" con sus parámetros a la derecha, más barra de estado con las versiones.
- Se navega la cola con las flechas del teclado; Enter o doble clic abren el aviso. Clic en una fuente filtra por ella.
- En tablet y celular la tarjeta se abre como hoja lateral; en celular, las vistas quedan en una franja deslizable y el resto del programa se despliega con el botón "Programa".

## 1.11.0 · 2026-10-29
- Alerta de salud: si un sitio pasa 24 horas sin entregar avisos, se abre un issue "⚠️ Buscador: …" con los errores; se cierra solo cuando el sitio se recupera.
- Pruebas automáticas (26, sin conexión) que corren en cada cambio del código (Actions → Pruebas).
- Nuevo sitio: Google Empleos, vía JobSpy (reúne avisos de portales menores y páginas propias de empresas).
- Vigilancia de páginas: lista `vigilar` en config.yml con páginas de "trabaja con nosotros"; si cambian, se abre un issue con el texto nuevo. Respeta el robots.txt de cada sitio. Se muestran en "Qué se está buscando".

## 1.10.0 · 2026-10-29
- Nuevo sitio: Laborum (laborum.cl), mediante la misma API que usa su buscador.
- Empleos Públicos: su robots.txt no permite revisión automática del servicio de avisos, así que no se incluye; la página tiene un acceso directo al portal.
- Diagnóstico de fuentes generalizado (Actions → Diagnóstico de fuentes).

## 1.9.0 · 2026-10-29
- Detalle del aviso cuando el sitio lo muestra: renta, jornada (part time, turnos 7x7…), tipo de contrato (reemplazo, indefinido…) y fecha de cierre.
- Duplicados entre sitios: el mismo aviso (mismo cargo y empresa) publicado en varios portales aparece una sola vez, con enlaces "También en…". Sin empresa conocida no se agrupa, para no juntar avisos distintos.
- Avisos cerrados: si pasó la fecha de cierre, se mueven a la pestaña "Cerrados". Si un aviso no aparece en las búsquedas hace 4 días o más, se indica y se muestra al final (puede seguir abierto: algunos sitios solo muestran avisos recientes).
- El issue de avisos nuevos omite duplicados e incluye renta, jornada y los otros sitios donde aparece.

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
