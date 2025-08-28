# from abc import ABC, abstractmethod
from abc import ABC, abstractmethod
from pydantic_core import core_schema  # <- importa del runtime de pydantic v2
from pydantic.json_schema import JsonSchemaValue

class RAGExpander(ABC):
    # @abstractmethod
    def expand(self, query: str) -> str:
        """Devuelve texto contextual para la query."""
        raise NotImplementedError

    @classmethod
    def __get_pydantic_core_schema__(cls, _source, _handler):
        return core_schema.is_instance_schema(cls)

    @classmethod
    def __get_pydantic_json_schema__(cls, _core_schema, _handler) -> JsonSchemaValue:
        # devolvemos un esquema “genérico” (suficiente para documentación/UI)
        return {
            "type": "object",
            "title": "RAGExpander",
            "description": "Instancia que implementa expand(query: str) -> str.",
            # puedes agregar más metadata si quieres
        }