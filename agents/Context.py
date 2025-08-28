from utils.MiRag import MiRag
from tools.Wikipedia import Wikipedia

from typing import Any, Optional, Type, get_origin, get_args, Protocol, runtime_checkable, List, Dict, Union
from pydantic import BaseModel, ValidationError, ConfigDict
from langchain_core.tools import BaseTool

class Context():
    _utils = [MiRag()]
    _tools = [Wikipedia()]

    def tools(self):
        return self._tools

    def inject(self, deps_model):
        if deps_model is None:
            return None

        # Construimos kwargs por nombre de campo
        values: Dict[str, Any] = {}
        for name, field in deps_model.model_fields.items():
            expected = field.annotation
            # Si el campo ya tiene default, podemos dejarlo vacío; si hay match lo rellenamos
            provided = None
            for obj in self._utils:
                if _matches_type(obj, expected):
                    provided = obj
                    break
            if provided is not None:
                values[name] = provided
            # else: si es requerido y no hay default, Pydantic levantará ValidationError

        try:
            return deps_model(**values)
        except ValidationError as e:
            # Puedes elegir: o relanzar, o devolver None, o empaquetar el error
            raise

def _unwrap_optional(t):
    """Si es Optional[T] o Union[T, None], devuelve T; en otro caso, devuelve t."""
    origin = get_origin(t)
    if origin is Union:
        args = [a for a in get_args(t) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return t

def _matches_type(instance: Any, expected_type: Any) -> bool:
    """Coincidencia por tipo robusta: clases normales, Protocols runtime_checkable, y duck-typing mínimo."""
    if expected_type is Any:
        return True
    T = _unwrap_optional(expected_type)

    # BaseTool, BaseModel, clases normales
    try:
        if isinstance(instance, T):
            return True
    except TypeError:
        # expected_type puede ser typing construct raro
        pass

    # Si es un Protocol runtime_checkable, isinstance funcionará arriba (ya retornaría True)
    # Duck-typing muy básico como último recurso:
    if getattr(T, "__name__", "") == "RAGExpander":
        return callable(getattr(instance, "expand", None))

    return False