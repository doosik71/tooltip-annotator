# `scripts/annotation_editor.py`

`scripts/annotation_editor.py`는 `images`, `segmentation`, `annotation` 데이터를 함께 보여 주고, 수술도구의 bounding box와 tip 좌표를 수동으로 수정할 수 있는 GUI 편집기다.

`--dataset <name>` 옵션을 주면 아래 경로가 자동으로 계산된다.

- 이미지 입력: `data/dataset/<name>/images/{train,val,test}`
- segmentation 입력: `data/dataset/<name>/segmentation/{train,val,test}`
- annotation 입출력: `data/dataset/<name>/annotation/{train,val,test}`
- 수동 보정본 출력: `data/dataset/<name>/annotation-manual/{train,val,test}`

## 사용자 문서

### 목적

자동 생성된 annotation JSON을 사람이 검토하고 수정하기 위한 도구다. segmentation에서 누락된 수술도구를 추가하거나, 잘못 생성된 annotation을 삭제하거나, bbox와 tip 위치를 미세 조정할 수 있다.

### 수동 보정본의 보존

이 편집기가 저장한 내용은 `annotation`뿐 아니라 **`annotation-manual`에도 원본으로 기록된다**.

- `annotation-manual`: 이 편집기만 쓴다. 사람이 보정한 프레임만 들어 있고, 어떤 스크립트도 다시 만들어낼 수 없다.
- `annotation`: `generate_annotation.py`가 만드는 생성물이다. 자동 생성 결과에 수동 보정분을 덮어쓴 전체 레이블이며, 학습·평가 코드가 읽는 대상이다.

`generate_annotation.py`는 `annotation-manual`에 파일이 있는 프레임을 건너뛰고 그 파일을 그대로 `annotation`에 복사한다. 따라서 **annotation을 다시 생성해도 이 편집기로 한 작업은 사라지지 않는다**. `annotation` 디렉터리를 통째로 지워도 보정 내용은 복원된다.

보정을 취소하고 자동 생성 결과로 돌아가려면 `Revert to Auto`를 사용한다(아래 참고). `annotation` 쪽 JSON을 직접 편집하는 것은 다음 생성 때 되돌아가므로 의미가 없다.

### 실행 전 요구 사항

- Python `3.12` 이상
- `opencv-python`
- `numpy`
- `tkinter` 사용 가능 환경
- `data/dataset/<dataset>/images` 디렉터리 존재
- `data/dataset/<dataset>/segmentation` 디렉터리 존재

`tkinter`는 일반적인 데스크톱 Python 환경에 기본 포함되는 경우가 많지만, 일부 최소 설치 환경에서는 별도 패키지가 필요할 수 있다.

### 실행 방법

프로젝트 루트에서 실행한다.

```bash
python -m scripts.annotation_editor --dataset erop
```

가상환경을 직접 사용할 경우:

```bash
.venv/bin/python -m scripts.annotation_editor --dataset erop
```

경로를 직접 지정할 수도 있다(`--dataset` 기본값을 무시).

```bash
python -m scripts.annotation_editor \
  --images ./data/dataset/erop/images \
  --segmentation ./data/dataset/erop/segmentation \
  --annotation ./data/dataset/erop/annotation \
  --manual ./data/dataset/erop/annotation-manual
```

### CLI 옵션

- `--dataset`
  - 데이터셋 이름(예: `erop`, `cholec80`). `--images`/`--segmentation`/`--annotation`/`--manual`을 명시하지 않았을 때 기본 경로를 계산하는 데 쓰인다.
- `--images`
  - 원본 RGB 이미지 루트. 기본값은 `data/dataset/<dataset>/images`. 명시하면 `--dataset` 기본값보다 항상 우선한다.
- `--segmentation`
  - binary mask 루트. 기본값은 `data/dataset/<dataset>/segmentation`. 명시하면 `--dataset` 기본값보다 항상 우선한다.
