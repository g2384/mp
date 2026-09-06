from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any, cast

from mutagen import MutagenError
from mutagen.mp3 import MP3

ROOT = Path(__file__).resolve().parent
MANUAL_TRACKS_PATH = ROOT / "song-metadata.json"
GENERATED_TRACKS_PATH = ROOT / "song-generated.json"
SORT_FIELDS = ("artist", "title", "id", "file")

JsonObject = dict[str, Any]
GeneratedTrack = dict[str, str | float]

def normalize_sort_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(character for character in decomposed if not "\u0300" <= character <= "\u036f").lower()


def track_sort_key(track: JsonObject) -> tuple[str, ...]:
    values = tuple(str(value) if value is not None else "" for value in (track.get(field) for field in SORT_FIELDS))
    normalized_values = tuple(normalize_sort_text(value) for value in values)
    return (*normalized_values, *values)


def mp3_duration_seconds(path: Path) -> float:
    try:
        return float(MP3(path).info.length)
    except (MutagenError, OSError) as error:
        raise ValueError(f"Could not read MP3 metadata: {path}") from error


def format_length(seconds: float) -> str:
    total_seconds = max(0, int(seconds + 0.5))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes}:{secs:02d}"


def load_manual_tracks() -> list[JsonObject]:
    if not MANUAL_TRACKS_PATH.exists():
        raise FileNotFoundError(f"Manual metadata file not found: {MANUAL_TRACKS_PATH.name}")

    payload = json.loads(MANUAL_TRACKS_PATH.read_text(encoding="utf-8"))
    tracks = payload.get("tracks", payload) if isinstance(payload, dict) else payload
    if not isinstance(tracks, list):
        raise ValueError(f"{MANUAL_TRACKS_PATH.name} must contain a 'tracks' array.")
    if not all(isinstance(track, dict) for track in tracks):
        raise ValueError(f"{MANUAL_TRACKS_PATH.name} must contain only track objects.")
    return cast(list[JsonObject], tracks)


def build_generated_entry(track: JsonObject) -> GeneratedTrack:
    file_value = track.get("file")
    if not isinstance(file_value, str) or not file_value.strip():
        raise ValueError(f"Manual track is missing a 'file' value: {track}")

    file_path = file_value.replace("\\", "/")
    source_path = (ROOT / file_path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Missing audio file for manual track: {source_path}")

    track_id = track.get("id")
    if not isinstance(track_id, str) or not track_id.strip():
        track_id = Path(file_path).stem

    duration_seconds = mp3_duration_seconds(source_path)
    file_size_mb = source_path.stat().st_size / (1024 * 1024)

    return {
        "id": track_id,
        "file": file_path,
        "sizeMB": round(file_size_mb, 2),
        "length": format_length(duration_seconds)
    }


def main() -> None:
    manual_tracks = sorted(load_manual_tracks(), key=track_sort_key)
    if not manual_tracks:
        raise RuntimeError("No track entries were found in the manual metadata file.")

    generated_tracks = [build_generated_entry(track) for track in manual_tracks]

    GENERATED_TRACKS_PATH.write_text(
        json.dumps({"tracks": generated_tracks}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Generated {len(generated_tracks)} track entries in {GENERATED_TRACKS_PATH.name}.")
    for entry in generated_tracks:
        print(f"- {entry['id']} | {entry['file']} | {entry['sizeMB']} MB | {entry['length']}")


if __name__ == "__main__":
    main()
