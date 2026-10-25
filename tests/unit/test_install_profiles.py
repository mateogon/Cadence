"""Resolve the installed profiles, including indirect ONNX dependencies, offline."""

import shutil
import tomllib
from importlib.metadata import metadata, requires
import subprocess
from pathlib import Path

import pytest
from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]
UV = shutil.which("uv")
pytestmark = pytest.mark.skipif(UV is None, reason="Profile resolution requires uv")


def exported_requirements(*profile_flags):
    result = subprocess.run(
        [
            UV, "export", "--locked", "--offline", "--no-dev", "--no-hashes",
            "--no-header", "--no-annotate", *profile_flags,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [Requirement(line) for line in result.stdout.splitlines() if line.strip()]


@pytest.mark.parametrize(
    ("platform", "machine", "gpu"),
    [
        ("darwin", "arm64", False),
        ("linux", "x86_64", False),
        ("win32", "AMD64", False),
        ("linux", "x86_64", True),
        ("win32", "AMD64", True),
    ],
)
def test_locked_profiles_install_one_runtime_and_matching_torch(platform, machine, gpu):
    flags = ("--no-group", "cpu", "--extra", "gpu") if gpu else ()
    environment = default_environment()
    environment.update(sys_platform=platform, platform_machine=machine, python_version="3.12")
    selected = {
        requirement.name: requirement
        for requirement in exported_requirements(*flags)
        if requirement.marker is None or requirement.marker.evaluate(environment)
    }
    runtime = "onnxruntime-gpu" if gpu else "onnxruntime"
    assert {name for name in selected if name.startswith("onnxruntime")} == {runtime}
    assert str(selected[runtime].specifier) == "==1.24.1"
    suffix = "" if platform == "darwin" else "+cu124" if gpu else "+cpu"
    for name in ("torch", "torchaudio"):
        assert str(selected[name].specifier) == f"==2.6.0{suffix}"
    assert str(selected["whisperx"].specifier) == "==3.3.1"
    assert str(selected["pyannote-audio"].specifier) == "==3.3.2"
    if platform == "win32":
        # CTranslate2 4.4 loads Windows DLLs through pkg_resources, removed in setuptools 82.
        setuptools_version = str(selected["setuptools"].specifier).removeprefix("==")
        assert Version(setuptools_version) < Version("82")


def test_uv_rejects_combined_cpu_and_gpu_profiles():
    result = subprocess.run(
        [UV, "export", "--locked", "--offline", "--extra", "gpu"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "conflict" in result.stderr.lower()


@pytest.mark.parametrize("name", ["supertonic", "faster-whisper"])
def test_runtime_metadata_overrides_preserve_other_upstream_dependencies(name):
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    override = next(
        item for item in config["tool"]["uv"]["dependency-metadata"] if item["name"] == name
    )
    upstream = {
        str(Requirement(value)) for value in requires(name)
        if Requirement(value).name != "onnxruntime"
    }
    assert {str(Requirement(value)) for value in override["requires-dist"]} == upstream
    assert override["requires-python"] == metadata(name)["Requires-Python"]
    assert override["version"] == metadata(name)["Version"]
    assert set(override["provides-extra"]) == set(metadata(name).get_all("Provides-Extra"))


def test_windows_release_profile_contains_gpu_runtime_and_build_tool():
    environment = default_environment()
    environment.update(sys_platform="win32", platform_machine="AMD64", python_version="3.12")
    selected = {
        requirement.name: requirement
        for requirement in exported_requirements("--no-group", "cpu", "--extra", "gpu", "--group", "build")
        if requirement.marker is None or requirement.marker.evaluate(environment)
    }
    assert "pyinstaller" in selected
    assert "onnxruntime-gpu" in selected
    assert "onnxruntime" not in selected
    assert str(selected["torch"].specifier) == "==2.6.0+cu124"
    assert str(selected["torchaudio"].specifier) == "==2.6.0+cu124"