- `--annotation`
  - JSON 저장 루트. 기본값은 `data/dataset/<dataset>/annotation`. 명시하면 `--dataset` 기본값보다 항상 우선한다.
- `--manual`
  - 수동 보정본 저장 루트. 기본값은 `data/dataset/<dataset>/annotation-manual`. 명시하면 `--dataset` 기본값보다 항상 우선한다.
- `--auto-save` / `--no-auto-save`
  - `Auto Save`의 시작 상태를 정한다. 기본값은 켜짐(`--auto-save`)이고, `--no-auto-save`를 주면 매번 저장 여부를 묻는 동작으로 시작한다. 어느 쪽이든 실행 중에 툴바 체크박스로 바꿀 수 있다.

`--dataset`과 네 경로 옵션을 모두 생략하면 `data/dataset-src`와 `data/dataset` 아래에서 찾은 **첫 번째 데이터셋**이 자동으로 선택된다. 따라서 아래처럼 인자 없이 실행할 수 있다.

```bash
python -m scripts.annotation_editor
```

찾은 데이터셋이 하나도 없으면 어떤 옵션이 필요한지 알려주는 메시지와 함께 종료한다.

`--dataset`과 네 경로 옵션을 모두 주지 않으면 어떤 플래그가 필요한지 알려주는 에러로 즉시 실패한다.

### 화면 구성

#### 상단 툴바

왼쪽부터 다음 순서로 놓인다.

- `Dataset`
  - 편집할 데이터셋을 선택한다. 목록은 `data/dataset-src`와 `data/dataset` 아래에서 찾은 이름이다. 바꾸면 images·segmentation·annotation·annotation-manual 네 경로가 모두 해당 데이터셋 기준으로 다시 계산되고 현재 split이 다시 로드된다. `--images` 등 경로 옵션을 직접 지정해 실행한 경우에는 비활성화된다.
- `Split`
  - `train`, `val`, `test` 중 하나를 선택한다.
- `Add Tool[INS]`
  - 새 수술도구 annotation 추가 모드로 들어간다. 단축키 `Insert`.
- `Delete Tool[DEL]`
  - 현재 선택된 annotation을 삭제한다. 단축키 `Delete`.
- `Save[F2]`
  - 현재 이미지의 annotation JSON을 저장한다. 단축키 `F2` 또는 `Ctrl+S`.
- `Reload[F3]`
  - 저장하지 않은 변경을 버리고 파일에서 다시 읽는다. 단축키 `F3`.
- `Revert to Auto[F4]`
  - 현재 프레임의 수동 보정본을 삭제하고 segmentation mask에서 자동 생성 결과를 다시 계산한다. 단축키 `F4`. 자동 생성 상태인 프레임에서는 비활성화된다.
- `Screenshot[F5]`
  - 현재 이미지를 overlay와 함께 `data/dataset/<dataset>/screenshot/<이미지 파일 이름>`으로 저장한다. 단축키 `F5`이다.
  - segmentation/annotation overlay는 `Show Segmentation`/`Show Annotation` 체크 상태를 그대로 따른다.
  - 화면 캡처가 아니라 원본 해상도로 다시 그린다. 선택 강조색, 리사이즈 핸들, 추가 모드 미리보기 박스 같은 편집용 표시는 넣지 않으며, 모든 박스는 비선택 색(`#3bd7ff`)으로 그린다. tip 연결선은 점선이 아닌 실선이다.
  - 저장하지 않은 편집도 화면에 보이는 그대로 반영된다. 같은 이름의 파일이 있으면 덮어쓴다.
  - `--images` 등 경로 옵션만으로 실행해 데이터셋 이름이 없으면 `--images` 디렉터리 옆의 `screenshot/`에 저장한다.
- `Auto Save`
  - 켜 두면 다른 이미지나 split으로 이동하거나 창을 닫을 때 저장 여부를 묻지 않고 바로 저장한다. **기본값은 켜짐**이며, `--no-auto-save`로 끈 상태로 시작할 수 있다.
