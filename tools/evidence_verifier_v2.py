#!/usr/bin/env python3
"""evidence_verifier_v2.py — 真实证据核验工具

从主题页和岗位页提取关键判断（claims），对照来源原件进行文本匹配核验。

用法:
  python tools/evidence_verifier_v2.py --run-id 261117-v2-fix

核验逻辑:
  1. 从 9 个主题页 + 4 个岗位页的"关键认识"段提取 claims
  2. 解析每个 claim 引用的 source_ids
  3. 读取每个 source 的 extracted.md，按段切分
  4. 用关键词覆盖率 + difflib.SequenceMatcher 找最佳匹配段落
  5. 检查数字/单位/实体一致性
  6. 判定: supported / partially_supported / not_supported / unverifiable

输出: runs/<run_id>/03_verification.json
"""
import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
REGISTRY = KB / "registry.jsonl"
TOPICS_DIR = KB / "topics"
SOURCES_DIR = KB / "sources"

TOPIC_PAGES = [
    "RD_sensors_and_algorithms.md",
    "RD_wearables_and_technologies.md",
    "CL_psg_hsAT_workflow.md",
    "CL_professional_collaboration.md",
    "AD_service_requirements.md",
    "AD_compliance_and_quality.md",
    "PC_public_communication.md",
    "PC_evidence_and_misleading.md",
    "cross_direction_synthesis.md",
]

JOB_PAGES = [
    "job_sleep_physician.md",
    "job_sleep_technologist.md",
    "job_sleep_center_admin.md",
    "job_sleep_health_educator.md",
]

# Simulated source IDs - must not be used as evidence
SIMULATED_IDS = {"S027", "S028", "S029", "S030", "S031", "S032"}


