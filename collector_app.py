import streamlit as st
import collect_notices
from pathlib import Path
import shutil
import os
import time

# 페이지 설정
st.set_page_config(page_title="공고 파일 수집기", page_icon="🚀")

st.title("📦 공고 파일 수집기")
st.markdown("""
이 도구는 **Jobda**와 **인디스워크**의 채용 공고 이미지를 자동으로 수집합니다.
수집이 완료되면 하단에 생성되는 **압축 파일(ZIP) 다운로드** 버튼을 클릭하세요.
""")

# 사이드바 설정 (옵션)
with st.sidebar:
    st.header("⚙️ 설정")
    workers = st.slider("동시 작업 수", 1, 10, 4)
    limit = st.number_input("사이트별 최대 공고 수", min_value=1, value=40)
    detail_limit = st.number_input("인디스워크 상세 제한 (0은 전체)", min_value=0, value=0)

# 메인 입력 화면
col1, col2 = st.columns(2)
with col1:
    site_choice = st.radio("수집 대상", ["both", "jobda", "inthiswork"], index=0)
with col2:
    st.info("URL을 비워두면 기본 주소로 수집을 시작합니다.")

jobda_url = st.text_input("Jobda URL", value=collect_notices.JOBDA_DEFAULT_URL)
inthiswork_url = st.text_input("인디스워크 URL", value=collect_notices.INTHISWORK_DEFAULT_URL)

# 실행 버튼
if st.button("🚀 수집 시작", type="primary"):
    # 가상의 Namespace 객체 생성 (기존 argparse 대응)
    class Args:
        def __init__(self):
            self.site = site_choice
            self.limit = limit
            self.detail_limit = detail_limit
            self.out = "web_collected"
            self.workers = workers
            self.jobda_url = jobda_url
            self.inthiswork_url = inthiswork_url
            self.interactive = False

    args = Args()
    run_root = Path(args.out).resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    sites = ["jobda", "inthiswork"] if args.site == "both" else [args.site]
    
    status_area = st.empty()
    log_area = st.expander("상세 로그 확인", expanded=True)
    
    summaries = []
    
    with st.spinner("데이터를 수집 중입니다..."):
        for site in sites:
            try:
                status_area.write(f"### 🔄 {site} 수집 중...")
                # collect_site는 stdout에 출력하므로, 실제 로그는 터미널에 찍히지만 
                # 데이터는 summaries에 담깁니다.
                site_name, output_dir, data = collect_notices.collect_site(args, site, run_root)
                summaries.append((site_name, output_dir, data))
            except Exception as e:
                st.error(f"{site} 수집 중 오류 발생: {e}")

    st.success("✅ 수집 완료!")
    
    # 결과 요약 및 다운로드 버튼
    for site, output_dir, data in summaries:
        st.write(f"**{site}**: 저장 {data['savedAssetCount']}개 / 실패 {data['failedAssetCount']}개")
        
        # 폴더를 ZIP으로 압축
        zip_path = f"{output_dir}.zip"
        shutil.make_archive(str(output_dir), 'zip', output_dir)
        
        with open(zip_path, "rb") as f:
            st.download_button(
                label=f"📂 {site} 결과 다운로드 (.zip)",
                data=f,
                file_name=os.path.basename(zip_path),
                mime="application/zip"
            )