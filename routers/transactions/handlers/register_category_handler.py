
from postgres.data_models.categories import Categories
from routers.transactions.data_models.new_category_registered_data_model import NewCategoryRegisteredDataModel
from settings import get_session
from sqlalchemy import func, select
from settings import logger


async def execute(category: str):
    try:
        session = await get_session()
        lower_category = category.lower()
        category_exists = await session.execute(select(Categories).where(func.lower(Categories.name) == lower_category))
        category_exists = category_exists.scalar()

        if category_exists:
            return NewCategoryRegisteredDataModel(sucess=True,
                                                  message="Categoria ja cadastrada!")
        else:
            new_category = Categories(name=category)
            session.add(new_category)
            await session.commit()
            await session.refresh(new_category)
            return NewCategoryRegisteredDataModel(sucess=True,
                                                  message="Categoria registrada com sucesso!")
    except Exception as e:
        return NewCategoryRegisteredDataModel(sucess=False,
                                              message=f"Erro ao registrar categoria: {e}")