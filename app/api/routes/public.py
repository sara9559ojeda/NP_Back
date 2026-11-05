"""Public product information for external users (use case "Visualizar información del producto", v1.1.0).

No authentication and no personal data. The Spanish copy still needs Sara's approval, so it is
published with ``contentStatus: "pendiente_de_aprobacion"`` and the web can flag it as such.
"""

from fastapi import APIRouter, Response

from app.core.config import APP_VERSION
from app.schemas.common import CamelModel

router = APIRouter(prefix="/public", tags=["public"])

CONTENT_VERSION = "2026-11-04"


class ProductFeature(CamelModel):
    title: str
    description: str


class ProductStep(CamelModel):
    order: int
    title: str
    description: str


class ProductRequirements(CamelModel):
    headsets: list[str]
    web: str


class ProductInfoOut(CamelModel):
    name: str
    tagline: str
    description: str
    audience: str
    features: list[ProductFeature]
    how_it_works: list[ProductStep]
    requirements: ProductRequirements
    disclaimer: str
    content_version: str
    content_status: str
    api_version: str


PRODUCT_INFO = ProductInfoOut(
    name="NEUROPHOBIA",
    tagline="Terapia de exposición a la aracnofobia en realidad virtual, acompañada por tu profesional.",
    description=(
        "NEUROPHOBIA es un prototipo académico de exposición gradual a arañas en realidad virtual (Meta Quest). "
        "Cada sesión avanza por niveles, registra cómo respondes y genera una retroalimentación que revisa tu "
        "profesional de la salud."
    ),
    audience="Personas con miedo a las arañas que siguen un proceso con un profesional de la salud.",
    features=[
        ProductFeature(title="Exposición gradual", description="Cinco niveles de exposición; empiezas en el que autorice tu profesional."),
        ProductFeature(title="Tú controlas", description="Puedes pausar o salir de forma segura en cualquier momento."),
        ProductFeature(title="Seguimiento", description="Tu profesional ve tu avance, la retroalimentación de cada sesión y deja notas."),
        ProductFeature(title="Privacidad", description="Los datos de las sesiones se guardan separados de tu identidad."),
    ],
    how_it_works=[
        ProductStep(order=1, title="Regístrate", description="Crea tu cuenta y acepta el consentimiento informado."),
        ProductStep(order=2, title="Empareja el visor", description="Genera un código en la web y escríbelo en las gafas."),
        ProductStep(order=3, title="Ajusta tu grado de fobia", description="Indica del 1 al 5 cuánto miedo sientes hoy."),
        ProductStep(order=4, title="Inicia la terapia", description="Pulsa «Comenzar» en el Refugio y avanza a tu ritmo."),
        ProductStep(order=5, title="Revisa tu avance", description="Consulta tus sesiones; tu profesional revisa la retroalimentación."),
    ],
    requirements=ProductRequirements(
        headsets=["Meta Quest 2", "Meta Quest 3", "Meta Quest 3S"],
        web="Navegador actualizado (Chrome, Edge, Firefox o Safari).",
    ),
    disclaimer=(
        "NEUROPHOBIA es un prototipo académico y no sustituye un diagnóstico ni un tratamiento profesional. "
        "Si sientes malestar intenso, detén la sesión y consulta con tu profesional de la salud."
    ),
    content_version=CONTENT_VERSION,
    content_status="pendiente_de_aprobacion",
    api_version=APP_VERSION,
)


@router.get("/product-info", response_model=ProductInfoOut, summary="Información del producto (usuario externo, sin sesión)")
def product_info(response: Response) -> ProductInfoOut:
    response.headers["Cache-Control"] = "public, max-age=300"
    return PRODUCT_INFO
