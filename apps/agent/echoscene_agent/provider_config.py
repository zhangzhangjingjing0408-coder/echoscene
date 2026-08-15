from __future__ import annotations

from dataclasses import dataclass

from echoscene_core.environment import merged_environment

DEFAULT_TTS_VOICE = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"


@dataclass(frozen=True)
class ProviderConfig:
    stt: str = "livekit-inference"
    llm: str = "livekit-inference"
    tts: str = "livekit-inference"
    stt_model: str = "deepgram/nova-3:multi"
    llm_model: str = "google/gemini-2.5-flash-lite"
    tts_model: str = "cartesia/sonic-3.5"
    tts_voice: str | None = DEFAULT_TTS_VOICE

    @classmethod
    def from_env(cls) -> ProviderConfig:
        env = merged_environment()
        return cls(
            stt=env.get("ECHOSCENE_STT_PROVIDER", "livekit-inference"),
            llm=env.get("ECHOSCENE_LLM_PROVIDER", "livekit-inference"),
            tts=env.get("ECHOSCENE_TTS_PROVIDER", "livekit-inference"),
            stt_model=env.get("ECHOSCENE_STT_MODEL", "deepgram/nova-3:multi"),
            llm_model=env.get(
                "ECHOSCENE_LLM_MODEL", "google/gemini-2.5-flash-lite"
            ),
            tts_model=env.get("ECHOSCENE_TTS_MODEL", "cartesia/sonic-3.5"),
            tts_voice=env.get("ECHOSCENE_TTS_VOICE") or DEFAULT_TTS_VOICE,
        )

    @property
    def demo_mode(self) -> bool:
        return self.llm == "mock" or self.stt == "mock" or self.tts == "mock"

    @property
    def tts_model_string(self) -> str:
        return f"{self.tts_model}:{self.tts_voice}" if self.tts_voice else self.tts_model


provider_config = ProviderConfig.from_env()
