from postgres.data_models.categories import Categories  # Ajuste o caminho conforme necessário
from routers.transactions.data_models.new_category_registered_data_model import NewCategoryRegisteredDataModel
from settings import get_session
from fastapi import APIRouter
from sqlalchemy import func, select

router = APIRouter()

@router.post("/")
async def create_category(category_name: str):
    """
    Create a new category
    """
    try:
        session = await get_session()

        # Converta o nome da categoria para minúsculo para a busca case-insensitive
        lower_category = category_name.lower()

        # Verifique se a categoria já existe
        category_exists = await session.execute(
            select(Categories).where(func.lower(Categories.name) == lower_category)
        )
        category_exists = category_exists.scalar()

        if category_exists:
            # Caso a categoria já exista, retorne um aviso
            return NewCategoryRegisteredDataModel(sucess=True,
                                                  message="Categoria já cadastrada!")
        else:
            # Se a categoria não existir, crie uma nova
            new_category = Categories(name=category_name)
            session.add(new_category)
            await session.commit()
            await session.refresh(new_category)
            return NewCategoryRegisteredDataModel(sucess=True,
                                                  message="Categoria registrada com sucesso!")
    except Exception as e:
        # Em caso de erro, retorne a mensagem de erro
        return NewCategoryRegisteredDataModel(sucess=False,
                                              message=f"Erro ao registrar categoria: {e}")


@router.get("/")
async def get_categories():
    """
    Get all categories
    """
    try:
        session = await get_session()

        # Query para pegar todas as categorias
        query = select(Categories)
        result = await session.execute(query)
        categories = result.scalars().all()

        # Extraindo o nome de cada categoria
        categories_names = [category.name for category in categories]

        return categories_names
    except Exception as e:
        return {"sucess": False, "message": f"Erro ao listar categorias: {e}"}
