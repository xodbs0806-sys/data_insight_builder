import os
import glob
import numpy as np
import pandas as pd

AGG_KEYWORDS = [
    "world", "oecd members", "oecd", "euro area", "european union", 
    "high income", "low income", "middle income", "income", "area", 
    "total", "ida & ibrd", "dividend", "small states", "demographic"
]

def find_label_col(df):
    """국가명이나 항목 이름을 나타내는 라벨 열을 찾습니다."""
    for c in ["Country Name", "Name", "국가명", "항목명", "지역"]:
        if c in df.columns:
            return c
    for c in df.columns:
        if df[c].dtype == object and not str(c).startswith("Unnamed"):
            return c
    return df.columns[0]

def find_year_cols(df):
    """4자리 숫자(1900~2100)로 된 연도 열 목록을 반환합니다."""
    years = []
    for c in df.columns:
        c_str = str(c).strip()
        if c_str.isdigit() and len(c_str) == 4 and 1900 <= int(c_str) <= 2100:
            years.append(c_str)
    return sorted(years, key=lambda x: int(x))

def filter_aggregates(df, exclude=True, label_col=None):
    """집계 행(World, High income 등)을 필터링합니다."""
    if label_col is None:
        label_col = find_label_col(df)
        
    if not exclude or label_col not in df.columns:
        return df.copy(), 0, []
        
    is_agg = df[label_col].astype(str).str.lower().apply(
        lambda x: any(kw in x for kw in AGG_KEYWORDS)
    )
    agg_df = df[is_agg]
    clean_df = df[~is_agg].copy()
    return clean_df, len(agg_df), agg_df[label_col].tolist()

def sanitize_records(records):
    """JSON 직렬화가 가능하도록 NaN과 Infinity를 None으로 변환합니다."""
    cleaned = []
    for row in records:
        cleaned_row = {}
        for k, v in row.items():
            if pd.isna(v) or v is None or (isinstance(v, float) and (np.isneginf(v) or np.isposinf(v))):
                cleaned_row[k] = None
            elif isinstance(v, (np.floating, float)):
                cleaned_row[k] = round(float(v), 2)
            elif isinstance(v, (np.integer, int)):
                cleaned_row[k] = int(v)
            else:
                cleaned_row[k] = v
        cleaned.append(cleaned_row)
    return cleaned

def try_load_metadata():
    """data 폴더 내의 Metadata_Country CSV가 있으면 로드합니다."""
    matches = glob.glob("data/**/Metadata_Country*.csv", recursive=True)
    if matches:
        try:
            return pd.read_csv(matches[0])
        except Exception:
            return None
    return None

# ==========================================
# 도구 1: reshape_wide_to_long
# ==========================================
def reshape_wide_to_long(df, params=None):
    params = params or {}
    exclude_aggs = params.get("exclude_aggregates", True)
    drop_na = params.get("drop_na", True)
    
    label_col = find_label_col(df)
    year_cols = find_year_cols(df)
    
    if not year_cols:
        return {"status": "error", "message": "변환할 연도 열(4자리 숫자)을 찾을 수 없습니다."}
        
    filtered_df, agg_count, _ = filter_aggregates(df, exclude=exclude_aggs, label_col=label_col)
    id_cols = [c for c in filtered_df.columns if c not in year_cols and not str(c).startswith("Unnamed")]
    
    melted = pd.melt(filtered_df, id_vars=id_cols, value_vars=year_cols, var_name="Year", value_name="Value")
    initial_melted_rows = len(melted)
    if drop_na:
        valid_mask = melted["Value"].notna() & (melted["Value"].astype(str).str.strip() != "") & (melted["Value"].astype(str).str.lower() != "nan")
        melted = melted[valid_mask].copy()
        
    try:
        melted["Value"] = pd.to_numeric(melted["Value"])
    except Exception:
        pass
        
    na_excluded = initial_melted_rows - len(melted)
    exclusion_reason = []
    if exclude_aggs and agg_count > 0:
        exclusion_reason.append(f"집계 행 {agg_count}개 제외")
    if drop_na and na_excluded > 0:
        exclusion_reason.append(f"연도별 결측 셀 {na_excluded}개 제외")
        
    min_year, max_year = year_cols[0], year_cols[-1]
    preview_records = sanitize_records(melted.head(100).to_dict(orient="records"))
    
    return {
        "status": "success",
        "tool": "reshape_wide_to_long",
        "summary": f"{min_year}년부터 {max_year}년까지의 연도 열을 [항목, 연도, 값] 형태의 긴 표로 변환했습니다.",
        "reference_period": f"{min_year}~{max_year}",
        "rows_used": len(melted),
        "rows_excluded": agg_count + (na_excluded if drop_na else 0),
        "exclusion_reason": ", ".join(exclusion_reason) if exclusion_reason else "없음",
        "columns_used": id_cols + ["Year", "Value"],
        "unit": "% (또는 원본 지표 단위)",
        "caution": "인터넷이 없던 과거 연도의 빈칸 셀은 제외되었습니다. 집계 행 제외 여부에 따라 국가 수가 달라집니다.",
        "data": {"total_records": len(melted), "columns": list(melted.columns), "preview_sample": preview_records}
    }

