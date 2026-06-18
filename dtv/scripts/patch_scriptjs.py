"""
Patch or restore script.js on the connected Android emulator.

Prepends dtv/scripts/ws_intercept.js to the game's script.js so all
WebSocket messages are logged (logcat or local HTTP server).

The game loads script.js from:
  /data/data/com.ankama.dofustouch/files/files/js/build/script.js

Requires root-level adb. AVD (Android Studio) is the target: `adb root` makes
adbd run as root so pull/push to app-private storage works directly.
NOTE: on BlueStacks adbd is NOT root — pull/push to /data/data/... will fail
with permission denied; you'd need a `su -c "cp ..."` staging dance instead.
Use AVD for patching.

Usage:
    python -m dtv.scripts.patch_scriptjs            # apply patch
    python -m dtv.scripts.patch_scriptjs --restore  # restore original
    python -m dtv.scripts.patch_scriptjs --check    # show current state on device

BEFORE patching, try the zero-modification path — if the WebView is debuggable,
you don't need to touch script.js at all (defeats native-hash AND re-download
risks). Probe it:
    adb shell cat /proc/net/unix | grep -a devtools
If you see a "@webview_devtools_remote_<pid>" socket, open chrome://inspect on
the host, click "inspect", and paste the ws_intercept.js IIFE into the console
of the page BEFORE login. Release builds usually disable this, so this script
is the fallback.

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
    # Permissions: world-readable so the app's uid can read a root-owned file
    adb("shell", "chmod", "644", device_path)
    # SELinux: an adb-pushed file keeps the shell's context, not app_data_file.
    # Under enforcing SELinux the app can't read it → silent failure that looks
    # like a native integrity check. restorecon relabels it to the dir's context.
    adb("shell", "restorecon", device_path, check=False)


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

    # Verify the patch actually landed on the device
    if SENTINEL not in device_first_line():
        print("\nWARNING: sentinel not found after push — patch may not have taken.")
        print("Check adb root access and the device path.")
        return

    print("\nPatch applied and verified on device.")
    print("Now:")
    print("  1. Start the game.")
    print("  2a. Logcat mode:  adb logcat | grep '\\[DTV\\]'")
    print("  2b. Fetch mode:   python -m dtv.scripts.ws_capture_server")
    print("  3. Restore when done: python -m dtv.scripts.patch_scriptjs --restore")
    print("\nIMPORTANT: the game may re-download script.js on launch and clobber")
    print("the patch. If you see no [DTV] lines, the file was overwritten — run")
    print("--check; if it shows ORIGINAL, the app re-fetched it. Workaround: launch")
    print("once to let it finish updating, force-stop, patch, then launch offline")
    print("(airplane mode on, or block dofustouch.cdn.ankama.com).")


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
