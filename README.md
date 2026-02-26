# kitten-say

A streaming TTS daemon for [KittenTTS](https://github.com/KittenML/kitten-tts) that eliminates cold-start latency and enables real-time playback with pipelined audio generation.

KittenTTS is a tiny (15M params) English TTS model that runs at ~2x realtime on Apple Silicon — but has a 6+ second model load time. `kitten-say` solves this with a persistent daemon that keeps the model hot in memory, serving TTS requests over a Unix socket with zero startup delay after first invocation.

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

- **Daemon** loads the model once and stays resident (~80MB RAM)
- **Client** connects, sends text, receives PCM frames, pipes to audio player
- **Pipelining**: audio plays while the next chunk is still generating — no gaps between sentences

## Quick Start

```bash
# Install dependencies
pip install kittentts
brew install espeak-ng sox  # macOS — sox provides the 'play' command

# Install kitten-say
sudo bash install.sh

# Use it
kitten-say "Hello world"
```

First call auto-starts the daemon (~6s to load model, cached after first download). Subsequent calls are instant.

## Usage

```
kitten-say "Hello world"              # speak text
kitten-say -v Luna "Hello world"      # pick a voice
kitten-say -f report.txt              # read a file
echo "Hello" | kitten-say             # pipe from stdin
kitten-say -o output.wav "text"       # save to WAV instead of playing
kitten-say -d 0.5 "Hello"            # 500ms delay before playback (BT speakers)
kitten-say -c paragraph -f book.txt   # chunk by paragraph instead of sentence
kitten-say --voices                   # list available voices
kitten-say --stop                     # shut down daemon
kitten-say -h                         # full help
```

## Voices

Eight built-in voices: **Bella**, **Jasper** (default), **Luna**, **Bruno**, **Rosie**, **Hugo**, **Kiki**, **Leo**

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `-v, --voice` | Voice name | `Jasper` |
| `-f, --file` | Read text from file | — |
| `-o, --output` | Save to WAV file instead of playing | — |
| `-d, --delay` | Seconds of silence before playback (for BT/USB speaker wake) | `0.2` |
| `-c, --chunks` | Chunking mode: `sentence`, `paragraph`, `fixed`, `none` | `sentence` |
| `--voices` | List available voices | — |
| `--stop` | Shut down the daemon | — |

## Architecture

### Daemon (`kitten-tts-daemon`)

- Loads KittenTTS model once, keeps it in memory
- Listens on Unix socket (`/tmp/kitten-tts.sock`)
- Serializes generation requests (model isn't thread-safe)
- Accepts connections from any local user
- Protocol: JSON request line → JSON header line → binary PCM frames (4-byte big-endian length prefix) → zero-length sentinel

### Client (`kitten-say`)

- Auto-starts daemon if not running (hybrid lifecycle)
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
| **Python 3.9+** | (usually pre-installed) | Runtime |
| **espeak-ng** | `brew install espeak-ng` | Phonemizer backend (required by KittenTTS) |
| **sox** | `brew install sox` | Audio playback (`play -q` command) |

### Python

| Package | Install | Why |
|---------|---------|-----|
| **kittentts** | `pip install kittentts` | TTS model + inference |

All other imports are Python stdlib. The client script has **zero** external Python dependencies.

### Tested On

- macOS (Apple Silicon M1 Max) — ~2x realtime generation
- Python 3.12 with kittentts in a virtualenv

### Linux Notes

Should work on Linux with `espeak-ng` and `sox` installed via your package manager. The client falls back to `play` (sox) if `afplay` isn't available. Untested — PRs welcome.

## Install

```bash
git clone https://github.com/Marvinthebored/kitten-say.git
cd kitten-say
pip install kittentts
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

On Apple Silicon (M1 Max):

| Metric | Value |
|--------|-------|
| Model load (first run, downloading) | ~80s |
| Model load (cached) | ~6s |
| Generation speed | ~2x realtime |
| RAM usage (idle) | ~80MB |
| Model size (ONNX) | ~78MB |
| Audio quality | 24kHz, mono |

## Protocol

For anyone wanting to build alternative clients:

1. Connect to Unix socket at `/tmp/kitten-tts.sock`
2. Send JSON line: `{"text": "Hello", "voice": "Jasper", "chunk_mode": "sentence"}\n`
3. Receive JSON header: `{"status": "streaming", "chunks": N, "sample_rate": 24000}\n`
4. Receive N PCM frames: 4-byte big-endian length + float32 PCM data
5. End sentinel: 4-byte zero (`\x00\x00\x00\x00`)

Other commands: `{"cmd": "ping"}`, `{"cmd": "voices"}`, `{"cmd": "shutdown"}`

## Credits

- [KittenTTS](https://github.com/KittenML/kitten-tts) — the model doing the actual work
- Built for use with [OpenClaw](https://github.com/openclaw/openclaw)

## License

MIT
