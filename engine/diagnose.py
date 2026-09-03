#!/usr/bin/env python3
"""대입네비 진단 엔진 v1
학생 프로필(내신·수능등급·지역·희망학과) → 지원 가능 전형 + 입결 대조 판정.

사용:
  from engine.diagnose import Student, diagnose
  s = Student(naesin=3.2, sat={'국어':3,'수학':4,'영어':2,'탐구':4}, region='인천', major='경영')
  report = diagnose(s)
"""
import json, glob, re, os
from dataclasses import dataclass, field

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = f'{BASE}/data/db'

# ---------------- 학생 ----------------
@dataclass
class Student:
    naesin: float                      # 내신 평균 등급
    sat: dict                          # {'국어':3,'수학':4,'영어':2,'탐구':4}
    region: str = ''                   # 거주/고교 지역 (시도명)
    major: str = ''                    # 희망 학과 키워드
    math_choice: str = ''              # '미적분'|'기하'|'확률과통계'
    gender: str = ''                   # '남'|'여'|''(미상) — 여대 필터용
    def grades_sorted(self):
        return sorted(self.sat.values())
    def best_sum(self, n):
        return sum(self.grades_sorted()[:n])

# ---------------- 지역인재 권역 ----------------
REGION_ZONE = {
    '부산':'부울경','울산':'부울경','경남':'부울경','창원':'부울경','김해':'부울경',
    '대구':'대구경북','경북':'대구경북','안동':'대구경북',
    '광주':'호남','전남':'호남','전북':'전북','전주':'전북',
    '대전':'충청','세종':'충청','충남':'충청','충북':'충청','천안':'충청','아산':'충청',
    '강원':'강원','춘천':'강원','원주':'강원','강릉':'강원',
    '제주':'제주',
    '서울':'수도권','인천':'수도권','경기':'수도권','수원':'수도권',
}
# 전형명/비고에 이 키워드가 있으면 해당 권역 전용
ZONE_PAT = {
    '부울경': r'부산|울산|경남|부울경|동남권',
    '대구경북': r'대구|경북(?!대)|안동',
    '호남': r'호남|광주(?!교)|전남',
    '전북': r'전북',
    '충청': r'충청|충남|충북|대전|세종',
    '강원': r'강원',
    '제주': r'제주',
}
UNIV_ZONE = json.load(open(f'{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}/data/db/univ_zone.json'))
REGIONAL_HINT = re.compile(r'지역인재|강원인재|지역균형(?!선발\(수도권\))|지역의사|지역의료|지역교과|지역종합|지역전형|지역학생|지역Ⅰ|지역Ⅱ|지역I|지역\[|글로컬인재|교육감|충남형|충청형|캠퍼스인재|혜화')
SPECIAL = re.compile(r'농어촌|특성화|기회균형|배려|기초|장애|만학도|평생|성인|재직|보훈|다문화|사회통합|사회배려|사회적배려|특수교육|취업자|북한|재외|검정|군사|선수|추천서필요|저소득|수급|차상위|한부모|고른기회|국가안보|사회기여|서해5도|지역인재\(저\)|조기취업형|계약학과')
NON_ACADEMIC = re.compile(r'체육|특기|실기|예체능|미술|음악|무용|공연|디자인실기')
WOMEN_UNIV = {'smwu','swu','sungshin','dongduk','duksung','ewha','seoulwomen'}  # 여자대학 — 남학생 지원 불가

# ---------------- 수능최저 파서 ----------------
def parse_min_requirement(crit: str, student: Student):
    """최저 기준 텍스트 → (충족여부 True/False/None, 설명). None=수동 확인 필요"""
    if not crit or not isinstance(crit, str): return None, '기준 없음'
    c = crit.replace(' ', '')
    if any(k in c for k in ('미적용','없음','면제')) and not re.search(r'\d개영역', c): return True, '최저 없음'
    # 의약 계열 한정 문구 → 일반 학과는 통과
    if re.search(r'(의예|의학|약학|치의|한의|수의|간호|의약)[^0-9]{0,8}(만|의경우|:)', c) and student.major and not re.search(r'의예|의학|약학|치의|한의|간호', student.major):
        return True, '의약계열 한정 최저 — 해당 없음'
    # 주간/야간 병기 시 첫 기준(주간) 사용
    c = c.split('/야간')[0]
    m = re.search(r'(\d)개(?:영역)?(?:중)?[^0-9]{0,8}?평균\s*(\d)등급', c)
    if m:
        n, lim = int(m.group(1)), int(m.group(2))
        got = student.best_sum(n) / n
        return got <= lim + 0.001, f'{n}개 평균 {lim}등급 (학생 {round(got,1)})'
    m = re.search(r'(\d)개(?:영역)?(?:의)?[^0-9]{0,10}?합(?:이|은|산)?\s*(\d+)', c)
    if m:
        n, lim = int(m.group(1)), int(m.group(2))
        got = student.best_sum(n)
        return got <= lim, f'{n}개 합 {lim} (학생 {got})'
    m = re.search(r'(\d)개영역(?:등급이)?(\d)등급', c)
    if m:
        got = student.grades_sorted()[0]
        return got <= int(m.group(2)), f'1개 영역 {m.group(2)}등급 (학생 최고 {got})'
    return None, f'수동 확인: {crit[:40]}'

