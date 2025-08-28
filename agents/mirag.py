from rag import RAGExpander

class MiRag(RAGExpander):
    def expand(self, query: str) -> str:
        """Devuelve texto contextual para la query."""
        return "Hola meu"
