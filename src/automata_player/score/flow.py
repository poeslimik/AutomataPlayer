"""반복과 도돌이표를 연주 순서로 펼친다.

세뇨, Fine, 코다, D.C., D.S.가 마디 중간에 있으면 그 박부터 이어서 연주하거나 그 박에서 멈춘다.
못갖춘마디도 같은 규칙이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class Jump:
    jump_to: str
    play_until: str
    continue_at: str
    play_repeats: bool


@dataclass(frozen=True)
class FlowAnchor:
    offset: Fraction
    start_repeat: bool = False
    end_repeat: int = 0
    markers: tuple[str, ...] = ()
    jump: Jump | None = None


@dataclass(frozen=True)
class MeasureFlow:
    length: Fraction
    endings: frozenset[int] | None = None
    anchors: tuple[FlowAnchor, ...] = ()
    onsets: tuple[Fraction, ...] = ()


def playback_segments(flows: list[MeasureFlow]) -> tuple[list[tuple[int, Fraction, Fraction]], bool]:
    """연주할 (마디, 시작 박, 끝 박) 목록. 끝 박은 포함하지 않는다."""
    count = len(flows)
    if count == 0:
        return [], False

    segments: list[tuple[int, Fraction, Fraction]] = []
    stack: list[list[object]] = [[0, Fraction(0), 1]]
    index = 0
    offset = Fraction(0)
    arrived = False
    force_final = False
    play_until = ""
    continue_at = ""
    jumps_taken: set[tuple[int, Fraction]] = set()
    unresolved = False
    deepest = 1
    for flow in flows:
        for anchor in flow.anchors:
            deepest = max(deepest, anchor.end_repeat)
    limit = count * max(4, deepest) * 8 + 8
    steps = 0

    while index < count and steps < limit:
        steps += 1
        flow = flows[index]
        if offset >= flow.length:
            index += 1
            offset = Fraction(0)
            arrived = False
            continue

        passage = int(stack[-1][2])
        if flow.endings is not None and passage not in flow.endings:
            index += 1
            offset = Fraction(0)
            arrived = False
            continue

        if _anchor_at(flow, offset, "start") and not arrived:
            if (stack[-1][0], stack[-1][1]) != (index, offset):
                landing = _enclosing_repeat_count(flows, index, offset) if force_final else 1
                stack.append([index, offset, landing])
        arrived = False
        passage = int(stack[-1][2])

        start_at = _next_start_repeat(flow, offset)
        decision = _next_decision(
            flows,
            index,
            offset,
            passage,
            force_final,
            play_until,
            jumps_taken,
            stack,
        )
        boundary = flow.length
        if start_at is not None:
            boundary = min(boundary, start_at)
        if decision is not None:
            boundary = min(boundary, _resume_after(decision[0], flow))
        if boundary <= offset:
            boundary = flow.length
        if boundary > offset:
            segments.append((index, offset, boundary))

        if start_at is not None and (decision is None or start_at < decision[0]):
            offset = start_at
            continue
        if decision is None or boundary < decision[0]:
            if boundary >= flow.length:
                index += 1
                offset = Fraction(0)
            else:
                offset = boundary
            continue

        kind, anchor = decision[1], decision[2]
        if kind == "until":
            if not continue_at:
                break
            target = _find_marker(flows, continue_at)
            play_until = ""
            continue_at = ""
            if target is None:
                unresolved = True
                break
            force_final = True
            landing = _enclosing_repeat_count(flows, target[0], target[1])
            stack = [[target[0], target[1], landing]]
            index, offset = target
            arrived = True
            continue
        if kind == "end" and passage < anchor.end_repeat:
            stack[-1][2] = passage + 1
            index = int(stack[-1][0])
            offset = stack[-1][1]
            arrived = True
            continue
        if kind == "end" and len(stack) > 1:
            stack.pop()
        if kind == "jump" and anchor.jump is not None:
            jumps_taken.add((index, anchor.offset))
            spec = anchor.jump
            target = _find_marker(flows, spec.jump_to) if spec.jump_to else (0, Fraction(0))
            if spec.jump_to and target is None:
                unresolved = True
            else:
                play_until = spec.play_until
                continue_at = spec.continue_at
                force_final = not spec.play_repeats
                landing_at = target if target is not None else (0, Fraction(0))
                landing_pass = (
                    _enclosing_repeat_count(flows, landing_at[0], landing_at[1]) if force_final else 1
                )
                stack = [[landing_at[0], landing_at[1], landing_pass]]
                index, offset = landing_at
                arrived = True
                continue
        if boundary >= flow.length:
            index += 1
            offset = Fraction(0)
        else:
            offset = boundary

    if steps >= limit:
        return [(item, Fraction(0), flows[item].length) for item in range(count)], True
    return segments, unresolved


def _anchor_at(flow: MeasureFlow, offset: Fraction, kind: str) -> bool:
    for anchor in flow.anchors:
        if anchor.offset != offset:
            continue
        if kind == "start" and anchor.start_repeat:
            return True
    return False


def _next_start_repeat(flow: MeasureFlow, offset: Fraction) -> Fraction | None:
    found = [anchor.offset for anchor in flow.anchors if anchor.start_repeat and anchor.offset > offset]
    if not found:
        return None
    return min(found)


def _next_decision(
    flows: list[MeasureFlow],
    index: int,
    offset: Fraction,
    passage: int,
    force_final: bool,
    play_until: str,
    jumps_taken: set[tuple[int, Fraction]],
    stack: list[list[object]],
) -> tuple[Fraction, str, FlowAnchor] | None:
    flow = flows[index]
    found: list[tuple[Fraction, int, str, FlowAnchor]] = []
    start_measure, start_offset, _passage = stack[-1]
    repeat_count = _enclosing_repeat_count(flows, int(start_measure), start_offset)  # type: ignore[arg-type]
    for anchor in flow.anchors:
        if anchor.offset < offset:
            continue
        if play_until and play_until in anchor.markers:
            found.append((anchor.offset, 0, "until", anchor))
        if anchor.end_repeat:
            found.append((anchor.offset, 1, "end", anchor))
        if anchor.jump is not None and (index, anchor.offset) not in jumps_taken:
            deferred = (not force_final) and repeat_count > 1 and passage < repeat_count
            if not deferred:
                found.append((anchor.offset, 2, "jump", anchor))
    if not found:
        return None
    offset_at, _priority, kind, anchor = min(found, key=lambda item: (item[0], item[1]))
    return offset_at, kind, anchor


def _resume_after(offset: Fraction, flow: MeasureFlow) -> Fraction:
    later = [onset for onset in flow.onsets if onset > offset]
    if later:
        return min(later)
    return flow.length


def _enclosing_repeat_count(flows: list[MeasureFlow], start_measure: int, start_offset: Fraction) -> int:
    depth = 0
    for measure in range(start_measure, len(flows)):
        for anchor in flows[measure].anchors:
            if measure == start_measure and anchor.offset < start_offset:
                continue
            origin = measure == start_measure and anchor.offset == start_offset and anchor.start_repeat
            if anchor.start_repeat and not origin:
                depth += 1
            if not anchor.end_repeat:
                continue
            if depth == 0:
                return anchor.end_repeat
            depth -= 1
    return 1


def _find_marker(flows: list[MeasureFlow], label: str) -> tuple[int, Fraction] | None:
    if not label:
        return 0, Fraction(0)
    for index, flow in enumerate(flows):
        for anchor in flow.anchors:
            if label in anchor.markers:
                return index, anchor.offset
    return None
