#!/usr/bin/env python3
"""
agent_pc.backup_&_restore — এজেন্টের পার্সোনাল কম্পিউটারের সম্পূর্ণ
ব্যাকআপ ও পুনরুদ্ধার সিস্টেম।

কী কী ব্যাকআপ হয়:
  1. User files       → ~/Documents, ~/Projects, ~/Downloads, ~/Desktop
  2. App configs      → ~/.mozilla, ~/.config, ~/.local/share
  3. Shell / dotfiles → ~/.bashrc, ~/.profile, ~/.gitconfig
  4. XFCE settings    → xfconf-query দিয়ে captured (wallpaper, panel, theme)
  5. Installed pkgs   → apt/pip/npm এর manual list
  6. Running session  → AT-SPI থেকে কোন app খোলা ছিল, কোন file

কীভাবে backup হয়:
  → সব কিছু tar.gz আর্কাইভে প্যাক হয়
  → HF Dataset (agent_pc) এ upload হয় (huggingface_hub দিয়ে)
  → Local fallback: /agent/backups/

কখন চলে:
  → Periodic: প্রতি ৫ মিনিটে (থ্রেড)
  → Manual: `python -m agent_pc.backup_&_restore backup`
  → On shutdown: SIGTERM handler

কীভাবে restore হয়:
  → pc_setup.py startup-এ এই ফাইলের `restore()` কল করে
  → HF Dataset থেকে latest snapshot download
  → ফাইল extract
  → Packages re-install
  → XFCE settings re-apply
  → Session re-launch
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════

HOME = Path(os.environ.get("HOME", "/home/user"))
AGENT_ROOT = Path("/agent")

# Local backup directory (fallback + staging)
BACKUP_DIR = AGENT_ROOT / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# HF Dataset config
HF_DATASET_REPO = os.environ.get("HF_BACKUP_DATASET", "your-username/agent_pc")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
HF_BACKUP_SUBDIR = "agent_pc_snapshots"

# Backup interval
BACKUP_INTERVAL_SECONDS = int(os.environ.get("BACKUP_INTERVAL_SECONDS", "300"))

# Paths to include in backup (relative to HOME)
BACKUP_PATHS = [
    # User files
    "Documents",
    "Projects",
    "Downloads",
    "Desktop",
    "Pictures",
    "Music",
    "Videos",
    # App configs
    ".mozilla",           # Firefox (bookmarks, history, cookies, logins)
    ".config",            # XFCE, VS Code, LibreOffice settings
    ".local/share",       # app data (recent files, plugins)
    ".thunderbird",       # email (if used)
    # Shell / dotfiles
    ".bashrc",
    ".profile",
    ".bash_profile",
    ".bash_aliases",
    ".gitconfig",
    ".ssh",               # ⚠️ SSH keys (careful!)
    # Custom
    "workspace",          # anything the agent created here
]

# Paths to EXCLUDE from backup
EXCLUDE_PATTERNS = [
    ".cache",
    ".local/share/Trash",
    ".local/share/recently-used.xbel",
    "node_modules",
    "__pycache__",
    "*.pyc",
    ".npm",
    ".yarn",
    "*.log",
    ".dbus_env",
    ".Xauthority",
    ".xsession-errors",
    ".bash_history",
    ".python_history",
    # Secrets (never backup)
    ".env",
    ".aws",
    ".config/gcloud",
    ".docker/config.json",
    ".netrc",
    ".huggingface/token",   # HF token — never backup!
]

# Session restore commands (app name → launch command)
APP_COMMANDS = {
    "Firefox":            "firefox-esr",
    "firefox-esr":        "firefox-esr",
    "Firefox ESR":        "firefox-esr",
    "Code":               "code",
    "Visual Studio Code": "code",
    "soffice":            "libreoffice",
    "LibreOffice":        "libreoffice",
    "LibreOffice Writer": "libreoffice --writer",
    "LibreOffice Calc":   "libreoffice --calc",
    "Thunar":             "thunar",
    "xfce4-terminal":     "xfce4-terminal",
    "Terminal":           "xfce4-terminal",
}


# ═══════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[backup {ts}] {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════
# HF Dataset upload / download
# ═══════════════════════════════════════════════════════════════════

def _hf_upload_file(local_path: Path, remote_name: str) -> bool:
    """HF Dataset-এ একটা ফাইল upload করো।"""
    if not HF_TOKEN:
        log("⚠️ HF_TOKEN নেই — শুধু local backup")
        return False
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=HF_TOKEN)
        api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=f"{HF_BACKUP_SUBDIR}/{remote_name}",
            repo_id=HF_DATASET_REPO,
            repo_type="dataset",
        )
        log(f"✅ HF upload: {remote_name}")
        return True
    except Exception as e:
        log(f"❌ HF upload failed: {e}")
        return False


def _hf_download_file(remote_name: str, local_path: Path) -> bool:
    """HF Dataset থেকে একটা ফাইল download করো।"""
    if not HF_TOKEN:
        return False
    try:
        from huggingface_hub import hf_hub_download
        downloaded = hf_hub_download(
            repo_id=HF_DATASET_REPO,
            filename=f"{HF_BACKUP_SUBDIR}/{remote_name}",
            repo_type="dataset",
            token=HF_TOKEN,
            local_dir=str(local_path.parent),
        )
        # Move to expected location
        shutil.move(downloaded, str(local_path))
        log(f"✅ HF download: {remote_name}")
        return True
    except Exception as e:
        log(f"⚠️ HF download failed: {e}")
        return False


def _hf_list_snapshots() -> list[str]:
    """HF Dataset-এ কী কী snapshot আছে।"""
    if not HF_TOKEN:
        return []
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=HF_TOKEN)
        files = api.list_repo_files(
            repo_id=HF_DATASET_REPO,
            repo_type="dataset",
        )
        prefix = f"{HF_BACKUP_SUBDIR}/"
        return sorted(
            [f[len(prefix):] for f in files if f.startswith(prefix)],
            reverse=True,   # newest first
        )
    except Exception as e:
        log(f"⚠️ HF list failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
# Package list capture
# ═══════════════════════════════════════════════════════════════════

def capture_packages(output_dir: Path) -> dict:
    """Installed packages capture করো (apt, pip, npm, snap)।"""
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {}

    # APT — manual-installed only
    try:
        r = subprocess.run(
            ["bash", "-c",
             "apt-mark showmanual 2>/dev/null || "
             "comm -23 <(apt-mark showmanual | sort) <(apt-mark showauto | sort)"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0 and r.stdout.strip():
            apt_file = output_dir / "apt-manual.txt"
            apt_file.write_text(r.stdout)
            result["apt"] = len(r.stdout.splitlines())
    except Exception as e:
        log(f"⚠️ apt capture failed: {e}")

    # PIP (venv-এর)
    try:
        pip_path = "/home/user/venv/bin/pip"
        if Path(pip_path).exists():
            r = subprocess.run([pip_path, "freeze"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                pip_file = output_dir / "pip-freeze.txt"
                pip_file.write_text(r.stdout)
                result["pip"] = len(r.stdout.splitlines())
    except Exception as e:
        log(f"⚠️ pip capture failed: {e}")

    # NPM global
    try:
        r = subprocess.run(["npm", "list", "-g", "--depth=0", "--json"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            npm_file = output_dir / "npm-global.json"
            npm_file.write_text(r.stdout)
            result["npm"] = "saved"
    except Exception as e:
        log(f"⚠️ npm capture failed: {e}")

    return result


def restore_packages(package_dir: Path) -> dict:
    """Package list থেকে re-install করো।"""
    result = {"apt": 0, "pip": 0, "npm": 0}

    # APT
    apt_file = package_dir / "apt-manual.txt"
    if apt_file.exists():
        try:
            pkgs = [line.strip() for line in apt_file.read_text().splitlines()
                    if line.strip() and not line.startswith("#")]
            if pkgs:
                # শুধু যা এখনো install হয়নি
                r = subprocess.run(["dpkg", "-l"], capture_output=True, text=True, timeout=30)
                installed = set()
                for line in r.stdout.splitlines():
                    parts = line.split()
                    if len(parts) > 1 and parts[0] == "ii":
                        installed.add(parts[1].split(":")[0])

                missing = [p for p in pkgs if p.split(":")[0] not in installed]
                if missing:
                    log(f"Re-installing {len(missing)} apt packages...")
                    subprocess.run(
                        ["apt-get", "install", "-y", "--no-install-recommends"] + missing,
                        check=False, timeout=600,
                    )
                    result["apt"] = len(missing)
        except Exception as e:
            log(f"⚠️ apt restore failed: {e}")

    # PIP
    pip_file = package_dir / "pip-freeze.txt"
    if pip_file.exists():
        try:
            pip_path = "/home/user/venv/bin/pip"
            if Path(pip_path).exists():
                subprocess.run(
                    [pip_path, "install", "--no-cache-dir", "-r", str(pip_file)],
                    check=False, timeout=600,
                )
                result["pip"] = "done"
        except Exception as e:
            log(f"⚠️ pip restore failed: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════
# XFCE settings capture / restore
# ═══════════════════════════════════════════════════════════════════

XFCE_CHANNELS = [
    "xfce4-desktop",     # wallpaper
    "xfwm4",             # window manager
    "xfce4-panel",       # panels
    "xfce4-session",     # session
    "xsettings",         # theme, fonts
    "thunar",            # file manager
    "keyboard-layout",
]


def capture_xfce_settings(output_dir: Path) -> bool:
    """XFCE settings (wallpaper, theme, panel) capture করো।"""
    output_dir.mkdir(parents=True, exist_ok=True)
    captured = {}

    for channel in XFCE_CHANNELS:
        try:
            r = subprocess.run(
                ["xfconf-query", "-c", channel, "-lv"],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":99")},
            )
            if r.returncode == 0 and r.stdout.strip():
                captured[channel] = r.stdout
        except Exception:
            pass

    if captured:
        (output_dir / "xfconf.json").write_text(
            json.dumps(captured, ensure_ascii=False, indent=2)
        )
        log(f"✅ XFCE settings captured: {len(captured)} channels")
        return True
    return False


def restore_xfce_settings(settings_file: Path) -> bool:
    """XFCE settings restore করো।"""
    if not settings_file.exists():
        return False
    try:
        captured = json.loads(settings_file.read_text())
        env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":99")}

        for channel, lines in captured.items():
            for line in lines.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Format: "property    value"
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                prop, value = parts

                # Type detection
                vtype = "string"
                if value.startswith("["):
                    vtype = "array"
                elif value.lower() in ("true", "false"):
                    vtype = "bool"
                elif value.replace(".", "", 1).replace("-", "", 1).isdigit():
                    vtype = "int" if "." not in value else "double"

                try:
                    subprocess.run(
                        ["xfconf-query", "-c", channel, "-p", prop,
                         "-s", value, "-t", vtype, "--create"],
                        check=False, timeout=5, env=env,
                        capture_output=True,
                    )
                except Exception:
                    pass

        log(f"✅ XFCE settings restored: {len(captured)} channels")
        return True
    except Exception as e:
        log(f"⚠️ XFCE restore failed: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# Session capture / restore (which apps were open)
# ═══════════════════════════════════════════════════════════════════

def capture_session(output_dir: Path) -> dict:
    """AT-SPI থেকে কোন apps খোলা ছিল সেটা capture করো।"""
    output_dir.mkdir(parents=True, exist_ok=True)
    session = {"apps": [], "captured_at": datetime.now(timezone.utc).isoformat()}

    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi

        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            app_name = app.get_name() or ""
            if not app_name:
                continue
            windows = []
            for j in range(app.get_child_count()):
                frame = app.get_child_at_index(j)
                if frame.get_role_name() == "frame":
                    windows.append(frame.get_name() or "")
            session["apps"].append({
                "name": app_name,
                "windows": windows,
            })
    except Exception as e:
        log(f"⚠️ session capture failed: {e}")

    (output_dir / "session.json").write_text(
        json.dumps(session, ensure_ascii=False, indent=2)
    )
    log(f"✅ session captured: {len(session['apps'])} apps")
    return session


def restore_session(session_file: Path) -> int:
    """Session থেকে apps re-launch করো।"""
    if not session_file.exists():
        return 0
    try:
        session = json.loads(session_file.read_text())
        env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":99")}
        launched = 0
        for app in session.get("apps", []):
            name = app.get("name", "")
            cmd = None
            for key, val in APP_COMMANDS.items():
                if key.lower() in name.lower():
                    cmd = val
                    break
            if cmd:
                try:
                    subprocess.Popen(
                        cmd.split(), env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    launched += 1
                    time.sleep(2)   # each app some time
                except Exception as e:
                    log(f"⚠️ could not launch {cmd}: {e}")
        log(f"✅ session restored: {launched} apps launched")
        return launched
    except Exception as e:
        log(f"⚠️ session restore failed: {e}")
        return 0


# ═══════════════════════════════════════════════════════════════════
# Core backup
# ═══════════════════════════════════════════════════════════════════

def _should_exclude(path: Path) -> bool:
    """Check if path matches exclude patterns."""
    p = str(path)
    for pat in EXCLUDE_PATTERNS:
        if pat.startswith("*."):
            if p.endswith(pat[1:]):
                return True
        elif pat in p:
            return True
    return False


def _create_tarball(output_path: Path, staging_dir: Path) -> None:
    """Staging directory থেকে tar.gz বানাও।"""
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(staging_dir, arcname=".")


def backup(force_hf: bool = True) -> Path:
    """
    সম্পূর্ণ backup চালাও।

    Returns:
        Path: backup archive-এর path
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log(f"═══ Backup শুরু: {ts} ═══")

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "snapshot"
        staging.mkdir()

        # ১. Home files copy (with exclude)
        log("→ user files copy...")
        for path_str in BACKUP_PATHS:
            src = HOME / path_str
            if not src.exists():
                continue
            dst = staging / "home" / path_str
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                if src.is_dir():
                    shutil.copytree(
                        src, dst,
                        ignore=shutil.ignore_patterns(*[
                            p for p in EXCLUDE_PATTERNS if not p.startswith("*")
                        ]),
                        dirs_exist_ok=True,
                    )
                else:
                    shutil.copy2(src, dst)
            except Exception as e:
                log(f"  ⚠️ {path_str}: {e}")

        # ২. Packages
        log("→ packages capture...")
        pkg_dir = staging / "packages"
        capture_packages(pkg_dir)

        # ৩. XFCE settings
        log("→ XFCE settings capture...")
        xfce_dir = staging / "xfce"
        capture_xfce_settings(xfce_dir)

        # ৪. Session
        log("→ session capture...")
        session_dir = staging / "session"
        capture_session(session_dir)

        # ৫. Metadata
        meta = {
            "created_at": ts,
            "home": str(HOME),
            "backup_paths": BACKUP_PATHS,
            "exclude_patterns": EXCLUDE_PATTERNS,
            "python_version": sys.version,
            "hostname": os.uname().nodename,
        }
        (staging / "meta.json").write_text(json.dumps(meta, indent=2))

        # ৬. Tarball তৈরি
        archive_name = f"agent_pc-{ts}.tar.gz"
        archive_path = BACKUP_DIR / archive_name
        log(f"→ tarball তৈরি: {archive_name}")
        _create_tarball(archive_path, staging)

        size_mb = archive_path.stat().st_size / (1024 * 1024)
        log(f"✅ Backup সম্পূর্ণ: {size_mb:.1f} MB")

        # ৭. HF-এ upload
        if force_hf:
            log("→ HF Dataset-এ upload...")
            _hf_upload_file(archive_path, archive_name)

        # ৮. পুরনো backup cleanup (local + HF — শুধু শেষ ৫টা রাখি)
        _cleanup_old_backups(keep=5)

        return archive_path


