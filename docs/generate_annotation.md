# `scripts/generate_annotation.py`

`scripts/generate_annotation.py`는 binary segmentation mask에서 도구(tool) 영역의 contour를 찾아, 각 영역의 bounding box와 tool tip 좌표를 계산하고 그 결과를 이미지별 annotation JSON 파일로 저장하는 스크립트다.

`--dataset <name>` 옵션을 주면 기본 입력은 `data/dataset/<name>/segmentation`, 기본 출력은 `data/dataset/<name>/annotation`이며, 입력과 출력 모두 `train`, `val`, `test` 세 분할 구조를 그대로 따른다.

사람이 `annotation_editor.py`로 보정한 레이블은 `data/dataset/<name>/annotation-manual`에 따로 보관되며, 이 스크립트는 그 디렉터리를 **읽기만 한다**. 보정본이 있는 프레임은 마스크를 다시 분석하지 않고 보정본을 그대로 출력에 복사하므로, `--overwrite`로 전체를 재생성해도 수동 작업이 사라지지 않는다.

## 사용자 문서

### 목적

segmentation 단계에서 생성된 binary mask로부터 학습용 레이블을 자동으로 만든다. mask 안의 각 도구 영역마다 다음 두 정보를 추출한다.

- `bbox`: 도구 영역을 감싸는 축 정렬(axis-aligned) bounding box
- `tip`: 도구의 끝점(tip)으로 추정되는 좌표

이 프로젝트의 기본 작업 순서에서 이 스크립트의 위치는 다음과 같다.

1. `scripts/generate_segmentation.py --dataset <name>`로 `data/dataset/<name>/segmentation` 준비
2. `scripts/generate_annotation.py --dataset <name>`로 bbox/tip annotation JSON 자동 생성
3. `scripts/annotation_editor.py --dataset <name>`로 생성된 annotation 수동 보정

즉, 이 스크립트의 출력은 완성된 정답이 아니라 **수동 보정의 출발점이 되는 초안 레이블**이다.

### 자동 생성본과 수동 보정본의 분리

이 스크립트가 다루는 디렉터리는 두 개이고, 역할이 다르다.

| 디렉터리            | 이 스크립트의 역할 | 내용                                                | 재생성 |
| ------------------- | ------------------ | --------------------------------------------------- | ------ |
| `annotation-manual` | 읽기 전용          | 사람이 보정한 프레임만                              | 불가   |
| `annotation`        | 쓰기 (생성물)      | 전체 프레임 = 자동 생성 결과에 수동 보정분을 덮어씀 | 가능   |

프레임 단위 우선순위는 단순하다.

1. `annotation-manual/{split}/{stem}.json`이 있으면 그 파일을 `annotation/{split}/{stem}.json`으로 복사한다. 마스크는 읽지 않는다.
2. 없으면 마스크에서 bbox/tip을 계산해 저장한다. (기존 동작)

이 때문에 다음이 성립한다.

- `--overwrite`로 전체를 재생성해도 수동 보정분은 유지된다.
- `annotation` 디렉터리를 통째로 삭제해도 보정 내용은 `annotation-manual`에서 복원된다.
- `annotation` 쪽 파일을 직접 편집하면 다음 실행 때 `annotation-manual`의 내용으로 되돌아간다. 수정은 반드시 `annotation_editor.py`로 해야 한다.

학습·평가 코드는 기존과 동일하게 `annotation` 하나만 읽는다. 어노테이션을 소비하는 쪽은 아무것도 바꿀 필요가 없다.

### 실행 전 요구 사항

- Python `3.12` 이상
- 프로젝트 의존성 설치
- `opencv-python` 설치
- `numpy` 설치
- `tqdm` 설치
- 입력 mask가 들어 있는 `segmentation` 디렉터리 (`train/val/test` 하위 폴더 포함)

`pyproject.toml` 기준 관련 의존성은 다음과 같다.

- `opencv-python`
- `numpy`
- `tqdm`

### 기본 실행 방법

프로젝트 루트에서 실행한다.

