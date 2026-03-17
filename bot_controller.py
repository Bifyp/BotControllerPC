#!/usr/bin/env python3
"""
Windows PC Controller Telegram Bot v3.3
Все исправления применены.
"""

import os, sys, subprocess, json, logging, asyncio, tempfile, random, platform
import socket, time, string, re, shutil, ctypes
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Set
from concurrent.futures import ThreadPoolExecutor
import urllib.request, urllib.parse

import mss, mss.tools

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_AVAILABLE = True
except Exception:
    PYCAW_AVAILABLE = False

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, CallbackQueryHandler, filters,
)
from telegram.constants import ParseMode

# ── конфиг ───────────────────────────────────────────────────────────────────
# ВАЖНО: замените токен и ID на свои, либо передавайте через переменные окружения:
#   BOT_TOKEN=xxx MASTER_ADMIN_ID=123 python bot_controller.py
BOT_TOKEN       = os.environ.get("BOT_TOKEN",       "YOUR_BOT_TOKEN_HERE")
MASTER_ADMIN_ID = int(os.environ.get("MASTER_ADMIN_ID", "YOUR_TELEGRAM_ID_HERE"))
CONFIG_FILE     = "bot_config.json"
WHITELIST_FILE  = "whitelist.json"
LOG_FILE        = "bot_controller.log"
SECURITY_LOG    = "security.log"
ANIME_VOICE     = "pl-PL-ZofiaNeural"   # польский голос
VERSION         = "3.3"
WEATHER_CITY    = "Swarzedz"
WEATHER_COORDS  = "52.4097,17.0756"
MAX_TEXT_LENGTH = 1000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("WinBot")

whitelist: Set[int] = set()
config: Dict = {}
clipboard_history = []
user_state: Dict[int, str] = {}
_executor = ThreadPoolExecutor(max_workers=6)

is_windows = os.name == "nt"
try:
    is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin()) if is_windows else False
except Exception:
    is_admin = False


# ─────────────────────────────────────────────────────────────────────────────
# БАЗОВЫЕ УТИЛИТЫ
# ─────────────────────────────────────────────────────────────────────────────

def make_bar(percent: float, length: int = 10) -> str:
    filled = max(0, min(length, int(percent / 100 * length)))
    return "█" * filled + "░" * (length - filled) + f" {percent:.0f}%"


async def run_bg(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, fn, *args)


def shell(cmd: str, timeout: int = 12, encoding: str = "cp866") -> str:
    """Выполнить shell-команду. cp866 — кодировка Windows cmd."""
    try:
        r = subprocess.run(cmd, capture_output=True, shell=True, timeout=timeout)
        for enc in (encoding, "utf-8", "cp1251", "latin-1"):
            try:
                return r.stdout.decode(enc).strip()
            except Exception:
                pass
        return r.stdout.decode("utf-8", errors="replace").strip()
    except subprocess.TimeoutExpired:
        return "⏱ Таймаут"
    except Exception as e:
        return f"❌ {e}"


def shell_ps(cmd: str, timeout: int = 10) -> str:
    """PowerShell команда — всегда UTF-8."""
    try:
        full = f'powershell -NoProfile -NonInteractive -Command "& {{{cmd}}}"'
        r = subprocess.run(full, capture_output=True, shell=True, timeout=timeout)
        out = r.stdout.decode("utf-8", errors="replace").strip()
        if not out:
            out = r.stderr.decode("utf-8", errors="replace").strip()
        return out
    except subprocess.TimeoutExpired:
        return "⏱ Таймаут"
    except Exception as e:
        return f"❌ {e}"


# ─────────────────────────────────────────────────────────────────────────────
# КОНФИГ
# ─────────────────────────────────────────────────────────────────────────────

class ConfigManager:
    DEFAULTS = {
        "startup_notification": True,
        "enable_voice_commands": True,
        "backup_voice_enabled": True,
        "clipboard_history_enabled": True,
        "max_clipboard_items": 10,
        "security_level": "high",
        "search_paths": ["C:\\Users", "D:\\"],
    }

    @staticmethod
    def load():
        global config
        cfg = dict(ConfigManager.DEFAULTS)
        try:
            if Path(CONFIG_FILE).exists():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg.update(json.load(f))
            else:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Config load: {e}")
        config = cfg

    @staticmethod
    def load_whitelist():
        global whitelist
        try:
            if Path(WHITELIST_FILE).exists():
                with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
                    whitelist = set(json.load(f).get("users", [MASTER_ADMIN_ID]))
            else:
                whitelist = {MASTER_ADMIN_ID}
                ConfigManager.save_whitelist()
        except Exception:
            whitelist = {MASTER_ADMIN_ID}

    @staticmethod
    def save_whitelist():
        with open(WHITELIST_FILE, "w", encoding="utf-8") as f:
            json.dump({"users": list(whitelist)}, f, indent=2)


ConfigManager.load()
ConfigManager.load_whitelist()


def is_authorized(uid: int) -> bool:
    return uid in whitelist


