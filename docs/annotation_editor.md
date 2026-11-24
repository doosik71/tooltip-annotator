# `scripts/annotation-editor.py`

`scripts/annotation-editor.py`는 이미지 위에 여러 출처의 annotation을 탭으로 바꿔 가며 보여 주고, 수술도구의 bounding box와 tip 좌표를 수동으로 수정할 수 있는 GUI 편집기다.

`--dataset <name>` 옵션을 주면 아래 경로가 자동으로 계산된다.

- 이미지 입력: `data/dataset/<name>/images/{train,val,test}`
- 최종 annotation 입출력: `data/dataset/<name>/annotation/{train,val,test}`
- 수동 보정본 입출력: `data/dataset/<name>/annotation-manual/{train,val,test}`
- 자동 annotation 입력(읽기 전용): `data/dataset/<name>/annotation-*/{train,val,test}` (예: `annotation-monai`, `annotation-qwen`)

## 사용자 문서

### 목적

자동 annotation 도구(MONAI, Qwen 등)의 결과를 사람이 비교·검토해 학습과 평가에 쓸 최종 레이블을 확정하는 도구다. 자동 결과 중 하나를 그대로 채택하거나, 고쳐서 수동 보정본으로 저장할 수 있다. 누락된 수술도구를 추가하거나, 잘못된 annotation을 삭제하거나, bbox와 tip 위치를 미세 조정할 수 있다.

### annotation 디렉터리의 역할

| 디렉터리            | 내용                                                     | 이 편집기         |
| ------------------- | -------------------------------------------------------- | ----------------- |
| `annotation`        | 학습·평가에 쓰는 **최종** 레이블                          | 읽기/쓰기         |
| `annotation-manual` | 사람이 직접 편집한 레이블. 어떤 스크립트도 다시 만들 수 없다 | 읽기/쓰기         |
| 그 밖의 `annotation-*` | 자동 annotation 도구의 결과 (`annotation-monai`, `annotation-qwen` 등) | **읽기 전용** |

`annotation`은 이 편집기가 관리한다. 편집해 저장하면 수동 보정본이 `annotation-manual`과 `annotation`에 함께 기록되고, 자동 결과를 고치지 않고 저장하면 그 결과가 `annotation`에 그대로 채택된다(아래 "저장 동작" 참고). 자동 annotation 디렉터리에는 절대 쓰지 않으므로, 자동 annotation 스크립트가 실행 중이어도 편집기를 함께 쓸 수 있다.

자동 annotation 디렉터리는 코드에 목록으로 정해져 있지 않다. `annotation` 디렉터리와 같은 위치에 있는 `annotation-*` 디렉터리(`annotation-manual` 제외)를 모두 찾아 탭으로 보여 주므로, 새 자동 annotation 도구는 `annotation-<이름>`에 결과를 쓰기만 하면 된다.

### 실행 전 요구 사항

- Python `3.12` 이상
- `opencv-python`
- `numpy`
- `tkinter` 사용 가능 환경
- `data/dataset/<dataset>/images` 디렉터리 존재

`tkinter`는 일반적인 데스크톱 Python 환경에 기본 포함되는 경우가 많지만, 일부 최소 설치 환경에서는 별도 패키지가 필요할 수 있다.

### 실행 방법

프로젝트 루트에서 실행한다.

```bash
python -m scripts.annotation-editor --dataset erop
```

가상환경을 직접 사용할 경우:

```bash
.venv/bin/python -m scripts.annotation-editor --dataset erop
```

경로를 직접 지정할 수도 있다(`--dataset` 기본값을 무시).

```bash
python -m scripts.annotation-editor \
  --images ./data/dataset/erop/images \
  --annotation ./data/dataset/erop/annotation \
  --manual ./data/dataset/erop/annotation-manual
```

### CLI 옵션

- `--dataset`
  - 데이터셋 이름(예: `erop`, `cholec80`). `--images`/`--annotation`/`--manual`을 명시하지 않았을 때 기본 경로를 계산하는 데 쓰인다.
- `--images`
  - 원본 RGB 이미지 루트. 기본값은 `data/dataset/<dataset>/images`. 명시하면 `--dataset` 기본값보다 항상 우선한다.
- `--annotation`
  - 최종 annotation JSON 루트. 기본값은 `data/dataset/<dataset>/annotation`. 명시하면 `--dataset` 기본값보다 항상 우선한다. 이 디렉터리와 같은 위치의 `annotation-*` 디렉터리가 자동 annotation 탭이 된다.
- `--manual`
  - 수동 보정본 저장 루트. 기본값은 `data/dataset/<dataset>/annotation-manual`. 명시하면 `--dataset` 기본값보다 항상 우선한다.
- `--auto-save` / `--no-auto-save`
  - `Auto Save`의 시작 상태를 정한다. 기본값은 켜짐(`--auto-save`)이고, `--no-auto-save`를 주면 매번 저장 여부를 묻는 동작으로 시작한다. 어느 쪽이든 실행 중에 툴바 체크박스로 바꿀 수 있다.

`--dataset`과 세 경로 옵션을 모두 생략하면 `data/dataset-src`와 `data/dataset` 아래에서 찾은 **첫 번째 데이터셋**이 자동으로 선택된다. 따라서 아래처럼 인자 없이 실행할 수 있다.

```bash
python -m scripts.annotation-editor
```

찾은 데이터셋이 하나도 없으면 어떤 옵션이 필요한지 알려주는 메시지와 함께 종료한다.

`--dataset`과 세 경로 옵션을 모두 주지 않으면 어떤 플래그가 필요한지 알려주는 에러로 즉시 실패한다.

### 화면 구성

#### 상단 툴바

왼쪽부터 다음 순서로 놓인다.

- `Dataset`
  - 편집할 데이터셋을 선택한다. 목록은 `data/dataset-src`와 `data/dataset` 아래에서 찾은 이름이다. 바꾸면 images·annotation·annotation-manual 경로가 모두 해당 데이터셋 기준으로 다시 계산되고, 자동 annotation 탭도 다시 찾은 뒤 현재 split이 다시 로드된다. `--images` 등 경로 옵션을 직접 지정해 실행한 경우에는 비활성화된다.
- `Split`
  - `train`, `val`, `test` 중 하나를 선택한다.
- `Add Tool[INS]`
  - 새 수술도구 annotation 추가 모드로 들어간다. 단축키 `Insert`.
- `Delete Tool[DEL]`
  - 현재 선택된 annotation을 삭제한다. 단축키 `Delete`.
- `Save[F2]`
  - 현재 탭의 annotation을 `annotation`에 반영한다. 단축키 `F2` 또는 `Ctrl+S`. 자세한 규칙은 "저장 동작"을 참고한다.
