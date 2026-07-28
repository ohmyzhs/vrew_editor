from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .project import clip_caption, short_id


OPEN_QUOTES = {'"', "“", "‘", "「", "『"}
CLOSE_QUOTES = {'"', "”", "’", "」", "』"}
ALL_QUOTES = OPEN_QUOTES | CLOSE_QUOTES
SENTENCE_END = re.compile(r'[.!?。！？…]+[\'"”’」』)\]]*$')
COMMA_END = re.compile(r'[,，、;；:：]+[\'"”’」』)\]]*$')
SOFT_ENDING = re.compile(
    r"(지만|는데|은데|ㄴ데|으나|거나|면서|으며|므로|니까|기에|"
    r"더니|다가|고|며|서|면|때|후|전)[,，、;；:：]?$"
)
STRONG_BINDING_END = re.compile(r"(의)$")
OBJECT_BINDING_END = re.compile(r"(을|를|와|과)$")
DEPENDENT_NEXT = re.compile(
    r"^(것|수|줄|채|뿐|듯|데|중|때|후|전|앞으로|뒤로|"
    r"안으로|밖으로|곁으로|위해|통해)"
)
MIN_CLAUSE_CHARS = 4
PUNCTUATION_HARD_SPLIT_CHARS = 12
PREFERRED_MIN_CHUNK_CHARS = 10
CHARACTER_TOLERANCE_RATIO = 0.10


def visible_length(text: str) -> int:
    return sum(1 for char in text if not char.isspace())


def semantic_length(text: str) -> int:
    return sum(1 for char in text if char.isalnum())


def soft_character_limit(max_chars: int) -> int:
    tolerance = max(1, round(max_chars * CHARACTER_TOLERANCE_RATIO))
    return max_chars + tolerance


