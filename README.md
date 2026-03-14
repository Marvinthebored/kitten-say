# kitten-say

A streaming TTS daemon for [KittenTTS](https://github.com/KittenML/kitten-tts) that eliminates cold-start latency and enables real-time playback with pipelined audio generation.

KittenTTS is a tiny, open-source English TTS model family that runs on CPU — no GPU required. `kitten-say` solves the model load overhead with a persistent daemon that keeps the model hot in memory, serving TTS requests over a Unix socket with zero startup delay after first invocation.

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

First call auto-starts the daemon (a few seconds to load model, cached after first download). Subsequent calls are instant.

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
kitten-say -c paragraph -f book.txt   # chunk by paragraph instead of sentence
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
| `-c, --chunks` | Chunking mode: `sentence`, `paragraph`, `fixed`, `none` | `sentence` |
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
- Sentence-level chunking: plays chunk N while generating chunk N+1
- Zero dependencies beyond Python stdlib (daemon needs `kittentts`)

### Chunking Modes

| Mode | Splits on | Best for |
|------|-----------|----------|
| `sentence` | `.` `!` `?` | General use — natural pauses, good pipelining |
| `paragraph` | Double newline | Long documents with clear paragraph structure |
| `fixed` | ~200 chars | Uniform chunk sizes |
| `none` | No splitting | Short text, maximum coherence |

## Dependencies

### System

| Package | Install | Why |
|---------|---------|-----|
| **Python 3.12+** | `brew install python@3.12` | Runtime (required by kittentts 0.8.1) |
| **espeak-ng** | `brew install espeak-ng` | Phonemizer backend (required by KittenTTS) |
| **sox** | `brew install sox` | Audio playback (`play -q` command) |

### Python

| Package | Install | Why |
|---------|---------|-----|
| **kittentts 0.8.1+** | see Quick Start | TTS model + inference |

All other imports are Python stdlib. The client script has **zero** external Python dependencies.

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
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
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

## Credits

- [KittenTTS](https://github.com/KittenML/kitten-tts) — the model doing the actual work

## License

MIT
