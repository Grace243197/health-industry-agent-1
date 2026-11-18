#!/usr/bin/env python3
"""self_check.py — 项目自检脚本

按 docs/v2-gap-report.md 验收标准检查知识库状态。
用法: python tools/self_check.py [--run-id RUN_ID]
"""
import json, os, sys, re, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(ROOT, "knowledge_base")
REGISTRY = os.path.join(KB, "registry.jsonl")
TOPICS_DIR = os.path.join(KB, "topics")
CARDS_DIR = os.path.join(KB, "cards")
SOURCES_DIR = os.path.join(KB, "sources")
RUNS_DIR = os.path.join(ROOT, "runs")

REQUIRED_FIELDS = [
    "source_id", "title", "type", "publisher", "publish_date",
    "ingest_date", "url_or_path", "domain", "theme", "topics",
    "access", "evidence_level", "raw_path", "extracted_path",
    "card_path", "dedup_key", "fetch_status",
]

REQUIRED_TOPIC_PAGES = [
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


def load_registry():
    entries = []
    if not os.path.isfile(REGISTRY):
        return entries
    with open(REGISTRY, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                entries.append(obj)
            except json.JSONDecodeError:
                pass
    return entries


def is_header(e):
    return e.get("source_id") == "__header__"


def is_excluded(e):
    return e.get("excluded") is True


def is_simulated(e):
    t = e.get("type", "")
    notes = e.get("notes", "")
    return t == "simulated_material" or "模拟" in notes or "simulated" in notes.lower()


def is_duplicate(e):
    return bool(e.get("duplicate_of"))


def check_registry_fields(entries):
    results = []
    for e in entries:
        if is_header(e):
            continue
        sid = e.get("source_id", "?")
        missing = [f for f in REQUIRED_FIELDS if f not in e or e[f] in (None, "")]
        if missing:
            results.append(f"  {sid}: 缺少字段 {missing}")
    return results


def check_paths(entries):
    results = []
    for e in entries:
        if is_header(e) or is_excluded(e) or is_duplicate(e):
            continue
        sid = e.get("source_id", "?")
        for key in ("raw_path", "extracted_path", "card_path"):
            p = e.get(key)
            if p and not os.path.isfile(os.path.join(ROOT, p)):
                results.append(f"  {sid}: {key} 不存在 -> {p}")
    return results


def count_unique_real(entries):
    """唯一真实来源（排除 header, excluded, simulated, duplicate）"""
    count = 0
    sids = []
    for e in entries:
        if is_header(e) or is_excluded(e) or is_simulated(e) or is_duplicate(e):
            continue
        count += 1
        sids.append(e.get("source_id"))
    return count, sids


def count_per_direction(entries, real_sids):
    """按方向统计来源数"""
    dirs = {"RD": [], "CL": [], "AD": [], "PC": []}
    for e in entries:
        sid = e.get("source_id")
        if sid not in real_sids:
            continue
        topics = e.get("topics", [])
        for d in dirs:
            if d in topics:
                dirs[d].append(sid)
    return dirs


def count_types(entries, real_sids):
    """统计来源类型"""
    types = set()
    for e in entries:
        if e.get("source_id") in real_sids:
            types.add(e.get("type", "unknown"))
    return types


def check_topic_pages():
    results = []
    missing = []
    for tp in REQUIRED_TOPIC_PAGES:
        fp = os.path.join(TOPICS_DIR, tp)
        if not os.path.isfile(fp):
            missing.append(tp)
        else:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            # Check for unclosed HTML comments
            opens = len(re.findall(r'<!--', content))
            closes = len(re.findall(r'-->', content))
            if opens != closes:
                results.append(f"  {tp}: 未闭合注释 ({opens} open vs {closes} close)")
            # Check for duplicate verification sections
            ver_count = len(re.findall(r'##\s*核验状态', content))
            if ver_count > 1:
                results.append(f"  {tp}: 重复核验段 ({ver_count} 个)")
    return missing, results


def check_cards():
    results = []
    todo_count = 0
    no_verification = 0
    total = 0
    for e in load_registry():
        if is_header(e) or is_excluded(e) or is_duplicate(e) or is_simulated(e):
            continue
        cp = e.get("card_path")
        if not cp or not os.path.isfile(os.path.join(ROOT, cp)):
            continue
        total += 1
        with open(os.path.join(ROOT, cp), "r", encoding="utf-8") as f:
            content = f.read()
        todos = len(re.findall(r'TODO', content))
        if todos > 0:
            todo_count += 1
            results.append(f"  {e.get('source_id')}: 有 {todos} 个 TODO")
        if "核验状态" not in content and "verification_status" not in content:
            no_verification += 1
    return total, todo_count, no_verification, results


def check_run(run_id):
    results = []
    run_dir = os.path.join(RUNS_DIR, run_id)
    if not os.path.isdir(run_dir):
        return [f"  run 目录不存在: {run_id}"]
    expected = ["01_collection.json", "03_verification.json", "status.json", "role_log.jsonl"]
    for f in expected:
        if not os.path.isfile(os.path.join(run_dir, f)):
            results.append(f"  {run_id}: 缺少 {f}")
    if not os.path.isdir(os.path.join(run_dir, "02_research")):
        results.append(f"  {run_id}: 缺少 02_research/ 目录")
    return results


def main():
    run_id = None
    if "--run-id" in sys.argv:
        idx = sys.argv.index("--run-id")
        if idx + 1 < len(sys.argv):
            run_id = sys.argv[idx + 1]

    entries = load_registry()
    all_issues = []
    checks = {}

    # 1. Registry fields
    field_issues = check_registry_fields(entries)
    checks["registry_fields"] = "PASS" if not field_issues else "FAIL"
    all_issues.extend(field_issues)

    # 2. File paths
    path_issues = check_paths(entries)
    checks["file_paths"] = "PASS" if not path_issues else "FAIL"
    all_issues.extend(path_issues)

    # 3. Unique real sources
    real_count, real_sids = count_unique_real(entries)
    checks["unique_real_sources"] = "PASS" if real_count >= 30 else "FAIL"

    # 4. Per direction
    dir_counts = count_per_direction(entries, real_sids)
    dir_ok = all(len(v) >= 6 for v in dir_counts.values())
    checks["per_direction"] = "PASS" if dir_ok else "FAIL"

    # 5. Type count
    types = count_types(entries, real_sids)
    checks["type_count"] = "PASS" if len(types) >= 4 else "FAIL"

    # 6. Topic pages
    missing_topics, topic_issues = check_topic_pages()
    checks["topic_pages"] = "PASS" if not missing_topics and not topic_issues else "FAIL"
    if missing_topics:
        all_issues.append(f"  缺少主题页: {missing_topics}")
    all_issues.extend(topic_issues)

    # 7. Cards
    total_cards, todo_cards, no_verif_cards, card_issues = check_cards()
    checks["cards_no_todo"] = "PASS" if todo_cards == 0 else "FAIL"

    # 8. Run artifacts
    if run_id:
        run_issues = check_run(run_id)
        checks["run_artifacts"] = "PASS" if not run_issues else "FAIL"
        all_issues.extend(run_issues)

    # Print report
    print("=" * 60)
    print("SELF CHECK REPORT")
    print("=" * 60)
    print(f"\n唯一真实来源数: {real_count} (要求 ≥30)")
    print(f"各方向来源数:")
    for d, sids in dir_counts.items():
        status = "OK" if len(sids) >= 6 else "NEED MORE"
        print(f"  {d}: {len(sids)} [{status}] {sids}")
    print(f"来源类型数: {len(types)} (要求 ≥4) -> {types}")
    print(f"整理卡: 总计 {total_cards}, 有 TODO {todo_cards}, 无核验状态 {no_verif_cards}")
    if missing_topics:
        print(f"缺少主题页: {missing_topics}")
    print()

    overall = "PASS" if all(v == "PASS" for v in checks.values()) else "FAIL"
    print(f"总体: {overall}")
    print()
    for k, v in checks.items():
        print(f"  [{v}] {k}")

    if all_issues:
        print(f"\n问题明细:")
        for issue in all_issues:
            print(issue)

    print("=" * 60)
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
