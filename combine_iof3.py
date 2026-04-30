#!/usr/bin/env python3
"""
Combine IOF 3 XML ResultList files into a series standings HTML report.

Results are grouped by class and sorted by combined time.  Competitors who
lack a valid (OK) time in every event they entered are listed at the bottom
with "no result"

Usage:
    python combine_iof3.py file1.xml file2.xml ...
    python combine_iof3.py --dir samples/
    python combine_iof3.py --output report.html --dir samples/
"""

import argparse
import glob
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

NS = "http://www.orienteering.org/datastandard/3.0"
OK_STATUS = "OK"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ns(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def fmt_time(seconds: Optional[int]) -> str:
    if seconds is None:
        return "–"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fmt_dist(metres: Optional[int]) -> str:
    if metres is None:
        return ""
    if metres >= 1000:
        return f"{metres / 1000:.1f} km"
    return f"{metres} m"


def _text(el, tag: str) -> Optional[str]:
    if el is None:
        return None
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else None


def _int_text(el, tag: str) -> Optional[int]:
    v = _text(el, tag)
    try:
        return int(v) if v else None
    except ValueError:
        return None


def _esc(s: Optional[str]) -> str:
    if not s:
        return ""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def _fmt_date(d: Optional[str]) -> str:
    if not d:
        return ""
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return d


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """One IOF 3 ResultList file = one event."""
    name: str
    date: Optional[str]
    source_file: str

    @property
    def label(self) -> str:
        date_str = _fmt_date(self.date)
        return f"{self.name}" + (f" ({date_str})" if date_str else "")


@dataclass
class PersonResult:
    """One competitor's result within a single event/class."""
    status: str
    time: Optional[int]          # seconds, None if no valid time
    position: Optional[int]
    time_behind: Optional[int]
    organisation: Optional[str]


@dataclass
class Competitor:
    iof_id: Optional[str]
    given: str
    family: str
    organisation: Optional[str]  # most recently seen club

    @property
    def full_name(self) -> str:
        return f"{self.given} {self.family}".strip()

    def match_key(self) -> str:
        """Key used to deduplicate competitors across events."""
        if self.iof_id:
            return f"id:{self.iof_id}"
        return f"name:{self.given.lower()}|{self.family.lower()}"


STATUS_LABELS = {
    "OK": "OK",
    "MissingPunch": "MP",
    "Disqualified": "DSQ",
    "DidNotFinish": "DNF",
    "DidNotStart": "DNS",
    "OverTime": "OT",
    "SportingWithdrawal": "SW",
    "NotCompeting": "NC",
    "Cancelled": "Cancelled",
    "InActive": "–",
}

STATUS_CSS = {
    "OK": "st-ok",
    "MissingPunch": "st-warn",
    "Disqualified": "st-bad",
    "DidNotFinish": "st-bad",
    "DidNotStart": "st-neutral",
    "OverTime": "st-warn",
    "SportingWithdrawal": "st-neutral",
    "NotCompeting": "st-neutral",
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_file(xml_path: str) -> tuple[Event, dict[str, list[tuple[Competitor, PersonResult]]]]:
    """
    Parse one IOF 3 ResultList XML.

    Returns:
        (Event, { class_name: [(Competitor, PersonResult), ...] })
    """
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        print(f"WARNING: Cannot parse {xml_path}: {e}", file=sys.stderr)
        return None, {}

    root = tree.getroot()

    if root.tag not in (ns("ResultList"), "ResultList"):
        print(f"WARNING: {xml_path} is not an IOF 3 ResultList (root={root.tag})", file=sys.stderr)
        return None, {}

    event_el = root.find(ns("Event"))
    event_name = _text(event_el, ns("Name")) if event_el is not None else Path(xml_path).stem
    event_date = None
    if event_el is not None:
        st = event_el.find(ns("StartTime"))
        if st is not None:
            event_date = _text(st, ns("Date"))

    event = Event(name=event_name, date=event_date, source_file=os.path.basename(xml_path))

    classes: dict[str, list[tuple[Competitor, PersonResult]]] = {}

    for class_result in root.findall(ns("ClassResult")):
        class_el = class_result.find(ns("Class"))
        class_name = _text(class_el, ns("Name")) if class_el is not None else "Unknown"

        entries: list[tuple[Competitor, PersonResult]] = []

        for pr_el in class_result.findall(ns("PersonResult")):
            person_el = pr_el.find(ns("Person"))
            if person_el is None:
                continue

            iof_id = _text(person_el, ns("Id"))
            name_el = person_el.find(ns("Name"))
            given = _text(name_el, ns("Given")) if name_el is not None else ""
            family = _text(name_el, ns("Family")) if name_el is not None else ""

            org_el = pr_el.find(ns("Organisation"))
            org = _text(org_el, ns("ShortName")) or _text(org_el, ns("Name")) if org_el is not None else None

            result_el = pr_el.find(ns("Result"))
            if result_el is None:
                continue

            status = _text(result_el, ns("Status")) or "Unknown"
            time_val = _int_text(result_el, ns("Time")) if status == OK_STATUS else None
            position = _int_text(result_el, ns("Position"))
            time_behind = _int_text(result_el, ns("TimeBehind"))

            competitor = Competitor(iof_id=iof_id, given=given or "", family=family or "", organisation=org)
            result = PersonResult(status=status, time=time_val, position=position,
                                  time_behind=time_behind, organisation=org)
            entries.append((competitor, result))

        if entries:
            classes[class_name] = entries

    return event, classes


# ---------------------------------------------------------------------------
# Series combining
# ---------------------------------------------------------------------------

@dataclass
class ClassRow:
    """One row in the final standings table for a class."""
    competitor: Competitor
    results: list[Optional[PersonResult]]   # one per event, None = not entered
    total_time: Optional[int]               # None → no result
    position: Optional[int]                 # None → no result


def build_standings(
    events: list[Event],
    class_data: dict[str, list[dict[str, tuple[Competitor, PersonResult]]]],
) -> dict[str, list[ClassRow]]:
    """
    For each class produce a sorted list of ClassRow.

    Ranking logic:
    - A competitor earns a total only if ALL their entered events have status OK.
    - Competitors with a valid total are ranked 1, 2, 3… by ascending total time.
    - Everyone else goes to the bottom of their class as no result
    """
    standings: dict[str, list[ClassRow]] = {}

    for class_name, per_event_maps in class_data.items():
        # Gather every unique competitor key that appears in any event
        all_keys: dict[str, Competitor] = {}
        for event_map in per_event_maps:
            for key, (comp, _) in event_map.items():
                if key not in all_keys:
                    all_keys[key] = comp
                elif comp.organisation:
                    all_keys[key].organisation = comp.organisation  # keep latest club

        rows: list[ClassRow] = []
        for key, comp in all_keys.items():
            results: list[Optional[PersonResult]] = []
            any_non_ok = False
            total = 0

            for event_map in per_event_maps:
                pr = event_map.get(key)
                if pr is None:
                    results.append(None)
                    any_non_ok = True
                else:
                    _, person_result = pr
                    results.append(person_result)
                    if person_result.status != OK_STATUS or person_result.time is None:
                        any_non_ok = True
                    else:
                        total += person_result.time

            total_time = None if any_non_ok else total
            rows.append(ClassRow(competitor=comp, results=results, total_time=total_time, position=None))

        # Sort: valid totals first (ascending), then no result (preserve original order)
        ranked = sorted([r for r in rows if r.total_time is not None], key=lambda r: r.total_time)
        unranked = [r for r in rows if r.total_time is None]

        pos = 1
        for i, row in enumerate(ranked):
            if i > 0 and ranked[i].total_time != ranked[i - 1].total_time:
                pos = i + 1
            row.position = pos

        standings[class_name] = ranked + unranked

    return standings


def collect_class_data(
    events: list[Event],
    raw: list[dict[str, list[tuple[Competitor, PersonResult]]]],
) -> dict[str, list[dict[str, tuple[Competitor, PersonResult]]]]:
    """
    Organise raw per-file class data into:
      { class_name: [ {competitor_key: (Competitor, PersonResult)}, ... ] }
    The outer list has one dict per event (in order).
    """
    # Find all class names
    all_classes: set[str] = set()
    for file_classes in raw:
        all_classes.update(file_classes.keys())

    class_data: dict[str, list[dict[str, tuple[Competitor, PersonResult]]]] = {
        cn: [] for cn in all_classes
    }

    for file_classes in raw:
        for cn in all_classes:
            entries = file_classes.get(cn, [])
            event_map: dict[str, tuple[Competitor, PersonResult]] = {}
            for comp, result in entries:
                key = comp.match_key()
                event_map[key] = (comp, result)
            class_data[cn].append(event_map)

    return class_data


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def generate_html(events: list[Event], standings: dict[str, list[ClassRow]], top3: bool = False) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build event header labels
    event_labels = [_esc(e.label) for e in events]

    class_sections = ""
    for class_name in sorted(standings.keys()):
        rows = standings[class_name]
        class_sections += _render_class(class_name, events, event_labels, rows, top3=top3)

    event_list_items = "".join(f"<li>{label}</li>" for label in event_labels)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Combined IOF Series Results</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f4f6fb; color: #222; margin: 0; padding: 0; font-size: 14px; }}
    header {{ background: #1a3a5c; color: #fff; padding: 1.2rem 2rem; }}
    header h1 {{ margin: 0; font-size: 1.5rem; }}
    header ul {{ margin: 0.6rem 0 0; padding-left: 1.2rem; opacity: 0.85;
                 font-size: 0.85rem; display: flex; gap: 1.5rem; list-style: none;
                 padding: 0; flex-wrap: wrap; }}
    header ul li::before {{ content: "▸ "; opacity: 0.6; }}
    main {{ max-width: 1300px; margin: 1.5rem auto; padding: 0 1rem; }}
    .class-section {{ background: #fff; border-radius: 8px;
                      box-shadow: 0 1px 4px rgba(0,0,0,0.1);
                      margin-bottom: 1.4rem; overflow: hidden; }}
    .class-header {{ background: #e8edf3; padding: 0.7rem 1rem;
                     border-bottom: 2px solid #c5d0df;
                     font-weight: 700; font-size: 1rem; color: #1a3a5c; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ padding: 0.45rem 0.7rem; text-align: left; background: #f0f4fa;
          border-bottom: 1px solid #d4dce8; color: #555; font-weight: 600;
          white-space: nowrap; font-size: 0.8rem; }}
    td {{ padding: 0.42rem 0.7rem; border-bottom: 1px solid #eee;
          vertical-align: middle; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #f8faff; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
    .evt-col {{ white-space: normal; min-width: 4.5rem; }}
    .pos {{ text-align: center; font-weight: 700; color: #555; width: 2.2rem; }}
    .pos-gold   {{ color: #b8860b; }}
    .pos-silver {{ color: #708090; }}
    .pos-bronze {{ color: #8b4513; }}
    .name {{ font-weight: 500; }}
    .club {{ color: #666; font-size: 0.82rem; }}
    .total {{ font-weight: 700; }}
    .na {{ color: #aaa; font-style: italic; }}
    .separator td {{ border-top: 2px dashed #ddd; background: #fafafa; }}
    .st {{ display: inline-block; padding: 0.1rem 0.4rem; border-radius: 10px;
           font-size: 0.75rem; font-weight: 600; }}
    .st-ok      {{ background: #d4edda; color: #155724; }}
    .st-warn    {{ background: #fff3cd; color: #856404; }}
    .st-bad     {{ background: #f8d7da; color: #721c24; }}
    .st-neutral {{ background: #e2e3e5; color: #383d41; }}
    .st-na      {{ color: #bbb; }}
    footer {{ text-align: center; padding: 1.2rem; color: #aaa; font-size: 0.78rem; }}
  </style>
</head>
<body>
<header>
  <h1>Combined IOF Series Results</h1>
  <ul>{event_list_items}</ul>
</header>
<main>
{class_sections}
</main>
<footer>Generated {generated_at} · IOF DataStandard 3.0 · {len(events)} event(s)</footer>
</body>
</html>"""


def _render_class(class_name: str, events: list[Event], event_labels: list[str], rows: list[ClassRow], top3: bool = False) -> str:
    if top3:
        rows = [r for r in rows if r.position is not None and r.position <= 3]
    if not rows:
        return ""

    table_rows = ""
    prev_was_ranked = True

    for row in rows:
        is_na = row.total_time is None

        # Insert a visual separator between ranked and no result rows
        if is_na and prev_was_ranked and any(r.total_time is not None for r in rows):
            table_rows += '<tr class="separator"><td></td><td></td><td></td>'
            table_rows += '<td></td>' * len(events)
            table_rows += '<td></td></tr>\n'
        prev_was_ranked = not is_na

        # Position cell
        if row.position == 1:
            pos_html = f'<td class="pos pos-gold">1</td>'
        elif row.position == 2:
            pos_html = f'<td class="pos pos-silver">2</td>'
        elif row.position == 3:
            pos_html = f'<td class="pos pos-bronze">3</td>'
        elif row.position:
            pos_html = f'<td class="pos">{row.position}</td>'
        else:
            pos_html = '<td class="pos na">–</td>'

        name_html = f'<td class="name">{_esc(row.competitor.full_name)}</td>'
        club_html = f'<td class="club">{_esc(row.competitor.organisation)}</td>'

        event_cells = ""
        for result in row.results:
            if result is None:
                event_cells += '<td class="num"><span class="st st-neutral">DNS</span></td>'
            elif result.status == OK_STATUS and result.time is not None:
                event_cells += f'<td class="num">{fmt_time(result.time)}</td>'
            elif result.status == OK_STATUS:
                # OK status but no time element in the XML
                event_cells += '<td class="num"><span class="st st-neutral">untimed</span></td>'
            else:
                label = STATUS_LABELS.get(result.status, result.status)
                css = STATUS_CSS.get(result.status, "st-neutral")
                event_cells += f'<td class="num"><span class="st {css}">{_esc(label)}</span></td>'

        if is_na:
            total_html = '<td class="num"><span class="st st-neutral">–</span></td>'
        else:
            total_html = f'<td class="num total">{fmt_time(row.total_time)}</td>'

        table_rows += (
            f"<tr>{pos_html}{name_html}{club_html}"
            f"{event_cells}{total_html}</tr>\n"
        )

    event_headers_html = "".join(
        f'<th class="num evt-col">{label}</th>' for label in event_labels
    )

    return f"""  <div class="class-section">
    <div class="class-header">{_esc(class_name)}</div>
    <table>
      <thead>
        <tr>
          <th class="pos">#</th>
          <th>Name</th>
          <th>Club</th>
          {event_headers_html}
          <th class="num">Total</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </div>
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def collect_xml_files(paths: list[str], directory: Optional[str]) -> list[str]:
    files: list[str] = []
    if directory:
        files.extend(glob.glob(os.path.join(directory, "*.xml")))
    for p in paths:
        if os.path.isdir(p):
            files.extend(glob.glob(os.path.join(p, "*.xml")))
        elif os.path.isfile(p):
            files.append(p)
        else:
            expanded = glob.glob(p)
            if expanded:
                files.extend(expanded)
            else:
                print(f"WARNING: {p} not found", file=sys.stderr)
    seen = set()
    unique = []
    for f in files:
        key = os.path.abspath(f)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return sorted(unique)


def main():
    parser = argparse.ArgumentParser(
        description="Combine IOF 3 XML ResultList files into a series standings HTML report."
    )
    parser.add_argument("--dir", metavar="DIR",
                        help="Directory to scan for *.xml files")
    parser.add_argument("--output", "-o", metavar="FILE", default="report.html",
                        help="Output HTML file (default: report.html)")
    parser.add_argument("files", nargs="*", metavar="FILE.xml",
                        help="IOF 3 XML ResultList files")
    parser.add_argument("--top3", action="store_true",
                        help="Only show the top 3 finishers per class (ties included)")
    args = parser.parse_args()

    xml_files = collect_xml_files(args.files, args.dir)
    if not xml_files:
        print("ERROR: No XML files found. Provide files directly or use --dir.", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {len(xml_files)} file(s)...")
    events: list[Event] = []
    raw_class_data: list[dict[str, list[tuple[Competitor, PersonResult]]]] = []

    for path in xml_files:
        event, file_classes = parse_file(path)
        if event is None:
            continue
        events.append(event)
        raw_class_data.append(file_classes)
        total_entries = sum(len(v) for v in file_classes.values())
        print(f"  {os.path.basename(path)}: {len(file_classes)} class(es), {total_entries} entries")

    if not events:
        print("ERROR: No valid IOF 3 ResultList files found.", file=sys.stderr)
        sys.exit(1)

    # Sort events (and paired class data) by date; undated events go last
    paired = sorted(zip(events, raw_class_data), key=lambda p: (p[0].date is None, p[0].date or ""))
    events, raw_class_data = [list(x) for x in zip(*paired)]

    class_data = collect_class_data(events, raw_class_data)
    standings = build_standings(events, class_data)

    total_competitors = sum(len(rows) for rows in standings.values())
    print(f"\nBuilding standings: {len(standings)} class(es), {total_competitors} competitor(s)")

    html = generate_html(events, standings, top3=args.top3)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report written to: {args.output}")


if __name__ == "__main__":
    main()
