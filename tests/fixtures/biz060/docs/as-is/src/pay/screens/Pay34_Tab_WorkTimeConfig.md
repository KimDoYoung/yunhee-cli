# Pay34_Tab_WorkTimeConfig

- 종류: 화면
- 메뉴: 기초자료 > 30. 자산&경영 > 근로시간기준관리 (#1489)
- 파일: `client/vi/pay/Pay34_Tab_WorkTimeConfig.java`

## 서비스

| 서비스 | 호출 위치 | 서버 | SQL ID |
|:---|:---|:---|:---|
| `pay.Pay34_WorkTimeConfig.delete` | Pay34_Tab_WorkTimeConfig:181 | [`Pay34_WorkTimeConfig.java:49`](../../pay/services/Pay34_WorkTimeConfig.md) | `UpdateDataModel(pay34_work_time_config)` 동적 DELETE |
| `pay.Pay34_WorkTimeConfig.selectByCompanyId` | Pay34_Tab_WorkTimeConfig:135 | [`Pay34_WorkTimeConfig.java:24`](../../pay/services/Pay34_WorkTimeConfig.md) | [`pay34_work_time_config.selectByCompanyId`](../../pay/sql/pay34_work_time_config.md) |
| `pay.Pay34_WorkTimeConfig.update` | Pay34_Tab_WorkTimeConfig:146 | [`Pay34_WorkTimeConfig.java:44`](../../pay/services/Pay34_WorkTimeConfig.md) | `UpdateDataModel(pay34_work_time_config)` 동적 INSERT/UPDATE |

## 테이블

[`pay34_work_time_config`](../../../db/tables/pay.md)

## UI

#### 이벤트
[E0] 화면 열림 (생성자 L51-73) → settings(), retrieve()
[E1] retrieveButton[조회].Select (L76) → retrieve()
[E2] insertButton[등록].Select (L82) → insertRow()
[E3] updateButton[저장].Select (L88) → update()
[E4] deleteButton[삭제].Select (L94) → deleteChk()
       └ [E5] msgBox.DialogHide [YES] (L160) → deleteRow()

#### 메서드
| 메서드 | 줄 | 호출처 | 하는 일 | 구분 |
| --- | --- | --- | --- | --- |
| public retrieve() | L130-141 | 생성자,E1 | 서비스 pay.Pay34_WorkTimeConfig.selectByCompanyId | 업무 |
| public update() | L144-147 | E3 | 서비스 pay.Pay34_WorkTimeConfig.update | 업무 |
| public insertRow() | L150-155 | E2 | GridInsertRow 행 추가 | 업무 |
| private deleteChk() | L157-175 | E4 | msgBox.show() | 업무 |
| public deleteRow() | L178-182 | E5 | GridDeleteData | 업무 |
