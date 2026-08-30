from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets"
MANUAL_TRACKS_PATH = ROOT / "song-metadata.json"
GENERATED_TRACKS_PATH = ROOT / "song-generated.json"


def normalize_title(value: str) -> str:
    cleaned = str(value or "").replace("\x00", " ")
    cleaned = re.sub(r"[_-]+", " ", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return "Untitled Song"
    return " ".join(part.capitalize() for part in cleaned.split())


def read_id3_text_frame(data: bytes, frame_id: bytes) -> str:
    offset = 10
    end = len(data)
    while offset + 10 <= end:
        if data[offset:offset + 4] == b"\x00\x00\x00\x00":
            break

        current_id = data[offset:offset + 4]
        if len(current_id) < 4:
            break

        size_bytes = data[offset + 4:offset + 8]
        if len(size_bytes) < 4:
            break

        frame_size = int.from_bytes(size_bytes, byteorder="big")
        if frame_size <= 0:
            break

        body_start = offset + 10
        body_end = body_start + frame_size
        if body_end > end:
            break

        if current_id == frame_id:
            payload = data[body_start:body_end]
            if not payload:
                return ""
            encoding = payload[0]
            text = payload[1:]
            if encoding == 1:
                text = text.decode("utf-16", errors="ignore")
            elif encoding == 2:
                text = text.decode("utf-16-be", errors="ignore")
            else:
                text = text.decode("latin-1", errors="ignore")
            return text.replace("\x00", "").strip()

        offset += 10 + frame_size

    return ""


def read_id3_metadata(path: Path) -> tuple[str, str]:
    try:
        data = path.read_bytes()
    except OSError:
        return normalize_title(path.stem), "Local Collection"

    if len(data) >= 10 and data[:3] == b"ID3":
        tag_size = 0
        for i in range(6, 10):
            tag_size = (tag_size << 7) | (data[i] & 0x7F)
        tag_data = data[10:10 + tag_size]
        title = read_id3_text_frame(tag_data, b"TIT2")
        artist = read_id3_text_frame(tag_data, b"TPE1")
        if title:
            return normalize_title(title), normalize_title(artist) if artist else "Local Collection"

    return normalize_title(path.stem), "Local Collection"


def mp3_duration_seconds(path: Path) -> float:
    data = path.read_bytes()
    if len(data) < 4:
        return 0.0

    offset = 0
    total_samples = 0
    frame_count = 0
    sample_rate = 44100

    while offset + 4 <= len(data):
        if (data[offset] & 0xFF) == 0xFF and (data[offset + 1] & 0xE0) == 0xE0:
            header = int.from_bytes(data[offset:offset + 4], byteorder="big", signed=False)
            version_index = (header >> 19) & 0x3
            layer_index = (header >> 17) & 0x3
            bitrate_index = (header >> 12) & 0xF
            sample_rate_index = (header >> 10) & 0x3
            padding = (header >> 9) & 0x1

            if version_index in (0, 2, 3) and layer_index in (1, 2, 3) and bitrate_index != 15 and sample_rate_index != 3:
                bitrate_table = {
                    3: {1: {1: 32, 2: 40, 3: 48, 4: 56, 5: 64, 6: 80, 7: 96, 8: 112, 9: 128, 10: 160, 11: 192, 12: 224, 13: 256, 14: 320},
                        2: {1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64, 9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160},
                        3: {1: 32, 2: 40, 3: 48, 4: 56, 5: 64, 6: 80, 7: 96, 8: 112, 9: 128, 10: 144, 11: 160, 12: 176, 13: 192, 14: 224}},
                    2: {1: {1: 32, 2: 48, 3: 56, 4: 64, 5: 80, 6: 96, 7: 112, 8: 128, 9: 144, 10: 160, 11: 176, 12: 192, 13: 224, 14: 256},
                        2: {1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64, 9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160},
                        3: {1: 32, 2: 40, 3: 48, 4: 56, 5: 64, 6: 80, 7: 96, 8: 112, 9: 128, 10: 144, 11: 160, 12: 176, 13: 192, 14: 224}},
                    0: {1: {1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64, 9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160},
                        2: {1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64, 9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160},
                        3: {1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64, 9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160}},
                }
                sample_rate_table = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}
                bitrate = bitrate_table.get(version_index, {}).get(layer_index, {}).get(bitrate_index, 0)
                sample_rate = sample_rate_table.get(version_index, [44100, 48000, 32000])[sample_rate_index]
                if bitrate and sample_rate:
                    frame_size = int((144 * bitrate * 1000) / sample_rate + padding)
                    if frame_size <= 0:
                        offset += 1
                        continue
                    samples_per_frame = 1152 if version_index == 3 else 576
                    total_samples += samples_per_frame
                    frame_count += 1
                    offset += max(frame_size, 1)
                    continue

        offset += 1

    if frame_count == 0:
        return 0.0

    return total_samples / sample_rate


def format_length(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def load_manual_tracks() -> list[dict]:
    if not MANUAL_TRACKS_PATH.exists():
        raise FileNotFoundError(f"Manual metadata file not found: {MANUAL_TRACKS_PATH.name}")

    payload = json.loads(MANUAL_TRACKS_PATH.read_text(encoding="utf-8"))
    tracks = payload.get("tracks", payload) if isinstance(payload, dict) else payload
    if not isinstance(tracks, list):
        raise ValueError(f"{MANUAL_TRACKS_PATH.name} must contain a 'tracks' array.")
    return tracks


def build_generated_entry(track: dict, source_path: Path) -> dict:
    file_path = track.get("file") or source_path.relative_to(ROOT).as_posix()
    file_path = file_path.replace("\\", "/")
    duration_seconds = mp3_duration_seconds(source_path)
    file_size_mb = source_path.stat().st_size / (1024 * 1024)

    return {
        "id": track.get("id") or Path(file_path).stem,
        "file": file_path,
        "sizeMB": round(file_size_mb, 2),
        "length": format_length(duration_seconds)
    }


def main() -> None:
    ASSET_DIR.mkdir(exist_ok=True)
    manual_tracks = load_manual_tracks()
    generated_tracks: list[dict] = []

    for track in manual_tracks:
        file_path = track.get("file")
        if not file_path:
            raise ValueError(f"Manual track is missing a 'file' value: {track}")

        source_path = (ROOT / file_path).resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Missing audio file for manual track: {source_path}")

        generated_tracks.append(build_generated_entry(track, source_path))

    if not generated_tracks:
        raise RuntimeError("No track entries were found in the manual metadata file.")

    GENERATED_TRACKS_PATH.write_text(
        json.dumps({"tracks": generated_tracks}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Generated {len(generated_tracks)} track entries in {GENERATED_TRACKS_PATH.name}.")
    for entry in generated_tracks:
        print(f"- {entry['id']} | {entry['file']} | {entry['sizeMB']} MB | {entry['length']}")


if __name__ == "__main__":
    main()
