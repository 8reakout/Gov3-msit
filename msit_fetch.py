from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from html import unescape
from typing import Any
from urllib.parse import urljoin

import requests


@dataclass
class Notice:
    notice_id: str
    title: str
    organization: str = ""
    department: str = ""
    manager_name: str = ""
    manager_tel: str = ""
    registered_date: str = ""
    url: str = ""
    file_name: str = ""
    file_url: str = ""
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_html(value: str) -> str:
    value = unescape(value or "")
    value = re.sub(r"(?i)<br\s*/?>", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _first_value(item: dict[str, Any], candidates: list[str]) -> str:
    for key in candidates:
        if key in item and item[key] not in (None, ""):
            return str(item[key]).strip()
    return ""


def _dig_items(data: Any) -> list[dict[str, Any]]:
    """MSIT API 응답에서 실제 공고 item 목록만 추출합니다."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if not isinstance(data, dict):
        return []

    paths = [
        ["response", "body", "items", "item"],
        ["body", "items", "item"],
        ["items", "item"],
    ]

    for path in paths:
        cur: Any = data

        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                cur = None
                break

        if cur is None:
            continue

        if isinstance(cur, dict):
            return [cur]

        if isinstance(cur, list):
            return [x for x in cur if isinstance(x, dict)]

    return []



def _normalize_date(value: str) -> str:
    value = _strip_html(value)
    if not value:
        return ""
    value = value.replace(".", "-").replace("/", "-")
    # 2026. 7. 10 형태 대비
    value = re.sub(r"\s+", "", value)
    # yyyy-MM-dd HH:mm:ss 형태면 날짜만 사용
    value = value.split(" ")[0]
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if match:
        y, m, d = match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return value


def _parse_date(value: str) -> date | None:
    value = _normalize_date(value)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _normalize_url(value: str, base_url: str = "https://www.msit.go.kr") -> str:
    value = unescape(value or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        return "https:" + value
    if value.startswith("www."):
        return "https://" + value
    if value.startswith("/"):
        return urljoin(base_url, value)
    return value


def _is_recent(registered_date: str, lookback_days: int) -> bool:
    reg = _parse_date(registered_date)
    if reg is None:
        return True
    return reg >= date.today() - timedelta(days=lookback_days)


def request_with_retry(api_url: str, params: dict[str, Any] | None = None, max_retries: int = 3) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[정보] MSIT 요청 시도: {attempt}/{max_retries}")
            response = requests.get(
                api_url,
                params=params or {},
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0 GovMonitoringBot/1.0",
                    "Accept": "application/json, text/html, application/xml, text/plain, */*",
                },
            )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as exc:
            last_error = exc
            print(f"[경고] MSIT 요청 실패: {attempt}/{max_retries} - {exc}")
            if attempt < max_retries:
                time.sleep(5)
    raise RuntimeError(f"MSIT 요청이 {max_retries}회 모두 실패했습니다: {last_error}")


def _build_params(
    config: dict[str, Any],
    service_key_name: str = "serviceKey",
    page_no: int = 1,
) -> dict[str, Any]:
    cfg = config["msit"]
    service_key = (
        os.getenv("MSIT_SERVICE_KEY")
        or os.getenv("DATA_GO_KR_SERVICE_KEY")
        or cfg.get("service_key", "")
    ).strip()

    if not service_key:
        raise ValueError("MSIT_SERVICE_KEY 또는 DATA_GO_KR_SERVICE_KEY 값이 없습니다.")

    params_cfg = cfg.get("params", {})

    return {
        service_key_name: service_key,
        "pageNo": page_no,
        "numOfRows": int(params_cfg.get("numOfRows", cfg.get("num_of_rows", 10))),
        "returnType": str(params_cfg.get("returnType", cfg.get("return_type", "xml"))),
    }

def _convert_api_item_to_notice(item: dict[str, Any], lookback_days: int) -> Notice | None:
    title = _strip_html(_first_value(item, ["subject", "title", "nttSj", "bbscttSj", "공고명", "제목"]))
    if not title:
        return None

    registered_date = _normalize_date(_first_value(item, ["pressDt", "regDt", "nttRgstDt", "등록일", "작성일"]))
    if not _is_recent(registered_date, lookback_days):
        return None

    url = _normalize_url(_first_value(item, ["viewUrl", "detailUrl", "url", "link", "상세URL"]))
    file_name = _strip_html(_first_value(item, ["fileName", "atchFileNm", "첨부파일"]))
    file_url = _normalize_url(_first_value(item, ["fileUrl", "atchFileUrl", "downloadUrl"]))

    files = item.get("files", [])
    if isinstance(files, list) and files:
        first_file = files[0]
        if isinstance(first_file, dict):
            if not file_name:
                file_name = _strip_html(str(first_file.get("fileName", "") or ""))
            if not file_url:
                file_url = _normalize_url(str(first_file.get("fileUrl", "") or ""))

    notice_id = _first_value(item, ["nttSeqNo", "bbsSeq", "seq", "id", "viewUrl"])
    if not notice_id:
        notice_id = f"{title}|{registered_date}|{url}"

    return Notice(
        notice_id=str(notice_id),
        title=title,
        organization="과학기술정보통신부",
        department=_strip_html(_first_value(item, ["deptName", "deptNm", "부서", "담당부서"])),
        manager_name=_strip_html(_first_value(item, ["managerName", "chargerNm", "담당자"])),
        manager_tel=_strip_html(_first_value(item, ["managerTel", "telNo", "연락처"])),
        registered_date=registered_date,
        url=url,
        file_name=file_name,
        file_url=file_url,
        raw=item,
    )


def _fetch_api_notices(config: dict[str, Any]) -> list[Notice]:
    cfg = config["msit"]
    api_url = cfg.get("api_url", "").strip()

    if not api_url:
        raise ValueError("config.yaml의 msit.api_url 값이 비어 있습니다.")

    lookback_days = int(cfg.get("lookback_days", 60))
    max_pages = int(cfg.get("max_pages", 10))

    all_notices: list[Notice] = []

    # 문서 기준은 serviceKey입니다. ServiceKey는 보조로만 시도합니다.
    for key_name in ["serviceKey", "ServiceKey"]:
        key_notices: list[Notice] = []
        stop_paging = False

        for page_no in range(1, max_pages + 1):
            params = _build_params(
                config,
                service_key_name=key_name,
                page_no=page_no,
            )

            print(
                f"[정보] MSIT API 호출 시작: key={key_name}, "
                f"pageNo={params['pageNo']}, numOfRows={params['numOfRows']}, "
                f"returnType={params['returnType']}"
            )

            try:
                response = request_with_retry(api_url, params=params, max_retries=3)
                text = response.text.strip()

                items: list[dict[str, Any]] = []

                if text.startswith("<"):
                    items = _parse_xml_items(text)
                else:
                    try:
                        data = response.json()
                    except Exception as exc:
                        raise RuntimeError(
                            "MSIT API 응답이 JSON/XML 형식이 아닙니다. 응답 앞부분: "
                            + text[:500]
                        ) from exc

                    items = _dig_items(data)

                print(f"[정보] MSIT API pageNo={page_no} 응답 item 수: {len(items)}")

                if not items:
                    print(f"[정보] MSIT API pageNo={page_no}에 공고가 없어 페이지 조회를 중단합니다.")
                    break

                page_notices: list[Notice] = []
                page_has_recent_source_item = False

                for item in items:
                    registered_date = _normalize_date(
                        _first_value(item, ["pressDt", "regDt", "nttRgstDt", "등록일", "작성일"])
                    )

                    if _is_recent(registered_date, lookback_days):
                        page_has_recent_source_item = True

                    notice = _convert_api_item_to_notice(item, lookback_days)

                    if notice is not None:
                        page_notices.append(notice)

                print(
                    f"[정보] MSIT API pageNo={page_no} 변환 후 공고 수: {len(page_notices)}"
                )

                key_notices.extend(page_notices)

                # 최신순 API라는 전제에서, 이 페이지에 최근 60일 공고가 하나도 없으면 중단합니다.
                if not page_has_recent_source_item:
                    print(
                        f"[정보] MSIT API pageNo={page_no}에서 최근 {lookback_days}일 공고가 없어 "
                        "다음 페이지 조회를 중단합니다."
                    )
                    stop_paging = True
                    break

            except Exception as exc:
                print(f"[경고] MSIT API pageNo={page_no} 호출 실패: {key_name} - {exc}")
                break

            if stop_paging:
                break

        if key_notices:
            print(f"[정보] MSIT API key={key_name} 전체 변환 공고 수: {len(key_notices)}")
            all_notices.extend(key_notices)
            break

    deduped: dict[str, Notice] = {}

    for notice in all_notices:
        deduped[notice.notice_id] = notice

    notices = sorted(
        deduped.values(),
        key=lambda n: (n.registered_date or "9999-99-99", n.title),
        reverse=True,
    )

    print(f"[정보] MSIT API 전체 수집 공고 수: {len(notices)}")
    return notices

def _extract_links(html: str) -> list[tuple[str, str]]:
    return re.findall(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _convert_html_row_to_notice(row_html: str, base_url: str, lookback_days: int) -> Notice | None:
    text = _strip_html(row_html)
    # 제목 링크 추출
    links = _extract_links(row_html)
    title = ""
    detail_url = ""
    for href, label_html in links:
        label = _strip_html(label_html)
        if label and not any(x in label for x in ["첨부", "파일", "다운로드"]):
            title = label
            detail_url = _normalize_url(href, base_url)
            break
    if not title:
        return None

    registered_date = ""
    date_match = re.search(r"(20\d{2})[.\-/ ]\s*(\d{1,2})[.\-/ ]\s*(\d{1,2})", text)
    if date_match:
        y, m, d = date_match.groups()
        registered_date = f"{y}-{int(m):02d}-{int(d):02d}"

    if not _is_recent(registered_date, lookback_days):
        return None

    dept = ""
    manager = ""
    tel = ""
    dept_match = re.search(r"부서\s*[:：]\s*([^|]+)", text)
    if dept_match:
        dept = dept_match.group(1).strip()
    manager_match = re.search(r"담당자\s*[:：]\s*([^|]+)", text)
    if manager_match:
        manager = manager_match.group(1).strip()
    tel_match = re.search(r"연락처\s*[:：]\s*([0-9\-]+)", text)
    if tel_match:
        tel = tel_match.group(1).strip()

    file_name = ""
    file_url = ""
    for href, label_html in links:
        label = _strip_html(label_html)
        href_l = href.lower()
        if "file" in href_l or "download" in href_l or "attach" in href_l or label in {"첨부", "파일"}:
            file_name = label or "첨부파일"
            file_url = _normalize_url(href, base_url)
            break

    return Notice(
        notice_id=detail_url or f"{title}|{registered_date}",
        title=title,
        organization="과학기술정보통신부",
        department=dept,
        manager_name=manager,
        manager_tel=tel,
        registered_date=registered_date,
        url=detail_url,
        file_name=file_name,
        file_url=file_url,
        raw={"source": "html"},
    )


def _fetch_html_notices(config: dict[str, Any]) -> list[Notice]:
    cfg = config["msit"]
    if not cfg.get("html_fallback_enabled", True):
        return []

    base_url = "https://www.msit.go.kr"
    list_url = cfg.get("html_list_url", "https://www.msit.go.kr/bbs/list.do?sCode=user&mPid=121&mId=311")
    lookback_days = int(cfg.get("lookback_days", 30))
    max_pages = int(cfg.get("html_max_pages", 5))

    print(f"[정보] MSIT 게시판 HTML 보조 수집 시작: 최근 {lookback_days}일, 최대 {max_pages}페이지")
    notices: list[Notice] = []

    for page in range(1, max_pages + 1):
        params = {"sCode": "user", "mPid": "121", "mId": "311", "pageIndex": page}
        response = request_with_retry(list_url, params=params, max_retries=2)
        html = response.text

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL)
        page_count = 0
        for row in rows:
            notice = _convert_html_row_to_notice(row, base_url, lookback_days)
            if notice is not None:
                notices.append(notice)
                page_count += 1

        print(f"[정보] MSIT HTML pageIndex={page} 수집 공고 수: {page_count}")
        if page_count == 0 and page > 1:
            break

    return notices


def fetch_msit_notices(config: dict[str, Any]) -> list[Notice]:
    api_notices = _fetch_api_notices(config)
    html_notices: list[Notice] = []

    if not api_notices:
        print("[정보] API 변환 결과가 없어 MSIT 게시판 HTML 보조 수집을 시도합니다.")
        html_notices = _fetch_html_notices(config)

    deduped: dict[str, Notice] = {}
    for notice in api_notices + html_notices:
        deduped[notice.notice_id] = notice

    notices = sorted(
        deduped.values(),
        key=lambda n: (n.registered_date or "9999-99-99", n.title),
        reverse=True,
    )
    print(f"[정보] 최종 수집 공고 수: {len(notices)}")
    return notices

def _text_of(parent: ET.Element, path: str) -> str:
    el = parent.find(path)
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _parse_xml_items(xml_text: str) -> list[dict[str, Any]]:
    """MSIT XML 응답에서 body/items/item 목록만 추출합니다."""
    root = ET.fromstring(xml_text)

    result_code = _text_of(root, "./header/resultCode")
    result_msg = _text_of(root, "./header/resultMsg")

    if result_code and result_code != "00":
        raise RuntimeError(
            f"MSIT API 오류: resultCode={result_code}, resultMsg={result_msg}"
        )

    items: list[dict[str, Any]] = []

    for item_el in root.findall("./body/items/item"):
        item: dict[str, Any] = {
            "subject": _text_of(item_el, "subject"),
            "viewUrl": _text_of(item_el, "viewUrl"),
            "deptName": _text_of(item_el, "deptName"),
            "managerName": _text_of(item_el, "managerName"),
            "managerTel": _text_of(item_el, "managerTel"),
            "pressDt": _text_of(item_el, "pressDt"),
        }

        files: list[dict[str, str]] = []
        for file_el in item_el.findall("./files/file"):
            files.append(
                {
                    "fileName": _text_of(file_el, "fileName"),
                    "fileUrl": _text_of(file_el, "fileUrl"),
                }
            )

        item["files"] = files
        items.append(item)

    return items
