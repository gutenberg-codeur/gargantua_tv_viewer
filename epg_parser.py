import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

from config import RECORDING_START_MARGIN, RECORDING_END_MARGIN, EPG_UNKNOWN_CHANNEL


@dataclass
class Timer:
    timer_id: str
    channel_id: str
    start_dt: datetime
    end_dt: datetime


@dataclass
class EpgEvent:
    id: str
    title: str
    description: str
    start: str
    end: str
    channel_number: int
    channel_name: str
    vdr_channel_id: str
    recorded: bool = False
    timer_id: str | None = None


# Official French DVB-T channel numbering (effective June 6, 2025)
CHANNEL_ORDER = {
    "TF1": 1, "France 2": 2, "France 3": 3, "France 4": 4,
    "France 5": 5, "M6": 6, "Arte": 7, "LCP": 8, "W9": 9,
    "TMC": 10, "TFX": 11, "Gulli": 12, "BFM TV": 13, "CNews": 14,
    "LCI": 15, "Franceinfo": 16, "CStar": 17, "T18": 18, "NOVO19": 19,
    "TF1 Séries Films": 20, "L'Équipe": 21, "6ter": 22,
    "RMC Story": 23, "RMC Découverte": 24, "Chérie 25": 25,
    "Paris Première": 26,
}

_EPG_REPLACEMENTS = {
    "tf1 hd": "tf1", "france2": "france 2", "france 2 hd": "france 2",
    "france3": "france 3", "france 3 hd": "france 3",
    "france4": "france 4", "france 4 hd": "france 4",
    "france5": "france 5", "france 5 hd": "france 5",
    "arte hd": "arte", "w9 hd": "w9",
    "tmc hd": "tmc", "tfx hd": "tfx",
    "gulli hd": "gulli",
    "lcp hd": "lcp", "lcp - assemblée nationale": "lcp",
    "lcp - assemblee nationale": "lcp", "lcp public sénat": "lcp",
    "bfmtv": "bfm tv", "bfm tv hd": "bfm tv",
    "cnews hd": "cnews",
    "lci hd": "lci",
    "france info": "franceinfo", "france info hd": "franceinfo",
    "franceinfo hd": "franceinfo",
    "cstar hd": "cstar",
    "tf1 series films": "tf1 séries films",
    "tf1 séries films hd": "tf1 séries films",
    "l'equipe": "l'équipe", "l equipe": "l'équipe",
    "l'équipe hd": "l'équipe", "6ter hd": "6ter",
    "rmc story hd": "rmc story",
    "rmc decouverte": "rmc découverte",
    "rmc découverte hd": "rmc découverte",
    "cherie 25": "chérie 25", "cherie 25 hd": "chérie 25", "chérie 25 hd": "chérie 25",
    "paris premiere": "paris première", "paris première hd": "paris première",
    "paris 1ere": "paris première",
    "novo 19": "novo19",
    # kept for backward compatibility (channels removed from DVB-T in Feb. 2025)
    "canal +": "canal+", "canal+ hd": "canal+",
    "c8 hd": "c8",
    "nrj12": "nrj 12", "nrj 12 hd": "nrj 12",
}

CHANNEL_ORDER_NORMALIZED = {
    _EPG_REPLACEMENTS.get(k.lower(), k.lower()): v
    for k, v in CHANNEL_ORDER.items()
}


def normalize_channel_name(name: str) -> str:
    s = " ".join(name.strip().lower().split())
    return _EPG_REPLACEMENTS.get(s, s)


def _build_channel_num_to_id(lstc_raw: str) -> dict:
    """Build {channel_number: vdr_channel_id} from SVDRP LSTC output.
    LSTC fields: name:freq:params:source:symbolrate:vpid:apid:tpid:caid:sid:nid:tid:rid
    Channel ID format: {source}-{nid}-{tid}-{sid}
    """
    mapping = {}
    for line in lstc_raw.splitlines():
        m = re.match(r"250[-\s](\d+)\s+(.*)", line)
        if not m:
            continue
        fields = m.group(2).split(":")
        if len(fields) < 13:
            continue
        try:
            source = fields[3]
            sid = fields[9]
            nid = fields[10]
            tid = fields[11]
            mapping[int(m.group(1))] = f"{source}-{nid}-{tid}-{sid}"
        except (IndexError, ValueError):
            continue
    return mapping


