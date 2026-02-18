from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BookFormatContract:
    root: Path
    content_dir: Path
    audio_dir: Path
    metadata_path: Path


def resolve_book_paths(book_root):
    root = Path(book_root)
    return BookFormatContract(
        root=root,
        content_dir=root / "content",
        audio_dir=root / "audio",
        metadata_path=root / "metadata.json",
    )
