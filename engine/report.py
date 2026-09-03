#!/usr/bin/env python3
"""대입네비 진단 리포트 출력기 v1 — diagnose() 결과 → 학생용 마크다운 한 장 보고서
사용: python3 engine/report.py  (샘플: 경영 3.2 인천)
     또는 from engine.report import render; md = render(diagnose(student))
"""
import json, os, sys
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from engine.diagnose import Student, diagnose

NAMES = json.load(open(f'{BASE}/data/db/univ_names.json'))

ORDER = ['안정', '적정', '도전', '상향']
DESC = {
    '안정': '작년 합격선이 내 성적보다 0.4등급 이상 낮았던 곳 — 백테스트상 이듬해에도 합격권 유지 약 89%',
    '적정': '작년 합격선이 내 성적과 비슷한 곳 — 주력 지원선(이듬해 합격권 유지 약 75%)',
    '도전': '작년 합격선이 내 성적보다 다소 높았던 곳(0.35 이내) — 유지율 약 33%, 서류·면접으로 승부',
    '상향': '작년 합격선이 내 성적보다 크게 높았던 곳 — 소신 지원(유지율 약 13%)',
}

def _dedup_latest(matches):
    """같은 (대학,전형,모집단위)는 최신 학년도만"""
    best = {}
    for m in matches:
        k = (m['대학'], m['전형명'], m['모집단위'])
        if k not in best or m['학년도'] > best[k]['학년도']:
            best[k] = m
    return list(best.values())

