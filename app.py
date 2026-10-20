import os
import io
import csv
import glob
import json
import time
import logging
from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from google import genai
from google.genai import types
import tools

# 환경변수 로드 (.env)
load_dotenv()

# 로깅 설정 (print 대신 Python standard logging 모듈 사용)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("DataInsightBuilder")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "data-insight-builder-secret-8282")
SITE_PASSWORD = os.getenv("SITE_PASSWORD", "8282")

# 환경변수 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

# 서버 메모리에 보관할 단 1개의 활성 데이터셋
CURRENT_DATASET = {
    "df": None,
    "filename": None,
    "file_size": 0,
    "encoding": None,
    "skiprows": 0,
    "diagnostics": None,
    "last_run_result": None
}

def detect_header_row(lines, max_check=25):
    """앞쪽 max_check개 줄을 검사하여 실제 표 헤더 행 인덱스를 찾습니다."""
    candidates = []
    for idx, line in enumerate(lines[:max_check]):
        if not line.strip():
            continue
        try:
            row = next(csv.reader([line]))
        except Exception:
            continue
        candidates.append({
            "idx": idx,
            "total_cols": len(row),
            "non_empty_count": len([c for c in row if c.strip()]),
            "row": row
        })
    if not candidates:
        return 0

    max_cols = max(c["total_cols"] for c in candidates)
    for c in candidates:
        if c["total_cols"] == max_cols:
            return c["idx"]
    return 0

def count_filled(series):
    """NaN과 빈 문자열을 제외한 유효 데이터 개수를 반환합니다."""
    valid = series.dropna()
    valid_str = valid.astype(str).str.strip()
    return int(((valid_str != "") & (valid_str.str.lower() != "nan")).sum())

def try_load_indicator_info():
    """data 폴더 내의 Metadata_Indicator CSV에서 지표 정의와 출처를 읽어옵니다."""
    matches = glob.glob("data/**/Metadata_Indicator*.csv", recursive=True)
    if matches:
        try:
            m_df = pd.read_csv(matches[0])
            note = m_df["SOURCE_NOTE"].iloc[0] if "SOURCE_NOTE" in m_df.columns else ""
            org = m_df["SOURCE_ORGANIZATION"].iloc[0] if "SOURCE_ORGANIZATION" in m_df.columns else ""
            name = m_df["INDICATOR_NAME"].iloc[0] if "INDICATOR_NAME" in m_df.columns else "인터넷 이용자 비율"
            return f"지표명: {name}\n정의: {note}\n출처 기관: {org}"
        except Exception:
            pass
    return "지표명: 인터넷 이용자 비율 (% of population)\n정의: 지난 3개월 동안 PC, 스마트폰 등을 통해 인터넷을 사용한 사람 비율\n출처 기관: ITU (국제전기통신연합) / World Bank"

