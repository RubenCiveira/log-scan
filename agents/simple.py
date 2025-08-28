import os, sys, json, logging, time, io, warnings
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from langchain_community.utilities import WikipediaAPIWrapper
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.tools import Tool

from agent import agent

class EchoAgent(Agent):
    def execute(self, instruction: str) -> str:
        return f"Echo: {instruction}"


# 🔇 silencia el warning de BeautifulSoup:
from bs4 import GuessedAtParserWarning
warnings.filterwarnings("ignore", category=GuessedAtParserWarning)

# Algunos modelos devueltos por OpenAI vienen con sufijo de fecha.
try:
    import tiktoken
except ImportError:
    tiktoken = None  # fallback: _count_tokens devolverá 0 si no hay tiktoken
# Normalizamos a claves conocidas para elegir encoding.
def _normalize_model_for_encoding(model: str) -> str:
    if not model:
        return "gpt-4o-mini"
    base = model.split("-")[0]  # p.ej. "gpt"
    # mapea variantes comunes a algo que tiktoken entienda
    if model.startswith("gpt-4o"):
        return "gpt-4o"  # tiktoken suele usar cl100k_base para estos
    if model.startswith("gpt-4.1"):
        return "gpt-4.1"
    if model.startswith("o4"):
        return "gpt-4o"  # usa la misma base
    return model

def _encoding_for_model(model: str):
    if not tiktoken:
        return None
    m = _normalize_model_for_encoding(model)
    try:
        return tiktoken.encoding_for_model(m)
    except Exception:
        # fallback razonable para modelos OpenAI modernos
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None

def _count_tokens(model: str, text: str) -> int:
    """Cuenta tokens aproximados de un texto plano para el modelo dado.
    Nota: no incluye los tokens de 'role' ni system, es una estimación."""
    if not text or not tiktoken:
        return 0
    enc = _encoding_for_model(model)
    if not enc:
        return 0
    try:
        return len(enc.encode(text))
    except Exception:
        return 0

log_stream = io.StringIO()

PRICING_PER_1K = {
    # input, output
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o":      (5.00, 15.00),
    "gpt-4.1-mini":(0.30, 1.20),
    "gpt-4.1":     (5.00, 15.00),
    "o4-mini":     (0.30, 1.20),
    "o4":          (5.00, 15.00),
    # añade aquí otros modelos que uses
}

