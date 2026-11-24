# -*- coding: utf-8 -*-
"""
knowledge.py · 知识库管家的核心逻辑（本 Agent 专有，手写）

三件事：
  1. 资料两分法：staging（临时素材）/ frozen（人工批准的可信基线）/ archive（归档）
  2. registry.jsonl 账本：一行一条 JSON，记录每个来源的状态与版本
  3. 人工闸门：staging → frozen 必须带 approved_by，Agent 无权自己批准

证据等级初判（保守）：
  A = 政府/监管/国家标准/同行评审文献（按 URL 与来源类型判断）
  B = 单一权威来源（WHO/NHS、行业白皮书、权威机构报告）
  C = 企业宣传、单一未交叉验证来源、无法追溯出处 —— 拿不准一律 C
"""

from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path

EVIDENCE_LEVELS = {"A": "政府/标准/同行评审，或多源交叉", "B": "单一权威来源", "C": "企业宣传或未交叉验证"}

# 判 A 的强特征
LEVEL_A_HINTS = ("pubmed", "doi.org", "europepmc", "clinicaltrials.gov",
                 ".gov", ".gov.cn", "国家标准", "国标", "standard", "guideline",
                 "指南", "论文", "学术", "同行评审")
# 判 B 的权威机构
LEVEL_B_HINTS = ("who.int", "nhs.uk", "iso.org", "ieee", "白皮书", "行业报告")
# 判 C 的企业宣传特征（优先级最高）
CORPORATE_HINTS = ("宣传", "新闻", "产品手册", "手册", "官网", "市场", "推广",
                   "发布会", "营销", "彩页")

PLACEHOLDER_APPROVERS = {"", "待定", "todo", "tbd", "无", "未知", "n/a", "none", "-"}


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def guess_level(title: str, source_type: str, url_or_path: str,
                is_corporate_material=None) -> tuple[str, str]:
    """返回 (等级, 判级理由)。企业宣传永远优先判 C。"""
    blob = " ".join([title or "", source_type or "", url_or_path or ""]).lower()

    if is_corporate_material is True or str(is_corporate_material).lower() in ("true", "1", "yes"):
        return "C", "标注为企业宣传材料（企业宣传 ≠ 证据）"
    if any(hint.lower() in blob for hint in CORPORATE_HINTS):
        return "C", "标题/类型/路径命中企业宣传特征"
    if any(hint.lower() in blob for hint in LEVEL_A_HINTS):
        return "A", "命中政府/标准/同行评审特征（仍需人工复核是否多源交叉）"
    if any(hint.lower() in blob for hint in LEVEL_B_HINTS):
        return "B", "命中单一权威机构特征"
    return "C", "无法确认权威性，按最低档 C 处理"


