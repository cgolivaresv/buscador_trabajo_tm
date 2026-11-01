"""Descripción completa de los avisos: baja la ficha de cada aviso y extrae su texto.

Sirve para:
  - marcar como ⭐ prioritario un aviso de título genérico ("Tecnólogo Médico") cuya
    descripción menciona resonancia,
  - completar renta, jornada, contrato y fecha de cierre que el listado no mostraba,
  - mostrar el texto en la tarjeta del aviso.

Respeta el robots.txt de cada sitio y tiene un tope de fichas por chequeo, para no
cargar los sitios. Cada aviso se intenta una sola vez.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .comun import USER_AGENT, json_ld_ofertas, limpio, normalizar, obtener, detalle_desde_texto

MAX_POR_CHEQUEO = 20
MAX_FALLAS = 3
LARGO_GUARDADO = 1800
_robots: dict[str, RobotFileParser] = {}


def _permitido(s, url: str) -> bool:
    p = urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = RobotFileParser()
        try:
            r = s.get(base + "/robots.txt", timeout=15)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots[base] = rp
    return _robots[base].can_fetch(USER_AGENT, url)


def extraer(html: str) -> tuple[str, dict]:
    """Texto principal de la ficha y datos estructurados (si la página trae JSON-LD)."""
    extra: dict = {}
    texto = ""
    ld = json_ld_ofertas(html)
    if ld:
        o = ld[0]
        desc = o.get("description") or ""
        if desc:
            texto = re.sub(r"<[^>]+>", " ", desc)
        if o.get("validThrough"):
            extra["cierre"] = str(o["validThrough"])[:10]
    if len(texto) < 200:
        try:
            import trafilatura

            texto = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True) or texto
        except Exception:
            pass
    texto = re.sub(r"[ \t]+", " ", texto or "")
    texto = re.sub(r"\n\s*\n+", "\n", texto).strip()
    return texto, extra


def enriquecer(s, historial: dict[str, dict], prioridad: list[str], patrones_prio: list[re.Pattern], t: str) -> dict:
    """Baja la descripción de hasta MAX_POR_CHEQUEO avisos: primero los de "prioridad"
    (los nuevos de este chequeo), después los guardados que aún no la tienen."""
    orden = [k for k in prioridad if k in historial]
    orden += [k for k, v in historial.items() if k not in orden and "descripcion" not in v
              and "descripcion_error" not in v and v.get("descripcion_fallas", 0) < MAX_FALLAS]
    res = {"leidas": 0, "sin_permiso": 0, "errores": 0, "subieron_a_prioritario": 0}
    for k in orden:
        if res["leidas"] + res["errores"] >= MAX_POR_CHEQUEO:
            break
        a = historial[k]
        if a.get("descripcion") or a.get("descripcion_error") or a.get("duplicado_de") \
                or a.get("descripcion_fallas", 0) >= MAX_FALLAS:
            continue
        a["descripcion_intento"] = t
        if not _permitido(s, a["url"]):
            a["descripcion_error"] = "el sitio no permite leer la ficha (robots.txt)"
            res["sin_permiso"] += 1
            continue
        try:
            texto, extra = extraer(obtener(s, a["url"]).text)
        except Exception as e:
            # Error pasajero (red, sitio caído): se reintenta en próximos chequeos.
            a["descripcion_fallas"] = a.get("descripcion_fallas", 0) + 1
            if a["descripcion_fallas"] >= MAX_FALLAS:
                a["descripcion_error"] = f"no se pudo leer la ficha ({type(e).__name__})"
            res["errores"] += 1
            continue
        res["leidas"] += 1
        if not texto:
            a["descripcion_error"] = "la ficha no tiene texto legible"
            continue
        a["descripcion"] = texto[:LARGO_GUARDADO]
        for campo, valor in {**detalle_desde_texto(texto[:4000]), **extra}.items():
            if valor and not a.get(campo):
                a[campo] = valor
        if a.get("afinidad") == 2 and any(p.search(normalizar(texto)) for p in patrones_prio):
            a["afinidad"] = 3
            a["prioridad_por_descripcion"] = True
            res["subieron_a_prioritario"] += 1
    return res


def resumen(texto: str, n: int = 220) -> str:
    t = limpio(texto)
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"
