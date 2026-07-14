from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from email_notifier import send_html_email
from msit_fetch import Notice, fetch_msit_notices

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

CONFIG_PATH = BASE_DIR / "config.yaml"
EXAMPLE_CONFIG_PATH = BASE_DIR / "config.example.yaml"
HTML_OUTPUT_PATH = BASE_DIR / "msit_notice_latest.html"


def load_config() -> dict[str, Any]:
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    if isinstance(data, list):
        return {str(x) for x in data}
    return set()


def save_seen_ids(path: Path, ids: set[str]) -> None:
    path.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def _link_html(url: str, label: str) -> str:
    if not url:
        return "-"
    return f'<a href="{escape(url)}" target="_blank">{escape(label)}</a>'


def _notice_rows(notices: list[Notice]) -> str:
    if not notices:
        return """
        <tr>
            <td colspan="7" class="empty">신규 공고가 없습니다.</td>
        </tr>
        """

    rows: list[str] = []
    for idx, notice in enumerate(notices, 1):
        detail_link = _link_html(notice.url, "바로가기") if notice.url else "-"
        attachment_link = _link_html(notice.file_url, notice.file_name or "첨부파일") if notice.file_url else "-"
        manager = " / ".join(x for x in [notice.manager_name, notice.manager_tel] if x) or "-"

        rows.append(
            f"""
            <tr>
                <td class="num">{idx}</td>
                <td class="title-cell"><div class="notice-title">{escape(notice.title)}</div></td>
                <td class="dept">{escape(notice.department or '-')}</td>
                <td class="manager">{escape(manager)}</td>
                <td class="date">{escape(notice.registered_date or '-')}</td>
                <td class="attach">{attachment_link}</td>
                <td class="link">{detail_link}</td>
            </tr>
            """
        )
    return "\n".join(rows)


