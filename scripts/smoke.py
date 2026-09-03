#!/usr/bin/env python3
"""종합 스모크 테스트 — 데이터·엔진 변경 후 1회 실행으로 회귀 검증.
사용: python3 scripts/smoke.py  (전부 OK면 종료코드 0)
이 세션(라운드㊸~64)에서 실제로 잡았던 결함 유형들을 자동 검사로 영구화한 것.
"""
import json, os, re, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
fails = []

def check(name, ok, detail=''):
    print(('  OK ' if ok else 'FAIL ') + name + (f' — {detail}' if detail else ''))
    if not ok: fails.append(name)

rows = json.load(open(f'{ROOT}/data/db/results_unified.json'))['rows']

# 1. 데이터 무결
check('행수 하한', len(rows) >= 15500, f'{len(rows)}행')
bad_paren = [r for r in rows if r.get('모집단위') and r['모집단위'].count('(') != r['모집단위'].count(')')
             and not r['모집단위'].startswith('(구)')]
check('모집단위 괄호 균형', not bad_paren, f'{len(bad_paren)}건')
agg = [r for r in rows if re.match(r'^(소계|합계|총계|계)(\(|$)', (r.get('모집단위') or '').strip())]
check('집계행 없음', not agg, f'{len(agg)}건')
oob = [r for r in rows if r.get('성적지표') == '수능백분위'
       and ((r.get('백분위_평균') or 0) > 100 or (r.get('백분위_최저') or 0) > 100)]
check('백분위 척도(≤100)', not oob, f'{len(oob)}건')
hdr = [r for r in rows if re.match(r'^(컷|최저|최고|평균|등급|충원|경쟁|cut|Cut)', (r.get('모집단위') or ''))]
check('모집단위 헤더 잔재 없음', not hdr, f'{len(hdr)}건')
mis = [r for r in rows if r['모집시기'] == '수시' and re.search(r'정시|수능\(|수능위주', r['전형명'] or '')]
check('모집시기 교차 오등록 없음', not mis, f'{len(mis)}건')

# 2. 유사중복(값 충돌) — 알려진 저위험 잔여 5키 이하 유지
key = collections.defaultdict(list)
for r in rows:
    key[(r['대학'], r['학년도'], r['모집시기'], r['전형명'], r.get('모집단위'))].append(r)
from engine.diagnose import SPECIAL, NON_ACADEMIC
dups = [k for k, v in key.items() if len(v) > 1
        and not SPECIAL.search(k[3] or '') and not NON_ACADEMIC.search(k[3] or '')]
check('노출 가능 유사중복 ≤5키', len(dups) <= 5, f'{len(dups)}키')

# 3. 엔진 회귀
from engine.diagnose import Student, diagnose
def n_cards(res): return sum(1 for m in res['matches'] if m['판정'] in ('안정','적정','도전','상향'))
base = diagnose(Student(naesin=3.5, sat={'국어':4,'수학':4,'영어':4,'탐구':4}, region='서울', major='경영'))
check('경영 3.5 기준 진단', n_cards(base) > 300 and len(base['tracks']) > 150,
      f"카드 {n_cards(base)}, 전형 {len(base['tracks'])}, 정시 {len(base['jeongsi'])}")
# 면허 가드: 약칭 입력에 자유전공 광역 카드가 나오면 안 됨
for kw in ('약대', '의대', '수의예', '한의대'):
    r = diagnose(Student(naesin=2.0, sat={'국어':2,'수학':2,'영어':2,'탐구':2}, region='서울', major=kw))
    broad = sum(1 for m in r['matches'] if m.get('광역') and m['판정'] in ('안정','적정','도전','상향'))
    check(f'면허 가드({kw})', broad == 0 and n_cards(r) > 0, f'실매치 {n_cards(r)}, 광역 {broad}')
# 여대 필터
male = diagnose(Student(naesin=2.0, sat={'국어':2,'수학':2,'영어':2,'탐구':2}, region='서울', major='경영', gender='남'))
w = [m for m in male['matches'] if m['대학'] in ('ewha','sookmyung','swu','smwu','sungshin','dongduk','duksung')]
check('남학생 여대 제외', not w, f'{len(w)}건')
# 정시: kw·ajou 카드 존재(과거 누락 버그 재발 감지)
js_unis = set(j['대학'] for j in base['jeongsi'])
check('정시 kw·ajou 매칭', 'kw' in js_unis and 'ajou' in js_unis, str(sorted(js_unis)))

# 4. 학종 파서 회귀
from engine.hakjong import parse, 제도필터
t = ('자율활동: 자율동아리 코딩반 운영.\n봉사활동: 개인봉사활동 24시간.\n'
     '수상경력: 교내 금상.\n독서활동상황: 12권.\n세부능력 및 특기사항: 발표 주도.')
warns = 제도필터(parse(t))
tags = set(w['태그'] for w in warns)
check('학생부 경고 4종', {'자율동아리','개인봉사','수상경력','독서상황'} <= tags, str(sorted(tags)))

print()
if fails:
    print(f'실패 {len(fails)}건: {fails}'); sys.exit(1)
print('전부 통과')