def log_sec(event: str, uid: int, details: str = ""):
    with open(SECURITY_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {event} uid={uid} {details}\n")


# ─────────────────────────────────────────────────────────────────────────────
# ГРОМКОСТЬ
# ─────────────────────────────────────────────────────────────────────────────

def set_volume(level: int) -> str:
    level = max(0, min(100, level))
    if PYCAW_AVAILABLE:
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            vol.SetMasterVolumeLevelScalar(level / 100.0, None)
            return f"🔊 Громкость: {make_bar(level)}"
        except Exception as e:
            logger.warning(f"pycaw: {e}")
    try:
        val = int(level / 100 * 65535)
        r = subprocess.run(f"nircmd setsysvolume {val}", capture_output=True, shell=True, timeout=3)
        if r.returncode == 0:
            return f"🔊 Громкость: {make_bar(level)}"
    except Exception:
        pass
    try:
        ps = (
            f'Add-Type -TypeDefinition \'using System.Runtime.InteropServices; '
            f'public class V {{ [DllImport("winmm.dll")] public static extern int waveOutSetVolume(System.IntPtr h, uint v); }}\'; '
            f'$v = [uint32]({level / 100.0} * 0xFFFF); '
            f'$vv = $v | ($v -shl 16); '
            f'[V]::waveOutSetVolume([System.IntPtr]::Zero, $vv)'
        )
        shell_ps(ps)
        return f"🔊 Громкость: {make_bar(level)}"
    except Exception as e:
        return f"❌ Не удалось установить громкость: {e}"


def get_volume() -> int:
    if PYCAW_AVAILABLE:
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            return int(vol.GetMasterVolumeLevelScalar() * 100)
        except Exception:
            pass
    return -1


# ─────────────────────────────────────────────────────────────────────────────
# СИСТЕМА
# ─────────────────────────────────────────────────────────────────────────────

class WindowsUtils:

    @staticmethod
    def get_system_info() -> Dict:
        info = {
            "os": platform.system(),
            "version": platform.version(),
            "hostname": socket.gethostname(),
            "username": os.environ.get("USERNAME", "unknown"),
            "cpu_cores": os.cpu_count() or 0,
            "python_version": platform.python_version(),
            "is_admin": is_admin,
            "disk_space": {},
        }
        if PSUTIL_AVAILABLE:
            try:
                mem = psutil.virtual_memory()
                info.update({
                    "ram_gb":      round(mem.total / 1024**3, 1),
                    "ram_used":    round(mem.used  / 1024**3, 1),
                    "ram_percent": mem.percent,
                    "cpu_percent": psutil.cpu_percent(interval=1),
                })
                for part in psutil.disk_partitions(all=False):
                    try:
                        u = psutil.disk_usage(part.mountpoint)
                        info["disk_space"][part.device] = {
                            "total_gb": round(u.total / 1024**3, 1),
                            "used_gb":  round(u.used  / 1024**3, 1),
                            "free_gb":  round(u.free  / 1024**3, 1),
                            "percent":  u.percent,
                        }
                    except Exception:
                        pass
            except Exception:
                pass
        return info

    @staticmethod
    def get_cpu_temp() -> str:
        ps = (
            'Get-WmiObject -Namespace "root/OpenHardwareMonitor" -Class Sensor '
            '| Where-Object { $_.SensorType -eq "Temperature" } '
            '| Select-Object Name, Value '
            '| ForEach-Object { $_.Name + ": " + [math]::Round($_.Value,1) + "C" }'
        )
        out = shell_ps(ps, timeout=5)
        if out and "C" in out and "❌" not in out and "⏱" not in out:
            lines = [l.strip() for l in out.splitlines() if l.strip() and "C" in l][:5]
            return "🌡 *Температуры (OHM):*\n" + "\n".join(f"• `{l}`" for l in lines)

        try:
            r = subprocess.run(
                r'wmic /namespace:\\root\wmi PATH MSAcpi_ThermalZoneTemperature get CurrentTemperature /value',
                capture_output=True, shell=True, timeout=5
            )
            out2 = r.stdout.decode("utf-8", errors="replace").strip()
            temps = []
            for line in out2.splitlines():
                if "CurrentTemperature=" in line:
                    val = line.split("=")[1].strip()
                    if val.isdigit():
                        celsius = round(int(val) / 10 - 273.15, 1)
                        temps.append(f"• CPU: `{celsius}°C`")
            if temps:
                return "🌡 *Температура:*\n" + "\n".join(temps)
        except Exception:
            pass

        return (
            "🌡 Температура недоступна\n"
            "_Установи LibreHardwareMonitor и запусти его — тогда данные появятся_"
        )

    @staticmethod
    def get_uptime() -> str:
        if not PSUTIL_AVAILABLE:
            return "❌ psutil не установлен"
        try:
            d = timedelta(seconds=int(time.time() - psutil.boot_time()))
            return f"⏱ *Uptime:* {d.days}д {d.seconds//3600}ч {(d.seconds%3600)//60}м"
        except Exception as e:
            return f"❌ {e}"

    @staticmethod
    def lock():
        try:
            ctypes.windll.user32.LockWorkStation()
            return True
        except Exception:
            return False

    @staticmethod
    def turn_off_display():
        try:
            ctypes.windll.user32.PostMessageW(
                ctypes.windll.user32.GetForegroundWindow(),
                0x0112, 0xF170, 2
            )
        except Exception:
            pass

    @staticmethod
    def sleep_pc():
        """Настоящий сон (Sleep/Suspend), не гибернация."""
        try:
            # SetSuspendState(Hibernate=False, ForceCritical=False, DisableWakeEvent=False)
            ctypes.windll.powrprof.SetSuspendState(0, 0, 0)
            return True
        except Exception:
            # Fallback через rundll32
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return True

    @staticmethod
    def clean_temp() -> str:
        cleaned, errors = 0, 0
        for temp_dir in [os.environ.get("TEMP", ""), r"C:\Windows\Temp"]:
            if not temp_dir or not os.path.isdir(temp_dir):
                continue
            for entry in os.scandir(temp_dir):
                try:
                    if entry.is_file(follow_symlinks=False):
                        os.remove(entry.path)
                    elif entry.is_dir(follow_symlinks=False):
                        shutil.rmtree(entry.path, ignore_errors=True)
                    cleaned += 1
                except Exception:
                    errors += 1
        return f"🗑 Очищено: {cleaned}, пропущено: {errors}"


# ─────────────────────────────────────────────────────────────────────────────
# БУФЕР ОБМЕНА
# ─────────────────────────────────────────────────────────────────────────────

class ClipboardManager:
    @staticmethod
    def get() -> str:
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            text = root.clipboard_get()
            root.update()   # FIX: update перед destroy чтобы буфер успел прочитаться
            root.destroy()
            return text if text else "(пусто)"
        except Exception:
            pass
        out = shell_ps("Get-Clipboard")
        return out if out else "(пусто)"

    @staticmethod
    def set(text: str) -> bool:
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()   # FIX: update() должен быть ДО destroy(), иначе буфер очищается
            # Небольшая задержка чтобы данные успели попасть в системный буфер
            time.sleep(0.1)
            root.destroy()
            return True
        except Exception:
            pass
        try:
            escaped = text.replace("'", "''")
            shell_ps(f"Set-Clipboard -Value '{escaped}'")
            return True
        except Exception:
            return False

    @staticmethod
    def add_to_history(text: str):
        if config.get("clipboard_history_enabled") and text and text not in clipboard_history:
            clipboard_history.insert(0, text[:500])
            del clipboard_history[config.get("max_clipboard_items", 10):]


# ─────────────────────────────────────────────────────────────────────────────
# ПРОЦЕССЫ
# ─────────────────────────────────────────────────────────────────────────────

class ProcessManager:
    @staticmethod
    def get_top(count: int = 10) -> str:
        """
        Двойной замер CPU.
        ВАЖНО: вызывать через run_bg(), т.к. содержит blocking time.sleep(1).
        """
        if not PSUTIL_AVAILABLE:
            return "❌ psutil не установлен"
        try:
            procs = {}
            for p in psutil.process_iter(["pid", "name", "memory_percent"]):
                try:
                    procs[p.pid] = {"name": p.name(), "mem": round(p.memory_percent(), 1)}
                    p.cpu_percent(interval=None)  # прогрев
                except Exception:
                    pass
            time.sleep(1)   # блокирующий sleep — OK, т.к. мы в ThreadPoolExecutor
            data = []
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    cpu = p.cpu_percent(interval=None)
                    if p.pid in procs:
                        data.append({
                            "name": procs[p.pid]["name"],
                            "cpu":  cpu,
                            "mem":  procs[p.pid]["mem"],
                        })
                except Exception:
                    pass
            data.sort(key=lambda x: x["cpu"], reverse=True)
            msg = "📊 *TOP процессы по CPU:*\n\n"
            for i, p in enumerate(data[:count], 1):
                name = p["name"][:22]
                msg += f"`{i:2}.` `{name:<22}` CPU:{p['cpu']:5.1f}% RAM:{p['mem']:4.1f}%\n"
            return msg
        except Exception as e:
            return f"❌ {e}"

    @staticmethod
    def kill(name: str) -> str:
        out = shell(f'taskkill /F /IM "{name}"')
        return f"✅ {out}" if out else f"✅ Завершено: {name}"

    @staticmethod
    def find(name: str) -> str:
        if not PSUTIL_AVAILABLE:
            return shell(f'tasklist /FI "IMAGENAME eq *{name}*"')
        found = []
        for p in psutil.process_iter(["pid", "name", "status"]):
            try:
                if name.lower() in p.name().lower():
                    found.append(f"• `{p.pid}` {p.name()} [{p.status()}]")
            except Exception:
                pass
        return "🔍 *Найдено:*\n" + "\n".join(found) if found else f"🔍 Процесс `{name}` не найден"


# ─────────────────────────────────────────────────────────────────────────────
# ФАЙЛЫ
# ─────────────────────────────────────────────────────────────────────────────

class FileManager:
    @staticmethod
    def get_recycle_bin() -> str:
        out = shell_ps(
            '$sh = New-Object -ComObject Shell.Application; '
            '$bin = $sh.Namespace(0xA); '
            '$cnt = ($bin.Items() | Measure-Object).Count; '
            'Write-Output "Файлов: $cnt"'
        )
        return f"🗑 *Корзина:*\n{out}" if out and "❌" not in out else "🗑 Корзина пуста или ошибка доступа"

    @staticmethod
    def empty_recycle_bin() -> str:
        shell_ps("Clear-RecycleBin -Force -ErrorAction SilentlyContinue")
        return "✅ Корзина очищена"

    @staticmethod
    def search(query: str) -> str:
        paths = config.get("search_paths", ["C:\\Users"])
        found = []
        for base in paths:
            if not os.path.isdir(base):
                continue
            try:
                out = shell(f'where /R "{base}" "*{query}*"', timeout=8)
                for line in out.splitlines():
                    line = line.strip()
                    if line and not line.startswith("❌") and not line.startswith("⏱"):
                        found.append(f"`{line}`")
                        if len(found) >= 10:
                            break
            except Exception:
                pass
            if len(found) >= 10:
                break
        return "🔍 *Найдено:*\n" + "\n".join(found) if found else "🔍 Файлы не найдены"

    @staticmethod
    def list_dir(path: str = None) -> str:
        path = path or os.path.join(os.environ.get("USERPROFILE", "C:\\Users"), "Desktop")
        try:
            items = []
            for e in sorted(os.scandir(path), key=lambda x: (not x.is_dir(), x.name.lower())):
                icon = "📁" if e.is_dir() else "📄"
                items.append(f"{icon} `{e.name}`")
            result = "\n".join(items[:20])
            return f"📂 *Рабочий стол:*\n{result}" if items else "📂 Папка пуста"
        except Exception as e:
            return f"❌ {e}"

    @staticmethod
    def open_folder(path: str = ".") -> str:
        try:
            subprocess.Popen(["explorer.exe", os.path.abspath(path)])
            return f"📁 Открыта папка: `{os.path.abspath(path)}`"
        except Exception as e:
            return f"❌ {e}"


# ─────────────────────────────────────────────────────────────────────────────
# СЕТЬ
# ─────────────────────────────────────────────────────────────────────────────

class NetworkUtils:

    @staticmethod
    def get_local_ips() -> str:
        hostname = socket.gethostname()
        lines = [f"🖥 Хост: `{hostname}`"]
        seen = set()
        try:
            for item in socket.getaddrinfo(hostname, None):
                ip = item[4][0]
                if ip not in seen and ":" not in ip:
                    seen.add(ip)
                    lines.append(f"• `{ip}`")
        except Exception:
            try:
                lines.append(f"• `{socket.gethostbyname(hostname)}`")
            except Exception:
                pass
        return "🌐 *Локальные IP:*\n" + "\n".join(lines)

    @staticmethod
    def get_external_ip() -> str:
        for url in ["https://api.ipify.org", "https://icanhazip.com", "https://ifconfig.me/ip"]:
            try:
                ip = urllib.request.urlopen(url, timeout=5).read().decode().strip()
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                    return f"🌍 Внешний IP: `{ip}`"
            except Exception:
                pass
        return "❌ Не удалось получить внешний IP"

    @staticmethod
    def ping_test() -> str:
        hosts = {"Google": "8.8.8.8", "Cloudflare": "1.1.1.1", "Yandex": "77.88.8.8"}
        lines = []
        for name, host in hosts.items():
            try:
                r = subprocess.run(
                    ["ping", "-n", "3", "-w", "2000", host],
                    capture_output=True, timeout=15
                )
                out = ""
                for enc in ("cp866", "cp1251", "utf-8", "latin-1"):
                    try:
                        out = r.stdout.decode(enc)
                        break
                    except Exception:
                        pass
                m = re.search(r"(?:Average|Среднее)\s*=\s*(\d+)\s*(?:ms|мс)", out, re.IGNORECASE)
                if m:
                    ms = int(m.group(1))
                    emoji = "🟢" if ms < 50 else ("🟡" if ms < 150 else "🔴")
                    lines.append(f"{emoji} {name}: `{ms} мс`")
                elif r.returncode == 0:
                    lines.append(f"🟢 {name}: доступен")
                else:
                    lines.append(f"⚫ {name}: нет ответа")
            except subprocess.TimeoutExpired:
                lines.append(f"⚫ {name}: таймаут")
            except Exception as e:
                lines.append(f"⚫ {name}: {e}")
        return "🌐 *Пинг:*\n" + "\n".join(lines)

    @staticmethod
    def get_wifi_networks() -> str:
        try:
            r = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True, timeout=10
            )
            out = ""
            for enc in ("cp866", "cp1251", "utf-8", "latin-1"):
                try:
                    out = r.stdout.decode(enc)
                    if out.strip():
                        break
                except Exception:
                    pass

            if not out.strip():
                return "📶 WiFi адаптер не найден или отключён"

            networks = []
            current = {}
            for raw_line in out.splitlines():
                line = raw_line.strip()
                ssid_m = re.match(r'^SSID\s+\d+\s*:\s*(.+)$', line)
                if ssid_m and "BSSID" not in line:
                    if current.get("ssid"):
                        networks.append(current)
                    current = {"ssid": ssid_m.group(1).strip()}
                    continue
                sig_m = re.match(r'^(?:Signal|Сигнал)\s*:\s*(.+)$', line, re.IGNORECASE)
                if sig_m and current:
                    current["signal"] = sig_m.group(1).strip()
                auth_m = re.match(r'^(?:Authentication|Проверка подлинности)\s*:\s*(.+)$', line, re.IGNORECASE)
                if auth_m and current:
                    current["auth"] = auth_m.group(1).strip()

            if current.get("ssid"):
                networks.append(current)

            if not networks:
                return f"📶 WiFi сети:\n```\n{out[:800]}\n```"

            result = []
            for n in networks[:10]:
                ssid   = n.get("ssid", "?")
                sig    = n.get("signal", "?")
                auth   = n.get("auth", "?")
                result.append(f"📶 `{ssid}` | {sig} | {auth}")
            return "📶 *WiFi сети:*\n" + "\n".join(result)
        except Exception as e:
            return f"❌ {e}"

    @staticmethod
    def get_wifi_password() -> str:
        try:
            r = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, timeout=5)
            out = ""
            for enc in ("cp866", "cp1251", "utf-8"):
                try:
                    out = r.stdout.decode(enc); break
                except Exception:
                    pass
            ssid = None
            for line in out.splitlines():
                m = re.match(r'^\s*SSID\s*:\s*(.+)$', line)
                if m and "BSSID" not in line:
                    ssid = m.group(1).strip()
                    break
            if not ssid:
                return "❌ Нет подключения к WiFi"

            r2 = subprocess.run(
                ["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"],
                capture_output=True, timeout=5
            )
            out2 = ""
            for enc in ("cp866", "cp1251", "utf-8"):
                try:
                    out2 = r2.stdout.decode(enc); break
                except Exception:
                    pass
            for line in out2.splitlines():
                m = re.match(r'^\s*(?:Key Content|Содержимое ключа)\s*:\s*(.+)$', line, re.IGNORECASE)
                if m:
                    return f"🔑 *Пароль WiFi `{ssid}`:*\n`{m.group(1).strip()}`"
            return f"🔑 WiFi `{ssid}` — пароль не найден или открытая сеть"
        except Exception as e:
            return f"❌ {e}"

    @staticmethod
    def get_network_speed() -> str:
        """
        Измерение скорости сети.
        ВАЖНО: содержит blocking time.sleep(2) — вызывать через run_bg().
        """
        if not PSUTIL_AVAILABLE:
            return "❌ psutil не установлен"
        try:
            n1 = psutil.net_io_counters()
            time.sleep(2)   # blocking sleep — OK в ThreadPoolExecutor
            n2 = psutil.net_io_counters()
            up_kb = (n2.bytes_sent - n1.bytes_sent) / 2 / 1024
            dn_kb = (n2.bytes_recv - n1.bytes_recv) / 2 / 1024
            return (
                f"📊 *Скорость сети:*\n"
                f"⬆️ Upload:   `{up_kb:.1f} KB/s` ({up_kb/1024:.2f} MB/s)\n"
                f"⬇️ Download: `{dn_kb:.1f} KB/s` ({dn_kb/1024:.2f} MB/s)"
            )
        except Exception as e:
            return f"❌ {e}"

    @staticmethod
    def get_firewall_status() -> str:
        try:
            r = subprocess.run(
                ["netsh", "advfirewall", "show", "allprofiles", "state"],
                capture_output=True, timeout=8
            )
            out = ""
            for enc in ("cp866", "cp1251", "utf-8"):
                try:
                    out = r.stdout.decode(enc); break
                except Exception:
                    pass

            if not out.strip():
                return "🔥 Firewall: нет данных"

            lines = []
            profile = None
            for line in out.splitlines():
                line = line.strip()
                pm = re.match(r'^(Domain|Private|Public|Домен|Частный|Общий)\s+Profile\s+Settings:', line, re.IGNORECASE)
                if pm:
                    profile = pm.group(1)
                    continue
                sm = re.match(r'^(?:State|Состояние)\s+(\w+)', line, re.IGNORECASE)
                if sm and profile:
                    state = sm.group(1)
                    emoji = "🟢" if state.lower() in ("on", "вкл", "включено") else "🔴"
                    lines.append(f"{emoji} {profile}: `{state}`")
                    profile = None

            if lines:
                return "🔥 *Firewall:*\n" + "\n".join(lines)
            clean = "\n".join(l for l in out.splitlines() if l.strip())[:600]
            return f"🔥 *Firewall:*\n```\n{clean}\n```"
        except Exception as e:
            return f"❌ {e}"

    @staticmethod
    def get_bluetooth_devices() -> str:
        out = shell_ps(
            'Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue '
            '| Where-Object { $_.Status -eq "OK" } '
            '| Select-Object -ExpandProperty FriendlyName'
        )
        if not out or "❌" in out or "⏱" in out:
            out2 = shell_ps(
                'Get-WmiObject Win32_PnPEntity '
                '| Where-Object { $_.Description -like "*Bluetooth*" -or $_.Service -like "*BthEnum*" } '
                '| Select-Object -ExpandProperty Name'
            )
            if out2 and "❌" not in out2:
                out = out2
            else:
                return "📡 Bluetooth устройств не найдено или Bluetooth выключен"

        devices = []
        for line in out.splitlines():
            line = line.strip()
            if line and len(line) > 1 and not line.startswith("-----"):
                clean = re.sub(r'[^\x20-\x7E\u0400-\u04FF\u0100-\u017F]', '', line).strip()
                if clean:
                    devices.append(f"• `{clean}`")

        return "📡 *Bluetooth устройства:*\n" + "\n".join(devices[:10]) if devices else "📡 Bluetooth устройств не найдено"

    @staticmethod
    def get_open_ports() -> str:
        try:
            r = subprocess.run(["netstat", "-ano"], capture_output=True, timeout=10)
            out = r.stdout.decode("cp866", errors="replace")
            seen = set()
            for line in out.splitlines():
                if "LISTENING" in line.upper():
                    parts = line.split()
                    if len(parts) >= 2:
                        port = parts[1].rsplit(":", 1)[-1]
                        if port.isdigit() and port not in seen:
                            seen.add(port)
            if seen:
                ports_sorted = sorted(seen, key=int)[:25]
                return "🔌 *Открытые порты (LISTENING):*\n" + "  ".join(f"`{p}`" for p in ports_sorted)
            return "🔌 Открытых портов не найдено"
        except Exception as e:
            return f"❌ {e}"

    @staticmethod
    def netboost() -> str:
        results = []
        r = subprocess.run("ipconfig /flushdns", capture_output=True, shell=True)
        results.append(f"DNS кэш: {'✅' if r.returncode == 0 else '❌'}")
        subprocess.run("arp -d *", capture_output=True, shell=True)
        results.append("ARP кэш: ✅")
        return "⚡ *Сетевой буст:*\n" + "\n".join(results)


