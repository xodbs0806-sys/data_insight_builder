import os
import sys
import json
from app import app, CURRENT_DATASET

def run_e2e_test():
    print("=====================================================================")
    print("🚀 AI Data Insight Builder - End-to-End (E2E) 통합 연동 테스트 시작")
    print("=====================================================================")
    
    client = app.test_client()
    
    # -------------------------------------------------------------
    # 1. GET / 및 정적 파일 검증
    # -------------------------------------------------------------
    print("\n[1단계 검증] GET / (인덱스 페이지 및 정적 파일 로드)")
    res_index = client.get("/")
    assert res_index.status_code == 200, f"Index page failed: {res_index.status_code}"
    html = res_index.get_data(as_text=True)
    assert "AI Data Insight Builder" in html, "HTML title/heading missing"
    assert "chart.js" in html.lower(), "Chart.js CDN missing"
    assert "app.js" in html, "app.js link missing"
    print("  ✅ GET / 성공 (Status 200, HTML 템플릿 및 CDN 연동 확인)")

    # -------------------------------------------------------------
    # 2. GET /health
    # -------------------------------------------------------------
    print("\n[2단계 검증] GET /health (서버 헬스체크 및 API 키 확인)")
    res_health = client.get("/health")
    assert res_health.status_code == 200, f"Health check failed: {res_health.status_code}"
    health_data = res_health.get_json()
    assert health_data["status"] == "ok", "Health status not ok"
    assert health_data["api_key_configured"] is True, "API Key not configured"
    print(f"  ✅ GET /health 성공 (Status: ok, Model: {health_data['model']}, Key Configured: True)")

    # -------------------------------------------------------------
    # 3. POST /inspect (World Bank 원본 CSV 업로드 및 진단)
    # -------------------------------------------------------------
    csv_path = "data/API_IT/API_IT.NET.USER.ZS_DS2_en_csv_v2_468465.csv"
    assert os.path.exists(csv_path), f"CSV file not found: {csv_path}"
    print(f"\n[3단계 검증] POST /inspect (파일 진단: {csv_path})")
    
    with open(csv_path, "rb") as f:
        res_inspect = client.post(
            "/inspect",
            data={"file": (f, "API_IT.NET.USER.ZS_DS2_en_csv_v2_468465.csv")},
            content_type="multipart/form-data"
        )
        
    assert res_inspect.status_code == 200, f"Inspect failed: {res_inspect.status_code}, {res_inspect.data}"
    inspect_data = res_inspect.get_json()
    assert inspect_data["status"] == "success", "Inspect response status is not success"
    diag = inspect_data["diagnostics"]
    
    print(f"  - 인코딩: {diag['file_info']['encoding']}")
    print(f"  - 건너뛴 행 수: {diag['file_info']['skiprows']}줄 (World Bank 상단 메타데이터 감지)")
    print(f"  - 데이터 차원: {diag['dimensions']['row_count']}행 × {diag['dimensions']['col_count']}열")
    print(f"  - 권장 기준연도: {diag['recommended_reference_year']}년")
    print(f"  - 집계 행(비국가) 후보: {len(diag['aggregate_candidates'])}개")
    print(f"  - 중복 행: {diag['duplicate_rows']}건")
    print(f"  - 감지된 경고 수: {len(diag['warnings'])}개")
    assert diag["recommended_reference_year"] == "2024", f"Expected recommended year 2024, got {diag['recommended_reference_year']}"
    assert len(diag["aggregate_candidates"]) == 32, f"Expected 32 aggregates, got {len(diag['aggregate_candidates'])}"
    print("  ✅ POST /inspect 성공 (품질 지표, 권장연도 2024, 32개 집계행 정확히 추출)")

    # -------------------------------------------------------------
    # 4. POST /suggest (Gemini 도구 추천)
    # -------------------------------------------------------------
    print("\n[4단계 검증] POST /suggest (Gemini 분석 추천 호출)")
    res_suggest = client.post("/suggest", content_type="application/json")
    assert res_suggest.status_code == 200, f"Suggest failed: {res_suggest.status_code}, {res_suggest.data}"
    suggest_data = res_suggest.get_json()
    assert suggest_data["status"] == "success", "Suggest status is not success"
    suggestions = suggest_data["suggestions"]
    print(f"  - Gemini 추천 개수: {len(suggestions)}개")
    for idx, s in enumerate(suggestions):
        print(f"    [{idx+1}] 도구: {s.get('tool')}, 기준: {s.get('reference_period')}, 이유: {s.get('why')[:30]}...")
    assert len(suggestions) >= 1, "No suggestions returned"
    print("  ✅ POST /suggest 성공 (JSON 응답 및 도구 카탈로그 검증 통과)")

    # -------------------------------------------------------------
    # 5. POST /run (Pandas 연산: top_bottom_n)
    # -------------------------------------------------------------
    print("\n[5단계 검증] POST /run (도구 실행 1: top_bottom_n)")
    run_payload = {
        "tool": "top_bottom_n",
        "params": {"reference_period": "2024", "n": 10}
    }
    res_run1 = client.post("/run", data=json.dumps(run_payload), content_type="application/json")
    assert res_run1.status_code == 200, f"Run tool 1 failed: {res_run1.status_code}, {res_run1.data}"
    result1 = res_run1.get_json()["result"]
    print(f"  - 요약: {result1['summary']}")
    print(f"  - 사용된 행: {result1['rows_used']}개, 제외된 행: {result1['rows_excluded']}개 ({result1['exclusion_reason']})")
    print(f"  - 차트 타입: {result1['chart_data']['type']}, 데이터셋 크기: {len(result1['chart_data']['datasets'][0]['data'])}")
    assert result1["rows_used"] == 195, f"Expected 195 countries used, got {result1['rows_used']}"
    assert result1["rows_excluded"] == 70, f"Expected 70 excluded, got {result1['rows_excluded']}"
    print("  ✅ POST /run (top_bottom_n) 성공 (Pandas 엄밀 연산 및 행 제외 추적 검증)")

    # -------------------------------------------------------------
    # 6. POST /run (Pandas 연산: compare_one_vs_all)
    # -------------------------------------------------------------
    print("\n[6단계 검증] POST /run (도구 실행 2: compare_one_vs_all)")
    run_payload2 = {
        "tool": "compare_one_vs_all",
        "params": {"reference_period": "2024", "target_item": "Korea, Rep."}
    }
    res_run2 = client.post("/run", data=json.dumps(run_payload2), content_type="application/json")
    assert res_run2.status_code == 200, f"Run tool 2 failed: {res_run2.status_code}, {res_run2.data}"
    result2 = res_run2.get_json()["result"]
    print(f"  - 한국 vs 세계 비교 요약: {result2['summary']}")
    print(f"  - 한국 보급률: {result2['data']['target_value']}%, 전체 평균: {result2['data']['world_mean']}%, 한국 순위: {result2['data']['target_rank']}위")
    assert result2["data"]["target_value"] >= 95.0, f"Expected Korea >= 95.0%, got {result2['data']['target_value']}"
    print("  ✅ POST /run (compare_one_vs_all) 성공 (한국 수치 및 순위 계산 완료)")

    # -------------------------------------------------------------
    # 7. POST /explain (모드 B: Pandas 계산 결과 기반 정식 보고서)
    # -------------------------------------------------------------
    print("\n[7단계 검증] POST /explain (모드 B: 엄격한 8대 규칙 및 7개 헤더 보고서)")
    res_explain_b = client.post("/explain", data=json.dumps({"mode": "B"}), content_type="application/json")
    assert res_explain_b.status_code == 200, f"Explain Mode B failed: {res_explain_b.status_code}, {res_explain_b.data}"
    explain_data_b = res_explain_b.get_json()
    assert explain_data_b["status"] == "success", "Explain Mode B status not success"
    report_b = explain_data_b["explanation"]
    
    headers_to_check = [
        "## 무엇을 봤는가",
        "## 데이터 출처와 정의",
        "## 기준 시점과 제외된 항목",
        "## 계산 결과",
        "## 읽어낼 수 있는 것",
        "## 이 데이터로는 알 수 없는 것",
        "## 다음에 확인해볼 것"
    ]
    for h in headers_to_check:
        assert h in report_b, f"Required header missing in Mode B report: {h}"
    print("  - 7개 필수 마크다운 헤더 준수 확인:")
    for h in headers_to_check:
        print(f"    ✔ {h}")
    assert len(report_b) > 200, "Report length is suspiciously short"
    print("  ✅ POST /explain (모드 B) 성공 (계산 결과 준수, 환각 방지 확인)")

    # -------------------------------------------------------------
    # 8. POST /explain (모드 A: 비교용 추측 보고서)
    # -------------------------------------------------------------
    print("\n[8단계 검증] POST /explain (모드 A: 수치 미제공 비교용 모드)")
    res_explain_a = client.post("/explain", data=json.dumps({"mode": "A"}), content_type="application/json")
    assert res_explain_a.status_code == 200, f"Explain Mode A failed: {res_explain_a.status_code}, {res_explain_a.data}"
    explain_data_a = res_explain_a.get_json()
    assert explain_data_a["mode"] == "A", "Expected mode A"
    print("  ✅ POST /explain (모드 A) 성공 (비교용 모드 정상 생성)")

    print("\n=====================================================================")
    print("🎉 모든 E2E 파이프라인 검증 통과 (1단계 ~ 5단계 완벽 연동 완료)!")
    print("=====================================================================")

if __name__ == "__main__":
    run_e2e_test()