def normalized_token(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return "".join(
        char.casefold() for char in text if char.isalnum()
    )


def _quote_state_after(text: str, in_quote: bool = False) -> bool:
    for char in text:
        if char == '"':
            in_quote = not in_quote
        elif char in OPEN_QUOTES:
            in_quote = True
        elif char in CLOSE_QUOTES:
            in_quote = False
    return in_quote


def _caption_tokens(clips: list[dict[str, Any]]) -> list[str]:
    joined = " ".join(clip_caption(clip) for clip in clips)
    return re.findall(r"\S+", joined)


def _word_units(clips: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    units: list[list[dict[str, Any]]] = []
    pending_prefix: list[dict[str, Any]] = []
    for clip in clips:
        for word in clip.get("words", []):
            word_type = word.get("type")
            if word_type == 2:
                continue
            if word_type == 0:
                unit = pending_prefix + [word]
                pending_prefix = []
                units.append(unit)
            elif units:
                units[-1].append(word)
            else:
                pending_prefix.append(word)
    if pending_prefix and units:
        units[-1].extend(pending_prefix)
    return units


def _split_context_groups(tokens: list[str]) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    in_quote = False
    current_kind = "narration"

    for token in tokens:
        starts_in_quote = in_quote
        token_kind = "dialogue" if starts_in_quote else "narration"
        for char in token:
            if char in OPEN_QUOTES:
                if char == '"':
                    in_quote = not in_quote
                else:
                    in_quote = True
                if not starts_in_quote:
                    token_kind = "dialogue"
            elif char in CLOSE_QUOTES:
                if char == '"':
                    in_quote = not in_quote
                else:
                    in_quote = False

        if current and token_kind != current_kind:
            groups.append(current)
            current = []
        current_kind = token_kind
        current.append(token)
        if starts_in_quote and not in_quote:
            groups.append(current)
            current = []
            current_kind = "narration"
    if current:
        groups.append(current)
    return groups


def _next_clause_length(tokens: list[str], start: int) -> int:
    parts: list[str] = []
    for token in tokens[start:]:
        parts.append(token)
        if SENTENCE_END.search(token) or COMMA_END.search(token):
            break
    return semantic_length(" ".join(parts))


def _split_explicit_boundaries(tokens: list[str]) -> list[list[str]]:
    """Hard-split only substantial clauses; short punctuation stays mergeable."""
    groups: list[list[str]] = []
    current: list[str] = []
    for index, token in enumerate(tokens):
        current.append(token)
        if SENTENCE_END.search(token):
            left_length = semantic_length(" ".join(current))
            right_length = _next_clause_length(tokens, index + 1)
            if (
                left_length > PUNCTUATION_HARD_SPLIT_CHARS
                and (
                    right_length == 0
                    or right_length > PUNCTUATION_HARD_SPLIT_CHARS
                )
            ):
                groups.append(current)
                current = []
            continue
        if COMMA_END.search(token):
            left_length = semantic_length(" ".join(current))
            right_length = _next_clause_length(tokens, index + 1)
            if (
                left_length > PUNCTUATION_HARD_SPLIT_CHARS
                and right_length > PUNCTUATION_HARD_SPLIT_CHARS
            ):
                groups.append(current)
                current = []
    if current:
        groups.append(current)
    return groups


def _boundary_adjustment(
    token: str,
    next_token: str | None,
    pause_after: float,
    clause_chars: int,
) -> float:
    adjustment = 0.0
    if SENTENCE_END.search(token):
        adjustment += (
            140.0
            if clause_chars <= PUNCTUATION_HARD_SPLIT_CHARS
            else -80.0
        )
    elif COMMA_END.search(token):
        adjustment += (
            110.0
            if clause_chars <= PUNCTUATION_HARD_SPLIT_CHARS
            else -45.0
        )
    stripped = token.rstrip('.,!?。！？…，、;；:：\'"”’」』)]')
    if SOFT_ENDING.search(stripped):
        adjustment -= 18.0
    if pause_after >= 0.8:
        adjustment -= 55.0
    elif pause_after >= 0.45:
        adjustment -= 28.0
    if STRONG_BINDING_END.search(stripped):
        adjustment += 400.0
    elif OBJECT_BINDING_END.search(stripped):
        adjustment += 250.0
    if next_token and DEPENDENT_NEXT.search(
        next_token.lstrip('\'"“‘「『')
    ):
        adjustment += 95.0
    return adjustment


def _chunk_tokens(
    tokens: list[str],
    max_chars: int,
    pause_after: list[float] | None = None,
) -> list[list[str]]:
    """Find balanced word-only chunks, preferring grammatical breakpoints."""
    if not tokens:
        return []
    pauses = pause_after or [0.0] * len(tokens)
    soft_max_chars = soft_character_limit(max_chars)
    prefix = [0]
    semantic_prefix = [0]
    for token in tokens:
        prefix.append(prefix[-1] + visible_length(token))
        semantic_prefix.append(semantic_prefix[-1] + semantic_length(token))
    if prefix[-1] <= soft_max_chars:
        return [tokens]

    # Cost tuple: fewest clips first, then semantic/length quality.
    best: list[tuple[int, float, int] | None] = [None] * (len(tokens) + 1)
    best[0] = (0, 0.0, -1)
    for right in range(1, len(tokens) + 1):
        candidate: tuple[int, float, int] | None = None
        for left in range(right):
            previous = best[left]
            if previous is None:
                continue
            length = prefix[right] - prefix[left]
            token_count = right - left
            if length > soft_max_chars and token_count > 1:
                continue
            short_penalty = (
                300.0
                if length < PREFERRED_MIN_CHUNK_CHARS
                and not (left == 0 and right == len(tokens))
                else 0.0
            )
            single_word_penalty = (
                90.0 if token_count == 1 and len(tokens) > 1 else 0.0
            )
            # Balanced chunks avoid a tiny tail; linguistic endings lower cost.
            quality = (
                previous[1]
                + (max_chars - min(length, max_chars)) ** 2
                + max(0, length - max_chars) ** 2 * 40.0
                + short_penalty
                + single_word_penalty
                + _boundary_adjustment(
                    tokens[right - 1],
                    tokens[right] if right < len(tokens) else None,
                    pauses[right - 1],
                    semantic_prefix[right] - semantic_prefix[left],
                )
            )
            score = (previous[0] + 1, quality, left)
            if candidate is None or score[:2] < candidate[:2]:
                candidate = score
        best[right] = candidate

    boundaries = [len(tokens)]
    cursor = len(tokens)
    while cursor > 0:
        item = best[cursor]
        if item is None:
            # Only possible for malformed input; preserve the remaining words.
            boundaries.append(0)
            break
        cursor = item[2]
        boundaries.append(cursor)
    boundaries.reverse()
    return [
        tokens[left:right]
        for left, right in zip(boundaries, boundaries[1:])
    ]


def semantic_chunks(
    tokens: list[str],
    max_chars: int = 20,
    pause_after: list[float] | None = None,
) -> list[list[str]]:
    chunks: list[list[str]] = []
    pauses = pause_after or [0.0] * len(tokens)
    token_cursor = 0
    for context_group in _split_context_groups(tokens):
        context_pauses = pauses[
            token_cursor : token_cursor + len(context_group)
        ]
        explicit_cursor = 0
        for explicit_group in _split_explicit_boundaries(context_group):
            explicit_pauses = context_pauses[
                explicit_cursor : explicit_cursor + len(explicit_group)
            ]
            chunks.extend(
                _chunk_tokens(
                    explicit_group,
                    max_chars,
                    explicit_pauses,
                )
            )
            explicit_cursor += len(explicit_group)
        token_cursor += len(context_group)
    return chunks


def _type2_marker(last_unit: list[dict[str, Any]]) -> dict[str, Any]:
    last = last_unit[-1]
    start = float(last.get("originalStartTime", 0) or 0)
    duration = float(last.get("originalDuration", last.get("duration", 0)) or 0)
    return {
        "id": short_id(),
        "text": "",
        "playbackRate": 1,
        "duration": 0,
        "aligned": False,
        "type": 2,
        "originalDuration": 0,
        "originalStartTime": start + duration,
        "truncatedWords": [],
        "assetIds": [],
    }


@dataclass
class ClipRepair:
    scene_id: str
    original_clip_count: int
    repaired_clip_count: int
    before: list[str]
    after: list[str]
    reasons: list[str] = field(default_factory=list)


@dataclass
class ClipRepairReport:
    original_clip_count: int
    final_clip_count: int
    repaired_scenes: list[ClipRepair]
    skipped_scenes: list[dict[str, Any]]

    @property
    def changed(self) -> bool:
        return bool(self.repaired_scenes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "originalClipCount": self.original_clip_count,
            "finalClipCount": self.final_clip_count,
            "repairedSceneCount": len(self.repaired_scenes),
            "repairs": [
                {
                    "sceneId": item.scene_id,
                    "originalClipCount": item.original_clip_count,
                    "repairedClipCount": item.repaired_clip_count,
                    "before": item.before,
                    "after": item.after,
                    "reasons": item.reasons,
                }
                for item in self.repaired_scenes
            ],
            "skippedScenes": self.skipped_scenes,
        }


def _repair_scene(
    scene_clips: list[dict[str, Any]], max_chars: int
) -> tuple[list[dict[str, Any]], ClipRepair | None, str | None]:
    tokens = _caption_tokens(scene_clips)
    if not tokens:
        return scene_clips, None, None

    units = _word_units(scene_clips)
    if len(tokens) != len(units):
        return scene_clips, None, (
            f"caption/word token mismatch ({len(tokens)} != {len(units)})"
        )
    for token, unit in zip(tokens, units):
        spoken = next((word for word in unit if word.get("type") == 0), None)
        if spoken is None or normalized_token(token) != normalized_token(
            str(spoken.get("text", ""))
        ):
            return scene_clips, None, "caption/word text mismatch"

    pauses = [
        sum(
            float(word.get("duration", 0) or 0)
            for word in unit
            if word.get("type") == 1
        )
        for unit in units
    ]
    chunks = semantic_chunks(tokens, max_chars, pauses)
    before = [clip_caption(clip) for clip in scene_clips]
    after = [" ".join(chunk) for chunk in chunks]
    if [normalized_token(text) for text in before] == [
        normalized_token(text) for text in after
    ]:
        return scene_clips, None, None

    new_clips: list[dict[str, Any]] = []
    unit_cursor = 0
    for chunk_index, chunk in enumerate(chunks):
        selected_units = units[unit_cursor : unit_cursor + len(chunk)]
        unit_cursor += len(chunk)
        template = copy.deepcopy(
            scene_clips[min(chunk_index, len(scene_clips) - 1)]
        )
        if chunk_index >= len(scene_clips):
            template["id"] = short_id()
        words = [
            copy.deepcopy(word)
            for unit in selected_units
            for word in unit
            if word.get("type") != 2
        ]
        words.append(_type2_marker(selected_units[-1]))
        template["words"] = words
        template["captions"] = [
            {"text": [{"insert": " ".join(chunk) + "\n"}]},
            {"text": [{"insert": "\n"}]},
        ]
        template.setdefault("dirty", {})["caption"] = True
        template.setdefault("dirty", {})["video"] = True
        new_clips.append(template)

    reasons = ["따옴표/문장부호/20글자 의미 단위 재분할"]
    if any(
        visible_length(text) > soft_character_limit(max_chars)
        for text in after
    ):
        reasons.append("단일 어절이 글자 제한 초과")
    repair = ClipRepair(
        scene_id=str(scene_clips[0].get("sceneId", "")),
        original_clip_count=len(scene_clips),
        repaired_clip_count=len(new_clips),
        before=before,
        after=after,
        reasons=reasons,
    )
    return new_clips, repair, None


def repair_dialogue_clips(
    clips: list[dict[str, Any]], max_chars: int = 20
) -> tuple[list[dict[str, Any]], ClipRepairReport]:
    original_count = len(clips)
    output: list[dict[str, Any]] = []
    repairs: list[ClipRepair] = []
    skipped: list[dict[str, Any]] = []

    def first_spoken_start(clip: dict[str, Any]) -> float | None:
        for word in clip.get("words", []):
            if word.get("type") == 0:
                return float(word.get("originalStartTime", 0) or 0)
        return None

    def last_spoken_start(clip: dict[str, Any]) -> float | None:
        for word in reversed(clip.get("words", [])):
            if word.get("type") == 0:
                return float(word.get("originalStartTime", 0) or 0)
        return None

    cursor = 0
    chunk_number = 0
    while cursor < len(clips):
        scene_id = clips[cursor].get("sceneId")
        end = cursor + 1
        previous_start = last_spoken_start(clips[cursor])
        quote_is_open = _quote_state_after(clip_caption(clips[cursor]))
        while end < len(clips) and clips[end].get("sceneId") == scene_id:
            next_start = first_spoken_start(clips[end])
            if (
                previous_start is not None
                and next_start is not None
                and next_start <= previous_start
                and not quote_is_open
            ):
                break
            quote_is_open = _quote_state_after(
                clip_caption(clips[end]),
                quote_is_open,
            )
            current_last = last_spoken_start(clips[end])
            if current_last is not None:
                previous_start = current_last
            end += 1
        group = clips[cursor:end]
        repaired, repair, skip_reason = _repair_scene(group, max_chars)
        chunk_number += 1
        group_label = f"{scene_id}:{chunk_number}"
        if repair:
            repair.scene_id = group_label
        output.extend(repaired)
        if repair:
            repairs.append(repair)
        if skip_reason:
            skipped.append(
                {
                    "sceneId": group_label,
                    "startClip": cursor + 1,
                    "endClip": end,
                    "reason": skip_reason,
                }
            )
        cursor = end

    return output, ClipRepairReport(
        original_clip_count=original_count,
        final_clip_count=len(output),
        repaired_scenes=repairs,
        skipped_scenes=skipped,
    )