def load_registry():
    entries = {}
    if not REGISTRY.exists():
        return entries
    with open(REGISTRY, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                sid = obj.get("source_id")
                if sid and sid != "__header__":
                    entries[sid] = obj
            except json.JSONDecodeError:
                pass
    return entries


def extract_claims_from_page(filepath):
    """从主题页/岗位页提取关键判断（claims）。"""
    if not os.path.isfile(filepath):
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    claims = []
    is_job_page = os.path.basename(filepath).startswith("job_")

    # 提取"关键认识"段
    section_match = re.search(r'##\s*关键认识\s*\n(.*?)(?=\n##\s|\Z)', content, re.DOTALL)
    if section_match:
        section = section_match.group(1)
        for line in section.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                claim_text = line[2:].strip()
                source_ids = re.findall(r'S\d{3}', claim_text)
                # Filter out simulated source IDs
                source_ids = [s for s in source_ids if s not in SIMULATED_IDS]
                flags = []
                if '会议纪要' in claim_text and '未独立核实' in claim_text:
                    flags.append('meeting_note_self_claim')
                if source_ids:
                    claims.append({
                        'text': claim_text,
                        'source_ids': list(set(source_ids)),
                        'flags': flags,
                        'page': os.path.basename(filepath),
                    })

    # 对于岗位页，提取关键判断段落
    if is_job_page and not claims:
        for section_name in ['岗位概述', '一、岗位概述', '主要工作职责', '能力要求', '岗位职责', '任职要求']:
            section_match = re.search(
                rf'^##[^\n]*{re.escape(section_name)}[^\n]*\n(.*?)(?=\n##[ \t]|\Z)',
                content, re.DOTALL | re.MULTILINE
            )
            if section_match:
                section = section_match.group(1)
                for line in section.split('\n'):
                    line = line.strip()
                    if line.startswith('- ') and len(line) > 20:
                        source_ids = re.findall(r'S\d{3}', line)
                        claims.append({
                            'text': line[2:].strip(),
                            'source_ids': list(set(source_ids)) if source_ids else [],
                            'flags': [],
                            'page': os.path.basename(filepath),
                        })

    return claims


def load_source_content(source_id, registry):
    """加载来源的 extracted.md 内容。"""
    entry = registry.get(source_id)
    if not entry:
        return None

    ext_path = entry.get("extracted_path", "")
    full_path = ROOT / ext_path if ext_path else SOURCES_DIR / source_id / "extracted.md"

    if not os.path.isfile(full_path):
        return None

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def split_into_paragraphs(text):
    """将文本按段切分。"""
    paragraphs = []
    current = []
    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append('\n'.join(current))
                current = []
        else:
            current.append(stripped)
    if current:
        paragraphs.append('\n'.join(current))
    return paragraphs


def extract_numbers(text):
    """提取文本中的数字+单位。"""
    patterns = [
        r'\d+\.?\d*\s*%',
        r'\d+\.?\d*\s*(?:ms|mmHg|bpm|kg|cm|ml|Hz|dB)',
        r'\d+\s*[-–]\s*\d+',
        r'[>≥<≤]\s*\d+\.?\d*',
    ]
    numbers = []
    for p in patterns:
        for m in re.finditer(p, text):
            numbers.append(m.group().strip())
    return numbers


def extract_keywords(text, min_len=2):
    """提取关键词。"""
    en_words = re.findall(r'[a-zA-Z]{3,}', text.lower())
    cn_chunks = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
    return set(en_words) | set(cn_chunks)


def verify_claim(claim, registry):
    """核验单个 claim。"""
    claim_text = claim['text']
    source_ids = claim['source_ids']
    page = claim['page']

    if not source_ids:
        return {
            'claim': claim_text,
            'page': page,
            'source_ids': [],
            'verdict': 'unverifiable',
            'reason': '无来源引用',
            'score': 0,
            'excerpt': '',
            'location': '',
            'flags': claim.get('flags', []),
        }

    claim_keywords = extract_keywords(claim_text)
    claim_numbers = extract_numbers(claim_text)

    best_result = None
    best_score = 0

    for sid in source_ids:
        entry = registry.get(sid)
        if not entry:
            continue

        # Skip excluded/duplicate sources
        if entry.get('excluded') or entry.get('duplicate_of'):
            continue

        content = load_source_content(sid, registry)
        if not content:
            result = {
                'claim': claim_text,
                'page': page,
                'source_ids': source_ids,
                'verdict': 'unverifiable',
                'reason': f'来源 {sid} 文件缺失或不可读',
                'score': 0,
                'excerpt': '',
                'location': '',
                'flags': claim.get('flags', []) + ['source_missing'],
            }
            if best_result is None:
                best_result = result
            continue

        is_meeting_note = entry.get('type') == 'meeting_note' or '会议纪要' in entry.get('notes', '')
        is_abstract_only = entry.get('only_abstract', False)

        paragraphs = split_into_paragraphs(content)

        best_para_idx = -1
        best_ratio = 0
        best_keyword_coverage = 0

        for i, para in enumerate(paragraphs):
            para_keywords = extract_keywords(para)
            if claim_keywords:
                coverage = len(claim_keywords & para_keywords) / len(claim_keywords)
            else:
                coverage = 0
            ratio = difflib.SequenceMatcher(None, claim_text[:200], para[:200]).ratio()
            combined = 0.6 * coverage + 0.4 * ratio

            if combined > best_ratio:
                best_ratio = combined
                best_para_idx = i
                best_keyword_coverage = coverage

        score = best_ratio
        flags = list(claim.get('flags', []))

        if is_meeting_note:
            flags.append('meeting_note_self_claim')
        if is_abstract_only:
            flags.append('abstract_only')

        number_consistent = True
        if best_para_idx >= 0 and claim_numbers:
            para_text = paragraphs[best_para_idx] if best_para_idx < len(paragraphs) else ""
            para_numbers = extract_numbers(para_text)
            for cn in claim_numbers:
                if cn not in para_text and not any(cn.replace('.', '') in pn for pn in para_numbers):
                    number_consistent = False
                    flags.append('number_mismatch')

        excerpt = ""
        location = ""
        if best_para_idx >= 0 and best_para_idx < len(paragraphs):
            excerpt = paragraphs[best_para_idx][:300]
            location = f"段落 {best_para_idx + 1}/{len(paragraphs)}"

        if score >= 0.7 and number_consistent:
            verdict = 'supported'
            reason = f'关键词覆盖率 {best_keyword_coverage:.0%}，数字/实体一致'
        elif score >= 0.4 or (score >= 0.2 and not number_consistent):
            verdict = 'partially_supported'
            reasons = []
            if best_keyword_coverage < 0.7:
                reasons.append(f'关键词覆盖率 {best_keyword_coverage:.0%}')
            if not number_consistent:
                reasons.append('数字/实体不完全一致')
            if is_meeting_note:
                reasons.append('会议纪要自述')
            if is_abstract_only:
                reasons.append('仅有摘要')
            reason = '；'.join(reasons) if reasons else f'匹配度 {score:.0%}'
        elif score < 0.2:
            verdict = 'not_supported'
            reason = f'匹配度过低 ({score:.0%})，来源中未找到支持内容'
        else:
            verdict = 'partially_supported'
            reason = f'匹配度中等 ({score:.0%})'

        result = {
            'claim': claim_text,
            'page': page,
            'source_ids': source_ids,
            'verdict': verdict,
            'reason': reason,
            'score': round(score, 3),
            'excerpt': excerpt,
            'location': location,
            'flags': flags,
            'keyword_coverage': round(best_keyword_coverage, 3),
        }

        if score > best_score:
            best_score = score
            best_result = result

    if best_result is None:
        best_result = {
            'claim': claim_text,
            'page': page,
            'source_ids': source_ids,
            'verdict': 'unverifiable',
            'reason': '所有引用来源均不可用',
            'score': 0,
            'excerpt': '',
            'location': '',
            'flags': claim.get('flags', []) + ['all_sources_missing'],
        }

    return best_result


def main():
    ap = argparse.ArgumentParser(description='证据核验工具 v2')
    ap.add_argument('--run-id', required=True, help='运行 ID')
    args = ap.parse_args()

    registry = load_registry()
    print(f"已加载 {len(registry)} 条来源记录")

    all_claims = []
    pages_processed = 0

    for page_file in TOPIC_PAGES + JOB_PAGES:
        page_path = TOPICS_DIR / page_file
        claims = extract_claims_from_page(str(page_path))
        all_claims.extend(claims)
        if claims:
            pages_processed += 1
        print(f"  {page_file}: {len(claims)} 条判断")

    print(f"\n共提取 {len(all_claims)} 条判断，来自 {pages_processed} 个页面")

    results = []
    verdict_counts = {'supported': 0, 'partially_supported': 0, 'not_supported': 0, 'unverifiable': 0}

    for i, claim in enumerate(all_claims):
        result = verify_claim(claim, registry)
        results.append(result)
        verdict_counts[result['verdict']] += 1

    print(f"\n核验结果:")
    for v, c in verdict_counts.items():
        print(f"  {v}: {c}")

    run_dir = ROOT / "runs" / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    output = {
        'run_id': args.run_id,
        'total_claims': len(all_claims),
        'pages_covered': pages_processed,
        'verdict_summary': verdict_counts,
        'results': results,
    }

    output_path = run_dir / '03_verification.json'
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n核验结果已保存: {output_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