# ─────────────────────────────────────────────────────────────────────────────
# ИГРЫ
# ─────────────────────────────────────────────────────────────────────────────

class GameUtils:

    @staticmethod
    def get_load() -> str:
        if not PSUTIL_AVAILABLE:
            return "❌ psutil не установлен"
        cpu  = psutil.cpu_percent(interval=1)
        mem  = psutil.virtual_memory()
        freq = psutil.cpu_freq()
        freq_str = f"{freq.current:.0f} MHz" if freq else "N/A"

        gpu_str = ""
        try:
            gpu_out = subprocess.check_output(
                "nvidia-smi --query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total "
                "--format=csv,noheader,nounits",
                shell=True, timeout=3
            ).decode("utf-8", errors="replace").strip()
            if gpu_out:
                parts = [p.strip() for p in gpu_out.split(",")]
                if len(parts) >= 5:
                    gname, gutil, gtemp, gmem_u, gmem_t = parts[:5]
                    gpu_bar = make_bar(float(gutil))
                    gpu_str = (
                        f"\n🎮 GPU: `{gname}`\n"
                        f"   {gpu_bar}\n"
                        f"   🌡 {gtemp}°C | VRAM: {float(gmem_u)/1024:.1f}/{float(gmem_t)/1024:.1f} GB"
                    )
        except Exception:
            gpu_str = "\n🎮 GPU: N/A (нет NVIDIA или nvidia-smi)"

        return (
            f"📊 *Нагрузка системы:*\n"
            f"🖥 CPU ({psutil.cpu_count()} ядер, {freq_str}): {make_bar(cpu)}\n"
            f"💾 RAM: {mem.used/1024**3:.1f}/{mem.total/1024**3:.1f} GB {make_bar(mem.percent)}"
            f"{gpu_str}"
        )

    @staticmethod
    def get_running_games() -> str:
        if not PSUTIL_AVAILABLE:
            return "❌ psutil не установлен"
        cats = {"Steam": [], "Epic Games": [], "GOG": [], "Другие": []}
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                exe  = (proc.info.get("exe") or "").lower()
                name = proc.info.get("name", "?")
                if "steamapps" in exe:
                    cats["Steam"].append(name)
                elif "epic games" in exe or "epicgames" in exe:
                    cats["Epic Games"].append(name)
                elif "gog galaxy" in exe:
                    cats["GOG"].append(name)
                elif any(x in exe for x in ["unity", "unreal", "games\\"]):
                    cats["Другие"].append(name)
            except Exception:
                pass
        msg   = "🎮 *Запущенные игры:*\n\n"
        found = False
        for cat, procs in cats.items():
            if procs:
                found = True
                unique = list(dict.fromkeys(procs))[:5]
                msg += f"*{cat}:*\n" + "\n".join(f"• `{p}`" for p in unique) + "\n"
        return msg if found else "🎮 Запущенных игр не обнаружено"

    @staticmethod
    def game_mode_on() -> str:
        for scheme in ("SCHEME_MIN", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"):
            r = subprocess.run(f"powercfg -setactive {scheme}", capture_output=True, shell=True)
            if r.returncode == 0:
                return "🎮 *Игровой режим ВКЛ*\nПлан: Максимальная производительность"
        return "⚠️ Не удалось включить игровой режим"

    @staticmethod
    def game_mode_off() -> str:
        for scheme in ("SCHEME_BALANCED", "381b4222-f694-41f0-9685-ff5bb260df2e"):
            r = subprocess.run(f"powercfg -setactive {scheme}", capture_output=True, shell=True)
            if r.returncode == 0:
                return "🛑 *Игровой режим ВЫКЛ*\nПлан: Сбалансированный"
        return "⚠️ Не удалось выключить игровой режим"

    @staticmethod
    def fps_boost() -> str:
        results = []
        shell_ps(
            'Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\GameBar" '
            '-Name "AllowAutoGameMode" -Value 0 -Force'
        )
        results.append("Xbox Game Bar: отключён")
        shell_ps(
            'reg add "HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences" '
            '/v "DirectXUserGlobalSettings" /t REG_SZ /d "SwapEffectUpgradeEnable=1;" /f'
        )
        results.append("GPU: High Performance")
        return "🚀 *FPS буст применён:*\n" + "\n".join(f"✅ {r}" for r in results)


# ─────────────────────────────────────────────────────────────────────────────
# МЕДИА
# ─────────────────────────────────────────────────────────────────────────────

class MediaUtils:

    @staticmethod
    def media_key(key: str) -> bool:
        VK = {
            "playpause": 0xB3,
            "nexttrack":  0xB0,
            "prevtrack":  0xB1,
            "stop":       0xB2,
        }
        vk = VK.get(key)
        if vk and is_windows:
            try:
                KEYEVENTF_KEYUP = 0x0002
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                time.sleep(0.05)
                ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
                return True
            except Exception as e:
                logger.warning(f"keybd_event: {e}")
        if PYAUTOGUI_AVAILABLE:
            try:
                pyautogui.press(key)
                return True
            except Exception:
                pass
        return False

    @staticmethod
    def discord_action(action: str) -> str:
        if not is_windows:
            return "❌ Только Windows"

        VK_CONTROL = 0x11
        VK_SHIFT   = 0x10
        VK_M       = 0x4D
        VK_D       = 0x44
        KEYEVENTF_KEYUP = 0x0002
        ke = ctypes.windll.user32.keybd_event

        def press_combo(key_vk):
            ke(VK_CONTROL, 0, 0, 0)
            ke(VK_SHIFT,   0, 0, 0)
            ke(key_vk,     0, 0, 0)
            time.sleep(0.05)
            ke(key_vk,     0, KEYEVENTF_KEYUP, 0)
            ke(VK_SHIFT,   0, KEYEVENTF_KEYUP, 0)
            ke(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

        try:
            if action == "mute":
                MediaUtils._focus_discord()
                time.sleep(0.2)
                press_combo(VK_M)
                return "🎙 Discord: переключён мут (Ctrl+Shift+M)"
            elif action == "deaf":
                MediaUtils._focus_discord()
                time.sleep(0.2)
                press_combo(VK_D)
                return "🎧 Discord: переключён звук (Ctrl+Shift+D)"
        except Exception as e:
            return f"❌ Ошибка: {e}"
        return "❌ Неизвестное действие"

    @staticmethod
    def _focus_discord():
        try:
            EnumWindows     = ctypes.windll.user32.EnumWindows
            GetWindowTextW  = ctypes.windll.user32.GetWindowTextW
            SetForeground   = ctypes.windll.user32.SetForegroundWindow
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible
            WNDENUMPROC     = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

            found = []
            def enum_cb(hwnd, lparam):
                if IsWindowVisible(hwnd):
                    buf = ctypes.create_unicode_buffer(256)
                    GetWindowTextW(hwnd, buf, 256)
                    if "discord" in buf.value.lower():
                        found.append(hwnd)
                return True

            EnumWindows(WNDENUMPROC(enum_cb), 0)
            if found:
                SetForeground(found[0])
        except Exception:
            pass

    @staticmethod
    def get_current_track() -> str:
        ps = (
            'try { '
            'Add-Type -AssemblyName Windows.Media; '
            '$mgr = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, '
            'Windows.Media, ContentType=WindowsRuntime]; '
            '$s = $mgr::RequestAsync().GetAwaiter().GetResult().GetCurrentSession(); '
            'if ($s) { '
            '  $info = $s.TryGetMediaPropertiesAsync().GetAwaiter().GetResult(); '
            '  Write-Output ($info.Artist + " - " + $info.Title) '
            '} else { Write-Output "nothing" } '
            '} catch { Write-Output "error" }'
        )
        out = shell_ps(ps, timeout=6)
        if out and out not in ("nothing", "error") and " - " in out:
            return f"🎵 Сейчас играет:\n*{out}*"
        return "🎵 Ничего не играет"

    @staticmethod
    def open_url(url: str) -> str:
        try:
            if is_windows:
                os.startfile(url)
            else:
                subprocess.Popen(["xdg-open", url])
            return "✅ Открываю в браузере..."
        except Exception as e:
            return f"❌ {e}"


# ─────────────────────────────────────────────────────────────────────────────
# ПОГОДА
# ─────────────────────────────────────────────────────────────────────────────

class WeatherUtils:
    LAT          = "52.4097"
    LON          = "17.0756"
    CITY_DISPLAY = "Swarzędz, Польша"

    @staticmethod
    def get_weather() -> str:
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={WeatherUtils.LAT}&longitude={WeatherUtils.LON}"
                f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,"
                f"weather_code,apparent_temperature,precipitation"
                f"&timezone=Europe/Warsaw"
            )
            data   = json.loads(urllib.request.urlopen(url, timeout=7).read())
            cur    = data["current"]
            temp   = cur["temperature_2m"]
            feels  = cur["apparent_temperature"]
            humid  = cur["relative_humidity_2m"]
            wind   = cur["wind_speed_10m"]
            precip = cur["precipitation"]
            wcode  = cur["weather_code"]
            desc   = WeatherUtils._wmo_desc(wcode)
            now    = datetime.now().strftime("%H:%M")

            return (
                f"🌤 *Погода в {WeatherUtils.CITY_DISPLAY}*\n"
                f"📅 Обновлено: {now}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"{desc}\n"
                f"🌡 Температура: `{temp}°C` (ощущается `{feels}°C`)\n"
                f"💧 Влажность: `{humid}%`\n"
                f"💨 Ветер: `{wind} км/ч`\n"
                f"🌧 Осадки: `{precip} мм`"
            )
        except Exception as e:
            try:
                url2 = f"https://wttr.in/{urllib.parse.quote('Swarzedz,Poland')}?format=3"
                out  = urllib.request.urlopen(url2, timeout=5).read().decode("utf-8").strip()
                return f"🌤 *Погода ({WeatherUtils.CITY_DISPLAY}):*\n{out}"
            except Exception as e2:
                return f"❌ Погода недоступна: {e} | {e2}"

    @staticmethod
    def _wmo_desc(code: int) -> str:
        codes = {
            0: "☀️ Ясно",
            1: "🌤 Преимущественно ясно", 2: "⛅ Переменная облачность", 3: "☁️ Пасмурно",
            45: "🌫 Туман", 48: "🌫 Изморозь",
            51: "🌦 Лёгкая морось", 53: "🌦 Морось", 55: "🌧 Сильная морось",
            61: "🌧 Слабый дождь", 63: "🌧 Дождь", 65: "🌧 Сильный дождь",
            71: "🌨 Слабый снег", 73: "❄️ Снег", 75: "❄️ Сильный снег",
            77: "🌨 Снежная крупа",
            80: "🌦 Ливень", 81: "🌧 Ливень", 82: "⛈ Сильный ливень",
            85: "🌨 Снежный ливень", 86: "❄️ Сильный снежный ливень",
            95: "⛈ Гроза", 96: "⛈ Гроза с градом", 99: "⛈ Сильная гроза с градом",
        }
        return codes.get(code, f"🌡 Код погоды: {code}")


# ─────────────────────────────────────────────────────────────────────────────
# НОВОСТИ
# ─────────────────────────────────────────────────────────────────────────────

class NewsUtils:

    @staticmethod
    def get_world_news(count: int = 7) -> str:
        sources = [
            ("Reuters",    "https://feeds.reuters.com/reuters/topNews"),
            ("BBC",        "https://feeds.bbci.co.uk/news/world/rss.xml"),
            ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
        ]
        headlines = []
        for source_name, url in sources:
            try:
                # FIX: передаём timeout в urlopen, а не в Request
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                xml = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", errors="replace")
                titles = re.findall(r'<title><!\[CDATA\[(.+?)\]\]></title>|<title>(.+?)</title>', xml)
                for t1, t2 in titles:
                    title = (t1 or t2).strip()
                    if title and len(title) > 15 and "RSS" not in title and source_name not in title:
                        title = re.sub(r'&amp;',  '&', title)
                        title = re.sub(r'&lt;',   '<', title)
                        title = re.sub(r'&gt;',   '>', title)
                        title = re.sub(r'&quot;', '"', title)
                        title = re.sub(r'&#\d+;', '',  title)
                        headlines.append((source_name, title))
                        if len(headlines) >= count:
                            break
            except Exception:
                pass
            if len(headlines) >= count:
                break

        if not headlines:
            return "📰 Новости временно недоступны"

        now = datetime.now().strftime("%H:%M")
        msg = f"📰 *Мировые новости* ({now}):\n━━━━━━━━━━━━━━━\n"
        for i, (src, title) in enumerate(headlines[:count], 1):
            msg += f"`{i}.` {title}\n_— {src}_\n\n"
        return msg.strip()


# ─────────────────────────────────────────────────────────────────────────────
# ГОЛОС
# ─────────────────────────────────────────────────────────────────────────────

class VoiceEngine:

    @staticmethod
    async def speak_edge(text: str) -> bool:
        """
        Edge-TTS синтез + воспроизведение через PowerShell MediaPlayer.
        FIX: убрана смешанная логика SoundPlayer/MediaPlayer.
        """
        try:
            import edge_tts
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                mp3_path = tmp.name

            await edge_tts.Communicate(text, ANIME_VOICE).save(mp3_path)

            # Воспроизводим через PowerShell WindowsMediaPlayer — надёжный способ
            ps_cmd = (
                f'Add-Type -AssemblyName PresentationCore; '
                f'$mp = [System.Windows.Media.MediaPlayer]::new(); '
                f'$mp.Open([uri]"{mp3_path}"); '
                f'$mp.Play(); '
                f'Start-Sleep -Milliseconds 500; '
                f'$dur = $mp.NaturalDuration; '
                f'if ($dur.HasTimeSpan) {{ Start-Sleep -Seconds ([math]::Ceiling($dur.TimeSpan.TotalSeconds) + 1) }}; '
                f'$mp.Close()'
            )
            # Запускаем асинхронно (не ждём окончания — пользователь не должен ждать)
            subprocess.Popen(
                ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_cmd],
                creationflags=subprocess.CREATE_NO_WINDOW if is_windows else 0
            )
            await asyncio.sleep(0.3)
            return True
        except Exception as e:
            logger.warning(f"Edge-TTS: {e}")
            return False

    @staticmethod
    def speak_pyttsx3(text: str) -> bool:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.setProperty("volume", 0.9)
            for v in engine.getProperty("voices"):
                if any(x in v.name.lower() for x in ("female", "zira", "irina", "helena", "zofia")):
                    engine.setProperty("voice", v.id)
                    break
            engine.say(text)
            engine.runAndWait()
            return True
        except Exception as e:
            logger.warning(f"pyttsx3: {e}")
            return False

    @staticmethod
    async def speak(text: str) -> bool:
        if len(text) > MAX_TEXT_LENGTH:
            return False
        if config.get("enable_voice_commands", True):
            if await VoiceEngine.speak_edge(text):
                return True
        if config.get("backup_voice_enabled", True):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(_executor, VoiceEngine.speak_pyttsx3, text)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# СКРИНШОТ
