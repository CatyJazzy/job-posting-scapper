import streamlit as st
import collect_notices
from pathlib import Path
import shutil
import os
import contextlib
import io

# 로그 캡처용 클래스
class StreamlitLogWriter(io.TextIOBase):
    def __init__(self, log_area):
        self.log_area = log_area
        self.logs = []
    def write(self, text):
        if text.strip():
            self.logs.append(text.strip())
            self.log_area.code("\n".join(self.logs[-15:]))
        return len(text)

st.set_page_config(page_title="공고 이미지 수집기", page_icon="📦")
st.title("📦 공고 이미지 자동 수집 도구")

# 상태 관리
if 'is_running' not in st.session_state:
    st.session_state.is_running = False

st.info("수집 대상과 URL, 개수를 설정한 뒤 아래 버튼을 눌러주세요.")

# --- 설정 섹션 (Form 밖으로 꺼내서 실시간 연동) ---
st.subheader("📋 수집 설정")

site_choice = st.radio(
    "1. 수집 대상 사이트", 
    ["both", "jobda", "inthiswork"], 
    format_func=lambda x: {"both":"둘 다", "jobda":"Jobda", "inthiswork":"인디스워크"}[x],
    horizontal=True,
    disabled=st.session_state.is_running
)

st.markdown("---")
# 이 체크박스가 이제 실시간으로 아래 input의 disabled 상태를 조절합니다.
use_custom_url = st.checkbox("🔗 URL을 직접 입력하시겠습니까?", value=False, disabled=st.session_state.is_running)

col1, col2 = st.columns(2)
with col1:
    jobda_url = st.text_input(
        "Jobda 수집 URL", 
        value=collect_notices.JOBDA_DEFAULT_URL, 
        disabled=not use_custom_url or st.session_state.is_running
    )
with col2:
    inthiswork_url = st.text_input(
        "인디스워크 수집 URL", 
        value=collect_notices.INTHISWORK_DEFAULT_URL, 
        disabled=not use_custom_url or st.session_state.is_running
    )

st.markdown("---")

limit = st.number_input(
    "3. 수집할 공고 개수 (최신순)", 
    min_value=1, max_value=200, value=40, 
    disabled=st.session_state.is_running
)

detail_limit = st.number_input(
    "4. 인디스워크 상세 수집 제한 (0은 전체)", 
    min_value=0, value=0,
    disabled=st.session_state.is_running
)

# --- 실행 버튼 ---
if st.button("🚀 수집 시작", type="primary", disabled=st.session_state.is_running):
    st.session_state.is_running = True
    
    # 내부 실행용 Args 클래스
    class Args:
        site = site_choice
        limit = limit
        detail_limit = detail_limit
        out = "web_collected"
        workers = 4
        jobda_url = jobda_url
        inthiswork_url = inthiswork_url
        interactive = False

    args = Args()
    run_root = Path(args.out).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    
    status_text = st.empty()
    progress_bar = st.progress(0)
    log_container = st.expander("실시간 수집 로그", expanded=True)
    log_area = log_container.empty()
    
    stream_writer = StreamlitLogWriter(log_area)
    sites = ["jobda", "inthiswork"] if args.site == "both" else [args.site]
    
    try:
        with contextlib.redirect_stdout(stream_writer):
            for i, site in enumerate(sites):
                current_pct = int((i / len(sites)) * 100)
                progress_bar.progress(current_pct)
                status_text.markdown(f"### 🔄 현재 **{site}** 수집 중...")
                
                # 수집 엔진 가동
                site_name, output_dir, data = collect_notices.collect_site(args, site, run_root)
                st.success(f"✅ {site} 수집 완료!")
                
                # 결과 압축 및 다운로드 버튼 생성
                zip_name = shutil.make_archive(str(output_dir), 'zip', output_dir)
                with open(zip_name, "rb") as f:
                    st.download_button(
                        label=f"📂 {site} 결과 다운로드 (.zip)",
                        data=f,
                        file_name=os.path.basename(zip_name),
                        key=f"dl_{site}_{i}"
                    )
        
        progress_bar.progress(100)
        status_text.success("🎉 모든 수집 작업이 완료되었습니다!")

    except Exception as e:
        st.error(f"❌ 오류 발생: {e}")
    
    st.session_state.is_running = False
    if st.button("🔄 초기화 후 다시 하기"):
        st.rerun()
