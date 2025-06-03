from models.base import Base, engine

def create_db():
    Base.metadata.create_all(engine)
    print("Tabelas criadas com sucesso!")

if __name__ == "__main__":
    create_db()