def _cleanup_old_backups(keep: int = 5) -> None:
    """শুধু শেষ N backup রাখো।"""
    backups = sorted(BACKUP_DIR.glob("agent_pc-*.tar.gz"), reverse=True)
    for old in backups[keep:]:
        try:
            old.unlink()
            log(f"  🗑️ old backup মুছলাম: {old.name}")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
# Core restore
# ═══════════════════════════════════════════════════════════════════

def _find_latest_backup() -> Path | None:
    """সর্বশেষ backup খুঁজে বের করো — local আগে, তারপর HF।"""
    # Local
    local_backups = sorted(BACKUP_DIR.glob("agent_pc-*.tar.gz"), reverse=True)
    if local_backups:
        return local_backups[0]

    # HF
    hf_list = _hf_list_snapshots()
    if hf_list:
        latest = hf_list[0]
        log(f"HF থেকে latest: {latest}")
        local_target = BACKUP_DIR / latest
        if _hf_download_file(latest, local_target):
            return local_target

    return None


def restore(archive_path: Path | None = None) -> bool:
    """
    Backup থেকে restore করো।

    Args:
        archive_path: নির্দিষ্ট archive; None হলে latest খুঁজে নেয়।

    Returns:
        bool: সফল হলে True
    """
    log("═══ Restore শুরু ═══")

    if archive_path is None:
        archive_path = _find_latest_backup()

    if not archive_path or not archive_path.exists():
        log("❌ কোনো backup পাওয়া যায়নি — fresh start")
        return False

    log(f"→ ব্যবহার করছি: {archive_path.name}")

    with tempfile.TemporaryDirectory() as tmp:
        extract_dir = Path(tmp) / "restore"
        extract_dir.mkdir()

        # ১. Extract
        log("→ extract...")
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(extract_dir)
        except Exception as e:
            log(f"❌ extract failed: {e}")
            return False

        # ২. Home files restore
        log("→ home files restore...")
        home_backup = extract_dir / "home"
        if home_backup.exists():
            for item in home_backup.iterdir():
                dst = HOME / item.name
                try:
                    if item.is_dir():
                        shutil.copytree(item, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dst)
                except Exception as e:
                    log(f"  ⚠️ {item.name}: {e}")

        # ৩. Packages restore
        log("→ packages restore...")
        pkg_dir = extract_dir / "packages"
        if pkg_dir.exists():
            restore_packages(pkg_dir)

        # ৪. XFCE settings restore
        log("→ XFCE settings restore...")
        xfce_file = extract_dir / "xfce" / "xfconf.json"
        if xfce_file.exists():
            restore_xfce_settings(xfce_file)

        # ৫. Session restore (apps re-launch)
        log("→ session restore...")
        session_file = extract_dir / "session" / "session.json"
        if session_file.exists():
            restore_session(session_file)

    log("✅ Restore সম্পূর্ণ")
    return True


