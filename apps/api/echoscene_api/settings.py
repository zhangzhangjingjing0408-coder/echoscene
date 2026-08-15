from __future__ import annotations

from dataclasses import dataclass

from echoscene_core.environment import merged_environment


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    trace_enabled: bool = True
    transcript_provider: str = "auto"
    content_provider: str = "auto"
    deepseek_api_key: str | None = None
    deepseek_content_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_max_output_tokens: int = 24_000
    transcript_cache_ttl_seconds: int = 2_592_000
    transcript_max_retries: int = 2
    transcript_retry_base_seconds: float = 0.35
    content_cache_ttl_seconds: int = 2_592_000
    preparation_cache_max_entries: int = 100
    supadata_api_key: str | None = None
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None
    livekit_agent_name: str = "echoscene"
    stt_model: str = "deepgram/nova-3:multi"
    llm_model: str = "google/gemini-2.5-flash-lite"
    tts_model: str = "cartesia/sonic-3.5"

    @classmethod
    def from_env(cls) -> Settings:
        env = merged_environment()
        return cls(
            environment=env.get("ECHOSCENE_ENV", "development"),
            trace_enabled=env.get("ECHOSCENE_TRACE_ENABLED", "true").lower() == "true",
            transcript_provider=env.get("ECHOSCENE_TRANSCRIPT_PROVIDER", "auto"),
            content_provider=env.get("ECHOSCENE_CONTENT_PROVIDER", "auto"),
            deepseek_api_key=env.get("DEEPSEEK_API_KEY") or None,
            deepseek_content_model=env.get("ECHOSCENE_CONTENT_MODEL", "deepseek-v4-pro"),
            deepseek_base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_max_output_tokens=int(
                env.get("ECHOSCENE_CONTENT_MAX_OUTPUT_TOKENS", "24000")
            ),
            transcript_cache_ttl_seconds=int(
                env.get("ECHOSCENE_TRANSCRIPT_CACHE_TTL_SECONDS", "2592000")
            ),
            transcript_max_retries=int(env.get("ECHOSCENE_TRANSCRIPT_MAX_RETRIES", "2")),
            transcript_retry_base_seconds=float(
                env.get("ECHOSCENE_TRANSCRIPT_RETRY_BASE_SECONDS", "0.35")
            ),
            content_cache_ttl_seconds=int(
                env.get("ECHOSCENE_CONTENT_CACHE_TTL_SECONDS", "2592000")
            ),
            preparation_cache_max_entries=int(
                env.get("ECHOSCENE_PREPARATION_CACHE_MAX_ENTRIES", "100")
            ),
            supadata_api_key=env.get("SUPADATA_API_KEY") or None,
            livekit_url=env.get("LIVEKIT_URL") or None,
            livekit_api_key=env.get("LIVEKIT_API_KEY") or None,
            livekit_api_secret=env.get("LIVEKIT_API_SECRET") or None,
            livekit_agent_name=env.get("LIVEKIT_AGENT_NAME", "echoscene"),
            stt_model=env.get("ECHOSCENE_STT_MODEL", "deepgram/nova-3:multi"),
            llm_model=env.get(
                "ECHOSCENE_LLM_MODEL", "google/gemini-2.5-flash-lite"
            ),
            tts_model=env.get("ECHOSCENE_TTS_MODEL", "cartesia/sonic-3.5"),
        )

    @property
    def livekit_configured(self) -> bool:
        return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret)


settings = Settings.from_env()