def call_gemini_with_retry(prompt, config=None, retries=3):
    """일시적 503 에러나 네트워크 지연에 대비한 Gemini API 재시도 헬퍼 함수입니다."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    last_err = None
    for attempt in range(retries):
        try:
            if config:
                return client.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=config)
            else:
                return client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        except Exception as e:
            last_err = e
            logger.warning(f"[AI RETRY] Gemini 호출 실패 (시도 {attempt+1}/{retries}): {str(e)}")
            time.sleep(2)
    raise last_err

@app.before_request
def require_login():
    """비밀번호 인증 검사 (정적 파일 및 공개 엔드포인트 제외)"""
    if request.path.startswith("/static") or request.path in ["/login", "/health"]:
        return None
    if not session.get("authenticated"):
        if request.method == "POST":
            return jsonify({"status": "error", "message": "접근 권한이 없습니다. 먼저 비밀번호를 입력해 주세요."}), 401
        return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(silent=True) or {}
            pwd = str(data.get("password", "")).strip()
        else:
            pwd = str(request.form.get("password", "")).strip()

        if pwd == SITE_PASSWORD:
            session["authenticated"] = True
            logger.info("[AUTH] 로그인 성공 (비밀번호 일치)")
            if request.is_json:
                return jsonify({"status": "success", "redirect": "/"})
            return redirect(url_for("index"))
        else:
            logger.warning("[AUTH] 로그인 실패: 잘못된 비밀번호")
            if request.is_json:
                return jsonify({"status": "error", "message": "비밀번호가 올바르지 않습니다."}), 401
            error = "비밀번호가 올바르지 않습니다. 다시 입력해 주세요."

    if session.get("authenticated"):
        return redirect(url_for("index"))

    return render_template("login.html", error=error)

@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    logger.info("[AUTH] 로그아웃 완료")
    return redirect(url_for("login"))

@app.route("/", methods=["GET"])
def index():
    logger.info("[REQUEST] GET /")
    index_path = os.path.join(app.template_folder, "index.html")
    if os.path.exists(index_path):
        return render_template("index.html")
    return "AI Data Insight Builder 서버가 정상 작동 중입니다. (GET /health 로 상태 확인 가능)"

@app.route("/health", methods=["GET"])
def health():
    logger.info("[REQUEST] GET /health")
    is_key_set = bool(GEMINI_API_KEY and GEMINI_API_KEY.strip() and GEMINI_API_KEY != "your_gemini_api_key_here")
    
    res = {
        "status": "ok",
        "api_key_configured": is_key_set,
        "model": GEMINI_MODEL
    }
    logger.info(f"[RESPONSE] status=200 api_key_configured={is_key_set} model={GEMINI_MODEL}")
    return jsonify(res)

@app.route("/inspect", methods=["POST"])
def inspect():
    logger.info("[REQUEST] POST /inspect")
    
    if "file" not in request.files:
        logger.warning("[ERROR] 파일이 전송되지 않음")
        return jsonify({"status": "error", "message": "업로드된 파일이 없습니다. CSV 파일을 선택해 주세요."}), 400
    
    file = request.files["file"]
    filename = file.filename or ""
    
    if not filename:
        logger.warning("[ERROR] 파일명이 비어있음")
        return jsonify({"status": "error", "message": "선택된 파일이 없습니다."}), 400
        
    if not filename.lower().endswith(".csv"):
        logger.warning(f"[ERROR] 잘못된 확장자: {filename}")
        return jsonify({"status": "error", "message": "CSV(.csv) 파일만 업로드할 수 있습니다."}), 400

    raw_bytes = file.read()
    file_size = len(raw_bytes)
    logger.info(f"[FILE] name={filename} size={file_size} bytes")

    if file_size == 0:
        logger.warning("[ERROR] 빈 파일")
        return jsonify({"status": "error", "message": "파일의 내용이 비어 있습니다(0 바이트)."}), 400

    encodings_to_try = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    detected_encoding = None
    decoded_text = None

    for enc in encodings_to_try:
        try:
            decoded_text = raw_bytes.decode(enc)
            detected_encoding = enc
            logger.info(f"[ENCODING] {enc} 성공")
            break
        except UnicodeDecodeError:
            logger.info(f"[ENCODING] {enc} 실패, 다음 인코딩 시도")
            continue

    if not detected_encoding or decoded_text is None:
        logger.error("[ERROR] 모든 인코딩(utf-8-sig, utf-8, cp949, euc-kr) 시도 실패")
        return jsonify({
            "status": "error",
            "message": "지원되는 인코딩(UTF-8, CP949, EUC-KR)으로 파일을 읽을 수 없습니다."
        }), 400

    lines = decoded_text.splitlines()
    if not lines:
        return jsonify({"status": "error", "message": "파일에 읽을 수 있는 데이터 행이 없습니다."}), 400

    skiprows = detect_header_row(lines)
    logger.info(f"[HEADER] 헤더 줄 감지 결과 (건너뛴 줄 수: {skiprows})")

    try:
        df = pd.read_csv(io.StringIO(decoded_text), skiprows=skiprows)
    except Exception as e:
        logger.error(f"[ERROR] Pandas CSV 파싱 실패: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"CSV 내용을 표로 변환하는 중 오류가 발생했습니다: {str(e)}"
        }), 400

    rows, cols = df.shape
    logger.info(f"[CSV] parsing 완료 rows={rows} columns={cols}")

    dtypes = {str(c): str(t) for c, t in df.dtypes.items()}
    numeric_cols = []
    string_cols = []
    candidate_year_cols = []

    for c in df.columns:
        c_str = str(c).strip()
        if c_str.isdigit() and len(c_str) == 4 and 1900 <= int(c_str) <= 2100:
            candidate_year_cols.append(c_str)
        
        if pd.api.types.is_numeric_dtype(df[c]):
            numeric_cols.append(c_str)
        else:
            try:
                converted = pd.to_numeric(df[c].dropna(), errors="coerce")
                if not converted.isna().all() and converted.notna().sum() > (len(df[c].dropna()) * 0.5):
                    numeric_cols.append(c_str)
                else:
                    string_cols.append(c_str)
            except Exception:
                string_cols.append(c_str)

    missing_values = {}
    for c in df.columns:
        c_str = str(c)
        filled_cnt = count_filled(df[c])
        miss_cnt = rows - filled_cnt
        missing_values[c_str] = {
            "missing_count": miss_cnt,
            "missing_ratio": round((miss_cnt / rows) * 100, 1) if rows > 0 else 0
        }

    duplicate_rows_count = int(df.duplicated().sum())
    unnamed_cols = [str(c) for c in df.columns if str(c).startswith("Unnamed:") or not str(c).strip()]
    completely_empty_cols = [str(c) for c in df.columns if missing_values[str(c)]["missing_count"] == rows]

    year_coverage = {}
    for y in sorted(candidate_year_cols, key=lambda x: int(x)):
        filled_cnt = count_filled(df[y])
        year_coverage[y] = {
            "filled_count": filled_cnt,
            "filled_ratio": round((filled_cnt / rows) * 100, 1) if rows > 0 else 0
        }

    recommended_year = None
    if candidate_year_cols:
        for y in sorted(candidate_year_cols, key=lambda x: int(x), reverse=True):
            if year_coverage[y]["filled_ratio"] >= 70.0:
                recommended_year = y
                break
        if not recommended_year:
            recommended_year = max(candidate_year_cols, key=lambda y: year_coverage[y]["filled_count"])

    agg_keywords = [
        "world", "oecd members", "oecd", "euro area", "european union", 
        "high income", "low income", "middle income", "income", "area", 
        "total", "ida & ibrd", "dividend", "small states", "demographic"
    ]
    name_col = "Country Name" if "Country Name" in df.columns else (string_cols[0] if string_cols else df.columns[0])
    aggregate_candidates = []
    
    if name_col in df.columns:
        for idx, val in enumerate(df[name_col]):
            val_str = str(val).lower()
            for kw in agg_keywords:
                if kw in val_str:
                    aggregate_candidates.append({
                        "index": idx,
                        "label": str(val),
                        "matched_keyword": kw
                    })
                    break

    warnings = []
    if skiprows > 0:
        warnings.append(f"상단 {skiprows}개 줄의 메타데이터/안내문을 건너뛰고 {skiprows + 1}번째 줄을 열 이름으로 인식했습니다.")
    if unnamed_cols:
        warnings.append(f"이름이 없거나 줄 끝 쉼표로 인해 생긴 Unnamed 열이 {len(unnamed_cols)}개 발견되었습니다: {unnamed_cols}")
    if completely_empty_cols:
        warnings.append(f"전체 행이 결측치(빈칸)인 열이 {len(completely_empty_cols)}개 있습니다.")
    if duplicate_rows_count > 0:
        warnings.append(f"내용이 완전히 동일한 중복 행이 {duplicate_rows_count}개 발견되었습니다.")
    if candidate_year_cols and recommended_year:
        latest_col_year = sorted(candidate_year_cols, key=lambda x: int(x))[-1]
        if latest_col_year != recommended_year:
            warnings.append(
                f"가장 최근 열({latest_col_year}년)은 결측치가 많아({year_coverage[latest_col_year]['filled_ratio']}%), "
                f"데이터가 충분한 {recommended_year}년({year_coverage[recommended_year]['filled_ratio']}%)을 권장 기준연도로 설정했습니다."
            )
    if aggregate_candidates:
        warnings.append(f"순수 국가가 아닌 지역/소득 묶음 집계 행으로 의심되는 항목이 {len(aggregate_candidates)}개 발견되었습니다.")

    raw_preview = df.head(10).to_dict(orient="records")
    preview_rows = tools.sanitize_records(raw_preview)

    diagnostics = {
        "file_info": {
            "filename": filename,
            "file_size": file_size,
            "encoding": detected_encoding,
            "skiprows": skiprows
        },
        "dimensions": {
            "row_count": rows,
            "col_count": cols,
            "columns": [str(c) for c in df.columns]
        },
        "dtypes": dtypes,
        "column_categories": {
            "numeric_columns": numeric_cols,
            "string_columns": string_cols,
            "candidate_year_columns": candidate_year_cols
        },
        "missing_values": missing_values,
        "duplicate_rows": duplicate_rows_count,
        "unnamed_or_empty_cols": unnamed_cols,
        "year_coverage": year_coverage,
        "recommended_reference_year": recommended_year,
        "aggregate_candidates": aggregate_candidates,
        "preview": preview_rows,
        "warnings": warnings,
        "storage_notice": "업로드된 데이터는 서버 메모리에만 1개 보관되며, 서버를 재시작하면 사라집니다."
    }

    CURRENT_DATASET["df"] = df
    CURRENT_DATASET["filename"] = filename
    CURRENT_DATASET["file_size"] = file_size
    CURRENT_DATASET["encoding"] = detected_encoding
    CURRENT_DATASET["skiprows"] = skiprows
    CURRENT_DATASET["diagnostics"] = diagnostics
    CURRENT_DATASET["last_run_result"] = None

    logger.info(f"[DIAGNOSE] 진단 완료 warnings={len(warnings)} aggregates={len(aggregate_candidates)} rec_year={recommended_year}")
    logger.info(f"[RESPONSE] status=200 rows={rows} cols={cols}")

    return jsonify({
        "status": "success",
        "diagnostics": diagnostics
    })

@app.route("/suggest", methods=["POST"])
def suggest():
    logger.info("[REQUEST] POST /suggest")
    
    if CURRENT_DATASET["diagnostics"] is None or CURRENT_DATASET["df"] is None:
        logger.warning("[ERROR] 업로드된 데이터셋 없음")
        return jsonify({
            "status": "error",
            "message": "먼저 CSV 파일을 업로드하여 진단을 수행해 주세요."
        }), 400
        
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        logger.error("[ERROR] API Key 미설정")
        return jsonify({
            "status": "error",
            "message": "Gemini API 키가 설정되지 않았습니다. .env 파일에 유효한 GEMINI_API_KEY를 입력해 주세요."
        }), 500

    diagnostics = CURRENT_DATASET["diagnostics"]
    
    diag_summary = {
        "filename": diagnostics["file_info"]["filename"],
        "row_count": diagnostics["dimensions"]["row_count"],
        "col_count": diagnostics["dimensions"]["col_count"],
        "recommended_reference_year": diagnostics["recommended_reference_year"],
        "year_columns_range": f"{diagnostics['column_categories']['candidate_year_columns'][0]}~{diagnostics['column_categories']['candidate_year_columns'][-1]}" if diagnostics['column_categories']['candidate_year_columns'] else "없음",
        "aggregate_candidates_count": len(diagnostics["aggregate_candidates"]),
        "key_warnings": diagnostics["warnings"][:3]
    }

    prompt = f"""당신은 데이터 분석 교육용 AI 어시스턴트입니다.
