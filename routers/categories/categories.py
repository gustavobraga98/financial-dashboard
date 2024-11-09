from postgres.data_models.categories import Categories  # Ajuste o caminho conforme necessário
from routers.transactions.data_models.new_category_registered_data_model import NewCategoryRegisteredDataModel
from settings import get_session
from datetime import datetime, timezone
from fastapi import APIRouter
from sqlalchemy import func, select

router = APIRouter()

@router.post("/")
async def create_categorie(category_name: str):
    """
    Create a new category
    """
    try:
        session = await get_session()
        lower_category = category_name.lower()
        category_exists = await session.execute(select(Categories).where(func.lower(Categories.name) == lower_category))
        category_exists = category_exists.scalar()

        if category_exists:
            return NewCategoryRegisteredDataModel(sucess=True,
                                                  message="Categoria ja cadastrada!")
        else:
            new_category = Categories(name=category_name)
            session.add(new_category)
            await session.commit()
            await session.refresh(new_category)
            return NewCategoryRegisteredDataModel(sucess=True,
                                                  message="Categoria registrada com sucesso!")
    except Exception as e:
        return NewCategoryRegisteredDataModel(sucess=False,
                                              message=f"Erro ao registrar categoria: {e}")


@router.get("/")
async def get_categories():
    """
    Get all categories
    """
    session = await get_session()
    query = select(Categories)
    result = await session.execute(query)
    categories = result.scalars().all()
    categories_names = []

    for category in categories:
        categories_names.append(category.name)

    return categories_names