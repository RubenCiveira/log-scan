from abc import ABC, abstractmethod
from typing import Type, Optional, Union, Dict, Any
from pydantic import BaseModel, ValidationError

Json = Dict[str, Any]

class Agent(ABC):
    """Interfaz genérica de agente: recibe una instrucción y devuelve un resultado en texto."""

    # === Configuración ===
    @classmethod
    def config_model(cls) -> Optional[Type[BaseModel]]:
        """Devuelve el modelo Pydantic de configuración (o None si no tiene)."""
        return None

    @classmethod
    def deps_model(cls) -> Optional[Type[BaseModel]]:
        """Modelo Pydantic que describe las dependencias. None si no usa deps."""
        return None

    def lookup_config(self, cfg: Union[BaseModel, Dict[str, Any], None]) -> Json:
        return self._lookup_with_model(self.config_model(), cfg, "config")

    def lookup_deps(self, deps: Union[BaseModel, Dict[str, Any], None]) -> Json:
        return self._lookup_with_model(self.deps_model(), deps, "deps")

    def resolve(self, instruction: str, cfg: Union[BaseModel, Dict[str, Any], None] = None, deps: Union[BaseModel, Dict[str, Any], None] = None, ) -> str:
        """Entry point público: valida cfg y ejecuta."""
        cfg_valid  = self._validate_with_model(self.config_model(), cfg,  "config")
        deps_valid = self._validate_with_model(self.deps_model(),   deps, "deps")
        return self._execute(instruction, cfg_valid, deps_valid)

    @abstractmethod
    def _execute(self, instruction: str, cfg: Optional[BaseModel], deps: Optional[BaseModel]) -> str:
        """
        Método PROTEGIDO (convención): implementar la lógica del agente
        usando 'cfg' ya validada.
        """

    def _normalize_pydantic_errors(self, where: str, ve: ValidationError) -> list[dict]:
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

    def _validate_with_model(
        self,
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
                        "detail": f"{self.__class__.__name__} no acepta {where}.",
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
                raise ValueError({"ok": False, "errors": self._normalize_pydantic_errors(where, ve)})

        if isinstance(payload, dict):
            try:
                return model(**payload)
            except ValidationError as ve:
                raise ValueError({"ok": False, "errors": self._normalize_pydantic_errors(where, ve)})

        raise TypeError(f"{where} debe ser {model.__name__}, dict o None")

    def _lookup_with_model(
        self,
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
                        "detail": f"{self.__class__.__name__} no acepta {where}.",
                        "source": {"pointer": f"/{where}"},
                    }],
                    "schema": None,
                }
            return {"ok": True, where: None, "errors": [], "schema": None}

        try:
            inst = self._validate_with_model(model, payload, where)
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
