"""Avisos de LinkedIn desde los correos de alertas que LinkedIn le envía a la persona.

No se consulta ninguna página de LinkedIn: todo sale del texto del correo (cargo,
empresa, ubicación y enlace). Una tarea programada lee los correos nuevos con acceso
a Gmail y los guarda con:

    python -m buscador.correo_linkedin agregar CORREOS.json

donde CORREOS.json es una lista de {"fecha": "<ISO del correo>", "texto": "<cuerpo en texto>"}.
Los correos no se guardan: solo cargo, empresa, ubicación, enlace limpio y fecha.

El chequeo horario incorpora docs/data/importados.json como fuente "linkedin".
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .comun import Aviso, limpio

RAIZ = Path(__file__).resolve().parent.parent
IMPORTADOS = RAIZ / "docs" / "data" / "importados.json"
DIAS_RETENCION = 30
_VER = re.compile(r"https?://(?:[a-z]+\.)?linkedin\.com/(?:comm/)?jobs/view/(\d+)")
_RUIDO = re.compile(r"^(solicitar|ver anuncio|ver todos|empleos de|amplía|recomendaciones|\d+ (antiguos|ex)|"
                    r"hace |tu perfil|coincide|en busca activa|alumni|promocionado|---)", re.I)


def parsear(texto: str, fecha: str) -> list[dict]:
    """Extrae los avisos de un correo de LinkedIn en texto plano. Cada aviso es un
    bloque: cargo, empresa, ubicación (líneas antes de "Ver anuncio de empleo: URL")."""
    out, vistos = [], set()
    lineas = [limpio(x) for x in (texto or "").splitlines()]
    for i, linea in enumerate(lineas):
        m = _VER.search(linea)
        if not m or m.group(1) in vistos:
            continue
        previas = []
        for x in reversed(lineas[max(0, i - 8): i]):
            if not x or x.startswith("---") or "http" in x:
                if previas:
                    break
                continue
            if _RUIDO.match(x):
                continue
            previas.append(x)
        previas.reverse()
        if not previas:
            continue
        vistos.add(m.group(1))
        titulo = previas[0]
        empresa = previas[1] if len(previas) > 1 else ""
        ubic = previas[2] if len(previas) > 2 else ""
        if re.fullmatch(r"\d{5,}", ubic):  # a veces LinkedIn pone un código en vez del lugar
            ubic = ""
        out.append({"id_linkedin": m.group(1), "titulo": titulo, "empresa": empresa, "ubicacion": ubic,
                    "url": f"https://www.linkedin.com/jobs/view/{m.group(1)}/", "fecha_correo": fecha})
    return out


def cargar() -> dict:
    try:
        d = json.loads(IMPORTADOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("avisos", [])
    return d


def agregar(nuevos: list[dict], ahora: str) -> int:
    d = cargar()
    por_id = {a["id_linkedin"]: a for a in d["avisos"]}
    antes = len(por_id)
    for a in nuevos:
        por_id.setdefault(a["id_linkedin"], a)
    limite = (datetime.fromisoformat(ahora) - timedelta(days=DIAS_RETENCION)).isoformat()
    d["avisos"] = sorted((a for a in por_id.values() if a["fecha_correo"] >= limite),
                         key=lambda a: a["fecha_correo"], reverse=True)
    d["actualizado"] = ahora
    IMPORTADOS.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(por_id) - antes


def lector(s, palabra: str) -> list[Aviso]:
    """Fuente "linkedin" del chequeo: los avisos importados desde los correos."""
    return [
        Aviso(sitio="linkedin_correo", titulo=a["titulo"], url=a["url"], empresa=a.get("empresa", ""),
              ubicacion=a.get("ubicacion", ""), publicado=a["fecha_correo"])
        for a in cargar()["avisos"]
    ]


lector.sin_palabras = True  # no busca por palabra clave: se lee una vez por chequeo


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "agregar":
        avisos = []
        for c in json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")):
            avisos += parsear(c["texto"], c["fecha"])
        n = agregar(avisos, datetime.now(timezone.utc).replace(microsecond=0).isoformat())
        print(f"{len(avisos)} avisos en los correos, {n} nuevos importados")
    else:
        print(__doc__)
