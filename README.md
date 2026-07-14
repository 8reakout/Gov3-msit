# MSIT Email Scheduler

과학기술정보통신부 사업공고 API를 조회해서 신규 공고를 이메일로 발송하는 Python 프로그램입니다.

## 구조

```text
msit_email_scheduler/
├─ main.py
├─ msit_fetch.py
├─ email_notifier.py
├─ config.example.yaml
├─ config.yaml
├─ .env.example
├─ requirements.txt
├─ seen_notice_ids.json
├─ latest_notices.json
├─ .gitignore
└─ .github/workflows/msit_email_notice.yml
```

## 로컬 실행

```powershell
copy .env.example .env
copy config.example.yaml config.yaml
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## .env 설정

```env
MSIT_SERVICE_KEY=공공데이터포털_인증키
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=보내는메일@gmail.com
SMTP_PASSWORD=구글_앱_비밀번호
MAIL_FROM=보내는메일@gmail.com
MAIL_TO=받는메일@example.com
MAIL_CC=
```

## GitHub Secrets

```text
MSIT_SERVICE_KEY
SMTP_HOST
SMTP_PORT
SMTP_USE_TLS
SMTP_USER
SMTP_PASSWORD
MAIL_FROM
MAIL_TO
MAIL_CC
```

## 주의

- Gmail은 일반 로그인 비밀번호가 아니라 앱 비밀번호를 사용해야 합니다.
- `seen_notice_ids.json`은 신규/기존 공고 구분을 위해 저장소에 유지합니다.
- `config.yaml`, `.env`, `msit_notice_latest.html`은 커밋하지 않습니다.