# ═══════════════════════════════════════════════════════════════════
# Periodic backup thread
# ═══════════════════════════════════════════════════════════════════

_backup_thread: threading.Thread | None = None
_backup_stop = threading.Event()


def start_periodic_backup(interval_seconds: int = BACKUP_INTERVAL_SECONDS) -> None:
    """Background-এ periodic backup চালু করো।"""
    global _backup_thread

    if _backup_thread and _backup_thread.is_alive():
        log("Periodic backup আগে থেকেই চলছে")
        return

    def _loop():
        log(f"Periodic backup চালু — প্রতি {interval_seconds}s")
        while not _backup_stop.wait(interval_seconds):
            try:
                backup(force_hf=True)
            except Exception as e:
                log(f"⚠️ periodic backup error: {e}")

    _backup_thread = threading.Thread(target=_loop, daemon=True, name="backup-loop")
    _backup_thread.start()


def stop_periodic_backup() -> None:
    """Periodic backup বন্ধ করো।"""
    _backup_stop.set()
    log("Periodic backup বন্ধ")


# ═══════════════════════════════════════════════════════════════════
# Signal handlers (graceful shutdown-এ backup)
# ═══════════════════════════════════════════════════════════════════

def install_shutdown_handler() -> None:
    """SIGTERM/SIGINT এলে দ্রুত backup নিয়ে exit।"""
    def _handler(signum, frame):
        log(f"Signal {signum} — দ্রুত backup...")
        try:
            backup(force_hf=True)
        except Exception as e:
            log(f"⚠️ shutdown backup failed: {e}")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="agent_pc backup & restore")
    parser.add_argument(
        "command",
        choices=["backup", "restore", "list", "auto"],
        help="কী করতে চান",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="নির্দিষ্ট archive (restore-এর জন্যে)",
    )
    parser.add_argument(
        "--no-hf",
        action="store_true",
        help="HF-এ upload করবেন না (শুধু local)",
    )
    args = parser.parse_args()

    if args.command == "backup":
        backup(force_hf=not args.no_hf)

    elif args.command == "restore":
        restore(args.archive)

    elif args.command == "list":
        local = sorted(BACKUP_DIR.glob("agent_pc-*.tar.gz"), reverse=True)
        print("=== Local backups ===")
        for b in local:
            size_mb = b.stat().st_size / (1024 * 1024)
            print(f"  {b.name}  ({size_mb:.1f} MB)")
        print("\n=== HF backups ===")
        for name in _hf_list_snapshots():
            print(f"  {name}")

    elif args.command == "auto":
        # Full auto: install shutdown handler + start periodic backup
        install_shutdown_handler()
        start_periodic_backup()
        log("Auto mode চালু — Ctrl+C দিলে backup হয়ে exit হবে")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            log("KeyboardInterrupt — backup...")
            backup(force_hf=True)


if __name__ == "__main__":
    main()