- `Reload[F3]`
  - 저장하지 않은 변경을 버리고 `Default` 탭으로 전환해 `annotation` 디렉터리의 값을 다시 읽는다. 단축키 `F3`.
- `Screenshot[F5]`
  - 현재 이미지를 overlay와 함께 `data/dataset/<dataset>/screenshot/<이미지 파일 이름>`으로 저장한다. 단축키 `F5`이다.
  - annotation overlay는 `Show Annotation` 체크 상태를 그대로 따르고, 현재 탭에 보이는 annotation을 그린다.
  - 화면 캡처가 아니라 원본 해상도로 다시 그린다. 선택 강조색, 리사이즈 핸들, 추가 모드 미리보기 박스 같은 편집용 표시는 넣지 않으며, 모든 박스는 비선택 색(`#3bd7ff`)으로 그린다. tip 연결선은 점선이 아닌 실선이다.
  - 저장하지 않은 편집도 화면에 보이는 그대로 반영된다. 같은 이름의 파일이 있으면 덮어쓴다.
  - `--images` 등 경로 옵션만으로 실행해 데이터셋 이름이 없으면 `--images` 디렉터리 옆의 `screenshot/`에 저장한다.
- `Auto Save [F9]`
  - 켜 두면 다른 이미지나 split으로 이동하거나 창을 닫을 때 저장 여부를 묻지 않고 바로 저장한다. **기본값은 켜짐**이며, `--no-auto-save`로 끈 상태로 시작할 수 있다. 탭을 바꿀 때는 이 설정과 무관하게 항상 묻는다. 단축키 `F9`.
- `Show Annotation [F10]`
  - annotation overlay 표시 여부를 전환한다. 끄면 도구를 선택하거나 편집할 수 없다. 단축키 `F10`.
- `Keep Tab [F11]`
  - 다른 프레임이나 split으로 이동할 때 탭을 유지할지 정한다. **기본값은 꺼짐**이며, 이때는 항상 `Default` 탭으로 돌아간다. 켜면 마지막으로 직접 고른 탭(예: `Detr`, `Opus`)을 계속 보여 주고, 그 탭에 파일이 없는 프레임만 `Default`로 연다. `Reload`를 누르거나 데이터셋을 바꾸면 기억한 탭이 `Default`로 돌아간다. 단축키 `F11`.
- `Every`
  - 이미지 목록에 매 N번째 파일만 보여 준다(1〜20, **기본값 1**은 전체). 영상 번호나 프레임 번호는 보지 않고, split 안에서 파일 이름순으로 매긴 목록 번호(1부터 시작)가 N의 배수인 파일만 남긴다. 예를 들어 10이면 목록 번호 10, 20, 30, …이 보인다.
  - 처음부터 순서대로 보정하면 앞쪽 영상에만 보정이 몰리므로, N을 키워 split 전체를 넓게 훑으며 보정할 때 쓴다. cholec80은 1초에 1장이라 N = 20이면 20초 간격이다.
  - `#` 칼럼은 원래 목록 번호를 그대로 보여 준다. 이전·다음 이동(`↑`/`↓`, 마우스 휠 등)은 보이는 파일 사이에서만 움직인다.
  - 지금 보고 있는 파일이 목록에서 빠지면 그 앞에서 가장 가까운 보이는 파일로 이동한다. 이때 저장하지 않은 편집이 있으면 다른 파일로 이동할 때와 같이 처리한다.
  - 목록 옆 표시 막대는 지금처럼 split 전체를 기준으로 한다.
  - 목록 위의 `Images (현재 / 전체)`도 split 전체 기준이다. N이 1이 아니면 뒤에 걸러진 목록 기준의 위치와 파일 수를 함께 적는다. 예: `Images (20 / 71,032), Every 20 (1 / 3,551)`.
  - split을 바꿔도 N은 유지되고, 편집기를 다시 실행하면 1로 돌아간다.

#### 버튼 색상

버튼은 하는 일의 성격에 따라 글자색이 다르다.

| 버튼                  | 글자색             |
| --------------------- | ------------------ |
| `Add Tool [INS]`      | 파랑 `#1565c0`     |
| `Delete Tool [DEL]`   | 빨강 `#c62828`     |
| `Save [F2]`           | 주황 `#e65100`     |
| `Reload [F3]`         | 보라 `#6a1b9a`     |
| `Screenshot [F5]`     | 청록 `#00838f`     |

비활성 상태에서는 모두 회색 `#9e9e9e`로 바뀌어, 색이 있는 버튼이라도 지금 누를 수 없다는 것이 드러난다.

`Add Tool`은 추가 모드에 들어가면 라벨이 `Adding... (Esc/Wheel to cancel)`로 바뀌면서 배경이 노란색 `#ffe680`이 된다. 이 상태에서 버튼을 다시 누르면 `Esc`처럼 추가 모드가 취소된다.

#### 단축키 정리

| 단축키             | 동작                            |
| ------------------ | ------------------------------- |
| `Insert`           | 수술도구 추가 모드              |
| `Delete`           | 선택된 annotation 삭제          |
| `F2` 또는 `Ctrl+S` | 저장                            |
| `F3`               | `annotation`에서 다시 읽기      |
| `F5`               | overlay 포함 스크린샷 저장      |
| `F9`               | `Auto Save` 켜기/끄기           |
| `F10`              | `Show Annotation` 켜기/끄기     |
| `F11`              | `Keep Tab` 켜기/끄기            |
| `Esc`              | 추가 모드 취소                  |
| 방향키             | 이전/다음 이미지                |
| `1`~`9`            | 해당 번호의 탭 선택             |
| 마우스 오른쪽 버튼 | 도구 팝업 메뉴                  |

낱자 키(`a`, `d`, `s`, `r`, `v`)는 바인딩하지 않는다. 입력 포커스가 어디에 있든 최상위 창이 받기 때문에, 무심코 누른 `d` 하나로 annotation이 삭제되는 사고를 막기 위해서다.

#### 좌측 패널

선택된 split 안의 이미지 목록을 `#`, `Image`, `Source` 세 칼럼(`ttk.Treeview`)으로 표시한다. 목록에서 이미지를 클릭하면 우측 메인 화면에 해당 이미지가 로드된다.

`#` 칼럼은 일련번호, `Image` 칼럼은 파일 이름이다. 일련번호는 1부터 시작하고, 자리수는 그 split의 전체 프레임 수에 맞춰 자동으로 정해진다.

```text
#        Image                                 Source
000001   doctor_250620_084707_00000000.png               # 108,424 프레임 → 6자리
00001    video01_00000000.png                  Manual    # 71,032 프레임 → 5자리
1        frame_0000.png                                  # 3 프레임 → 1자리
```

split이나 데이터셋을 바꾸면 자리수도 다시 계산된다.

