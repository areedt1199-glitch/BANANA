import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Banana IoT & AI Platform (กล้วยหอมทอง)"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = Field(default="homthong_smart_farm_secret_key_change_in_production_2026", env="SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Database Settings
    # Default fallback to aiosqlite for zero-setup local dev; use postgresql+asyncpg:// in production/docker
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./banana_smart_farm.db",
        env="DATABASE_URL"
    )
    
    # CORS Origins
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "*"
    ]
    
    # MQTT Broker Settings (For ESP32 communication)
    MQTT_BROKER_HOST: str = Field(default="localhost", env="MQTT_BROKER_HOST")
    MQTT_BROKER_PORT: int = Field(default=1883, env="MQTT_BROKER_PORT")
    MQTT_USERNAME: str = Field(default="", env="MQTT_USERNAME")
    MQTT_PASSWORD: str = Field(default="", env="MQTT_PASSWORD")
    MQTT_TOPIC_TELEMETRY: str = "homthong/+/+/telemetry"  # homthong/{tenant_id}/{device_id}/telemetry
    MQTT_TOPIC_COMMAND: str = "homthong/{tenant_id}/{device_id}/cmd"
    
    # Kluai Hom Thong Agronomic Baseline Constants
    MAX_SAFE_EC_DS_M: float = 0.85
    HARD_CUTOFF_EC_DS_M: float = 1.00
    CRITICAL_WIND_SPEED_KMH: float = 30.0
    SIGATOKA_HUMIDITY_THRESHOLD_PCT: float = 90.0
    SIGATOKA_HOURS_RISK: int = 10
    
    # AI Vision API
    GEMINI_API_KEY: str = Field(default="", env="GEMINI_API_KEY")

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "allow"

settings = Settings()
