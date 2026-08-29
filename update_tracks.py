from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets"
HTML_PATH = ROOT / "index.html"


def normalize_title(value: str) -> str:
    cleaned = str(value or "").replace("\x00", " ")
    cleaned = re.sub(r"[_-]+", " ", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return "Untitled Song"
    return " ".join(part.capitalize() for part in cleaned.split())


def sanitize_file_stem(title: str, used_names: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", title or "track")
    base = re.sub(r"-+", "-", base).strip("-").lower()
    base = base[:26] if len(base) > 26 else base
    base = base or "track"

    candidate = base
    counter = 2
    while candidate in used_names:
        candidate = f"{base}-{counter}"
        counter += 1

    used_names.add(candidate)
    return candidate


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

    fallback_title = normalize_title(path.stem)
    return fallback_title, "Local Collection"


def mp3_duration_seconds(path: Path) -> float:
    data = path.read_bytes()
    if len(data) < 4:
        return 0.0

    sample_rate = 44100
    total_samples = 0
    frame_count = 0
    offset = 0

    bitrate_table = {
        3: {1: {0: 0, 1: 32, 2: 40, 3: 48, 4: 56, 5: 64, 6: 80, 7: 96, 8: 112, 9: 128, 10: 160, 11: 192, 12: 224, 13: 256, 14: 320, 15: 0},
            2: {0: 0, 1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64, 9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160, 15: 0},
            3: {0: 0, 1: 32, 2: 40, 3: 48, 4: 56, 5: 64, 6: 80, 7: 96, 8: 112, 9: 128, 10: 144, 11: 160, 12: 176, 13: 192, 14: 224, 15: 0}},
        2: {1: {0: 0, 1: 32, 2: 48, 3: 56, 4: 64, 5: 80, 6: 96, 7: 112, 8: 128, 9: 144, 10: 160, 11: 176, 12: 192, 13: 224, 14: 256, 15: 0},
            2: {0: 0, 1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64, 9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160, 15: 0},
            3: {0: 0, 1: 32, 2: 40, 3: 48, 4: 56, 5: 64, 6: 80, 7: 96, 8: 112, 9: 128, 10: 144, 11: 160, 12: 176, 13: 192, 14: 224, 15: 0}},
        0: {1: {0: 0, 1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64, 9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160, 15: 0},
            2: {0: 0, 1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64, 9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160, 15: 0},
            3: {0: 0, 1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64, 9: 80, 10: 96, 11: 112, 12: 128, 13: 144, 14: 160, 15: 0}},
    }

    sample_rate_table = {
        3: [44100, 48000, 32000],
        2: [22050, 24000, 16000],
        0: [11025, 12000, 8000],
    }

    while offset + 4 <= len(data):
        if (data[offset] & 0xFF) == 0xFF and (data[offset + 1] & 0xE0) == 0xE0:
            header = int.from_bytes(data[offset:offset + 4], byteorder="big", signed=False)
            version_index = (header >> 19) & 0x3
            layer_index = (header >> 17) & 0x3
            bitrate_index = (header >> 12) & 0xF
            sample_rate_index = (header >> 10) & 0x3
            padding = (header >> 9) & 0x1

            if version_index in (0, 2, 3) and layer_index in (1, 2, 3) and bitrate_index != 15 and sample_rate_index != 3:
                version_key = version_index
                bitrate = bitrate_table.get(version_key, {}).get(layer_index, {}).get(bitrate_index, 0)
                sample_rate = sample_rate_table.get(version_key, [44100, 48000, 32000])[sample_rate_index]
                if bitrate and sample_rate:
                    frame_size = int((144 * bitrate * 1000) / sample_rate + padding)
                    if frame_size <= 0:
                        offset += 1
                        continue
                    samples_per_frame = 1152 if version_key == 3 else 576
                    total_samples += samples_per_frame
                    frame_count += 1
                    offset += max(frame_size, 1)
                    continue

        offset += 1

    if frame_count == 0:
        return 0.0

    return total_samples / sample_rate if sample_rate else 0.0


def build_track_entry(path: Path, used_names: set[str]) -> dict:
    title, artist = read_id3_metadata(path)
    file_stem = sanitize_file_stem(title, used_names)
    target_path = path.with_name(f"{file_stem}.mp3")

    if target_path.exists() and target_path != path:
        suffix = 2
        while target_path.exists():
            candidate = f"{file_stem}-{suffix}.mp3"
            target_path = path.with_name(candidate)
            suffix += 1

    if path != target_path:
        path.rename(target_path)

    duration_seconds = mp3_duration_seconds(target_path)
    file_size_bytes = target_path.stat().st_size
    size_mb = file_size_bytes / (1024 * 1024)
    length = f"{int(duration_seconds // 60)}:{int(duration_seconds % 60):02d}"

    return {
        "title": title,
        "artist": artist or "Local Collection",
        "icon": "🎵",
        "file": target_path.relative_to(ROOT).as_posix(),
        "sizeMB": round(size_mb, 2),
        "length": length,
        "accent": "#f6b87c",
        "extra": {
            "source": "Local MP3 file in the assets folder",
            "path": target_path.relative_to(ROOT).as_posix(),
            "format": "MP3",
            "notes": "Generated from the current files in the assets folder.",
            "tags": ["minimal", "lo-fi", "desktop-friendly"],
            "license": "Personal / demo use",
            "sizeMB": round(size_mb, 2),
            "length": length,
        },
    }


def write_tracks_into_html(tracks: list[dict]) -> None:
    html_text = HTML_PATH.read_text(encoding="utf-8")
    start_marker = "const tracks = ["
    start_index = html_text.index(start_marker)
    end_index = html_text.index("];", start_index)
    replacement = "const tracks = " + json.dumps(tracks, ensure_ascii=False, indent=2) + ";"
    updated_html = html_text[:start_index] + replacement + html_text[end_index + 2:]
    HTML_PATH.write_text(updated_html, encoding="utf-8")


def main() -> None:
    ASSET_DIR.mkdir(exist_ok=True)
    used_names: set[str] = set()
    entries: list[dict] = []

    for mp3_path in sorted(ASSET_DIR.glob("*.mp3")):
        entries.append(build_track_entry(mp3_path, used_names))

    if not entries:
        raise RuntimeError(f"No .mp3 files were found in {ASSET_DIR}.")

    write_tracks_into_html(entries)
    print(f"Updated {len(entries)} song entries in {HTML_PATH.name}.")
    for entry in entries:
        print(f"- {entry['title']} | {entry['file']} | {entry['sizeMB']} MB | {entry['length']}")


if __name__ == "__main__":
    main()
