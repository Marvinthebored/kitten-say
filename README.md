# kitten-say

A streaming TTS daemon for [KittenTTS](https://github.com/KittenML/kitten-tts) that keeps the model hot in memory and plays audio chunk-by-chunk over a simple Unix-socket protocol.

KittenTTS is a tiny, open-source English TTS model family that runs on CPU — no GPU required. `kitten-say` solves the model-load overhead with a persistent daemon that keeps the model resident between calls.

## Models

Three model sizes, all sounding surprisingly good:

| Model | Params | Size | Speed (M1 Max) | Speed (Intel i7) | Best for |
|-------|--------|------|-----------------|-------------------|----------|
| **nano** | 14M | <25MB | **0.08x** (12.5x RT) | **0.13x** (7.9x RT) | Real-time, edge, IoT |
| **micro** | 40M | ~40MB | ~0.25x | ~0.45x | Balanced |
| **mini** | 80M | ~79MB | 0.51x (2x RT) | 0.89x | Highest quality, narration |

All three produce natural-sounding speech. The quality difference between nano and mini is primarily in audio fidelity (compression artifacts), not voice quality (cadence, intonation, naturalness). For most uses, nano is indistinguishable.

## How It Works

```
┌──────────────┐     Unix Socket      ┌──────────────────┐
│  kitten-say   │ ──── JSON req ────▶ │  kitten-tts-daemon │
│  (client)     │ ◀── PCM frames ─── │  (model in memory) │
└──────┬───────┘                      └──────────────────┘
       │
       ▼
   ┌────────┐
   │ play/  │  ← streams each chunk as it's generated
   │ afplay │    (chunk N plays while chunk N+1 generates)
   └────────┘
```

- **Daemon** loads the model once and stays resident
- **Client** connects, sends text, receives PCM frames, pipes to audio player
- **Pipelining**: audio plays while the next chunk is still generating — no gaps between sentences
- **Auto model switching**: requesting a different model gracefully restarts the daemon

## Quick Start

```bash
# Install dependencies
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
brew install espeak-ng sox  # macOS — sox provides the 'play' command

# Install kitten-say
sudo bash install.sh

# Use it
kitten-say "Hello world"

# Use the fastest model
kitten-say -m nano "Hello world"
```

First call auto-starts the daemon (a few seconds to load model, cached after first download). Subsequent calls skip model load, though the first spoken chunk still costs real synthesis time.

## Usage

```
kitten-say "Hello world"              # speak text (default: mini model)
kitten-say -m nano "Hello world"      # use nano model (fastest)
kitten-say -m micro "Hello world"     # use micro model (balanced)
kitten-say -v Luna "Hello world"      # pick a voice
kitten-say -f report.txt              # read a file
echo "Hello" | kitten-say             # pipe from stdin
kitten-say -o output.wav "text"       # save to WAV instead of playing
kitten-say -d 0.5 "Hello"            # 500ms delay before playback (BT speakers)
kitten-say -s "Hello"                # native KittenTTS streaming (default on)
kitten-say --no-stream "Hello"       # force legacy/manual chunking
kitten-say -c paragraph --no-stream -f book.txt
kitten-say --voices                   # list available voices
kitten-say --info                     # show daemon status and loaded model
kitten-say --stop                     # shut down daemon
kitten-say -h                         # full help
```

### Switching Models

The daemon auto-restarts when you switch models:

```bash
kitten-say -m nano "Quick response"    # starts daemon with nano
kitten-say -m mini "Quality narration" # restarts daemon with mini
kitten-say --info                      # shows which model is loaded
```

## Voices

Eight built-in voices: **Bella**, **Jasper** (default), **Luna**, **Bruno**, **Rosie**, **Hugo**, **Kiki**, **Leo**

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `-m, --model` | Model: `nano`, `micro`, `mini`, or full HF id | `mini` |
| `-v, --voice` | Voice name | `Jasper` |
| `-f, --file` | Read text from file | — |
| `-o, --output` | Save to WAV file instead of playing | — |
| `-d, --delay` | Seconds of silence before playback (for BT/USB speaker wake) | `0.2` |
| `-s, --stream` | Use KittenTTS native `generate_stream()` path | on |
| `--no-stream` | Disable native streaming and use kitten-say manual chunking | off |
| `-c, --chunks` | Chunking mode when `--no-stream`: `sentence`, `paragraph`, `fixed`, `none` | `sentence` |
| `--voices` | List available voices | — |
| `--info` | Show daemon status and loaded model | — |
| `--stop` | Shut down the daemon | — |

## Architecture

### Daemon (`kitten-tts-daemon`)

- Loads KittenTTS model once, keeps it in memory
- Listens on Unix socket (`/tmp/kitten-tts.sock`)
- Writes `.model` metadata file so the client knows which model is loaded
- Serializes generation requests (model isn't thread-safe)
- Accepts connections from any local user
- Protocol: JSON request line → JSON header line → binary PCM frames (4-byte big-endian length prefix) → zero-length sentinel

### Client (`kitten-say`)

- Auto-starts daemon if not running (hybrid lifecycle)
- Auto-restarts daemon if requested model differs from loaded model
- Streams PCM frames to audio player as they arrive
- Can request either native KittenTTS streaming or legacy/manual chunking
- Legacy/manual mode still plays chunk N while generating chunk N+1
- Zero dependencies beyond Python stdlib (daemon needs `kittentts`)

### Chunking Modes

| Mode | Splits on | Best for |
|------|-----------|----------|
| `sentence` | `.` `!` `?` | General use — natural pauses, good pipelining |
| `paragraph` | Double newline | Long documents with clear paragraph structure |
| `fixed` | ~200 chars | Uniform chunk sizes |
| `none` | No splitting | Short text, maximum coherence |

These modes apply only to `--no-stream`. Native KittenTTS streaming currently uses its own internal sentence-style splitting.

## Dependencies

### System

| Package | Install | Why |
|---------|---------|-----|
| **Python 3.12+** | `brew install python@3.12` | Runtime |
| **espeak-ng** | `brew install espeak-ng` | Phonemizer backend (required by KittenTTS) |
| **sox** | `brew install sox` | Audio playback (`play -q` command) |

### Python

| Package | Install | Why |
|---------|---------|-----|
| **kittentts** (prefer GitHub main) | see Quick Start | TTS model + inference |

All other imports are Python stdlib. The client script has **zero** external Python dependencies.

If you are upgrading an older 0.8.1-era environment, pin `numpy<2` before importing the old stack. Some older `spacy`/`misaki` baggage was compiled against NumPy 1.x and breaks under NumPy 2.x. Current GitHub main removed `misaki`, but dirty upgraded venvs can still carry the old conflict.

### Tested On

- macOS (Apple Silicon M1 Max) — nano: 12.5x realtime, mini: 2x realtime
- macOS (Intel i7 2015 MBP) — nano: 7.9x realtime, mini: ~1.1x realtime
- Python 3.12 with kittentts 0.8.1

### Linux Notes

Should work on Linux with `espeak-ng` and `sox` installed via your package manager. The client falls back to `play` (sox) if `afplay` isn't available. Untested — PRs welcome.

## Install

```bash
git clone https://github.com/Marvinthebored/kitten-say.git
cd kitten-say
pip install --upgrade "numpy<2"
pip install --upgrade "git+https://github.com/KittenML/KittenTTS.git"
brew install espeak-ng sox   # macOS
sudo bash install.sh
```

The install script places three files in `/usr/local/bin/`:

| File | What |
|------|------|
| `kitten-say` | Shell wrapper (sets Python interpreter) |
| `kitten-say.py` | Client script |
| `kitten-tts-daemon` | Daemon script |

### Customising the Python Path

The install script hardcodes a virtualenv Python path in the wrapper. Edit `/usr/local/bin/kitten-say` if your venv is elsewhere:

```bash
#!/bin/bash
exec /path/to/your/venv/bin/python3 /usr/local/bin/kitten-say.py "$@"
```

## Daemon Lifecycle

**Hybrid mode** — the daemon is not always-on. It starts on first `kitten-say` invocation and stays running until you explicitly stop it:

```bash
kitten-say --stop
```

This keeps the model warm for rapid successive calls without cluttering your process list when you don't need TTS.

## Performance

### Apple Silicon (M1 Max)

| Model | Load (cached) | Generate (5s audio) | RT Factor | RAM |
|-------|---------------|---------------------|-----------|-----|
| nano | ~4s | 0.42s | 0.08x | ~30MB |
| mini | ~3s | 2.38s | 0.51x | ~80MB |

### Intel (2015 MBP i7)

| Model | Load (cached) | Generate (5s audio) | RT Factor | RAM |
|-------|---------------|---------------------|-----------|-----|
| nano | ~14s | 0.64s | 0.13x | ~30MB |
| mini | ~15s | 4.12s | 0.89x | ~80MB |

Audio: 24kHz, mono, float32 PCM (converted to 16-bit WAV for playback).

## Protocol

For anyone wanting to build alternative clients:

1. Connect to Unix socket at `/tmp/kitten-tts.sock`
2. Send JSON line: `{"text": "Hello", "voice": "Jasper", "chunk_mode": "sentence"}\n`
3. Receive JSON header: `{"status": "streaming", "chunks": N, "sample_rate": 24000}\n`
4. Receive N PCM frames: 4-byte big-endian length + float32 PCM data
5. End sentinel: 4-byte zero (`\x00\x00\x00\x00`)

Commands: `{"cmd": "ping"}`, `{"cmd": "voices"}`, `{"cmd": "info"}`, `{"cmd": "shutdown"}`

The `info` command returns: `{"model": "KittenML/kitten-tts-nano-0.8", "voices": [...], "pid": 12345}`

## 2026-03-27 Update / Ground Truth

Today we re-checked this stack against the live scripts and the upgraded KittenTTS build, because memory and reality had diverged in a few annoying ways. The short version:

- **Native streaming works**: the daemon can now request KittenTTS `generate_stream()` and the client exposes that as default behavior.
- **`--no-stream` keeps the old path**: manual chunking remains available for A/B testing and debugging.
- **The practical difference is smaller than expected**: current KittenTTS `generate_stream()` and `generate()` both call the same internal `chunk_text()` helper. The stream version just yields each chunk instead of concatenating them.
- **Chunking is still sentence-style**: upstream currently splits with `re.split(r'[.!?]+', text)` and then word-splits anything over ~400 chars. So cadence differences versus our own sentence chunking may be negligible.
- **Named voices now work across model tiers** on the upgraded GitHub-main build. Earlier assumptions that nano only accepted `expr-voice-*` were true for an older package state, not the current one.
- **Model switching is real**: nano/micro/mini do switch correctly, but the most obvious difference can be pacing / pause length rather than a cartoonishly different timbre.

### Operational gotchas we hit

- **Old client ↔ new daemon mismatch** is confusing. If only one side is updated, the flags may appear to work while silently exercising the wrong code path.
- **Stale daemon metadata** caused earlier confusion about which model was really loaded. The client relies on the daemon's `.model` file; old daemons without that metadata muddy the water.
- **`/tmp/kitten-tts-daemon.log` permissions matter** when different local users start the daemon (`marvin` vs `sanae`). The client now tries to make the log world-writable before spawning the daemon.
- **`--stop` only works if you're talking to the right daemon**. If you have multiple versions floating around in different paths, kill the stray process and restart cleanly.

### What changed in this repo

- Added native-stream request plumbing between client and daemon.
- Added `--no-stream` to force legacy/manual chunking.
- Kept model switching (`nano` / `micro` / `mini`) and info reporting.
- Documented the upstream chunking reality instead of pretending it is magic.

### Performance reminder

On both MarvinMBP (Intel) and M1 hardware, all three models are still effectively real-time once playback starts. The main latency remains **time to first chunk**, not total throughput.

## Credits

- [KittenTTS](https://github.com/KittenML/kitten-tts) — the model doing the actual work

## License

MIT