- `Show Segmentation`
  - segmentation overlay 표시 여부를 전환한다.

#### 버튼 색상

버튼은 하는 일의 성격에 따라 글자색이 다르다.

| 버튼                  | 글자색             |
| --------------------- | ------------------ |
| `Add Tool [INS]`      | 파랑 `#1565c0`     |
| `Delete Tool [DEL]`   | 빨강 `#c62828`     |
| `Save [F2]`           | 주황 `#e65100`     |
| `Reload [F3]`         | 보라 `#6a1b9a`     |
| `Revert to Auto [F4]` | 초록 `#2e7d32`     |
| `Screenshot [F5]`     | 청록 `#00838f`     |

비활성 상태에서는 모두 회색 `#9e9e9e`로 바뀌어, 색이 있는 버튼이라도 지금 누를 수 없다는 것이 드러난다.

`Add Tool`은 추가 모드에 들어가면 라벨이 `Adding... (Esc/Wheel to cancel)`로 바뀌면서 배경이 노란색 `#ffe680`이 된다. 이 상태에서 버튼을 다시 누르면 `Esc`처럼 추가 모드가 취소된다.

#### 단축키 정리

| 단축키             | 동작                            |
| ------------------ | ------------------------------- |
| `Insert`           | 수술도구 추가 모드              |
| `Delete`           | 선택된 annotation 삭제          |
| `F2` 또는 `Ctrl+S` | 저장                            |
| `F3`               | 파일에서 다시 읽기              |
| `F4`               | 자동 생성 결과로 되돌리기       |
| `F5`               | overlay 포함 스크린샷 저장      |
| `Esc`              | 추가 모드 취소                  |
| 방향키             | 이전/다음 이미지                |

낱자 키(`a`, `d`, `s`, `r`, `v`)는 바인딩하지 않는다. 입력 포커스가 어디에 있든 최상위 창이 받기 때문에, 무심코 누른 `d` 하나로 annotation이 삭제되는 사고를 막기 위해서다.

#### 좌측 패널

선택된 split 안의 이미지 목록을 표시한다. 목록에서 이미지를 클릭하면 우측 메인 화면에 해당 이미지가 로드된다.

각 행은 `[일련번호] 파일이름` 형식으로 표시된다. 일련번호는 1부터 시작하고, 자리수는 그 split의 전체 프레임 수에 맞춰 자동으로 정해진다.

```text
  [000001] doctor_250620_084707_00000000.png     # 108,424 프레임 → 6자리
* [00001] video01_00000000.png                   # 71,032 프레임 → 5자리
  [1] frame_0000.png                             # 3 프레임 → 1자리
```

split이나 데이터셋을 바꾸면 자리수도 다시 계산된다.

수동 보정본이 있는 프레임은 **노란색 배경**으로 강조되고, 파일명 앞에 `*` 표시가 붙는다. 선택된 상태에서도 구분이 유지되도록 선택 색은 호박색으로 따로 지정된다.

스크롤바 왼쪽의 얇은 표시 막대는 VS Code의 overview ruler처럼 목록 전체에서 프레임 위치를 보여 준다. 막대 높이가 목록 전체에 대응하며, 수동 보정 프레임은 호박색(`#e8a33d`) 눈금, 현재 프레임은 파란색(`#1565c0`) 눈금으로 표시된다. 지금 목록에 보이는 행의 범위는 반투명한 어두운 상자로 겹쳐 그린다. 그리는 순서는 수동 보정 눈금, 보이는 범위 상자, 현재 프레임 눈금이다. 그래서 상자 안의 보정 눈금은 어둡게 비쳐 보이고, 현재 프레임 눈금은 항상 맨 위에 보인다. 표시 전용이라 클릭해도 반응하지 않는다.

