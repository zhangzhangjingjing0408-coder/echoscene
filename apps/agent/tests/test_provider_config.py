from echoscene_agent.provider_config import DEFAULT_TTS_VOICE, ProviderConfig


def test_default_tts_descriptor_pins_one_voice_across_sessions(monkeypatch) -> None:
    monkeypatch.delenv("ECHOSCENE_TTS_VOICE", raising=False)
    config = ProviderConfig(tts_voice=DEFAULT_TTS_VOICE)
    assert config.tts_model_string == f"cartesia/sonic-3.5:{DEFAULT_TTS_VOICE}"