```bash
python -m scripts.generate_annotation --dataset erop
```

`uv`를 사용 중이면 다음처럼 실행할 수 있다.

```bash
uv run python -m scripts.generate_annotation --dataset erop
```

`--dataset`을 주면 아래 경로를 사용한다.

- 입력 디렉터리: `data/dataset/<dataset>/segmentation`
- 출력 디렉터리: `data/dataset/<dataset>/annotation`
- 수동 보정 디렉터리: `data/dataset/<dataset>/annotation-manual`
- 덮어쓰기: 비활성화 (기존 JSON은 건너뜀)

### CLI 옵션

- `--dataset`
  - 데이터셋 이름(예: `erop`, `cholec80`). `--input`/`--output`을 명시하지 않았을 때 기본 경로를 계산하는 데 쓰인다.
- `--input`
  - `train/val/test` segmentation mask가 들어 있는 루트 디렉터리. 기본값은 `data/dataset/<dataset>/segmentation`. 명시하면 `--dataset` 기본값보다 항상 우선한다.
- `--output`
  - `train/val/test` annotation JSON을 저장할 루트 디렉터리. 기본값은 `data/dataset/<dataset>/annotation`. 명시하면 `--dataset` 기본값보다 항상 우선한다.
- `--manual`
  - 수동 보정 JSON이 들어 있는 루트 디렉터리. 기본값은 `data/dataset/<dataset>/annotation-manual`. 이 스크립트는 여기에 쓰지 않는다. 디렉터리가 없으면 보정본이 하나도 없는 것으로 보고 조용히 넘어간다.
- `--overwrite`
  - 지정하면 기존 **자동 생성** JSON 파일을 건너뛰지 않고 다시 생성해 덮어쓴다. 지정하지 않으면 이미 존재하는 JSON은 건너뛴다. 어느 쪽이든 수동 보정분은 보존된다.

### 실행 예시

`--dataset`으로 기본 경로를 사용해 annotation을 생성하는 예시:

```bash
python -m scripts.generate_annotation --dataset cholec80
```

입력과 출력 경로를 직접 지정하는 예시(`--dataset` 기본값을 무시):

```bash
python -m scripts.generate_annotation --input ./data/dataset/erop/segmentation --output ./data/dataset_v2/annotation
```

자동 생성분만 모두 다시 생성하는 예시(수동 보정분은 유지):

```bash
python -m scripts.generate_annotation --dataset cholec80 --overwrite
```

수동 보정분을 무시하고 순수한 자동 생성 결과만 얻는 예시(디버깅 용도. `--manual`을 빈 디렉터리로 돌린다):

```bash
python -m scripts.generate_annotation --dataset cholec80 --overwrite \
  --manual ./temp/empty --output ./temp/annotation-auto-only
```

### 입력 대상 파일

각 split 디렉터리(`train/val/test`) 바로 아래에서 다음 확장자의 파일만 mask로 읽는다.

- `.png`
- `.jpg`
- `.jpeg`
- `.bmp`
- `.tif`
- `.tiff`

확장자 비교는 소문자 기준으로 수행하므로 대문자 확장자도 처리된다. 하위 디렉터리는 재귀 탐색하지 않는다.

입력 mask는 binary mask를 전제로 한다. 3채널 이미지가 들어오면 grayscale로 변환한 뒤, 픽셀값 `127`을 기준으로 이진화(threshold)한다. 따라서 `0`/`255`가 아닌 mask라도 `127`보다 큰 값이 전경(도구)으로 처리된다.

### 출력 구조

실행 시 출력 디렉터리 아래에 다음 하위 폴더가 생성된다.

```text
./data/dataset/<dataset>/
├── annotation/              # 이 스크립트가 쓴다
│   ├── train/
│   ├── val/
│   └── test/
└── annotation-manual/       # 이 스크립트는 읽기만 한다
    ├── train/
    ├── val/
    └── test/
```

annotation 파일명은 입력 mask의 확장자만 `.json`으로 바꾼 형태다.

```text
{mask파일이름}.json
```