- 같은 픽셀 높이에 놓이는 눈금은 하나로 합쳐 그리므로, 7만 장 규모 split에서도 그리는 양은 막대 높이를 넘지 않는다.
- 수동 보정 프레임의 위치는 split을 열 때 한 번 계산하고, 저장이나 `Revert to Auto` 때 현재 프레임만 갱신한다.
- 막대는 위아래에 스크롤바 화살표 버튼 높이만큼 여백을 두어, 스크롤바의 스크롤 영역과 같은 높이로 맞춘다. 화살표 높이는 테마마다 다르므로 고정값을 쓰지 않고, 스크롤바 크기가 바뀔 때마다 `identify()`로 측정한다. 다만 스크롤바 막대(thumb)에는 최소 크기가 있어서, 큰 split에서는 눈금과 thumb의 위치가 여전히 1~3픽셀 어긋날 수 있다. 보이는 범위 상자는 눈금과 같은 비율로 그리므로, 상자 안에 들어온 눈금이 곧 지금 목록에 보이는 행이다. 스크롤바를 드래그할 때는 thumb 대신 상자를 보고 원하는 눈금에 맞추면 된다.
- 큰 split에서는 화면에 보이는 행이 막대 높이로 1픽셀도 되지 않으므로, 상자는 최소 높이(`LIST_MARKER_VISIBLE_MIN_HEIGHT = 8`)로 그린다. 이때 상자는 실제 범위의 중심에 놓인다.
- Tk 캔버스는 반투명 채우기를 지원하지 않는다. 그래서 상자 아래에 있는 색(막대 배경과 보정 눈금)에 검정을 30% 섞은 색(`LIST_MARKER_VISIBLE_COLOR`, `LIST_MARKER_VISIBLE_ALPHA`)을 미리 계산해 칠하는 방식으로 반투명을 흉내 낸다. 플랫폼마다 동작이 다른 `stipple` 무늬는 쓰지 않았다.

| 프레임 상태        | 배경색                       |
| ------------------ | ---------------------------- |
| 자동 생성          | 기본값 (흰색)                |
| 수동 보정          | 연한 노랑 `#ffe9a8`          |
| 수동 보정 + 선택됨 | 호박색 `#e8a33d`             |

색상은 `scripts/annotation_editor.py` 상단의 `MANUAL_ITEM_*` 상수로 정의되어 있다.

#### 상태 표시줄

창 하단 오른쪽에 현재 상태가 표시된다. 왼쪽에는 마우스 조작 안내가 함께 놓인다.

```text
tools=2 | mode=select
```

`tools`는 현재 프레임의 annotation 개수, `mode`는 `select` 또는 `add`이다. 저장·되돌리기·스크린샷 같은 동작을 하면 그 결과 메시지가 대신 표시되었다가, 다음 상태 변화 때 위 형식으로 돌아온다.

#### 우측 메인 화면

다음 요소가 함께 표시된다.

- 원본 이미지
- segmentation mask 반투명 overlay
- annotation bbox
- annotation tip

### 편집 방법

#### bbox 이동

bbox 내부를 마우스로 드래그하면 전체 박스를 이동할 수 있다. tip도 함께 같은 만큼 이동한다.

#### 박스가 겹쳐 있는 경우

클릭 지점에 여러 박스가 겹쳐 있으면 **가장 작은 박스**가 선택된다. 큰 박스 안에 들어 있는 작은 박스도 그대로 클릭해서 선택할 수 있다.

큰 박스를 선택하려면 작은 박스에 덮이지 않은 부분을 클릭한다. 크기가 같은 박스끼리 겹친 경우에는 현재 선택이 유지된다.

#### bbox 크기 조정

선택된 bbox의 네 모서리 핸들을 드래그하면 박스 크기를 조정할 수 있다.

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
2. `Delete Tool` 버튼 클릭 또는 `Delete` 키 입력

도구가 하나도 없는 상태로 저장해도 된다. 빈 `annotations` 배열이 수동 보정본으로 기록되므로, "이 프레임에는 도구가 없다"는 판단이 다음 자동 생성에서 유지된다.