# ---------------- 지역인재 자격 ----------------
def regional_eligible(name: str, bigo: str, student: Student, univ: str = ''):
    """(전형이 지역제한인지, 학생이 자격 있는지). 권역 미상이면 대학 소재 권역으로 폴백"""
    text = f'{name} {bigo}'
    if not REGIONAL_HINT.search(text): return False, True
    # 수도권 대학의 '지역균형'은 학교장추천 전국형(중앙대 등) — 지역 제한 아님
    if '지역균형' in name and UNIV_ZONE.get(univ) == '수도권' and not re.search(r'비수도권|수도권외', name):
        return False, True
    zone = REGION_ZONE.get(student.region, '')
    # 요구 권역이 '호남'이면 전북 학생도 자격(호남권=광주·전남·전북)
    ok = lambda req: zone == req or (req == '호남' and zone == '전북')
    # 권역 판정은 전형명에서만(비고는 설명문 노이즈), 없으면 대학 소재 권역
    for z, pat in ZONE_PAT.items():
        if re.search(pat, name):
            return True, ok(z)
    uz = UNIV_ZONE.get(univ)
    if uz: return True, ok(uz)
    return True, None

# ---------------- 학과 매칭 ----------------
# 자유 입력 → 사전 키 정규화(약칭·구어체). 면허 가드가 원문 입력에 우회되지 않게 하는 1차 관문.
MAJOR_ALIAS = {
    '약대': '약학', '의대': '의예', '의학과': '의예', '치대': '치의', '치의예': '치의',
    '한의대': '한의', '한의예': '한의', '수의예': '수의', '수의학': '수의', '수의대': '수의',
    '컴공': '컴퓨터', '소프트웨어': '컴퓨터', '국문과': '국어국문', '국문': '국어국문',
    '영문과': '영어', '영문': '영어', '수교': '수학교육', '화공': '화학', '전자공학': '전기전자',
    '전기공학': '전기전자', '전전': '전기전자', '체대': '체육', '간호학과': '간호', '간호학': '간호',
    '유교과': '유아교육', '사복': '사회복지', '경찰행정': '경찰', '기계공학': '기계',
}

