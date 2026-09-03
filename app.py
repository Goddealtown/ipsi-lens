#!/usr/bin/env python3
"""입시렌즈 진단 웹 앱(프로토타입) — Streamlit
실행: streamlit run app.py
입력(내신·수능·지역·희망계열·성별) → 수시/정시 진단 리포트 렌더.
"""
import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.diagnose import Student, diagnose, MAJOR_SYNONYM
from engine.report import render

st.set_page_config(page_title='입시렌즈 진단', page_icon='🧭', layout='wide')
st.title('🧭 입시렌즈 — 대입 진단 리포트')
st.caption('전국 62개 대학 16,000여 건의 공식 입시결과(각 대학 입학처 발표)를 기반으로 한 진단입니다.')

with st.sidebar:
    st.header('내 정보 입력')
    naesin = st.number_input('내신 평균 등급', 1.0, 9.0, 3.5, 0.1)
    st.subheader('수능 예상 등급')
    c1, c2 = st.columns(2)
    with c1:
        kor = st.selectbox('국어', list(range(1, 10)), 3)
        eng = st.selectbox('영어', list(range(1, 10)), 3)
    with c2:
        math = st.selectbox('수학', list(range(1, 10)), 3)
        tam = st.selectbox('탐구', list(range(1, 10)), 3)
    region = st.selectbox('거주/고교 지역', ['서울','인천','경기','부산','울산','경남','대구','경북','광주','전남','전북','대전','세종','충남','충북','강원','제주'])
    majors = sorted(MAJOR_SYNONYM.keys())
    major = st.selectbox('희망 계열/학과', majors, index=majors.index('경영') if '경영' in majors else 0)
    major_free = st.text_input('직접 입력(선택)', '', help='목록에 없는 학과 키워드')
    gender = st.radio('성별', ['미입력','여','남'], horizontal=True)
    go = st.button('진단하기', type='primary', use_container_width=True)

if go:
    st_major = major_free.strip() or major
    stu = Student(naesin=float(naesin),
                  sat={'국어':int(kor),'수학':int(math),'영어':int(eng),'탐구':int(tam)},
                  region=region, major=st_major,
                  gender='' if gender=='미입력' else gender)
    with st.spinner('전국 입시결과 대조 중…'):
        res = diagnose(stu)
    # 학생부 탭 입력 등 위젯 조작으로 재실행돼도 결과가 유지되도록 저장
    st.session_state['diag'] = {'major': st_major, 'naesin': float(naesin),
                                'res': res, 'md': render(res)}

if 'diag' in st.session_state:
    d = st.session_state['diag']
    st_major, res, md = d['major'], d['res'], d['md']
    naesin_saved = d['naesin']

    from collections import Counter
    cnt = Counter(m['판정'] for m in res['matches'] if m['판정'] in ('안정','적정','도전','상향'))
    n = sum(cnt.values())
    c1, c2, c3 = st.columns(3)
    c1.metric('지원 가능 전형', f"{len(res['tracks'])}개")
    c2.metric('입결 대조 카드(수시)', f"{n}건")
    c3.metric('정시 참고 카드', f"{len(res.get('jeongsi') or [])}건")

    # 판정 분포 요약 바
    g1, g2, g3, g4 = st.columns(4)
    g1.metric('🟢 안정', cnt.get('안정', 0))
    g2.metric('🟡 적정', cnt.get('적정', 0))
    g3.metric('🟠 도전', cnt.get('도전', 0))
    g4.metric('🔴 상향', cnt.get('상향', 0))

    tab1, tab2, tab3 = st.tabs(['📋 진단 리포트', '🔎 전체 카드 표', '📝 학생부 점검(베타)'])
    with tab1:
        st.markdown(md)
    with tab2:
        import pandas as pd
        from engine.report import NAMES
        best = {}
        for m in res['matches']:
            if m['판정'] not in ('안정','적정','도전','상향'): continue
            k = (m['대학'], m['전형명'], m['모집단위'])
            if k not in best or m['학년도'] > best[k]['학년도']:
                best[k] = m
        df = pd.DataFrame([{'대학': NAMES.get(m['대학'], m['대학']), '전형': m['전형명'],
                            '모집단위': m['모집단위'], '학년도': m['학년도'],
                            '합격선': m['컷'], '전년대비': m.get('컷변동'),
                            '경쟁률': m.get('경쟁률'), '판정': m['판정']}
                           for m in best.values()])
        sel = st.multiselect('판정 필터', ['안정','적정','도전','상향'], default=['적정','도전'])
        view = df[df['판정'].isin(sel)].sort_values('합격선')
        st.dataframe(view, use_container_width=True, height=480)
    with tab3:
        st.caption('학생부(자율·동아리·진로·봉사·세특) 텍스트를 붙여넣으면 대입 미반영 항목을 자동 점검합니다. 판정이 아닌 제도 안내입니다.')
        sb = st.text_area('학생부 내용 붙여넣기', height=220, key='sb_text')
        if sb.strip():
            from engine.hakjong import parse as hj_parse, 제도필터
            secs = hj_parse(sb)
            warns = 제도필터(secs)
            st.write(f'인식된 섹션: {", ".join(secs.keys()) if secs else "없음(항목 제목 포함해 붙여넣어 주세요)"}')
            if warns:
                st.warning(f'대입 미반영 항목 {len(warns)}건 발견')
                for w in warns:
                    st.markdown(f"- **[{w['섹션']}/{w['태그']}]** {w['경고']}\n  - 발췌: _{w['발췌']}…_")
            elif secs:
                st.success('미반영 항목이 발견되지 않았습니다.')
        # 진단 결과 대학 중 학종 평가요소 공표 대학 안내
        from engine.hakjong import CRITERIA
        from engine.report import NAMES as _NM
        my_unis = set(m['대학'] for m in res['matches'] if '종합' in m['전형명'] or '인재' in m['전형명'])
        crits = [c for c in CRITERIA if c['university_id'] in my_unis and c.get('요소') and c['요소'][0].get('비율')]
        if crits:
            st.subheader('지원권 대학의 학종 평가요소(공표 비율)')
            st.caption('각 대학 요강이 공표한 학생부종합 평가요소 비율입니다. 세특·활동을 비중 높은 역량에 맞춰 보완하세요.')
            import pandas as pd
            cdf = pd.DataFrame([{'대학': _NM.get(c['university_id'], c['university_id']),
                                 '전형': ('학생부종합(공통)' if c.get('전형','').startswith('미상') else c.get('전형','')), '단계': c.get('단계',''),
                                 '요소': ' · '.join(f"{e['명']} {e['비율']}%" for e in c['요소'])}
                                for c in crits])
            st.dataframe(cdf, use_container_width=True, height=260)
    st.download_button('리포트 다운로드(.md)', md,
        file_name=f'대입진단_{st_major}_{naesin_saved}등급.md', mime='text/markdown')
else:
    st.info('왼쪽에서 성적을 입력하고 **진단하기**를 눌러주세요.')
    st.markdown('''
- **수시**: 내신 등급을 62개 대학 최종등록자 합격선(50/70/80%컷 등)과 대조해 안정·적정·도전·상향으로 분류합니다.
- **정시**: 수능 예상 등급을 백분위로 근사해 정시 입결과 대조한 참고 판정을 제공합니다.
- **자격 필터**: 지역인재(권역)·여자대학·수능최저를 자동 반영합니다.
''')
