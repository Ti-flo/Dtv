"""
Patch or restore script.js on the connected Android emulator.

Prepends dtv/scripts/ws_intercept.js to the game's script.js so all
WebSocket messages are logged (logcat or local HTTP server).

The game loads script.js from:
  /data/data/com.ankama.dofustouch/files/files/js/build/script.js

Requires `adb root` access (AVD with Android Studio, or BlueStacks with Magisk root).

Usage:
    python -m dtv.scripts.patch_scriptjs            # apply patch
    python -m dtv.scripts.patch_scriptjs --restore  # restore original
    python -m dtv.scripts.patch_scriptjs --check    # show first 5 lines on device

Detection notes:
    - The Proxy-based interceptor keeps WebSocket.prototype/.name/.toString() intact.
    - No change to game message behaviour (same bytes sent/received).
    - UNKNOWN RISK: the APK's native Java code might hash script.js before
      loading it into the WebView. If the app crashes or refuses to start
      after patching, that's the cause. Nothing we can do without APK decompilation.
    - Logstash telemetry might send file metadata — use a throwaway account on AVD.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

DEVICE_PATH = "/data/data/com.ankama.dofustouch/files/files/js/build/script.js"
BACKUP_PATH = Path(__file__).parent.parent.parent / "data" / "script_backup.js"
INTERCEPT_PATH = Path(__file__).parent / "ws_intercept.js"

SENTINEL = "/* DTV WebSocket interceptor"   # marks a patched file


def adb(*args, check=True, capture=False) -> subprocess.CompletedProcess:
    cmd = ["adb"] + list(args)
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
    )


def adb_root():
    """Ensure adb has root access."""
    result = adb("root", check=False, capture=True)
    if "adbd is already running as root" in result.stdout or "restarting adbd as root" in result.stdout:
        return True
    # BlueStacks: try shell su
    r = adb("shell", "su", "-c", "id", check=False, capture=True)
    if "uid=0" in r.stdout:
        return True
    print("ERROR: adb root not available. On AVD: run `adb root` first.")
    return False


def pull_device(device_path: str, local_path: Path):
    print(f"Pulling {device_path} → {local_path}")
    local_path.parent.mkdir(parents=True, exist_ok=True)
    adb("pull", device_path, str(local_path))


def push_to_device(local_path: Path, device_path: str):
    print(f"Pushing {local_path} → {device_path}")
    adb("push", str(local_path), device_path)
    # Fix permissions (the app needs to read this file)
    adb("shell", "chmod", "644", device_path)


def device_first_line() -> str:
    r = adb("shell", "head", "-c", "200", DEVICE_PATH, check=False, capture=True)
    return r.stdout[:200]


def apply_patch():
    if not INTERCEPT_PATH.exists():
        print(f"ERROR: intercept file not found: {INTERCEPT_PATH}")
        sys.exit(1)

    # Check if already patched
    first = device_first_line()
    if SENTINEL in first:
        print("Already patched (sentinel found). Use --restore first if you want to re-patch.")
        return

    # Pull original to backup
    if not BACKUP_PATH.exists():
        pull_device(DEVICE_PATH, BACKUP_PATH)
        print(f"Backup saved: {BACKUP_PATH} ({BACKUP_PATH.stat().st_size:,} bytes)")
    else:
        print(f"Backup already exists at {BACKUP_PATH} — skipping pull.")

    # Build patched file: intercept + newline + original
    intercept = INTERCEPT_PATH.read_text(encoding="utf-8")
    original = BACKUP_PATH.read_bytes()

    with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as f:
        tmp = Path(f.name)
        f.write(intercept.encode("utf-8"))
        f.write(b"\n\n")
        f.write(original)

    patched_size = tmp.stat().st_size
    print(f"Patched file size: {patched_size:,} bytes (+{patched_size - len(original)} from intercept)")

    push_to_device(tmp, DEVICE_PATH)
    tmp.unlink()

    print("\nPatch applied.")
    print("Now:")
    print("  1. Stop the game if running: adb shell am force-stop com.ankama.dofustouch")
    print("  2. Start the game")
    print("  3a. Logcat mode:  adb logcat | grep '\\[DTV\\]'")
    print("  3b. Fetch mode:   python -m dtv.scripts.ws_capture_server")
    print(f"  4. Restore when done: python -m dtv.scripts.patch_scriptjs --restore")


def restore():
    if not BACKUP_PATH.exists():
        print(f"ERROR: No backup found at {BACKUP_PATH}. Cannot restore.")
        sys.exit(1)

    first = device_first_line()
    if SENTINEL not in first:
        print("Device file does not appear to be patched (sentinel not found).")
        print("Restoring backup anyway...")

    push_to_device(BACKUP_PATH, DEVICE_PATH)
    print("Original script.js restored.")
    print("Force-stop the game and relaunch to pick up the change:")
    print("  adb shell am force-stop com.ankama.dofustouch")


def check():
    print(f"First 300 chars of {DEVICE_PATH}:")
    r = adb("shell", "head", "-c", "300", DEVICE_PATH, check=False, capture=True)
    print(r.stdout)
    if SENTINEL in r.stdout:
        print("→ PATCHED (sentinel found)")
    else:
        print("→ ORIGINAL (no sentinel)")


def main():
    if "--restore" in sys.argv:
        if not adb_root():
            sys.exit(1)
        restore()
    elif "--check" in sys.argv:
        check()
    else:
        if not adb_root():
            sys.exit(1)
        apply_patch()


if __name__ == "__main__":
    main()