MAJOR_SYNONYM = {
    '경영': r'경영(?!정보통신)', '경제': r'경제|금융(?!보험)', '간호': r'간호',
    '컴퓨터': r'컴퓨터|소프트웨어|SW|인공지능|AI(?![A-Za-z])|정보보호|데이터',
    '기계': r'기계|메카|모빌리티|자동차', '전기전자': r'전기|전자(?!상거래)',
    '화학': r'화학|화공', '심리': r'심리', '미디어': r'미디어|신문방송|커뮤니케이션|언론',
    '행정': r'행정(?!사)', '법': r'법학|법률', '영어': r'영어|영문',
    '물리치료': r'물리치료', '유아교육': r'유아교육', '사회복지': r'사회복지|복지',
    '건축': r'건축', '식품영양': r'식품영양|영양',
    '의예': r'의예|의학과', '약학': r'약학(?!대학원)', '수의': r'수의', '치의': r'치의',
    '한의': r'한의', '국어국문': r'국어국문|국문학|문예창작', '수학': r'수학',
    '물리': r'물리(?!치료)', '생명': r'생명|바이오(?!메디컬헬스)', '통계': r'통계',
    '토목': r'토목|건설(?!환경공학과$)', '환경': r'환경(?!조경)', '반도체': r'반도체',
    '항공': r'항공', '임상병리': r'임상병리', '방사선': r'방사선', '치위생': r'치위생',
    '작업치료': r'작업치료', '응급구조': r'응급구조', '호텔관광': r'호텔|관광',
    '광고홍보': r'광고|홍보', '회계': r'회계|세무', '부동산': r'부동산',
    '체육': r'체육|스포츠', '역사': r'사학과|역사', '철학': r'철학',
    '정치외교': r'정치외교|정치|외교', '사회학': r'사회학', '무역': r'무역|국제통상|국제상학',
    '소방': r'소방', '경찰': r'경찰', '데이터': r'데이터|빅데이터|통계', '수학교육': r'수학교육',
}
# 광역/계열 모집단위 → 포함 전공 키워드(그 안에서 전공 선택 가능)
BROAD_UNITS = {
    r'자유전공|자율전공|미래융합학부|상상력인재|창의융합학부|아너스|글로벌인재': '*',  # 전 계열
    r'미래융합사회과학|사회과학(대학|학부|계열)|인문사회.*(계열|학부)': '경영 경제 행정 법 심리 미디어 사회복지',
    r'경영(계열|대학|학부)|경상(계열|대학)': '경영 경제',
    r'공학(계열|1|2|3)|공과(대학|계열)|IT공과': '기계 전기전자 화학 컴퓨터 건축',
    r'SW융합|소프트웨어(계열|융합|대학)|IT(융합)?(계열|대학|학부)|컴퓨터(공학)?학부|AI컴퓨터': '컴퓨터',
    r'간호(대학|학부)': '간호',
    r'보건(계열|과학대학)': '물리치료 간호 식품영양',
}
def major_match(mu: str, keyword: str):
    if not mu or not keyword: return False
    pat = MAJOR_SYNONYM.get(keyword)
    if pat and re.search(pat, mu): return True
    if not pat and keyword in mu: return True
    LICENSED = {'의예','약학','수의','치의','한의','간호','물리치료','임상병리','방사선','치위생','작업치료','응급구조','유아교육','수학교육'}
    # '수의예'·'치의예' 같은 직접 입력도 면허 가드에 걸리도록 부분 포함 검사(사전 키 정확 일치만으론 우회됨)
    is_licensed = any(l in keyword for l in LICENSED)
    for bp, kws in BROAD_UNITS.items():
        if re.search(bp, mu):
            if kws == '*' and not is_licensed: return 'broad'
            if kws != '*' and keyword in kws.split(): return 'broad'
    return False

# ---------------- 판정 ----------------
def judge(cut, naesin):
    if cut is None: return None
    d = cut - naesin
    if d >= 0.4: return '안정'
    if d >= 0.05: return '적정'
    if d >= -0.35: return '도전'
    return '상향'

# 경영·인문 없는 특수대학
NO_GENERAL = {'bnue','cnue','cue','cje','dnue','gjue','ginue','jnue','knsu','gnue','snue'}

def eligible_tracks(student: Student):
    """전형 DB 전체에서 학생이 지원 가능한 일반 전형 목록"""
    out = []
    for f in sorted(glob.glob(f'{DB}/admissions_*_2027.json')):
        j = json.load(open(f)); uid = j['university_id']
        if uid in NO_GENERAL and '초등' not in (student.major or ''): continue
        if uid in WOMEN_UNIV and student.gender == '남': continue
        for a in j['admissions']:
            name = a.get('전형명') or ''; big = a.get('전형대분류') or ''
            if big not in ('학생부교과', '학생부종합'): continue
            if SPECIAL.search(name) or NON_ACADEMIC.search(name): continue
            bigo = str(a.get('비고') or '')
            is_reg, ok_reg = regional_eligible(name, bigo, student, uid)
            if is_reg and ok_reg is False: continue
            mj = a.get('수능최저') or {}
            if not mj.get('적용여부'):
                ok_min, why = True, '최저 없음'
            else:
                ok_min, why = parse_min_requirement(mj.get('기준'), student)
            if ok_min is False: continue
            try: method = ' + '.join(f"{e['name']}{e['배점']}" for e in a['rules'][0]['요소'])
            except Exception: method = ''
            out.append({'대학': uid, '전형명': name, '유형': big, '단계': len(a.get('rules', [])),
                        '방법': method[:40], '최저판정': why,
                        '최저보류': ok_min is None, '지역미상': is_reg and ok_reg is None})
    return out

