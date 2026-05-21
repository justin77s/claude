#!/usr/bin/env python3
"""키워드 보고서에 광고 다운로드 파일의 입찰가를 매칭해 새 열로 추가한다.

사용법:
    python3 add_bid_prices.py <파일A> <파일B> [-o 출력경로]

두 파일은 순서/파일명에 상관없이 전달해도 된다. 헤더로 자동 판별한다.
  - 키워드 보고서 : 헤더에 캠페인 / 광고그룹 / 키워드 열이 있음
  - 광고 다운로드 : 헤더에 캠페인 이름 / 광고그룹 이름 / 키워드 / 키워드 입찰가 열이 있음

매칭 기준은 (캠페인 이름, 광고그룹 이름, 키워드) 3개가 정확히 일치하는 경우다.
일치하는 행이 없으면 입찰가 칸은 빈칸으로 둔다.
"""

import argparse
import csv
import os
import sys

BID_HEADER = "입찰가"


def read_rows(path):
    # utf-8-sig: 엑셀이 붙이는 BOM을 제거하고 읽는다.
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def find_header(rows, required):
    """required 열 이름을 모두 포함하는 첫 행의 인덱스를 반환한다."""
    for i, row in enumerate(rows):
        cells = {c.strip() for c in row}
        if required <= cells:
            return i
    return -1


def classify(rows):
    """('ad'|'report', 헤더행인덱스) 를 반환한다. 판별 불가 시 (None, -1)."""
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


def build_bid_lookup(rows, header_idx):
    header = rows[header_idx]
    ci_camp = col_index(header, "캠페인 이름")
    ci_grp = col_index(header, "광고그룹 이름")
    ci_kw = col_index(header, "키워드")
    ci_bid = col_index(header, "키워드 입찰가")
    lookup = {}
    for row in rows[header_idx + 1:]:
        if len(row) <= max(ci_camp, ci_grp, ci_kw, ci_bid):
            continue
        key = (row[ci_camp].strip(), row[ci_grp].strip(), row[ci_kw].strip())
        lookup[key] = row[ci_bid].strip()
    return lookup


def annotate_report(rows, header_idx, lookup):
    header = rows[header_idx]
    ci_camp = col_index(header, "캠페인")
    ci_grp = col_index(header, "광고그룹")
    ci_kw = col_index(header, "키워드")
    need = max(ci_camp, ci_grp, ci_kw)

    out = []
    total = matched = 0
    misses = []
    for i, row in enumerate(rows):
        if i < header_idx:
            out.append(row)  # 제목/안내 행 그대로 보존
        elif i == header_idx:
            out.append(row + [BID_HEADER])
        elif not any(c.strip() for c in row):
            out.append(row)  # 빈 행 보존
        elif len(row) <= need:
            out.append(row + [""])  # 열 수가 모자란 비정상 행
        else:
            key = (row[ci_camp].strip(), row[ci_grp].strip(), row[ci_kw].strip())
            total += 1
            bid = lookup.get(key, "")
            if bid:
                matched += 1
            else:
                misses.append(key)
            out.append(row + [bid])
    return out, total, matched, misses


def main():
    parser = argparse.ArgumentParser(description="키워드 보고서에 입찰가 열을 추가한다.")
    parser.add_argument("file_a")
    parser.add_argument("file_b")
    parser.add_argument("-o", "--output", help="출력 CSV 경로 (기본: 보고서명_입찰가추가.csv)")
    args = parser.parse_args()

    files = {}
    for p in (args.file_a, args.file_b):
        rows = read_rows(p)
        kind, hdr = classify(rows)
        if kind is None:
            sys.exit(f"오류: 파일 형식을 판별할 수 없습니다 -> {p}")
        if kind in files:
            sys.exit(f"오류: 같은 형식({kind})의 파일이 두 개입니다. 보고서 1개 + 광고 다운로드 1개가 필요합니다.")
        files[kind] = (p, rows, hdr)

    if "report" not in files or "ad" not in files:
        sys.exit("오류: 키워드 보고서와 광고 다운로드 파일이 각각 1개씩 필요합니다.")

    rpt_path, rpt_rows, rpt_hdr = files["report"]
    _, ad_rows, ad_hdr = files["ad"]

    lookup = build_bid_lookup(ad_rows, ad_hdr)
    out_rows, total, matched, misses = annotate_report(rpt_rows, rpt_hdr, lookup)

    if args.output:
        out_path = args.output
    else:
        base = os.path.splitext(os.path.basename(rpt_path))[0]
        out_path = os.path.join(os.path.dirname(rpt_path) or ".", f"{base}_입찰가추가.csv")

    # utf-8-sig 로 써서 엑셀에서 한글이 깨지지 않게 한다.
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(out_rows)

    print(f"출력: {out_path}")
    print(f"데이터행: {total}  입찰가채움: {matched}  빈칸: {total - matched}")
    if misses:
        print("미매칭(빈칸) 목록:")
        for camp, grp, kw in misses:
            print(f"  - {camp} / {grp} / {kw}")


if __name__ == "__main__":
    main()
