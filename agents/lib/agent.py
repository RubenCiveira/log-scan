from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, Dict, Any, List, Tuple, Type, Union
from pydantic import BaseModel, ValidationError
from langchain_core.tools import BaseTool

Cfg = TypeVar("Cfg", bound=BaseModel)
Deps = TypeVar("Deps", bound=BaseModel)
Json = Dict[str, Any]

class Agent(ABC, Generic[Cfg, Deps]):
    """Interfaz genérica de agente: recibe una instrucción y devuelve un resultado en texto."""
    __slots__ = ("_cfg", "_deps", "_tools")

    def __init__(self, cfg: Cfg, deps: Optional[Deps], tools: Tuple[BaseTool, ...]):
        # Todo lo que guardamos aquí es inmutable
        cfg_valid  = self._validate_with_model(self.config_model(), cfg,  "config")
        deps_valid = self._validate_with_model(self.deps_model(), deps, "deps")

        deps_tools = self._extract_tools_from_deps(deps_valid)
        ext_tools  = [t for t in (tools or []) if isinstance(t, BaseTool)]
        final_tools = self._merge_tools(deps_tools, ext_tools)

        self._cfg: Cfg = cfg_valid
        self._deps: Optional[Deps] = deps_valid
        self._tools: Tuple[BaseTool, ...] = final_tools

    # ---- getters por si te interesan en subclases ----
    @property
    def cfg(self) -> Optional[BaseModel]:
        return self._cfg

    @property
    def deps(self) -> Optional[BaseModel]:
        return self._deps

    @property
    def tools(self) -> List[BaseTool]:
        return self._tools

    # === Configuración ===
    @classmethod
    def config_model(cls) -> Optional[Type[BaseModel]]:
        """Devuelve el modelo Pydantic de configuración (o None si no tiene)."""
        return None

    @classmethod
    def deps_model(cls) -> Optional[Type[BaseModel]]:
        """Modelo Pydantic que describe las dependencias. None si no usa deps."""
        return None

    @classmethod
    def lookup_config(cls, cfg: Union[BaseModel, Dict[str, Any], None]) -> Json:
        return cls._lookup_with_model(cls.config_model(), cfg, "config")

    @classmethod
    def lookup_deps(cls, deps: Union[BaseModel, Dict[str, Any], None]) -> Json:
        return cls._lookup_with_model(cls.deps_model(), deps, "deps")

    def resolve(
        self,
        instruction: str,
    ) -> str:
        """Entry point público: valida cfg y ejecuta."""
        return self._execute(instruction)

    @abstractmethod
    def _execute(
        self,
        instruction: str,
        cfg: Optional[BaseModel],
        deps: Optional[BaseModel],
        tools: List[BaseTool],
    ) -> str:
        """
        Método PROTEGIDO (convención): implementar la lógica del agente
        usando 'cfg' ya validada.
        """

    @classmethod
    def _lookup_with_model(
        cls,
        model: Optional[Type[BaseModel]],
        payload: Union[BaseModel, Dict[str, Any], None],
        where: str,                 # "config" | "deps"
    ) -> Json:
        if model is None:
            if payload not in (None, {}, []):
                return {
                    "ok": False,
                    where: None,
                    "errors": [{
                        "code": f"{where}.not_supported",
                        "title": f"{where} no admitido",
                        "detail": f"{cls.__class__.__name__} no acepta {where}.",
                        "source": {"pointer": f"/{where}"},
                    }],
                    "schema": None,
                }
            return {"ok": True, where: None, "errors": [], "schema": None}

        try:
            inst = cls._validate_with_model(model, payload, where)
            return {
                "ok": True,
                where: inst.model_dump() if inst is not None else None,
                "errors": [],
                "schema": None,  # evita generar JSON Schema aquí si te está dando problemas
            }
        except ValueError as ve:
            data = ve.args[0] if (ve.args and isinstance(ve.args[0], dict)) else {}
            return {
                "ok": False,
                where: None,
                "errors": data.get("errors", [{
                    "code": f"{where}.error",
                    "title": f"Error de {where}",
                }]),
                "schema": None,
            }

    @classmethod
    def _validate_with_model(
        cls,
        model: Optional[Type[BaseModel]],
        payload: Union[BaseModel, Dict[str, Any], None],
        where: str,   # "config" | "deps"
    ) -> Optional[BaseModel]:
        if model is None:
            if payload not in (None, {}, []):
                # el agente no acepta ese bloque
                raise ValueError({
                    "ok": False,
                    "errors": [{
                        "code": f"{where}.not_supported",
                        "title": f"{where} no admitido",
                        "detail": f"{cls.__class__.__name__} no acepta {where}.",
                        "source": {"pointer": f"/{where}"},
                    }],
                })
            return None

        if isinstance(payload, model):
            return payload

        if payload is None:
            # ⬇️ ANTES no capturabas el ValidationError aquí:
            try:
                return model()  # usará defaults; si falta algo, lanzará ValidationError
            except ValidationError as ve:
                raise ValueError({"ok": False, "errors": cls._normalize_pydantic_errors(where, ve)})

        if isinstance(payload, dict):
            try:
                return model(**payload)
            except ValidationError as ve:
                raise ValueError({"ok": False, "errors": cls._normalize_pydantic_errors(where, ve)})

        raise TypeError(f"{where} debe ser {model.__name__}, dict o None")

    @classmethod
    def _normalize_pydantic_errors(cls, where: str, ve: ValidationError) -> list[dict]:
        errs: list[dict] = []
        for e in ve.errors():
            loc = e.get("loc", [])
            # pointer tipo /field/subfield
            pointer = "/" + "/".join(map(str, loc)) if loc else "/"
            etype = e.get("type") or ""
            # Heurística para "faltante"
            is_missing = etype.endswith(".missing") or etype == "missing" or e.get("msg", "").lower().startswith("field required")

            errs.append({
                "code": f"{where}.missing" if is_missing else f"{where}.validation",
                "title": "Campo requerido ausente" if is_missing else "Error de validación",
                "detail": e.get("msg", "Entrada inválida"),
                "source": {"pointer": pointer},
                "meta": {"type": etype, "ctx": e.get("ctx")},
            })
        return errs

    def _extract_tools_from_deps(self, deps_bm) -> list[BaseTool]:
        tools = []
        if deps_bm:
            for name, field in deps_bm.model_fields.items():
                val = getattr(deps_bm, name, None)
                if isinstance(val, BaseTool):
                    tools.append(val)
        return tools

    def _merge_tools(self, prefer_left: list[BaseTool], right: list[BaseTool]) -> list[BaseTool]:
        by = {t.name: t for t in prefer_left}
        for t in right:
            if t.name not in by:
                by[t.name] = t
        return list(by.values())