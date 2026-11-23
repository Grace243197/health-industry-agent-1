# -*- coding: utf-8 -*-
"""
红队四例：用可判定的语料把四种 verdict 固定下来。

不联网、不调用模型，纯规则断言。跑法：
  python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from precheck import check_one, load_claims   # noqa: E402

SOURCE_TEXT = """# SRC007

Polysomnography (PSG) is the gold standard for sleep monitoring and diagnosis.

Sleep of 7 Chinese adults were recorded concurrently with PSG and LANMAO devices.

The LANMAO Sleep Recorder is a wearable single-channel EEG device for home use.
"""


class RedTeamPrecheck(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sources = Path(self.temp.name) / "sources"
        self.sources.mkdir()
        (self.sources / "SRC007_LANMAO.md").write_text(SOURCE_TEXT, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _verdict(self, statement):
        return check_one({"claim_id": "T", "statement": statement,
                          "source_ids": ["SRC007"]}, self.sources)["verdict"]

    def test_verbatim_claim_is_verified(self):
        self.assertEqual(self._verdict(
            "Polysomnography (PSG) is the gold standard for sleep monitoring and diagnosis"),
            "verified")

    def test_tampered_number_is_contradicted(self):
        """把 7 名受试者改成 700 名 —— 数字在原文里找不到，必须判 contradicted。"""
        self.assertEqual(self._verdict(
            "Sleep of 700 Chinese adults were recorded concurrently with PSG"),
            "contradicted")

    def test_unrelated_claim_is_insufficient(self):
        self.assertEqual(self._verdict(
            "The device costs 3000 yuan and holds CE certification"),
            "insufficient")

    def test_overgeneralized_claim_is_partially_supported(self):
        """把「居家单通道 EEG」说成「取代 PSG 的临床诊断」—— 过度概括。"""
        self.assertIn(self._verdict(
            "The LANMAO device replaces PSG in clinical diagnosis"),
            ("partially_supported", "insufficient"))

    def test_no_source_dir_means_insufficient(self):
        empty = Path(self.temp.name) / "empty"
        empty.mkdir()
        outcome = check_one({"claim_id": "T", "statement": "anything",
                             "source_ids": ["SRC999"]}, empty)
        self.assertEqual(outcome["verdict"], "insufficient")

    def test_json_loader_reads_w2_format(self):
        claims_dir = Path(self.temp.name) / "claims"
        claims_dir.mkdir()
        (claims_dir / "claims_demo.json").write_text(
            '[{"claim_id": "C1", "statement": "PSG 是金标准", "source_id": ["SRC007"]}]',
            encoding="utf-8")
        claims = load_claims(claims_dir)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["claim_id"], "C1")
        self.assertEqual(claims[0]["source_ids"], ["SRC007"])


if __name__ == "__main__":
    unittest.main()