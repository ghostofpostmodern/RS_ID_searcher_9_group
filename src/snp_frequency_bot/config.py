from dataclasses import dataclass
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv is optional; ignore if not installed
    pass


@dataclass
class Settings:
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    ncbi_timeout: int = int(os.getenv("NCBI_API_TIMEOUT", 30))
    cache_ttl: int = int(os.getenv("CACHE_TTL", 86400))
    max_requests_per_hour: int = int(os.getenv("MAX_REQUESTS_PER_HOUR", 50))


settings = Settings()
