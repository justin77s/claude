#!/usr/bin/env python3
"""키워드 보고서와 광고 다운로드를 매칭해 입찰가/키워드ID 정보를 만든다.

사용법:
    # 1) 보고서에 입찰가 열만 추가
    python3 add_bid_prices.py <키워드보고서> <광고다운로드> [-o 출력경로]

    # 2) 네이버 입찰가 일괄수정 템플릿 채우기 (템플릿 파일을 같이 넘기면 됨)
    python3 add_bid_prices.py <키워드보고서> <광고다운로드> <업로드템플릿> [-o 출력경로]

파일은 순서/이름에 상관없이 전달해도 된다. 헤더로 자동 판별한다.
  - 키워드 보고서 : 헤더에 캠페인 / 광고그룹 / 키워드 열
  - 광고 다운로드 : 헤더에 캠페인 이름 / 광고그룹 이름 / 키워드 / 키워드 입찰가 / 광고그룹 ID / 키워드 ID 열
  - 업로드 템플릿 : 헤더에 광고그룹ID / 키워드ID / 키워드입찰가 열 (네이버 일괄수정 양식)

매칭 기준은 (캠페인 이름, 광고그룹 이름, 키워드) 3개가 정확히 일치하는 경우다.
템플릿 모드에서는 매칭된 키워드만(=키워드ID가 있는 것만) 채우고, 안내/헤더(1~6행)는 그대로 보존한다.
"""

import argparse
import csv
import io
import os
import sys

BID_HEADER = "입찰가"


def read_rows(path):
    """(행 리스트, 인코딩) 을 반환한다. utf-8-sig 우선, 실패하면 cp949(엑셀 한글)."""
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        return list(csv.reader(io.StringIO(text))), enc
    raise SystemExit(f"오류: 인코딩을 인식할 수 없습니다 -> {path}")


def find_header(rows, required):
    """required 열 이름(정확히 일치)을 모두 포함하는 첫 행의 인덱스를 반환한다."""
    for i, row in enumerate(rows):
        cells = {c.strip() for c in row}
        if required <= cells:
            return i
    return -1


def find_header_prefix(rows, prefixes):
    """각 prefix로 시작하는 셀을 모두 가진 첫 행의 인덱스를 반환한다."""
    for i, row in enumerate(rows):
        cells = [c.strip() for c in row]
        if all(any(c.startswith(p) for c in cells) for p in prefixes):
            return i
    return -1


def classify(rows):
    """('template'|'ad'|'report', 헤더행인덱스). 판별 불가 시 (None, -1)."""
    t_hdr = find_header_prefix(rows, ["키워드ID", "키워드입찰가"])
    if t_hdr != -1:
        return "template", t_hdr
    ad_hdr = find_header(rows, {"캠페인 이름", "광고그룹 이름", "키워드", "키워드 입찰가"})
    if ad_hdr != -1:
        return "ad", ad_hdr
    rpt_hdr = find_header(rows, {"캠페인", "광고그룹", "키워드"})
    if rpt_hdr != -1:
        return "report", rpt_hdr
    return None, -1


def col_index(header_row, name):
    for i, c in enumerate(header_row):
        if c.strip() == name:
            return i
    raise ValueError(f"'{name}' 열을 찾을 수 없습니다: {header_row}")


def build_ad_lookup(rows, header_idx):
    """(캠페인이름, 광고그룹이름, 키워드) -> {'bid','grpid','kwid'}."""
    header = rows[header_idx]
    ci_camp = col_index(header, "캠페인 이름")
    ci_grp = col_index(header, "광고그룹 이름")
    ci_kw = col_index(header, "키워드")
    ci_bid = col_index(header, "키워드 입찰가")
    ci_grpid = col_index(header, "광고그룹 ID")
    ci_kwid = col_index(header, "키워드 ID")
    need = max(ci_camp, ci_grp, ci_kw, ci_bid, ci_grpid, ci_kwid)
    lookup = {}
    for row in rows[header_idx + 1:]:
        if len(row) <= need:
            continue
        key = (row[ci_camp].strip(), row[ci_grp].strip(), row[ci_kw].strip())
        lookup[key] = {
            "bid": row[ci_bid].strip(),
            "grpid": row[ci_grpid].strip(),
            "kwid": row[ci_kwid].strip(),
        }
    return lookup


def report_keys(rows, header_idx):
    """보고서 데이터행을 (행, (캠페인,광고그룹,키워드)) 로 순회한다. 빈/비정상행은 (행, None)."""
    header = rows[header_idx]
    ci_camp = col_index(header, "캠페인")
    ci_grp = col_index(header, "광고그룹")
    ci_kw = col_index(header, "키워드")
    need = max(ci_camp, ci_grp, ci_kw)
    for row in rows[header_idx + 1:]:
        if not any(c.strip() for c in row) or len(row) <= need:
            yield row, None
        else:
            yield row, (row[ci_camp].strip(), row[ci_grp].strip(), row[ci_kw].strip())


