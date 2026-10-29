"""Pruebas de la lógica del buscador, sin conexión a internet.

Corren en GitHub Actions en cada cambio (workflow "Pruebas").
"""
import json
from datetime import date

import pytest

import buscador.__main__ as m
from buscador import salud, sitios, vigilancia
from buscador.comun import Aviso, detalle_desde_texto


@pytest.fixture
def cfg():
    return m.cargar_config()


class R:
    def __init__(self, text="", js=None, status=200):
        self.text, self._js, self.status_code = text, js, status

    def json(self):
        return self._js

    def raise_for_status(self):
        pass


# ------------------------------------------------------------------ detalle
@pytest.mark.parametrize(
    "texto,clave,esperado",
    [
        ("Tecnólogo Médico Turno 7x7 Calama", "jornada", "Turno 7x7"),
        ("TM Imagenología (reemplazo)", "contrato", "Reemplazo"),
        ("TM part time $ 1.200.000 a $1.500.000", "renta", "$ 1.200.000 a $1.500.000"),
        ("Jornada completa, contrato indefinido", "contrato", "Indefinido"),
    ],
)
def test_detalle(texto, clave, esperado):
    assert detalle_desde_texto(texto)[clave] == esperado


# ------------------------------------------------------------ sin tildes
def test_variantes_sin_tildes(cfg):
    assert m.sin_tildes("tecnólogo médico imagenología") == "tecnologo medico imagenologia"
    assert m.sin_tildes("Ñuble año") == "Ñuble año"
    pc = m.palabras_para("computrabajo", cfg)
    assert "tecnologo medico resonancia" in pc and "tecnólogo médico resonancia" in pc
    assert pc.count("especialista de aplicaciones") == 1  # sin tildes no se duplica
    assert m.palabras_para("linkedin", cfg) == cfg["palabras_clave"]


# ------------------------------------------------------------ perfil y zona
@pytest.mark.parametrize(
    "titulo,ubic,empresa,esperado",
    [
        ("Tecnólogo Médico Resonancia Magnética", "Talca, Maule", "", 3),
        ("Tecnólogo médico TC", "Colina", "", 2),
        ("Application Specialist MR", "Santiago", "Siemens Healthineers", 3),
        ("Especialista de Aplicaciones", "Santiago", "GE HealthCare", 2),
        ("Especialista de Aplicaciones SAP", "Santiago", "Accenture", 0),
        ("Tecnólogo Médico Imagenología", "Antofagasta", "", 0),
        ("Tecnólogo médico imagenología para Calama", "", "", 0),
        ("TENS Imagenología", "Talca", "", 0),
        ("Tecnólogo médico UCI intensivo", "Talca", "", 2),
        ("Tecnólogo Médico Oftalmología", "Talca", "", 0),
        ("Vendedor", "Temuco", "", 0),
        ("TM Radiología", "Valdivia, Los Ríos", "", 2),
        ("Tecnólogo Médico Imagenología", "4,2", "", 2),
    ],
)
def test_evaluar(cfg, titulo, ubic, empresa, esperado):
    assert m.evaluar(titulo, ubic, empresa, cfg) == esperado


# --------------------------------------------------------------- duplicados
def test_duplicados_entre_sitios():
    h = {
        "1": {"id": "1", "sitio": "computrabajo", "titulo": "Tecnólogo/a Médico/a Scanner", "empresa": "Adecco Chile", "encontrado": "1", "url": "u1"},
        "2": {"id": "2", "sitio": "trabajando", "titulo": "Tecnólogo Médico Scanner", "empresa": "ADECCO", "encontrado": "2", "url": "u2", "renta": "$1"},
        "3": {"id": "3", "sitio": "linkedin", "titulo": "Tecnólogo Médico Scanner", "empresa": "Confidencial", "encontrado": "3", "url": "u3"},
    }
    m.agrupar_duplicados(h)
    assert h["2"]["duplicado_de"] == "1"
    assert h["1"]["tambien_en"] == [{"sitio": "trabajando", "url": "u2"}]
    assert h["1"]["renta"] == "$1"
    assert "duplicado_de" not in h["3"]  # sin empresa conocida no se agrupa


