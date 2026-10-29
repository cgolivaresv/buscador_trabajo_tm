"""Marcas que hace la persona desde la página (visto, postulé, descartado…).

La página guarda las marcas en docs/data/marcas.json, mediante la API de GitHub. El
buscador solo las LEE (nunca escribe ese archivo, para no chocar con la página) y las
usa para:
  - no notificar avisos de empresas descartadas,
  - no notificar republicaciones (mismo cargo y empresa) de avisos descartados,
  - conservar en el historial los avisos en proceso de postulación,
  - recordar hacer seguimiento a postulaciones sin cambios en DIAS_SEGUIMIENTO días.

Formato de marcas.json:
  {"avisos": {"<id>": {"estado": "postule", "cambio": "<ISO>", "nota": "...",
                       "titulo": "...", "empresa": "...", "url": "...",
                       "historial": [{"estado": "...", "fecha": "<ISO>"}]}},
   "empresas_descartadas": ["Nombre empresa", ...]}
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .comun import normalizar

EN_PROCESO = {"postule", "entrevista", "oferta"}
DIAS_SEGUIMIENTO = 7
ETAPA = {"postule": "postulaste", "entrevista": "tuviste la entrevista", "oferta": "recibiste la oferta"}


def cargar(ruta: Path) -> dict:
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("avisos", {})
    d.setdefault("empresas_descartadas", [])
    return d


def empresa_descartada(empresa: str, marcas: dict) -> bool:
    e = normalizar(empresa)
    return bool(e) and any(normalizar(x) == e for x in marcas["empresas_descartadas"])


def firmas_descartadas(marcas: dict, firma) -> set[str]:
    """Firmas (cargo + empresa) de los avisos que la persona descartó."""
    out = set()
    for m in marcas["avisos"].values():
        if m.get("estado") == "descartado":
            f = firma({"titulo": m.get("titulo", ""), "empresa": m.get("empresa", "")})
            if f:
                out.add(f)
    return out


def seguimiento(marcas: dict, ruta_rec: Path, t: str) -> list[dict]:
    """Acciones de issue para postulaciones sin cambios hace DIAS_SEGUIMIENTO días.
    Se recuerda una vez por aviso y etapa; ruta_rec guarda lo ya recordado."""
    try:
        hechos = json.loads(ruta_rec.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hechos = {}
    ahora = datetime.fromisoformat(t)
    acciones = []
    for aid, m in marcas["avisos"].items():
        est, cambio = m.get("estado"), m.get("cambio")
        clave = f"{aid}:{est}"
        if est not in EN_PROCESO or not cambio or clave in hechos:
            continue
        try:
            dias = (ahora - datetime.fromisoformat(cambio.replace("Z", "+00:00"))).days
        except ValueError:
            continue
        if dias < DIAS_SEGUIMIENTO:
            continue
        hechos[clave] = t
        nombre = m.get("titulo") or "un aviso"
        empresa = f" ({m['empresa']})" if m.get("empresa") else ""
        cuerpo = [f"Hace {dias} días que {ETAPA[est]} a **{nombre}**{empresa} y no has registrado cambios."]
        if m.get("url"):
            cuerpo.append(f"\nAviso: {m['url']}")
        if m.get("nota"):
            cuerpo.append(f"\nTu nota: {m['nota']}")
        cuerpo.append(
            "\nSugerencia: escribe o llama para preguntar en qué etapa va el proceso. "
            "Si hay novedades, actualiza la etapa en la página (Entrevista, Oferta o Descartar)."
        )
        acciones.append({"accion": "abrir", "titulo": f"📌 Seguimiento: {nombre}{empresa}", "cuerpo": "\n".join(cuerpo)})
    ruta_rec.write_text(json.dumps(hechos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return acciones