업로드된 데이터셋의 진단 요약과 사용 가능한 분석 도구 카탈로그를 확인하고,
초보자에게 가장 가치 있고 유익한 분석 3~5개를 도구 카탈로그에서 골라 제안하세요.

[진단 결과 요약]
{json.dumps(diag_summary, ensure_ascii=False, indent=2)}

[도구 카탈로그]
{json.dumps(tools.TOOL_CATALOG, ensure_ascii=False, indent=2)}

[엄격한 규칙]
1. 도구 카탈로그에 명시된 12개 도구 이름(tool)만 사용할 수 있습니다. 카탈로그에 없는 도구는 절대 제안하지 마세요.
2. 데이터에 실제로 존재하는 열/연도만 파라미터로 지정하세요. (권장 기준 연도: {diagnostics['recommended_reference_year']})
3. 직접 계산하거나 숫자를 지어내지 마세요.
4. 반드시 아래 JSON 형식으로만 응답하세요:
{{
  "suggestions": [
    {{
      "tool": "도구이름",
      "params": {{ "파라미터키": "값" }},
      "reference_period": "기준시점",
      "why": "이 분석이 이 데이터에서 의미 있는 이유",
      "caution": "해석할 때 주의할 점"
    }}
  ]
}}"""

    logger.info(f"[AI] suggest 요청 시작 (model={GEMINI_MODEL})")
    
    try:
        response = call_gemini_with_retry(
            prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2)
        )
        logger.info("[AI] suggest 응답 수신 완료")
        
        raw_text = response.text or "{}"
        parsed_result = json.loads(raw_text)
        suggestions = parsed_result.get("suggestions", [])
        
        valid_suggestions = []
        for s in suggestions:
            tool_name = s.get("tool")
            if tool_name in tools.TOOL_RUN_MAP:
                if not isinstance(s.get("params"), dict):
                    s["params"] = {}
                if s.get("reference_period") and "reference_period" not in s["params"]:
                    s["params"]["reference_period"] = s["reference_period"]
                valid_suggestions.append(s)

        logger.info(f"[AI] JSON 파싱 결과: 총 {len(valid_suggestions)}개 제안 확정")
        logger.info(f"[RESPONSE] status=200 suggestions_count={len(valid_suggestions)}")

        return jsonify({
            "status": "success",
            "model_used": GEMINI_MODEL,
            "suggestions": valid_suggestions
        })
        
    except json.JSONDecodeError as je:
        logger.error(f"[ERROR] JSON 파싱 실패: {str(je)}")
        return jsonify({"status": "error", "message": "Gemini 응답을 JSON으로 변환하는 데 실패했습니다."}), 500
    except Exception as e:
        logger.error(f"[ERROR] Gemini API 호출 실패: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"AI 분석 제안 생성 중 오류가 발생했습니다: {str(e)}"
        }), 500

@app.route("/run", methods=["POST"])
def run_tool():
    logger.info("[REQUEST] POST /run")
    
    if CURRENT_DATASET["df"] is None:
        logger.warning("[ERROR] 실행할 데이터셋 없음")
        return jsonify({
            "status": "error", 
            "message": "먼저 CSV 파일을 업로드하여 진단을 수행해 주세요."
        }), 400
        
    req_data = request.get_json(silent=True) or {}
    tool_name = req_data.get("tool")
    
    if not tool_name:
        logger.warning("[ERROR] 도구명 미전달")
        return jsonify({
            "status": "error", 
            "message": "실행할 분석 도구(tool)를 지정해 주세요."
        }), 400
        
    if tool_name not in tools.TOOL_RUN_MAP:
        logger.warning(f"[ERROR] 존재하지 않는 도구: {tool_name}")
        return jsonify({
            "status": "error", 
            "message": f"'{tool_name}'은(는) 유효한 분석 도구가 아닙니다. 12개 카탈로그 도구 중에서 선택해 주세요."
        }), 400
        
    params = req_data.get("params", {})
    df = CURRENT_DATASET["df"]
    
    try:
        result = tools.TOOL_RUN_MAP[tool_name](df, params)
        if result.get("status") == "error":
            logger.warning(f"[TOOL ERROR] {tool_name}: {result.get('message')}")
            return jsonify(result), 400
            
        CURRENT_DATASET["last_run_result"] = result
        
        logger.info(f"[TOOL] {tool_name}, params={params}, rows_used={result.get('rows_used')}, rows_excluded={result.get('rows_excluded')}")
        logger.info(f"[RESPONSE] status=200 tool={tool_name}")
        
        return jsonify({
            "status": "success",
            "result": result
        })
    except Exception as e:
        logger.error(f"[ERROR] 도구 실행 실패 ({tool_name}): {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"분석 도구 실행 중 오류가 발생했습니다: {str(e)}"
        }), 500

@app.route("/explain", methods=["POST"])
def explain():
    logger.info("[REQUEST] POST /explain")
    
    if CURRENT_DATASET["df"] is None or CURRENT_DATASET["diagnostics"] is None:
        return jsonify({
            "status": "error",
            "message": "먼저 CSV 파일을 업로드하여 진단을 수행해 주세요."
        }), 400
        
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        return jsonify({
            "status": "error",
            "message": "Gemini API 키가 설정되지 않았습니다. .env 파일에 유효한 GEMINI_API_KEY를 입력해 주세요."
        }), 500

    req_data = request.get_json(silent=True) or {}
    mode = str(req_data.get("mode", "B")).upper()
    
    diagnostics = CURRENT_DATASET["diagnostics"]
    last_run = CURRENT_DATASET.get("last_run_result")
    
    # 모드 A (비교용, 의도적으로 허술하게): 계산 결과 없이 진단 요약만 주고 보고서 요구
    if mode == "A":
        logger.info("[AI] explain 요청 시작 (모드 A: 비교용/계산결과 미제공)")
        prompt = f"""당신은 일반 AI 어시스턴트입니다.
