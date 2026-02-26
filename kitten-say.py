#!/usr/bin/env python3
"""kitten-say — speak text using local KittenTTS.

Usage:
  kitten-say "Hello world"              speak text
  kitten-say -v Luna "Hello world"      pick a voice
  kitten-say -o out.wav "Hello world"   save to file
  echo "Hello" | kitten-say             pipe from stdin
  kitten-say --voices                   list available voices
  kitten-say --stop                     shut down daemon

Voices: Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo
"""

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import wave

# === Defaults (tune these) ===
DEFAULT_VOICE = "Jasper"
DEFAULT_CHUNK_MODE = "sentence"     # sentence | paragraph | fixed | none
DEFAULT_DELAY = 0.2                 # seconds of silence before playback (for BT/USB speaker wake)
SOCKET_PATH = "/tmp/kitten-tts.sock"
SAMPLE_RATE = 24000
DAEMON_TIMEOUT = 90                 # max seconds to wait for daemon startup
PLAYER = "auto"                     # auto | afplay | play

# Path to daemon script and venv python
DAEMON_SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "kitten-tts-daemon")
VENV_PYTHON = "/Users/sanae/qwen-tts-env/bin/python3"

# ── Helpers ──────────────────────────────────────────────────────────────────

def find_python():
    """Find the Python interpreter that has kittentts."""
    if VENV_PYTHON and os.path.exists(VENV_PYTHON):
        return VENV_PYTHON
    # Try common locations
    candidates = [
        os.path.expanduser("~/qwen-tts-env/bin/python3"),
        os.path.expanduser("~/tts-env/bin/python3"),
        "/usr/local/bin/python3",
        "python3",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "python3"


def connect(socket_path: str, timeout: float = 5.0) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(socket_path)
    return sock


def daemon_running(socket_path: str) -> bool:
    try:
        s = connect(socket_path, timeout=2.0)
        s.sendall(json.dumps({"cmd": "ping"}).encode() + b"\n")
        resp = s.recv(1024)
        s.close()
        return b"ok" in resp
    except Exception:
        return False


def start_daemon(socket_path: str) -> bool:
    """Launch daemon in background, wait until ready."""
    python = find_python()
    daemon = DAEMON_SCRIPT

    if not os.path.exists(daemon):
        print(f"Error: daemon not found at {daemon}", file=sys.stderr)
        return False

    print("Starting daemon (first-run model load may take a moment)...", file=sys.stderr)

    # Launch detached
    log = open("/tmp/kitten-tts-daemon.log", "a")
    subprocess.Popen(
        [python, daemon, "-s", socket_path],
        stdout=log, stderr=log,
        start_new_session=True,
    )

    # Wait for socket
    start = time.time()
    while time.time() - start < DAEMON_TIMEOUT:
        if daemon_running(socket_path):
            return True
        time.sleep(0.5)

    print("Error: daemon failed to start. Check /tmp/kitten-tts-daemon.log", file=sys.stderr)
    return False


def ensure_daemon(socket_path: str) -> bool:
    if daemon_running(socket_path):
        return True
    return start_daemon(socket_path)


def recv_json(sock: socket.socket) -> dict:
    data = b""
    while b"\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("daemon closed connection")
        data += chunk
    return json.loads(data.decode().strip())


def recv_frame(sock: socket.socket):
    """Receive one PCM frame. Returns bytes or None for end sentinel."""
    length_bytes = b""
    while len(length_bytes) < 4:
        chunk = sock.recv(4 - len(length_bytes))
        if not chunk:
            return None
        length_bytes += chunk

    length = struct.unpack(">I", length_bytes)[0]
    if length == 0:
        return None

    pcm = b""
    while len(pcm) < length:
        chunk = sock.recv(min(65536, length - len(pcm)))
        if not chunk:
            return None
        pcm += chunk
    return pcm


def find_player():
    """Find audio player command."""
    if PLAYER != "auto":
        return PLAYER
    # Prefer sox play (quieter, more reliable with temp files)
    for p in ("/opt/homebrew/bin/play", "/usr/local/bin/play", "/usr/bin/play"):
        if os.path.exists(p):
            return p
    # macOS fallback
    if os.path.exists("/usr/bin/afplay"):
        return "afplay"
    return "play"


def play_wav(path: str):
    """Play a WAV file, blocking until done."""
    player = find_player()
    cmd = [player]
    if "play" in player:
        cmd.append("-q")  # quiet mode for sox
    cmd.append(path)
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write_wav(path: str, pcm_bytes: bytes, sample_rate: int):
    """Write PCM float32 to 16-bit WAV."""
    import array
    # Convert float32 to int16
    n_samples = len(pcm_bytes) // 4
    floats = struct.unpack(f"{n_samples}f", pcm_bytes)
    int16s = array.array("h", [max(-32768, min(32767, int(s * 32767))) for s in floats])

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16s.tobytes())


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_voices(socket_path: str):
    if not ensure_daemon(socket_path):
        return 1
    sock = connect(socket_path)
    sock.sendall(json.dumps({"cmd": "voices"}).encode() + b"\n")
    resp = recv_json(sock)
    sock.close()
    for v in resp.get("voices", []):
        print(f"  {v}")
    return 0


