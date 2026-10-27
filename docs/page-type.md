● 판별기를 tools/page-style.py에 만들었습니다. 표준 라이브러리만 쓰고 Python 3.8 이상에서 돕니다. 이 저장소의 tools/*.py와
  같은 위치입니다.

  사용법
  page-style.py Fnd01_Tab_FundSearch.tsx          # TOBE → SID만 출력 (SGVF)
  page-style.py Fnd01_Tab_FundSearch.java         # AS-IS → SID
  page-style.py --json a.tsx b.java               # 특징·근거까지 JSON 출력
  page-style.py --all <디렉터리>                  # 모든 *_Tab_* 판별 + SID별 분포
  page-style.py --compare <asis.java> <tobe.tsx>  # 두 SID가 같은지 (종료코드 0/1)
  - 화면 파일 머리 주석의 스타일: XXX와 판별 결과가 다르면 경고합니다.
  - 같은 폴더의 *_Edit_*, *_Page_*, *_Grid_* 파일을 따라가서 읽기 전용 폼인지, 팝업인지, 트리인지 판별합니다.

  구조: 코드를 두 부분으로 나눴습니다.
  - extract_tsx와 extract_java가 같은 모양의 특징을 뽑습니다. 특징에는 조회 툴바, 그리드·트리 개수, 폼 종류, 분할 방향,
    팝업 여부가 있습니다.
  - classify() 하나가 특징을 SID로 바꿉니다. SID 규칙이 바뀌면 이 함수만 고치면 됩니다.

  검증한 결과
  - 알려진 세 화면(Fnd01_Tab_FundSearch, Fnd01_Tab_FundCode, Fnd08_Tab_OrgAuth)은 AS-IS와 TOBE가 SGVF, SGEF, SGT로 모두
    일치합니다.
  - AS-IS 511개와 TOBE 237개에 돌렸습니다. 이름이 같은 236개 중 173개(약 73%)에서 AS-IS와 TOBE의 SID가 일치합니다.
  - TOBE 분포는 SG 68, SGP 22, SGVF 1, SGEF 7, SGT 3, TG 7, GG 39, CG 60, 미분류 30입니다. 정답을 아는 샘플은 세
    화면뿐이라 나머지의 정확도는 사람이 확인한 것이 아닙니다.

  새로 생긴 SID SGP: 처음 돌렸을 때 미분류의 가장 큰 덩어리가 "조회 툴바와 그리드 하나에, 편집은 팝업창"인 화면이었습니다.
  그래서 SGP(SearchGrid+Popup)를 추가했고 TOBE에서 22개가 해당합니다. docs/page-style.md 표에는 아직 넣지 않았습니다.

  남은 한계 (yunhee 담당자에게 넘길 때 같이 알려 주세요)
  - AS-IS와 TOBE의 SID가 다른 화면이 63개입니다. 대표 사례는 GG와 SG(7개), CG와 SG(6개씩 양쪽)입니다. CG는 "편집 가능한
    그리드"라서 AS-IS의 ColorButtonBar("저장") 같은 문자열 패턴으로 짐작하기 때문에 가장 부정확합니다.
  - 미분류가 TOBE 30개, AS-IS 59개입니다. 폼이 좌우로 붙은 화면, 트리와 폼이 같이 있는 화면(*_Tab_ClassTree), 그리드
    개수를 못 센 화면이 섞여 있습니다. 새 SID 후보이거나 규칙을 더 다듬어야 합니다.
  - 읽기 전용 폼의 기준은 setReadOnly 5개 이상(AS-IS), readOnly 1개 이상이고 [저장] 버튼 없음(TOBE)입니다. 경계에 있는
    화면은 틀릴 수 있습니다.

  yunhee 담당자에게는 이 파일과 위 한계를 같이 전달하면 됩니다. 규칙(SID 정의)은 classify()에 모아 두었으니, yunhee에서는
  이 부분을 설정 파일(docs/page-style.md 등)로 빼는 것을 권합니다. ntfy 알림은 보냈습니다.