def match_results(student: Student, years=(2025, 2026)):
    """통합 입결에서 희망 학과 행 추출 + 판정"""
    u = json.load(open(f'{DB}/results_unified.json'))
    out = []
    for r in u['rows']:
        if r['학년도'] not in years or r['모집시기'] != '수시': continue
        if r['대학'] in WOMEN_UNIV and student.gender == '남': continue
        mm = major_match(r.get('모집단위') or '', student.major)
        if not mm: continue
        full = (r.get('전형명') or '') + ' ' + (r.get('모집단위') or '')
        if SPECIAL.search(full): continue
        is_reg, ok_reg = regional_eligible(r.get('전형명') or '', r.get('모집단위') or '', student, r['대학'])
        if is_reg and ok_reg is False: continue
        cut = r.get('대표컷')
        is_nonsul = '논술' in (r.get('전형명') or '')
        out.append({'대학': r['대학'], '학년도': r['학년도'], '전형명': r['전형명'],
                    '모집단위': r['모집단위'], '컷': cut, '컷출처': r.get('대표컷_출처'),
                    '컷변동': r.get('컷_전년대비'),
                    '경쟁률': r.get('경쟁률'), '충원': r.get('충원값'),
                    '광역': mm == 'broad',
                    '판정': ('논술(등급참고)' if is_nonsul else judge(cut, student.naesin))})
    return out


# ---------------- 정시(수능 백분위) 진단 ----------------
# 등급별 대표 백분위(구간 중앙값): 1등급 상위4%→98, 2등급 4~11%→92.5, ...
# 스타나인 등급 구간의 백분위 중앙값: 1등급 상위4%→98, 2등급 4~11%→92.5, 3등급 11~23%→83,
# 4등급 23~40%→68.5, 5등급 40~60%→50, 6등급 60~77%→31.5, 7등급 77~89%→17, 8등급 89~96%→7.5, 9등급→2
GRADE_PCT = {1:98.0, 2:92.5, 3:83.0, 4:68.5, 5:50.0, 6:31.5, 7:17.0, 8:7.5, 9:2.0}

def jeongsi_match(student: Student, years=(2025, 2026)):
    """정시 수능백분위 입결 대조. 학생 국·수·탐 등급→백분위 근사 평균과 비교."""
    pcts = [GRADE_PCT.get(student.sat.get(k)) for k in ('국어','수학','탐구')]
    pcts = [p for p in pcts if p is not None]
    if not pcts: return []
    my = round(sum(pcts)/len(pcts), 1)
    u = json.load(open(f'{DB}/results_unified.json'))
    out = []
    for r in u['rows']:
        if r['모집시기'] != '정시' or r['학년도'] not in years: continue
        if r.get('성적지표') != '수능백분위': continue
        if r['대학'] in WOMEN_UNIV and student.gender == '남': continue
        pavg = r.get('백분위_평균')
        basis = '평균'
        if pavg is None:
            pavg = r.get('백분위_최저')  # 일부 대학(아주 등)은 70%컷만 공개 — 참고 판정에 사용
            basis = '70%컷'
        if pavg is None: continue
        mm = major_match(r.get('모집단위') or '', student.major)
        if not mm: continue
        full = (r.get('전형명') or '') + ' ' + (r.get('모집단위') or '')
        if SPECIAL.search(full) or NON_ACADEMIC.search(full): continue
        d = my - pavg   # 백분위는 높을수록 유리
        if d >= 3: j = '안정'
        elif d >= 0: j = '적정'
        elif d >= -3: j = '도전'
        else: j = '상향'
        out.append({'대학': r['대학'], '학년도': r['학년도'], '전형명': r['전형명'],
                    '모집단위': r['모집단위'], '작년백분위': pavg, '컷기준': basis, '내백분위': my,
                    '경쟁률': r.get('경쟁률'), '광역': mm == 'broad', '판정': j})
    return out

def diagnose(student: Student):
    student.major = MAJOR_ALIAS.get((student.major or '').strip(), (student.major or '').strip())
    tracks = eligible_tracks(student)
    matches = match_results(student)
    jeongsi = jeongsi_match(student)
    from collections import Counter
    summary = Counter(m['판정'] for m in matches if m['판정'])
    return {'student': student, 'tracks': tracks, 'matches': matches, 'jeongsi': jeongsi, 'summary': dict(summary)}

if __name__ == '__main__':
    s = Student(naesin=3.2, sat={'국어':3,'수학':4,'영어':2,'탐구':4}, region='인천', major='경영')
    r = diagnose(s)
    print(f"지원가능 전형 {len(r['tracks'])}건({len(set(t['대학'] for t in r['tracks']))}개교) | 입결매칭 {len(r['matches'])}행 | 판정 {r['summary']}")
