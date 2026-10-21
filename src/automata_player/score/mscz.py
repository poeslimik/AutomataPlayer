"""MuseScore .mscz / .mscx 를 공통 Score로 읽는다.

.mscz는 .mscx XML을 담은 zip이다. 음표의 `<pitch>`는 MIDI 번호이고,
`<tempo>`는 4분음표가 1초에 몇 개 나가는지다 (BPM = 값 × 60).
길이는 `<durationType>`과 점음표, 잇단음표로 계산한다.

반복, 도돌이표, 케이던차, 꾸밈음, 아르페지오, 글리산도, 트릴은
연주 순서로 펼친다. 잇단음표는 한 겹만 비율을 적용한다.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from automata_player.i18n import t
from automata_player.model import Note, PartInfo, Pause, Score, ScoreError, TempoMark, TimeStretch, merge_ties
from automata_player.pitch import tpc_alter
from automata_player.score.flow import FlowAnchor, Jump, MeasureFlow, playback_segments

# durationType 한 개의 4분음표 길이. "measure"는 마디 길이라 따로 다룬다.
_QUARTERS = {
    "1024th": Fraction(1, 256),
    "512th": Fraction(1, 128),
    "256th": Fraction(1, 64),
    "128th": Fraction(1, 32),
    "64th": Fraction(1, 16),
    "32nd": Fraction(1, 8),
    "16th": Fraction(1, 4),
    "eighth": Fraction(1, 2),
    "quarter": Fraction(1),
    "half": Fraction(2),
    "whole": Fraction(4),
    "breve": Fraction(8),
    "longa": Fraction(16),
}

_ACCIACCATURA = Fraction(1, 16)
_GRACE_BEFORE = frozenset({"grace", "acciaccatura", "grace4", "grace8", "grace16", "grace32"})
_GRACE_AFTER = frozenset({"grace8after", "grace16after", "grace32after"})
_CADENZA_WORDS = ("cadenza", "케이던차", "カデンツァ", "华彩")


def load_score(path: str | Path) -> Score:
    score_path = Path(path)
    if not score_path.is_file():
        raise ScoreError(t("file_missing", path=score_path))
    suffix = score_path.suffix.lower()
    data = score_path.read_bytes()
    if suffix == ".mscz":
        return parse_mscz(data, title=score_path.stem)
    if suffix == ".mscx":
        return parse_mscx(data, title=score_path.stem)
    raise ScoreError(t("bad_extension"))


def parse_mscz(data: bytes, *, title: str) -> Score:
    from io import BytesIO

    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            candidates = [
                info
                for info in archive.infolist()
                if info.filename.lower().endswith(".mscx") and not info.filename.endswith(",")
            ]
            if not candidates:
                raise ScoreError(t("mscz_missing_inner"))
            chosen = max(candidates, key=lambda info: info.file_size)
            payload = archive.read(chosen)
    except zipfile.BadZipFile as exc:
        raise ScoreError(t("mscz_zip")) from exc
    return parse_mscx(payload, title=title)


def parse_mscx(data: bytes, *, title: str) -> Score:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ScoreError(t("xml_parse", message=exc)) from exc
    for element in root.iter():
        if "}" in element.tag:
            element.tag = element.tag.rsplit("}", 1)[-1]
    score_element = root if root.tag == "Score" else root.find("Score")
    if score_element is None:
        raise ScoreError(t("no_score_element"))
    return _parse_score(score_element, title)


def _parse_score(score_element: ET.Element, fallback_title: str) -> Score:
    division = _division(score_element)
    title = _meta(score_element, "workTitle") or _meta(score_element, "movementTitle") or fallback_title
    warnings: list[str] = []
    notes: list[Note] = []
    tempos: list[TempoMark] = []
    stretches: list[TimeStretch] = []
    pauses: list[Pause] = []
    parts: list[PartInfo] = []
    open_tuplets = False
    staff_measures: list[list[_RawMeasure]] = []

    part_elements = score_element.findall("Part")
    if not part_elements and score_element.findall("Staff"):
        part_elements = [score_element]
    # MuseScore 4.6 이후에는 마디가 Part 안이 아니라 Score 바로 아래 Staff에 있다.
    content_staves = [
        staff for staff in score_element.findall("Staff") if staff.find("Measure") is not None
    ]
    next_content = 0

    for part_index, part_element in enumerate(part_elements):
        meta_staves = part_element.findall("Staff")
        name = (
            _plain_text(part_element, "trackName")
            or _plain_text(part_element, "longName")
            or t("part_fallback", n=part_index + 1)
        )
        if not meta_staves:
            meta_staves = [part_element] if part_element.find("Measure") is not None else []
        parts.append(PartInfo(part_index, name, max(len(meta_staves), 1)))
        for staff_index, meta in enumerate(meta_staves):
            if meta.find("Measure") is not None:
                staff = meta
            elif next_content < len(content_staves):
                staff = content_staves[next_content]
                next_content += 1
            else:
                continue
            parsed, unclosed, percussion = _parse_staff(
                staff,
                division=division,
                part_index=part_index,
                part_name=name,
                staff_index=staff_index,
                percussion=_is_percussion(meta),
            )
            staff_measures.append(parsed)
            open_tuplets = open_tuplets or unclosed
            if percussion:
                _warn_once(warnings, "percussion")

    _place_playback(staff_measures, notes, tempos, stretches, pauses, warnings)
    if open_tuplets:
        warnings.append("tuplet")
    if not tempos:
        tempos.append(TempoMark(Fraction(0), 120.0))
        warnings.append("tempo-default")
    elif tempos[0].position > 0:
        tempos.insert(0, TempoMark(Fraction(0), 120.0))

    tempos.sort(key=lambda mark: mark.position)
    return Score(
        title=title.strip() or fallback_title,
        notes=merge_ties(notes),
        tempos=tuple(tempos),
        parts=tuple(parts),
        warnings=tuple(warnings),
        stretches=tuple(stretches),
        pauses=tuple(pauses),
    )


@dataclass
class _Render:
    """한 성부를 소리로 펼칠 때 같이 넘어가는 값."""

    part_index: int
    part_name: str
    staff_index: int
    glissandi: list[tuple[Fraction, int, Fraction, int, str]] | None
    fifths: int = 0
    bpm: float = 120.0
    accidental_state: dict[int, int] | None = None


@dataclass
class _VoiceChord:
    duration: Fraction
    end: Fraction
    at_barline: bool = False


@dataclass
class _Anchor:
    offset: Fraction
    start_repeat: bool = False
    end_repeat: int = 0
    markers: list[str] = field(default_factory=list)
    jump: Jump | None = None
    opens_next: bool = False


@dataclass
class _RawMeasure:
    length: Fraction
    notes: list[Note] = field(default_factory=list)
    tempos: list[TempoMark] = field(default_factory=list)
    stretches: list[TimeStretch] = field(default_factory=list)
    endings: frozenset[int] | None = None
    cadenza: bool = False
    simile: bool = False
    voltas: list[tuple[frozenset[int], int]] = field(default_factory=list)
    anchors: list[_Anchor] = field(default_factory=list)
    glissandi: list[tuple[Fraction, int, Fraction, int, str]] = field(default_factory=list)
    pause: float = 0.0


def _parse_staff(
    staff: ET.Element,
    *,
    division: int,
    part_index: int,
    part_name: str,
    staff_index: int,
    percussion: bool = False,
) -> tuple[list[_RawMeasure], bool, bool]:
    parsed: list[_RawMeasure] = []
    percussion = percussion or _is_percussion(staff)
    signature = (4, 4)
    tuplet_stacks: dict[int, list[tuple[int, int]]] = {}
    previous_chord: dict[int, _VoiceChord] = {}
    render = _Render(
        part_index=part_index,
        part_name=part_name,
        staff_index=staff_index,
        glissandi=None,
    )

    for measure in staff.findall("Measure"):
        found = _time_signature(measure)
        if found is not None:
            signature = found
        measure_fifths = _key_fifths(measure)
        if measure_fifths is not None:
            render.fifths = measure_fifths
        render.accidental_state = {step: _alter_for_step(step, render.fifths) for step in range(7)}
        nominal = _measure_length(measure, signature)
        notes: list[Note] = []
        tempos: list[TempoMark] = []
        stretches: list[TimeStretch] = []
        anchors: list[_Anchor] = []
        glissandi: list[tuple[Fraction, int, Fraction, int, str]] = []
        render.glissandi = glissandi
        barlines: list[tuple[bool, bool, Fraction, bool, int]] = []
        content = Fraction(0)
        voices = measure.findall("voice")
        containers = voices if voices else [measure]
        for voice_index, voice in enumerate(containers):
            stack = tuplet_stacks.setdefault(voice_index, [])
            cursor = Fraction(0)
            pending: list[tuple[str, ET.Element, Fraction]] = []
            children = list(voice)
            for child_index, child in enumerate(children):
                if voice is measure and child.tag == "voice":
                    continue
                if child.tag == "KeySig":
                    voice_fifths = _key_fifths(child)
                    if voice_fifths is not None:
                        render.fifths = voice_fifths
                        render.accidental_state = {
                            step: _alter_for_step(step, render.fifths) for step in range(7)
                        }
                    continue
                if child.tag == "Tuplet":
                    stack.append(_tuplet_ratio(child))
                    continue
                if child.tag == "endTuplet":
                    if stack:
                        stack.pop()
                    continue
                if child.tag == "Tempo":
                    bpm_value = _tempo_bpm(child)
                    if bpm_value is not None:
                        render.bpm = bpm_value
                        tempos.append(TempoMark(max(Fraction(0), cursor + _location_delta(child)), bpm_value))
                    continue
                if child.tag == "BarLine":
                    start, end = _barline_flags(_child_text(child, "subtype") or _child_text(child, "barStyle") or "")
                    follows = any(item.tag in {"Chord", "Rest"} for item in children[child_index + 1 :])
                    count = (
                        _positive_int(_child_text(child, "repeatCount"))
                        or _positive_int(_child_text(child, "playCount"))
                        or _positive_int(_child_text(measure, "repeatCount"))
                        or 2
                    )
                    barlines.append((start, end, max(Fraction(0), cursor + _location_delta(child)), follows, count))
                    continue
                if child.tag == "Marker":
                    label = _marker_label(child)
                    if label:
                        _anchor_at(anchors, max(Fraction(0), cursor + _location_delta(child))).markers.append(label)
                    continue
                if child.tag == "Jump":
                    _anchor_at(anchors, max(Fraction(0), cursor + _location_delta(child))).jump = _read_jump(child)
                    continue
                if child.tag not in {"Chord", "Rest"}:
                    continue
                kind = _grace_kind(child)
                if kind == "after":
                    _attach_grace_after(
                        notes,
                        child,
                        _duration(child, division, nominal, stack),
                        render,
                    )
                    continue
                if kind is not None:
                    pending.append((kind, child, _duration(child, division, nominal, stack)))
                    continue
                duration = _duration(child, division, nominal, stack)
                if child.tag == "Rest":
                    previous_chord.pop(voice_index, None)
                factor = _fermata_factor(child)
                if factor is not None and factor > 1.0:
                    stretches.append(TimeStretch(cursor, duration, factor))
                stolen = Fraction(0)
                if pending and child.tag == "Chord":
                    earlier = parsed[-1] if parsed else None
                    state = previous_chord.get(voice_index)
                    if pending[0][0] == "acciaccatura":
                        _apply_acciaccatura(
                            pending,
                            cursor,
                            state,
                            notes,
                            earlier.notes if earlier is not None else None,
                            earlier.length if earlier is not None else None,
                            render,
                        )
                    else:
                        grace_notes, stolen = _sound_grace(
                            pending,
                            duration,
                            cursor,
                            render,
                        )
                        notes.extend(grace_notes)
                    pending = []
                sounding = duration - stolen
                if child.tag == "Chord" and not percussion and sounding > 0:
                    notes.extend(
                        _chord_notes(
                            child,
                            start=cursor + stolen,
                            duration=sounding,
                            render=render,
                        )
                    )
                    previous_chord[voice_index] = _VoiceChord(duration, cursor + duration)
                cursor += duration
            if pending:
                loose, span = _loose_grace(pending, cursor, render)
                notes.extend(loose)
                cursor += span
            content = max(content, cursor)
        length = content if content > nominal else nominal
        for start, end, bar_offset, follows, count in barlines:
            position = bar_offset if follows else length
            anchor = _anchor_at(anchors, position)
            if start and end:
                anchor.end_repeat = count
                if follows:
                    anchor.start_repeat = True
                else:
                    anchor.opens_next = True
            elif start:
                anchor.start_repeat = True
            elif end:
                anchor.end_repeat = count
        raw = _RawMeasure(
            length=length,
            notes=notes,
            tempos=tempos,
            stretches=stretches,
            anchors=anchors,
            glissandi=glissandi,
            pause=_section_pause(measure),
        )
        _read_measure_flow(measure, raw)
        if raw.cadenza and raw.length != content:
            for anchor in raw.anchors:
                if anchor.offset == raw.length:
                    anchor.offset = content
            raw.length = content
        parsed.append(raw)
        kept: dict[int, _VoiceChord] = {}
        for voice_index, state in previous_chord.items():
            if state.end == raw.length:
                kept[voice_index] = _VoiceChord(state.duration, state.end, at_barline=True)
        previous_chord = kept

    _resolve_glissandi(parsed)
    for index, raw in enumerate(parsed):
        for anchor in raw.anchors:
            if anchor.opens_next and index + 1 < len(parsed):
                _anchor_at(parsed[index + 1].anchors, Fraction(0)).start_repeat = True
        for endings, span in raw.voltas:
            for follow in range(index, min(len(parsed), index + span)):
                parsed[follow].endings = endings
    for index, raw in enumerate(parsed):
        if not raw.simile or index == 0:
            continue
        previous = parsed[index - 1]
        raw.notes = [replace(note) for note in previous.notes]
        raw.tempos = [replace(mark) for mark in previous.tempos]
        raw.stretches = [replace(item) for item in previous.stretches]
        raw.length = previous.length

    unclosed = any(stack for stack in tuplet_stacks.values())
    return parsed, unclosed, percussion


def _place_playback(
    staff_measures: list[list[_RawMeasure]],
    notes: list[Note],
    tempos: list[TempoMark],
    stretches: list[TimeStretch],
    pauses: list[Pause],
    warnings: list[str],
) -> None:
    if not staff_measures:
        return
    count = max(len(staff) for staff in staff_measures)
    flows: list[MeasureFlow] = []
    for index in range(count):
        length = Fraction(0)
        endings: frozenset[int] | None = None
        anchors: list[_Anchor] = []
        onsets: list[Fraction] = []
        for staff in staff_measures:
            if index >= len(staff):
                continue
            measure = staff[index]
            length = max(length, measure.length)
            if measure.endings is not None:
                endings = measure.endings
            anchors.extend(measure.anchors)
            onsets.extend(note.start for note in measure.notes)
        flows.append(
            MeasureFlow(
                length=length,
                endings=endings,
                anchors=tuple(_flow_anchor(anchor) for anchor in _merged_anchors(anchors)),
                onsets=tuple(sorted(set(onsets))),
            )
        )

    segments, unresolved = playback_segments(flows)
    if unresolved:
        _warn_once(warnings, "flow")
    origins: list[Fraction] = []
    cursor = Fraction(0)
    for _measure, start, end in segments:
        origins.append(cursor)
        cursor += end - start

    seen_pause: set[int] = set()
    for staff in staff_measures:
        for play_index, (measure_index, seg_start, seg_end) in enumerate(segments):
            if measure_index >= len(staff):
                continue
            measure = staff[measure_index]
            previous = segments[play_index - 1] if play_index else None
            following = segments[play_index + 1] if play_index + 1 < len(segments) else None
            link_in = previous is not None and _segments_join(previous, (measure_index, seg_start, seg_end), measure.length)
            link_out = following is not None and _segments_join(
                (measure_index, seg_start, seg_end), following, flows[measure_index].length
            )
            origin = origins[play_index]
            for note in measure.notes:
                if note.start < seg_start or note.start >= seg_end:
                    continue
                duration = note.duration
                if note.start + duration > seg_end:
                    duration = seg_end - note.start
                if duration <= 0:
                    continue
                tie_forward = note.tie_forward and note.start + note.duration <= seg_end and (
                    note.end < measure.length or link_out
                )
                tie_back = note.tie_back and (note.start > seg_start or link_in)
                notes.append(
                    replace(
                        note,
                        start=origin + (note.start - seg_start),
                        duration=duration,
                        tie_forward=tie_forward,
                        tie_back=tie_back,
                    )
                )
            for mark in measure.tempos:
                if seg_start <= mark.position < seg_end:
                    _put_tempo(tempos, TempoMark(origin + (mark.position - seg_start), mark.bpm))
            for item in measure.stretches:
                if seg_start <= item.start < seg_end:
                    stretches.append(
                        TimeStretch(origin + (item.start - seg_start), item.duration, item.factor)
                    )
            if (
                measure.pause > 0
                and seg_end == measure.length
                and play_index not in seen_pause
            ):
                pauses.append(Pause(origin + (measure.length - seg_start), measure.pause))
                seen_pause.add(play_index)


def _segments_join(
    previous: tuple[int, Fraction, Fraction],
    following: tuple[int, Fraction, Fraction],
    previous_length: Fraction,
) -> bool:
    previous_index, _start, previous_end = previous
    following_index, following_start, _end = following
    if previous_index == following_index:
        return previous_end == following_start
    return previous_index + 1 == following_index and previous_end == previous_length and following_start == 0


def _merged_anchors(anchors: list[_Anchor]) -> list[_Anchor]:
    merged: dict[Fraction, _Anchor] = {}
    for anchor in anchors:
        current = merged.get(anchor.offset)
        if current is None:
            merged[anchor.offset] = _Anchor(
                offset=anchor.offset,
                start_repeat=anchor.start_repeat,
                end_repeat=anchor.end_repeat,
                markers=list(anchor.markers),
                jump=anchor.jump,
                opens_next=anchor.opens_next,
            )
            continue
        current.start_repeat = current.start_repeat or anchor.start_repeat
        current.end_repeat = max(current.end_repeat, anchor.end_repeat)
        for label in anchor.markers:
            if label not in current.markers:
                current.markers.append(label)
        if anchor.jump is not None:
            current.jump = anchor.jump
        current.opens_next = current.opens_next or anchor.opens_next
    return sorted(merged.values(), key=lambda item: item.offset)


def _flow_anchor(anchor: _Anchor) -> FlowAnchor:
    return FlowAnchor(
        offset=anchor.offset,
        start_repeat=anchor.start_repeat,
        end_repeat=anchor.end_repeat,
        markers=tuple(anchor.markers),
        jump=anchor.jump,
    )


def _anchor_at(anchors: list[_Anchor], offset: Fraction) -> _Anchor:
    for anchor in anchors:
        if anchor.offset == offset:
            return anchor
    anchor = _Anchor(offset=offset)
    anchors.append(anchor)
    return anchor


def _location_delta(element: ET.Element) -> Fraction:
    location = element.find("location")
    if location is None:
        return Fraction(0)
    text = _child_text(location, "fractions")
    if not text:
        return Fraction(0)
    return _parse_fraction(text) * 4


def _grace_kind(element: ET.Element) -> str | None:
    if element.find("appoggiatura") is not None:
        return "appoggiatura"
    for tag in _GRACE_AFTER:
        if element.find(tag) is not None:
            return "after"
    for tag in _GRACE_BEFORE:
        if element.find(tag) is not None:
            return "acciaccatura"
    return None


def _ticks(quarters: Fraction) -> int:
    return int(quarters * 480)


def _apply_acciaccatura(
    pending: list[tuple[str, ET.Element, Fraction]],
    cursor: Fraction,
    state: _VoiceChord | None,
    notes: list[Note],
    earlier_notes: list[Note] | None,
    earlier_length: Fraction | None,
    render: _Render,
) -> None:
    """짧은 꾸밈음은 본음 박 앞에서 난다.

    바로 앞 음이 붙어 있으면 그 음의 절반과 첫 꾸밈음 길이 중 짧은 쪽을 앞 음 끝에서 떼어 낸다.
    쉼표가 끼면 앞 음은 그대로 두고, 꾸밈음만 박 앞에 놓는다.
    """
    if not pending:
        return
    adjacent = state is not None and (state.end == cursor or (cursor == 0 and state.at_barline))
    total = _ticks(pending[0][2])
    if adjacent and state is not None:
        total = min(total, _ticks(state.duration) // 2)
    step = total // len(pending)
    if total <= 0 or step <= 0:
        return
    stolen = Fraction(total, 480)
    if adjacent:
        if cursor > 0:
            _shorten_notes(notes, cursor, stolen)
        elif earlier_notes is not None and earlier_length is not None:
            _shorten_notes(earlier_notes, earlier_length, stolen)
    for index, (_kind, element, _written) in enumerate(pending):
        start = cursor - Fraction(total - step * index, 480)
        duration = Fraction(step, 480)
        sounded = _chord_notes(
            element,
            start=start if start >= 0 else Fraction(0),
            duration=duration,
            render=render,
        )
        if start < 0:
            if earlier_notes is None or earlier_length is None:
                continue
            placed = earlier_length + start
            if placed < 0:
                continue
            earlier_notes.extend(replace(note, start=placed) for note in sounded)
        else:
            notes.extend(sounded)


def _shorten_notes(notes: list[Note], end: Fraction, stolen: Fraction) -> None:
    new_end = end - stolen
    for index, note in enumerate(notes):
        if note.end != end or note.start >= end:
            continue
        duration = new_end - note.start
        if duration > 0:
            notes[index] = replace(note, duration=duration)


def _section_pause(measure: ET.Element) -> float:
    for element in measure.iter("LayoutBreak"):
        if _compact(_child_text(element, "subtype") or "") != "section":
            continue
        written = _child_text(element, "pause")
        if written is None:
            return 3.0
        try:
            value = float(written)
        except ValueError:
            return 3.0
        return value if value > 0 else 0.0
    return 0.0


def _attach_grace_after(
    notes: list[Note],
    element: ET.Element,
    written: Fraction,
    render: _Render,
) -> None:
    if not notes:
        return
    anchor = notes[-1].start
    main = notes[-1].duration
    grace_notes, stolen = _sound_grace(
        [("appoggiatura", element, written)],
        main,
        anchor,
        render,
    )
    if stolen <= 0:
        return
    shortened = main - stolen
    for index, note in enumerate(notes):
        if note.start == anchor:
            notes[index] = replace(note, duration=shortened)
    shift = anchor + shortened
    notes.extend(replace(note, start=shift + (note.start - anchor)) for note in grace_notes)


def _loose_grace(
    pending: list[tuple[str, ET.Element, Fraction]],
    cursor: Fraction,
    render: _Render,
) -> tuple[list[Note], Fraction]:
    notes: list[Note] = []
    span = Fraction(0)
    for kind, element, written in pending:
        sounding = _ACCIACCATURA if kind == "acciaccatura" else written
        notes.extend(
            _chord_notes(
                element,
                start=cursor + span,
                duration=sounding,
                render=render,
            )
        )
        span += sounding
    return notes, span


def _sound_grace(
    pending: list[tuple[str, ET.Element, Fraction]],
    main: Fraction,
    cursor: Fraction,
    render: _Render,
) -> tuple[list[Note], Fraction]:
    """앞꾸밈음은 본음 박 위에서, 첫 꾸밈음의 길이를 본음의 절반까지로 제한해 똑같이 나눈다."""
    if not pending or main <= 0:
        return [], Fraction(0)
    main_ticks = _ticks(main)
    if main_ticks <= 0:
        return [], Fraction(0)
    ontime = min(500, _ticks(pending[0][2]) * 1000 // main_ticks)
    each = ontime // len(pending)
    stolen = Fraction(ontime, 1000) * main
    step = Fraction(each, 1000) * main
    notes: list[Note] = []
    offset = cursor
    if step > 0:
        for _kind, element, _duration in pending:
            notes.extend(
                _chord_notes(
                    element,
                    start=offset,
                    duration=step,
                    render=render,
                )
            )
            offset += step
    return notes, stolen


def _read_measure_flow(measure: ET.Element, raw: _RawMeasure) -> None:
    if measure.find("startRepeat") is not None:
        _anchor_at(raw.anchors, Fraction(0)).start_repeat = True
    if measure.find("endRepeat") is not None:
        count = _positive_int(_child_text(measure, "endRepeat")) or 2
        counted = _positive_int(_child_text(measure, "repeatCount")) or _positive_int(
            _child_text(measure, "playCount")
        )
        anchor = _anchor_at(raw.anchors, raw.length)
        anchor.end_repeat = max(anchor.end_repeat, counted or count)
    if measure.find("cadenza") is not None or measure.find("Cadenza") is not None:
        raw.cadenza = True

    for child in list(measure):
        if child.tag == "voice":
            continue
        if child.tag == "Marker":
            label = _marker_label(child)
            if label:
                _anchor_at(raw.anchors, max(Fraction(0), _location_delta(child))).markers.append(label)
        elif child.tag == "Jump":
            _anchor_at(raw.anchors, max(Fraction(0), _location_delta(child))).jump = _read_jump(child)
        elif child.tag == "BarLine":
            start, end = _barline_flags(_child_text(child, "subtype") or _child_text(child, "barStyle") or "")
            count = (
                _positive_int(_child_text(child, "repeatCount"))
                or _positive_int(_child_text(child, "playCount"))
                or _positive_int(_child_text(measure, "repeatCount"))
                or 2
            )
            position = Fraction(0) if start and not end else raw.length
            anchor = _anchor_at(raw.anchors, position)
            if start and end:
                anchor.end_repeat = max(anchor.end_repeat, count)
                anchor.opens_next = True
            elif start:
                anchor.start_repeat = True
            elif end:
                anchor.end_repeat = max(anchor.end_repeat, count)
    for volta in measure.iter("Volta"):
        endings = _volta_endings(volta)
        if endings:
            raw.voltas.append((frozenset(endings), _volta_span(volta)))
    if any(element.tag == "MeasureRepeat" for element in measure.iter()):
        raw.simile = True
    for tag in ("StaffText", "SystemText", "RehearsalMark"):
        for element in measure.iter(tag):
            if _is_cadenza_text("".join(element.itertext())):
                raw.cadenza = True


def _barline_flags(subtype: str) -> tuple[bool, bool]:
    key = _compact(subtype)
    if key in {"startrepeat", "beginrepeat"}:
        return True, False
    if key in {"endrepeat", "endrepeatbar"}:
        return False, True
    if key in {"endstartrepeat", "endstart"}:
        return True, True
    if subtype.strip().isdigit():
        value = int(subtype)
        return (value & 4) != 0, (value & 8) != 0
    if "start" in key and "end" in key:
        return True, True
    if "start" in key or "begin" in key:
        return True, False
    if "end" in key and "repeat" in key:
        return False, True
    return False, False


def _read_jump(element: ET.Element) -> Jump:
    defaults = {
        "dc": ("", "fine", "", False),
        "dcalfine": ("", "fine", "", False),
        "dacapo": ("", "fine", "", False),
        "dcalcoda": ("", "coda", "codab", False),
        "ds": ("segno", "fine", "", False),
        "dalsegno": ("segno", "fine", "", False),
        "dsalfine": ("segno", "fine", "", False),
        "dsalcoda": ("segno", "coda", "codab", False),
        "dcaldoublecoda": ("", "varcoda", "varcodab", False),
        "dsaldoublecoda": ("segno", "varcoda", "varcodab", False),
    }
    subtype = _compact(_child_text(element, "subtype") or "".join(element.itertext()))
    jump_to, play_until, continue_at, play_repeats = defaults.get(subtype, ("", "fine", "", False))
    if element.find("jumpTo") is not None:
        jump_to = _marker_key(_child_text(element, "jumpTo") or "")
    if element.find("playUntil") is not None:
        play_until = _marker_key(_child_text(element, "playUntil") or "")
    if element.find("continueAt") is not None:
        continue_at = _marker_key(_child_text(element, "continueAt") or "")
    repeats = _child_text(element, "playRepeats")
    if repeats is not None:
        play_repeats = repeats not in {"0", "false"}
    return Jump(jump_to, play_until, continue_at, play_repeats)


def _marker_label(element: ET.Element) -> str:
    written = _child_text(element, "label") or _child_text(element, "markerType") or "".join(element.itertext())
    return _marker_key(written)


def _marker_key(value: str) -> str:
    key = _compact(value)
    aliases = {
        "fine": "fine",
        "segno": "segno",
        "coda": "coda",
        "codab": "codab",
        "tocoda": "coda",
        "varcoda": "varcoda",
        "varcodab": "varcodab",
        "tocodasym": "varcoda",
    }
    return aliases.get(key, key)


def _volta_endings(volta: ET.Element) -> set[int]:
    written = _child_text(volta, "endings") or _child_text(volta, "beginText") or ""
    return {int(number) for number in re.findall(r"\d+", written)}


def _volta_span(volta: ET.Element) -> int:
    measures = volta.find(".//measures")
    if measures is None or not measures.text or not measures.text.strip().lstrip("-").isdigit():
        return 1
    return max(1, abs(int(measures.text.strip())))


def _positive_int(value: str | None) -> int:
    if value and value.strip().isdigit() and int(value) > 0:
        return int(value)
    return 0


def _compact(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _is_cadenza_text(value: str) -> bool:
    folded = value.casefold()
    return any(word.casefold() in folded for word in _CADENZA_WORDS)


def _chord_notes(
    chord: ET.Element,
    *,
    start: Fraction,
    duration: Fraction,
    render: _Render,
) -> list[Note]:
    part_index = render.part_index
    part_name = render.part_name
    staff_index = render.staff_index
    glissandi = render.glissandi
    fifths = render.fifths
    bpm = render.bpm
    accidental_state = render.accidental_state
    if _child_text(chord, "play") == "0":
        return []
    trill = _active_trill(chord)
    found: list[Note] = []
    tpcs: list[int | None] = []
    for note_element in chord.findall("Note"):
        if _child_text(note_element, "play") == "0":
            continue
        pitch_text = _child_text(note_element, "pitch")
        if pitch_text is None:
            continue
        pitch = int(pitch_text)
        tpc_text = _child_text(note_element, "tpc2") or _child_text(note_element, "tpc")
        tpc = int(tpc_text) if tpc_text is not None and tpc_text.lstrip("-").isdigit() else None
        alter = tpc_alter(tpc) if tpc is not None else None
        forward, back = _tie_flags(note_element)
        glide = _glissando_span(note_element)
        if glide is not None and glissandi is not None and trill is None:
            quarters, measures, style = glide
            glissandi.append((start, pitch, quarters, measures, style))
        found.append(
            Note(
                start=start,
                duration=duration,
                pitch=pitch,
                part_index=part_index,
                part_name=part_name,
                staff_index=staff_index,
                alter=alter,
                tie_forward=forward,
                tie_back=back,
            )
        )
        tpcs.append(tpc)
        if accidental_state is not None:
            step = _CIRCLE_TO_STEP[tpc % 7] if tpc is not None else _step_from_pitch(pitch, fifths)
            written_alter = tpc_alter(tpc) if tpc is not None else _written_alter(pitch, step)
            accidental_state[step] = written_alter
    if trill is not None and found:
        top_index = max(range(len(found)), key=lambda index: found[index].pitch)
        upper = _trill_upper_pitch(
            found[top_index].pitch,
            tpcs[top_index],
            fifths,
            trill,
            accidental_state,
        )
        if accidental_state is not None:
            upper_step = _step_from_pitch(upper, fifths)
            accidental_state[upper_step] = _written_alter(upper, upper_step)
        others = [note for index, note in enumerate(found) if index != top_index]
        return others + _expand_trill(found[top_index], upper, bpm, _starts_on_upper(trill))
    marked = {(item[0], item[1]) for item in glissandi} if glissandi is not None else set()
    plain = [note for note in found if (note.start, note.pitch) not in marked]
    gliding = [note for note in found if (note.start, note.pitch) in marked]
    if len(plain) >= 2:
        plain = _spread_arpeggio(chord, plain, bpm)
    return plain + gliding


_NATURAL_PC = (0, 2, 4, 5, 7, 9, 11)
_CIRCLE_TO_STEP = (0, 4, 1, 5, 2, 6, 3)
_SHARP_STEPS = (3, 0, 4, 1, 5, 2, 6)
_FLAT_STEPS = (6, 2, 5, 1, 4, 0, 3)


def _active_trill(chord: ET.Element) -> list[ET.Element] | None:
    found: list[ET.Element] = []
    for element in list(chord.iter("Ornament")) + list(chord.iter("Articulation")) + list(chord.iter("Trill")):
        subtype = _compact(_child_text(element, "subtype") or "")
        if element.tag == "Trill" or subtype in {"trill", "ornamenttrill"}:
            found.append(element)
    if not found or any(_playback_off(element) for element in found):
        return None
    return found


def _playback_off(element: ET.Element) -> bool:
    play = _child_text(element, "play")
    return play in {"0", "false"}


def _expand_trill(note: Note, upper: int, bpm: float, start_on_upper: bool) -> list[Note]:
    """MuseScore 4의 트릴 렌더러와 같은 분할.

    보통 빠르기에서는 32분음표, 아주 빠르면 16분음표, 느리면 그보다 잘게 나눈다.
    본음에서 시작하고, 윗음에서 시작하도록 켜면 그 순서를 바꾼다.
    """
    ticks = float(note.duration) * 480
    if ticks <= 24:
        return [note]
    quarters_per_second = bpm / 60
    if quarters_per_second >= 200 / 60:
        sub_ticks = 120
    elif quarters_per_second >= 108 / 60:
        sub_ticks = 60
    else:
        sub_ticks = 24
    alterations = int(max(ticks / sub_ticks / 2, 0))
    if alterations <= 0:
        return [note]
    total = alterations * 2
    step = note.duration / total
    first, second = (upper, note.pitch) if start_on_upper else (note.pitch, upper)
    sounded: list[Note] = []
    for index in range(alterations):
        for offset, pitch in ((0, first), (1, second)):
            place = index * 2 + offset
            sounded.append(
                replace(
                    note,
                    start=note.start + step * place,
                    duration=step,
                    pitch=pitch,
                    tie_forward=False,
                    tie_back=note.tie_back if place == 0 else False,
                )
            )
    return sounded


def _starts_on_upper(elements: list[ET.Element]) -> bool:
    for element in elements:
        text = _child_text(element, "startOnUpperNote")
        if text in {"1", "true"}:
            return True
    return False


def _trill_upper_pitch(
    pitch: int,
    tpc: int | None,
    fifths: int,
    elements: list[ET.Element],
    accidental_state: dict[int, int] | None,
) -> int:
    for element in elements:
        interval = element.find("intervalAbove")
        if interval is None:
            continue
        step, quality = _ornament_interval(interval)
        if quality != "auto":
            return pitch + _explicit_semitones(step, quality)
        return pitch + _auto_semitones(pitch, tpc, step, fifths, accidental_state)
    for element in elements:
        chromatic = element.find(".//chromatic")
        if chromatic is not None and chromatic.text and chromatic.text.strip().lstrip("-").isdigit():
            return pitch + int(chromatic.text.strip())
    accidental = None
    for element in elements:
        mark = element.find("Accidental")
        if mark is not None:
            accidental = _accidental_alter(mark)
            break
    return pitch + _auto_semitones(pitch, tpc, 1, fifths, accidental_state, accidental)


def _ornament_interval(interval: ET.Element) -> tuple[int, str]:
    """MuseScore는 음정을 `second,minor`처럼 쉼표로 이어 적는다."""
    text = (interval.text or "").strip()
    if "," in text:
        step_name, _, quality = text.partition(",")
        return _interval_step(step_name), _compact(quality) or "auto"
    step = _interval_step(interval.get("step") or _child_text(interval, "step") or "second")
    quality = _compact(interval.get("type") or _child_text(interval, "type") or "auto")
    return step, quality


def _interval_step(value: str) -> int:
    names = {
        "unison": 0,
        "second": 1,
        "third": 2,
        "fourth": 3,
        "fifth": 4,
        "sixth": 5,
        "seventh": 6,
        "octave": 7,
    }
    return names.get(_compact(value), 1)


def _explicit_semitones(step: int, quality: str) -> int:
    base = {0: 0, 1: 2, 2: 4, 3: 5, 4: 7, 5: 9, 6: 11, 7: 12}[step]
    perfect = step in {0, 3, 4, 7}
    if perfect:
        if quality == "diminished":
            return base - 1
        if quality == "augmented":
            return base + 1
        return base
    if quality == "diminished":
        return base - 2
    if quality == "minor":
        return base - 1
    if quality == "augmented":
        return base + 1
    return base


def _auto_semitones(
    pitch: int,
    tpc: int | None,
    steps: int,
    fifths: int,
    accidental_state: dict[int, int] | None,
    accidental: int | None = None,
) -> int:
    step = _CIRCLE_TO_STEP[tpc % 7] if tpc is not None else _step_from_pitch(pitch, fifths)
    sounded = pitch
    for _index in range(max(steps, 0)):
        step = (step + 1) % 7
        alter = accidental if accidental is not None and _index == steps - 1 else _state_alter(
            step, fifths, accidental_state
        )
        target = (_NATURAL_PC[step] + alter) % 12
        for delta in range(1, 13):
            if (sounded + delta) % 12 == target:
                sounded += delta
                break
    return sounded - pitch


def _state_alter(step: int, fifths: int, accidental_state: dict[int, int] | None) -> int:
    if accidental_state is not None and step in accidental_state:
        return accidental_state[step]
    return _alter_for_step(step, fifths)


def _written_alter(pitch: int, step: int) -> int:
    natural = _NATURAL_PC[step]
    alter = (pitch % 12) - natural
    if alter > 6:
        alter -= 12
    if alter < -6:
        alter += 12
    return alter


def _step_from_pitch(pitch: int, fifths: int) -> int:
    pc = pitch % 12
    for step in range(7):
        if (_NATURAL_PC[step] + _alter_for_step(step, fifths)) % 12 == pc:
            return step
    for step, natural in enumerate(_NATURAL_PC):
        if natural == pc:
            return step
    if fifths >= 0:
        for step, natural in enumerate(_NATURAL_PC):
            if (natural + 1) % 12 == pc:
                return step
    else:
        for step, natural in enumerate(_NATURAL_PC):
            if (natural - 1) % 12 == pc:
                return step
    return 0


def _alter_for_step(step: int, fifths: int) -> int:
    if fifths > 0 and step in _SHARP_STEPS[:fifths]:
        return 1
    if fifths < 0 and step in _FLAT_STEPS[:-fifths]:
        return -1
    return 0


def _accidental_alter(element: ET.Element) -> int | None:
    subtype = _compact(_child_text(element, "subtype") or "".join(element.itertext()))
    values = {
        "accidentaldoubleflat": -2,
        "accidentalflat": -1,
        "accidentalnatural": 0,
        "accidentalsharp": 1,
        "accidentaldoublesharp": 2,
        "flat": -1,
        "natural": 0,
        "sharp": 1,
    }
    return values.get(subtype)


def _key_fifths(element: ET.Element) -> int | None:
    target = element if element.tag == "KeySig" else None
    if target is None:
        for child in list(element):
            if child.tag == "KeySig":
                target = child
                break
    if target is None:
        return None
    text = _child_text(target, "accidental") or _child_text(target, "concertKey")
    if text is None or not text.lstrip("-").isdigit():
        return None
    return int(text)


def _spread_arpeggio(chord: ET.Element, notes: list[Note], bpm: float) -> list[Note]:
    """MuseScore MIDI와 같이 64틱에서 시작해, 화음에 다 안 들어가면 2/3로 줄인다."""
    direction = _arpeggio_direction(chord)
    if direction is None or len(notes) < 2:
        return notes
    ordered = sorted(notes, key=lambda note: note.pitch, reverse=direction == "down")
    span = ordered[0].duration
    ticks = _ticks(span)
    if ticks <= 0:
        return notes
    gap = 64
    while gap and gap * len(ordered) > ticks:
        gap = 2 * gap // 3
    stretch = _arpeggio_stretch(chord)
    ratio = bpm / 120.0 if bpm > 0 else 1.0
    start = ordered[0].start
    end = ordered[0].end
    spread: list[Note] = []
    for index, note in enumerate(ordered):
        ot = int(((gap * index * 1000) // ticks) * ratio * stretch)
        ot = min(max(ot, 0), 1000)
        onset = start + span * Fraction(ot, 1000)
        spread.append(replace(note, start=onset, duration=max(end - onset, Fraction(0))))
    return spread


def _arpeggio_stretch(chord: ET.Element) -> float:
    element = chord.find("Arpeggio")
    if element is None:
        return 1.0
    written = _child_text(element, "timeStretch")
    if not written:
        return 1.0
    try:
        value = float(written)
    except ValueError:
        return 1.0
    return value if value > 0 else 1.0


def _arpeggio_direction(chord: ET.Element) -> str | None:
    element = chord.find("Arpeggio")
    if element is None:
        written = _child_text(chord, "arpeggio")
        if written is None:
            return None
        return _direction_name(written)
    return _direction_name(_child_text(element, "subtype") or "0")


def _direction_name(value: str) -> str:
    key = _compact(value)
    if key in {"2", "5", "down", "downstraight"}:
        return "down"
    return "up"


def _glissando_span(note_element: ET.Element) -> tuple[Fraction, int, str] | None:
    located: list[tuple[ET.Element, ET.Element | None]] = []
    for spanner in note_element.findall("Spanner"):
        if spanner.get("type") not in {"Glissando", "Portamento"}:
            continue
        body = spanner.find("Glissando")
        if body is None:
            body = spanner.find("Portamento")
        if body is None:
            body = spanner
        location = body.find(".//location")
        if location is None:
            location = spanner.find(".//location")
        located.append((body, location))
    for tag in ("Glissando", "Portamento"):
        found = note_element.find(tag)
        if found is not None:
            located.append((found, found.find(".//location")))
    if not located:
        return None
    body, location = located[0]
    quarters = Fraction(0)
    measures = 0
    if location is not None:
        fractions = _child_text(location, "fractions")
        if fractions:
            quarters = _parse_fraction(fractions) * 4
        counted = _child_text(location, "measures")
        if counted and counted.lstrip("-").isdigit():
            measures = int(counted)
    text = " ".join(
        part
        for part in (
            _child_text(body, "subtype"),
            _child_text(body, "glissandoStyle"),
            _child_text(body, "text"),
            body.get("type"),
        )
        if part
    )
    style = "white" if "white" in _compact(text) or "diatonic" in _compact(text) else "chromatic"
    return quarters, measures, style


def _resolve_glissandi(measures: list[_RawMeasure]) -> None:
    if not any(measure.glissandi for measure in measures):
        return
    origins: list[Fraction] = []
    cursor = Fraction(0)
    for measure in measures:
        origins.append(cursor)
        cursor += measure.length
    for index, measure in enumerate(measures):
        if not measure.glissandi:
            continue
        rebuilt: list[Note] = []
        replaced: set[int] = set()
        for note_index, note in enumerate(measure.notes):
            match = next(
                (
                    spec
                    for spec in measure.glissandi
                    if spec[0] == note.start and spec[1] == note.pitch and note_index not in replaced
                ),
                None,
            )
            if match is None:
                rebuilt.append(note)
                continue
            replaced.add(note_index)
            _start, _pitch, quarters, measure_delta, style = match
            target = _glissando_target(measures, origins, index, note, quarters, measure_delta)
            rebuilt.extend(_glissando_notes(note, target, style))
        measure.notes = rebuilt


def _glissando_target(
    measures: list[_RawMeasure],
    origins: list[Fraction],
    measure_index: int,
    note: Note,
    quarters: Fraction,
    measure_delta: int,
) -> int | None:
    if measure_delta == 0:
        tick = origins[measure_index] + note.start + quarters
    else:
        destination = measure_index + measure_delta
        if destination < 0 or destination >= len(measures):
            return None
        tick = origins[destination] + quarters
    closest: tuple[int, int] | None = None
    for index, measure in enumerate(measures):
        for candidate in measure.notes:
            if candidate.part_index != note.part_index or candidate.staff_index != note.staff_index:
                continue
            if origins[index] + candidate.start != tick or candidate.pitch == note.pitch:
                continue
            distance = abs(candidate.pitch - note.pitch)
            if closest is None or distance < closest[0]:
                closest = (distance, candidate.pitch)
    if closest is None:
        return None
    return closest[1]


def _glissando_notes(note: Note, end_pitch: int | None, style: str) -> list[Note]:
    if end_pitch is None or end_pitch == note.pitch or note.duration <= 0:
        return [note]
    pitches = _glissando_pitches(note.pitch, end_pitch, style == "white")
    if len(pitches) <= 1:
        return [note]
    step = note.duration / len(pitches)
    sounded: list[Note] = []
    for index, pitch in enumerate(pitches):
        sounded.append(
            replace(
                note,
                start=note.start + step * index,
                duration=step,
                pitch=pitch,
                tie_forward=False,
                tie_back=note.tie_back if index == 0 else False,
            )
        )
    return sounded


def _glissando_pitches(start: int, end: int, white: bool) -> list[int]:
    step = 1 if end > start else -1
    pitches: list[int] = []
    pitch = start
    while (step > 0 and pitch < end) or (step < 0 and pitch > end):
        pitches.append(pitch)
        pitch += step
        if not white:
            continue
        while (step > 0 and pitch < end) or (step < 0 and pitch > end):
            if pitch % 12 not in {1, 3, 6, 8, 10}:
                break
            pitch += step
    return pitches


def _duration(
    element: ET.Element,
    division: int,
    measure_len: Fraction,
    stack: list[tuple[int, int]],
) -> Fraction:
    duration_type = _child_text(element, "durationType")
    if duration_type is None:
        ticks = _child_text(element, "duration")
        if ticks is None:
            raise ScoreError(t("no_duration"))
        return Fraction(int(ticks), division)

    if duration_type == "measure":
        length = measure_len
    else:
        try:
            length = _QUARTERS[duration_type]
        except KeyError as exc:
            raise ScoreError(t("bad_duration", duration=duration_type)) from exc
        dots_text = _child_text(element, "dots")
        dots = int(dots_text) if dots_text else 0
        if dots > 0:
            length *= Fraction((1 << (dots + 1)) - 1, 1 << dots)

    for normal, actual in stack:
        length *= Fraction(normal, actual)
    return length


def _tuplet_ratio(element: ET.Element) -> tuple[int, int]:
    normal = int(_child_text(element, "normalNotes") or "2")
    actual = int(_child_text(element, "actualNotes") or "3")
    if actual <= 0 or normal <= 0:
        raise ScoreError(t("bad_tuplet"))
    return normal, actual


def _tie_flags(note_element: ET.Element) -> tuple[bool, bool]:
    forward = False
    back = False
    spanners = [
        element
        for element in note_element.findall("Spanner")
        if element.get("type") in {None, "Tie"}
    ]
    spanners.extend(note_element.findall("Tie"))
    for spanner in spanners:
        has_next = spanner.find(".//next") is not None
        has_prev = spanner.find(".//prev") is not None
        if has_next:
            forward = True
        if has_prev:
            back = True
        if spanner.tag == "Tie" and not has_next and not has_prev:
            forward = True
    return forward, back


def _is_percussion(staff: ET.Element) -> bool:
    for staff_type in staff.findall("StaffType"):
        if staff_type.get("group") == "percussion":
            return True
        group = staff_type.find("group")
        if group is not None and (group.text or "").strip() == "percussion":
            return True
    return False


def _time_signature(measure: ET.Element) -> tuple[int, int] | None:
    for element in measure.iter("TimeSig"):
        numerator = _child_text(element, "sigN")
        denominator = _child_text(element, "sigD")
        if numerator and denominator and int(denominator) > 0:
            return int(numerator), int(denominator)
    return None


def _measure_length(measure: ET.Element, signature: tuple[int, int]) -> Fraction:
    irregular = measure.get("len")
    if irregular:
        return _parse_fraction(irregular) * 4
    numerator, denominator = signature
    return Fraction(numerator, denominator) * 4


_FERMATA_FACTORS = {
    "fermata": 2.0,
    "fermataAbove": 2.0,
    "fermataBelow": 2.0,
    "fermataShort": 1.5,
    "fermataShortAbove": 1.5,
    "fermataShortBelow": 1.5,
    "fermataLong": 3.0,
    "fermataLongAbove": 3.0,
    "fermataLongBelow": 3.0,
    "fermataVeryShort": 1.25,
    "fermataVeryShortAbove": 1.25,
    "fermataVeryShortBelow": 1.25,
    "fermataVeryLong": 4.0,
    "fermataVeryLongAbove": 4.0,
    "fermataVeryLongBelow": 4.0,
}


def _fermata_factor(element: ET.Element) -> float | None:
    """페르마타가 이 음표·쉼표를 몇 배로 늘리는지. 없으면 None.

    MuseScore의 timeStretch가 있으면 그 값을 쓰고, 없으면 기호 종류로 정한다.
    보통 페르마타는 2배다. 이 구간이 늘어난 만큼 뒤의 음도 늦어진다.
    """
    fermata = element.find("Fermata")
    if fermata is None:
        return None
    written = _child_text(fermata, "timeStretch")
    if written:
        value = float(written)
        if value > 0:
            return value
    subtype = (_child_text(fermata, "subtype") or "fermata").strip()
    return _FERMATA_FACTORS.get(subtype, 2.0)


def _tempo_bpm(element: ET.Element) -> float | None:
    raw = _child_text(element, "tempo")
    if raw:
        per_second = float(raw)
        if per_second > 0:
            return per_second * 60.0
    match = re.search(r"=\s*(\d+(?:\.\d+)?)", "".join(element.itertext()))
    if not match:
        return None
    bpm = float(match.group(1))
    return bpm if bpm > 0 else None


def _warn_once(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def _put_tempo(tempos: list[TempoMark], mark: TempoMark) -> None:
    for index, existing in enumerate(tempos):
        if existing.position == mark.position:
            tempos[index] = mark
            return
    tempos.append(mark)


def _division(score_element: ET.Element) -> int:
    raw = _child_text(score_element, "Division")
    if raw is None:
        return 480
    value = int(raw)
    return value if value > 0 else 480


def _meta(score_element: ET.Element, name: str) -> str | None:
    for element in score_element.iter("metaTag"):
        if element.get("name") == name:
            text = "".join(element.itertext()).strip()
            if text:
                return text
    return None


def _plain_text(parent: ET.Element, tag: str) -> str | None:
    for element in parent.iter(tag):
        text = "".join(element.itertext()).strip()
        if text:
            return text
    return None


def _child_text(parent: ET.Element, tag: str) -> str | None:
    element = parent.find(tag)
    if element is None or element.text is None:
        return None
    text = element.text.strip()
    return text or None


def _parse_fraction(text: str) -> Fraction:
    token = text.strip()
    if "/" not in token:
        return Fraction(token)
    numerator, denominator = token.split("/", 1)
    return Fraction(int(numerator.strip()), int(denominator.strip()))