`Source` 칼럼은 그 프레임의 `annotation` 레이블이 어느 탭의 레이블과 같은지 보여 주고, 행의 배경색도 이 값에 따라 정해진다.

- `Manual`, 그리고 자동 annotation 탭(`Monai`, `Opus`, `Qwen` 등)을 탭 순서대로 비교해 처음 일치하는 탭 이름을 표시한다. 일치하는 탭이 없거나 `annotation`에 파일이 없으면 빈칸이다. 예를 들어 예전 검출기로 다시 만든 레이블처럼 지금 어느 탭에도 없는 출처는 빈칸이 된다.
- 비교 대상은 파일의 `annotations` 목록(box, tip, tip2, label)뿐이다. `source`, `model`, `edited_at` 같은 메타데이터는 보지 않는다.
- 도구가 없는 프레임(`annotations`가 빈 목록)은 같은 빈 목록을 가진 첫 탭과 일치한다.
- 수만 개 행을 한꺼번에 계산하지 않는다. 스크롤이 멈추고 50ms(`SOURCE_UPDATE_DELAY_MS`) 뒤 지금 화면에 보이는 행 중 아직 값이 없는 행만 작업 스레드에서 계산하고, 끝난 결과를 30ms(`SOURCE_POLL_MS`)마다 확인해 칸을 채운다. 한 번 계산한 값은 split을 다시 열 때까지 유지된다.
- 저장(편집 저장이나 자동 결과 채택)으로 `annotation` 파일이 바뀌면 현재 프레임의 값만 바로 다시 계산한다.
- 행 배경색은 `Default` 다음 탭부터 탭 순서대로 `SOURCE_ROW_BACKGROUNDS`의 10가지 색을 하나씩 쓴다. 첫 색은 `Manual`의 노란색(`#ffe9a8`)이고, cholec80에서는 `Monai` 하늘색, `Opus` 연두색, `Qwen` 분홍색, `Qwen2.5` 살구색, `Yolo` 연보라색이 된다. 탭이 10개를 넘으면 나머지 탭과, 일치하는 탭이 없는 행은 기본 색으로 둔다.
- 행 색은 `Source` 값만 따른다. 그래서 수동 보정본이 있어도 `annotation`이 다른 탭의 결과를 채택한 프레임은 그 탭의 색으로 보인다. 수동 보정본이 있는지는 목록에 따로 표시하지 않고, 표시 막대의 호박색 눈금으로만 알 수 있다.
- 선택된 행은 `Treeview`에서 tag 색보다 테마의 선택 색이 우선하므로, 선택된 상태에서는 출처 색 대신 일반 선택 색으로 보인다.

스크롤바 왼쪽의 얇은 표시 막대는 VS Code의 overview ruler처럼 목록 전체에서 프레임 위치를 보여 준다. 막대 높이가 목록 전체에 대응하며, 수동 보정 프레임은 호박색(`#e8a33d`) 눈금, 현재 프레임은 파란색(`#1565c0`) 눈금으로 표시된다. 지금 목록에 보이는 행의 범위는 반투명한 어두운 상자로 겹쳐 그린다. 그리는 순서는 수동 보정 눈금, 보이는 범위 상자, 현재 프레임 눈금이다. 그래서 상자 안의 보정 눈금은 어둡게 비쳐 보이고, 현재 프레임 눈금은 항상 맨 위에 보인다. 표시 전용이라 클릭해도 반응하지 않는다.

- 같은 픽셀 높이에 놓이는 눈금은 하나로 합쳐 그리므로, 7만 장 규모 split에서도 그리는 양은 막대 높이를 넘지 않는다.
- 수동 보정 프레임의 위치는 split을 열 때 한 번 계산하고, 수동 보정본을 저장할 때 현재 프레임만 갱신한다.
- 막대는 위아래에 스크롤바 화살표 버튼 높이만큼 여백을 두어, 스크롤바의 스크롤 영역과 같은 높이로 맞춘다. 화살표 높이는 테마마다 다르므로 고정값을 쓰지 않고, 스크롤바 크기가 바뀔 때마다 `identify()`로 측정한다. 다만 스크롤바 막대(thumb)에는 최소 크기가 있어서, 큰 split에서는 눈금과 thumb의 위치가 여전히 1~3픽셀 어긋날 수 있다. 보이는 범위 상자는 눈금과 같은 비율로 그리므로, 상자 안에 들어온 눈금이 곧 지금 목록에 보이는 행이다. 스크롤바를 드래그할 때는 thumb 대신 상자를 보고 원하는 눈금에 맞추면 된다.
- 큰 split에서는 화면에 보이는 행이 막대 높이로 1픽셀도 되지 않으므로, 상자는 최소 높이(`LIST_MARKER_VISIBLE_MIN_HEIGHT = 8`)로 그린다. 이때 상자는 실제 범위의 중심에 놓인다.
- Tk 캔버스는 반투명 채우기를 지원하지 않는다. 그래서 상자 아래에 있는 색(막대 배경과 보정 눈금)에 검정을 30% 섞은 색(`LIST_MARKER_VISIBLE_COLOR`, `LIST_MARKER_VISIBLE_ALPHA`)을 미리 계산해 칠하는 방식으로 반투명을 흉내 낸다. 플랫폼마다 동작이 다른 `stipple` 무늬는 쓰지 않았다.

| 프레임 상태        | 배경색                       |
| ------------------ | ---------------------------- |
| 수동 보정본 없음   | 기본값 (흰색)                |
| 수동 보정          | 연한 노랑 `#ffe9a8`          |
| 수동 보정 + 선택됨 | 호박색 `#e8a33d`             |

색상은 `scripts/annotation-editor.py` 상단의 `MANUAL_ITEM_*` 상수로 정의되어 있다.

#### 상태 표시줄

창 하단 오른쪽에 현재 상태가 표시된다. 왼쪽에는 마우스 조작 안내가 함께 놓인다.

```text
tools 2 | mode=select
```

`tools` 뒤의 숫자는 현재 프레임의 annotation 개수로, 1.5배 크기의 굵은 파란색(`#1565c0`)으로 강조된다. `mode`는 `select` 또는 `add`이다. 저장·다시 읽기·스크린샷 같은 동작을 하면 `|` 오른쪽에 그 결과 메시지가 대신 표시되었다가, 다음 상태 변화 때 `mode=...`로 돌아온다. 도구 수는 메시지가 표시되는 동안에도 계속 보인다.

도구 수의 크기와 색은 `TOOL_COUNT_FONT_SCALE`, `TOOL_COUNT_FOREGROUND` 상수로 바꿀 수 있다.

#### 우측 메인 화면

상단에 annotation 출처를 고르는 탭이 있고, 그 아래 화면에 다음 요소가 함께 표시된다.

- 원본 이미지
- annotation bbox
- annotation tip (두 번째 tip이 있으면 함께)

#### annotation 탭