# ─────────────────────────────────────────────────────────────────────────────

def take_screenshot(path: str = "screenshot.png") -> str:
    with mss.mss() as sct:
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        img = sct.grab(monitor)
        mss.tools.to_png(img.rgb, img.size, output=path)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# УТИЛИТЫ
# ─────────────────────────────────────────────────────────────────────────────

class UtilityTools:

    @staticmethod
    def generate_password(length: int = 16) -> str:
        chars = string.ascii_letters + string.digits + "!@#$%^&*-_"
        pwd   = "".join(random.choice(chars) for _ in range(length))
        return f"🔐 *Пароль ({length} символов):*\n`{pwd}`"

    @staticmethod
    def calculate(expr: str) -> str:
        import math
        clean = expr.strip()
        if not re.match(r'^[\d\s\+\-\*\/\(\)\.\,\%\^a-z_]+$', clean.lower()):
            return "❌ Недопустимые символы. Пример: `2+2*5` или `sqrt(144)`"
        try:
            safe   = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
            safe["__builtins__"] = {}
            result = eval(clean, safe, {})
            if isinstance(result, float) and result == int(result):
                result = int(result)
            return f"📊 `{clean}` = `{result}`"
        except ZeroDivisionError:
            return "❌ Деление на ноль"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    @staticmethod
    def random_number(min_v: int = 1, max_v: int = 100) -> str:
        n = random.randint(min_v, max_v)
        return f"🎲 Случайное число [{min_v}–{max_v}]: *{n}*"

    @staticmethod
    def clipboard_history_msg() -> str:
        if not clipboard_history:
            return "📋 История буфера пуста"
        msg = "📋 *История буфера обмена:*\n\n"
        for i, item in enumerate(clipboard_history[:8], 1):
            preview = item[:80].replace("\n", " ").replace("`", "'")
            msg += f"`{i}.` {preview}{'…' if len(item) > 80 else ''}\n"
        return msg

    @staticmethod
    def taskmgr():
        try:
            subprocess.Popen("taskmgr.exe")
            return "🖥 Диспетчер задач открыт"
        except Exception as e:
            return f"❌ {e}"