다음 데이터셋의 진단 요약만 보고 이 데이터를 종합적으로 분석한 보고서를 작성해 주세요.
(참고: 당신에게는 Pandas의 실제 계산 결과 표가 주어지지 않았습니다. 기억이나 추측으로 수치와 순위를 그럴듯하게 적어보세요.)

[데이터셋 정보]
파일명: {diagnostics['file_info']['filename']}
행 수: {diagnostics['dimensions']['row_count']}개, 열 수: {diagnostics['dimensions']['col_count']}개
연도 열: {diagnostics['column_categories']['candidate_year_columns'][0]}~{diagnostics['column_categories']['candidate_year_columns'][-1]}
권장 기준연도: {diagnostics['recommended_reference_year']}

자유로운 형식으로 한국 및 세계 인터넷 보급률 현황 보고서를 작성해 주세요."""

    # 모드 B (정식): Pandas 계산 결과만 전달하고 8가지 엄격한 규칙으로 해석
    else:
        if last_run is None:
            return jsonify({
                "status": "error",
                "message": "정식 해석(모드 B)을 위해 먼저 분석 도구를 실행(POST /run)해 주세요."
            }), 400
            
        logger.info(f"[AI] explain 요청 시작 (모드 B: 정식/도구={last_run.get('tool')})")
        indicator_info = try_load_indicator_info()
        
        prompt = f"""당신은 데이터 분석 교육용 AI 어시스턴트입니다.