| 탭 (단축키)            | 보여 주는 annotation                    | 활성 조건                          |
| ---------------------- | --------------------------------------- | ---------------------------------- |
| `[1] Default`          | `annotation` (최종 레이블)               | 항상                               |
| `[2] Manual`           | `annotation-manual` (수동 보정본)        | 현재 프레임의 수동 보정본이 있을 때 |
| `[3] Monai`, `[4] Qwen` 등 | `annotation-monai`, `annotation-qwen` 등 | 현재 프레임의 결과 파일이 있을 때   |

- 자동 annotation 탭은 `annotation-` 뒤의 이름을 첫 글자만 대문자로 바꿔 이름을 붙이고, 이름순으로 `Manual` 뒤에 놓는다.
- 숫자 키 `1`~`9`로 해당 번호의 탭을 고를 수 있다. 비활성 탭은 클릭이나 숫자 키로 고를 수 없다.
- 탭은 클릭하기 쉽도록 안쪽 여백을 좌우 20px, 상하 6px로 넓혔다. `TAB_PADDING` 상수로 바꿀 수 있다.
- 선택된 탭은 굵은 흰 글자에 파란 배경(`#1565c0`, 표시 막대의 현재 프레임 눈금과 같은 색)으로 그려 지금 보고 있는 출처가 바로 보이게 했다. `TAB_SELECTED_BACKGROUND`, `TAB_SELECTED_FOREGROUND` 상수로 바꿀 수 있다. 굵은 글씨는 폭이 조금 넓어서, 탭을 바꾸면 탭 폭이 몇 픽셀 달라질 수 있다.
- 현재 프레임에 파일이 없어 비활성인 탭은 다른 탭(`#c3c3c3`)보다 어두운 배경(`#a6a6a6`)에 회색 글자(`#7a7a7a`)로 그린다. `TAB_DISABLED_BACKGROUND`, `TAB_DISABLED_FOREGROUND` 상수로 바꿀 수 있다. ttk 스타일의 상태별 색 지정(`style.map`)은 옵션마다 상속된 지정을 통째로 대체하므로, 선택 탭 색을 지정하면서 테마의 회색 비활성 글자색도 함께 다시 적어야 한다.
- 활성 여부는 프레임을 열 때마다 파일 존재로 다시 판단한다. 자동 annotation 스크립트가 실행 중이어도 새로 생긴 결과가 바로 반영된다. 단, 새 `annotation-*` **디렉터리**는 편집기를 다시 실행하거나 데이터셋을 다시 선택해야 탭으로 나타난다.
- 다른 프레임을 열면 기본적으로 `Default` 탭이 선택된다. `Keep Tab`을 켜 두면 마지막으로 직접 고른 탭이 유지된다. 그 탭에 파일이 없는 프레임은 `Default`로 열리지만, 고른 탭은 기억해 두었다가 파일이 있는 프레임에서 다시 선택한다.
- 저장하지 않은 편집이 있는 상태에서 탭을 바꾸면 `Auto Save` 설정과 무관하게 저장 여부를 묻는다. `Cancel`을 고르면 탭이 바뀌지 않는다.

### 편집 방법

#### bbox 이동

bbox 내부를 마우스로 드래그하면 전체 박스를 이동할 수 있다. tip도 함께 같은 만큼 이동한다.

#### 박스가 겹쳐 있는 경우

클릭 지점에 여러 박스가 겹쳐 있으면 **가장 작은 박스**가 선택된다. 큰 박스 안에 들어 있는 작은 박스도 그대로 클릭해서 선택할 수 있다.

큰 박스를 선택하려면 작은 박스에 덮이지 않은 부분을 클릭한다. 크기가 같은 박스끼리 겹친 경우에는 현재 선택이 유지된다.

#### bbox 크기 조정

선택된 bbox의 네 모서리 핸들을 드래그하면 박스 크기를 조정할 수 있다.

박스를 줄여 tip이 박스 밖으로 나가게 되면, tip은 박스 안에서 가장 가까운 위치로 따라 들어온다. 같은 드래그 안에서 박스를 다시 키우면 tip은 원래 위치로 돌아간다.

#### tip 이동

빨간색 tip 핸들을 드래그하면 tip 좌표를 직접 조정할 수 있다.

#### 핸들 위 커서

마우스 포인터가 tip 핸들이나 선택된 bbox의 리사이즈 핸들 위에 오면 커서가 십자선(`crosshair`)으로 바뀌고, 그 핸들 하나가 흰색(`#ffffff`)으로 칠해진다. 드래그하는 동안에는 십자선과 강조가 유지되고, 추가 모드에서는 바뀌지 않는다. 겹친 핸들 중 어느 것이 잡힐지를 클릭 전에 보여 주므로, 강조된 핸들이 곧 드래그될 핸들이다.

TurboVNC 같은 원격 화면에서는 화살표 커서의 끝이 실제 클릭 지점과 몇 픽셀 어긋나 보일 수 있다. 특히 이미지 가장자리에 붙은 핸들은 절반이 캔버스 밖으로 잘려 클릭할 수 있는 폭이 좁기 때문에, 화살표 끝을 보고 누르면 빗나가기 쉽다. 십자선은 교차점이 실제 클릭 지점이므로 이를 보고 조준하면 된다. 커서 모양과 강조 색은 `HANDLE_CURSOR`, `HANDLE_HOVER_FILL` 상수로 바꿀 수 있다.

#### 새 수술도구 추가

1. `Add Tool` 버튼 클릭
2. 이미지 위에서 마우스를 드래그해 bbox 생성
3. 생성된 bbox가 새 annotation으로 추가됨
4. 필요하면 tip을 추가로 드래그해 조정

`Esc` 키로 add mode를 취소할 수 있다.

추가 모드 동안에는 이미지가 절반 밝기(`ADD_MODE_BRIGHTNESS = 0.5`)로 어두워지고, 드래그 중인 bbox 내부만 원래 밝기로 표시된다. 박스가 추가되거나 추가 모드가 취소되면 원래 밝기로 돌아온다. annotation 박스와 tip 같은 overlay 선은 어두워지지 않으며, 스크린샷에도 반영되지 않는다.

#### 잘못된 annotation 삭제

1. 삭제할 annotation 선택
2. `Delete Tool` 버튼 클릭, `Delete` 키 입력, 또는 오른쪽 클릭 메뉴의 `Delete Tool`

도구가 하나도 없는 상태로 저장해도 된다. 빈 `annotations` 배열이 수동 보정본으로 기록되므로, "이 프레임에는 도구가 없다"는 판단이 최종 레이블에 남는다.

#### 두 번째 tip

벌어진 가위나 bipolar forceps처럼 끝이 둘인 도구는 두 번째 tip(`tip2`)을 가질 수 있다. `annotation-qwen` 결과에 들어 있을 수 있고, 편집기에서 직접 추가하거나 지울 수도 있다.