# ==========================================
# 도구 2: quality_report
# ==========================================
def quality_report(df, params=None):
    params = params or {}
    exclude_aggs = params.get("exclude_aggregates", True)
    label_col = find_label_col(df)
    filtered_df, agg_count, _ = filter_aggregates(df, exclude=exclude_aggs, label_col=label_col)
    total_rows, total_cols = filtered_df.shape
    
    missing_list = []
    for c in filtered_df.columns:
        s = filtered_df[c]
        valid_cnt = ((s.notna()) & (s.astype(str).str.strip() != "") & (s.astype(str).str.lower() != "nan")).sum()
        miss_cnt = total_rows - int(valid_cnt)
        miss_ratio = round((miss_cnt / total_rows) * 100, 1) if total_rows > 0 else 0
        missing_list.append({"column": str(c), "missing_count": miss_cnt, "missing_ratio": miss_ratio, "dtype": str(s.dtype)})
        
    missing_list.sort(key=lambda x: x["missing_ratio"], reverse=True)
    duplicate_rows = int(filtered_df.duplicated().sum())
    unnamed_cols = [str(c) for c in filtered_df.columns if str(c).startswith("Unnamed:") or not str(c).strip()]
    
    return {
        "status": "success",
        "tool": "quality_report",
        "summary": f"전체 {total_rows}행 {total_cols}열에 대한 결측치, 중복, 열 구조 품질 진단 결과입니다.",
        "reference_period": "전체 데이터셋",
        "rows_used": total_rows,
        "rows_excluded": agg_count if exclude_aggs else 0,
        "exclusion_reason": f"집계 행 {agg_count}개 제외" if (exclude_aggs and agg_count > 0) else "없음",
        "columns_used": [str(c) for c in filtered_df.columns],
        "unit": "건 / %",
        "caution": "결측치가 80% 이상인 열은 단독 분석에 사용 시 왜곡 위험이 매우 높습니다.",
        "data": {"total_rows": total_rows, "total_cols": total_cols, "duplicate_rows": duplicate_rows, "unnamed_cols": unnamed_cols, "top_missing_columns": missing_list[:15], "all_column_stats": missing_list}
    }

# ==========================================
# 도구 3: year_coverage
# ==========================================
def year_coverage(df, params=None):
    params = params or {}
    exclude_aggs = params.get("exclude_aggregates", True)
    label_col = find_label_col(df)
    filtered_df, agg_count, _ = filter_aggregates(df, exclude=exclude_aggs, label_col=label_col)
    total_rows = len(filtered_df)
    year_cols = find_year_cols(filtered_df)
    
    if not year_cols:
        return {"status": "error", "message": "데이터에서 연도 열을 찾을 수 없습니다."}
        
    coverage_table = []
    for y in year_cols:
        s = filtered_df[y]
        filled_cnt = int(((s.notna()) & (s.astype(str).str.strip() != "") & (s.astype(str).str.lower() != "nan")).sum())
        ratio = round((filled_cnt / total_rows) * 100, 1) if total_rows > 0 else 0
        coverage_table.append({"year": y, "filled_count": filled_cnt, "total_rows": total_rows, "filled_ratio": ratio})
        
    rec_year = None
    for item in reversed(coverage_table):
        if item["filled_ratio"] >= 70.0:
            rec_year = item["year"]
            break
    if not rec_year and coverage_table:
        rec_year = max(coverage_table, key=lambda x: x["filled_count"])["year"]
        
    chart_data = {
        "type": "bar",
        "labels": [item["year"] for item in coverage_table],
        "datasets": [{
            "label": "데이터 충실도 (%)",
            "data": [item["filled_ratio"] for item in coverage_table],
            "backgroundColor": ["#4f46e5" if item["year"] == rec_year else "#93c5fd" for item in coverage_table]
        }]
    }
    
    return {
        "status": "success",
        "tool": "year_coverage",
        "summary": f"연도별 데이터 충실도를 분석한 결과, 가장 안정적인 권장 기준연도는 {rec_year}년입니다.",
        "reference_period": f"{year_cols[0]}~{year_cols[-1]} (권장: {rec_year})",
        "rows_used": total_rows,
        "rows_excluded": agg_count if exclude_aggs else 0,
        "exclusion_reason": f"집계 행 {agg_count}개 제외" if (exclude_aggs and agg_count > 0) else "없음",
        "columns_used": year_cols,
        "unit": "개 / %",
        "caution": f"가장 끝 연도({coverage_table[-1]['year']}년)는 충실도가 낮으므로 분석 시 {rec_year}년을 사용하는 것이 안전합니다.",
        "data": {"recommended_year": rec_year, "coverage_table": coverage_table},
        "chart_data": chart_data
    }

