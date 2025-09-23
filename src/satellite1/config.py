from __future__ import annotations
from typing import Literal
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from .components.pcm5122 import PCM5122Config


class AppConfig(BaseModel):
    logging_level: Literal["DEBUG","INFO","WARNING","ERROR"] = "INFO"
    pcm5122: PCM5122Config = PCM5122Config()


# Optional: env support (SAT1_PCM5122__I2C_ADDR=0x18 etc.)
class AppSettings(BaseSettings, AppConfig):
    model_config = SettingsConfigDict(
        env_prefix="SAT1_",
        env_nested_delimiter="__",
        extra="ignore",
    )