- 두 번째 tip은 첫 번째 tip과 같은 빨간 원형 핸들로 그려지며, 드래그로 옮길 수 있다.
- bbox를 이동하면 두 tip이 함께 이동하고, bbox를 줄이면 두 tip이 모두 박스 안으로 따라 들어온다.
- 추가와 삭제는 오른쪽 클릭 메뉴로 한다(아래 참고).

#### 오른쪽 클릭 메뉴

이미지 위에서 마우스 오른쪽 버튼을 누르면 팝업 메뉴가 뜬다. 도구 위에서 누르면 그 도구가 먼저 선택된다. 빈 곳에서 누르면 현재 선택이 그대로 유지된다.

메뉴에는 지금 쓸 수 있는 항목만 다음 순서로 나온다.

| 순서 | 메뉴 항목                                  | 나오는 조건과 동작                                            |
| ---- | ------------------------------------------ | ------------------------------------------------------------ |
| 1    | `Add Second Tip` 또는 `Remove Second Tip`  | 선택된 도구가 있을 때만 나온다. 두 번째 tip이 없으면 `Add Second Tip`: 오른쪽 클릭한 위치에 두 번째 tip을 만든다(위치가 박스 밖이면 박스 안의 가장 가까운 픽셀로 옮긴다). 있으면 `Remove Second Tip`: 두 번째 tip을 지운다 |
| 2    | `Add Tool` 또는 `Delete Tool`              | 선택된 도구가 없으면 `Add Tool`: 추가 모드로 들어간다(`Add Tool` 버튼과 같다). 있으면 `Delete Tool`: 선택된 도구를 삭제한다 |
| 3    | `Cancel`                                   | 항상 나온다. 아무것도 하지 않고 메뉴를 닫는다                  |

`Delete Tool`은 툴바의 삭제 버튼과 같은 빨간 글자로 표시된다. 메뉴는 `Cancel`, `Esc`, 또는 메뉴 바깥 아무 곳이나 클릭해도 닫힌다. 바깥 클릭은 메뉴를 닫는 데만 쓰이고 그 위치의 도구 선택 등에는 전달되지 않는다.

`Show Annotation`이 꺼져 있으면 도구를 고를 수 없으므로 `Add Tool`과 `Cancel`만 나온다. 추가 모드 중에는 메뉴가 뜨지 않는다.

### 저장 동작

어느 탭에서 저장하느냐, 그리고 편집했느냐에 따라 쓰는 곳이 다르다.

| 탭                     | 편집 여부   | 저장 결과                                                                 |
| ---------------------- | ----------- | ------------------------------------------------------------------------- |
| 모든 탭                | 편집함      | `annotation-manual`과 `annotation`에 `source: "manual"`로 저장           |
| `Monai`, `Qwen` 등     | 편집 안 함  | 그 탭의 JSON 파일을 `annotation`에 **그대로 복사**(채택). `source`는 원래 값 유지 |
| `Default`, `Manual`    | 편집 안 함  | 저장할 것이 없으므로 `Save`가 비활성                                       |

- 자동 annotation 탭에서는 편집하지 않아도 `Save`가 활성화되어 있다. 누르면 그 결과를 최종 레이블로 채택한다.
- 채택할 때 그 프레임의 `annotation-manual` 파일은 지우지 않는다. 수동 보정본은 `Manual` 탭에서 계속 볼 수 있다.
- 자동 annotation 탭에서 편집해 저장하면 그 결과는 이제 수동 보정본이므로 화면이 `Manual` 탭으로 바뀐다.
- 자동 annotation 디렉터리에는 어떤 경우에도 쓰지 않는다.

다음 두 방법으로 저장할 수 있다.

- `Save` 버튼 클릭
- `F2` 또는 `Ctrl+S`

이미지나 split을 바꾸거나 창을 닫을 때 저장되지 않은 변경이 있으면 저장 여부를 묻는다.

#### 자동 저장

`Auto Save`를 켜면 이 질문이 사라지고, 같은 상황에서 묻지 않고 바로 저장한다. 프레임을 연속으로 훑으며 보정할 때 화살표 키만으로 작업을 이어갈 수 있다.

- 기본값은 켜짐이다. 매번 저장 여부를 확인받고 싶으면 체크박스를 끄거나 `--no-auto-save`로 실행한다.
- 저장되지 않은 변경이 있는 상태에서 `Auto Save`를 켜면 그 변경이 즉시 저장된다.
- 창을 닫을 때도 묻지 않고 저장한다.
- 탭 전환은 예외다. 다른 탭을 보려는 것일 수 있으므로 항상 묻는다.
- 편집하지 않은 프레임은 저장하지 않는다. 자동 annotation 탭을 보며 이동하더라도 채택은 `Save`를 눌러야만 일어난다.

잘못 저장한 프레임은 원하는 탭을 골라 다시 저장하면 된다. 예를 들어 `Monai` 탭에서 편집 없이 `Save`를 누르면 MONAI 결과가 다시 `annotation`에 채택된다.

### 저장 파일 형식

편집해 저장하면 각 이미지에 대해 같은 basename의 JSON 파일을 **두 곳에** 저장한다. 두 파일의 내용은 바이트 단위로 동일하다.

예시:

```text
이미지:             ./data/dataset/erop/images/train/sample01_00000030.png
수동 보정본(원본):  ./data/dataset/erop/annotation-manual/train/sample01_00000030.json
annotation(최종):   ./data/dataset/erop/annotation/train/sample01_00000030.json
```

JSON 구조는 다음과 같다.

```json
{
  "image": "sample01_00000030.png",
  "width": 736,
  "height": 480,
  "source": "manual",
  "edited_at": "2026-10-26T15:04:11+09:00",
  "annotations": [
    {
      "bbox": {
        "x": 120,
        "y": 90,
        "width": 80,
        "height": 40
      },
      "tip": {
        "x": 145,
        "y": 102
      },
      "tip2": {
        "x": 190,
        "y": 125
      },
      "label": "bipolar forceps"
    }
  ]
}
```

`source`는 이 편집기가 편집 후 저장한 파일에서 항상 `manual`이고, `edited_at`은 저장 시각(ISO 8601, 로컬 타임존)이다. `tip2`(두 번째 tip)와 `label`(도구 이름)은 있을 때만 기록된다. `label`은 편집기에서 바꿀 수 없고, 읽어 온 값을 그대로 보존한다.

자동 annotation을 편집 없이 채택한 프레임은 `annotation`에만 그 결과 파일의 사본이 생긴다. `source`는 원래 값(예: `qwen`, `tooltip-annotator/scripts/generate-annotation-monai.py`)이고 `edited_at`은 붙지 않는다.

### 문제 해결