# ==========================================
# 도구 4: detect_aggregates
# ==========================================
def detect_aggregates(df, params=None):
    params = params or {}
    label_col = params.get("label_column") or find_label_col(df)
    if label_col not in df.columns:
        return {"status": "error", "message": f"라벨 열 '{label_col}'을 찾을 수 없습니다."}
        
    total_rows = len(df)
    agg_list = []
    clean_list = []
    for idx, val in enumerate(df[label_col]):
        val_str = str(val).lower()
        matched = None
        for kw in AGG_KEYWORDS:
            if kw in val_str:
                matched = kw
                break
        if matched:
            agg_list.append({"index": idx, "name": str(val), "matched_keyword": matched})
        else:
            clean_list.append(str(val))
            
    return {
        "status": "success",
        "tool": "detect_aggregates",
        "summary": f"전체 {total_rows}개 행 중 순수 항목 {len(clean_list)}개, 집계 후보 {len(agg_list)}개를 탐지했습니다.",
        "reference_period": "전체 데이터셋",
        "rows_used": total_rows,
        "rows_excluded": 0,
        "exclusion_reason": "없음 (전체 탐지 도구)",
        "columns_used": [label_col],
        "unit": "개 행",
        "caution": "국가 간 순위 비교나 평균을 구할 때는 반드시 집계 행을 제외해야 중복 계산을 방지할 수 있습니다.",
        "data": {"total_rows": total_rows, "pure_entities_count": len(clean_list), "aggregates_count": len(agg_list), "aggregate_candidates": agg_list, "pure_entities_sample": clean_list[:20]}
    }

# ==========================================
# 도구 5: describe_numeric
# ==========================================
def describe_numeric(df, params=None):
    params = params or {}
    exclude_aggs = params.get("exclude_aggregates", True)
    ref_period = params.get("reference_period") or params.get("value_column")
    year_cols = find_year_cols(df)
    if not ref_period:
        ref_period = year_cols[-2] if len(year_cols) >= 2 else (year_cols[-1] if year_cols else None)
        
    if not ref_period or ref_period not in df.columns:
        return {"status": "error", "message": f"분석할 숫자 열 또는 기준 연도 '{ref_period}'를 데이터에서 찾을 수 없습니다."}
        
    label_col = find_label_col(df)
    filtered_df, agg_count, _ = filter_aggregates(df, exclude=exclude_aggs, label_col=label_col)
    s = pd.to_numeric(filtered_df[ref_period], errors="coerce")
    clean_series = s[s.notna()]
    
    rows_used = len(clean_series)
    na_count = len(filtered_df) - rows_used
    stats = {
        "count": rows_used,
        "mean": round(float(clean_series.mean()), 2),
        "std": round(float(clean_series.std()), 2),
        "min": round(float(clean_series.min()), 2),
        "q25": round(float(clean_series.quantile(0.25)), 2),
        "median": round(float(clean_series.median()), 2),
        "q75": round(float(clean_series.quantile(0.75)), 2),
        "max": round(float(clean_series.max()), 2)
    }
    
    chart_data = {
        "type": "bar",
        "labels": ["최소값", "25% 분위", "중앙값", "평균값", "75% 분위", "최대값"],
        "datasets": [{
            "label": f"{ref_period} 주요 통계치 (%)",
            "data": [stats["min"], stats["q25"], stats["median"], stats["mean"], stats["q75"], stats["max"]],
            "backgroundColor": ["#94a3b8", "#cbd5e1", "#3b82f6", "#1d4ed8", "#cbd5e1", "#94a3b8"]
        }]
    }
    
    return {
        "status": "success",
        "tool": "describe_numeric",
        "summary": f"{ref_period}년 유효 국가 {rows_used}곳의 평균은 {stats['mean']}%, 중앙값은 {stats['median']}%입니다.",
        "reference_period": str(ref_period),
        "rows_used": rows_used,
        "rows_excluded": agg_count + na_count,
        "exclusion_reason": f"집계 행 {agg_count}개 제외, 결측 행 {na_count}개 제외",
        "columns_used": [ref_period],
        "unit": "%",
        "caution": "평균값과 중앙값의 차이가 클 경우 일부 극단치로 인한 왜곡이 존재할 수 있습니다.",
        "data": stats,
        "chart_data": chart_data
    }