def build_html_message(new_notices: list[Notice], old_notices: list[Notice], total_count: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>과학기술정보통신부 사업공고 알림</title>
<style>
    body {{ margin:0; padding:0; background:#f5f6f7; color:#111; font-family:'Malgun Gothic','Apple SD Gothic Neo',Arial,sans-serif; font-size:14px; }}
    .wrap {{ max-width:1080px; margin:0 auto; background:#fff; border:1px solid #d9dee5; }}
    .header {{ background:#203a54; color:#fff; padding:24px 26px; }}
    .header h1 {{ margin:0 0 10px; font-size:24px; font-weight:800; }}
    .header .time {{ font-size:13px; color:#d7e3ef; }}
    .summary {{ padding:22px 26px 18px; border-bottom:1px solid #e2e6ea; }}
    .badge {{ display:inline-block; margin-right:10px; padding:9px 15px; border-radius:18px; font-weight:800; font-size:13px; }}
    .badge-new {{ background:#e8f6ea; }} .badge-old {{ background:#eef3ff; }} .badge-total {{ background:#f4f4f4; }}
    .summary-desc {{ margin-top:18px; color:#555; line-height:1.6; font-size:13px; }}
    .section {{ padding:26px; }}
    .section h2 {{ margin:0 0 14px; font-size:20px; }}
    table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
    th {{ background:#f0f1f3; border:1px solid #d7dbe0; padding:13px 8px; text-align:center; font-weight:800; font-size:13px; }}
    td {{ border:1px solid #d7dbe0; padding:13px 10px; vertical-align:middle; font-size:13px; line-height:1.45; }}
    .num {{ width:46px; text-align:center; }}
    .title-cell {{ width:auto; }}
    .notice-title {{ font-weight:800; color:#000; line-height:1.5; }}
    .dept {{ width:135px; text-align:center; }}
    .manager {{ width:120px; text-align:center; }}
    .date {{ width:105px; text-align:center; white-space:nowrap; }}
    .attach {{ width:90px; text-align:center; }}
    .link {{ width:80px; text-align:center; }}
    a {{ color:#0070c9; text-decoration:underline; font-weight:700; }}
    .empty {{ text-align:center; color:#666; padding:28px; }}
    .old-summary {{ margin-top:22px; padding:15px 17px; background:#f8fafc; border:1px solid #e3e7ec; color:#555; line-height:1.7; font-size:13px; }}
    .footer {{ padding:0 26px 26px; color:#666; font-size:12px; line-height:1.6; }}
</style>
</head>
<body>
<div class="wrap">
    <div class="header">
        <h1>과학기술정보통신부 사업공고 알림</h1>
        <div class="time">조회시각: {escape(now)}</div>
    </div>
    <div class="summary">
        <span class="badge badge-new">신규 {len(new_notices)}건</span>
        <span class="badge badge-old">기존 {len(old_notices)}건</span>
        <span class="badge badge-total">전체 {total_count}건</span>
        <div class="summary-desc">
            기존 공고는 이미 이전에 발송된 공고입니다. 이 메일에는 신규 공고만 상세 표시합니다.<br>
            동일한 HTML 문서를 첨부파일로도 함께 발송합니다.
        </div>
    </div>
    <div class="section">
        <h2>신규 공고 목록</h2>
        <table>
            <thead>
                <tr>
                    <th class="num">번호</th>
                    <th>공고명</th>
                    <th class="dept">부서</th>
                    <th class="manager">담당/연락처</th>
                    <th class="date">등록일</th>
                    <th class="attach">첨부</th>
                    <th class="link">링크</th>
                </tr>
            </thead>
            <tbody>
                {_notice_rows(new_notices)}
            </tbody>
        </table>
        <div class="old-summary">
            기존 공고 <strong>{len(old_notices)}</strong>건은 이미 이전에 발송된 공고입니다.<br>
            신규 공고가 없을 경우 목록은 비어 있을 수 있습니다.
        </div>
    </div>
    <div class="footer">
        ※ 과학기술정보통신부 사업공고 API를 기준으로 수집했습니다.<br>
        ※ API 응답 구조가 맞지 않을 경우 과기정통부 사업공고 게시판 HTML을 보조 수집합니다.
    </div>
</div>
</body>
</html>
"""


def build_text_message(new_notices: list[Notice], old_notices: list[Notice], total_count: int) -> str:
    lines = [
        "과학기술정보통신부 사업공고 알림",
        f"신규 {len(new_notices)}건 / 기존 {len(old_notices)}건 / 전체 {total_count}건",
        "",
    ]
    for idx, notice in enumerate(new_notices, 1):
        lines.extend([
            f"{idx}. {notice.title}",
            f"- 부서: {notice.department or '-'}",
            f"- 담당/연락처: {' / '.join(x for x in [notice.manager_name, notice.manager_tel] if x) or '-'}",
            f"- 등록일: {notice.registered_date or '-'}",
            f"- 링크: {notice.url or '-'}",
            "",
        ])
    return "\n".join(lines)


def save_html_file(html_body: str) -> Path:
    HTML_OUTPUT_PATH.write_text(html_body, encoding="utf-8")
    print(f"[정보] HTML 파일 저장 완료: {HTML_OUTPUT_PATH}")
    return HTML_OUTPUT_PATH


def run() -> None:
    config = load_config()
    state_config = config.get("state", {})
    seen_path = BASE_DIR / state_config.get("seen_file", "seen_notice_ids.json")
    latest_path = BASE_DIR / state_config.get("latest_file", "latest_notices.json")

    seen_ids = load_seen_ids(seen_path)
    notices = fetch_msit_notices(config)

    new_notices = [n for n in notices if n.notice_id not in seen_ids]
    old_notices = [n for n in notices if n.notice_id in seen_ids]

    subject = f"[MSIT] 신규 공고 {len(new_notices)}건 / 전체 {len(notices)}건"
    html_body = build_html_message(new_notices, old_notices, len(notices))
    text_body = build_text_message(new_notices, old_notices, len(notices))
    html_file_path = save_html_file(html_body)

    send_html_email(subject, html_body, text_body, attachment_path=html_file_path)

    all_ids = seen_ids | {n.notice_id for n in notices}
    save_seen_ids(seen_path, all_ids)
    latest_path.write_text(
        json.dumps([n.to_dict() for n in new_notices], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