#### 창이 열리지 않는 경우

GUI 환경이 없는 터미널 세션일 수 있다. 로컬 데스크톱 세션이나 X11/Wayland가 활성화된 환경에서 실행해야 한다.

#### annotation 파일이 없는데 편집은 가능한가

가능하다. `Default` 탭에 기존 JSON이 없으면 빈 annotation 상태로 열리고, 편집해 저장하면 새 JSON 파일이 생성된다.

#### `Monai`나 `Qwen` 탭이 비활성화된 경우

현재 프레임에 그 도구의 결과 파일이 없는 경우다. 자동 annotation이 아직 그 프레임까지 진행되지 않았을 수 있다. 다음에 그 프레임을 열 때 다시 확인한다.

#### 자동 annotation 탭이 아예 보이지 않는 경우

`annotation` 디렉터리와 같은 위치에 `annotation-<이름>` 디렉터리가 있는지 확인한다. 편집기를 실행한 뒤에 생긴 디렉터리는 편집기를 다시 실행하거나 데이터셋을 다시 선택해야 나타난다.

#### 자동 annotation 스크립트가 다시 실행되면 보정한 내용이 사라지는가

사라지지 않는다. 자동 annotation 스크립트는 자기 `annotation-*` 디렉터리에만 쓰고, 이 편집기는 `annotation`과 `annotation-manual`에만 쓴다. 이미 채택한 결과도 `annotation`에 복사된 사본이므로, 자동 결과가 다시 만들어져도 바뀌지 않는다. 새 결과를 쓰려면 그 탭에서 다시 `Save`를 누른다.

## 개발 문서

### 입력/출력 경로 모델

편집기는 데이터셋 이름 하나와 세 개의 루트 디렉터리, 그리고 실행 시 찾아낸 자동 annotation 디렉터리들을 사용한다.

- `--images`
  - 원본 RGB 이미지 루트
- `--annotation`
  - 최종 레이블 루트. 편집 저장 시 수동 보정본의 사본이, 채택 시 자동 결과의 사본이 여기에 쓰인다
- `--manual`
  - 수동 보정본 루트. 이 편집기만 쓴다
- 자동 annotation 루트
  - `--annotation`의 부모 디렉터리에서 찾은 `annotation-*` 디렉터리(`--manual`과 `annotation-manual` 제외). 읽기만 한다

각 루트 아래에는 모두 `train`, `val`, `test` 디렉터리가 있다고 가정한다. `images`의 split 디렉터리만 시작할 때 검사한다.

`main()`은 `parse_args()` 직후 세 경로 모두 `tooltip.dataset_paths.resolve_path()`로 확정한다. `--dataset`만 주면 각각 `data/dataset/<dataset>/{images,annotation,annotation-manual}`로 기본값이 계산되고, 경로 옵션을 직접 주면 그 값이 항상 우선한다.

`--dataset`과 경로 옵션을 모두 생략하면 `list_datasets()[0]`을 기본값으로 쓴다.

`Dataset` 콤보로 데이터셋을 바꾸면 `_switch_dataset()`이 세 루트를 전부 데이터셋 이름 기준으로 다시 계산하고 `_rebuild_tabs()`로 탭을 다시 만든다. 이는 직접 지정한 경로를 조용히 버리는 셈이 되므로, 경로 옵션이 하나라도 주어졌으면 `main()`이 `args.dataset_locked`를 세워 콤보를 비활성화한다.

`_switch_dataset()`은 선택한 데이터셋의 images 디렉터리가 실제로 있을 때만 출력 디렉터리를 만든다. `data/dataset-src`에만 있고 아직 프레임을 추출하지 않은 데이터셋을 골랐을 때 빈 디렉터리를 만들지 않기 위해서다.

### 내부 상태

`AnnotationEditor` 클래스는 현재 이미지와 편집 상태를 메모리에 유지한다.

주요 상태는 다음과 같다.

- `current_image_rgb`
  - 현재 원본 이미지
- `current_annotations`
  - 현재 편집 중인 annotation 목록
- `selected_annotation_index`
  - 현재 선택된 annotation 인덱스
- `dirty`
  - 저장되지 않은 변경 여부
- `mode`
  - `select` 또는 `add`
- `auto_save_var`
  - `Auto Save` 체크박스 상태. `--auto-save`/`--no-auto-save`로 초기값이 결정되며 기본은 켜짐이다
- `current_dataset`
  - 현재 선택된 데이터셋 이름. `Dataset` 콤보를 바꾸면 `_switch_dataset()`이 세 루트를 모두 다시 계산한다
- `dataset_locked`
  - 경로 옵션을 직접 지정해 실행했는지 여부. 참이면 `Dataset` 콤보를 비활성화한다
- `tabs`
  - 탭마다 `(이름, 루트, 종류)` 튜플. 종류는 `default`, `manual`, `auto` 중 하나다. 인덱스 0이 `Default`(`DEFAULT_TAB`), 1이 `Manual`(`MANUAL_TAB`)이고 그 뒤가 자동 annotation이다. `_discover_tabs()`가 만든다
- `current_tab`
  - 지금 화면에 보이는 탭의 인덱스. 프레임을 새로 열 때마다 `DEFAULT_TAB`으로 돌아간다
- `manual_stems`
  - 현재 split에서 수동 보정본이 있는 파일 스템 집합. split을 열 때 `annotation-manual/{split}`를 한 번만 훑어서 만들고, 이후 수동 보정본을 저장할 때 증분 갱신한다. 10만 장 규모 split에서도 목록 강조를 위해 프레임마다 파일 존재 여부를 확인하지 않기 위한 것이다. 탭 활성 여부는 이 집합이 아니라 현재 프레임 하나에 대해서만 파일 존재로 판단한다

### 표시 방식

원본 이미지는 창 크기에 맞게 OpenCV로 축소한 뒤 `Canvas`에 표시된다.

annotation overlay는 Canvas 도형으로 따로 그린다.

- bbox: 사각형
- tip, 두 번째 tip: 빨간 원형 핸들. bbox 중심에서 각 tip까지 점선을 긋는다
- 선택된 bbox: 강조 색상과 코너 핸들 표시
- 도구 번호: bbox 좌상단 안쪽에 1부터 표시

도구 번호는 Canvas 텍스트 항목의 기본 글꼴(`TkDefaultFont`)을 그대로 쓰면 수술 영상 위에서 너무 작아 잘 보이지 않는다. 그래서 기본 글꼴을 복제해 크기만 `ANNOTATION_LABEL_FONT_SCALE`(기본 2)배로 키운 글꼴을 쓴다.

Tk는 글꼴 크기를 음수로 주면 포인트가 아니라 픽셀로 해석하는데, 곱셈은 두 표기 모두에서 동일하게 동작하므로 `size * 2`로 충분하다(실측: `-12` → `-24`, 줄 높이 15 px → 28 px).