# configurar logging para escribir al buffer
logging.basicConfig(
    stream=log_stream,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

def match_pricing(model_name: str):
    """Intenta encontrar precio por coincidencia exacta o prefijo."""
    if model_name in PRICING_PER_1K:
        return PRICING_PER_1K[model_name]
    # fallback por prefijo (por si el modelo devuelve variantes con sufijos)
    for key in PRICING_PER_1K.keys():
        if model_name.startswith(key):
            return PRICING_PER_1K[key]
    return (0.0, 0.0)

def estimate_cost_usd(model: str, prompt_toks: int, completion_toks: int) -> float:
    mi, mo = match_pricing(model)
    return (prompt_toks / 1000.0) * mi + (completion_toks / 1000.0) * mo

class CostTracingHandler(BaseCallbackHandler):
    """Captura cada inicio/fin de llamada LLM para calcular tokens, coste y tiempos."""
    def __init__(self):
        self.calls: Dict[str, Dict[str, Any]] = {}
        self.finished: List[Dict[str, Any]] = []

    # Algunos proveedores disparan on_chat_model_start además de on_llm_start.
    # Implementamos ambas por robustez, ambas usarán la misma lógica.

    def on_llm_start(self, serialized: dict, prompts: List[str], run_id: str, parent_run_id: Optional[str] = None, **kwargs):
        self._start_common("llm", serialized, prompts, run_id, parent_run_id)

    def on_chat_model_start(self, serialized: dict, messages: List[List[Any]], run_id: str, parent_run_id: Optional[str] = None, **kwargs):
        # messages es lista de listas de mensajes; tomamos un preview textual
        prompts = []
        for convo in messages:
            text = " ".join(getattr(m, "content", "") for m in convo if hasattr(m, "content"))
            if text:
                prompts.append(text)
        self._start_common("chat", serialized, prompts, run_id, parent_run_id)

    def _start_common(self, kind: str, serialized: dict, prompts: List[str], run_id: str, parent_run_id: Optional[str]):
        t0 = time.time()
        name = serialized.get("name") or serialized.get("id") or "unknown"
        # Guardamos una “call” provisional
        self.calls[run_id] = {
            "kind": kind,
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "start_time": t0,
            "model": None,  # lo sabremos al final
            "prompts": prompts,
            "prompt_preview": (prompts[0][:200] + "…") if prompts else "",
            "output_preview": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "request_id": None,
            "raw": {},  # metadata cruda por si hace falta auditar
        }
        logger.debug(f"[CB] start {kind} run_id={run_id} with {len(prompts)} prompt(s)")

    def on_llm_end(self, response, run_id: str, parent_run_id: Optional[str] = None, **kwargs):
        self._end_common(response, run_id)

    def on_llm_error(self, error: BaseException, run_id: str, **kwargs):
        # Marcamos el fin con error también
        call = self.calls.pop(run_id, None)
        if call:
            call["end_time"] = time.time()
            call["latency_ms"] = int((call["end_time"] - call["start_time"]) * 1000)
            call["error"] = str(error)
            self.finished.append(call)
        logger.error(f"[CB] error run_id={run_id}: {error}")

    # Helper extractor
    def _end_common(self, response, run_id: str):
        t1 = time.time()
        call = self.calls.pop(run_id, None)
        if not call:
            return

        # Extraer metadata y tokens de la forma más compatible posible
        # En callbacks, 'response' suele ser un LLMResult:
        # - response.generations[0][0].message   → AIMessage
        # - response.llm_output.get("token_usage") → dict
        model = None
        request_id = None
        prompt_toks = comp_toks = total_toks = 0
        output_preview = None
        raw_meta: Dict[str, Any] = {}

        try:
            # llm_output puede traer usage/model/otros
            llm_output = getattr(response, "llm_output", {}) or {}
            raw_meta["llm_output"] = llm_output
            # 1) llm_output
            usage = llm_output.get("token_usage") or llm_output.get("usage") or {}

            # 2) generations / message
            gens = getattr(response, "generations", None)
            gen0 = gens[0][0] if gens and len(gens)>0 and len(gens[0])>0 else None
            msg = getattr(gen0, "message", None) if gen0 else None
            if msg is not None:
                output_content = getattr(msg, "content", "")
                output_preview = str(output_content)[:200] + "…"
                rm = getattr(msg, "response_metadata", {}) or {}
                raw_meta["response_message_metadata"] = rm
                # modelo puede venir aquí
                model = llm_output.get("model") or llm_output.get("model_name") or rm.get("model") or rm.get("model_name")
                request_id = rm.get("id") or rm.get("request_id")
                # usage también puede venir aquí
                usage = usage or rm.get("token_usage") or rm.get("usage") or {}

            # 3) generation_info (algunas versiones lo ponen aquí)
            if gen0:
                gi = getattr(gen0, "generation_info", {}) or {}
                raw_meta["generation_info"] = gi
                usage = usage or gi.get("token_usage") or gi.get("usage")

            # 4) ultimo intento: openai raw
            if not usage:
                openai_raw = llm_output.get("openai_api_response") or {}
                raw_meta["openai_api_response"] = openai_raw
                usage = openai_raw.get("usage") or {}

            # ---- parseo final de usage ----
            prompt_toks = int(usage.get("prompt_tokens") or 0)
            comp_toks   = int(usage.get("completion_tokens") or 0)
            total_toks  = int(usage.get("total_tokens") or (prompt_toks + comp_toks))

            # 5) Fallback con tiktoken si seguimos sin datos
            if (prompt_toks + comp_toks) == 0:
                eff_model = model or "gpt-4o-mini"
                # usamos lo que guardamos en start y el mensaje de salida
                # ojo: es aproximación (no cuenta roles ni system tokens exactamente)
                input_text = " ".join(call.get("prompts") or [])
                prompt_toks = _count_tokens(eff_model, input_text)
                comp_toks   = _count_tokens(eff_model, getattr(msg, "content", "") if msg else "")
                total_toks  = prompt_toks + comp_toks

            model = llm_output.get("model_name")

            # generations → primera respuesta
            gens = getattr(response, "generations", None)
            if gens and len(gens) > 0 and len(gens[0]) > 0:
                gen0 = gens[0][0]
                # gen0.message puede ser AIMessage con response_metadata
                msg = getattr(gen0, "message", None)
                if msg is not None:
                    output_preview = str(getattr(msg, "content", ""))[:200] + "…"
                    # Algunas SDK ponen usage/model/request_id en response_metadata
                    rm = getattr(msg, "response_metadata", {}) or {}
                    raw_meta["response_message_metadata"] = rm
                    model = model or rm.get("model_name")
                    request_id = rm.get("id") or rm.get("request_id")
                    # si no vino usage arriba, intenta aquí
                    if not usage and "token_usage" in rm:
                        tu = rm["token_usage"]
                        prompt_toks = int(tu.get("prompt_tokens") or 0)
                        comp_toks = int(tu.get("completion_tokens") or 0)
                        total_toks = int(tu.get("total_tokens") or (prompt_toks + comp_toks))
        except Exception as ex:
            logger.debug(f"[CB] metadata extraction fallback: {ex}")

        # Coste
        model_eff = model or "unknown"
        cost = estimate_cost_usd(model_eff, prompt_toks, comp_toks)
        call.update({
            "model": model_eff,
            "output_preview": output_preview,
            "prompt_tokens": prompt_toks,
            "completion_tokens": comp_toks,
            "total_tokens": total_toks,
            "cost_usd": round(cost, 8),
            "request_id": request_id,
            "raw": raw_meta,
            "end_time": t1,
            "latency_ms": int((t1 - call["start_time"]) * 1000),
        })
        self.finished.append(call)
        logger.debug(f"[CB] end run_id={run_id} model={model_eff} tok={total_toks} cost={cost:.6f} USD")

def run(agent):
    if len(sys.argv) < 2:
        sys.stderr.write("Error: falta el argumento (prompt)\n")
        sys.exit(1)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        sys.stderr.write("Error: falta OPENAI_API_KEY en el entorno\n")
        sys.exit(2)

    prompt = sys.argv[1]

    # configura tu modelo y parámetros
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("OPENAI_TEMPERATURE", "0"))
    max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "256"))

    handler = CostTracingHandler()

    t0 = time.time()
    try:
        logger.debug(f"Prompt recibido: {prompt}")
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=256,
            callbacks=[handler],
        )

        wiki_api = WikipediaAPIWrapper()
        wiki_tool = Tool.from_function(
            name="wikipedia",
            description="Consulta Wikipedia y devuelve un resumen",
            func=wiki_api.run,
        )

        tools = [wiki_tool]

        # resp = llm.invoke(prompt)
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Eres un agente útil. Usa herramientas cuando sea necesario."),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),  # 👈 requerido
        ])
        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            # callbacks=[handler],      # se propagan a sub-llamadas
            verbose=False
        )
        # Ejecutar con callbacks (opcional, redundante, pero explícito)
        resp = agent_executor.invoke(
            {"input": "¿Quién es Rosalía? Busca y dame 3 datos."}
        )

        duration_ms = int((time.time() - t0) * 1000)

        # usage y metadatos (estructura puede variar según versión/SDK)
        total_prompt = sum(c["prompt_tokens"] for c in handler.finished)
        total_completion = sum(c["completion_tokens"] for c in handler.finished)
        total_tokens = sum(c["total_tokens"] for c in handler.finished)
        total_cost = round(sum(c["cost_usd"] for c in handler.finished), 8)

        out = {
            "input": prompt,
            "output": getattr(resp, "content", None),
            "model_requested": model_name,
            "params": {"temperature": temperature, "max_tokens": max_tokens},
            "calls": [
                {
                    "run_id": c["run_id"],
                    "parent_run_id": c["parent_run_id"],
                    "model": c["model"],
                    "prompt_tokens": c["prompt_tokens"],
                    "completion_tokens": c["completion_tokens"],
                    "total_tokens": c["total_tokens"],
                    "cost_usd": c["cost_usd"],
                    "latency_ms": c["latency_ms"],
                    "request_id": c["request_id"],
                    "prompt_preview": c["prompt_preview"],
                    "output_preview": c["output_preview"],
                    # si no quieres exponer metadata cruda, quítalo:
                    "raw": c["raw"],
                }
                for c in handler.finished
            ],
            "totals": {
                "prompt_tokens": total_prompt,
                "completion_tokens": total_completion,
                "total_tokens": total_tokens,
                "cost_usd": total_cost,
                "latency_ms": duration_ms,
            },
            # logs opcionales en string
            "logs": log_stream.getvalue(),
        }
        print(json.dumps(out, ensure_ascii=False, default=str))
    except Exception as e:
        sys.stderr.write(f"Error ejecutando LLM: {e}\n")
        sys.exit(3)

if __name__ == "__main__":
    main()