def render(result, top_n=12):
    s = result['student']
    tracks = result['tracks']
    matches = _dedup_latest(result['matches'])
    sat_txt = ' / '.join(f"{k} {v}등급" for k, v in s.sat.items())
    n_uni = len(set(t['대학'] for t in tracks))

    L = []
    L.append(f"# 대입 진단 리포트")
    L.append("")
    L.append(f"**프로필** · 내신 {s.naesin}등급 · 수능(예상) {sat_txt} · {s.region} 거주 · **{s.major}** 계열 희망")
    L.append("")
    L.append("## 1. 지원 자격 진단")
    hold = sum(1 for t in tracks if t.get('최저보류'))
    L.append(f"- 전국 전형 DB 대조 결과, 일반전형 기준 **{n_uni}개 대학 {len(tracks)}개 전형**에 지원 자격이 있습니다.")
    L.append(f"- 수능최저학력기준: 예상 등급으로 자동 판정한 결과 위 전형 모두 충족 가능합니다."
             + (f" (기준이 복잡해 수동 확인이 필요한 전형 {hold}건은 별도 표시)" if hold else ""))
    L.append(f"- 지역인재 전형은 {s.region} 거주 기준으로 자격이 없는 전형을 제외했습니다.")
    holds = [t for t in tracks if t.get('최저보류')]
    if holds:
        L.append("")
        L.append("<details><summary>⚠️ 수능최저 수동 확인 필요 전형 (펼쳐보기)</summary>")
        L.append("")
        L.append("| 대학 | 전형 | 기준(요약) |")
        L.append("|---|---|---|")
        for t in holds[:20]:
            why = t['최저판정'].replace('수동 확인: ', '')
            L.append(f"| {NAMES.get(t['대학'], t['대학'])} | {t['전형명'][:18]} | {why[:38]} |")
        L.append("")
        L.append("</details>")
    L.append("")
    L.append("## 2. 작년 입시결과 기반 판정")
    L.append("")
    grouped = defaultdict(list)
    for m in matches:
        j = m['판정']
        if j in ORDER: grouped[j].append(m)
    for j in ORDER:
        rows = grouped.get(j, [])
        if not rows: continue
        # 안정: 내 성적에 가까운(컷 낮은) 순 = 상위 대학 우선 / 나머지: 컷 높은 순
        if j == '안정':
            rows = [r for r in rows if (r['컷'] or 0) <= 6.5]  # 정원미달성 비정상 컷 제외
            rows.sort(key=lambda x: (x['컷'] or 9))
        else:
            rows.sort(key=lambda x: (-(x['컷'] or 0)))
        # 같은 대학 편중 완화: 표에는 대학당 최대 2곳(잔여는 '외 N곳'에 포함)
        capped, seen_uni = [], {}
        for r in rows:
            c = seen_uni.get(r['대학'], 0)
            if c < 2:
                capped.append(r); seen_uni[r['대학']] = c + 1
        overflow = len(rows) - len(capped)
        rows = capped
        L.append(f"### {'🟢🟡🟠🔴'[ORDER.index(j)]} {j} ({len(rows)}곳) — {DESC[j]}")
        L.append("")
        L.append("| 대학 | 전형 | 모집단위 | 작년 합격선 | 경쟁률 |")
        L.append("|---|---|---|---|---|")
        for m in rows[:top_n]:
            uni = NAMES.get(m['대학'], m['대학'])
            cut = f"{m['컷']}" + (" ᵇ" if m.get('광역') else "") \
                + (" ⚡" if m.get('컷변동') is not None and abs(m['컷변동']) >= 0.7 else "")
            gy = f"{round(m['경쟁률'],1)}:1" if m.get('경쟁률') else '-'
            jh = m['전형명'] if len(m['전형명']) <= 18 else m['전형명'][:17] + '…'
            mu2 = m['모집단위'] if len(m['모집단위']) <= 18 else m['모집단위'][:17] + '…'
            L.append(f"| {uni} | {jh} | {mu2} | {cut} | {gy} |")
        if len(rows) > top_n:
            L.append(f"| … | | 외 {len(rows)-top_n}곳 | | |")
        L.append("")
    nonsul = [m for m in matches if m['판정'] == '논술(등급참고)']
    if nonsul:
        uni_list = sorted(set(NAMES.get(m['대학'], m['대학']) for m in nonsul))
        L.append(f"### ✏️ 논술 전형 ({len(uni_list)}개 대학 {len(nonsul)}건)")
        L.append("논술은 논술고사 성적으로 선발하므로 내신 합격선은 참고용입니다. "
                 "내신 부담 없이 지원할 수 있는 카드입니다.")
        L.append("대상: " + ', '.join(uni_list))
        L.append("")
    jz = result.get('jeongsi') or []
    if jz:
        best = {}
        for m in jz:
            k = (m['대학'], m['전형명'], m['모집단위'])
            if k not in best or m['학년도'] > best[k]['학년도']:
                best[k] = m
        jrows = sorted(best.values(), key=lambda x: -(x['작년백분위'] or 0))
        good = [m for m in jrows if m['판정'] in ('적정', '도전')]
        L.append(f"## 3. 정시(수능) 참고 판정")
        L.append(f"예상 수능 등급을 백분위로 근사(국·수·탐 평균 {jz[0]['내백분위']})해 "
                 f"정시 입결과 대조한 참고 자료입니다. 등급→백분위 근사에는 오차가 있습니다.")
        L.append("")
        L.append("| 대학 | 전형 | 모집단위 | 작년 백분위(평균) | 판정 |")
        L.append("|---|---|---|---|---|")
        # 대학당 최대 2건(도배 방지), 적정·도전 우선 → 부족하면 안정 → 상향 순으로 채움
        pri = {'적정': 0, '도전': 1, '안정': 2, '상향': 3}
        cand = sorted(jrows, key=lambda x: (pri.get(x['판정'], 9), -(x['작년백분위'] or 0)))
        show, per_uni = [], {}
        for m in cand:
            if per_uni.get(m['대학'], 0) >= 2: continue
            per_uni[m['대학']] = per_uni.get(m['대학'], 0) + 1
            show.append(m)
            if len(show) >= 10: break
        for m in show:
            uni = NAMES.get(m['대학'], m['대학'])
            jh = m['전형명'] if len(m['전형명']) <= 16 else m['전형명'][:15] + '…'
            mu = m['모집단위'] if len(m['모집단위']) <= 16 else m['모집단위'][:15] + '…'
            L.append(f"| {uni} | {jh} | {mu} | {m['작년백분위']} | {m['판정']} |")
        L.append("")
    # 4. 학종 평가요소 안내 — 지원권 대학 중 요소·비율 공표 대학
    try:
        from engine.hakjong import CRITERIA
        my_unis = set(m['대학'] for m in result['matches'] if '종합' in m['전형명'] or '인재' in m['전형명'])
        crits = [c for c in CRITERIA if c['university_id'] in my_unis and c.get('요소') and c['요소'][0].get('비율')]
    except Exception:
        crits = []
    if crits:
        L.append("## 4. 학생부종합 평가요소 (지원권 대학 공표 비율)")
        L.append("아래 대학은 요강에 학종 평가요소 비율을 공표했습니다. "
                 "세특·활동 보완의 우선순위를 정할 때 참고하세요.")
        L.append("")
        L.append("| 대학 | 전형 | 단계 | 평가요소 |")
        L.append("|---|---|---|---|")
        for c in crits[:14]:
            els = ' · '.join(f"{e['명']} {e['비율']}%" for e in c['요소'])
            jh = c.get('전형', '')
            if jh.startswith('미상'): jh = '학생부종합(공통)'
            jh = jh if len(jh) <= 20 else jh[:19] + '…'
            L.append(f"| {NAMES.get(c['university_id'], c['university_id'])} | {jh} | {c.get('단계','')} | {els} |")
        L.append("")
    L.append("---")
    L.append("ᵇ 광역/자유전공 모집단위 — 입학 후 해당 전공 선택 가능한 단위의 합격선입니다.")
    L.append("")
    L.append("⚡ 변동 주의 — 이 전형·학과의 합격선이 직전 연도 대비 0.7등급 이상 움직였습니다. "
             "자체 분석(연도 쌍 3,169건) 결과 합격선의 연간 변동은 표준편차 ±0.7등급 수준으로, "
             "'안정' 판정도 확정 합격을 뜻하지 않습니다.")
    L.append("")
    L.append("> **데이터 출처**: 각 대학 입학처가 공식 발표한 전년도 입시결과 및 2027학년도 모집요강 "
             "(수집일 기준 최신본). 합격선은 대학마다 산출 기준(50%/70%컷·평균, 반영교과)이 달라 "
             "단순 비교에는 한계가 있으며, 실제 지원 시 반드시 해당 대학 요강을 확인하세요. "
             "판정별 유지율은 자체 백테스트(2025년 합격선 기준 판정을 2026년 실제 합격선과 대조, "
             "전형·학과 1,797쌍×성적 시나리오) 결과입니다.")
    return '\n'.join(L)

if __name__ == '__main__':
    st = Student(naesin=3.2, sat={'국어':3,'수학':4,'영어':2,'탐구':4}, region='인천', major='경영')
    md = render(diagnose(st))
    out = f'{BASE}/output/sample_report_경영_3.2_인천.md'
    os.makedirs(f'{BASE}/output', exist_ok=True)
    open(out, 'w', encoding='utf-8').write(md)
    print(md[:2000])
    print(f"\n... 저장: {out} ({len(md)}자)")