### 좌표계 처리

편집기 내부에는 두 좌표계가 있다.

- 이미지 좌표계
- Canvas 표시 좌표계

창 크기에 따라 이미지는 확대/축소되어 표시되므로, 마우스 이벤트는 `canvas -> image` 좌표 변환 후 처리한다.

### 편집 동작 설계

#### 방향키 바인딩

이미지 이동 단축키(`Up`/`Down`/`Left`/`Right`)는 최상위 윈도우에 바인딩되어 있다. 그런데 `Up`/`Down`만은 이미지 목록(`ttk.Treeview`)에도 따로 바인딩한다.

`Treeview` 클래스는 `Up`/`Down`에 선택을 한 칸 옮기는 동작을 바인딩한다. 이 클래스 바인딩이 선택을 옮기면서 `<<TreeviewSelect>>`를 발생시키고, 그 결과 `_on_image_selected()`가 이미지를 연다. 이어서 최상위 바인딩이 `_navigate_images()`를 호출하면 **한 칸 더** 이동한다. 즉 목록에 포커스가 있을 때 `Down` 한 번에 두 칸을 건너뛴다.

Tk의 바인딩 순서는 위젯 → 클래스 → 최상위 → `all`이고 `"break"`를 반환하면 남은 단계가 모두 취소된다. 따라서 목록 위젯 자체에 `Up`/`Down`을 바인딩하고 `"break"`를 반환하면 클래스 바인딩과 최상위 바인딩이 모두 건너뛰어져 한 칸만 이동한다.

`Left`/`Right`에는 이 처리가 필요 없다. `Treeview` 클래스 바인딩은 트리 항목을 접고 펴기만 하는데, 이 목록에는 하위 항목이 없어 아무 일도 일어나지 않는다.

`<<TreeviewSelect>>`는 큐에 들어가는 이벤트라, 코드에서 `selection_set()`으로 행을 고른 뒤에도 나중에 도착한다. 그래서 억제 플래그를 두지 않고, `current_index`를 먼저 갱신해 두었다가 핸들러에서 선택된 행이 이미 `current_index`이면 무시한다. 탭 전환의 `<<NotebookTabChanged>>`와 같은 방식이다.

탭 막대(`ttk.Notebook`)도 같은 이유로 방향키를 위젯에 직접 바인딩한다. 탭을 클릭하면 포커스가 탭 막대로 가는데, `Notebook` 클래스 바인딩은 `Left`/`Right`로 탭을 순환시킨다. 그러면 방향키 한 번에 탭과 이미지가 함께 바뀐다. 탭 막대 위젯에 네 방향키를 바인딩해 이미지 이동만 하고 `"break"`를 반환한다.

#### 탭 전환

탭 막대는 탭 모양만 쓴다. 각 탭에는 빈 `ttk.Frame`을 넣고, 실제 그림은 그 아래 하나뿐인 Canvas에 현재 탭의 annotation으로 그린다.

탭 클릭은 `<<NotebookTabChanged>>`, 숫자 키는 `_on_tab_shortcut()`을 거쳐 둘 다 `_request_tab()`으로 모인다. 여기서 활성 여부를 확인하고, 저장하지 않은 편집이 있으면 `_confirm_leave_current_image(always_ask=True)`로 묻는다. 거절되면 탭 막대 선택을 `current_tab`으로 되돌린다.

`<<NotebookTabChanged>>`는 큐에 들어가는 이벤트라 코드에서 `select()`를 호출한 뒤에도 나중에 도착한다. 그래서 별도의 억제 플래그를 두지 않고, 핸들러에서 선택된 탭이 이미 `current_tab`과 같으면 무시한다. `current_tab`은 항상 `select()`보다 먼저 갱신된다.

`_refresh_tab_states()`는 탭마다 `tab(state=...)`를 다시 정한 뒤 `current_tab`을 선택한다. 비활성 탭은 선택할 수 없으므로 순서가 중요하다.

`PageDown`/`PageUp`, `Home`/`End`는 최상위에 바인딩된 단축키가 없어 `Treeview` 클래스 바인딩이 단독으로 동작한다. 이 바인딩은 목록을 스크롤만 하고 선택은 바꾸지 않는다.

#### hit test 우선순위

`_hit_test()`는 세 단계를 차례로 본다. 한 annotation씩 돌면서 tip·코너·내부를 순서대로 보는 방식이 아니라, 종류별로 전체를 훑는다.

1. **tip 핸들**: 임계 거리 안에 있는 tip 중 가장 가까운 것. tip은 다른 박스 내부에 놓일 수 있으므로 박스에 가려지면 안 된다.
2. **코너 핸들**: 선택된 박스에만 존재한다.
3. **박스 내부**: 클릭 지점을 포함하는 박스 중 **면적이 가장 작은 것**.

3단계에서 면적을 기준으로 삼기 때문에, 큰 박스 안에 중첩된 작은 박스가 큰 박스에 가려지지 않는다. 면적이 같으면 현재 선택된 박스를 유지해 같은 자리를 반복 클릭할 때 선택이 번갈아 바뀌지 않게 한다.

tip 핸들 단계는 `TIP_KEYS = ("tip", "tip2")`의 두 tip을 모두 후보로 본다. hit 결과의 `handle`에 어느 tip인지가 담기고, 같은 값이 `drag_state["handle"]`과 hover 강조 `("tip", index, key)`에 그대로 쓰인다.

#### 이동

bbox 내부 hit 시 `move` 모드가 활성화된다. 드래그 중 bbox와 모든 tip(`drag_state["start_tips"]`)이 함께 이동한다.

#### 리사이즈

선택된 bbox의 모서리 hit 시 `resize` 모드가 활성화된다. 드래그 중 bbox가 갱신되고, 각 tip은 드래그 시작 시점의 위치를 새 bbox 안으로 clamp한 값이 된다. 그래서 박스를 줄여도 tip이 박스 밖에 남지 않고, 다시 키우면 원래 위치로 돌아간다.

#### tip 수정

tip 핸들 hit 시 `tip` 모드가 활성화된다. 드래그 중 잡은 tip의 좌표만 바뀌고, 그 tip이 박스 밖으로 나가면 박스가 드래그 시작 크기에서 늘어난다.

#### 추가

`Add Tool` 후 드래그하면 preview bbox를 그리고, mouse release 시 새 annotation을 생성한다. 새 annotation에는 두 번째 tip이 없다.

#### 오른쪽 클릭 메뉴

`<ButtonPress-3>`에 바인딩된 `_on_canvas_context_menu()`가 처리한다. 클릭 지점을 `_hit_test()`로 확인해 도구가 있으면 선택한 뒤, 선택 여부에 따라 `tk.Menu`를 새로 만들어 `tk_popup()`으로 띄운다. 메뉴를 매번 새로 만드는 것은 항목 구성과 활성 상태가 선택된 도구에 따라 달라지기 때문이다.

