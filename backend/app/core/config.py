from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI QA Platform"
    environment: str = "dev"
    default_llm_provider: str = "openai"
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_model: str = "claude-3-5-sonnet-latest"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    ollama_model: str = "llama3.1"
    ollama_base_url: str = "http://localhost:11434"
    llm_timeout_seconds: int = 30
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    max_parallel_steps: int = 5
    max_heal_attempts: int = 3
    run_history_backend: str = "sqlite"
    run_history_sqlite_path: str = "data/run_history.db"
    session_backend: str = "sqlite"
    session_sqlite_path: str = "data/sessions.db"
    qa_memory_backend: str = "sqlite"
    qa_memory_sqlite_path: str = "data/qa_memory.db"
    web_rag_enabled: bool = False
    web_rag_search_max_results: int = 5
    web_rag_chunk_size: int = 700
    web_rag_chunk_overlap: int = 120
    web_rag_cache_ttl_seconds: int = 1800
    advanced_testcase_generation_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
