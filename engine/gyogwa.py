#!/usr/bin/env python3
"""교과(내신) 엔진 v0.1 — 성적표 → 대학별 교과점수/평균등급 → 판정."""
import json, os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F=json.load(open(os.path.join(ROOT,'data/db/formulas_gyogwa.json'),encoding='utf-8'))['formulas']

def ajou_score(subs,f):
    xs=[(s['단위'],f['등급점수표'][s['등급']-1]) for s in subs
        if s['교과'] in f['반영교과'] and s.get('등급')]
    진로=[s for s in subs if s['교과'] in f['반영교과'] and s.get('성취도')]
    진로=sorted(진로,key=lambda s:(s['성취도'],-s['단위']))[:5]
    xs+= [(s['단위'],f['성취도점수'][s['성취도']]) for s in 진로]
    n=sum(u for u,_ in xs)
    return sum(u*p for u,p in xs)/n, len(xs)

def avg_grade(subs,반영교과):
    xs=[(s['단위'],s['등급']) for s in subs if s['교과'] in 반영교과 and s.get('등급')]
    return sum(u*g for u,g in xs)/sum(u for u,_ in xs), len(xs)

def judge_grade(g,cut50,cut70):
    gap=cut70-cut50
    if g<=cut50-2*gap: return '안정'
    if g<=cut50: return '적정'
    if g<=cut70: return '소신'
    if g<=cut70+2*gap: return '도전'
    return '매우 도전'

if __name__=='__main__':
    # 샘플 성적표 (일부 학기)
    성적=[
     {'교과':'국어','과목':'문학','단위':4,'등급':2},
     {'교과':'수학','과목':'수학Ⅰ','단위':4,'등급':1},
     {'교과':'수학','과목':'수학Ⅱ','단위':4,'등급':2},
     {'교과':'영어','과목':'영어Ⅰ','단위':4,'등급':2},
     {'교과':'과학','과목':'물리학Ⅰ','단위':3,'등급':1},
     {'교과':'과학','과목':'화학Ⅰ','단위':3,'등급':2},
     {'교과':'사회','과목':'통합사회','단위':3,'등급':3},
     {'교과':'과학','과목':'물리학Ⅱ','단위':3,'성취도':'A'},
     {'교과':'수학','과목':'기하','단위':3,'성취도':'A'},
     {'교과':'한국사','과목':'한국사','단위':3,'등급':4},  # 반영 제외 확인용
    ]
    f=F[0]
    pt,n=ajou_score(성적,f)
    print(f"[아주대 고교추천] 교과점수 {pt:.2f}/100 (반영 {n}과목 — 한국사 제외 확인)")
    g,n2=avg_grade(성적,['국어','수학','영어','사회','과학'])
    print(f"[평균 석차등급] {g:.2f}등급 (등급과목 {n2}개, 이수단위 가중)")
    # 서강 지역균형 판정 (입결: 인문 1.57/1.59, 컴퓨터 1.79/1.96, 경영 1.46/1.60)
    print(f"\n━━ 서강대 지역균형(교과) 판정 — 2026 최종등록자 등급컷")
    for 단위,c50,c70 in [('인문학부',1.57,1.59),('경영학부',1.46,1.60),('컴퓨터공학과',1.79,1.96),('생명과학과',1.23,1.25)]:
        print(f"  {단위:8s} 50%컷 {c50} / 70%컷 {c70} → {judge_grade(g,c50,c70)}")
    print("  ※ 수능최저 충족 전제. 등급컷은 서강대 자체공개 입결(A등급 출처)")
