"""FastAPI dependency injection — singletons for Settings, ModelRouter, PromptLoader."""

from __future__ import annotations

import functools
import logging

from src.adapters.ak_llm import AkLlmAdapter
from src.adapters.k_exaone import KExaoneAdapter
from src.adapters.solar_pro3 import SolarPro3Adapter
from src.config import Settings
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the application-wide Settings singleton."""
    settings = Settings()
    logger.info("Settings loaded (debug=%s, log_level=%s)", settings.debug, settings.log_level)
    return settings


@functools.lru_cache(maxsize=1)
def get_model_router() -> ModelRouter:
    """Return the ModelRouter singleton with all LLM adapters registered."""
    settings = get_settings()
    registry_path = settings.resolve_registry_path()

    router = ModelRouter(registry_path)

    # Instantiate and register all LLM adapters
    adapters: dict[str, SolarPro3Adapter | KExaoneAdapter | AkLlmAdapter] = {}

    if settings.upstage_api_key:
        adapters["solar-pro3"] = SolarPro3Adapter(settings)
        logger.info("Registered adapter: solar-pro3")
    else:
        logger.warning("solar-pro3 adapter skipped — UPSTAGE_API_KEY not set")

    if settings.lg_k_exaone_api_key:
        adapters["k-exaone"] = KExaoneAdapter(settings)
        logger.info("Registered adapter: k-exaone")
    else:
        logger.warning("k-exaone adapter skipped — LG_K_EXAONE_API_KEY not set")

    if settings.skt_a_x_api_key:
        adapters["ak-llm"] = AkLlmAdapter(settings)
        logger.info("Registered adapter: ak-llm")
    else:
        logger.warning("ak-llm adapter skipped — SKT_A_X_API_KEY not set")

    router.register_adapters(adapters)
    return router


@functools.lru_cache(maxsize=1)
def get_prompt_loader() -> PromptLoader:
    """Return the PromptLoader singleton."""
    settings = get_settings()
    return PromptLoader(settings.resolve_prompts_dir())


@functools.lru_cache(maxsize=1)
def get_sessionmaker():
    """RAG DB 접속용 async sessionmaker 싱글턴 (RAG 이전으로 추가).

    retrieval.retrieve_grounding(db, ...)에 넘길 AsyncSession을 만든다.
    지연 import — sqlalchemy는 RAG를 쓸 때만 필요.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)
