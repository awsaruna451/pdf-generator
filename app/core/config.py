"""
Application configuration settings
"""
import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # API Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    
    # CORS Settings
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    # PDF Settings
    OUTPUT_DIR: str = "output"
    
    # Security Settings
    SECRET_KEY: str = "your-secret-key-change-in-production"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Create settings instance
settings = Settings()
