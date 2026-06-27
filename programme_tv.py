#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import subprocess
from datetime import datetime, timedelta, date
from typing import List

from PyQt6.QtCore import Qt, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QSizePolicy,
    QPushButton,
    QToolTip,
    QFrame,
    QTextEdit,
    QMessageBox,
)


# ============================
# SSH / EPG CONFIG
# ============================

# Note: These values are now defined in config.py
# Import them if you need to use this module standalone
# For now, they're injected at runtime from the main application
SSH_BASE_CMD = None  # Will be set from config
REMOTE_EPG_DATA_PATH = None  # Will be set from config


# --------------------------
# Display constants
# --------------------------

CHANNEL_COLUMN_WIDTH = 140
ROW_HEIGHT = 40
HEADER_HEIGHT = 30


# --------------------------
# Channel display order
# --------------------------

CHANNEL_ORDER = {
    "TF1": 1,
    "France 2": 2,
    "France 3": 3,
    "Canal+": 4,
    "France 5": 5,
    "M6": 6,
    "Arte": 7,
    "C8": 8,
    "W9": 9,
    "TMC": 10,
    "TFX": 11,
    "NRJ 12": 12,
    "LCP": 13,
    "France 4": 14,
    "BFM TV": 15,
    "CNews": 16,
    "CStar": 17,
    "Gulli": 18,
    "TF1 Séries Films": 20,
    "L'Équipe": 21,
    "6ter": 22,
    "RMC Story": 23,
    "RMC Découverte": 24,
    "Chérie 25": 25,
}


def normalize_channel_name(name: str) -> str:
    s = name.strip().lower()
    s = " ".join(s.split())

    # common name variants
    replacements = {
        "tf1 hd": "tf1",
        "france2": "france 2",
        "france 2 hd": "france 2",
        "france3": "france 3",
        "france 3 hd": "france 3",
        "canal +": "canal+",
        "canal+ hd": "canal+",
        "france5": "france 5",
        "france 5 hd": "france 5",
        "arte hd": "arte",
        "c8 hd": "c8",
        "w9 hd": "w9",
        "tmc hd": "tmc",
        "tfx hd": "tfx",
        "nrj12": "nrj 12",
        "nrj 12 hd": "nrj 12",
        "lcp hd": "lcp",
        "france4": "france 4",
        "france 4 hd": "france 4",
        "bfmtv": "bfm tv",
        "bfm tv hd": "bfm tv",
        "cnews hd": "cnews",
        "cstar hd": "cstar",
        "gulli hd": "gulli",
        "tf1 series films": "tf1 séries films",
        "tf1 séries films hd": "tf1 séries films",
        "l'equipe": "l'équipe",
        "l equipe": "l'équipe",
        "l'équipe hd": "l'équipe",
        "6ter hd": "6ter",
        "rmc story hd": "rmc story",
        "rmc decouverte": "rmc découverte",
        "rmc découverte hd": "rmc découverte",
        "cherie 25": "chérie 25",
        "cherie 25 hd": "chérie 25",
    }

    return replacements.get(s, s)


CHANNEL_ORDER_NORMALIZED = {
    normalize_channel_name(name): number
    for name, number in CHANNEL_ORDER.items()
}


# --------------------------
# SSH + EPG data parser
# --------------------------

class RemoteCommandRunner:
    """
    Runs commands on the remote machine.

    base_cmd e.g.:
        ["ssh", "your-vdr-server"]
    """

    def __init__(self, base_cmd=None):
        if base_cmd is None:
            base_cmd = ["ssh", "your-vdr-server"]
        self.base_cmd = base_cmd

    def run(self, *args: str) -> subprocess.CompletedProcess:
        cmd = self.base_cmd + list(args)
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return result