예를 들어 입력이 `sample01_00000030.png`면 출력은 `sample01_00000030.json`이 된다.

### 출력 JSON 형식

각 JSON 파일은 한 이미지에 대한 annotation 전체를 담는다.

```json
{
  "image": "sample01_00000030.png",
  "width": 736,
  "height": 480,
  "source": "auto",
  "annotations": [
    {
      "bbox": {
        "x": 120,
        "y": 64,
        "width": 88,
        "height": 152
      },
      "tip": {
        "x": 150,
        "y": 200
      }
    }
  ]
}
```

필드 의미는 다음과 같다.

- `image`: 원본 mask 파일 이름 (확장자 포함)
- `width`, `height`: mask 이미지의 가로/세로 크기 (픽셀)
- `source`: 레이블의 출처. 이 스크립트가 계산한 파일은 `auto`, `annotation_editor.py`가 저장한 파일은 `manual`이다
- `edited_at`: `source`가 `manual`인 파일에만 있는 수정 시각 (ISO 8601, 로컬 타임존)
- `annotations`: mask에서 찾은 도구 영역 목록
  - `bbox.x`, `bbox.y`: bounding box의 좌상단 좌표
  - `bbox.width`, `bbox.height`: bounding box의 너비/높이
  - `tip.x`, `tip.y`: 추정된 도구 끝점 좌표

`source` 필드가 도입되기 전에 생성된 파일에는 이 키가 없으며, 그 경우는 `auto`로 간주한다. 학습·평가 코드는 `annotations`만 읽으므로 이 메타데이터 필드가 늘어도 영향을 받지 않는다.

좌표는 모두 정수로 저장되며, JSON은 `indent=2`와 `sort_keys=True`로 직렬화되어 키가 알파벳 순으로 정렬된다. 도구 영역이 하나도 없는 mask는 `annotations`가 빈 배열인 JSON으로 저장된다.

### 동작 방식

1. CLI 인자를 파싱한다.
2. OpenCV/numpy import 여부와 입력 경로의 유효성을 검사한다.
3. 출력 디렉터리 아래 `train`, `val`, `test` 폴더를 생성한다.
4. `--overwrite`가 아니고 모든 출력 JSON이 이미 존재하며 수동 보정분도 모두 반영된 상태면, 아무 작업도 하지 않고 `All annotation files already exist. Nothing to do.`를 출력한 뒤 종료한다.
5. split별로 mask 파일 목록을 정렬해 수집한다.
6. 해당 프레임의 수동 보정본이 있으면 그것을 출력으로 복사하고 다음 프레임으로 넘어간다.
7. 없으면 mask를 읽어 binary mask로 변환한다.
8. mask에서 외곽 contour를 찾고, contour마다 bounding box와 tip 좌표를 계산한다. 너무 작은 bbox는 노이즈로 보고 버린다(아래 "작은 박스 제외" 참고).
9. 결과를 JSON으로 직렬화해 split별 출력 폴더에 저장한다.
10. 모든 split 처리가 끝나면 split별 저장/건너뜀/수동 보정 개수를 출력한다.

### tip 좌표 추정 방식

tip(끝점)은 다음 절차로 정한다.

1. contour의 무게중심(centroid)을 구한다.
2. centroid에서 가장 먼 점 `A`를 찾는다.
3. 점 `A`에서 가장 먼 점 `B`를 찾는다. (`A`와 `B`는 도구 영역의 양 끝 극점이 된다)
4. `A`와 `B` 중 **이미지 중심에 더 가까운 점**을 tip으로 선택한다.

이는 수술 영상에서 도구가 보통 화면 가장자리에서 들어와 화면 중앙을 향하고, 도구의 끝(tip)이 화면 안쪽을 향한다는 가정을 반영한 것이다. 따라서 길쭉한 도구 영역에서는 자루 쪽이 아니라 안쪽 끝이 tip으로 잡히는 경향이 있다.

이 추정은 휴리스틱이므로 도구가 짧거나, 화면 중앙을 가로지르거나, mask가 부정확한 경우에는 실제 tip과 다를 수 있다. 이런 경우를 보정하기 위한 단계가 `annotation_editor.py`다.