def cmd_stop(socket_path: str):
    if not daemon_running(socket_path):
        print("Daemon not running.")
        return 0
    sock = connect(socket_path)
    sock.sendall(json.dumps({"cmd": "shutdown"}).encode() + b"\n")
    sock.close()
    print("Daemon stopped.")
    return 0


def cmd_speak(text: str, voice: str, chunk_mode: str, output: str, socket_path: str, delay: float = 0.0):
    if not text.strip():
        print("Nothing to say.", file=sys.stderr)
        return 1

    if not ensure_daemon(socket_path):
        return 1

    sock = connect(socket_path, timeout=60.0)
    req = {"text": text, "voice": voice, "chunk_mode": chunk_mode}
    sock.sendall(json.dumps(req).encode() + b"\n")

    header = recv_json(sock)
    if "error" in header:
        print(f"Error: {header['error']}", file=sys.stderr)
        sock.close()
        return 1

    sample_rate = header.get("sample_rate", SAMPLE_RATE)
    all_pcm = b""
    chunk_idx = 0
    prev_player = None

    while True:
        frame = recv_frame(sock)
        if frame is None:
            break
        chunk_idx += 1

        if output:
            # Collecting for file output
            all_pcm += frame
        else:
            # Prepend silence for speaker wake on first chunk
            if chunk_idx == 1 and delay > 0:
                silence_samples = int(sample_rate * delay)
                frame = b'\x00' * (silence_samples * 4) + frame

            # Stream: play each chunk immediately
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()
            write_wav(tmp_path, frame, sample_rate)

            # Wait for previous chunk to finish playing
            if prev_player is not None:
                prev_player.wait()

            # Start playback
            player = find_player()
            cmd = [player]
            if "play" in player:
                cmd.append("-q")
            cmd.append(tmp_path)
            prev_player = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    sock.close()

    # Wait for last chunk
    if prev_player is not None:
        prev_player.wait()

    # Clean up temp files (best effort)
    # They're in /tmp, OS will clean eventually

    if output:
        write_wav(output, all_pcm, sample_rate)
        duration = len(all_pcm) / 4 / sample_rate
        print(f"Saved {output} ({duration:.1f}s)")

    return 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="kitten-say",
        description="Speak text using local KittenTTS.",
        epilog="Voices: Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("text", nargs="?", help="text to speak (or pipe via stdin)")
    p.add_argument("-v", "--voice", default=DEFAULT_VOICE, help=f"voice (default: {DEFAULT_VOICE})")
    p.add_argument("-f", "--file", dest="infile", help="read text from file")
    p.add_argument("-d", "--delay", type=float, default=DEFAULT_DELAY,
                    help="seconds of silence before playback (e.g. 0.3 for BT speakers)")
    p.add_argument("-c", "--chunks", default=DEFAULT_CHUNK_MODE,
                    choices=["sentence", "paragraph", "fixed", "none"],
                    help=f"chunking mode (default: {DEFAULT_CHUNK_MODE})")
    p.add_argument("-o", "--output", help="save to WAV file instead of playing")
    p.add_argument("-s", "--socket", default=SOCKET_PATH, help=argparse.SUPPRESS)
    p.add_argument("--voices", action="store_true", help="list available voices")
    p.add_argument("--stop", action="store_true", help="shut down the daemon")

    args = p.parse_args()

    if args.voices:
        return cmd_voices(args.socket)
    if args.stop:
        return cmd_stop(args.socket)

    # Get text from arg, file, or stdin
    text = args.text
    if text is None and args.infile:
        with open(args.infile, "r") as f:
            text = f.read()
    if text is None:
        if sys.stdin.isatty():
            p.print_help()
            return 0
        text = sys.stdin.read()

    return cmd_speak(text, args.voice, args.chunks, args.output, args.socket, args.delay)


if __name__ == "__main__":
    raise SystemExit(main())
