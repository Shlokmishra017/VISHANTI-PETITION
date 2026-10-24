from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # app environment and database connection string
    ENV: str = "development"
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/vishanti"
    TEST_DATABASE_URL: str = "sqlite:///./test.db"

    # secrets and session keys
    SECRET_KEY: str = "vishanti-super-secret-ledger-key-change-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # demo SLA defaults in seconds
    DEMO_SLA_SECONDS: int = 300

    # file storage directory for attachments
    UPLOAD_DIR: str = "uploads"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
