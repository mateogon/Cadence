import qt.main_window as mw


def test_tts_settings_apply_and_reject_invalid_speed(qapp, monkeypatch):
    monkeypatch.setattr(mw, "load_settings", lambda: dict(mw.DEFAULTS))
    saved = []
    warnings = []
    monkeypatch.setattr(mw, "save_settings", lambda values: saved.append(values))
    monkeypatch.setattr(mw, "apply_settings_to_environ", lambda *args, **kwargs: None)
    monkeypatch.setattr(mw.QtWidgets.QMessageBox, "warning", lambda *args: warnings.append(args))
    dlg = mw.RuntimeSettingsDialog()
    assert dlg._vars["CADENCE_TTS_MODEL"].currentText() == "supertonic-3"
    assert dlg._vars["CADENCE_TTS_SPEED"].currentText() == "1.05"
    assert dlg._vars["CADENCE_TTS_STEPS"].currentText() == "8"
    dlg._vars["CADENCE_TTS_SPEED"].setCurrentText("nan")
    dlg._apply()
    assert warnings and not saved
    dlg._vars["CADENCE_TTS_SPEED"].setCurrentText("1.25")
    dlg._vars["CADENCE_TTS_STEPS"].setCurrentText("10")
    dlg._vars["CADENCE_TTS_MODEL"].setCurrentText("supertonic-2")
    dlg._apply()
    assert saved[0]["CADENCE_TTS_MODEL"] == "supertonic-2"
    assert saved[0]["CADENCE_TTS_SPEED"] == "1.25"
    assert saved[0]["CADENCE_TTS_STEPS"] == "10"
    dlg.close()


def test_runtime_settings_dialog_loads_values_from_settings(qapp, monkeypatch):
    valid_profiles = sorted(mw.STYLE_PROFILES.keys())
    chosen_profile = next((p for p in valid_profiles if p != "cadence"), "cadence")

    fake_settings = dict(mw.DEFAULTS)
    fake_settings["CADENCE_STYLE_PROFILE"] = chosen_profile
    fake_settings["CADENCE_SYNTH_WORKERS"] = "3"
    fake_settings["CADENCE_WHISPERX_PYTHON"] = "C:/Python/python.exe"

    monkeypatch.setattr(mw, "load_settings", lambda: fake_settings)

    dlg = mw.RuntimeSettingsDialog()

    assert dlg._vars["CADENCE_STYLE_PROFILE"].currentText() == chosen_profile
    assert dlg._vars["CADENCE_SYNTH_WORKERS"].currentText() == "3"
    assert dlg._vars["CADENCE_WHISPERX_PYTHON"].text() == "C:/Python/python.exe"
    dlg.close()


def test_runtime_settings_dialog_reset_restores_defaults(qapp, monkeypatch):
    fake_settings = dict(mw.DEFAULTS)
    fake_settings["CADENCE_SYNTH_WORKERS"] = "4"
    fake_settings["CADENCE_WHISPERX_PYTHON"] = "C:/override/python.exe"

    monkeypatch.setattr(mw, "load_settings", lambda: fake_settings)

    dlg = mw.RuntimeSettingsDialog()

    dlg._vars["CADENCE_SYNTH_WORKERS"].setCurrentText("2")
    dlg._vars["CADENCE_WHISPERX_PYTHON"].setText("D:/temp/python.exe")

    dlg._reset_defaults()

    assert dlg._vars["CADENCE_SYNTH_WORKERS"].currentText() == mw.DEFAULTS["CADENCE_SYNTH_WORKERS"]
    assert dlg._vars["CADENCE_WHISPERX_PYTHON"].text() == mw.DEFAULTS["CADENCE_WHISPERX_PYTHON"]
    dlg.close()


def test_runtime_settings_dialog_apply_saves_and_updates_env(qapp, monkeypatch):
    monkeypatch.setattr(mw, "load_settings", lambda: dict(mw.DEFAULTS))

    captured = {"saved": None, "applied": None}

    def _fake_save(settings):
        captured["saved"] = settings

    def _fake_apply(settings, override=True):
        captured["applied"] = (settings, override)

    monkeypatch.setattr(mw, "save_settings", _fake_save)
    monkeypatch.setattr(mw, "apply_settings_to_environ", _fake_apply)

    dlg = mw.RuntimeSettingsDialog()

    dlg._vars["CADENCE_SYNTH_WORKERS"].setCurrentText("3")
    dlg._vars["CADENCE_WHISPERX_PYTHON"].setText("C:/venv/python.exe")

    dlg._apply()

    assert captured["saved"] is not None
    assert captured["saved"]["CADENCE_SYNTH_WORKERS"] == "3"
    assert captured["saved"]["CADENCE_WHISPERX_PYTHON"] == "C:/venv/python.exe"

    applied_settings, override = captured["applied"]
    assert override is True
    assert applied_settings["CADENCE_SYNTH_WORKERS"] == "3"
    assert dlg.result() == mw.QtWidgets.QDialog.DialogCode.Accepted
    dlg.close()
