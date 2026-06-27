import re
import subprocess

from PyQt6.QtCore import QThread, pyqtSignal

from config import SVDRP_CMD, SSH_TARGET, SSH_SIGNAL_CMD, REMOTE_EPG_PATH
from epg_parser import _parse_epg, _parse_timers, _mark_recorded_events


def vdr_command(*args, timeout: int = 10) -> subprocess.CompletedProcess:
    """Run a svdrpsend command on the VDR server via SSH."""
    return subprocess.run(
        ["ssh", SSH_TARGET, "svdrpsend", *args],
        capture_output=True, text=True, timeout=timeout,
    )


def get_channels():
    try:
        result = subprocess.run(
            SVDRP_CMD, check=True, capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Délai SSH dépassé (VDR server inaccessible ?)")
    except Exception as e:
        raise RuntimeError(f"Commande VDR échouée : {e}")

    channels = []
    for line in result.stdout.splitlines():
        m = re.match(r"250-?(\d+)\s+([^;]+);", line)
        if m:
            channels.append((int(m.group(1)), m.group(2).strip()))

    if not channels:
        raise RuntimeError("Aucune chaîne trouvée dans la sortie de svdrpsend LSTC.")
    return channels


class ChannelWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def run(self):
        try:
            self.finished.emit(get_channels())
        except Exception as e:
            self.error.emit(str(e))


class SignalWorker(QThread):
    result = pyqtSignal(str)

    def run(self):
        try:
            r = subprocess.run(
                SSH_SIGNAL_CMD, capture_output=True, text=True, timeout=5,
            )
            out = r.stdout.strip() or r.stderr.strip()
            self.result.emit(out or "Signal: N/A")
        except subprocess.TimeoutExpired:
            self.result.emit("Signal: timeout")
        except Exception as e:
            self.result.emit(f"Signal: erreur ({e})")


class EPGLoaderWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def run(self):
        try:
            result = subprocess.run(
                ["ssh", SSH_TARGET, "cat", REMOTE_EPG_PATH],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())
            epg_data = _parse_epg(result.stdout)
            try:
                lstc = vdr_command("LSTC")
                lstt = vdr_command("LSTT")
                _mark_recorded_events(epg_data, _parse_timers(lstt.stdout, lstc.stdout))
            except Exception:
                pass  # timers are optional
            self.finished.emit(epg_data)
        except subprocess.TimeoutExpired:
            self.error.emit("Délai SSH dépassé lors du chargement EPG.")
        except Exception as e:
            self.error.emit(str(e))


class TimerLoaderWorker(QThread):
    finished = pyqtSignal(list)

    def run(self):
        try:
            lstc = vdr_command("LSTC")
            lstt = vdr_command("LSTT")
            self.finished.emit(_parse_timers(lstt.stdout, lstc.stdout))
        except Exception:
            self.finished.emit([])
