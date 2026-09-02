import os
import shutil
import sys
from pathlib import Path


def _get_candidates() -> list[Path]:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir / "platform-tools",
            exe_dir / "resources" / "platform-tools",
            Path(sys._MEIPASS) / "platform-tools",
        ])
    else:
        script_dir = Path(__file__).resolve().parent
        repo_root = script_dir.parent
        candidates.extend([
            script_dir / "platform-tools",
            repo_root / "platform-tools",
        ])

    return [p for p in candidates if p.exists()]


def _find_adb_dir(candidates: list[Path]) -> Path | None:
    for folder in candidates:
        if (folder / "adb.exe").exists() or (folder / "adb").exists():
            return folder.resolve()
    return None


def _copy_platform_tools(source_dir: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in source_dir.iterdir():
        dest = target_dir / item.name
        if item.is_dir():
            if dest.exists():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    return target_dir


def ensure_adb_available() -> Path | None:
    """Make bundled ADB tools available on PATH for the current session."""
    existing_adb = shutil.which("adb")
    if existing_adb:
        return Path(existing_adb).resolve().parent

    bundled_dir = _find_adb_dir(_get_candidates())
    if bundled_dir is None:
        return None

    local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home())
    target_dir = Path(local_app_data) / "Twitter Automator" / "platform-tools"
    if not (target_dir / "adb.exe").exists() and not (target_dir / "adb").exists():
        target_dir = _copy_platform_tools(bundled_dir, target_dir)
    else:
        target_dir.mkdir(parents=True, exist_ok=True)

    os.environ["PATH"] = str(target_dir) + os.pathsep + os.environ.get("PATH", "")
    os.environ["ANDROID_HOME"] = str(target_dir)
    os.environ["ANDROID_SDK_ROOT"] = str(target_dir)
    return target_dir
