from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import DEFAULT_SCOPE, DEFAULT_STATE


class OneIDSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    one_id_sso_url: str
    one_id_client_id: str
    one_id_client_secret: str
    one_id_client_scope: str = DEFAULT_SCOPE
    one_id_client_state: str = DEFAULT_STATE
