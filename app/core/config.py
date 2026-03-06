from pydantic_settings import BaseSettings, SettingsConfigDict


# Settings class that sets values from .env file
class Settings(BaseSettings):
    PROJECT_NAME: str = "Delta Backend"

    # Postgres connection details
    POSTGRES_CONNECTION_URL: str

    # Auth Config
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int

    # Github App Credentials
    GITHUB_APP_ID: str
    GITHUB_PRIVATE_KEY_PATH: str
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    GITHUB_WEBHOOK_SECRET: str

    # RQ Config
    REDIS_URL: str
    NUM_WORKERS: int

    FRONTEND_URL: str

    # Cloned Repos Storage Path
    REPOS_BASE_PATH: str

    # LLM Config
    GEMINI_API_KEY: str
    LLM_MODEL: str

    # Load values from .env file
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
    )


settings = Settings()