def annotate_report(rows, header_idx, lookup):
    out, total, matched, misses = [], 0, 0, []
    for i, row in enumerate(rows[:header_idx + 1]):
        out.append(row if i < header_idx else row + [BID_HEADER])
    for row, key in report_keys(rows, header_idx):
        if key is None:
            out.append(row if not any(c.strip() for c in row) else row + [""])
            continue
        total += 1
        bid = lookup.get(key, {}).get("bid", "")
        if bid:
            matched += 1
        else:
            misses.append(key)
        out.append(row + [bid])
    return out, total, matched, misses


def fill_template(template_rows, t_hdr, report_rows, r_hdr, lookup):
    header = template_rows[t_hdr]
    idx_grp = idx_kwid = idx_kw = idx_bid = None
    for i, c in enumerate(header):
        cs = c.strip()
        if cs.startswith("광고그룹ID"):
            idx_grp = i
        elif cs.startswith("키워드ID"):
            idx_kwid = i
        elif cs.startswith("키워드입찰가"):
            idx_bid = i
        elif cs.startswith("키워드"):
            idx_kw = i
    if idx_kwid is None or idx_bid is None:
        raise SystemExit("오류: 템플릿에서 키워드ID/키워드입찰가 열을 찾을 수 없습니다.")

    out = list(template_rows[:t_hdr + 1])  # 안내+헤더(1~6행) 보존
    ncol = len(header)
    total = filled = 0
    misses = []
    for _, key in report_keys(report_rows, r_hdr):
        if key is None:
            continue
        total += 1
        info = lookup.get(key)
        if not info or not info["kwid"]:
            misses.append(key)
            continue
        new = [""] * ncol
        if idx_grp is not None:
            new[idx_grp] = info["grpid"]
        new[idx_kwid] = info["kwid"]
        if idx_kw is not None:
            new[idx_kw] = key[2]
        new[idx_bid] = info["bid"]
        out.append(new)
        filled += 1
    return out, total, filled, misses


def write_csv(path, rows, encoding):
    with open(path, "w", newline="", encoding=encoding) as f:
        csv.writer(f).writerows(rows)


def default_out(src_path, suffix):
    base = os.path.splitext(os.path.basename(src_path))[0]
    return os.path.join(os.path.dirname(src_path) or ".", f"{base}{suffix}.csv")


def main():
    parser = argparse.ArgumentParser(description="키워드 보고서 입찰가/키워드ID 매칭 도구")
    parser.add_argument("files", nargs="+", help="키워드보고서, 광고다운로드 (+ 선택: 업로드템플릿)")
    parser.add_argument("-o", "--output", help="출력 CSV 경로")
    args = parser.parse_args()

    files = {}
    for p in args.files:
        rows, enc = read_rows(p)
        kind, hdr = classify(rows)
        if kind is None:
            sys.exit(f"오류: 파일 형식을 판별할 수 없습니다 -> {p}")
        if kind in files:
            sys.exit(f"오류: 같은 형식({kind})의 파일이 두 개입니다.")
        files[kind] = (p, rows, hdr, enc)

    if "report" not in files or "ad" not in files:
        sys.exit("오류: 키워드 보고서와 광고 다운로드 파일이 각각 1개씩 필요합니다.")

    rpt_path, rpt_rows, rpt_hdr, _ = files["report"]
    _, ad_rows, ad_hdr, _ = files["ad"]
    lookup = build_ad_lookup(ad_rows, ad_hdr)

    if "template" in files:
        t_path, t_rows, t_hdr, t_enc = files["template"]
        out_rows, total, filled, misses = fill_template(t_rows, t_hdr, rpt_rows, rpt_hdr, lookup)
        out_path = args.output or default_out(t_path, "_입력완료")
        write_csv(out_path, out_rows, t_enc)  # 템플릿 원본 인코딩(보통 cp949) 유지
        print(f"출력(템플릿): {out_path}  (인코딩 {t_enc})")
        print(f"보고서 데이터행: {total}  템플릿 채움: {filled}  제외(키워드ID 없음): {total - filled}")
        label = "제외(키워드ID 없음) 목록"
    else:
        out_rows, total, filled, misses = annotate_report(rpt_rows, rpt_hdr, lookup)
        out_path = args.output or default_out(rpt_path, "_입찰가추가")
        write_csv(out_path, out_rows, "utf-8-sig")
        print(f"출력: {out_path}")
        print(f"데이터행: {total}  입찰가채움: {filled}  빈칸: {total - filled}")
        label = "미매칭(빈칸) 목록"

    if misses:
        print(f"{label}:")
        for camp, grp, kw in misses:
            print(f"  - {camp} / {grp} / {kw}")


if __name__ == "__main__":
    main()
