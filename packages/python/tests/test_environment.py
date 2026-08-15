from echoscene_core.environment import apply_environment, merged_environment


def test_local_nonempty_value_wins_but_empty_placeholder_does_not_erase(tmp_path) -> None:
    base = tmp_path / ".env"
    local = tmp_path / ".env.local"
    base.write_text("MODEL=base\nAPI_KEY=configured\n", encoding="utf-8")
    local.write_text('MODEL=local\nAPI_KEY=""\n', encoding="utf-8")

    resolved = merged_environment((str(base), str(local)), {})

    assert resolved["MODEL"] == "local"
    assert resolved["API_KEY"] == "configured"


def test_nonempty_process_value_has_highest_priority(tmp_path) -> None:
    base = tmp_path / ".env"
    base.write_text("MODEL=file\n", encoding="utf-8")

    resolved = merged_environment((str(base),), {"MODEL": "process"})

    assert resolved["MODEL"] == "process"


def test_apply_environment_exports_file_values_without_overriding_process(tmp_path) -> None:
    base = tmp_path / ".env"
    local = tmp_path / ".env.local"
    base.write_text("LIVEKIT_URL=wss://base.example\nMODEL=base\n", encoding="utf-8")
    local.write_text('LIVEKIT_URL=""\nMODEL=local\n', encoding="utf-8")
    target = {"MODEL": "process"}

    resolved = apply_environment((str(base), str(local)), target)

    assert resolved["LIVEKIT_URL"] == "wss://base.example"
    assert target["LIVEKIT_URL"] == "wss://base.example"
    assert target["MODEL"] == "process"