# ==========================================
# 도구 6: trend_line
# ==========================================
def trend_line(df, params=None):
    params = params or {}
    label_col = params.get("label_column") or find_label_col(df)
    items = params.get("items") or ["Korea, Rep.", "United States", "Japan", "Germany", "World"]
    year_cols = find_year_cols(df)
    
    matched_df = df[df[label_col].isin(items)].copy()
    if matched_df.empty:
        matched_df = df.head(3).copy()
        items = matched_df[label_col].tolist()
        
    colors = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#9333ea"]
    datasets = []
    trend_table = []
    
    for idx, (_, row) in enumerate(matched_df.iterrows()):
        c_name = str(row[label_col])
        values = [round(float(row[y]), 2) if pd.notna(row[y]) and str(row[y]).strip() != "" else None for y in year_cols]
        color = colors[idx % len(colors)]
        datasets.append({
            "label": c_name,
            "data": values,
            "borderColor": color,
            "backgroundColor": color,
            "fill": False,
            "tension": 0.2
        })
        valid_vals = [v for v in values if v is not None]
        trend_table.append({"name": c_name, "start_val": valid_vals[0] if valid_vals else None, "latest_val": valid_vals[-1] if valid_vals else None})
        
    return {
        "status": "success",
        "tool": "trend_line",
        "summary": f"{len(matched_df)}개 대상의 {year_cols[0]}~{year_cols[-1]}년 시계열 추이입니다.",
        "reference_period": f"{year_cols[0]}~{year_cols[-1]}",
        "rows_used": len(matched_df),
        "rows_excluded": len(df) - len(matched_df),
        "exclusion_reason": f"선택 항목 외 나머지 {len(df) - len(matched_df)}개 행 제외",
        "columns_used": [label_col] + year_cols,
        "unit": "%",
        "caution": "연도별로 통계 조사가 비어있는 구간은 선이 끊기거나 보간되어 보일 수 있습니다.",
        "data": {"selected_items": items, "years": year_cols, "summary_table": trend_table},
        "chart_data": {"type": "line", "labels": year_cols, "datasets": datasets}
    }

# ==========================================
# 도구 7: top_bottom_n (기준시점 필수)
# ==========================================
def top_bottom_n(df, params=None):
    params = params or {}
    ref_period = params.get("reference_period")
    if not ref_period:
        return {"status": "error", "message": "기준 시점(reference_period)은 필수 파라미터입니다. (예: '2024')"}
        
    n = int(params.get("n", 10))
    exclude_aggs = params.get("exclude_aggregates", True)
    label_col = params.get("label_column") or find_label_col(df)
    
    filtered_df, agg_count, _ = filter_aggregates(df, exclude=exclude_aggs, label_col=label_col)
    filtered_df["_numeric_val"] = pd.to_numeric(filtered_df[ref_period], errors="coerce")
    valid_df = filtered_df.dropna(subset=["_numeric_val"]).sort_values(by="_numeric_val", ascending=False)
    
    top_records = sanitize_records(valid_df.head(n)[[label_col, "_numeric_val"]].rename(columns={"_numeric_val": "value"}).to_dict(orient="records"))
    bottom_records = sanitize_records(valid_df.tail(n)[[label_col, "_numeric_val"]].sort_values(by="_numeric_val").rename(columns={"_numeric_val": "value"}).to_dict(orient="records"))
    
    return {
        "status": "success",
        "tool": "top_bottom_n",
        "summary": f"{ref_period}년 기준 상위 {len(top_records)}개국과 하위 {len(bottom_records)}개국 순위입니다.",
        "reference_period": str(ref_period),
        "rows_used": len(valid_df),
        "rows_excluded": agg_count + (len(filtered_df) - len(valid_df)),
        "exclusion_reason": f"집계 행 {agg_count}개 제외, 결측 행 {len(filtered_df) - len(valid_df)}개 제외",
        "columns_used": [label_col, str(ref_period)],
        "unit": "%",
        "caution": "서로 다른 연도를 섞지 않고 동일한 기준 연도로만 공정하게 순위를 매겼습니다.",
        "data": {"top_n": top_records, "bottom_n": bottom_records},
        "chart_data": {
            "type": "bar", "indexAxis": "y",
            "labels": [r[label_col] for r in top_records],
            "datasets": [{"label": f"{ref_period}년 상위 {len(top_records)}개국 (%)", "data": [r["value"] for r in top_records], "backgroundColor": "#2563eb"}]
        }
    }