def test_vigencia():
    t = "2026-10-29T18:00:00+00:00"
    h = {
        "a": {"sitio": "x", "visto_ultima_vez": "2026-10-24T18:00:00+00:00"},
        "b": {"sitio": "x", "visto_ultima_vez": t, "cierre": "2026-10-01"},
        "c": {"sitio": "caido", "visto_ultima_vez": "2026-10-01T18:00:00+00:00"},
    }
    m.marcar_vigencia(h, {"x": {"resultados": 3}, "caido": {"resultados": 0}}, t)
    assert (h["a"]["vigencia"], h["a"]["dias_sin_ver"]) == ("sin_ver", 5)
    assert h["b"]["vigencia"] == "cerrado"
    assert h["c"]["vigencia"] == "vigente"  # si el sitio falló, no se marca


# -------------------------------------------------------------------- salud
def test_salud_abre_y_cierra(tmp_path):
    ruta = tmp_path / "salud.json"
    falla = {"x": {"nombre": "Sitio X", "resultados": 0, "errores": ["HTTPError 403"]}}
    assert salud.revisar(ruta, falla, "2026-10-29T10:00:00+00:00") == []
    acc = salud.revisar(ruta, falla, "2026-10-30T11:00:00+00:00")
    assert [a["accion"] for a in acc] == ["abrir"] and "403" in acc[0]["cuerpo"]
    assert salud.revisar(ruta, falla, "2026-10-30T12:00:00+00:00") == []  # no repite
    acc = salud.revisar(ruta, {"x": {"nombre": "Sitio X", "resultados": 4}}, "2026-10-30T13:00:00+00:00")
    assert [a["accion"] for a in acc] == ["cerrar"]


# --------------------------------------------------------------- vigilancia
def test_vigilancia(tmp_path, monkeypatch):
    paginas = {"v1": "<html><body><main>Cargo: Secretaria</main><nav>Menú</nav></body></html>",
               "v2": "<html><body><main>Cargo: Secretaria<br>Cargo: Tecnólogo Médico RM</main></body></html>"}
    actual = {"v": "v1"}
    monkeypatch.setattr(vigilancia, "obtener", lambda s, u, **k: R(paginas[actual["v"]]))
    monkeypatch.setattr(vigilancia, "_permitido", lambda s, u, c: True)
    ruta, pg = tmp_path / "vig.json", [{"nombre": "Clínica", "url": "https://c.cl/empleos", "selector": "main"}]
    _, acc = vigilancia.revisar(None, pg, ruta, "2026-10-29T10:00:00+00:00")
    assert acc == []  # la primera vez solo guarda la base
    actual["v"] = "v2"
    resumen, acc = vigilancia.revisar(None, pg, ruta, "2026-10-29T11:00:00+00:00")
    assert len(acc) == 1 and "Tecnólogo Médico RM" in acc[0]["cuerpo"]
    assert resumen[0]["cambiado"] == "2026-10-29T11:00:00+00:00"


# ----------------------------------------------------------------- lectores
def test_computrabajo(monkeypatch):
    html = """<article class="box_offer"><h2><a class="js-o-link" href="/ofertas-de-trabajo/oferta-de-trabajo-de-tm-X#lc">TM RM</a></h2>
    <p class="dFlex"><a offer-grid-article-company-url>Manpower Chile</a><span class="mr10">4,2</span></p>
    <p class="fs16"><span class="mr10">Talca, Maule</span></p><p class="fs13 fc_aux">Hace 3 horas</p></article>"""
    monkeypatch.setattr(sitios, "obtener", lambda s, u, **k: R(html))
    av = sitios.computrabajo(None, "x")[0]
    assert (av.empresa, av.ubicacion) == ("Manpower Chile", "Talca, Maule")
    assert av.url.endswith("oferta-de-trabajo-de-tm-X")


def test_linkedin(monkeypatch):
    html = """<li><a class="base-card__full-link" href="https://cl.linkedin.com/jobs/view/tm-1?x=1"></a>
    <h3 class="base-search-card__title">TM Resonancia</h3><h4 class="base-search-card__subtitle">Clínica</h4>
    <span class="job-search-card__location">Talca</span><time datetime="2026-10-28"></time></li>"""
    monkeypatch.setattr(sitios, "obtener", lambda s, u, **k: R(html))
    av = sitios.linkedin(None, "x")[0]
    assert (av.titulo, av.url, av.publicado) == ("TM Resonancia", "https://cl.linkedin.com/jobs/view/tm-1", "2026-10-28")