#### 자동 생성 결과로 되돌리기

1. 되돌릴 프레임을 연다 (목록에서 노란색으로 강조된 프레임)
2. `Revert to Auto` 버튼 클릭 또는 `V` 키 입력
3. 확인 대화상자에서 `Yes` 선택

`annotation-manual`의 해당 파일이 삭제되고, segmentation mask에서 bbox/tip이 다시 계산되어 `annotation`에 저장된다. 계산에는 `generate_annotation.py`와 동일한 코드(`tooltip/annotation.py`)를 쓰므로 결과도 동일하다.

segmentation mask가 없는 프레임에서는 자동 생성 결과를 만들 수 없으므로 경고만 표시하고 아무것도 바꾸지 않는다.

### 저장 동작

annotation 정보가 바뀌면 `Save` 버튼이 활성화된다.

다음 두 방법으로 저장할 수 있다.

- `Save` 버튼 클릭
- `Ctrl+S`

이미지나 split을 바꾸거나 창을 닫을 때 저장되지 않은 변경이 있으면 저장 여부를 묻는다.

#### 자동 저장

`Auto Save`를 켜면 이 질문이 사라지고, 같은 상황에서 묻지 않고 바로 저장한다. 프레임을 연속으로 훑으며 보정할 때 화살표 키만으로 작업을 이어갈 수 있다.

- 기본값은 켜짐이다. 매번 저장 여부를 확인받고 싶으면 체크박스를 끄거나 `--no-auto-save`로 실행한다.
- 저장되지 않은 변경이 있는 상태에서 `Auto Save`를 켜면 그 변경이 즉시 저장된다.
- 창을 닫을 때도 묻지 않고 저장한다.

잘못 저장한 프레임은 `Revert to Auto`로 자동 생성 결과로 되돌릴 수 있다.

### 저장 파일 형식

각 이미지에 대해 같은 basename의 JSON 파일을 **두 곳에** 저장한다. 두 파일의 내용은 바이트 단위로 동일하다.

예시:

```text
이미지:             ./data/dataset/erop/images/train/sample01_00000030.png
수동 보정본(원본):  ./data/dataset/erop/annotation-manual/train/sample01_00000030.json
annotation(생성물): ./data/dataset/erop/annotation/train/sample01_00000030.json
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
      }
    }
  ]
}
```

`source`는 이 편집기가 저장한 파일에서 항상 `manual`이고, `edited_at`은 저장 시각(ISO 8601, 로컬 타임존)이다. `Revert to Auto`로 되돌린 프레임은 `annotation`에만 `source: "auto"` 파일이 남고 `edited_at`은 붙지 않는다.

### 문제 해결

#### 창이 열리지 않는 경우

GUI 환경이 없는 터미널 세션일 수 있다. 로컬 데스크톱 세션이나 X11/Wayland가 활성화된 환경에서 실행해야 한다.

#### 이미지가 보이는데 segmentation이 안 보이는 경우

다음 항목을 확인하면 된다.

- 같은 basename의 segmentation PNG가 존재하는지 확인
- 경로가 `data/dataset/<dataset>/segmentation/{split}`인지 확인
- `Show Segmentation` 체크가 켜져 있는지 확인

#### annotation 파일이 없는데 편집은 가능한가

가능하다. 기존 JSON이 없으면 빈 annotation 상태로 열리고, 저장 시 새 JSON 파일이 생성된다.

#### 보정한 내용이 `generate_annotation.py` 재실행으로 사라지지 않는가

사라지지 않는다. 저장된 내용은 `annotation-manual`에 원본으로 남고, `generate_annotation.py`는 그 디렉터리를 읽기만 하면서 해당 프레임의 자동 생성을 건너뛴다. `--overwrite`를 줘도 마찬가지다.

#### `Revert to Auto` 버튼이 비활성화된 경우