### annotation 정렬

한 이미지에 여러 도구 영역이 있으면, `bbox`의 `(x, y, width, height)` 순서로 정렬되어 저장된다. 같은 mask를 다시 처리해도 annotation 순서가 일정하게 유지된다.

### 종료 및 출력

- 모든 출력이 이미 존재하고 `--overwrite`가 아니면 `All annotation files already exist. Nothing to do.`를 출력하고 종료 코드 `0`으로 끝난다.
- 정상 완료 시 `Annotation generation complete.`와 split별 개수를 출력하고 종료 코드 `0`을 반환한다. 개수는 네 가지다.
  - `saved`: mask에서 새로 계산해 저장한 자동 생성 파일 수
  - `skipped`: 이미 존재해 건너뛴 자동 생성 파일 수
  - `manual`: 수동 보정본이 있어 mask를 읽지 않은 프레임 수
  - `restored`: 그 중 출력이 보정본과 달라 다시 복사한 파일 수. 평소에는 `0`이고, `--overwrite`를 줬거나 출력이 지워졌거나 손으로 변경된 경우에만 늘어난다
- OpenCV/numpy import 실패, 잘못된 인자, 입력 경로 오류, split 폴더 누락, mask 읽기 실패 등은 예외로 중단된다.

### 문제 해결

#### `opencv-python is required` 에러가 나는 경우

OpenCV가 설치되지 않은 상태다. 프로젝트 의존성을 설치한 뒤 다시 실행하면 된다.

#### `numpy is required` 에러가 나는 경우

numpy가 설치되지 않은 상태다. 프로젝트 의존성을 설치한 뒤 다시 실행하면 된다.

#### `Input directory does not exist` 에러가 나는 경우

`--input` 경로가 실제로 존재하는지 확인해야 한다. `--dataset`만 썼다면 `data/dataset/<dataset>/segmentation`이 준비되어 있어야 한다.

#### `Either --dataset or --input must be provided.` 에러가 나는 경우

`--dataset`도 `--input`도 주지 않은 경우다. 둘 중 하나는 반드시 지정해야 한다. `--output`도 마찬가지다.

#### `Split directory does not exist` 에러가 나는 경우

입력 디렉터리 아래에 `train`, `val`, `test` 세 폴더가 모두 있어야 한다. segmentation 단계를 먼저 정상적으로 실행했는지 확인한다.

#### `Failed to read segmentation mask` 에러가 나는 경우

mask 파일이 손상되었거나 OpenCV가 읽을 수 없는 형식이다. 해당 파일을 확인하거나 segmentation을 다시 생성한다.

#### tip 위치가 부정확한 경우

tip 추정은 휴리스틱이므로 항상 정확하지 않다. `annotation_editor.py`로 수동 보정한다.

#### 이미 생성한 JSON이 갱신되지 않는 경우

기본 동작은 기존 JSON을 건너뛴다. 다시 생성하려면 `--overwrite`를 지정한다.

#### `--overwrite`를 줬는데도 특정 프레임이 갱신되지 않는 경우

그 프레임에 수동 보정본이 있는 경우다. `annotation-manual/{split}/{stem}.json`이 존재하면 mask를 다시 분석하지 않는다. 의도한 동작이며, 자동 생성 결과로 되돌리려면 `annotation_editor.py`에서 해당 프레임을 열고 `Revert to Auto`를 누른다.

#### `annotation`을 직접 고쳤는데 다음 실행에서 되돌아간 경우

수동 보정본이 있는 프레임의 출력은 매 실행마다 `annotation-manual`의 내용으로 맞춰진다(`restored` 개수로 보고된다). `annotation`은 생성물이므로 직접 편집하지 말고 `annotation_editor.py`를 사용한다.

## 개발 문서

### 파일 구조

스크립트는 다음 함수들로 구성된다.