Python Pandas가 엄밀하게 계산한 분석 결과만을 전달받았습니다.
아래 8가지 엄격한 규칙을 100% 준수하여 공식 데이터 분석 보고서를 작성하세요.

[Python Pandas 계산 결과]
{json.dumps(last_run, ensure_ascii=False, indent=2)}

[지표 정의 및 출처 정보]
{indicator_info}

[엄격한 작성 규칙 - 위반 시 감점]
1. 제공된 계산 결과에 있는 숫자만 사용하세요. 직접 계산하거나 숫자를 지어내지 마세요.
2. 데이터에 없는 국가·연도·열을 언급하지 마세요.
3. 기준 시점과 제외된 행 수 및 이유(집계 행, 결측 등)를 반드시 본문에 명시하세요.
4. 상관관계를 인과관계로 표현하지 마세요.
5. 지표의 정의와 출처를 보고서 앞부분에 표기하세요.
6. 확인할 수 없는 것은 "이 데이터로는 확인할 수 없다"라고 분명히 쓰세요.
7. 중학생도 이해할 수 있게 명쾌하게 쓰되 정확성을 절대 희생하지 마세요.
8. 아래 제시된 7개 마크다운 헤더 형식을 정확히 지켜서 작성하세요.

[출력 형식 - 반드시 아래 7개 마크다운 헤더로 작성]
## 무엇을 봤는가
## 데이터 출처와 정의
## 기준 시점과 제외된 항목
## 계산 결과
## 읽어낼 수 있는 것
## 이 데이터로는 알 수 없는 것
## 다음에 확인해볼 것"""

    try:
        response = call_gemini_with_retry(prompt)
        report_text = response.text or "보고서 내용이 비어 있습니다."
        logger.info(f"[AI] explain 응답 수신 완료 (모드: {mode})")
        logger.info(f"[RESPONSE] status=200 mode={mode}")
        
        return jsonify({
            "status": "success",
            "mode": mode,
            "tool_analyzed": last_run.get("tool") if last_run else None,
            "explanation": report_text
        })
    except Exception as e:
        logger.error(f"[ERROR] Gemini 해석 생성 실패 (모드 {mode}): {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"AI 분석 보고서 생성 중 오류가 발생했습니다: {str(e)}"
        }), 500

