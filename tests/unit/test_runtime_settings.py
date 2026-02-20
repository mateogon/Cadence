import json

from system import runtime_settings


def test_load_settings_returns_defaults_when_file_missing(tmp_path):
    settings_path = tmp_path / "missing_settings.json"

    settings = runtime_settings.load_settings(path=settings_path)

    assert settings == runtime_settings.DEFAULTS


def test_load_settings_returns_defaults_for_malformed_json(tmp_path):
    settings_path = tmp_path / "bad_settings.json"
    settings_path.write_text("{not valid json", encoding="utf-8")

    settings = runtime_settings.load_settings(path=settings_path)

    assert settings == runtime_settings.DEFAULTS


def test_load_settings_merges_and_normalizes_values(tmp_path):
    settings_path = tmp_path / "cadence_settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "CADENCE_SYNTH_WORKERS": " 3 ",
                "CADENCE_TTS_MAX_CHARS": 1200,
                "CADENCE_FORCE_CPU": None,
                "UNRELATED": "ignored",
            }
        ),
        encoding="utf-8",
    )

    settings = runtime_settings.load_settings(path=settings_path)

    assert settings["CADENCE_SYNTH_WORKERS"] == "3"
    assert settings["CADENCE_TTS_MAX_CHARS"] == "1200"
    assert settings["CADENCE_FORCE_CPU"] == runtime_settings.DEFAULTS["CADENCE_FORCE_CPU"]
    assert "UNRELATED" not in settings


def test_save_settings_writes_defaults_for_missing_keys(tmp_path):
    settings_path = tmp_path / "out_settings.json"

    runtime_settings.save_settings(
        {
            "CADENCE_SYNTH_WORKERS": " 2 ",
            "CADENCE_FORCE_CPU": 1,
        },
        path=settings_path,
    )

    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["CADENCE_SYNTH_WORKERS"] == "2"
    assert payload["CADENCE_FORCE_CPU"] == "1"
    assert payload["CADENCE_TTS_MAX_CHARS"] == runtime_settings.DEFAULTS["CADENCE_TTS_MAX_CHARS"]


def test_apply_settings_to_environ_respects_override(monkeypatch):
    monkeypatch.setenv("CADENCE_FORCE_CPU", "0")

    runtime_settings.apply_settings_to_environ(
        {"CADENCE_FORCE_CPU": "1", "CADENCE_SYNTH_WORKERS": "4"},
        override=False,
    )

    assert runtime_settings.os.environ["CADENCE_FORCE_CPU"] == "0"
    assert runtime_settings.os.environ["CADENCE_SYNTH_WORKERS"] == "4"

    runtime_settings.apply_settings_to_environ(
        {"CADENCE_FORCE_CPU": "1"},
        override=True,
    )
    assert runtime_settings.os.environ["CADENCE_FORCE_CPU"] == "1"
