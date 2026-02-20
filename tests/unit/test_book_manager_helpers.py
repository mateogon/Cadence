from system.book_manager import BookManager


def test_get_extract_worker_count_defaults_when_env_missing(monkeypatch):
    monkeypatch.delenv("CADENCE_EXTRACT_WORKERS", raising=False)
    value = BookManager._get_extract_worker_count()
    assert isinstance(value, int)
    assert value >= 1
    assert value <= 4


def test_get_extract_worker_count_clamps_to_min_one(monkeypatch):
    monkeypatch.setenv("CADENCE_EXTRACT_WORKERS", "0")
    assert BookManager._get_extract_worker_count() == 1


def test_get_extract_worker_count_ignores_invalid(monkeypatch):
    monkeypatch.delenv("CADENCE_EXTRACT_WORKERS", raising=False)
    fallback = BookManager._get_extract_worker_count()
    monkeypatch.setenv("CADENCE_EXTRACT_WORKERS", "abc")
    assert BookManager._get_extract_worker_count() == fallback


def test_get_tts_max_chunk_chars_defaults_and_floor(monkeypatch):
    monkeypatch.delenv("CADENCE_TTS_MAX_CHARS", raising=False)
    assert BookManager._get_tts_max_chunk_chars() == 1600

    monkeypatch.setenv("CADENCE_TTS_MAX_CHARS", "100")
    assert BookManager._get_tts_max_chunk_chars() == 400


def test_get_whisperx_batch_size_defaults_and_validation(monkeypatch):
    monkeypatch.delenv("CADENCE_WHISPERX_BATCH_SIZE", raising=False)
    assert BookManager._get_whisperx_batch_size() == 24

    monkeypatch.setenv("CADENCE_WHISPERX_BATCH_SIZE", "8")
    assert BookManager._get_whisperx_batch_size() == 8

    monkeypatch.setenv("CADENCE_WHISPERX_BATCH_SIZE", "bad")
    assert BookManager._get_whisperx_batch_size() == 24


def test_tokenize_for_alignment_normalizes_curly_punctuation():
    tokens = BookManager.tokenize_for_alignment("Don’t stop — now")

    cleaned_words = [t["clean"] for t in tokens if t["clean"]]
    assert cleaned_words == ["dont", "stop", "now"]


def test_align_timestamps_exact_word_match_preserves_word_text():
    txt = "Hello world!"
    json_words = [
        {"word": "hello", "start": 0.0, "end": 0.3},
        {"word": "world", "start": 0.3, "end": 0.8},
    ]

    aligned = BookManager.align_timestamps(txt, json_words)

    assert [item["word"] for item in aligned] == ["Hello", " ", "world!"]
    assert aligned[0]["start"] == 0.0
    assert aligned[0]["end"] == 0.3
    assert aligned[2]["start"] == 0.3
    assert aligned[2]["end"] == 0.8


def test_align_timestamps_replace_block_distributes_times():
    txt = "alpha beta gamma"
    json_words = [
        {"word": "alpha", "start": 0.0, "end": 0.2},
        {"word": "delta", "start": 0.2, "end": 0.4},
        {"word": "gamma", "start": 0.4, "end": 0.6},
    ]

    aligned = BookManager.align_timestamps(txt, json_words)
    words = [item for item in aligned if item["word"].strip()]

    assert [w["word"] for w in words] == ["alpha", "beta", "gamma"]
    assert words[1]["start"] == 0.2
    assert words[1]["end"] == 0.4