class KnowledgeBase(object):
    def __init__(self, kb_dir, project_root, collector_sources=None):
        self.root = Path(kb_dir)
        self.project_root = Path(project_root)
        # 注意：属性不能叫 self.archive —— 会覆盖同名方法 archive()
        self.staging_dir = self.root / "staging"
        self.frozen_dir = self.root / "frozen"
        self.archive_dir = self.root / "archive"
        self.registry_path = self.root / "registry.jsonl"
        self.collector_sources = Path(collector_sources) if collector_sources else None
        for path in (self.staging_dir, self.frozen_dir, self.archive_dir):
            path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ 账本
    def load_registry(self) -> list:
        if not self.registry_path.is_file():
            return []
        records = []
        for line in self.registry_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def _save_registry(self, records) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, "w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def find(self, source_id: str):
        for record in self.load_registry():
            if record.get("source_id") == source_id:
                return record
        return None

    def next_id(self) -> str:
        max_n = 0
        for record in self.load_registry():
            match = re.match(r"SRC(\d+)", record.get("source_id", ""))
            if match:
                max_n = max(max_n, int(match.group(1)))
        return "SRC{0:03d}".format(max_n + 1)

    # ------------------------------------------------------------ 读原文
    def _resolve_input(self, path: str) -> Path:
        """允许读采集 Agent 的 sources 与 staging；其它路径一律拒绝。"""
        candidate = Path(path)
        target = (candidate if candidate.is_absolute() else self.project_root / candidate).resolve()
        allowed = [self.staging_dir.resolve()]
        if self.collector_sources:
            allowed.append(self.collector_sources.resolve())
        if not any(target == root or str(target).startswith(str(root) + os.sep)
                   for root in allowed):
            raise PermissionError(
                "只能预处理采集产出（{0}）或 staging/ 内的文件，收到：{1}".format(
                    self.collector_sources, path))
        if not target.is_file():
            raise FileNotFoundError("文件不存在：{0}".format(path))
        return target

    @staticmethod
    def _read_text(path: Path) -> str:
        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                raise RuntimeError("预处理 PDF 需要 pypdf：pip install pypdf")
            reader = PdfReader(str(path))
            return "\n\n".join((page.extract_text() or "") for page in reader.pages)
        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _parse_meta(text: str) -> dict:
        """兼容两种写法：`- source_id: SRC001` 与 `| **来源编号** | SRC001 |`。

        W2 时期的来源卡是表格体，只认 `- key:` 会把编号与标题全部丢掉，
        退化成"文件名当标题 + 重新编号"，导致账本对不上。
        """
        aliases = {
            "source_id": ("source_id", "来源编号", "编号"),
            "title": ("title", "标题"),
            "source_type": ("source_type", "来源类型", "类型"),
            "url_or_path": ("url_or_path", "url", "文件路径", "路径"),
            "is_corporate_material": ("is_corporate_material",),
            "note": ("note", "备注"),
        }
        fields = {}
        for key, names in aliases.items():
            for name in names:
                pattern = (r"^\s*[-|*]*\s*\*{0,2}" + re.escape(name) +
                           r"\*{0,2}\s*[:：|]\s*(.+?)\s*\|?\s*$")
                match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
                if match:
                    value = match.group(1).strip().strip("*`|").strip()
                    if value:
                        fields[key] = value
                        break
        return fields

    # ------------------------------------------------------------ 预处理
    def preprocess(self, path: str, source_type: str = "") -> dict:
        """标准化一份素材并登记为 staging。只补元数据，不改写原文。"""
        target = self._resolve_input(path)
        raw = self._read_text(target)
        if not raw.strip():
            raise ValueError("原文为空，无法入库（扫描件需先 OCR）")

        meta = self._parse_meta(raw)
        source_id = meta.get("source_id") or self.next_id()
        existing = self.find(source_id)
        if existing:
            raise ValueError("{0} 已在库中（状态 {1}），未重复登记".format(
                source_id, existing.get("status")))

        title = meta.get("title") or target.stem
        kind = source_type or meta.get("source_type") or (
            "pdf" if target.suffix.lower() == ".pdf" else "doc")
        url_or_path = meta.get("url_or_path")
        if not url_or_path:
            try:
                url_or_path = str(target.relative_to(self.project_root)).replace("\\", "/")
            except ValueError:
                url_or_path = str(target)

        level, reason = guess_level(
            title, kind, url_or_path, meta.get("is_corporate_material"))

        header = "\n".join([
            "# " + title,
            "",
            "- source_id: {0}".format(source_id),
            "- title: {0}".format(title),
            "- source_type: {0}".format(kind),
            "- url_or_path: {0}".format(url_or_path),
            "- evidence_level: {0}（初判：{1}）".format(level, reason),
            "- origin_file: {0}".format(target.name),
            "- preprocessed_at: {0}".format(_now()),
            "",
            "## 原文（逐字保留，未改写）",
            "",
        ])
        out_path = self.staging_dir / "{0}.md".format(source_id)
        out_path.write_text(header + raw, encoding="utf-8")

        record = {
            "source_id": source_id,
            "title": title,
            "source_type": kind,
            "url_or_path": url_or_path,
            "evidence_level": level,
            "level_reason": reason,
            "status": "staging",
            "approved_by": "",
            "approved_at": "",
            "frozen_at": "",
            "version": 1,
            "updated_at": _now(),
            "path": str(out_path.relative_to(self.root)).replace("\\", "/"),
        }
        records = self.load_registry()
        records.append(record)
        self._save_registry(records)
        return {"record": record, "path": str(out_path),
                "note": "已登记为 staging；冻结需要人工批准"}

    # ------------------------------------------------------------ 人工闸门
    def freeze(self, source_id: str, approved_by: str) -> dict:
        """staging → frozen。没有人工批准就拒绝，Agent 不能自己批准自己。"""
        approver = (approved_by or "").strip()
        if approver.lower() in PLACEHOLDER_APPROVERS:
            raise PermissionError(
                "需要人工批准：approved_by 不能为空或是占位符（收到「{0}」）。"
                "请让负责人显式提供姓名。".format(approved_by or ""))

        records = self.load_registry()
        record = next((r for r in records if r.get("source_id") == source_id), None)
        if record is None:
            raise ValueError("registry 里没有 {0}".format(source_id))

        status = record.get("status")
        if status != "staging":
            raise PermissionError(
                "{0} 当前状态是 {1}，只有 staging 才能冻结".format(source_id, status))

        source_file = self.staging_dir / "{0}.md".format(source_id)
        if not source_file.is_file():
            raise FileNotFoundError("staging 里找不到文件：{0}".format(source_file.name))
        target_file = self.frozen_dir / "{0}.md".format(source_id)
        source_file.replace(target_file)

        now = _now()
        record.update({
            "status": "frozen",
            "approved_by": approver,
            "approved_at": now,
            "frozen_at": now,
            "version": int(record.get("version", 1)) + 1,
            "updated_at": now,
            "path": str(target_file.relative_to(self.root)).replace("\\", "/"),
        })
        self._save_registry(records)
        return {"record": record, "path": str(target_file),
                "note": "已冻结进基线库，approve_by={0}".format(approver)}

    def archive(self, source_id: str) -> dict:
        records = self.load_registry()
        record = next((r for r in records if r.get("source_id") == source_id), None)
        if record is None:
            raise ValueError("registry 里没有 {0}".format(source_id))
        if record.get("status") == "archived":
            raise ValueError("{0} 已经是 archived".format(source_id))

        moved = None
        for folder in (self.frozen_dir, self.staging_dir):
            candidate = folder / "{0}.md".format(source_id)
            if candidate.is_file():
                target = self.archive_dir / candidate.name
                candidate.replace(target)
                moved = target
                break
        if moved is None:
            raise FileNotFoundError("{0} 的文件不在 frozen/ 或 staging/".format(source_id))

        now = _now()
        record.update({
            "status": "archived",
            "version": int(record.get("version", 1)) + 1,
            "updated_at": now,
            "path": str(moved.relative_to(self.root)).replace("\\", "/"),
        })
        self._save_registry(records)
        return {"record": record, "path": str(moved), "note": "已归档"}

    # ------------------------------------------------------------ 检索
    def search(self, query: str, top_k: int = 5) -> list:
        """frozen 优先，staging 其次。返回带来源与等级的片段。"""
        terms = set()
        for run in re.findall(r"[\u4e00-\u9fff]{2,}", query or ""):
            if len(run) <= 6:
                terms.add(run)
            else:
                for index in range(len(run) - 1):
                    terms.add(run[index:index + 2])
        for word in re.findall(r"[A-Za-z]{2,}", query or ""):
            terms.add(word.lower())
        if not terms:
            return []

        records = {r["source_id"]: r for r in self.load_registry()
                   if r.get("status") in ("frozen", "staging")}
        hits = []
        for source_id, record in records.items():
            path = self.root / record.get("path", "")
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            lowered = text.lower()
            score = sum(lowered.count(term) for term in terms)
            if score <= 0:
                continue
            line = ""
            for candidate in text.splitlines():
                candidate = candidate.strip()
                if (candidate and not candidate.startswith(("#", "|", "-", ">"))
                        and len(candidate) >= 12):
                    line = candidate
                    break
            hits.append({
                "source_id": source_id,
                "title": record.get("title", ""),
                "evidence_level": record.get("evidence_level", "C"),
                "status": record.get("status"),
                "score": score,
                "snippet": line[:220],
            })
        # frozen 优先，其次按命中次数
        hits.sort(key=lambda item: (item["status"] != "frozen", -item["score"]))
        return hits[:int(top_k)]

    # ------------------------------------------------------------ 列表
    def list_sources(self, status=None) -> list:
        records = self.load_registry()
        if status:
            records = [r for r in records if r.get("status") == status]
        return records