현재 프레임에 수동 보정본이 없는 경우다. 이미 자동 생성 상태이므로 되돌릴 것이 없다. 목록에서 노란색으로 강조된 프레임에서만 활성화된다.

## 개발 문서

### 입력/출력 경로 모델

편집기는 데이터셋 이름 하나와 네 개의 루트 디렉터리를 사용한다.

- `--images`
  - 원본 RGB 이미지 루트
- `--segmentation`
  - binary mask 루트
- `--annotation`
  - 전체 레이블(생성물) 루트. 저장 시 수동 보정본의 사본이 여기에 반영된다
- `--manual`
  - 수동 보정본(원본) 루트. 이 편집기만 쓴다

각 루트 아래에는 모두 `train`, `val`, `test` 디렉터리가 있다고 가정한다.

`main()`은 `parse_args()` 직후 네 경로 모두 `tooltip.dataset_paths.resolve_path()`로 확정한다. `--dataset`만 주면 각각 `data/dataset/<dataset>/{images,segmentation,annotation,annotation-manual}`로 기본값이 계산되고, 경로 옵션을 직접 주면 그 값이 항상 우선한다.

`--dataset`과 경로 옵션을 모두 생략하면 `list_datasets()[0]`을 기본값으로 쓴다.

`Dataset` 콤보로 데이터셋을 바꾸면 `_switch_dataset()`이 네 루트를 전부 데이터셋 이름 기준으로 다시 계산한다. 이는 직접 지정한 경로를 조용히 버리는 셈이 되므로, 경로 옵션이 하나라도 주어졌으면 `main()`이 `args.dataset_locked`를 세워 콤보를 비활성화한다.

`_switch_dataset()`은 선택한 데이터셋의 images 디렉터리가 실제로 있을 때만 출력 디렉터리를 만든다. `data/dataset-src`에만 있고 아직 프레임을 추출하지 않은 데이터셋을 골랐을 때 빈 디렉터리를 만들지 않기 위해서다.

### 내부 상태

`AnnotationEditor` 클래스는 현재 이미지와 편집 상태를 메모리에 유지한다.

주요 상태는 다음과 같다.

- `current_image_rgb`
  - 현재 원본 이미지
- `current_segmentation_mask`
  - 현재 segmentation mask
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
  - 현재 선택된 데이터셋 이름. `Dataset` 콤보를 바꾸면 `_switch_dataset()`이 네 루트를 모두 다시 계산한다
- `dataset_locked`
  - 경로 옵션을 직접 지정해 실행했는지 여부. 참이면 `Dataset` 콤보를 비활성화한다
- `current_source`
  - 현재 프레임의 출처(`auto` / `manual`). `Revert to Auto` 버튼의 활성 여부에 쓰인다
- `manual_stems`
  - 현재 split에서 수동 보정본이 있는 파일 스템 집합. split을 열 때 `annotation-manual/{split}`를 한 번만 훑어서 만들고, 이후 저장/되돌리기 때 증분 갱신한다. 10만 장 규모 split에서도 프레임마다 파일 존재 여부를 확인하지 않기 위한 것이다

### 표시 방식

원본 이미지는 `Canvas`에 표시되고, segmentation은 OpenCV로 반투명 합성한 뒤 렌더링된다.

annotation overlay는 Canvas 도형으로 따로 그린다.

- bbox: 사각형
- tip: 빨간 원형 핸들
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

이미지 이동 단축키(`Up`/`Down`/`Left`/`Right`)는 최상위 윈도우에 바인딩되어 있다. 그런데 `Up`/`Down`만은 이미지 목록(`tk.Listbox`)에도 따로 바인딩한다.

