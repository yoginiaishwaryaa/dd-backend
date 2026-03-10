from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings


# Factory function to get a configured Gemini LLM instance
def get_llm(temperature: float = 0) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=temperature,
    )