class RemoteEpgDataLoader:
    """
    Reads the VDR epg.data file via SSH and returns a dict:

    {
      "channels": [
        {
          "number": int,
          "name": str,
          "vdr_channel_id": str,
          "events": [
            {
              "id": str,
              "title": str,
              "description": str,
              "start": "YYYY-MM-DDTHH:MM:SS",
              "end":   "YYYY-MM-DDTHH:MM:SS",
              "channel_number": int,
              "channel_name": str,
              "vdr_channel_id": str,
              "recorded": bool (optional)
            },
            ...
          ]
        },
        ...
      ]
    }
    """

    def __init__(self, runner: RemoteCommandRunner, remote_path: str):
        self.runner = runner
        self.remote_path = remote_path

    def load(self) -> dict:
        result = self.runner.run("cat", self.remote_path)
        if result.returncode != 0:
            raise RuntimeError(
                f"SSH error reading {self.remote_path}: "
                f"{result.stderr.strip()}"
            )

        channels = []
        current_channel = None
        current_event = None
        current_desc_lines: List[str] = []

        for raw in result.stdout.splitlines():
            line = raw.rstrip("\n")
            if not line:
                continue

            prefix = line[0]

            # New channel: "C <channelID> <name...>"
            if prefix == "C" and line.startswith("C "):
                if current_channel is not None and current_event is not None:
                    self._finalize_and_append_event(
                        current_channel, current_event, current_desc_lines
                    )
                    current_event = None
                    current_desc_lines = []

                parts = line.split()
                if len(parts) >= 3:
                    vdr_channel_id = parts[1]
                    name = " ".join(parts[2:]).strip()
                else:
                    vdr_channel_id = "1"
                    name = "Unknown"

                normalized_name = normalize_channel_name(name)
                ch_num = CHANNEL_ORDER_NORMALIZED.get(normalized_name, 9999)

                current_channel = {
                    "number": ch_num,
                    "name": name,
                    "vdr_channel_id": vdr_channel_id,
                    "events": [],
                }
                channels.append(current_channel)
                continue

            if current_channel is None:
                continue

            # New event: "E <eventID> <start> <duration> ..."
            if prefix == "E" and line.startswith("E "):
                if current_event is not None:
                    self._finalize_and_append_event(
                        current_channel, current_event, current_desc_lines
                    )

                parts = line.split()
                if len(parts) < 4:
                    current_event = None
                    current_desc_lines = []
                    continue

                try:
                    event_id = parts[1]
                    start_ts = int(parts[2])
                    duration_sec = int(parts[3])
                except ValueError:
                    current_event = None
                    current_desc_lines = []
                    continue

                start_dt = datetime.fromtimestamp(start_ts)
                end_dt = start_dt + timedelta(seconds=duration_sec)

                current_event = {
                    "id": event_id,
                    "title": "",
                    "short_text": "",
                    "description": "",
                    "start_dt": start_dt,
                    "end_dt": end_dt,
                }
                current_desc_lines = []
                continue

            if current_event is None:
                continue

            # Title: "T ..."
            if prefix == "T" and line.startswith("T "):
                current_event["title"] = line[2:].strip()
                continue

            # Short text: "S ..."
            if prefix == "S" and line.startswith("S "):
                current_event["short_text"] = line[2:].strip()
                continue

            # Description: "D..."
            if prefix == "D":
                desc = line[1:].lstrip()
                current_desc_lines.append(desc)
                continue

            # End of event: "e"
            if prefix == "e":
                self._finalize_and_append_event(
                    current_channel, current_event, current_desc_lines
                )
                current_event = None
                current_desc_lines = []
                continue

        if current_channel is not None and current_event is not None:
            self._finalize_and_append_event(
                current_channel, current_event, current_desc_lines
            )

        return {"channels": channels}

    def _finalize_and_append_event(self, channel: dict, event: dict, desc_lines: List[str]):
        full_desc = self._build_full_description(
            event.get("short_text", ""),
            desc_lines,
        )
        event["description"] = full_desc
        start_dt = event["start_dt"]
        end_dt = event["end_dt"]
        event["start"] = start_dt.isoformat()
        event["end"] = end_dt.isoformat()
        for k in ("start_dt", "end_dt", "short_text"):
            event.pop(k, None)

        event["channel_number"] = channel["number"]
        event["channel_name"] = channel["name"]
        event["vdr_channel_id"] = channel["vdr_channel_id"]
        channel["events"].append(event)

    @staticmethod
    def _build_full_description(short_text: str, desc_lines: List[str]) -> str:
        desc_long = "\n".join(desc_lines).strip()
        if short_text and desc_long:
            return short_text + "\n\n" + desc_long
        elif short_text:
            return short_text
        else:
            return desc_long


# --------------------------
# Custom widgets
# --------------------------

