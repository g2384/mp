# MP

A minimal local music player.

## Regenerate track data

Install the metadata dependency and run the generator from this directory:

```powershell
python -m pip install -r requirements.txt
python update_tracks.py
```

The script reads `song-metadata.json`, validates each referenced MP3, and rewrites
`song-generated.json` in deterministic artist-then-title order.
The player reads that generated file when it loads the playlist.