# ==========================================
# 도구 8: group_summary (기준시점 필수)
# ==========================================
def group_summary(df, params=None):
    params = params or {}
    ref_period = params.get("reference_period")
    if not ref_period:
        return {"status": "error", "message": "기준 시점(reference_period)은 필수 파라미터입니다. (예: '2024')"}
        
    working_df = df.copy()
    group_col = params.get("group_column")
    if not group_col or group_col not in working_df.columns:
        mdf = try_load_metadata()
        if mdf is not None and "Country Code" in working_df.columns:
            working_df = pd.merge(working_df, mdf[["Country Code", "Region"]], on="Country Code", how="left")
            group_col = "Region"
            
    filtered_df, agg_count, _ = filter_aggregates(working_df, exclude=params.get("exclude_aggregates", True))
    filtered_df["_numeric_val"] = pd.to_numeric(filtered_df[ref_period], errors="coerce")
    valid_df = filtered_df.dropna(subset=["_numeric_val", group_col])
    
    grp = valid_df.groupby(group_col)["_numeric_val"].agg(mean="mean", median="median", count="count").reset_index().sort_values(by="mean", ascending=False)
    summary_records = sanitize_records(grp.to_dict(orient="records"))
    
    return {
        "status": "success",
        "tool": "group_summary",
        "summary": f"{ref_period}년 {group_col}별 평균 및 중앙값 분석 결과입니다.",
        "reference_period": str(ref_period),
        "rows_used": len(valid_df),
        "rows_excluded": agg_count + (len(filtered_df) - len(valid_df)),
        "exclusion_reason": f"집계 행 {agg_count}개 제외, 결측 {len(filtered_df) - len(valid_df)}개 제외",
        "columns_used": [group_col, str(ref_period)],
        "unit": "%",
        "caution": "그룹 내 국가 수가 적은 지역은 특정 국가 수치에 의해 평균이 좌우될 수 있습니다.",
        "data": {"group_column": group_col, "groups": summary_records},
        "chart_data": {
            "type": "bar", "labels": [r[group_col] for r in summary_records],
            "datasets": [{"label": f"{ref_period}년 {group_col}별 평균 (%)", "data": [r["mean"] for r in summary_records], "backgroundColor": "#3b82f6"}]
        }
    }

# ==========================================
# 도구 9: change_rate (기준시점 필수)
# ==========================================
def change_rate(df, params=None):
    """두 시점 사이의 절대 변화량(%p)과 상대 변화율(%)을 계산하여 고성장 국가를 도출합니다."""
    params = params or {}
    ref_end = params.get("period_end") or params.get("reference_period")
    if not ref_end:
        return {"status": "error", "message": "종료 기준 시점(reference_period 또는 period_end)은 필수입니다. (예: '2024')"}
        
    year_cols = find_year_cols(df)
    ref_end = str(ref_end).strip()
    ref_start = str(params.get("period_start", "")).strip()
    
    if not ref_start:
        # 기본값: 기준 시점 10년 전 (또는 5년 전)
        if ref_end in year_cols:
            idx = year_cols.index(ref_end)
            ref_start = year_cols[max(0, idx - 10)]
        else:
            ref_start = year_cols[0]
            
    if ref_start not in df.columns or ref_end not in df.columns:
        return {"status": "error", "message": f"시작 시점 '{ref_start}' 또는 종료 시점 '{ref_end}' 열이 데이터에 없습니다."}
        
    exclude_aggs = params.get("exclude_aggregates", True)
    label_col = find_label_col(df)
    filtered_df, agg_count, _ = filter_aggregates(df, exclude=exclude_aggs, label_col=label_col)
    
    val_start = pd.to_numeric(filtered_df[ref_start], errors="coerce")
    val_end = pd.to_numeric(filtered_df[ref_end], errors="coerce")
    
    valid_mask = val_start.notna() & val_end.notna()
    valid_df = filtered_df[valid_mask].copy()
    
    valid_df["start_val"] = val_start[valid_mask]
    valid_df["end_val"] = val_end[valid_mask]
    valid_df["diff_points"] = valid_df["end_val"] - valid_df["start_val"]
    valid_df["pct_change"] = ((valid_df["diff_points"]) / valid_df["start_val"].replace(0, np.nan)) * 100
    
    valid_df = valid_df.sort_values(by="diff_points", ascending=False)
    
    top_growth = sanitize_records(valid_df.head(10)[[label_col, "start_val", "end_val", "diff_points", "pct_change"]].to_dict(orient="records"))
    
    rows_used = len(valid_df)
    na_count = len(filtered_df) - rows_used
    
    chart_data = {
        "type": "bar",
        "labels": [r[label_col] for r in top_growth],
        "datasets": [{
            "label": f"{ref_start}~{ref_end}년 증가폭 (%p)",
            "data": [r["diff_points"] for r in top_growth],
            "backgroundColor": "#10b981"
        }]
    }
    
    return {
        "status": "success",
        "tool": "change_rate",
        "summary": f"{ref_start}년부터 {ref_end}년까지 {rows_used}개국 중 가장 많이 성장한 상위 10개국의 변화폭입니다.",
        "reference_period": f"{ref_start}~{ref_end}",
        "rows_used": rows_used,
        "rows_excluded": agg_count + na_count,
        "exclusion_reason": f"집계 행 {agg_count}개 제외, 두 시점 중 하나라도 결측인 행 {na_count}개 제외",
        "columns_used": [label_col, ref_start, ref_end],
        "unit": "%p (포인트 증가량)",
        "caution": "시작 연도의 수치가 0에 가까우면 백분율 변화율(%)이 극단적으로 크게 나타날 수 있으므로 절대 증가폭(%p)을 함께 살펴봐야 합니다.",
        "data": {"period_start": ref_start, "period_end": ref_end, "top_growth": top_growth},
        "chart_data": chart_data
    }