bbox/tip 계산과 payload 생성은 공용 모듈 `tooltip/annotation.py`에 있고, 스크립트는 파일 탐색과 skip/overwrite/override 정책만 담당한다. `annotation_editor.py`의 "자동으로 되돌리기" 기능이 같은 계산 코드를 써야 하므로 모듈로 분리되어 있다.

`tooltip/annotation.py`:

- `load_binary_mask(mask_path)`
  - mask를 읽어 grayscale 변환 후 `127` 기준으로 이진화한다.
- `contour_centroid(points)`
  - contour의 무게중심을 계산한다. moment가 0이면 좌표 평균으로 대체한다.
- `farthest_point(reference, points)`
  - 기준점에서 가장 먼 점을 반환한다.
- `compute_tip(points, image_center)`
  - 양 끝 극점을 구하고 이미지 중심에 가까운 점을 tip으로 선택한다.
- `is_too_small_box(width, height)`
  - 노이즈로 보고 버릴 bbox 크기인지 판정한다.
- `extract_annotations(mask)`
  - contour별 bbox/tip을 만들고 너무 작은 bbox를 버린 뒤, 정렬된 annotation 리스트로 반환한다.
- `build_payload(image_name, width, height, annotations, source)`
  - 메타와 annotation 리스트를 합쳐 payload를 만든다. `source`가 `manual`이면 `edited_at`을 덧붙인다.
- `build_auto_payload(mask_path, mask)`
  - mask에서 annotation을 추출해 `source="auto"` payload를 만든다.
- `write_annotation(output_path, payload)`
  - payload를 JSON으로 직렬화해 저장한다.
- `annotation_source(payload)`
  - payload의 출처를 반환한다. `source` 키가 없는 구버전 파일은 `auto`로 본다.

`scripts/generate_annotation.py`:

- `parse_args()`
  - CLI 인자(`--dataset`, `--input`, `--output`, `--manual`, `--overwrite`)를 정의하고 파싱한다.
- `validate_args(args)`
  - OpenCV/numpy 의존성, 입력 루트, split 디렉터리 존재 여부를 검증한다. `--manual`은 존재할 경우에만 디렉터리인지 확인한다. `--dataset` 기반 기본 경로 해석은 `main()`에서 이 함수 호출 전에 끝난다.
- `ensure_output_dirs(output_root)`
  - 출력 루트 아래 `train`, `val`, `test` 디렉터리를 생성한다.
- `_needs_materialize(manual_path, output_path)`
  - 출력이 수동 보정본과 다른지(또는 없는지) 크기 비교 후 바이트 비교로 판정한다.
- `_all_outputs_up_to_date(input_root, output_root, manual_root)`
  - 모든 출력 JSON이 존재하고 수동 보정분도 모두 반영된 상태인지 검사한다.
- `list_images(image_dir)`
  - 디렉터리에서 지원 확장자의 파일을 정렬해 반환한다.
- `process_split(...)`
  - 한 split을 처리하고 `saved`/`skipped`/`manual`/`restored` 개수를 반환한다.
- `main()`
  - `tooltip.dataset_paths.resolve_path()`로 `--input`/`--output`/`--manual`을 확정한 뒤 전체 파이프라인을 조합하고 종료 코드 `0`을 반환한다.

### 핵심 구현 세부 사항

#### 0. `--dataset` 경로 해석

`main()`은 `parse_args()` 직후 다음을 수행한다.

```python
args.input = resolve_path(args.input, args.dataset, segmentation_dir, "--input")
args.output = resolve_path(args.output, args.dataset, annotation_dir, "--output")
```

`resolve_path()`(`tooltip/dataset_paths.py`)는 명시적으로 준 경로가 있으면 그대로 쓰고, 없으면 `--dataset` 이름으로 기본 경로를 계산한다. 둘 다 없으면 어떤 플래그가 필요한지 알려주는 `ValueError`를 즉시 던진다.

#### 1. 의존성 지연 import

`cv2`와 `numpy`는 모듈 상단에서 `try/except`로 import하고, 실패하면 import 에러 객체를 보관한다. 실제 검증은 `validate_args()`에서 수행해, 의존성이 없을 때 traceback 대신 사람이 읽기 쉬운 `RuntimeError` 메시지를 제공한다.

