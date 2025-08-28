import os, sys, json, logging, time, io, warnings
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, SkipValidation
from langchain_openai import ChatOpenAI
from langchain_core.memory import BaseMemory
from langchain_core.callbacks import BaseCallbackHandler
from langchain_community.utilities import WikipediaAPIWrapper
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.tools import Tool

from agent import Agent
from rag import RAGExpander

class TooledConfig(BaseModel):
    model: str = Field("gpt-4o-mini", title="Modelo")
    temperature: float = Field(0.0, ge=0.0, le=2.0, title="Temperature")
    max_tokens: int = Field(256, ge=1, le=8192, title="Máx. tokens")
    lang: str = Field("es", title="Idioma")
    system_prompt: str = Field(
        "Eres un agente útil. Usa herramientas cuando sea necesario.",
        title="Prompt del sistema"
    )

class TooledDeps(BaseModel):
    memory: Optional[BaseMemory] = Field(default=None, description="Memoria de LangChain")
    rag: RAGExpander = Field(default=None, description="Proveedor RAG")

class TooledAgent(Agent):
    @classmethod
    def config_model(cls):
        return TooledConfig

    @classmethod
    def deps_model(cls):
        return TooledDeps 

    def _execute(self, instruction: str, cfg: Optional[TooledConfig], ctx: Optional[TooledConfig]) -> str:
        print( ctx.rag )
        return "verde"
        # model_name = cfg.model
        # temperature = cfg.temperature
        # max_tokens = cfg.max_tokens

        # llm = ChatOpenAI(
        #     model="gpt-4o-mini",
        #     temperature=0,
        #     max_tokens=256,
        # )

        # # TODO: use cfg.lang to select wikipedia source.
        # wiki_api = WikipediaAPIWrapper()
        # wiki_tool = Tool.from_function(
        #     name="wikipedia",
        #     description="Consulta Wikipedia y devuelve un resumen",
        #     func=wiki_api.run,
        # )

        # tools = [wiki_tool]

        # prompt = ChatPromptTemplate.from_messages([
        #     ("system", cfg.system_prompt),
        #     ("human", "{input}"),
        #     MessagesPlaceholder(variable_name="agent_scratchpad"),  # 👈 requerido
        # ])
        # agent = create_tool_calling_agent(llm, tools, prompt)
        # agent_executor = AgentExecutor(
        #     agent=agent,
        #     tools=tools,
        #     # callbacks=[handler],      # se propagan a sub-llamadas
        #     verbose=False
        # )
        # # Ejecutar con callbacks (opcional, redundante, pero explícito)
        # resp = agent_executor.invoke(
        #     {"input": instruction}
        # )
        # return resp["output"]

