from lib.rag import RAGExpander

class TypeMiRag(RAGExpander):
    def expand(self, query: str) -> str:
        """Devuelve texto contextual para la query."""
        return "Hola meu"

def MiRag():
    return TypeMiRag()