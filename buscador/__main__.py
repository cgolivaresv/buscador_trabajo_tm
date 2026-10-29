"""Ejecuta un chequeo completo: busca, filtra, fusiona con el historial y guarda.

Uso:  python -m buscador [--nuevos ARCHIVO.md]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import __version__
from .comun import fecha_publicacion, normalizar, sesion
from . import sitios as _sitios
from .sitios import LECTORES
from . import marcas, salud, vigilancia

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "docs" / "data"
AVISOS = DATOS / "avisos.json"
ESTADO = DATOS / "estado.json"
ESTADISTICAS = DATOS / "estadisticas.json"
SALUD = DATOS / "salud.json"
VIGILANCIA = DATOS / "vigilancia.json"
MARCAS = DATOS / "marcas.json"
RECORDATORIOS = DATOS / "recordatorios.json"
NOMBRES = {
    "linkedin": "LinkedIn",
    "computrabajo": "Computrabajo",
    "chiletrabajos": "Chiletrabajos",
    "trabajando": "Trabajando.cl",
    "indeed": "Indeed",
    "google": "Google Empleos",
    "laborum": "Laborum",
}


def ahora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def cargar_config() -> dict:
    cfg = yaml.safe_load((RAIZ / "config.yml").read_text(encoding="utf-8")) or {}
    cfg.setdefault("palabras_clave", [])
    cfg.setdefault("excluir", [])
    cfg.setdefault("ubicaciones", [])
    cfg.setdefault("ubicaciones_excluir", [])
    cfg.setdefault("perfil", {})
    cfg.setdefault("solo_afines", False)
    cfg.setdefault("sitios", {k: True for k in LECTORES})
    cfg.setdefault("dias_retencion", 60)
    cfg.setdefault("sin_tildes_en", [])
    cfg.setdefault("antiguedad_maxima_horas", 0)
    cfg["_excluir"] = _patrones(cfg["excluir"])
    cfg["_zona_si"] = _patrones(cfg["ubicaciones"])
    cfg["_zona_no"] = _patrones(cfg["ubicaciones_excluir"])
    cfg["_prioritario"] = _patrones((cfg["perfil"] or {}).get("prioritario"))
    cfg["_afin"] = _patrones((cfg["perfil"] or {}).get("afin"))
    cfg["_empresas"] = _patrones((cfg["perfil"] or {}).get("empresas_del_rubro"))
    cfg["_cargos_empresa"] = _patrones((cfg["perfil"] or {}).get("cargos_en_esas_empresas"))
    return cfg


def _patron(termino: str) -> re.Pattern | None:
    """Palabra o frase completa; con * al final, cualquier palabra que empiece así."""
    t = normalizar(str(termino))
    if not t:
        return None
    prefijo = t.endswith("*")
    t = re.escape(t.rstrip("*").strip())
    return re.compile(rf"\b{t}" + ("" if prefijo else r"\b"))


def _patrones(lista) -> list[re.Pattern]:
    return [p for p in map(_patron, lista or []) if p]


def evaluar(titulo: str, ubicacion: str, empresa: str, cfg) -> int:
    """0 = se descarta; 1 = sin relación con el perfil; 2 = afín; 3 = prioritario."""
    return evaluar_con_motivo(titulo, ubicacion, empresa, cfg)[0]


def evaluar_con_motivo(titulo: str, ubicacion: str, empresa: str, cfg) -> tuple[int, str]:
    """Como evaluar(), y además el motivo cuando se descarta: exclusión, zona o perfil."""
    a = _evaluar(titulo, ubicacion, empresa, cfg)
    if a:
        return a, ""
    tit = normalizar(titulo)
    if any(p.search(tit) for p in cfg["_excluir"]):
        return 0, "exclusion"
    if _evaluar(titulo, "", empresa, cfg) or _evaluar("", ubicacion, empresa, cfg) == 0 and _fuera_de_zona(tit, ubicacion, cfg):
        return 0, "zona"
    return 0, "perfil"


def _fuera_de_zona(tit: str, ubicacion: str, cfg) -> bool:
    ub = normalizar(ubicacion)
    if re.fullmatch(r"[\d.,\s]*", ub):
        ub = ""
    return bool(cfg["_zona_si"]) and not (ub and any(p.search(ub) for p in cfg["_zona_si"])) and any(
        p.search(ub) or p.search(tit) for p in cfg["_zona_no"])


def _evaluar(titulo: str, ubicacion: str, empresa: str, cfg) -> int:
    tit = normalizar(titulo)
    if any(p.search(tit) for p in cfg["_excluir"]):
        return 0
    ub = normalizar(ubicacion)
    if re.fullmatch(r"[\d.,\s]*", ub):  # sin ubicación o con un dato que no lo es
        ub = ""
    # Zona: se acepta si la ubicación nombra una zona de interés; se descarta si la
    # ubicación o el título ("…para Calama") nombran una zona fuera de interés; si no
    # nombran ninguna conocida (p. ej. solo la comuna), se acepta.
    if cfg["_zona_si"] and not (ub and any(p.search(ub) for p in cfg["_zona_si"])):
        if any(p.search(ub) or p.search(tit) for p in cfg["_zona_no"]):
            return 0
    if any(p.search(tit) for p in cfg["_prioritario"]):
        return 3
    if any(p.search(tit) for p in cfg["_afin"]):
        return 2
    # Fabricantes de equipos: cuenta como afín solo si el cargo es técnico-clínico.
    if any(p.search(normalizar(empresa)) for p in cfg["_empresas"]) and any(
        p.search(tit) for p in cfg["_cargos_empresa"]
    ):
        return 2
    return 0 if cfg["solo_afines"] else 1


_GENERO = re.compile(r"\((?:a|as|o|os)\)|/(?:a|as|o|os)\b|\bo/a\b")
_SIN_EMPRESA = {"", "confidencial", "empresa confidencial", "importante empresa", "reservado"}


def firma(d: dict) -> str | None:
    """Clave para reconocer el mismo aviso en distintos sitios: título + empresa.
    Sin empresa conocida no se agrupa, para no juntar avisos distintos."""
    emp = normalizar(d.get("empresa"))
    emp = re.sub(r"\b(s\.?a\.?|spa|ltda|limitada|chile)\b|[^a-z0-9 ]", " ", emp)
    emp = re.sub(r"\s+", " ", emp).strip()
    if emp in _SIN_EMPRESA:
        return None
    tit = _GENERO.sub("", normalizar(d.get("titulo")))
    tit = re.sub(r"[^a-z0-9 ]", " ", tit)
    tit = re.sub(r"\s+", " ", tit).strip()
    return f"{tit}|{emp}" if tit else None


def agrupar_duplicados(historial: dict[str, dict]) -> None:
    """Marca como duplicado el mismo aviso publicado en otro sitio. Queda como principal
    el que se encontró primero; los demás se listan en su campo "tambien_en"."""
    grupos: dict[str, list[dict]] = {}
    for d in historial.values():
        d.pop("duplicado_de", None)
        d.pop("tambien_en", None)
        f = firma(d)
        if f:
            grupos.setdefault(f, []).append(d)
    for miembros in grupos.values():
        if len({m["sitio"] for m in miembros}) < 2:
            continue  # dentro de un mismo sitio pueden ser vacantes distintas
        miembros.sort(key=lambda m: m.get("encontrado", ""))
        principal = miembros[0]
        vistos = {principal["sitio"]}
        for m in miembros[1:]:
            m["duplicado_de"] = principal["id"]
            if m["sitio"] not in vistos:
                principal.setdefault("tambien_en", []).append({"sitio": m["sitio"], "url": m["url"]})
                vistos.add(m["sitio"])
            for k in ("renta", "jornada", "contrato", "cierre"):
                if m.get(k) and not principal.get(k):
                    principal[k] = m[k]


DIAS_SIN_VER = 4


def marcar_vigencia(historial: dict[str, dict], estado_sitios: dict, t: str) -> None:
    """vigente / sin_ver (no aparece hace DIAS_SIN_VER días o más) / cerrado (pasó la
    fecha de cierre). "sin_ver" no prueba que esté cerrado: las búsquedas de algunos
    sitios solo muestran avisos recientes. Si el sitio falló en este chequeo, no se marca."""
    ahora_dt = datetime.fromisoformat(t)
    hoy = ahora_dt.astimezone(timezone(timedelta(hours=-3))).date().isoformat()
    for d in historial.values():
        d["vigencia"], d["dias_sin_ver"] = "vigente", 0
        cierre = (d.get("cierre") or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cierre) and cierre < hoy:
            d["vigencia"] = "cerrado"
            continue
        sitio_ok = estado_sitios.get(d["sitio"], {}).get("resultados", 0) > 0
        dias = (ahora_dt - datetime.fromisoformat(d.get("visto_ultima_vez", t))).days
        if sitio_ok and dias >= DIAS_SIN_VER:
            d["vigencia"], d["dias_sin_ver"] = "sin_ver", dias


def sin_tildes(texto: str) -> str:
    """'tecnólogo médico' → 'tecnologo medico' (conserva la ñ)."""
    import unicodedata

    t = texto.replace("ñ", "\0").replace("Ñ", "\1")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return t.replace("\0", "ñ").replace("\1", "Ñ")


def palabras_para(sitio: str, cfg: dict) -> list[str]:
    """Palabras clave a buscar en un sitio. En los sitios de "sin_tildes_en" se agrega
    la variante sin tildes de cada palabra, porque su buscador puede distinguirlas."""
    out: list[str] = []
    for p in cfg["palabras_clave"]:
        for v in ([p, sin_tildes(p)] if sitio in (cfg["sin_tildes_en"] or []) else [p]):
            if v not in out:
                out.append(v)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nuevos", help="escribe aquí un resumen Markdown de los avisos nuevos")
    ap.add_argument("--acciones", help="escribe aquí las acciones de issue (alertas y páginas vigiladas)")
    args = ap.parse_args()

    cfg = cargar_config()
    DATOS.mkdir(parents=True, exist_ok=True)
    historial: dict[str, dict] = {}
    if AVISOS.exists():
        for a in json.loads(AVISOS.read_text(encoding="utf-8")).get("avisos", []):
            historial[a["id"]] = a
    primera_vez = not historial
    mk = marcas.cargar(MARCAS)

    # Estadística por palabra clave: avisos únicos encontrados y cuántos resultaron
    # útiles (afín o prioritario), acumulados entre chequeos.
    stats: dict = {"desde": None, "chequeos": 0, "palabras": {}}
    if ESTADISTICAS.exists():
        stats = json.loads(ESTADISTICAS.read_text(encoding="utf-8"))
    def _anotar(palabra: str, sitio: str, aid: str, afinidad: int) -> None:
        p = stats["palabras"].setdefault(palabra, {"vistos": {}, "por_sitio": {}})
        p["vistos"][aid] = max(afinidad, p["vistos"].get(aid, 0))
        ps = p["por_sitio"].setdefault(sitio, {})
        ps[aid] = max(afinidad, ps.get(aid, 0))

    horas_max = int(cfg["antiguedad_maxima_horas"] or 0)
    _sitios.HORAS_MAXIMAS = horas_max

    def demasiado_antiguo(publicado: str, encontrado: str, observado: str | None = None) -> bool:
        """True si el aviso tenía más de horas_max horas al encontrarlo. "observado" es
        cuándo se leyó el texto de la fecha (importa en las relativas, "Hace 3 días").
        Sin fecha reconocible, se admite (para no perder avisos)."""
        if not horas_max:
            return False
        pub = fecha_publicacion(publicado, datetime.fromisoformat(observado or encontrado))
        return pub is not None and (datetime.fromisoformat(encontrado) - pub).total_seconds() > horas_max * 3600

    s = sesion()
    t = ahora()
    estado_sitios: dict[str, dict] = {}
    encontrados: dict[str, dict] = {}

    for sitio, lector in LECTORES.items():
        if not cfg["sitios"].get(sitio, False):
            continue
        st = {"nombre": NOMBRES[sitio], "resultados": 0, "errores": [], "descartados": {}, "muestra": []}
        vistos_descarte: set[str] = set()
        for palabra in palabras_para(sitio, cfg):
            try:
                avisos = lector(s, palabra)
            except Exception as e:  # un sitio caído no detiene a los demás
                st["errores"].append(f"«{palabra}»: {type(e).__name__}: {str(e)[:160]}")
                continue
            st["resultados"] += len(avisos)
            for av in avisos:
                if not av.titulo or not av.url:
                    continue
                afinidad, motivo = evaluar_con_motivo(av.titulo, av.ubicacion, av.empresa, cfg)
                if afinidad and marcas.empresa_descartada(av.empresa, mk):
                    afinidad, motivo = 0, "empresa"  # empresa que la persona descartó
                _anotar(palabra, sitio, av.id, afinidad)
                if afinidad and av.id not in historial and demasiado_antiguo(av.publicado, t):
                    afinidad, motivo = 0, "antiguedad"
                if not afinidad:
                    if av.id not in vistos_descarte:
                        vistos_descarte.add(av.id)
                        st["descartados"][motivo] = st["descartados"].get(motivo, 0) + 1
                        if len(st["muestra"]) < 12:
                            st["muestra"].append({"titulo": av.titulo, "ubicacion": av.ubicacion, "motivo": motivo})
                    continue
                d = encontrados.get(av.id)
                if d:
                    if palabra not in d["palabras"]:
                        d["palabras"].append(palabra)
                    continue
                encontrados[av.id] = {
                    "id": av.id,
                    "sitio": av.sitio,
                    "titulo": av.titulo,
                    "url": av.url,
                    "empresa": av.empresa,
                    "ubicacion": av.ubicacion,
                    "publicado": av.publicado,
                    "palabras": [palabra],
                    "afinidad": afinidad,
                    "renta": av.renta,
                    "jornada": av.jornada,
                    "contrato": av.contrato,
                    "cierre": av.cierre,
                }
        estado_sitios[sitio] = st
        print(f"{NOMBRES[sitio]}: {st['resultados']} resultados, {len(st['errores'])} errores")
        for err in st["errores"]:
            print(f"  - {err}")

    nuevos = []
    for aid, d in encontrados.items():
        if aid in historial:
            h = historial[aid]
            h["visto_ultima_vez"] = t
            for p in d["palabras"]:
                if p not in h.setdefault("palabras", []):
                    h["palabras"].append(p)
            for k in ("titulo", "empresa", "ubicacion", "publicado", "renta", "jornada", "contrato", "cierre"):
                if d.get(k):  # se refresca con lo último que muestra el sitio
                    h[k] = d[k]
        else:
            d["encontrado"] = t
            d["visto_ultima_vez"] = t
            historial[aid] = d
            nuevos.append(d)

    limite = datetime.now(timezone.utc) - timedelta(days=int(cfg["dias_retencion"]))
    # El historial se vuelve a evaluar en cada chequeo, por si cambió la configuración.
    for v in historial.values():
        v["afinidad"] = evaluar(v.get("titulo", ""), v.get("ubicacion", ""), v.get("empresa", ""), cfg)
        if v["afinidad"] and marcas.empresa_descartada(v.get("empresa", ""), mk):
            v["afinidad"] = 0
    # Los avisos en proceso de postulación se conservan siempre, aunque ya no aparezcan.
    en_proceso = {k for k, m in mk["avisos"].items() if m.get("estado") in marcas.EN_PROCESO}
    historial = {
        k: v
        for k, v in historial.items()
        if k in en_proceso
        or (datetime.fromisoformat(v.get("visto_ultima_vez", t)) >= limite and v["afinidad"])
    }

    acciones = salud.revisar(SALUD, estado_sitios, t)
    paginas, acc_vig = vigilancia.revisar(s, cfg.get("vigilar") or [], VIGILANCIA, t)
    acciones += acc_vig
    acciones += marcas.seguimiento(mk, RECORDATORIOS, t)
    if args.acciones:
        Path(args.acciones).write_text(json.dumps(acciones, ensure_ascii=False), encoding="utf-8")
    for a in acciones:
        print(f"Acción: {a['accion']} · {a['titulo']}")

    marcar_vigencia(historial, estado_sitios, t)
    agrupar_duplicados(historial)
    # Republicaciones (mismo cargo y empresa) de avisos que la persona descartó.
    descartadas = marcas.firmas_descartadas(mk, firma)
    for d in historial.values():
        d.pop("auto_descartado", None)
        if d["id"] not in mk["avisos"] and firma(d) in descartadas:
            d["auto_descartado"] = True
    nuevos = [
        d for d in nuevos
        if d["id"] in historial
        and not d.get("duplicado_de")
        and not d.get("auto_descartado")
        and d.get("vigencia") != "cerrado"
    ]

    lista = sorted(historial.values(), key=lambda a: a.get("encontrado", ""), reverse=True)
    AVISOS.write_text(
        json.dumps({"actualizado": t, "avisos": lista}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    stats["desde"] = stats["desde"] or t
    stats["hasta"] = t
    stats["chequeos"] = stats.get("chequeos", 0) + 1
    ESTADISTICAS.write_text(json.dumps(stats, ensure_ascii=False) + "\n", encoding="utf-8")
    ESTADO.write_text(
        json.dumps(
            {
                "version": __version__,
                "ultimo_chequeo": t,
                "nuevos": len(nuevos),
                "total": len(lista),
                "palabras_clave": cfg["palabras_clave"],
                "zona": cfg.get("zona_nombre") or "",
                "sitios": estado_sitios,
                "paginas_vigiladas": paginas,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Nuevos: {len(nuevos)} · En historial: {len(lista)}")

    # En la primera ejecución todo es "nuevo": se guarda como base sin avisar.
    if args.nuevos and nuevos and not primera_vez:
        lineas = [f"Se encontraron **{len(nuevos)}** avisos nuevos.\n"]
        for d in sorted(nuevos, key=lambda x: -x.get("afinidad", 1)):
            extra = " · ".join(x for x in (d["empresa"], d["ubicacion"], d.get("renta"), d.get("jornada")) if x)
            if d.get("tambien_en"):
                extra += " · también en " + ", ".join(
                    f"[{NOMBRES.get(o['sitio'], o['sitio'])}]({o['url']})" for o in d["tambien_en"]
                )
            marca = "⭐ " if d.get("afinidad") == 3 else ""
            lineas.append(
                f"- {marca}[{d['titulo']}]({d['url']}) — {NOMBRES.get(d['sitio'], d['sitio'])}"
                + (f" · {extra}" if extra else "")
            )
        Path(args.nuevos).write_text("\n".join(lineas) + "\n", encoding="utf-8")

    sin_ningun_resultado = estado_sitios and all(
        v["resultados"] == 0 and v["errores"] for v in estado_sitios.values()
    )
    return 1 if sin_ningun_resultado else 0


if __name__ == "__main__":
    sys.exit(main())