# ─────────────────────────────────────────────────────────────────────────────
# КЛАВИАТУРЫ
# ─────────────────────────────────────────────────────────────────────────────

def kb(buttons):
    return InlineKeyboardMarkup(buttons)

BACK = [InlineKeyboardButton("◀️ Назад", callback_data="menu_main")]

def main_menu_kb():
    return kb([
        [InlineKeyboardButton("🎮 Игры",          callback_data="menu_games"),
         InlineKeyboardButton("🔊 Голос/Новости",  callback_data="menu_voice")],
        [InlineKeyboardButton("💻 Система",        callback_data="menu_system"),
         InlineKeyboardButton("🎵 Медиа",          callback_data="menu_media")],
        [InlineKeyboardButton("🌐 Сеть",           callback_data="menu_network"),
         InlineKeyboardButton("📊 Информация",     callback_data="menu_info")],
        [InlineKeyboardButton("🛠 Утилиты",        callback_data="menu_utils"),
         InlineKeyboardButton("⏰ Планировщик",    callback_data="menu_scheduler")],
        [InlineKeyboardButton("📸 Скриншот",       callback_data="action_screenshot"),
         InlineKeyboardButton("❓ Помощь",         callback_data="action_help")],
    ])

def games_kb():
    return kb([
        [InlineKeyboardButton("🎮 Режим ВКЛ",       callback_data="action_game_on"),
         InlineKeyboardButton("🛑 Режим ВЫКЛ",      callback_data="action_game_off")],
        [InlineKeyboardButton("📊 CPU/GPU нагрузка",callback_data="action_load"),
         InlineKeyboardButton("🎯 Список игр",       callback_data="action_games_list")],
        [InlineKeyboardButton("🔌 Пинг",             callback_data="action_ping"),
         InlineKeyboardButton("⚡ Сетевой буст",     callback_data="action_netboost")],
        [InlineKeyboardButton("🚀 FPS буст",         callback_data="action_fps_boost"),
         InlineKeyboardButton("🗑 Очистка temp",     callback_data="action_clean_temp")],
        [InlineKeyboardButton("📸 Скриншот",         callback_data="action_screenshot"),
         InlineKeyboardButton("⚙️ Планы питания",    callback_data="action_power_plans")],
        BACK,
    ])

def voice_kb():
    return kb([
        [InlineKeyboardButton("👋 Привет (вслух)",  callback_data="action_hello"),
         InlineKeyboardButton("😂 Анекдот (вслух)", callback_data="action_joke")],
        [InlineKeyboardButton("⏰ Время (вслух)",    callback_data="action_time"),
         InlineKeyboardButton("🌤 Погода Swarzędz", callback_data="action_weather")],
        [InlineKeyboardButton("🗣 Произнести...",    callback_data="action_say_prompt"),
         InlineKeyboardButton("📰 Новости мира",    callback_data="action_news")],
        BACK,
    ])

def system_kb():
    return kb([
        [InlineKeyboardButton("🔒 Блокировка",      callback_data="action_lock"),
         InlineKeyboardButton("💤 Сон",             callback_data="action_sleep")],
        [InlineKeyboardButton("⚠️ Выключить",       callback_data="action_shutdown_confirm"),
         InlineKeyboardButton("🔄 Перезагрузка",    callback_data="action_reboot_confirm")],
        [InlineKeyboardButton("🗑 Очистка temp",     callback_data="action_clean_temp"),
         InlineKeyboardButton("🖥 Дисплей ВЫКЛ",    callback_data="action_display_off")],
        [InlineKeyboardButton("📋 Буфер → чат",     callback_data="action_clip_send"),
         InlineKeyboardButton("📌 Текст → буфер",   callback_data="action_clip_set")],
        [InlineKeyboardButton("⚙️ Конфиг",          callback_data="action_config"),
         InlineKeyboardButton("🖥 Диспетчер задач", callback_data="action_taskmgr")],
        BACK,
    ])

def media_kb():
    return kb([
        [InlineKeyboardButton("⏯ Play/Pause",       callback_data="action_playpause"),
         InlineKeyboardButton("⏭ Следующий",        callback_data="action_next"),
         InlineKeyboardButton("⏮ Предыдущий",       callback_data="action_prev")],
        [InlineKeyboardButton("🔇 0%",              callback_data="action_vol_0"),
         InlineKeyboardButton("🔉 50%",              callback_data="action_vol_50"),
         InlineKeyboardButton("🔊 100%",             callback_data="action_vol_100")],
        [InlineKeyboardButton("🔈 -10%",             callback_data="action_vol_down"),
         InlineKeyboardButton("🎚 Громкость?",      callback_data="action_vol_get"),
         InlineKeyboardButton("🔊 +10%",             callback_data="action_vol_up")],
        [InlineKeyboardButton("🎵 Что играет?",      callback_data="action_nowplaying"),
         InlineKeyboardButton("⏹ Стоп",             callback_data="action_stop")],
        [InlineKeyboardButton("🎙 Discord Mute",     callback_data="action_discord_mute"),
         InlineKeyboardButton("🎧 Discord Deafen",   callback_data="action_discord_deaf")],
        [InlineKeyboardButton("🎧 SoundCloud...",    callback_data="action_sc_prompt"),
         InlineKeyboardButton("📺 YouTube...",       callback_data="action_yt_prompt")],
        BACK,
    ])

def network_kb():
    return kb([
        [InlineKeyboardButton("🌐 Локальный IP",    callback_data="action_localip"),
         InlineKeyboardButton("🌍 Внешний IP",      callback_data="action_extip")],
        [InlineKeyboardButton("🔌 Ping тест",       callback_data="action_ping"),
         InlineKeyboardButton("📶 WiFi сети",       callback_data="action_wifi")],
        [InlineKeyboardButton("🔑 Пароль WiFi",     callback_data="action_wifi_pass"),
         InlineKeyboardButton("📡 Bluetooth",       callback_data="action_bluetooth")],
        [InlineKeyboardButton("📊 Скорость сети",   callback_data="action_netspeed"),
         InlineKeyboardButton("🔥 Firewall",        callback_data="action_firewall")],
        [InlineKeyboardButton("🔌 Открытые порты",  callback_data="action_ports"),
         InlineKeyboardButton("⚡ Буст сети",       callback_data="action_netboost")],
        BACK,
    ])

def info_kb():
    return kb([
        [InlineKeyboardButton("🖥 О системе",        callback_data="action_sysinfo"),
         InlineKeyboardButton("💾 Диски",            callback_data="action_disks")],
        [InlineKeyboardButton("📊 Топ процессов",   callback_data="action_proctop"),
         InlineKeyboardButton("💻 Uptime",           callback_data="action_uptime")],
        [InlineKeyboardButton("📈 CPU/RAM",          callback_data="action_load"),
         InlineKeyboardButton("🌡 Температура CPU", callback_data="action_temp")],
        [InlineKeyboardButton("🔍 Найти процесс",   callback_data="action_find_proc"),
         InlineKeyboardButton("💥 Завершить процесс",callback_data="action_kill_proc")],
        BACK,
    ])

def utils_kb():
    return kb([
        [InlineKeyboardButton("📋 История буфера",  callback_data="action_clip_hist"),
         InlineKeyboardButton("🗑 Корзина",          callback_data="action_recycle")],
        [InlineKeyboardButton("🗑 Очистить корзину", callback_data="action_recycle_empty"),
         InlineKeyboardButton("📁 Рабочий стол",    callback_data="action_desktop")],
        [InlineKeyboardButton("🔐 Генер. пароль",   callback_data="action_passgen"),
         InlineKeyboardButton("🎲 Случ. число",     callback_data="action_random")],
        [InlineKeyboardButton("📊 Калькулятор...",  callback_data="action_calc_prompt"),
         InlineKeyboardButton("🔍 Поиск файлов...", callback_data="action_search_file_prompt")],
        [InlineKeyboardButton("📂 Открыть папку бота", callback_data="action_open_folder"),
         InlineKeyboardButton("🖥 Диспетчер задач", callback_data="action_taskmgr")],
        BACK,
    ])

