#!/usr/bin/env python3
"""정시 엔진 프로토타입 v0.1
학생 수능 성적 → 대학별 환산점수.

원칙(03 문서): 판정은 결정론적 Rule Engine만. 환산식이 미확인인 대학은
계산을 거부하고 이유를 말한다 — 추측 금지.

사용: python3 engine/jeongsi.py  (내장 샘플 학생으로 데모)
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMULAS = json.load(open(os.path.join(ROOT, 'data/db/formulas_jeongsi.json'), encoding='utf-8'))['formulas']

def _trunc(x, n):
    """소수점 n자리 이하 절사 (전남대형 절사규칙)."""
    import math
    return math.floor(x * 10**n) / 10**n

def convert(student, f):
    """학생 성적을 대학 f의 환산식으로 계산. (점수, 만점, 설명행들) 반환. 계산 불가 시 예외."""
    lines = []
    if f.get('계산불가'):
        raise ValueError(f['계산불가'])
    계열 = student.get('계열', '자연')

    # 전남대형: A=(개인표준/전국최고)×기준만점 절사10 → B=A×(영역만점/기준) 절사4 → C=ΣB → E=round3(C+영어) → +한국사 가산
    if f.get('비율형식') == '표준점수비율환산':
        최고 = student.get('전국최고표준')
        if not 최고:
            raise ValueError('전국최고 표준점수 미제공 — 해당 연도 영역별 최고 표준점수 필요')
        만점표 = next((v for k, v in f['영역만점'].items() if 계열 in k), None)
        if 만점표 is None: raise ValueError(f'계열({계열}) 영역만점표 미확보')
        기준 = f.get('기준만점', 800)
        C = 0.0
        for 영역 in ('국어', '수학'):
            A = _trunc(student[영역]['표준점수'] / 최고[영역] * 기준, 10)
            B = _trunc(A * 만점표[영역] / 기준, 4)
            C += B
            lines.append(f"{영역}: {student[영역]['표준점수']}/{최고[영역]} → A {A:.4f} × {만점표[영역]}/{기준} = {B:.4f}")
        for s in student['탐구'][:f.get('탐구과목수', 2)]:
            A = _trunc(s['표준점수'] / 최고['탐구'][s['과목']] * 기준, 10)
            B = _trunc(A * 만점표['탐구과목'] / 기준, 4)
            C += B
            lines.append(f"탐구({s['과목']}): {s['표준점수']}/{최고['탐구'][s['과목']]} → {B:.4f}")
        영표 = f['영어']['등급표']; 한표 = f['한국사']['등급표']
        D = 영표[student['영어등급'] - 1]
        E = round(C + D, 3)
        F_ = 한표[student['한국사등급'] - 1]
        lines.append(f"영어 {student['영어등급']}등급 +{D} · 한국사 {student['한국사등급']}등급 가산 +{F_}")
        만점 = sum(만점표[k] for k in ('국어', '수학')) + 만점표['탐구과목'] * f.get('탐구과목수', 2) + 영표[0]
        return E + F_, 만점, lines
    # 계열 비율 선택: 키에 계열명이 포함된 항목 → 없으면 '전체'
    비율표 = None
    for k, v in f['계열비율'].items():
        if 계열 in k: 비율표 = v; break
    if 비율표 is None: 비율표 = f['계열비율'].get('전체') or list(f['계열비율'].values())[0]

    기본지표 = '백분위' if '백분위' in f['반영지표'] else '표준점수'
    지표별 = f.get('영역별지표', {})
    ix = lambda 영역: 지표별.get(영역, 기본지표)
    탐지 = ix('탐구')
    탐구 = sorted(student['탐구'], key=lambda x: -x[탐지])[:f.get('탐구과목수', 2)]
    합 = sum(s[탐지] for s in 탐구)
    탐구값 = 합 if f.get('탐구집계') == '합' else 합 / len(탐구)
    영역값 = {'국어': student['국어'][ix('국어')], '수학': student['수학'][ix('수학')], '탐구': 탐구값}
    # 시립대형: 영어가 비율 반영이면 계열별 등급점수표에서 만점 대비 값을 구해 주입
    if any(k.startswith('영어') for k in 비율표):
        spec = f.get('영어', {})
        계열표들 = spec.get('등급표_계열')
        if not 계열표들: raise ValueError('영어가 비율 반영인데 등급점수표 미확보')
        표k = next((k for k in 계열표들 if 계열 in k or k in 선택계열키), None) if (선택계열키:=next((k for k in f['계열비율'] if 비율표 is f['계열비율'][k]),'')) is not None else None
        표k = 표k or next((k for k in 계열표들 if 계열 in k), list(계열표들)[0])
        표 = 계열표들[표k]
        영역값['영어'] = 표[student['영어등급'] - 1] / 표[0] * 100  # 만점 100 정규화 후 비율 적용
        lines.append(f"영어 {student['영어등급']}등급 → {표[student['영어등급']-1]}/{표[0]}점 ({표k})")

    # 충남대형: 총점 = Σ(표준점수×영역배점)÷200 + 영어 감점 + 한국사 감점
    if f.get('비율형식') == '표준점수배점_200':
        배점표 = next((v for k, v in f['계열비율'].items() if 계열 in k), None)
        if 배점표 is None: raise ValueError(f'계열({계열}) 배점표 미확보')
        합 = 0.0
        for 영역 in ('국어', '수학'):
            if 영역 in 배점표:
                합 += student[영역]['표준점수'] * 배점표[영역]
                lines.append(f"{영역}: 표준 {student[영역]['표준점수']} × {배점표[영역]}")
        탐합 = sum(s['표준점수'] for s in student['탐구'][:f.get('탐구과목수', 2)])
        if student.get('과탐가산'): 탐합 *= 1.1
        합 += 탐합 * 배점표['탐구']
        lines.append(f"탐구(표준 합{'×1.1' if student.get('과탐가산') else ''}): {탐합:g} × {배점표['탐구']}")
        총점 = 합 / 200
        영감 = next((v for k, v in f['영어']['감점표_계열'].items() if 계열 in k), None)
        if 영감 is None: raise ValueError(f'계열({계열}) 영어 감점표 미확보')
        총점 += 영감[student['영어등급'] - 1] + f['한국사']['감점표'][student['한국사등급'] - 1]
        lines.append(f"영어 {student['영어등급']}등급 {영감[student['영어등급']-1]} · 한국사 {student['한국사등급']}등급 {f['한국사']['감점표'][student['한국사등급']-1]}")
        return 총점, f['반영총점'], lines

    # 경북대형: (Σ 영역별 가중점수 + 영어등급점수) × 스케일 + 한국사 가산
    if f.get('비율형식') == '가중치합산_스케일':
        # 스케일·기준만점이 계열별 dict인 경우(연세형) 계열로 선택
        스케일표 = f.get('총점스케일_계열')
        if 스케일표:
            스케일 = next((v for k, v in 스케일표.items() if 계열 in k), None)
            기준만점 = next((v for k, v in f['기준만점_계열'].items() if 계열 in k), None)
            if 스케일 is None: raise ValueError(f'계열({계열}) 스케일 미확보')
        else:
            스케일 = f['총점스케일']; 기준만점 = f['기준만점합']
        탐백분위 = '백분위' in f.get('탐구지표', '')
        합 = 0.0
        for 영역, w in 비율표.items():
            if 영역 == '탐구':
                지표 = '백분위' if 탐백분위 else '표준점수'
                base = sum(s[지표] for s in student['탐구'][:f.get('탐구과목수', 2)])
                lines.append(f"탐구({f.get('탐구지표', '표준')[:12]} 근사): {base} × {w}")
            else:
                base = student[영역]['표준점수']
                lines.append(f"{영역}: 표준 {base} × {w}")
            합 += base * w
        영표 = f['영어']['등급표']
        영어값 = 영표[student['영어등급'] - 1]
        if f.get('영어처리') == '스케일후가산':
            총점 = 합 * 스케일 + 영어값
            lines.append(f"×스케일 후 영어 {student['영어등급']}등급 {'+' if 영어값>=0 else ''}{영어값}")
        else:
            합 += 영어값
            lines.append(f"영어 {student['영어등급']}등급 +{영어값}")
            총점 = 합 * 스케일
        한표 = f['한국사']['등급표']
        총점 += 한표[student['한국사등급'] - 1]
        lines.append(f"×스케일 {스케일:.4f} 후 한국사 {student['한국사등급']}등급 {'+' if 한표[student['한국사등급']-1]>=0 else ''}{한표[student['한국사등급']-1]}")
        return 총점, f.get('수능만점') or 기준만점 * 스케일, lines

    총점 = 0.0; 만점 = 0.0
    가중치형 = f.get('비율형식', '').startswith('가중치') and f.get('비율형식') != '가중치합산_스케일'
    # 우수영역순(가천형): 후보 영역을 학생 성적 내림차순으로 정렬해 높은 비율부터 배정
    if f.get('비율형식', '').startswith('우수영역순'):
        배점표 = f.get('영어', {}).get('등급배점표')
        if 배점표:  # 가천형: 영어 등급배점을 우수영역 후보값으로 직접 사용
            영역값['영어'] = 배점표[student['영어등급'] - 1]
            lines.append(f"영어 {student['영어등급']}등급 → 배점 {영역값['영어']}")
        고정 = {k: v for k, v in 비율표.items() if not k.startswith('우수')}
        고정영역 = {k.split('(')[0] for k in 고정}
        # 고정비율 영역(예: 탐구 20%)은 우수순 후보에서 제외 — 이중반영 방지
        후보키 = [k for k in ('국어', '수학', '영어', '탐구') if k not in 고정영역]
        if '영어' in 후보키 and '영어' not in 영역값:
            raise ValueError('영어가 우수영역 후보인데 등급배점표/변환표 미확보')
        정렬 = sorted(((영역값[k], k) for k in 후보키 if k in 영역값), reverse=True)
        비율들 = [v for k, v in 비율표.items() if k.startswith('우수')]
        for (val, 영역), w in zip(정렬, 비율들):
            총점 += val * w / 100; 만점 += 100 * w / 100
            lines.append(f"{영역}(우수순): {val} × {w}%")
        for 영역, w in 고정.items():
            base = 영역값.get(영역.split('(')[0])
            if base is None: continue
            총점 += base * w / 100; 만점 += 100 * w / 100
            lines.append(f"{영역}: {base} × {w}%")
        # 영어/한국사 처리로 진행하지 않고 반환 전 공통 검증만 수행
        for 영역 in ('영어', '한국사'):
            spec = f.get(영역, {})
            if '미확인' in spec.get('방식', ''):
                raise ValueError(f"{영역} 처리방식 미확인 — 요강 원문 추출 필요")
        return 총점, 만점, lines
    for 영역, w in 비율표.items():
        base = 영역값.get(영역.split('(')[0])
        if base is None: continue
        총점 += base * w / (1 if 가중치형 else 100)
        만점 += (100 if ix(영역.split('(')[0]) == '백분위' else 140) * w / (1 if 가중치형 else 100)
        lines.append(f"{영역}: {base} × {w}{'' if 가중치형 else '%'}")

    # 영어/한국사
    for 영역 in ('영어', '한국사'):
        spec = f.get(영역, {})
        표 = spec.get('등급표')
        방식 = spec.get('방식', '')
        if spec.get('등급표_계열'): continue
        if ('미확인' in 방식) or ('미추출' in 방식) or (표 is not None and not isinstance(표, list)):
            raise ValueError(f"{영역} 등급표 미확보 — 요강 원문 추출 필요")
        # 영역이 비율표에 이미 포함된 경우(시립대형)는 등급표 없이도 비율 계산에서 처리됨
        if isinstance(표, list) is False and 영역 in ''.join(비율표.keys()) and not spec.get('등급표_계열'):
            raise ValueError(f"{영역}이 비율 반영인데 등급점수표 미확보")
        if isinstance(표, list):
            등급 = student[영역 + '등급']
            pt = 표[등급 - 1]
            총점 += pt; 만점 += 표[0]
            lines.append(f"{영역} {등급}등급: {'+' if pt >= 0 else ''}{pt} ({spec['방식']})")
    return 총점, 만점, lines

def convert_best(student, f):
    """A/B 이원산출: 계열비율 키가 A형/B형이면 각각 계산해 상위 반영."""
    keys = list(f['계열비율'].keys())
    if not any(k.endswith('형') for k in keys):
        return convert(student, f) + (None,)
    best = None
    for k in keys:
        f2 = dict(f); f2['계열비율'] = {'전체': f['계열비율'][k]}
        r = convert(student, f2)
        if best is None or r[0] > best[0][0]: best = (r, k)
    return best[0] + (best[1],)

def selftest():
    """요강 산출 예시 대조 — 서강 2026 골든테스트."""
    g = {'이름':'골든','계열':'자연','국어':{'표준점수':128,'백분위':94},'수학':{'표준점수':135,'백분위':96},
         '탐구':[{'과목':'t1','표준점수':64.3,'백분위':93},{'과목':'t2','표준점수':67.4,'백분위':98}],
         '영어등급':2,'한국사등급':1}
    for f in FORMULAS:
        if f.get('골든테스트'):
            총점,만점,_,유형 = convert_best(g, f)
            기대 = f['골든테스트']['기대값']
            ok = abs(총점-기대) < 0.05
            print(f"골든테스트 {f['university_id']}{f['admission_year']}: 계산 {총점:.2f} vs 요강예시 {기대} → {'✅ 일치' if ok else '❌ 불일치'} (채택유형 {유형})")
        for t in f.get('골든테스트목록', []):
            s = dict(t['학생']); s['계열'] = t['계열']; s['이름'] = t['이름']
            총점, 만점, _ = convert(s, f)
            ok = abs(총점 - t['기대값']) < 0.001
            print(f"골든테스트 {f['university_id']}{f['admission_year']} {t['이름']}: 계산 {총점:.3f} vs 요강예시 {t['기대값']} → {'✅ 일치' if ok else '❌ 불일치'}")

def run(student):
    print(f"◆ 학생: {student['이름']} ({student['계열']}) — "
          f"국어 백분위 {student['국어']['백분위']} · 수학 {student['수학']['백분위']} · "
          f"탐구 {[s['백분위'] for s in student['탐구']]} · 영어 {student['영어등급']}등급\n")
    for f in FORMULAS:
        tag = f"{f['university_id']} {f['admission_year']} {f['전형명']}"
        try:
            총점, 만점, lines, 유형 = convert_best(student, f)
            pct = 총점 / 만점 * 100
            print(f"[{tag}]  환산 {총점:,.1f} / {만점:,.1f}  ({pct:.1f}%)")
            for l in lines: print(f"    {l}")
        except (ValueError, KeyError) as e:
            print(f"[{tag}]  ⚠ 계산 불가: {e}")
        print()
    print("※ 판정(안정/적정/도전)은 AdmissionResult(과거 합격선)와 비교해야 나온다 — 다음 단계.")
    print("※ 같은 학생이라도 대학마다 %가 다른 것이 정상 — 대학 간 환산점수 비교 금지 원칙.")

if __name__ == '__main__':
    # 샘플 학생: 상위권 자연계
    sample = {
        '이름': '샘플학생A', '계열': '자연',
        '국어': {'백분위': 91, '표준점수': 128},
        '수학': {'백분위': 95, '표준점수': 135},
        '탐구': [{'과목': '화학Ⅰ', '백분위': 88, '표준점수': 64},
                 {'과목': '생명Ⅰ', '백분위': 92, '표준점수': 66}],
        '영어등급': 2, '한국사등급': 3,
    }
    selftest()
    print()
    run(sample)

def judge(score, cut50, cut70):
    """판정: 환산점수 vs 전년 최종등록자 컷. 06문서 원칙 — 보수적, 5단계."""
    if score >= cut50 + (cut50 - cut70) * 2: return '안정'
    if score >= cut50: return '적정'
    if score >= cut70: return '소신'
    if score >= cut70 - (cut50 - cut70) * 2: return '도전'
    return '매우 도전'

def demo_judge():
    import json as _j
    res=_j.load(open(os.path.join(ROOT,'data/db/results_sogang_2026_jeongsi.json'),encoding='utf-8'))
    f=[x for x in FORMULAS if x['university_id']=='sogang' and x['admission_year']==2026][0]
    g={'이름':'샘플학생A','계열':'인문','국어':{'표준점수':128},'수학':{'표준점수':135},
       '탐구':[{'과목':'t1','표준점수':64.3},{'과목':'t2','표준점수':67.4}],'영어등급':2,'한국사등급':1}
    총점,만점,_,유형=convert_best(g,f)
    print(f"\n━━ 판정 데모: 서강대 정시 나군 (환산 {총점:.2f}, {유형}) — 전년 최종등록자 컷 기준")
    for u in res['단위결과']:
        print(f"  {u['모집단위']:8s} 50%컷 {u['컷50']:.2f} / 70%컷 {u['컷70']:.2f} → {judge(총점,u['컷50'],u['컷70'])}")
    print("  ※ 판정은 전년(2026) 결과 단순 비교 — 3개년 축적 후 변동폭 반영 예정")

if __name__ == '__main__' and '--judge' in sys.argv:
    demo_judge()