# ==========================================
# 도구 10: distribution (기준시점 필수)
# ==========================================
def distribution(df, params=None):
    """기준 시점 수치의 구간별 빈도(히스토그램) 분포를 산출합니다."""
    params = params or {}
    ref_period = params.get("reference_period")
    if not ref_period:
        return {"status": "error", "message": "기준 시점(reference_period)은 필수 파라미터입니다. (예: '2024')"}
        
    ref_period = str(ref_period).strip()
    if ref_period not in df.columns:
        return {"status": "error", "message": f"기준 시점 열 '{ref_period}'을 찾을 수 없습니다."}
        
    exclude_aggs = params.get("exclude_aggregates", True)
    label_col = find_label_col(df)
    filtered_df, agg_count, _ = filter_aggregates(df, exclude=exclude_aggs, label_col=label_col)
    
    s = pd.to_numeric(filtered_df[ref_period], errors="coerce").dropna()
    rows_used = len(s)
    na_count = len(filtered_df) - rows_used
    
    bins = [0, 20, 40, 60, 80, 100]
    bin_labels = ["0~20% (매우 낮음)", "20~40% (낮음)", "40~60% (보통)", "60~80% (높음)", "80~100% (매우 높음)"]
    
    counts, _ = np.histogram(s, bins=bins)
    
    dist_records = []
    for lbl, cnt in zip(bin_labels, counts):
        dist_records.append({
            "range": lbl,
            "count": int(cnt),
            "ratio": round(float(cnt / rows_used) * 100, 1) if rows_used > 0 else 0
        })
        
    chart_data = {
        "type": "bar",
        "labels": bin_labels,
        "datasets": [{
            "label": f"{ref_period}년 국가 수 (개국)",
            "data": [int(c) for c in counts],
            "backgroundColor": ["#ef4444", "#f97316", "#eab308", "#3b82f6", "#10b981"]
        }]
    }
    
    return {
        "status": "success",
        "tool": "distribution",
        "summary": f"{ref_period}년 {rows_used}개국의 보급률 구간 분포(히스토그램)입니다.",
        "reference_period": ref_period,
        "rows_used": rows_used,
        "rows_excluded": agg_count + na_count,
        "exclusion_reason": f"집계 행 {agg_count}개 제외, 결측 {na_count}개 제외",
        "columns_used": [ref_period],
        "unit": "개국",
        "caution": "80~100% 구간에 국가가 집중되어 있다면 글로벌 디지털 보급이 포화 상태에 진입했음을 뜻합니다.",
        "data": {"distribution": dist_records},
        "chart_data": chart_data
    }

