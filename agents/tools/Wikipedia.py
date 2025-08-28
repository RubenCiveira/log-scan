from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.tools import Tool

def Wikipedia():
    wiki_api = WikipediaAPIWrapper()
    return Tool.from_function(
            name="wikipedia",
            description="Consulta Wikipedia y devuelve un resumen",
            func=wiki_api.run,
    )