Tk의 `Listbox` 클래스는 가상 이벤트 `<<PrevLine>>`/`<<NextLine>>`을 바인딩하고, Tk는 이를 각각 `<Key-Up>`/`<Key-Down>`에 매핑한다. 이 클래스 바인딩이 선택을 한 칸 옮기면서 `<<ListboxSelect>>`를 발생시키고, 그 결과 `_on_image_selected()`가 이미지를 연다. 이어서 최상위 바인딩이 `_navigate_images()`를 호출하면 **한 칸 더** 이동한다. 즉 목록에 포커스가 있을 때 `Down` 한 번에 두 칸을 건너뛴다.

Tk의 바인딩 순서는 위젯 → 클래스 → 최상위 → `all`이고 `"break"`를 반환하면 남은 단계가 모두 취소된다. 따라서 목록 위젯 자체에 `Up`/`Down`을 바인딩하고 `"break"`를 반환하면 클래스 바인딩과 최상위 바인딩이 모두 건너뛰어져 한 칸만 이동한다.

`Left`/`Right`에는 이 처리가 필요 없다. 대응하는 클래스 바인딩 `<<PrevChar>>`/`<<NextChar>>`는 가로 스크롤(`xview`)만 하고 선택을 바꾸지 않는다.

`Ctrl+N`/`Ctrl+P`와 `PageDown`/`PageUp`은 최상위에 바인딩된 단축키가 없으므로 `Listbox` 클래스 바인딩이 단독으로 동작하고, `<<ListboxSelect>>` 경로를 거쳐 정상적으로 한 번만 이동한다.

#### hit test 우선순위

`_hit_test()`는 세 단계를 차례로 본다. 한 annotation씩 돌면서 tip·코너·내부를 순서대로 보는 방식이 아니라, 종류별로 전체를 훑는다.

1. **tip 핸들**: 임계 거리 안에 있는 tip 중 가장 가까운 것. tip은 다른 박스 내부에 놓일 수 있으므로 박스에 가려지면 안 된다.
2. **코너 핸들**: 선택된 박스에만 존재한다.
3. **박스 내부**: 클릭 지점을 포함하는 박스 중 **면적이 가장 작은 것**.

3단계에서 면적을 기준으로 삼기 때문에, 큰 박스 안에 중첩된 작은 박스가 큰 박스에 가려지지 않는다. 면적이 같으면 현재 선택된 박스를 유지해 같은 자리를 반복 클릭할 때 선택이 번갈아 바뀌지 않게 한다.

#### 이동

bbox 내부 hit 시 `move` 모드가 활성화된다. 드래그 중 bbox와 tip이 함께 이동한다.

#### 리사이즈

선택된 bbox의 모서리 hit 시 `resize` 모드가 활성화된다. 드래그 중 bbox만 갱신되고, tip은 화면 경계 안으로 clamp된다.

#### tip 수정

tip 핸들 hit 시 `tip` 모드가 활성화된다. 드래그 중 tip 좌표만 바뀐다.

#### 추가

`Add Tool` 후 드래그하면 preview bbox를 그리고, mouse release 시 새 annotation을 생성한다.

### 저장 정책

저장 시 현재 메모리 상태를 그대로 JSON으로 직렬화한다. 주기적인 자동 저장(일정 시간마다 저장)은 하지 않는다. `Auto Save`는 "이미지를 떠날 때 묻는 대신 저장"하는 것이며, 저장 시점은 `Auto Save`가 꺼져 있을 때 `Yes`를 누르는 시점과 동일하다.

구현은 `_confirm_leave_current_image()` 한 곳에 모여 있다. 이미지 이동, split 전환, 창 닫기가 모두 이 함수를 거치므로, 여기서 질문 대신 저장으로 분기하면 세 경로가 한꺼번에 처리된다.

쓰기는 두 단계다.

1. `annotation-manual/{split}/{stem}.json`에 `source: "manual"` payload를 쓴다. 이것이 원본이다.
2. 그 파일을 `annotation/{split}/{stem}.json`으로 `shutil.copyfile()` 복사한다.