```python
try:
    import cv2
except ImportError as exc:
    cv2 = None
    CV2_IMPORT_ERROR = exc
else:
    CV2_IMPORT_ERROR = None
```

#### 2. binary mask 로딩

mask는 `cv2.IMREAD_UNCHANGED`로 읽는다. 3채널이면 `BGR2GRAY`로 변환하고, 이후 `cv2.threshold(mask, 127, 255, THRESH_BINARY)`로 이진화한다.

이 덕분에 입력이 엄밀한 `0/255` mask가 아니어도, soft mask나 다채널 mask를 일관된 binary mask로 정규화할 수 있다.

#### 3. contour 추출 방식

contour는 `cv2.findContours(mask, RETR_EXTERNAL, CHAIN_APPROX_NONE)`로 찾는다.

- `RETR_EXTERNAL`: 가장 바깥 contour만 추출하므로, 도구 내부의 구멍은 별도 영역으로 잡지 않는다.
- `CHAIN_APPROX_NONE`: contour의 모든 경계 점을 보존한다. 극점(tip 후보) 탐색이 점 집합 기반이라 점을 압축하지 않는다.

**작은 박스 제외**: contour의 bbox가 다음 중 하나에 해당하면 annotation에서 제외한다. 이렇게 작은 영역은 실제 도구가 아닌 마스크 노이즈인 경우가 대부분이었다.

- 폭과 높이가 **모두** `SMALL_BOX_MIN_SIZE`(16px)보다 작다.
- 폭 **또는** 높이가 `THIN_BOX_MIN_SIZE`(10px)보다 작다.

필터는 `tooltip/annotation.py`의 `extract_annotations()` 안에 있으므로, annotation editor에서 프레임을 자동 결과로 되돌릴 때도 같은 기준이 적용된다. 이미 만들어 둔 JSON에는 소급 적용되지 않으므로 `--overwrite`로 다시 생성해야 한다. 수동 보정본은 그대로 유지된다.

#### 4. tip 계산 로직

`compute_tip()`은 다음을 수행한다.

```python
center = contour_centroid(points)
point_a = farthest_point(center, points)
point_b = farthest_point(point_a, points)
# image_center에 더 가까운 점을 tip으로 선택
return point_a if distance_a <= distance_b else point_b
```

`A`(centroid에서 최원점)와 `B`(A에서 최원점)는 길쭉한 영역의 양 끝 극점을 근사한다. 두 점의 거리 비교는 모두 **제곱 거리**(`sqrt` 생략)로 처리해 불필요한 연산을 줄인다. 동률(`distance_a == distance_b`)이면 `A`를 선택한다.

`contour_centroid()`는 `cv2.moments`의 `m00`이 0인 퇴화 contour(예: 선분)에서는 좌표 평균으로 대체해 0 나눗셈을 피한다.

#### 5. annotation 정렬과 결정성

`extract_annotations()`는 각 contour의 `(x, y, width, height)`를 키로 정렬한 뒤 annotation만 추출한다. 따라서 같은 입력에 대해 출력 순서가 항상 동일하다.

JSON 직렬화도 `sort_keys=True`라서 키 순서까지 결정적이다. 이로 인해 git diff나 재현성 측면에서 안정적이다.

#### 6. skip / overwrite / override 정책

프레임 단위 판정 순서는 다음과 같다.

1. **수동 보정본 우선**: `annotation-manual/{split}/{stem}.json`이 있으면 `--overwrite` 여부와 무관하게 그 파일을 출력으로 복사하고 종료한다. 이미 같은 내용이면 복사도 생략한다.
2. **skip**: 출력 JSON이 존재하고 `--overwrite`가 아니면 건너뛴다.
3. **생성**: 그 외에는 mask에서 계산해 저장한다.

