# 축산 현황판

가격·시세 / 질병·방역 / 뉴스 / 통계를 한 화면에 모아 보여주고, 하루 한 번 자동 갱신되는 개인용 사이트입니다.

## 구조
- `index.html` — 화면. `data/data.json`을 읽어 그립니다.
- `scripts/fetch_data.py` — 데이터 수집 (파이썬 표준 라이브러리만 사용)
- `.github/workflows/update.yml` — 매일 한국시간 06:00 자동 실행 후 `data.json` 커밋

## 세팅 (처음 한 번)
1. GitHub에서 새 저장소를 만들고 이 폴더 내용을 그대로 올립니다.
2. **Settings → Pages → Source: Deploy from a branch → main / (root)** 로 저장합니다.
3. **Actions** 탭에서 `축산 데이터 업데이트`를 `Run workflow`로 한 번 수동 실행합니다. (뉴스·방역은 키 없이 바로 채워집니다)
4. 접속 주소: `https://<내아이디>.github.io/<저장소이름>/`

## 가격·통계 켜기 (선택, 무료 키 필요)
**Settings → Secrets and variables → Actions → New repository secret** 에 등록합니다.

| 이름 | 값 | 발급처 |
|---|---|---|
| `KAMIS_KEY` | KAMIS 인증키 | kamis.or.kr → 오픈API 신청 |
| `KAMIS_ID` | KAMIS 요청자 ID | 위와 동일 |
| `KOSIS_URL` | KOSIS 통계표 API 주소 (JSON) | kosis.kr 오픈API → 통계표 선택 후 'URL 생성' (형식은 json) |

`KOSIS_URL`은 가축동향조사(사육두수) 같은 통계표를 골라 만든 주소를 그대로 붙여넣으면 됩니다.

## 참고
- 한 출처가 실패해도 이전 데이터를 유지하고, 화면 하단에 실패 사실을 표시합니다.
- 저장소에 60일간 변경이 없으면 GitHub이 예약 실행을 멈출 수 있으니, 가끔 Actions 탭에서 상태를 확인해 주세요.