def _parse_timers(lstt_raw: str, lstc_raw: str) -> list[Timer]:
    """Parse SVDRP LSTT output into Timer objects with full VDR channel IDs."""
    ch_map = _build_channel_num_to_id(lstc_raw)
    timers = []
    for line in lstt_raw.splitlines():
        m = re.match(r"250[-\s](\d+)\s+(.*)", line)
        if not m:
            continue
        timer_id = m.group(1)
        parts = m.group(2).split(":")
        if len(parts) < 8:
            continue
        try:
            flags = int(parts[0])
            if not (flags & 1):
                continue
            channel_id = ch_map.get(int(parts[1]), "")
            if not channel_id:
                continue
            day_str = parts[2]
            start_str = parts[3].zfill(4)
            end_str = parts[4].zfill(4)
            if not re.match(r"\d{4}-\d{2}-\d{2}", day_str):
                continue
            rec_date = datetime.strptime(day_str, "%Y-%m-%d").date()
            start_h, start_m = int(start_str[:2]), int(start_str[2:])
            end_h, end_m = int(end_str[:2]), int(end_str[2:])
            start_dt = datetime(rec_date.year, rec_date.month, rec_date.day, start_h, start_m)
            end_dt = datetime(rec_date.year, rec_date.month, rec_date.day, end_h, end_m)
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            timers.append(Timer(timer_id=timer_id, channel_id=channel_id,
                                start_dt=start_dt, end_dt=end_dt))
        except (ValueError, IndexError):
            continue
    return timers


def _mark_recorded_events(epg_data: dict, timers: list[Timer]):
    """Mark EPG events that overlap with a VDR timer as recorded."""
    for channel in epg_data.get("channels", []):
        ch_id = channel.get("vdr_channel_id", "")
        ch_timers = [t for t in timers if t.channel_id == ch_id]
        if not ch_timers:
            continue
        for ev in channel.get("events", []):
            try:
                ev_start = datetime.fromisoformat(ev.start)
                ev_end = datetime.fromisoformat(ev.end)
            except Exception:
                continue
            for t in ch_timers:
                t_start = t.start_dt + RECORDING_START_MARGIN
                t_end = t.end_dt - RECORDING_END_MARGIN
                if ev_start < t_end and ev_end > t_start:
                    ev.recorded = True
                    ev.timer_id = t.timer_id
                    break


def _parse_epg(raw: str) -> dict:
    channels = []
    current_channel = None
    current_event = None
    current_desc_lines: List[str] = []

    for line in raw.splitlines():
        if not line:
            continue
        prefix = line[0]

        if prefix == "C" and line.startswith("C "):
            if current_channel is not None and current_event is not None:
                _finalize_event(current_channel, current_event, current_desc_lines)
                current_event = None
                current_desc_lines = []

            parts = line.split()
            vdr_id = parts[1] if len(parts) >= 2 else "1"
            name = " ".join(parts[2:]).strip() if len(parts) >= 3 else "Unknown"
            norm = normalize_channel_name(name)
            current_channel = {
                "number": CHANNEL_ORDER_NORMALIZED.get(norm, EPG_UNKNOWN_CHANNEL),
                "name": name,
                "vdr_channel_id": vdr_id,
                "events": [],
            }
            channels.append(current_channel)
            continue

        if current_channel is None:
            continue

        if prefix == "E" and line.startswith("E "):
            if current_event is not None:
                _finalize_event(current_channel, current_event, current_desc_lines)
            parts = line.split()
            if len(parts) < 4:
                current_event = None
                current_desc_lines = []
                continue
            try:
                start_dt = datetime.fromtimestamp(int(parts[2]))
                end_dt = start_dt + timedelta(seconds=int(parts[3]))
            except ValueError:
                current_event = None
                current_desc_lines = []
                continue
            current_event = {
                "id": parts[1], "title": "", "short_text": "",
                "start_dt": start_dt, "end_dt": end_dt,
            }
            current_desc_lines = []
            continue

        if current_event is None:
            continue

        if prefix == "T" and line.startswith("T "):
            current_event["title"] = line[2:].strip()
        elif prefix == "S" and line.startswith("S "):
            current_event["short_text"] = line[2:].strip()
        elif prefix == "D":
            current_desc_lines.append(line[1:].lstrip())
        elif prefix == "e":
            _finalize_event(current_channel, current_event, current_desc_lines)
            current_event = None
            current_desc_lines = []

    if current_channel and current_event:
        _finalize_event(current_channel, current_event, current_desc_lines)

    return {"channels": channels}


def _finalize_event(channel: dict, event: dict, desc_lines: List[str]):
    short = event.get("short_text", "")
    desc = "\n".join(desc_lines).strip()
    description = (short + "\n\n" + desc).strip() if short and desc else (short or desc)
    channel["events"].append(EpgEvent(
        id=event["id"],
        title=event.get("title", ""),
        description=description,
        start=event["start_dt"].isoformat(),
        end=event["end_dt"].isoformat(),
        channel_number=channel["number"],
        channel_name=channel["name"],
        vdr_channel_id=channel["vdr_channel_id"],
    ))
