from adapters.generate_audiobook_supertonic import sanitize_text


class TextProcessor:
    def __init__(self, supported):
        self.supported = set(supported)
        self.validated = []

    def validate_text(self, text):
        self.validated.append(text)
        unsupported = sorted(set(text) - self.supported)
        return not unsupported, unsupported


def test_sanitize_text_handles_unicode_punctuation():
    processor = TextProcessor("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ,-.")
    assert sanitize_text("Don’t wait—now…", processor) == "Dont wait, now..."
    assert processor.validated == ["Don't wait, now..."]


def test_sanitize_text_preserves_supported_apostrophes_and_accents():
    processor = TextProcessor("L'été d'Álex.")
    assert sanitize_text("L’été d’Álex.", processor) == "L'été d'Álex."


def test_sanitize_text_does_not_merge_unsupported_word_separator():
    processor = TextProcessor("abcd ")
    assert sanitize_text("ab☃cd", processor) == "ab cd"


def test_sanitize_text_normalizes_before_validation():
    processor = TextProcessor("ABC ")
    assert sanitize_text("ＡＢＣ\u00a0Ａ", processor) == "ABC A"
    assert processor.validated == ["ABC A"]


def test_sanitize_text_collapses_whitespace_and_drops_unsupported_quotes():
    processor = TextProcessor("abcd ")
    assert sanitize_text(" 'ab'\n\tcd ", processor) == "ab cd"
