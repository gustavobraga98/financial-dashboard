from fastapi import APIRouter
from routers.dashboard import handlers as dashboard_handlers
router = APIRouter()

@router.get("/pizza_graph/")
async def get_balance(type: str, range: str):
    pizza_data = await dashboard_handlers.generate_pizza_graph_handler.execute(type, range)
    return pizza_data