여기에 더해 전역 단축 경로가 있다. `main()`은 `--overwrite`가 아닐 때 `_all_outputs_up_to_date()`로 "모든 출력이 존재하고 수동 보정분도 모두 반영됨"을 확인하면 즉시 종료한다. 수동 보정본이 새로 생겼거나 바뀐 경우에는 이 검사가 실패하므로, `--overwrite` 없이 그냥 재실행하는 것만으로 보정분이 출력에 반영된다.

수동 보정본 조회는 split 디렉터리가 존재할 때만 수행하므로, 보정을 한 번도 하지 않은 데이터셋에서는 추가 비용이 사실상 없다.

#### 7. 복사 기반 반영(materialize)

수동 보정본은 파싱 후 재직렬화하지 않고 `shutil.copyfile()`로 바이트 단위 복사한다. 덕분에 출력 파일과 보정본이 항상 바이트 단위로 동일해지고, `_needs_materialize()`의 동일성 판정이 단순한 바이트 비교로 끝난다.

### 예외와 종료 방식

`main()`은 예외를 별도로 잡지 않는다. 따라서 다음 문제는 traceback과 함께 즉시 종료된다.

- OpenCV/numpy import 실패
- 잘못된 인자 값
- 입력 루트 또는 split 디렉터리 누락
- mask 읽기 실패 (`load_binary_mask`의 `RuntimeError`)

반면 "모든 출력이 이미 존재"하는 경우와 "도구 영역이 없는 mask"는 예외가 아니라 정상 상황으로 취급한다(각각 조기 종료, 빈 `annotations`).

### 현재 설계 제약

- 입력 split 디렉터리의 하위 폴더를 재귀 탐색하지 않는다.
- tip 추정이 "양 끝 극점 중 이미지 중심에 가까운 점" 휴리스틱에 의존하므로 항상 정확하지 않다.
- 작은 박스 제외 기준(16px / 10px)이 코드 상수로 고정되어 있어 CLI로 바꿀 수 없다. 기준보다 큰 노이즈 영역은 여전히 annotation으로 들어올 수 있다.
- `RETR_EXTERNAL`만 사용하므로 겹치거나 중첩된 도구를 분리하지 못할 수 있다.
- 출력 좌표가 정수로 고정되어 있어 서브픽셀 정밀도는 유지되지 않는다.
- 로그 출력이 `print()`와 `tqdm`에 묶여 있어 구조화된 로그에는 적합하지 않다.
- 수동 보정본은 프레임 단위로만 적용된다. 한 프레임 안의 도구 하나만 보정하고 나머지는 자동 생성 결과를 따라가게 할 수는 없다.
- `annotation`과 `annotation-manual`에 보정 내용이 중복 저장된다. `annotation`은 언제든 재생성 가능한 생성물이라는 전제로 감수한 비용이다.

### 확장 권장 사항

1. 작은 박스 제외 기준을 CLI 옵션으로 노출하기
2. tip 추정 알고리즘을 교체 가능하게 분리(예: skeleton 기반, 곡률 기반)
3. 다중/중첩 도구 분리를 위해 contour 검색 모드나 후처리 추가
4. 클래스/라벨 정보를 annotation에 포함할 수 있도록 스키마 확장
5. split 이름을 옵션화해 `train/val/test` 외 구성도 지원
6. 예외를 정리해 사용자 친화적인 에러 메시지와 종료 코드 제공

### 다른 코드에서 재사용할 때

핵심 분석 함수들은 파일 시스템과 분리되어 있어 numpy mask 배열만 있으면 단독으로 사용할 수 있다.

```python
from pathlib import Path
from tooltip.annotation import extract_annotations, load_binary_mask

mask = load_binary_mask(Path("./data/dataset/erop/segmentation/train/sample01_00000030.png"))
annotations = extract_annotations(mask)
```

`extract_annotations()`는 binary mask(numpy 배열)를 받아 annotation 리스트를 반환하므로, 파이프라인 외부에서도 bbox/tip 계산 로직만 따로 재사용하기 좋다. 이 함수들은 `scripts/generate_annotation.py`가 아니라 공용 모듈 `tooltip/annotation.py`에 있다.