def test_trabajando_json(monkeypatch):
    js = {"ofertas": [{"idOferta": 61, "nombreCargo": "TM Resonancia", "nombreEmpresa": "X", "nombreComuna": "Talca"}]}
    monkeypatch.setattr(sitios, "obtener", lambda s, u, **k: R(js=js))
    av = sitios.trabajando(None, "x")[0]
    assert av.url == "https://www.trabajando.cl/trabajo/61-tm-resonancia" and av.ubicacion == "Talca"


def test_laborum():
    class S:
        cookies = type("c", (), {"get_dict": lambda self, domain=None: {"x": 1}})()

        def post(self, *a, **k):
            return R(js={"content": [{"id": 9, "titulo": "TM RM", "empresa": "Y", "confidencial": False,
                                      "fechaPublicacion": "20-10-2026", "localizacion": "Talca", "tipoTrabajo": "Full-time"}]})

    av = sitios.laborum(S(), "x")[0]
    assert av.url == "https://www.laborum.cl/empleos/tm-rm-y-9.html"
    assert (av.publicado, av.jornada) == ("2026-10-20", "Jornada completa")


def test_jobspy(monkeypatch):
    import jobspy
    import pandas as pd

    monkeypatch.setattr(jobspy, "scrape_jobs", lambda **k: pd.DataFrame(
        [{"job_url": "https://g/1", "title": "TM", "company": float("nan"), "location": None, "date_posted": date(2026, 10, 28)}]))
    av = sitios.google(None, "x")[0]
    assert (av.sitio, av.empresa, av.publicado) == ("google", "", "2026-10-28")


def test_google_diagnostico(monkeypatch):
    import jobspy
    import pandas as pd

    df = pd.DataFrame()
    df.attrs = {"errors": {"google": "no job data returned"}}
    monkeypatch.setattr(jobspy, "scrape_jobs", lambda **k: df)

    class S:
        def get(self, url, **k):
            r = R("Our systems have detected unusual traffic from your computer network")
            r.url = "https://www.google.com/sorry/index"
            return r

    with pytest.raises(RuntimeError, match="bloqueó"):
        sitios.google(S(), "x")


def test_trabajando_sin_avisos_no_es_error(monkeypatch):
    def fake(s, u, **k):
        if "api/searchjob" in u:
            return R(js={"ofertas": []})
        if "sitemap" in u:
            return R("<urlset></urlset>")
        return R("<html></html>")

    monkeypatch.setattr(sitios, "obtener", fake)
    sitios._SITEMAP.clear()
    assert sitios.trabajando(None, "jefe imagenología") == []



# ------------------------------------------------------------------- marcas
def test_marcas(tmp_path):
    from buscador import marcas

    mk = {"avisos": {
        "a1": {"estado": "descartado", "titulo": "Tecnólogo Médico Scanner", "empresa": "Adecco"},
        "a2": {"estado": "postule", "cambio": "2026-10-20T12:00:00Z", "titulo": "TM RM", "empresa": "Clínica", "url": "u"},
        "a3": {"estado": "entrevista", "cambio": "2026-10-28T12:00:00Z", "titulo": "TM TC"},
    }, "empresas_descartadas": ["Manpower Chile"]}
    assert marcas.empresa_descartada("MANPOWER CHILE", mk)
    assert not marcas.empresa_descartada("Adecco", mk)
    assert m.firma({"titulo": "Tecnólogo/a Médico/a Scanner", "empresa": "ADECCO CHILE"}) in marcas.firmas_descartadas(mk, m.firma)
    ruta = tmp_path / "rec.json"
    acc = marcas.seguimiento(mk, ruta, "2026-10-29T12:00:00+00:00")
    assert [a["titulo"] for a in acc] == ["📌 Seguimiento: TM RM (Clínica)"]
    assert marcas.seguimiento(mk, ruta, "2026-10-30T12:00:00+00:00") == []  # una sola vez por etapa