순서가 중요하다. 원본을 먼저 쓰므로, 2단계에서 중단되더라도 보정 내용 자체는 유실되지 않고 다음 `generate_annotation.py` 실행 때 `annotation`에 반영된다.

`annotation`에 사본을 두는 이유는 어노테이션 소비자(학습·평가 코드, 베이스라인, 데이터셋 브라우저) 전체가 `annotation/{split}/*.json`을 직접 읽고 있기 때문이다. 읽는 쪽에서 두 디렉터리를 합치게 하려면 여러 서브 프로젝트를 동시에 고쳐야 하므로, 쓰는 쪽에서 합쳐 두는 방식을 택했다.

### 되돌리기 정책

`Revert to Auto`는 `annotation-manual`의 파일을 지우고, 메모리에 이미 올라와 있는 segmentation mask로 `tooltip.annotation.extract_annotations()`를 다시 호출해 `annotation`에 `source: "auto"` payload를 쓴다. `generate_annotation.py`가 쓰는 것과 같은 함수이므로 두 경로의 결과가 어긋날 수 없다.

### 현재 설계 제약

- undo/redo가 없다. 다만 마지막으로 저장한 상태를 버리고 자동 생성 결과로 되돌리는 `Revert to Auto`는 있다.
- `Auto Save` 설정은 실행 간에 기억되지 않는다. 실행 중에 끄더라도 다음 실행에서는 다시 켜진 상태로 시작한다. 항상 꺼진 상태로 쓰려면 `--no-auto-save`로 실행한다.
- 다각형 contour 편집은 지원하지 않는다.
- 겹친 박스 중 큰 쪽을 선택하려면 작은 박스에 덮이지 않은 영역을 클릭해야 한다. 같은 지점을 반복 클릭해 겹친 박스를 순환 선택하는 기능은 없다.
- tip만 자동으로 다시 계산하는 기능은 없다. `Revert to Auto`는 bbox와 tip을 함께 되돌린다.
- segmentation overlay 색상과 알파 값은 코드 상수로 고정되어 있다.
- 버튼 색상은 `ttk.Style`로 지정한다. ttk 버튼에는 `foreground` 옵션이 직접 없기 때문에 색마다 별도 스타일(`Add.TButton` 등)을 만들어 붙이고, `style.map()`으로 `disabled` 상태만 회색으로 되돌린다. 색 지정이 테마에 따라 무시될 수 있어, 현재 기본 테마(`default`) 밖에서는 보장되지 않는다.
- 도구 번호 글꼴 배율은 `ANNOTATION_LABEL_FONT_SCALE` 상수로 고정되어 있고, 실행 중에 바꿀 수는 없다. 박스가 글꼴보다 작으면 번호가 박스 밖으로 비어져 나올 수 있다.
- 일련번호는 정렬된 목록 안에서의 위치일 뿐이며, 프레임 번호나 파일 이름의 숫자와는 무관하다.
- 매우 큰 데이터셋에서는 좌측 이미지 목록 필터링 기능이 없다. 수동 보정된 프레임만 모아 보는 기능도 없다(색상과 `*` 표시로 구분만 된다).
- `tk.Listbox`는 항목별 글꼴 옵션을 지원하지 않으므로(`itemconfig`에 `-font`가 없다) 수동 보정 프레임을 굵은 글씨로 표시할 수 없다. 굵게 표시하려면 목록 위젯을 `ttk.Treeview`로 교체해야 한다.
- 수동 보정은 프레임 단위다. 한 프레임 안의 도구 하나만 보정하고 나머지는 자동 생성 결과를 따르게 할 수 없다.

### 확장 권장 사항

1. undo/redo 추가
2. 키보드 단축키 확장
3. annotation 목록 패널 추가
4. tip 자동 snap 또는 contour 기반 재계산 기능 추가
5. 이미지 이동 버튼과 검색 기능 추가
6. 변경 이력 또는 작업 로그 저장 기능 추가
7. 수동 보정된 프레임만 걸러 보는 목록 필터 추가
