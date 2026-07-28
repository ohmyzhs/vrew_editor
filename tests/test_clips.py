from __future__ import annotations

import unittest

from vrew_auto_editor.clips import (
    repair_dialogue_clips,
    semantic_chunks,
    soft_character_limit,
    visible_length,
)


class SemanticChunkTests(unittest.TestCase):
    def test_separates_narration_and_dialogue(self) -> None:
        chunks = semantic_chunks(
            ["굽신거렸습니다.", '"대무녀님,', "도와주십시오.\""],
            max_chars=20,
        )
        self.assertEqual(
            chunks,
            [["굽신거렸습니다."], ['"대무녀님,', '도와주십시오."']],
        )

    def test_separates_two_speakers(self) -> None:
        chunks = semantic_chunks(
            ['"참', '곱단', '말이야."', '"그러게.', '정말', '곱네."'],
            max_chars=20,
        )
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0][-1].endswith('."'))
        self.assertTrue(chunks[1][0].startswith('"'))

    def test_long_dialogue_respects_character_limit(self) -> None:
        chunks = semantic_chunks(
            ["“당장", "저", "구렁이", "목을", "비틀어", "놔라!", "살려",
             "보냈다간", "네가", "쫓겨날", "줄", "알아라!”"],
            max_chars=20,
        )
        self.assertGreater(len(chunks), 1)
        self.assertTrue(
            all(
                visible_length(" ".join(chunk)) <= soft_character_limit(20)
                for chunk in chunks
            )
        )

    def test_keeps_short_sentences_together(self) -> None:
        chunks = semantic_chunks(
            ["아이가", "돌아왔습니다.", "마을은", "조용해졌습니다."],
            max_chars=20,
        )
        self.assertEqual(len(chunks), 1)

    def test_ignores_short_comma_marker(self) -> None:
        chunks = semantic_chunks(
            ["단,", "이", "조건은", "그대로", "둡니다."],
            max_chars=20,
        )
        self.assertEqual(chunks, [["단,", "이", "조건은", "그대로", "둡니다."]])

    def test_ignores_short_vocative_before_comma(self) -> None:
        chunks = semantic_chunks(
            ['"대무녀님,', "도와주십시오.\""],
            max_chars=20,
        )
        self.assertEqual(chunks, [['"대무녀님,', '도와주십시오."']])

    def test_uses_meaningful_comma_as_boundary(self) -> None:
        chunks = semantic_chunks(
            [
                "겨우",
                "열",
                "살",
                "난",
                "딸아이가",
                "끌려",
                "나갔고,",
                "여윈",
                "손목에는",
                "밧줄",
                "자국이",
                "남았습니다.",
            ],
            max_chars=20,
        )
        self.assertEqual(chunks[0][-1], "나갔고,")
        self.assertEqual(chunks[1][0], "여윈")

    def test_keeps_short_intro_comma_with_following_words(self) -> None:
        chunks = semantic_chunks(
            [
                "그럼",
                "지금부터,",
                "종으로",
                "팔려간",
                "아이가",
                "십",
                "년",
                "만에",
                "돌아온",
                "이야기를",
                "시작합니다.",
            ],
            max_chars=20,
        )
        self.assertNotEqual(chunks[0], ["그럼", "지금부터,"])

    def test_keeps_short_dialogue_punctuation_within_tolerance(self) -> None:
        cases = [
            ['"네가', "어디서", "왔든,", "오늘부터", "내", '딸이다."'],
            ['"이', "손", "놓아라!", "내", "딸이다,", "내", "딸이란", '말이다!"'],
            ['"마침', "잘됐군.", "능주", "포목전에서", "사람을", '구한다더라."'],
        ]
        for tokens in cases:
            with self.subTest(tokens=tokens):
                chunks = semantic_chunks(tokens, max_chars=20)
                self.assertNotIn(
                    tokens[0:2],
                    chunks,
                )
                self.assertTrue(
                    all(
                        visible_length(" ".join(chunk))
                        <= soft_character_limit(20)
                        for chunk in chunks
                    )
                )

    def test_allows_ten_percent_character_tolerance(self) -> None:
        tokens = ["가나다라마바사아자차", "카타파하거너더러머버", "서"]
        self.assertEqual(visible_length(" ".join(tokens)), 21)
        self.assertEqual(semantic_chunks(tokens, max_chars=20), [tokens])

    def test_reflows_open_quote_across_tts_time_reset(self) -> None:
        def clip(
            clip_id: str,
            caption: str,
            words: list[str],
        ) -> dict:
            return {
                "id": clip_id,
                "sceneId": "scene",
                "words": [
                    {
                        "id": f"{clip_id}-{index}",
                        "text": word,
                        "type": 0,
                        "duration": 0.5,
                        "originalDuration": 0.5,
                        "originalStartTime": index * 0.5,
                        "assetIds": [f"asset-{clip_id}-{index}"],
                    }
                    for index, word in enumerate(words)
                ],
                "captions": [
                    {"text": [{"insert": caption + "\n"}]},
                    {"text": [{"insert": "\n"}]},
                ],
            }

        source = [
            clip("a", "“마침 잘됐군.", ["마침", "잘됐군."]),
            clip(
                "b",
                "능주 포목전에서 계집아이 하나를 구한다더니.”",
                ["능주", "포목전에서", "계집아이", "하나를", "구한다더니."],
            ),
        ]
        repaired, report = repair_dialogue_clips(source, max_chars=20)
        captions = [
            " ".join(
                block["insert"].strip()
                for caption in item["captions"]
                for block in caption["text"]
                if block["insert"].strip()
            )
            for item in repaired
        ]
        self.assertTrue(report.changed)
        self.assertNotEqual(captions[0], "“마침 잘됐군.")
        self.assertEqual(
            [
                word["id"]
                for item in repaired
                for word in item["words"]
                if word["type"] == 0
            ],
            ["a-0", "a-1", "b-0", "b-1", "b-2", "b-3", "b-4"],
        )

    def test_keeps_closed_quote_speakers_separate_at_same_start(self) -> None:
        source = []
        for clip_id, caption, words in [
            ("a", "“아버지!”", ["아버지!"]),
            (
                "b",
                "“이 손 놓아라! 내 딸이다, 내 딸이란 말이다!”",
                ["이", "손", "놓아라!", "내", "딸이다,", "내", "딸이란", "말이다!"],
            ),
        ]:
            source.append(
                {
                    "id": clip_id,
                    "sceneId": "scene",
                    "words": [
                        {
                            "id": f"{clip_id}-{index}",
                            "text": word,
                            "type": 0,
                            "duration": 0.5,
                            "originalDuration": 0.5,
                            "originalStartTime": index * 0.5,
                            "assetIds": [f"asset-{clip_id}-{index}"],
                        }
                        for index, word in enumerate(words)
                    ],
                    "captions": [
                        {"text": [{"insert": caption + "\n"}]},
                        {"text": [{"insert": "\n"}]},
                    ],
                }
            )

        repaired, _ = repair_dialogue_clips(source, max_chars=20)
        captions = [
            item["captions"][0]["text"][0]["insert"].strip()
            for item in repaired
        ]
        self.assertEqual(captions[0], "“아버지!”")
        self.assertTrue(captions[1].startswith("“이 손 놓아라!"))

    def test_never_splits_inside_a_word(self) -> None:
        tokens = ["가느다란", "울음소리를", "들었습니다."]
        chunks = semantic_chunks(tokens, max_chars=8)
        self.assertEqual([token for chunk in chunks for token in chunk], tokens)

    def test_does_not_break_after_genitive_particle(self) -> None:
        chunks = semantic_chunks(
            [
                "대감댁",
                "마름의",
                "호통에",
                "소작농의",
                "집",
                "마당이",
                "얼어붙었습니다.",
            ],
            max_chars=20,
        )
        self.assertFalse(any(chunk[-1].endswith("의") for chunk in chunks[:-1]))

    def test_uses_tts_pause_as_preferred_boundary(self) -> None:
        tokens = [
            "봉출은",
            "대감댁",
            "논일을",
            "마치고",
            "돌아오던",
            "길에",
            "개울가에서",
            "들었습니다.",
        ]
        pauses = [0, 0, 0, 1.1, 0, 0, 0, 0]
        chunks = semantic_chunks(tokens, max_chars=20, pause_after=pauses)
        self.assertEqual(chunks[0][-1], "마치고")


if __name__ == "__main__":
    unittest.main()