def scheduler_kb():
    return kb([
        [InlineKeyboardButton("💤 Сон 15м",          callback_data="action_sleep_15"),
         InlineKeyboardButton("💤 Сон 30м",          callback_data="action_sleep_30"),
         InlineKeyboardButton("💤 Сон 60м",          callback_data="action_sleep_60")],
        [InlineKeyboardButton("⚠️ Выкл 15м",         callback_data="action_shutdown_15"),
         InlineKeyboardButton("⚠️ Выкл 30м",         callback_data="action_shutdown_30"),
         InlineKeyboardButton("⚠️ Выкл 60м",         callback_data="action_shutdown_60")],
        [InlineKeyboardButton("🔄 Ребут 15м",         callback_data="action_reboot_15"),
         InlineKeyboardButton("🔄 Ребут 30м",         callback_data="action_reboot_30")],
        [InlineKeyboardButton("⏱ Свой таймер /off",  callback_data="action_custom_timer"),
         InlineKeyboardButton("❌ Отменить таймер",   callback_data="action_cancel_timer")],
        BACK,
    ])

def confirm_kb(yes_cb: str, back_cb: str = "menu_system"):
    return kb([[
        InlineKeyboardButton("✅ Подтвердить", callback_data=yes_cb),
        InlineKeyboardButton("❌ Отмена",      callback_data=back_cb),
    ]])

