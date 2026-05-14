import streamlit as st
import collect_notices
from pathlib import Path
import shutil
import os
import contextlib
import io

# 로그를 실시간으로 캡처하기 위한 클래스
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

# 1. 수집 상태 관리 (실행 중인지 여부)
if 'is_running' not in st.session_state:
    st.session_state.is_running = False

st.info("수집 대상과 개수를 정한 뒤 실행 버튼을 눌러주세요.")

# 📋 수집 설정 섹션
st.subheader("📋 수집 설정")

# 버튼이 비활성화되는 동안 입력값들도 수정 못하게 disabled 처리를 연동할 수 있습니다.
site_choice = st.radio(
    "1. 수집 대상 사이트", 
    ["both", "jobda", "inthiswork"], 
    format_func=lambda x: {"both":"둘 다", "jobda":"Jobda", "inthiswork":"인디스워크"}[x],
    horizontal=True,
    help="이미지를 가져올 사이트를 선택하세요.",
    disabled=st.session_state.is_running
)

limit = st.number_input(
    "2. 수집할 공고 개수 (최신순)", 
    min_value=1, max_value=200, value=40, 
    help="각 사이트의 공고 목록에서 최신순으로 몇 개의 공고를 확인할지 결정합니다.",
    disabled=st.session_state.is_running
)

detail_limit = st.number_input(
    "3. 인디스워크 상세 수집 제한 (0은 전체)", 
    min_value=0, value=0,
    help="인디스워크에서 상세 페이지 본문까지 들어가서 수집할 공고의 개수입니다. 0이면 위에서 설정한 개수만큼 모두 수집합니다.",
    disabled=st.session_state.is_running
)

# 2. 버튼 클릭 시 상태 변경 및 실행
# st.session_state.is_running이 True이면 버튼이 비활성화됨
if st.button("🚀 수집 시작", type="primary", disabled=st.session_state.is_running):
    st.session_state.is_running = True
    st.rerun() # 상태 반영을 위해 화면 새로고침

# 3. 실제 수집 로직 (상태가 True일 때만 실행)
if st.session_state.is_running:
    class Args:
        site = site_choice
        limit = limit
        detail_limit = detail_limit
        out = "web_collected"
        workers = 4
        jobda_url = collect_notices.JOBDA_DEFAULT_URL
        inthiswork_url = collect_notices.INTHISWORK_DEFAULT_URL
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
                status_text.markdown(f"### 🔄 현재 **{site}** 수집 중... ({i+1}/{len(sites)})")
                
                # 수집 실행
                site_name, output_dir, data = collect_notices.collect_site(args, site, run_root)
                st.success(f"✅ {site} 수집 완료! (성공: {data['savedAssetCount']}, 실패: {data['failedAssetCount']})")
                
                # ZIP 압축 및 다운로드 버튼
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
    
    # 작업 완료 후 버튼 다시 활성화
    st.session_state.is_running = False
    if st.button("🔄 새로 시작하기"):
        st.rerun()