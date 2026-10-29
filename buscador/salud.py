"""Salud del buscador: detecta sitios que dejaron de entregar avisos.

Se guarda por sitio la última vez que trajo resultados. Si un sitio activo pasa
HORAS_LIMITE sin resultados, se pide abrir un issue; cuando vuelve a funcionar,
se pide cerrarlo.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

HORAS_LIMITE = 24
PREFIJO = "⚠️ Buscador: "


def titulo_alerta(nombre: str) -> str:
    return f"{PREFIJO}{nombre} sin resultados hace más de {HORAS_LIMITE} horas"


def revisar(ruta: Path, estado_sitios: dict, t: str) -> list[dict]:
    """Actualiza el archivo de salud y devuelve acciones de issue (abrir/cerrar)."""
    salud = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    ahora = datetime.fromisoformat(t)
    acciones = []
    for sitio, st in estado_sitios.items():
        h = salud.setdefault(sitio, {"desde": t, "ultimo_ok": None, "alerta": False})
        nombre = st.get("nombre", sitio)
        if st.get("resultados", 0) > 0:
            h["ultimo_ok"] = t
            if h.get("alerta"):
                h["alerta"] = False
                acciones.append(
                    {
                        "accion": "cerrar",
                        "titulo": titulo_alerta(nombre),
                        "comentario": f"{nombre} volvió a entregar avisos ({st['resultados']} en el chequeo de {t[:16]} UTC).",
                    }
                )
            continue
        referencia = datetime.fromisoformat(h.get("ultimo_ok") or h.get("desde") or t)
        horas = (ahora - referencia).total_seconds() / 3600
        if horas >= HORAS_LIMITE and not h.get("alerta"):
            h["alerta"] = True
            errores = st.get("errores") or []
            detalle = "\n".join(f"- `{e}`" for e in errores[:8]) or "- Respondió sin errores, pero sin ningún aviso."
            ultimo = h.get("ultimo_ok")
            acciones.append(
                {
                    "accion": "abrir",
                    "titulo": titulo_alerta(nombre),
                    "cuerpo": (
                        f"**{nombre}** no entrega avisos desde "
                        f"{'el ' + ultimo[:16].replace('T', ' ') + ' UTC' if ultimo else 'que se activó'} "
                        f"(unas {int(horas)} horas).\n\n"
                        f"Último chequeo:\n{detalle}\n\n"
                        "Lo más probable es que el sitio haya cambiado su página o esté bloqueando las "
                        "consultas. El resto de los sitios sigue funcionando. Este issue se cierra solo "
                        "cuando el sitio vuelva a responder."
                    ),
                }
            )
    ruta.write_text(json.dumps(salud, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return acciones
