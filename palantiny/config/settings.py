"""Optional standalone settings; server code may use app.core.config instead."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PalantinySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    neo4j_uri: Optional[str] = Field(default=None, alias="NEO4J_URI")
    neo4j_username: str = Field(default="neo4j", alias="NEO4J_USERNAME")
    neo4j_password: str = Field(default="", alias="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="neo4j", alias="NEO4J_DATABASE")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    mongodb_uri: Optional[str] = Field(default=None, alias="MONGODB_URI")
    similarity_threshold: float = Field(default=0.75, alias="SIMILARITY_THRESHOLD")
    monograph_glob: str = Field(
        default="data/herb_monograph_chapters/**/*.cypher.txt",
        alias="PALANTINY_MONOGRAPH_GLOB",
    )
    herb_prices_cypher_path: str = Field(
        default="data/herb_prices_from_csv.cypher",
        alias="PALANTINY_HERB_PRICES_CYPHER",
    )


@lru_cache
def get_palantiny_settings() -> PalantinySettings:
    return PalantinySettings()
