# Buscador de Trabajo TM

Revisa cada hora, de 7:00 a 22:00 (hora de Chile), los avisos de **LinkedIn, Computrabajo, Chiletrabajos, Trabajando.cl e Indeed** según tus palabras clave, guarda los nuevos y te los muestra en una página.

## Cómo funciona

1. **GitHub Actions** ejecuta `python -m buscador` cada hora entre 7:00 y 22:00 (`.github/workflows/buscar.yml`).
2. El script busca cada palabra clave en cada sitio, descarta duplicados y guarda el historial en `docs/data/avisos.json`.
3. Si hay avisos nuevos, abre un **issue** con la lista (GitHub te avisa por correo).
4. La página en **GitHub Pages** (`docs/index.html`) muestra los avisos con filtros y estados: nuevo, visto, postulé, descartado.

En el primer chequeo todo lo encontrado se guarda como base, sin abrir issue, para no llenarte de avisos antiguos.

## Configurar

Todo se ajusta en [`config.yml`](config.yml), editándolo directo en GitHub:

| Campo | Para qué sirve |
|---|---|
| `palabras_clave` | Términos que se buscan en cada sitio |
| `perfil` | Términos que marcan un aviso como ⭐ prioritario o afín |
| `solo_afines` | Descartar los avisos que no calzan con el perfil |
| `excluir` | Términos que, si aparecen en el título, descartan el aviso |
| `ubicaciones` / `ubicaciones_excluir` | Zonas aceptadas y zonas descartadas (vacío = todo Chile) |
| `sitios` | Activar o desactivar cada portal |
| `notificar_issue` | Abrir un issue cuando haya avisos nuevos |
| `dias_retencion` | Días sin ver un aviso antes de borrarlo del historial |

## Puesta en marcha (una sola vez)

1. **Activar Pages:** Settings → Pages → *Build and deployment* → Source: *Deploy from a branch* → Branch: `main`, carpeta `/docs` → Save.
2. **Permitir que Actions guarde resultados:** Settings → Actions → General → *Workflow permissions* → *Read and write permissions* → Save.
3. **Primer chequeo:** pestaña Actions → *Buscar avisos* → *Run workflow*.
4. **Correos:** asegúrate de estar en *Watch* del repositorio para recibir los issues.

## Revisar si un sitio falla

La página muestra cuántos resultados trajo cada sitio en el último chequeo y los errores, si los hubo. El detalle completo queda en `docs/data/estado.json` y en el registro de cada ejecución en Actions. Los portales cambian su HTML de vez en cuando; cada lector está en `buscador/sitios.py`.

LinkedIn limita bastante la lectura automática, así que puede fallar a ratos. Como respaldo, sus alertas de empleo por correo son lo más confiable.

## Correr en tu computador

```bash
pip install -r requirements.txt
python -m buscador
```