# ==========================================
# 도구 11: correlation_scatter (기준시점 필수)
# ==========================================
def correlation_scatter(df, params=None):
    """두 시점(또는 두 숫자 열) 간의 피어슨 상관계수를 계산하고 산점도 데이터를 반환합니다."""
    params = params or {}
    ref_period = params.get("reference_period") or params.get("col_y")
    if not ref_period:
        return {"status": "error", "message": "기준 시점(reference_period)은 필수 파라미터입니다. (예: '2024')"}
        
    year_cols = find_year_cols(df)
    col_y = str(ref_period).strip()
    col_x = str(params.get("col_x", "")).strip()
    
    if not col_x:
        if col_y in year_cols:
            idx = year_cols.index(col_y)
            col_x = year_cols[max(0, idx - 10)]
        else:
            col_x = year_cols[0]
            
    if col_x not in df.columns or col_y not in df.columns:
        return {"status": "error", "message": f"비교할 열 '{col_x}' 또는 '{col_y}'를 찾을 수 없습니다."}
        
    exclude_aggs = params.get("exclude_aggregates", True)
    label_col = find_label_col(df)
    filtered_df, agg_count, _ = filter_aggregates(df, exclude=exclude_aggs, label_col=label_col)
    
    sx = pd.to_numeric(filtered_df[col_x], errors="coerce")
    sy = pd.to_numeric(filtered_df[col_y], errors="coerce")
    
    valid_mask = sx.notna() & sy.notna()
    valid_df = filtered_df[valid_mask].copy()
    valid_df["x"] = sx[valid_mask]
    valid_df["y"] = sy[valid_mask]
    
    rows_used = len(valid_df)
    na_count = len(filtered_df) - rows_used
    
    r_corr = round(float(valid_df[["x", "y"]].corr().iloc[0, 1]), 4) if rows_used > 1 else 0
    
    points = []
    for _, row in valid_df.iterrows():
        points.append({
            "x": round(float(row["x"]), 2),
            "y": round(float(row["y"]), 2),
            "label": str(row[label_col])
        })
        
    chart_data = {
        "type": "scatter",
        "datasets": [{
            "label": f"{col_x}년 vs {col_y}년 상관관계 (r={r_corr})",
            "data": [{"x": p["x"], "y": p["y"]} for p in points],
            "backgroundColor": "#6366f1"
        }]
    }
    
    return {
        "status": "success",
        "tool": "correlation_scatter",
        "summary": f"{col_x}년과 {col_y}년 사이의 상관계수는 {r_corr}입니다.",
        "reference_period": f"{col_x} vs {col_y}",
        "rows_used": rows_used,
        "rows_excluded": agg_count + na_count,
        "exclusion_reason": f"집계 행 {agg_count}개 제외, 결측 행 {na_count}개 제외",
        "columns_used": [col_x, col_y],
        "unit": "상관계수 (-1 ~ 1)",
        "caution": "⚠️ 상관관계는 인과관계가 아닙니다. 두 변수 사이에 높은 양의 상관관계가 나타난다고 해서 한쪽이 다른 쪽의 원인이 됨을 의미하지는 않습니다.",
        "data": {
            "col_x": col_x,
            "col_y": col_y,
            "correlation_coefficient": r_corr,
            "interpretation": "매우 강한 양의 상관관계" if r_corr >= 0.7 else ("뚜렷한 양의 상관관계" if r_corr >= 0.4 else "약한 상관관계"),
            "sample_points": points[:30]
        },
        "chart_data": chart_data
    }

# ==========================================
# 도구 12: compare_one_vs_all (기준시점 필수)
# ==========================================
def compare_one_vs_all(df, params=None):
    """특정 대상(대한민국 등)의 수치를 전체 평균 및 중앙값과 직관적으로 대비합니다."""
    params = params or {}
    ref_period = params.get("reference_period")
    if not ref_period:
        return {"status": "error", "message": "기준 시점(reference_period)은 필수 파라미터입니다. (예: '2024')"}
        
    ref_period = str(ref_period).strip()
    if ref_period not in df.columns:
        return {"status": "error", "message": f"기준 시점 열 '{ref_period}'이 없습니다."}
        
    label_col = find_label_col(df)
    target = params.get("target_item") or "Korea, Rep."
    
    exclude_aggs = params.get("exclude_aggregates", True)
    filtered_df, agg_count, _ = filter_aggregates(df, exclude=exclude_aggs, label_col=label_col)
    
    s = pd.to_numeric(filtered_df[ref_period], errors="coerce")
    valid_mask = s.notna()
    clean_df = filtered_df[valid_mask].copy()
    clean_df["_val"] = s[valid_mask]
    
    rows_used = len(clean_df)
    na_count = len(filtered_df) - rows_used
    
    mean_val = round(float(clean_df["_val"].mean()), 2)
    median_val = round(float(clean_df["_val"].median()), 2)
    
    # 대상 항목 값 찾기
    target_row = clean_df[clean_df[label_col].astype(str).str.contains(target, case=False, na=False)]
    if target_row.empty:
        target_name = str(clean_df.iloc[0][label_col])
        target_val = round(float(clean_df.iloc[0]["_val"]), 2)
    else:
        target_name = str(target_row.iloc[0][label_col])
        target_val = round(float(target_row.iloc[0]["_val"]), 2)
        
    # 순위 계산
    clean_df_sorted = clean_df.sort_values(by="_val", ascending=False).reset_index(drop=True)
    target_rank = int(clean_df_sorted[clean_df_sorted[label_col] == target_name].index[0]) + 1
    
    diff_from_mean = round(target_val - mean_val, 2)
    diff_from_median = round(target_val - median_val, 2)
    
    chart_data = {
        "type": "bar",
        "labels": [target_name, "전체 평균 (Mean)", "전체 중앙값 (Median)"],
        "datasets": [{
            "label": f"{ref_period}년 인터넷 이용률 (%)",
            "data": [target_val, mean_val, median_val],
            "backgroundColor": ["#dc2626", "#3b82f6", "#94a3b8"]
        }]
    }
    
    return {
        "status": "success",
        "tool": "compare_one_vs_all",
        "summary": f"{ref_period}년 {target_name}의 수치는 {target_val}%로, 전체 평균({mean_val}%)보다 {abs(diff_from_mean)}%p {'높습니다' if diff_from_mean >= 0 else '낮습니다'}.",
        "reference_period": ref_period,
        "rows_used": rows_used,
        "rows_excluded": agg_count + na_count,
        "exclusion_reason": f"집계 행 {agg_count}개 제외, 결측 행 {na_count}개 제외",
        "columns_used": [label_col, ref_period],
        "unit": "%",
        "caution": "특정 1개 국가의 우수성을 과장하기보다는 전체 분포(평균 및 중앙값)와 함께 입체적으로 해석해야 합니다.",
        "data": {
            "target_item": target_name,
            "target_value": target_val,
            "target_rank": target_rank,
            "total_countries": rows_used,
            "world_mean": mean_val,
            "world_median": median_val,
            "diff_from_mean": diff_from_mean,
            "diff_from_median": diff_from_median
        },
        "chart_data": chart_data
    }

