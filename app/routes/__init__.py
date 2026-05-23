from app.routes.ad import router as ad_router
from app.routes.devices import router as devices_router
from app.routes.ops import router as ops_router
from app.routes.tickets_api import router as tickets_api_router

__all__ = ["ad_router", "devices_router", "ops_router", "tickets_api_router"]
