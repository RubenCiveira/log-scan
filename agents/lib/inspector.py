import json
from agent import Agent

def inspect(agent_cls: type[Agent]) -> dict | None:
    model = agent_cls.config_model()
    if not model:
        return None
    schema = model.model_json_schema()
    schema.setdefault("$id", f"urn:agent-config:{agent_cls.__name__}:1.0.0")
    schema.setdefault("title", f"{agent_cls.__name__}Config")
    # return schema
    print(json.dumps(schema, ensure_ascii=False, indent=2))