class TimeHeaderWidget(QWidget):
    """Time axis (3-hour window) with hour markers."""

    def __init__(self, window_start: datetime, window_end: datetime, parent=None):
        super().__init__(parent)
        self.window_start = window_start
        self.window_end = window_end
        self.setMinimumHeight(HEADER_HEIGHT)
        self.setMaximumHeight(HEADER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(600, HEADER_HEIGHT)

    def set_window(self, window_start: datetime, window_end: datetime):
        self.window_start = window_start
        self.window_end = window_end
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()

        painter.fillRect(rect, QColor(240, 240, 240))

        pen = QPen(QColor(180, 180, 180))
        painter.setPen(pen)
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        total_seconds = (self.window_end - self.window_start).total_seconds()
        if total_seconds <= 0:
            return

        painter.setFont(QFont("Sans", 9))

        current = self.window_start.replace(minute=0, second=0, microsecond=0)
        if current < self.window_start:
            current += timedelta(hours=1)

        while current <= self.window_end:
            x = self._time_to_x(current, total_seconds, rect.width())

            painter.setPen(QPen(QColor(160, 160, 160)))
            painter.drawLine(int(x), rect.top(), int(x), rect.bottom())

            painter.setPen(QPen(QColor(0, 0, 0)))
            label = current.strftime("%H:%M")
            painter.drawText(
                int(x) + 2,
                rect.top(),
                60,
                rect.height(),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

            current += timedelta(hours=1)

    def _time_to_x(self, t: datetime, total_seconds: float, width: int) -> float:
        if t <= self.window_start:
            return 0.0
        if t >= self.window_end:
            return float(width)
        dt = (t - self.window_start).total_seconds()
        return (dt / total_seconds) * width


class ProgramRowWidget(QWidget):
    """
    Single channel row showing programs over a 3-hour window.
    - Hover: tooltip + event_hovered signal
    - Left click: event_clicked signal (used to schedule recording when mode is active)
    """
    event_hovered = pyqtSignal(dict)
    event_clicked = pyqtSignal(dict)

    def __init__(self, events, window_start: datetime, window_end: datetime, parent=None):
        super().__init__(parent)
        self.events = events
        self.window_start = window_start
        self.window_end = window_end
        self.setMinimumHeight(ROW_HEIGHT)
        self.setMaximumHeight(ROW_HEIGHT)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.program_boxes = []
        self.last_tooltip_event_id = None

        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:
        return QSize(600, ROW_HEIGHT)

    def set_window(self, window_start: datetime, window_end: datetime):
        self.window_start = window_start
        self.window_end = window_end
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()

        self.program_boxes = []

        painter.fillRect(rect, QColor(250, 250, 250))

        total_seconds = (self.window_end - self.window_start).total_seconds()
        if total_seconds <= 0:
            return

        painter.setPen(QPen(QColor(230, 230, 230)))
        current = self.window_start.replace(minute=0, second=0, microsecond=0)
        if current < self.window_start:
            current += timedelta(hours=1)
        while current <= self.window_end:
            x = self._time_to_x(current, total_seconds, rect.width())
            painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
            current += timedelta(hours=1)

        painter.setFont(QFont("Sans", 9))

        for ev in self.events:
            try:
                start = datetime.fromisoformat(ev["start"])
                end = datetime.fromisoformat(ev["end"])
            except Exception:
                continue

            if end <= self.window_start or start >= self.window_end:
                continue

            ev_start = max(start, self.window_start)
            ev_end = min(end, self.window_end)
            dur_seconds = (ev_end - ev_start).total_seconds()
            if dur_seconds <= 0:
                continue

            x = self._time_to_x(ev_start, total_seconds, rect.width())
            w = (dur_seconds / total_seconds) * rect.width()
            if w < 3:
                w = 3

            bar_rect = QRect(int(x), rect.top() + 2, int(w), rect.height() - 4)

            recorded = ev.get("recorded", False)
            if recorded:
                painter.setPen(QPen(QColor(200, 0, 0), 2))
                painter.setBrush(QColor(255, 200, 200))
            else:
                painter.setPen(QPen(QColor(120, 150, 200)))
                painter.setBrush(QColor(180, 210, 255))

            painter.drawRect(bar_rect)

            self.program_boxes.append({"rect": QRect(bar_rect), "event": ev})

            title = ev.get("title") or ""
            painter.setPen(QPen(QColor(0, 0, 0)))
            text_rect = bar_rect.adjusted(4, 0, -4, 0)
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                title,
            )

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        ev_found = None

        for box in self.program_boxes:
            if box["rect"].contains(pos):
                ev_found = box["event"]
                break

        if ev_found is not None:
            ev_id = ev_found.get("id")
            if ev_id != self.last_tooltip_event_id:
                self.last_tooltip_event_id = ev_id

                title = ev_found.get("title") or ""
                try:
                    start_dt = datetime.fromisoformat(ev_found["start"])
                    end_dt = datetime.fromisoformat(ev_found["end"])
                    heures = f"{start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')}"
                except Exception:
                    heures = ""

                tooltip = title
                if heures:
                    tooltip += f"\n{heures}"

                QToolTip.showText(QCursor.pos(), tooltip, self)
                self.event_hovered.emit(ev_found)
        else:
            if self.last_tooltip_event_id is not None:
                self.last_tooltip_event_id = None
                QToolTip.hideText()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            clicked_event = None

            for box in self.program_boxes:
                if box["rect"].contains(pos):
                    clicked_event = box["event"]
                    break

            if clicked_event is not None:
                self.event_clicked.emit(clicked_event)

        super().mousePressEvent(event)

    def leaveEvent(self, event):
        self.last_tooltip_event_id = None
        QToolTip.hideText()
        super().leaveEvent(event)

    def _time_to_x(self, t: datetime, total_seconds: float, width: int) -> float:
        if t <= self.window_start:
            return 0.0
        if t >= self.window_end:
            return float(width)
        dt = (t - self.window_start).total_seconds()
        return (dt / total_seconds) * width


# --------------------------
# Main window
# --------------------------

class EPGMainWindow(QMainWindow):
    def __init__(self, epg_data: dict, runner: RemoteCommandRunner, parent=None):
        super().__init__(parent)
        self.epg_data = epg_data
        self.runner = runner

        self.setWindowTitle("EPG VDR (epg.data via SSH) - 3-hour view")
        self.resize(1200, 800)

        self.window_duration = timedelta(hours=3)
        now = datetime.now()
        self.window_start = now.replace(minute=0, second=0, microsecond=0)
        self.window_end = self.window_start + self.window_duration

        self.row_widgets: List[ProgramRowWidget] = []
        self.recording_mode = False

        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        top_layout = QVBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)

        record_layout = QHBoxLayout()
        record_layout.setContentsMargins(0, 0, 0, 0)
        record_layout.setSpacing(8)

        self.record_button = QPushButton("Enregistrement")
        self.record_button.setCheckable(True)
        self.record_button.toggled.connect(self.toggle_recording_mode)
        self._update_record_button_style()

        record_layout.addWidget(self.record_button)
        record_layout.addStretch()

        top_layout.addLayout(record_layout)

        header_date_layout = QHBoxLayout()
        header_date_layout.setContentsMargins(0, 0, 0, 0)
        header_date_layout.setSpacing(8)

        self.date_label = QLabel()
        self._update_date_label()
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_date_layout.addStretch()
        header_date_layout.addWidget(self.date_label)
        header_date_layout.addStretch()

        top_layout.addLayout(header_date_layout)

        day_buttons_layout = QHBoxLayout()
        day_buttons_layout.setContentsMargins(0, 0, 0, 0)
        day_buttons_layout.setSpacing(8)

        btn_day_prev = QPushButton("Jour -1")
        btn_day_today = QPushButton("Aujourd'hui")
        btn_day_next = QPushButton("Jour +1")

        btn_day_prev.clicked.connect(self.day_minus_one)
        btn_day_today.clicked.connect(self.day_today)
        btn_day_next.clicked.connect(self.day_plus_one)

        day_buttons_layout.addStretch()
        day_buttons_layout.addWidget(btn_day_prev)
        day_buttons_layout.addWidget(btn_day_today)
        day_buttons_layout.addWidget(btn_day_next)
        day_buttons_layout.addStretch()

        top_layout.addLayout(day_buttons_layout)

        hour_buttons_layout = QHBoxLayout()
        hour_buttons_layout.setContentsMargins(0, 0, 0, 0)
        hour_buttons_layout.setSpacing(8)

        btn_prev = QPushButton("⟵ -3 h")
        btn_now = QPushButton("Maintenant")
        btn_next = QPushButton("+3 h ⟶")

        btn_prev.clicked.connect(self.shift_minus_3h)
        btn_now.clicked.connect(self.center_on_now)
        btn_next.clicked.connect(self.shift_plus_3h)

        hour_buttons_layout.addStretch()
        hour_buttons_layout.addWidget(btn_prev)
        hour_buttons_layout.addWidget(btn_now)
        hour_buttons_layout.addWidget(btn_next)
        hour_buttons_layout.addStretch()

        top_layout.addLayout(hour_buttons_layout)

        main_layout.addLayout(top_layout)

        header_time_layout = QHBoxLayout()
        header_time_layout.setContentsMargins(0, 0, 0, 0)
        header_time_layout.setSpacing(4)

        spacer = QLabel("Chaîne")
        spacer.setFixedWidth(CHANNEL_COLUMN_WIDTH)
        spacer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spacer.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        header_time_layout.addWidget(spacer)

        self.time_header = TimeHeaderWidget(self.window_start, self.window_end)
        header_time_layout.addWidget(self.time_header)

        header_container = QWidget()
        header_container.setLayout(header_time_layout)
        main_layout.addWidget(header_container)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        channels_widget = QWidget()
        grid = QGridLayout(channels_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(2)

        channels = self.epg_data.get("channels", [])

        for row_index, ch in enumerate(sorted(channels, key=lambda c: (c.get("number", 9999), c.get("name", "").lower()))):
            ch_num = ch.get("number")
            ch_name = ch.get("name", f"Ch {ch_num}")
            events = ch.get("events", [])

            label_num = "?" if ch_num == 9999 else str(ch_num)
            label = QLabel(f"{label_num:>3}  {ch_name}")
            label.setFixedWidth(CHANNEL_COLUMN_WIDTH)
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            grid.addWidget(label, row_index, 0)

            row_widget = ProgramRowWidget(events, self.window_start, self.window_end)
            row_widget.event_hovered.connect(self.show_event_details)
            row_widget.event_clicked.connect(self.handle_event_clicked)
            grid.addWidget(row_widget, row_index, 1)
            self.row_widgets.append(row_widget)

        scroll_area.setWidget(channels_widget)
        main_layout.addWidget(scroll_area)

        details_label = QLabel("<b>Détails de l'émission</b>")
        main_layout.addWidget(details_label)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMinimumHeight(120)
        self.details_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        main_layout.addWidget(self.details_text)

        self.setCentralWidget(central)

    def toggle_recording_mode(self, checked: bool):
        self.recording_mode = checked
        self._update_record_button_style()

    def _update_record_button_style(self):
        if self.recording_mode:
            self.record_button.setText("Enregistrement (sélectionner une émission)")
            self.record_button.setStyleSheet("background-color: #ffaaaa; font-weight: bold;")
        else:
            self.record_button.setText("Enregistrement")
            self.record_button.setStyleSheet("")

    def show_event_details(self, ev: dict):
        title = ev.get("title") or ""
        desc = ev.get("description") or ""
        try:
            start_dt = datetime.fromisoformat(ev["start"])
            end_dt = datetime.fromisoformat(ev["end"])
            heures = f"{start_dt.strftime('%Y-%m-%d %H:%M')} – {end_dt.strftime('%H:%M')}"
        except Exception:
            heures = ""

        parts = []
        if title:
            parts.append(title)
        if heures:
            parts.append(heures)
        if desc:
            parts.append("")
            parts.append(desc)

        self.details_text.setPlainText("\n".join(parts))

    def handle_event_clicked(self, ev: dict):
        if not self.recording_mode:
            self.show_event_details(ev)
            return

        title = ev.get("title") or ""
        channel_name = ev.get("channel_name") or ""
        vdr_channel_id = ev.get("vdr_channel_id") or "?"

        try:
            start_dt = datetime.fromisoformat(ev["start"])
            end_dt = datetime.fromisoformat(ev["end"])
            heures_str = f"{start_dt.strftime('%Y-%m-%d %H:%M')} – {end_dt.strftime('%H:%M')}"
        except Exception:
            heures_str = "Unknown time"

        text = (
            "Voulez-vous programmer l'enregistrement de cette émission ?\n\n"
            f"Titre   : {title}\n"
            f"Chaîne  : {channel_name} (VDR ID {vdr_channel_id})\n"
            f"Horaires: {heures_str}"
        )

        reply = QMessageBox.question(
            self,
            "Confirmer l'enregistrement",
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.schedule_recording(ev)

    def schedule_recording(self, ev: dict):
        try:
            start_dt = datetime.fromisoformat(ev["start"])
            end_dt = datetime.fromisoformat(ev["end"])
        except Exception as e:
            QMessageBox.critical(self, "Erreur EPG", f"Dates invalides pour cet évènement:\n{e}")
            return

        vdr_channel_id = ev.get("vdr_channel_id")
        if not vdr_channel_id:
            QMessageBox.critical(self, "Erreur VDR", "ChannelID VDR inconnu pour cet évènement.")
            return

        margin_before = 5
        margin_after = 10

        start_dt_adj = start_dt - timedelta(minutes=margin_before)
        end_dt_adj = end_dt + timedelta(minutes=margin_after)

        day_str = start_dt_adj.strftime("%Y-%m-%d")
        start_str = start_dt_adj.strftime("%H%M")
        stop_str = end_dt_adj.strftime("%H%M")

        flags = 1
        priority = 50
        lifetime = 99

        title = ev.get("title") or "Enregistrement"

        safe_title = title
        safe_title = safe_title.replace('"', "'")
        safe_title = safe_title.replace("'", "'")
        safe_title = safe_title.replace(":", " -")
        safe_title = safe_title.replace("\n", " ").strip()

        settings = f"{flags}:{vdr_channel_id}:{day_str}:{start_str}:{stop_str}:{priority}:{lifetime}:{safe_title}"

        try:
            result = self.runner.run("svdrpsend", "NEWT", settings)
        except Exception as e:
            QMessageBox.critical(self, "Erreur SSH", f"Impossible d'envoyer la commande à VDR :\n{e}")
            return

        if result.returncode == 0:
            ev["recorded"] = True
            self._refresh_rows()

            QMessageBox.information(
                self,
                "Enregistrement programmé",
                f"Timer créé pour :\n{title}\n\n"
                f"Chaîne VDR : {vdr_channel_id}\n"
                f"Jour       : {day_str}\n"
                f"Heures    : {start_str}–{stop_str}\n\n"
                f"Réponse VDR :\n{result.stdout}",
            )
        else:
            QMessageBox.critical(
                self,
                "Erreur VDR",
                f"Commande NEWT échouée.\n\n"
                f"NEWT {settings}\n\n"
                f"stdout :\n{result.stdout}\n\n"
                f"stderr :\n{result.stderr}",
            )

    def _refresh_rows(self):
        for row in self.row_widgets:
            row.update()

    @staticmethod
    def _weekday_fr(d: date) -> str:
        jours = [
            "lundi", "mardi", "mercredi",
            "jeudi", "vendredi", "samedi", "dimanche"
        ]
        return jours[d.weekday()]

    def _update_date_label(self):
        today = datetime.now().date()
        d = self.window_start.date()
        delta_days = (d - today).days

        if delta_days == 0:
            rel = "Aujourd'hui"
        elif delta_days == 1:
            rel = "Demain"
        elif delta_days == 2:
            rel = "Après-demain"
        elif delta_days > 2:
            rel = f"J+{delta_days}"
        elif delta_days == -1:
            rel = "J-1"
        else:
            rel = f"J{delta_days}"

        weekday = self._weekday_fr(d)
        txt_plain = (
            f"{rel} ({weekday}) "
            f"{self.window_start.strftime('%H:%M')} → {self.window_end.strftime('%H:%M')}"
        )
        txt_html = f'<span style="color:red; font-weight:bold;">{txt_plain}</span>'
        self.date_label.setText(txt_html)

    def _apply_window_change(self):
        self.time_header.set_window(self.window_start, self.window_end)
        for row in self.row_widgets:
            row.set_window(self.window_start, self.window_end)
        self._update_date_label()

    def shift_minus_3h(self):
        self.window_start -= self.window_duration
        self.window_end = self.window_start + self.window_duration
        self._apply_window_change()

    def shift_plus_3h(self):
        self.window_start += self.window_duration
        self.window_end = self.window_start + self.window_duration
        self._apply_window_change()

    def center_on_now(self):
        now = datetime.now()
        self.window_start = now.replace(minute=0, second=0, microsecond=0)
        self.window_end = self.window_start + self.window_duration
        self._apply_window_change()

    def day_minus_one(self):
        self.window_start -= timedelta(days=1)
        self.window_end = self.window_start + self.window_duration
        self._apply_window_change()

    def day_plus_one(self):
        self.window_start += timedelta(days=1)
        self.window_end = self.window_start + self.window_duration
        self._apply_window_change()

    def day_today(self):
        today = datetime.now().date()
        self.window_start = datetime(
            year=today.year, month=today.month, day=today.day, hour=0, minute=0
        )
        self.window_end = self.window_start + self.window_duration
        self._apply_window_change()


# --------------------------
# Entry point
# --------------------------

def main():
    app = QApplication(sys.argv)

    runner = RemoteCommandRunner(base_cmd=SSH_BASE_CMD)
    loader = RemoteEpgDataLoader(runner=runner, remote_path=REMOTE_EPG_DATA_PATH)

    try:
        epg_data = loader.load()
    except Exception as e:
        print(f"EPG load error: {e}", file=sys.stderr)
        return

    window = EPGMainWindow(epg_data, runner)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
