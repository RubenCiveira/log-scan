import os, sys, json, logging, time, io, warnings
from lib.runner import run
from agents.test.context import AgentContext
from kind.TooledAgent import TooledAgent
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.tools import Tool

ctx = AgentContext()

if len(sys.argv) < 2:
    sys.stderr.write( json.dumps({
        "system": "Error: falta el argumento (prompt)"
    }, ensure_ascii=False, default=str) )
    sys.exit(1)

props = { "temperature": 1 }
deps = ctx.inject( TooledAgent.deps_model() )

tools = ctx.tools()

check = TooledAgent.lookup_config(props)
if not check["ok"]:
    sys.stderr.write(json.dumps({
        "system": "Config inválida",
        "errors": check["errors"]
    }, ensure_ascii=False))
    sys.exit(5)

check = TooledAgent.lookup_deps(deps)
if not check["ok"]:
    sys.stderr.write(json.dumps({
        "system": "Dependencias inválida",
        "errors": check["errors"]
    }, ensure_ascii=False))
    sys.exit(6)
prompt = sys.argv[1]

run( TooledAgent(props, deps, tools), prompt )