@app.route("/ask", methods=["POST"])
def ask_question():
    logger.info("[REQUEST] POST /ask")
    
    if CURRENT_DATASET["df"] is None or CURRENT_DATASET["diagnostics"] is None:
        return jsonify({
            "status": "error",
            "message": "먼저 CSV 파일을 업로드하여 진단을 수행해 주세요."
        }), 400
        
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        return jsonify({
            "status": "error",
            "message": "Gemini API 키가 설정되지 않았습니다. .env 파일에 유효한 GEMINI_API_KEY를 입력해 주세요."
        }), 500

    req_data = request.get_json(silent=True) or {}
    user_question = req_data.get("question", "").strip()
    
    if not user_question:
        return jsonify({
            "status": "error",
            "message": "질문 내용을 입력해 주세요."
        }), 400

    diagnostics = CURRENT_DATASET["diagnostics"]
    last_run = CURRENT_DATASET.get("last_run_result")
    indicator_info = try_load_indicator_info()

    context_data = {
        "file_info": {
            "filename": diagnostics["file_info"]["filename"],
            "row_count": diagnostics["dimensions"]["row_count"],
            "col_count": diagnostics["dimensions"]["col_count"],
            "recommended_reference_year": diagnostics["recommended_reference_year"],
            "aggregate_candidates_count": len(diagnostics["aggregate_candidates"]),
            "warnings": diagnostics["warnings"]
        },
        "indicator_metadata": indicator_info,
        "last_calculated_result": last_run
    }

    prompt = f"""당신은 데이터 분석 교육용 AI 멘토입니다.
사용자가 업로드된 데이터셋 및 Pandas 계산 결과를 바탕으로 질문을 남겼습니다.
아래 제공된 데이터 맥락 정보에만 엄밀히 근거하여 친절하고 명쾌하게 답변해 주세요.

[현재 데이터셋 맥락]
{json.dumps(context_data, ensure_ascii=False, indent=2)}

[사용자 질문]
"{user_question}"

[엄격한 답변 원칙]
1. 제공된 맥락 정보와 계산 결과에 있는 내용만을 기반으로 사실에 입각하여 답변하세요.
2. 만약 질문에 답하기 위해 필요한 정보가 이 데이터에 없다면(예: 원인 분석을 위한 다른 경제 지표, 데이터셋에 없는 연도 등), "이 데이터셋에는 해당 내용이 포함되어 있지 않아 확인할 수 없습니다"라고 분명하게 선을 긋고 설명하세요.
3. 숫자를 자의적으로 계산하거나 추측하여 지어내지 마세요.
4. 상관관계를 성급하게 인과관계로 비약하지 마세요.
5. 통계 초보자나 중학생도 쉽게 이해할 수 있도록 쉬운 설명과 깔끔한 마크다운 서식(소제목, 글머리 기호 등)을 사용하세요."""

    try:
        logger.info(f"[AI] ask_question 요청: '{user_question[:30]}...'")
        response = call_gemini_with_retry(prompt)
        answer_text = response.text or "답변 내용을 생성하지 못했습니다."
        logger.info("[AI] ask_question 응답 수신 완료")
        logger.info("[RESPONSE] status=200 endpoint=/ask")
        
        return jsonify({
            "status": "success",
            "question": user_question,
            "answer": answer_text
        })
    except Exception as e:
        logger.error(f"[ERROR] Gemini 추가 질문 답변 실패: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"AI 답변 생성 중 오류가 발생했습니다: {str(e)}"
        }), 500

if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    port = int(os.getenv("FLASK_PORT", 5001))
    logger.info(f"AI Data Insight Builder 서버 시작 (Port: {port}, Debug: {debug_mode})")
    app.run(host="127.0.0.1", port=port, debug=debug_mode)