MENUS = {
    "main":      ("🏠 *Главное меню*",             main_menu_kb),
    "games":     ("🎮 *Игры и производительность*", games_kb),
    "voice":     ("🔊 *Голос и новости*",           voice_kb),
    "system":    ("💻 *Система*",                   system_kb),
    "media":     ("🎵 *Медиа*",                     media_kb),
    "network":   ("🌐 *Сеть*",                      network_kb),
    "info":      ("📊 *Информация*",                info_kb),
    "utils":     ("🛠 *Утилиты*",                   utils_kb),
    "scheduler": ("⏰ *Планировщик*",               scheduler_kb),
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

async def answer_cb(query, text: str, reply_kb=None):
    if len(text) > 4000:
        text = text[:3990] + "\n_[обрезано]_"
    try:
        await query.edit_message_text(text, reply_markup=reply_kb, parse_mode=ParseMode.MARKDOWN)
    except Exception as edit_err:
        # FIX: Telegram бросает исключение если текст/разметка не изменились.
        # Пробуем отправить новым сообщением только если это реальная ошибка.
        err_msg = str(edit_err).lower()
        if "message is not modified" not in err_msg:
            try:
                await query.message.reply_text(text, reply_markup=reply_kb, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                logger.error(f"answer_cb: {e}")
    try:
        await query.answer()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_authorized(uid):
        await update.message.reply_text(
            f"❌ *Доступ запрещён*\nВаш ID: `{uid}`\nОбратитесь к администратору.",
            parse_mode=ParseMode.MARKDOWN
        )
        log_sec("UNAUTHORIZED", uid)
        return

    info   = await run_bg(WindowsUtils.get_system_info)
    vol    = get_volume()
    uptime = await run_bg(WindowsUtils.get_uptime)

    text = (
        f"🤖 *Windows Bot v{VERSION}*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🖥 `{info['hostname']}` · 👤 `{info['username']}`\n"
        f"🔑 {'✅ Admin' if is_admin else '👤 User'}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🖥 CPU: {make_bar(info.get('cpu_percent', 0))}\n"
        f"💾 RAM: {info.get('ram_used','?')}/{info.get('ram_gb','?')} GB {make_bar(info.get('ram_percent', 0))}\n"
        f"🔊 Громкость: {f'{vol}%' if vol >= 0 else 'N/A'}\n"
        f"{uptime}\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(text, reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN)


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACK HANDLER
# ─────────────────────────────────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = query.from_user.id

    if not is_authorized(uid):
        await query.answer("❌ Нет доступа", show_alert=True)
        return

    data = query.data

    if data.startswith("menu_"):
        name = data[5:]
        if name in MENUS:
            title, kb_fn = MENUS[name]
            await answer_cb(query, title, kb_fn())
        return

    await query.answer()

    # ── ИГРЫ ─────────────────────────────────────────────────────────────────
    if data == "action_game_on":
        result = await run_bg(GameUtils.game_mode_on)
        await answer_cb(query, result, games_kb())

    elif data == "action_game_off":
        result = await run_bg(GameUtils.game_mode_off)
        await answer_cb(query, result, games_kb())

    elif data == "action_load":
        await answer_cb(query, "⏳ Замеряю нагрузку...", games_kb())
        result = await run_bg(GameUtils.get_load)
        await answer_cb(query, result, games_kb())

    elif data == "action_games_list":
        result = await run_bg(GameUtils.get_running_games)
        await answer_cb(query, result, games_kb())

    elif data == "action_fps_boost":
        result = await run_bg(GameUtils.fps_boost)
        await answer_cb(query, result, games_kb())

    elif data == "action_power_plans":
        out = await run_bg(lambda: shell("powercfg /list"))
        await answer_cb(query, f"⚙️ *Планы питания:*\n```\n{out[:800]}\n```", games_kb())

    elif data == "action_netboost":
        await answer_cb(query, "⚡ Выполняю буст...", games_kb())
        result = await run_bg(NetworkUtils.netboost)
        await answer_cb(query, result, games_kb())

    # ── ГОЛОС ─────────────────────────────────────────────────────────────────
    elif data == "action_hello":
        texts = [
            "Привет! Всё работает, я на связи!",
            "Здравствуйте! Готов выполнять команды!",
            "Привет-привет! Чем могу помочь?",
        ]
        text = random.choice(texts)
        asyncio.create_task(VoiceEngine.speak(text))
        await answer_cb(query, f"🔊 _Произносится на ПК..._\n\n_{text}_", voice_kb())

    elif data == "action_joke":
        jokes = [
            "Почему программист мокрый? Потому что он в бассейне потоков!",
            "Что сказал ноль единице? Ты мне ноль внимания!",
            "Сколько программистов нужно вкрутить лампочку? Ни одного — это проблема железа!",
            "Программист умер. Стоит у врат рая. Бог говорит: твоя жизнь была хороша? Программист: да, всего один баг.",
        ]
        joke = random.choice(jokes)
        asyncio.create_task(VoiceEngine.speak(joke))
        await answer_cb(query, f"🔊 _Произносится на ПК..._\n\n😂 _{joke}_", voice_kb())

    elif data == "action_time":
        now    = datetime.now()
        months = ['января','февраля','марта','апреля','мая','июня',
                  'июля','августа','сентября','октября','ноября','декабря']
        text   = f"Сейчас {now:%H} часов {now:%M} минут, {now.day} {months[now.month-1]}"
        asyncio.create_task(VoiceEngine.speak(text))
        await answer_cb(
            query,
            f"⏰ *Время:* `{now:%H:%M:%S}`\n📅 *Дата:* `{now:%d.%m.%Y}`\n🔊 _Произносится на ПК..._",
            voice_kb()
        )

    elif data == "action_weather":
        await answer_cb(query, "🌤 Получаю погоду...", voice_kb())
        result = await run_bg(WeatherUtils.get_weather)
        await answer_cb(query, result, voice_kb())

    elif data == "action_news":
        await answer_cb(query, "📰 Загружаю новости...", voice_kb())
        result = await run_bg(NewsUtils.get_world_news)
        await answer_cb(query, result, voice_kb())

    elif data == "action_say_prompt":
        user_state[uid] = "say"
        await query.message.reply_text("🗣 Введите текст для произношения на ПК:")

    # ── СИСТЕМА ───────────────────────────────────────────────────────────────
    elif data == "action_lock":
        ok = WindowsUtils.lock()
        await answer_cb(query, "🔒 *ПК заблокирован*" if ok else "❌ Ошибка блокировки", system_kb())

    elif data == "action_sleep":
        # FIX: настоящий сон (Sleep), а не гибернация (/h)
        await answer_cb(query, "💤 *Переход в сон...*", system_kb())
        await run_bg(WindowsUtils.sleep_pc)

    elif data == "action_shutdown_confirm":
        await answer_cb(query, "⚠️ *Подтвердите выключение ПК*", confirm_kb("action_shutdown_do"))

    elif data == "action_shutdown_do":
        await answer_cb(query, "⚠️ *Выключение через 5 секунд...*")
        subprocess.Popen(["shutdown", "/s", "/f", "/t", "5"])

    elif data == "action_reboot_confirm":
        await answer_cb(query, "🔄 *Подтвердите перезагрузку*", confirm_kb("action_reboot_do"))

    elif data == "action_reboot_do":
        await answer_cb(query, "🔄 *Перезагрузка через 5 секунд...*")
        subprocess.Popen(["shutdown", "/r", "/f", "/t", "5"])

    elif data == "action_clean_temp":
        await answer_cb(query, "🗑 Очищаю...", system_kb())
        result = await run_bg(WindowsUtils.clean_temp)
        await answer_cb(query, result, system_kb())

    elif data == "action_display_off":
        WindowsUtils.turn_off_display()
        await answer_cb(query, "🖥 *Дисплей выключен*", system_kb())

    elif data == "action_clip_send":
        clip = await run_bg(ClipboardManager.get)
        ClipboardManager.add_to_history(clip)
        preview = clip[:1500]
        await query.message.reply_text(
            f"📋 *Буфер обмена:*\n```\n{preview}\n```",
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "action_clip_set":
        user_state[uid] = "clip_set"
        await query.message.reply_text("📌 Введите текст для копирования в буфер:")

    elif data == "action_config":
        vol = get_volume()
        msg = (
            f"⚙️ *Конфигурация:*\n"
            f"• Громкость: `{vol if vol >= 0 else 'N/A'}%`\n"
            f"• Edge-TTS: `{'ВКЛ' if config.get('enable_voice_commands') else 'ВЫКЛ'}`\n"
            f"• Голос: `{ANIME_VOICE}`\n"
            f"• Город погоды: `{WeatherUtils.CITY_DISPLAY}`\n"
        )
        await answer_cb(query, msg, system_kb())

    elif data == "action_taskmgr":
        result = await run_bg(UtilityTools.taskmgr)
        await answer_cb(query, result, system_kb())

    # ── МЕДИА ─────────────────────────────────────────────────────────────────
    elif data == "action_playpause":
        MediaUtils.media_key("playpause")
        await answer_cb(query, "⏯ Play/Pause", media_kb())

    elif data == "action_next":
        MediaUtils.media_key("nexttrack")
        await answer_cb(query, "⏭ Следующий трек", media_kb())

    elif data == "action_prev":
        MediaUtils.media_key("prevtrack")
        await answer_cb(query, "⏮ Предыдущий трек", media_kb())

    elif data == "action_stop":
        MediaUtils.media_key("stop")
        await answer_cb(query, "⏹ Стоп", media_kb())

    elif data == "action_vol_0":
        r = await run_bg(set_volume, 0);    await answer_cb(query, r, media_kb())
    elif data == "action_vol_50":
        r = await run_bg(set_volume, 50);   await answer_cb(query, r, media_kb())
    elif data == "action_vol_100":
        r = await run_bg(set_volume, 100);  await answer_cb(query, r, media_kb())

    elif data == "action_vol_up":
        cur = get_volume()
        r   = await run_bg(set_volume, min(100, (cur if cur >= 0 else 50) + 10))
        await answer_cb(query, r, media_kb())

    elif data == "action_vol_down":
        cur = get_volume()
        r   = await run_bg(set_volume, max(0, (cur if cur >= 0 else 50) - 10))
        await answer_cb(query, r, media_kb())

    elif data == "action_vol_get":
        vol = get_volume()
        bar = make_bar(vol) if vol >= 0 else "N/A"
        await answer_cb(query, f"🔊 Громкость: {bar}", media_kb())

    elif data == "action_nowplaying":
        result = await run_bg(MediaUtils.get_current_track)
        await answer_cb(query, result, media_kb())

    elif data == "action_discord_mute":
        result = await run_bg(MediaUtils.discord_action, "mute")
        await answer_cb(query, result, media_kb())

    elif data == "action_discord_deaf":
        result = await run_bg(MediaUtils.discord_action, "deaf")
        await answer_cb(query, result, media_kb())

    elif data == "action_sc_prompt":
        user_state[uid] = "sc"
        await query.message.reply_text("🎧 Введите запрос для SoundCloud:")

    elif data == "action_yt_prompt":
        user_state[uid] = "yt"
        await query.message.reply_text("📺 Введите запрос для YouTube:")

    # ── СЕТЬ ─────────────────────────────────────────────────────────────────
    elif data == "action_localip":
        await answer_cb(query, NetworkUtils.get_local_ips(), network_kb())

    elif data == "action_extip":
        await answer_cb(query, "🌍 Получаю...", network_kb())
        r = await run_bg(NetworkUtils.get_external_ip)
        await answer_cb(query, r, network_kb())

    elif data == "action_ping":
        await answer_cb(query, "🌐 Пингую серверы...", network_kb())
        r = await run_bg(NetworkUtils.ping_test)
        await answer_cb(query, r, network_kb())

    elif data == "action_wifi":
        await answer_cb(query, "📶 Сканирую...", network_kb())
        r = await run_bg(NetworkUtils.get_wifi_networks)
        await answer_cb(query, r, network_kb())

    elif data == "action_wifi_pass":
        r = await run_bg(NetworkUtils.get_wifi_password)
        await answer_cb(query, r, network_kb())

    elif data == "action_bluetooth":
        await answer_cb(query, "📡 Ищу устройства...", network_kb())
        r = await run_bg(NetworkUtils.get_bluetooth_devices)
        await answer_cb(query, r, network_kb())

    elif data == "action_netspeed":
        await answer_cb(query, "📊 Измеряю скорость (2 сек)...", network_kb())
        r = await run_bg(NetworkUtils.get_network_speed)
        await answer_cb(query, r, network_kb())

    elif data == "action_firewall":
        r = await run_bg(NetworkUtils.get_firewall_status)
        await answer_cb(query, r, network_kb())

    elif data == "action_ports":
        await answer_cb(query, "🔌 Получаю порты...", network_kb())
        r = await run_bg(NetworkUtils.get_open_ports)
        await answer_cb(query, r, network_kb())

    # ── ИНФОРМАЦИЯ ────────────────────────────────────────────────────────────
    elif data == "action_sysinfo":
        info   = await run_bg(WindowsUtils.get_system_info)
        uptime = await run_bg(WindowsUtils.get_uptime)
        msg = (
            f"🖥 *Система:*\n"
            f"• ОС: `{info['os']} {info['version'][:30]}`\n"
            f"• Хост: `{info['hostname']}` | Юзер: `{info['username']}`\n"
            f"• CPU ({info['cpu_cores']} ядер): {make_bar(info.get('cpu_percent', 0))}\n"
            f"• RAM: {info.get('ram_used','?')}/{info.get('ram_gb','?')} GB {make_bar(info.get('ram_percent', 0))}\n"
            f"• {uptime}\n"
            f"• Python `{info['python_version']}` | {'✅ Admin' if is_admin else '👤 User'}"
        )
        await answer_cb(query, msg, info_kb())

    elif data == "action_disks":
        info = await run_bg(WindowsUtils.get_system_info)
        msg  = "💾 *Диски:*\n"
        for dev, sp in info.get("disk_space", {}).items():
            msg += f"\n*{dev}* {make_bar(sp['percent'])}\nСвободно: `{sp['free_gb']:.1f}` / `{sp['total_gb']:.1f}` GB\n"
        await answer_cb(query, msg or "💾 Нет данных о дисках", info_kb())

    elif data == "action_proctop":
        await answer_cb(query, "⏳ Замеряю (1-2 сек)...", info_kb())
        result = await run_bg(ProcessManager.get_top)
        await answer_cb(query, result, info_kb())

    elif data == "action_uptime":
        r = await run_bg(WindowsUtils.get_uptime)
        await answer_cb(query, r, info_kb())

    elif data == "action_temp":
        await answer_cb(query, "🌡 Получаю температуру...", info_kb())
        r = await run_bg(WindowsUtils.get_cpu_temp)
        await answer_cb(query, r, info_kb())

    elif data == "action_find_proc":
        user_state[uid] = "find_proc"
        await query.message.reply_text("🔍 Введите имя процесса:")

    elif data == "action_kill_proc":
        user_state[uid] = "kill_proc"
        await query.message.reply_text("💥 Введите имя процесса для завершения (например `notepad.exe`):")

    # ── УТИЛИТЫ ───────────────────────────────────────────────────────────────
    elif data == "action_clip_hist":
        await answer_cb(query, UtilityTools.clipboard_history_msg(), utils_kb())

    elif data == "action_recycle":
        r = await run_bg(FileManager.get_recycle_bin)
        await answer_cb(query, r, utils_kb())

    elif data == "action_recycle_empty":
        r = await run_bg(FileManager.empty_recycle_bin)
        await answer_cb(query, r, utils_kb())

    elif data == "action_desktop":
        r = await run_bg(FileManager.list_dir)
        await answer_cb(query, r, utils_kb())

    elif data == "action_passgen":
        await answer_cb(query, UtilityTools.generate_password(), utils_kb())

    elif data == "action_random":
        await answer_cb(query, UtilityTools.random_number(), utils_kb())

    elif data == "action_calc_prompt":
        user_state[uid] = "calc"
        await query.message.reply_text("📊 Введите выражение (пример: `2+2*5` или `sqrt(144)`):")

    elif data == "action_search_file_prompt":
        user_state[uid] = "search_file"
        await query.message.reply_text("🔍 Введите название файла для поиска:")

    elif data == "action_open_folder":
        r = await run_bg(FileManager.open_folder, ".")
        await answer_cb(query, r, utils_kb())

    # ── ПЛАНИРОВЩИК ───────────────────────────────────────────────────────────
    elif data == "action_sleep_15":
        # FIX: реальный сон через таймер shutdown не поддерживается для Sleep.
        # Используем PowerShell с Start-Sleep + SetSuspendState.
        subprocess.Popen(
            'powershell -Command "Start-Sleep 900; '
            'Add-Type -Assembly System.Windows.Forms; '
            '[System.Windows.Forms.Application]::SetSuspendState(\'Suspend\', $false, $false)"',
            shell=True, creationflags=subprocess.CREATE_NO_WINDOW if is_windows else 0
        )
        await answer_cb(query, "💤 *Сон через 15 минут*", scheduler_kb())

    elif data == "action_sleep_30":
        subprocess.Popen(
            'powershell -Command "Start-Sleep 1800; '
            'Add-Type -Assembly System.Windows.Forms; '
            '[System.Windows.Forms.Application]::SetSuspendState(\'Suspend\', $false, $false)"',
            shell=True, creationflags=subprocess.CREATE_NO_WINDOW if is_windows else 0
        )
        await answer_cb(query, "💤 *Сон через 30 минут*", scheduler_kb())

    elif data == "action_sleep_60":
        subprocess.Popen(
            'powershell -Command "Start-Sleep 3600; '
            'Add-Type -Assembly System.Windows.Forms; '
            '[System.Windows.Forms.Application]::SetSuspendState(\'Suspend\', $false, $false)"',
            shell=True, creationflags=subprocess.CREATE_NO_WINDOW if is_windows else 0
        )
        await answer_cb(query, "💤 *Сон через 60 минут*", scheduler_kb())

    elif data == "action_shutdown_15":
        subprocess.Popen("shutdown /s /f /t 900", shell=True)
        await answer_cb(query, "⚠️ *Выключение через 15 минут*", scheduler_kb())
    elif data == "action_shutdown_30":
        subprocess.Popen("shutdown /s /f /t 1800", shell=True)
        await answer_cb(query, "⚠️ *Выключение через 30 минут*", scheduler_kb())
    elif data == "action_shutdown_60":
        subprocess.Popen("shutdown /s /f /t 3600", shell=True)
        await answer_cb(query, "⚠️ *Выключение через 60 минут*", scheduler_kb())
    elif data == "action_reboot_15":
        subprocess.Popen("shutdown /r /f /t 900", shell=True)
        await answer_cb(query, "🔄 *Перезагрузка через 15 минут*", scheduler_kb())
    elif data == "action_reboot_30":
        subprocess.Popen("shutdown /r /f /t 1800", shell=True)
        await answer_cb(query, "🔄 *Перезагрузка через 30 минут*", scheduler_kb())

    # FIX: action_cancel_timer теперь обрабатывается и в callback (не только в /off)
    elif data == "action_cancel_timer":
        r   = subprocess.run("shutdown /a", capture_output=True, shell=True)
        msg = "✅ *Таймер отменён*" if r.returncode == 0 else "ℹ️ Нет активных таймеров shutdown"
        await answer_cb(query, msg, scheduler_kb())

    elif data == "action_custom_timer":
        await answer_cb(query,
            "⏱ *Свой таймер:*\n"
            "`/off 30` — выкл через 30м\n"
            "`/off 1:30` — выкл через 1ч30м\n"
            "`/off reboot 20` — ребут через 20м\n"
            "`/off cancel` — отмена",
            scheduler_kb()
        )

    # ── СКРИНШОТ ─────────────────────────────────────────────────────────────
    elif data == "action_screenshot":
        try:
            path = await run_bg(take_screenshot)
            await query.message.reply_photo(photo=open(path, "rb"), caption="📸 Скриншот")
        except Exception as e:
            await query.message.reply_text(f"❌ {e}")

    # ── ПОМОЩЬ ────────────────────────────────────────────────────────────────
    elif data == "action_help":
        await answer_cb(query, (
            f"❓ *Windows Bot v{VERSION}*\n\n"
            "*Команды:*\n"
            "`/start` — главное меню\n"
            "`/say <текст>` — произнести вслух\n"
            "`/volume <0-100>` — громкость\n"
            "`/sc <запрос>` — SoundCloud\n"
            "`/yt <запрос>` — YouTube\n"
            "`/screenshot` — скриншот\n"
            "`/sysinfo` — инфо о системе\n"
            "`/off [минуты]` — выключить\n"
            "`/off reboot [мин]` — перезагрузить\n"
            "`/off cancel` — отменить таймер\n"
            "`/adduser <id>` — добавить юзера\n"
            "`/removeuser <id>` — удалить юзера"
        ), main_menu_kb())


# ─────────────────────────────────────────────────────────────────────────────
# ТЕКСТОВЫЙ ВВОД
# ─────────────────────────────────────────────────────────────────────────────

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    if not is_authorized(uid):
        return
    text  = update.message.text.strip()
    state = user_state.pop(uid, None)

    if not state:
        await update.message.reply_text("🏠", reply_markup=main_menu_kb())
        return

    if state == "say":
        asyncio.create_task(VoiceEngine.speak(text))
        await update.message.reply_text("🔊 _Произносится на ПК..._", parse_mode=ParseMode.MARKDOWN)

    elif state == "sc":
        url = text if text.startswith("http") else f"https://soundcloud.com/search?q={urllib.parse.quote(text)}"
        MediaUtils.open_url(url)
        await update.message.reply_text(f"🎧 Открываю SoundCloud: `{text}`", parse_mode=ParseMode.MARKDOWN)

    elif state == "yt":
        url = text if text.startswith("http") else f"https://www.youtube.com/results?search_query={urllib.parse.quote(text)}"
        MediaUtils.open_url(url)
        await update.message.reply_text(f"📺 Открываю YouTube: `{text}`", parse_mode=ParseMode.MARKDOWN)

    elif state == "calc":
        await update.message.reply_text(UtilityTools.calculate(text), parse_mode=ParseMode.MARKDOWN)

    elif state == "search_file":
        await update.message.reply_text("🔍 Ищу...")
        result = await run_bg(FileManager.search, text)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)

    elif state == "clip_set":
        ok = await run_bg(ClipboardManager.set, text)
        await update.message.reply_text("✅ Скопировано в буфер обмена" if ok else "❌ Ошибка")

    elif state == "find_proc":
        result = await run_bg(ProcessManager.find, text)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)

    elif state == "kill_proc":
        result = await run_bg(ProcessManager.kill, text)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)


# ─────────────────────────────────────────────────────────────────────────────
# КОМАНДЫ
# ─────────────────────────────────────────────────────────────────────────────

async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("Использование: `/say <текст>`", parse_mode=ParseMode.MARKDOWN)
        return
    text = " ".join(context.args)
    asyncio.create_task(VoiceEngine.speak(text))
    await update.message.reply_text("🔊 _Произносится..._", parse_mode=ParseMode.MARKDOWN)


async def volume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    if not context.args:
        vol = get_volume()
        await update.message.reply_text(
            f"🔊 Текущая громкость: {make_bar(vol) if vol >= 0 else 'N/A'}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    try:
        level  = int(context.args[0])
        result = await run_bg(set_volume, level)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        await update.message.reply_text("❌ Число 0-100")


async def sc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("Использование: `/sc <запрос>`", parse_mode=ParseMode.MARKDOWN)
        return
    q   = " ".join(context.args)
    url = q if q.startswith("http") else f"https://soundcloud.com/search?q={urllib.parse.quote(q)}"
    MediaUtils.open_url(url)
    await update.message.reply_text(f"🎧 SoundCloud: `{q}`", parse_mode=ParseMode.MARKDOWN)


async def yt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("Использование: `/yt <запрос>`", parse_mode=ParseMode.MARKDOWN)
        return
    q   = " ".join(context.args)
    url = q if q.startswith("http") else f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}"
    MediaUtils.open_url(url)
    await update.message.reply_text(f"📺 YouTube: `{q}`", parse_mode=ParseMode.MARKDOWN)


async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    try:
        path = await run_bg(take_screenshot)
        await update.message.reply_photo(photo=open(path, "rb"), caption="📸")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def sysinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    info   = await run_bg(WindowsUtils.get_system_info)
    uptime = await run_bg(WindowsUtils.get_uptime)
    await update.message.reply_text(
        f"🖥 `{info['hostname']}` | CPU: {make_bar(info.get('cpu_percent',0))}\n"
        f"💾 RAM: {info.get('ram_used','?')}/{info.get('ram_gb','?')} GB {make_bar(info.get('ram_percent',0))}\n"
        f"{uptime}",
        reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN
    )


async def adduser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ADMIN_ID:
        await update.message.reply_text("❌ Только главный администратор")
        return
    if not context.args:
        await update.message.reply_text("Использование: `/adduser <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        nid = int(context.args[0])
        whitelist.add(nid)
        ConfigManager.save_whitelist()
        log_sec("USER_ADDED", update.effective_user.id, f"added={nid}")
        await update.message.reply_text(f"✅ Добавлен: `{nid}`", parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        await update.message.reply_text("❌ Числовой ID")


async def removeuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ADMIN_ID:
        await update.message.reply_text("❌ Только главный администратор")
        return
    if not context.args:
        await update.message.reply_text("Использование: `/removeuser <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        rid = int(context.args[0])
        if rid == MASTER_ADMIN_ID:
            await update.message.reply_text("❌ Нельзя удалить главного администратора")
            return
        whitelist.discard(rid)
        ConfigManager.save_whitelist()
        await update.message.reply_text(f"✅ Удалён: `{rid}`", parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        await update.message.reply_text("❌ Числовой ID")


async def off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    args = list(context.args)

    if args and args[0].lower() in ("cancel", "отмена", "стоп"):
        r   = subprocess.run("shutdown /a", capture_output=True, shell=True)
        msg = "✅ *Таймер отменён*" if r.returncode == 0 else "ℹ️ Нет активных таймеров"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())
        return

    reboot = False
    if args and args[0].lower() in ("reboot", "restart", "r"):
        reboot = True
        args   = args[1:]

    seconds, time_str = 5, "сейчас"
    if args:
        raw = args[0].replace(",", ".")
        try:
            if ":" in raw:
                h, m     = int(raw.split(":")[0]), int(raw.split(":")[1])
                seconds  = h * 3600 + m * 60
                time_str = f"{h}ч {m}м"
            else:
                # FIX: корректное вычисление часов/минут из дробных минут
                total_sec = int(float(raw) * 60)
                seconds   = total_sec
                h, m      = divmod(total_sec // 60, 60)
                rem_m     = (total_sec // 60) % 60
                if h:
                    time_str = f"{h}ч {rem_m}м"
                else:
                    time_str = f"{total_sec // 60}м"
        except ValueError:
            await update.message.reply_text(
                "❌ Формат: `/off 30` или `/off 1:30`", parse_mode=ParseMode.MARKDOWN
            )
            return

    flag  = "/r" if reboot else "/s"
    label = "🔄 Перезагрузка" if reboot else "⚠️ Выключение"
    subprocess.Popen(f"shutdown {flag} /f /t {seconds}", shell=True)

    cancel_kb = kb([[InlineKeyboardButton("❌ Отменить", callback_data="action_cancel_timer")]])
    await update.message.reply_text(
        f"{label} через *{time_str}*",
        parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_kb
    )


# ─────────────────────────────────────────────────────────────────────────────
# УВЕДОМЛЕНИЕ ПРИ ЗАПУСКЕ
# ─────────────────────────────────────────────────────────────────────────────

async def on_startup(application: Application):
    if not config.get("startup_notification", True):
        return
    try:
        info   = WindowsUtils.get_system_info()
        uptime = WindowsUtils.get_uptime()
        msg = (
            f"🟢 *Windows Bot v{VERSION} запущен!*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🖥 `{info['hostname']}` · 👤 `{info['username']}`\n"
            f"🖥 CPU: {make_bar(info.get('cpu_percent', 0))}\n"
            f"💾 RAM: {make_bar(info.get('ram_percent', 0))}\n"
            f"⏰ `{datetime.now():%Y-%m-%d %H:%M:%S}`\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )
        await application.bot.send_message(
            chat_id=MASTER_ADMIN_ID,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_kb()
        )
        logger.info("Startup notification sent")
    except Exception as e:
        logger.error(f"Startup notification failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────────────────────────────────────

def run_bot():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    cmds = [
        ("start",       start),
        ("say",         say_command),
        ("volume",      volume_command),
        ("sc",          sc_command),
        ("yt",          yt_command),
        ("screenshot",  screenshot_command),
        ("sysinfo",     sysinfo_command),
        ("adduser",     adduser_command),
        ("removeuser",  removeuser_command),
        ("off",         off_command),
    ]
    for cmd, fn in cmds:
        app.add_handler(CommandHandler(cmd, fn))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info(f">>> Windows Bot v{VERSION} started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()