# ==========================================
# 도구 카탈로그 정의 (Step 17 Gemini 제안용)
# ==========================================
TOOL_CATALOG = [
    {
        "name": "reshape_wide_to_long",
        "description": "가로로 펼쳐진 연도 열들을 세로형(Long/Tidy) 데이터로 변환",
        "requires_reference_period": False,
        "parameters": ["exclude_aggregates", "drop_na"]
    },
    {
        "name": "quality_report",
        "description": "열별 결측률 순위, 중복 행 수, Unnamed 열 감지 등 종합 품질 보고서",
        "requires_reference_period": False,
        "parameters": ["exclude_aggregates"]
    },
    {
        "name": "year_coverage",
        "description": "연도별 데이터 유효값 개수 및 충실도 계산, 권장 기준연도 산출",
        "requires_reference_period": False,
        "parameters": ["exclude_aggregates"]
    },
    {
        "name": "detect_aggregates",
        "description": "전 세계 평균, 고소득국 그룹 등 집계 행 후보 탐지 및 분리",
        "requires_reference_period": False,
        "parameters": ["label_column"]
    },
    {
        "name": "describe_numeric",
        "description": "기준 연도의 개수, 평균, 중앙값, 최소, 최대, 표준편차 등 기술통계 산출",
        "requires_reference_period": True,
        "parameters": ["reference_period", "exclude_aggregates"]
    },
    {
        "name": "trend_line",
        "description": "선택된 관심 국가들의 연도별 시계열 변화 추이 선 그래프 생성",
        "requires_reference_period": False,
        "parameters": ["items", "label_column"]
    },
    {
        "name": "top_bottom_n",
        "description": "기준 연도 기준 상위 N개 및 하위 N개 국가 랭킹 수평 막대 차트",
        "requires_reference_period": True,
        "parameters": ["reference_period", "n", "exclude_aggregates", "label_column"]
    },
    {
        "name": "group_summary",
        "description": "대륙(Region) 또는 소득그룹별 평균·중앙값 집계 막대 차트",
        "requires_reference_period": True,
        "parameters": ["reference_period", "group_column", "exclude_aggregates"]
    },
    {
        "name": "change_rate",
        "description": "두 시점 사이의 증가폭(%p) 계산 및 최고 성장 국가 도출",
        "requires_reference_period": True,
        "parameters": ["reference_period", "period_start", "exclude_aggregates"]
    },
    {
        "name": "distribution",
        "description": "기준 연도 수치의 구간별 빈도(0~20%, 20~40% 등) 히스토그램 분포",
        "requires_reference_period": True,
        "parameters": ["reference_period", "exclude_aggregates"]
    },
    {
        "name": "correlation_scatter",
        "description": "두 시점(예: 10년 전 vs 기준연도) 간 피어슨 상관계수 및 산점도",
        "requires_reference_period": True,
        "parameters": ["reference_period", "col_x", "exclude_aggregates"]
    },
    {
        "name": "compare_one_vs_all",
        "description": "특정 대상(대한민국) 수치 vs 전체 평균 및 중앙값 비교 강조 막대",
        "requires_reference_period": True,
        "parameters": ["reference_period", "target_item", "exclude_aggregates"]
    }
]

# 실행 함수 매핑
TOOL_RUN_MAP = {
    "reshape_wide_to_long": reshape_wide_to_long,
    "quality_report": quality_report,
    "year_coverage": year_coverage,
    "detect_aggregates": detect_aggregates,
    "describe_numeric": describe_numeric,
    "trend_line": trend_line,
    "top_bottom_n": top_bottom_n,
    "group_summary": group_summary,
    "change_rate": change_rate,
    "distribution": distribution,
    "correlation_scatter": correlation_scatter,
    "compare_one_vs_all": compare_one_vs_all
}