`Add Second Tip`은 메뉴를 띄운 지점의 이미지 좌표를 받아 `_add_second_tip()`에서 박스 안으로 clamp해 `tip2`를 만든다. `Remove Second Tip`은 `_remove_second_tip()`에서 `tip2`를 지운다. 두 동작 모두 `_mark_dirty()`를 호출하므로 일반 편집과 같은 저장 규칙을 따른다.

### 저장 정책

저장 시 현재 메모리 상태를 그대로 JSON으로 직렬화한다. 주기적인 자동 저장(일정 시간마다 저장)은 하지 않는다. `Auto Save`는 "이미지를 떠날 때 묻는 대신 저장"하는 것이며, 저장 시점은 `Auto Save`가 꺼져 있을 때 `Yes`를 누르는 시점과 동일하다.

구현은 `_confirm_leave_current_image()` 한 곳에 모여 있다. 이미지 이동, split 전환, 창 닫기가 모두 이 함수를 거치므로, 여기서 질문 대신 저장으로 분기하면 세 경로가 한꺼번에 처리된다. 탭 전환만 `always_ask=True`로 호출해 `Auto Save`를 건너뛰고 항상 묻는다.

`_save_current_annotation()`은 `dirty`와 현재 탭 종류로 분기한다.

- **편집함(`dirty`)**: 두 단계로 쓴다.
  1. `annotation-manual/{split}/{stem}.json`에 `source: "manual"` payload를 쓴다. annotation마다 `bbox`, `tip`, 그리고 있으면 `tip2`, `label`을 담는다. 이것이 원본이다.
  2. 그 파일을 `annotation/{split}/{stem}.json`으로 `shutil.copyfile()` 복사한다.

  원본을 먼저 쓰므로, 2단계에서 중단되더라도 보정 내용 자체는 `annotation-manual`에 남는다. 자동 annotation 탭에서 저장했다면 `current_tab`을 `MANUAL_TAB`으로 바꾼다.
- **편집 안 함 + 자동 annotation 탭**: 그 탭의 파일을 `annotation/{split}/{stem}.json`으로 `shutil.copyfile()` 복사한다. 파싱 후 다시 쓰지 않으므로 `source`, `model` 같은 메타데이터와 모든 필드가 그대로 보존된다.
- **편집 안 함 + `Default`/`Manual` 탭**: 아무것도 하지 않는다.

쓰기 대상 경로는 항상 `_tab_annotation_path(DEFAULT_TAB, ...)`(`annotation`)와 `_tab_annotation_path(MANUAL_TAB, ...)`(`annotation-manual`)뿐이다. 자동 annotation 루트는 읽기 경로로만 쓰인다.

`annotation`을 최종 레이블로 두는 이유는 어노테이션 소비자(학습·평가 코드, 베이스라인, 데이터셋 브라우저) 전체가 `annotation/{split}/*.json`을 직접 읽고 있기 때문이다. 읽는 쪽에서 여러 디렉터리를 합치게 하려면 여러 서브 프로젝트를 동시에 고쳐야 하므로, 쓰는 쪽(이 편집기)에서 확정해 두는 방식을 택했다.

### 현재 설계 제약

- undo/redo가 없다. 저장하지 않은 편집은 `Reload`나 탭 전환(저장하지 않음 선택)으로 버릴 수 있고, 저장한 프레임은 다른 탭의 결과를 다시 채택할 수 있다.
- `Auto Save` 설정은 실행 간에 기억되지 않는다. 실행 중에 끄더라도 다음 실행에서는 다시 켜진 상태로 시작한다. 항상 꺼진 상태로 쓰려면 `--no-auto-save`로 실행한다.
- 다각형 contour 편집은 지원하지 않는다.
- 겹친 박스 중 큰 쪽을 선택하려면 작은 박스에 덮이지 않은 영역을 클릭해야 한다. 같은 지점을 반복 클릭해 겹친 박스를 순환 선택하는 기능은 없다.
- tip만 자동으로 다시 계산하는 기능은 없다.
- 도구 이름(`label`)은 보존만 하고 화면에 표시하거나 편집하지 않는다.
- 탭 목록은 시작할 때와 데이터셋을 바꿀 때만 만든다. 실행 중에 새로 생긴 `annotation-*` 디렉터리는 반영되지 않는다.
- 숫자 키 단축키는 `1`~`9`까지다. 탭이 9개를 넘으면 10번째부터는 클릭으로만 고를 수 있다.
- `Default` 탭은 `annotation` 하나만 보여 준다. 그 프레임의 최종 레이블이 어느 탭과 같은지는 좌측 목록의 `Source` 칼럼으로 알 수 있다. 다만 어느 탭과도 같지 않은 레이블의 출처는 파일의 `source` 값으로만 알 수 있다.
- `Source` 값은 split을 열 때부터 다시 열 때까지 캐시된다. 편집기 밖에서 `annotation`이나 `annotation-*` 파일이 바뀌면 split을 다시 열어야 반영된다.
- 버튼 색상은 `ttk.Style`로 지정한다. ttk 버튼에는 `foreground` 옵션이 직접 없기 때문에 색마다 별도 스타일(`Add.TButton` 등)을 만들어 붙이고, `style.map()`으로 `disabled` 상태만 회색으로 되돌린다. 색 지정이 테마에 따라 무시될 수 있어, 현재 기본 테마(`default`) 밖에서는 보장되지 않는다.
- 도구 번호 글꼴 배율은 `ANNOTATION_LABEL_FONT_SCALE` 상수로 고정되어 있고, 실행 중에 바꿀 수는 없다. 박스가 글꼴보다 작으면 번호가 박스 밖으로 비어져 나올 수 있다.
- 일련번호는 정렬된 목록 안에서의 위치일 뿐이며, 프레임 번호나 파일 이름의 숫자와는 무관하다.
- 매우 큰 데이터셋에서는 좌측 이미지 목록 필터링 기능이 없다. 수동 보정된 프레임만 모아 보는 기능도 없다(`Manual` 색으로 구분만 된다).
- 수동 보정과 채택은 프레임 단위다. 한 프레임 안에서 도구마다 다른 출처의 결과를 고를 수 없다. 필요하면 한 탭에서 편집해 수동 보정본으로 저장한다.

### 확장 권장 사항

1. undo/redo 추가
2. 키보드 단축키 확장
3. annotation 목록 패널 추가
4. 상태 표시줄에 `Default` 탭 annotation의 `source` 표시
5. 이미지 이동 버튼과 검색 기능 추가
6. 변경 이력 또는 작업 로그 저장 기능 추가
7. 수동 보정된 프레임만 걸러 보는 목록 필터 추가
