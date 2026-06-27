from datetime import datetime, timedelta
from typing import List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QPushButton, QMessageBox, QLabel, QTextEdit, QFrame, QGridLayout,
    QSizePolicy, QToolTip,
)
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QCursor

from config import (
    RECORDING_START_MARGIN, RECORDING_END_MARGIN,
    VDR_TIMER_PRIORITY, VDR_TIMER_LIFETIME, EPG_UNKNOWN_CHANNEL,
    LANGUAGE,
)
from epg_parser import EpgEvent, _mark_recorded_events
from workers import TimerLoaderWorker, vdr_command
from translations import get_translator

t = get_translator(LANGUAGE)

EPG_ROW_HEIGHT = 40
EPG_HEADER_HEIGHT = 30
EPG_CHANNEL_COL_WIDTH = 140


class TimeHeaderWidget(QWidget):
    def __init__(self, window_start: datetime, window_end: datetime, parent=None):
        super().__init__(parent)
        self.window_start = window_start
        self.window_end = window_end
        self.setFixedHeight(EPG_HEADER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_window(self, ws: datetime, we: datetime):
        self.window_start, self.window_end = ws, we
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        rect = self.rect()
        painter.fillRect(rect, QColor(240, 240, 240))
        painter.setPen(QPen(QColor(180, 180, 180)))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        total = (self.window_end - self.window_start).total_seconds()
        if total <= 0:
            return

        painter.setFont(QFont("Sans", 9))
        cur = self.window_start.replace(minute=0, second=0, microsecond=0)
        if cur < self.window_start:
            cur += timedelta(hours=1)

        while cur <= self.window_end:
            x = int((cur - self.window_start).total_seconds() / total * rect.width())
            painter.setPen(QPen(QColor(160, 160, 160)))
            painter.drawLine(x, rect.top(), x, rect.bottom())
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(x + 2, rect.top(), 60, rect.height(),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             cur.strftime("%H:%M"))
            cur += timedelta(hours=1)


class ProgramRowWidget(QWidget):
    event_hovered = pyqtSignal(object)
    event_clicked = pyqtSignal(object)

    def __init__(self, events, window_start: datetime, window_end: datetime, parent=None):
        super().__init__(parent)
        self.events = events
        self.window_start = window_start
        self.window_end = window_end
        self.setFixedHeight(EPG_ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._boxes = []
        self._last_tooltip_id = None

    def set_window(self, ws: datetime, we: datetime):
        self.window_start, self.window_end = ws, we
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        rect = self.rect()
        self._boxes = []
        painter.fillRect(rect, QColor(250, 250, 250))

        total = (self.window_end - self.window_start).total_seconds()
        if total <= 0:
            return

        painter.setPen(QPen(QColor(230, 230, 230)))
        cur = self.window_start.replace(minute=0, second=0, microsecond=0)
        if cur < self.window_start:
            cur += timedelta(hours=1)
        while cur <= self.window_end:
            x = int((cur - self.window_start).total_seconds() / total * rect.width())
            painter.drawLine(x, rect.top(), x, rect.bottom())
            cur += timedelta(hours=1)

        painter.setFont(QFont("Sans", 9))
        for ev in self.events:
            try:
                start = datetime.fromisoformat(ev.start)
                end = datetime.fromisoformat(ev.end)
            except Exception:
                continue
            if end <= self.window_start or start >= self.window_end:
                continue

            ev_start = max(start, self.window_start)
            ev_end = min(end, self.window_end)
            dur = (ev_end - ev_start).total_seconds()
            if dur <= 0:
                continue

            x = int((ev_start - self.window_start).total_seconds() / total * rect.width())
            w = max(3, int(dur / total * rect.width()))
            bar = QRect(x, rect.top() + 2, w, rect.height() - 4)

            if ev.recorded:
                painter.setPen(QPen(QColor(200, 0, 0), 2))
                painter.setBrush(QColor(255, 200, 200))
            else:
                painter.setPen(QPen(QColor(120, 150, 200)))
                painter.setBrush(QColor(180, 210, 255))

            painter.drawRect(bar)
            self._boxes.append({"rect": QRect(bar), "event": ev})

            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(bar.adjusted(4, 0, -4, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             ev.title or "")

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        found = next((b["event"] for b in self._boxes if b["rect"].contains(pos)), None)
        if found:
            eid = found.id
            if eid != self._last_tooltip_id:
                self._last_tooltip_id = eid
                try:
                    s = datetime.fromisoformat(found.start)
                    e = datetime.fromisoformat(found.end)
                    tip = f"{found.title}\n{s.strftime('%H:%M')}–{e.strftime('%H:%M')}"
                except Exception:
                    tip = found.title
                QToolTip.showText(QCursor.pos(), tip, self)
                self.event_hovered.emit(found)
        else:
            if self._last_tooltip_id is not None:
                self._last_tooltip_id = None
                QToolTip.hideText()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            found = next((b["event"] for b in self._boxes if b["rect"].contains(pos)), None)
            if found:
                self.event_clicked.emit(found)
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        self._last_tooltip_id = None
        QToolTip.hideText()
        super().leaveEvent(event)


class EPGMainWindow(QMainWindow):
    channel_selected = pyqtSignal(int)

    def __init__(self, epg_data: dict, parent=None):
        super().__init__(parent)
        self.epg_data = epg_data
        self.setWindowTitle("Guide des programmes")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(1200, 800)

        self._window_duration = timedelta(hours=3)
        now = datetime.now()
        self.window_start = now.replace(minute=0, second=0, microsecond=0)
        self.window_end = self.window_start + self._window_duration
        self._row_widgets: List[ProgramRowWidget] = []
        self._recording_mode = False
        self._timer_loader: TimerLoaderWorker | None = None

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        rec_layout = QHBoxLayout()
        self._record_btn = QPushButton(t("Recording"))
        self._record_btn.setCheckable(True)
        self._record_btn.toggled.connect(self._toggle_recording)
        self._update_record_style()
        rec_layout.addWidget(self._record_btn)
        rec_layout.addStretch()
        layout.addLayout(rec_layout)

        self._date_label = QLabel()
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._date_label)

        day_layout = QHBoxLayout()
        for label, slot in [(t("Day -1"), self._day_prev), (t("Today"), self._day_today),
                             (t("Day +1"), self._day_next)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            day_layout.addWidget(b)
        layout.addLayout(day_layout)

        hour_layout = QHBoxLayout()
        for label, slot in [(t("← -3 h"), self._shift_back), (t("Now"), self._center_now),
                             ("+3 h ⟶", self._shift_fwd)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            hour_layout.addWidget(b)
        layout.addLayout(hour_layout)

        hdr_layout = QHBoxLayout()
        hdr_layout.setContentsMargins(0, 0, 0, 0)
        spacer = QLabel("Chaîne")
        spacer.setFixedWidth(EPG_CHANNEL_COL_WIDTH)
        spacer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr_layout.addWidget(spacer)
        self._time_header = TimeHeaderWidget(self.window_start, self.window_end)
        hdr_layout.addWidget(self._time_header)
        layout.addLayout(hdr_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(2)

        channels = sorted(
            epg_data.get("channels", []),
            key=lambda c: (c.get("number", EPG_UNKNOWN_CHANNEL), c.get("name", "").lower()),
        )
        for row, ch in enumerate(channels):
            ch_num = ch.get("number")
            ch_name = ch.get("name", f"Ch {ch_num}")
            label_txt = "?" if ch_num == EPG_UNKNOWN_CHANNEL else str(ch_num)

            btn = QPushButton(f"{label_txt:>3}  {ch_name}")
            btn.setFixedWidth(EPG_CHANNEL_COL_WIDTH)
            btn.setStyleSheet("text-align: left; padding-left: 4px;")
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            if ch_num != EPG_UNKNOWN_CHANNEL:
                btn.clicked.connect(self._make_channel_handler(ch_num))
            grid.addWidget(btn, row, 0)

            row_w = ProgramRowWidget(ch.get("events", []), self.window_start, self.window_end)
            row_w.event_hovered.connect(self._show_details)
            row_w.event_clicked.connect(self._on_event_clicked)
            grid.addWidget(row_w, row, 1)
            self._row_widgets.append(row_w)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        layout.addWidget(QLabel("<b>Détails</b>"))
        self._details = QTextEdit()
        self._details.setReadOnly(True)
        self._details.setFixedHeight(120)
        layout.addWidget(self._details)

        self.setCentralWidget(central)
        self._update_date_label()

    def _make_channel_handler(self, ch_num: int):
        def handler():
            self.channel_selected.emit(ch_num)
        return handler

    def _toggle_recording(self, checked: bool):
        self._recording_mode = checked
        self._update_record_style()

    def _update_record_style(self):
        if self._recording_mode:
            self._record_btn.setText(t("Recording (select a program)"))
            self._record_btn.setStyleSheet("background-color: #ffaaaa; font-weight: bold;")
        else:
            self._record_btn.setText(t("Recording"))
            self._record_btn.setStyleSheet("")

    def _show_details(self, ev: EpgEvent):
        try:
            s = datetime.fromisoformat(ev.start)
            e = datetime.fromisoformat(ev.end)
            heures = f"{s.strftime('%Y-%m-%d %H:%M')} – {e.strftime('%H:%M')}"
        except Exception:
            heures = ""
        self._details.setPlainText("\n".join(filter(None, [ev.title, heures, "", ev.description])))

    def _on_event_clicked(self, ev: EpgEvent):
        if ev.recorded and not self._recording_mode:
            self._show_details(ev)
            self._cancel_recording(ev)
            return
        if not self._recording_mode:
            self._show_details(ev)
            return
        self._schedule_recording(ev)

    def _cancel_recording(self, ev: EpgEvent):
        if not ev.timer_id:
            QMessageBox.warning(self, "Timer inconnu",
                                "Impossible de trouver l'ID du timer VDR.\n"
                                "Redémarrez l'application pour rafraîchir.")
            return
        reply = QMessageBox.question(
            self, "Annuler l'enregistrement",
            f"Supprimer le timer pour :\n{ev.title or '?'} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            result = vdr_command("DELT", ev.timer_id)
        except Exception as e:
            QMessageBox.critical(self, "Erreur SSH", str(e))
            return
        if result.returncode == 0:
            QMessageBox.information(self, "Timer supprimé",
                                    f"{t('Recording cancelled')}: {ev.title}")
            self._reload_timers()
        else:
            QMessageBox.critical(self, "Erreur VDR",
                                 f"DELT échoué :\n{result.stdout}\n{result.stderr}")

    def _schedule_recording(self, ev: EpgEvent):
        try:
            start_dt = datetime.fromisoformat(ev.start)
            end_dt = datetime.fromisoformat(ev.end)
        except Exception as e:
            QMessageBox.critical(self, "Erreur EPG", f"Dates invalides :\n{e}")
            return

        if not ev.vdr_channel_id:
            QMessageBox.critical(self, "Erreur VDR", "ChannelID VDR inconnu.")
            return

        title = (ev.title or t("Recording")).replace('"', "'").replace(":", " -").strip()
        s_adj = start_dt - RECORDING_START_MARGIN
        e_adj = end_dt + RECORDING_END_MARGIN
        settings = (f"1:{ev.vdr_channel_id}:{s_adj.strftime('%Y-%m-%d')}:"
                    f"{s_adj.strftime('%H%M')}:{e_adj.strftime('%H%M')}:"
                    f"{VDR_TIMER_PRIORITY}:{VDR_TIMER_LIFETIME}:{title}")

        reply = QMessageBox.question(
            self, "Confirmer l'enregistrement",
            f"Enregistrer :\n{title}\n{start_dt.strftime('%Y-%m-%d %H:%M')} – {end_dt.strftime('%H:%M')}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            result = vdr_command("NEWT", settings)
        except Exception as e:
            QMessageBox.critical(self, "Erreur SSH", str(e))
            return

        if result.returncode == 0:
            QMessageBox.information(self, t("Recording scheduled"),
                                    f"Timer créé : {title}\n{result.stdout}")
            self._reload_timers()
        else:
            QMessageBox.critical(self, "Erreur VDR",
                                 f"NEWT échoué :\n{result.stdout}\n{result.stderr}")

    def _reload_timers(self):
        for channel in self.epg_data.get("channels", []):
            for ev in channel.get("events", []):
                ev.recorded = False
                ev.timer_id = None
        self._timer_loader = TimerLoaderWorker()
        self._timer_loader.finished.connect(self._on_timers_reloaded)
        self._timer_loader.start()

    def _on_timers_reloaded(self, timers: list):
        _mark_recorded_events(self.epg_data, timers)
        for row in self._row_widgets:
            row.update()

    def _apply_window(self):
        self.window_end = self.window_start + self._window_duration
        self._time_header.set_window(self.window_start, self.window_end)
        for row in self._row_widgets:
            row.set_window(self.window_start, self.window_end)
        self._update_date_label()

    def _shift_back(self):
        self.window_start -= self._window_duration
        self._apply_window()

    def _shift_fwd(self):
        self.window_start += self._window_duration
        self._apply_window()

    def _center_now(self):
        self.window_start = datetime.now().replace(minute=0, second=0, microsecond=0)
        self._apply_window()

    def _day_prev(self):
        self.window_start -= timedelta(days=1)
        self._apply_window()

    def _day_next(self):
        self.window_start += timedelta(days=1)
        self._apply_window()

    def _day_today(self):
        t = datetime.now().date()
        self.window_start = datetime(t.year, t.month, t.day)
        self._apply_window()

    def _update_date_label(self):
        today = datetime.now().date()
        d = self.window_start.date()
        delta = (d - today).days
        rel = {0: t("Today"), 1: t("Tomorrow"), 2: t("Day after tomorrow"), -1: t("Yesterday")}.get(
            delta, f"J+{delta}" if delta > 0 else f"J{delta}"
        )
        jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        txt = (f"{rel} ({jours[d.weekday()]}) "
               f"{self.window_start.strftime('%H:%M')} → {self.window_end.strftime('%H:%M')}")
        self._date_label.setText(f'<span style="color:red;font-weight:bold;">{txt}</span>')
