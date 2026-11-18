# tooltip-annotator

수술 영상에서 프레임 데이터를 만들고, semantic segmentation과 tip annotation을 생성 및 수정하는 도구 모음이다.

현재 파이프라인은 다음 단계로 구성된다.

1. 원본 비디오를 progressive 형태로 변환
2. 비디오 프레임을 이미지 데이터셋으로 추출
3. MONAI segmentation 모델 다운로드
4. 이미지별 binary segmentation mask 생성
5. 자동 annotation 생성 (segmentation mask 기반 MONAI, VLM 기반 Qwen 등. 도구별 디렉터리에 저장)
6. GUI 편집기로 자동 annotation을 비교·채택·보정해 최종 annotation 확정 (수정본은 별도 디렉터리에 보존)

## 요구 사항

- Python `3.12` 이상
- 프로젝트 의존성 설치
- `ffmpeg`
- GUI 편집기를 사용할 경우 `tkinter`
- GPU 추론을 사용할 경우 CUDA가 동작하는 PyTorch 환경

의존성 설치 예시:

```bash
uv sync
```

또는 가상환경에서 직접 설치 후 사용한다.

## 데이터 구조

여러 출처의 데이터셋을 비교 평가할 수 있도록 원본과 파이프라인 산출물을 분리한다.

```text
./data/
├── dataset-src/            # 읽기 전용 원본 데이터셋 소스 (심볼릭 링크 등)
│   ├── erop/                 # 예: 이롭 내시경 수술 동영상
│   └── cholec80/             # 예: cholec80 공개 데이터셋 동영상
└── dataset/                # 파이프라인이 생성하는 내부 데이터셋
    ├── erop/
    │   ├── progressive/        # (선택) 디인터레이스/재인코딩된 동영상
    │   ├── images/
    │   │   ├── train/
    │   │   ├── val/
    │   │   └── test/
    │   ├── segmentation/
    │   │   ├── train/
    │   │   ├── val/
    │   │   └── test/
    │   ├── annotation/          # 학습·평가에 쓰는 최종 레이블 (annotation-editor가 관리)
    │   │   ├── train/
    │   │   ├── val/
    │   │   └── test/
    │   ├── annotation-manual/   # 사람이 보정한 레이블의 원본 (재생성 불가, 별도 git 저장소)
    │   │   ├── train/
    │   │   ├── val/
    │   │   └── test/
    │   ├── annotation-monai/    # generate-annotation-monai 결과 (mask 기반 자동 annotation)
    │   │   └── ...
    │   ├── annotation-qwen/     # generate-annotation-qwen 결과 (VLM 기반 자동 annotation)
    │   │   └── ...
    │   └── screenshot/          # (선택) annotation-editor 스크린샷
    └── cholec80/
        └── ... (동일 구조)
```

각 스크립트는 `--dataset <name>` 옵션을 받아 위 컨벤션에 따른 기본 입출력 경로를 자동 계산한다. 예를 들어 `--dataset cholec80`을 주면 입력/출력 경로가 `data/dataset-src/cholec80`, `data/dataset/cholec80/images` 등으로 자동 결정된다. `--input`/`--output`(또는 GUI 편집기의 `--images`/`--annotation`/`--manual`)을 직접 지정하면 그 값이 `--dataset` 기본값보다 항상 우선한다.

annotation 디렉터리들의 관계는 다음과 같다.

| 디렉터리                 | 쓰는 주체                       | 내용                                                      | 재생성 |
| ------------------------ | ------------------------------- | --------------------------------------------------------- | ------ |
| `annotation`             | `annotation-editor`             | 학습·평가에 쓰는 최종 레이블. 채택한 자동 결과 또는 수동 보정본 | 불가   |
| `annotation-manual`      | `annotation-editor`             | 사람이 보정한 프레임만                                     | 불가   |
| `annotation-monai`       | `generate-annotation-monai`     | segmentation mask에서 계산한 순수 자동 결과                 | 가능   |
| `annotation-qwen`        | `generate-annotation-qwen`      | VLM(Qwen3-VL)이 지정한 순수 자동 결과                       | 가능   |
| `annotation-qwen2.5`     | `generate-annotation-qwen25`    | 이전 VLM(Qwen2.5-VL) 결과. 비교용                          | 가능   |

자동 annotation 스크립트는 각자 자기 `annotation-<이름>` 디렉터리에만 쓰고, `annotation`과 `annotation-manual`은 건드리지 않는다. `annotation-editor`는 반대로 자동 annotation 디렉터리를 읽기만 하고, 사람이 고르거나 고친 결과를 `annotation`(과 `annotation-manual`)에 쓴다. 따라서 자동 annotation을 다시 실행해도 **최종 레이블과 수동 보정분은 바뀌지 않는다**. 새 자동 annotation 도구는 `annotation-<이름>` 디렉터리에 결과를 쓰기만 하면 편집기에 탭으로 나타난다.

`annotation-manual`은 이 파이프라인에서 유일하게 스크립트로 다시 만들 수 없는 산출물이다. 그래서 **데이터셋별로 독립된 git 저장소**로 분리해 관리한다. 이 저장소의 `.gitignore`는 `data/` 전체를 제외하므로 두 저장소는 경로만 겹칠 뿐 서로를 참조하지 않는다(서브모듈이 아니다).

| 데이터셋   | 수작업 레이블 저장소                                        |
| ---------- | ----------------------------------------------------------- |
| `cholec80` | https://github.com/doosik71/cholec80-annotation-manual.git   |

```bash
git clone https://github.com/doosik71/cholec80-annotation-manual.git \
  data/dataset/cholec80/annotation-manual
```

관리 방법 상세: [docs/annotation_manual.md](./docs/annotation_manual.md)

학습·평가 코드와 베이스라인들은 기존과 동일하게 `annotation` 하나만 읽으면 된다.

`data/dataset-src`는 읽기 전용 외부 원본이므로 스크립트가 그 안에 쓰지 않는다. `generate-progressive.py`의 출력(디인터레이스/재인코딩된 동영상)은 `data/dataset-src/<name>/progressive`가 아니라 `data/dataset/<name>/progressive`에 저장된다. `generate-dataset.py`는 `--dataset`만 주어졌을 때 `data/dataset/<name>/progressive`가 존재하고 비어있지 않으면 그것을, 없으면 `data/dataset-src/<name>`(원본)을 입력으로 사용한다. 즉 원본 자체가 이미 progressive 형식이라 디인터레이스가 필요 없는 데이터셋은 1단계를 건너뛰어도 된다.

모델 파일 기본 위치는 다음과 같다(데이터셋과 무관한 공용 자원).

```text
./temp/models/model.pt
```

## 패키지 구조

- `scripts/`: 사용자가 직접 실행하는 진입점 스크립트.
- `tooltip/`: 스크립트들이 공유하는 임포트 전용 모듈(`tooltip/dataset_paths.py`의 데이터셋 경로 계산 등). 직접 실행하지 않는다.

## 작업 순서

이하 예시는 `cholec80` 데이터셋 기준이며, `--dataset erop`처럼 이름만 바꾸면 다른 데이터셋에도 동일하게 적용된다.

### 1. 비디오를 progressive로 변환

```bash
python scripts/generate-progressive.py --dataset cholec80
```

기본 입력은 `./data/dataset-src/cholec80`, 기본 출력은 `./data/dataset/cholec80/progressive`이다.

문서: [docs/generate_progressive.md](./docs/generate_progressive.md)

### 2. 데이터셋 이미지 생성

```bash
python scripts/generate-dataset.py --dataset cholec80
```

기본 출력은 `./data/dataset/cholec80/images/{train,val,test}`이다.

문서: [docs/generate_dataset.md](./docs/generate_dataset.md)

### 3. segmentation 모델 다운로드

```bash
python scripts/download-model.py
```

문서: [docs/download_model.md](./docs/download_model.md)

### 4. GPU 환경 점검

GPU를 사용할 예정이면 먼저 환경 점검을 권장한다.

```bash
python -m scripts.check-cuda --device cuda:0
```

이 스크립트는 다음을 확인한다.

- PyTorch CUDA 인식 상태
- cuDNN 버전 정합성
- `nvidia-smi`, `nvcc`
- `libtorch_cuda.so`가 실제로 물고 있는 CUDA/cuDNN 라이브러리
- 최소 CUDA Conv2D smoke test
- cuDNN enabled/disabled 비교

### 5. segmentation mask 생성

```bash
python -m scripts.generate-segmentation --dataset cholec80
```

기본 입력은 `./data/dataset/cholec80/images/{train,val,test}`이고, 기본 출력은 `./data/dataset/cholec80/segmentation/{train,val,test}`이다.

주요 옵션 예시:

```bash
python -m scripts.generate-segmentation --dataset cholec80 --device cuda:0
python -m scripts.generate-segmentation --dataset cholec80 --device cpu
python -m scripts.generate-segmentation --dataset cholec80 --overwrite
```

문서: [docs/generate_segmentation.md](./docs/generate_segmentation.md)

### 6. annotation JSON 자동 생성

자동 annotation 도구는 여러 개이며, 각자 자기 디렉터리에 결과를 쓴다. 필요한 것만 실행하면 된다.

MONAI(segmentation mask 기반):

```bash
python -m scripts.generate-annotation-monai --dataset cholec80
```

segmentation mask에서 contour를 찾고, 각 contour의 bounding box와 tool tip 좌표를 계산해 JSON으로 저장한다. 기본 출력은 `./data/dataset/cholec80/annotation-monai/{train,val,test}`이다. 마스크를 다시 생성한 뒤 결과를 갱신하려면 `--overwrite`를 준다.

```bash
python -m scripts.generate-annotation-monai --dataset cholec80 --overwrite
```

문서: [docs/generate_annotation_monai.md](./docs/generate_annotation_monai.md)

Qwen(VLM 기반):

```bash
uv run python -m scripts.generate-annotation-qwen --dataset cholec80
```

기본 출력은 `./data/dataset/cholec80/annotation-qwen/{train,val,test}`이다.

문서: [docs/generate_annotation_qwen.md](./docs/generate_annotation_qwen.md)

### 7. GUI 편집기로 annotation 수정

```bash
python -m scripts.annotation-editor --dataset cholec80
```

`--dataset`을 생략하면 발견된 첫 번째 데이터셋이 자동으로 선택되므로, 인자 없이 `python -m scripts.annotation-editor`로 실행해도 된다.

편집기에서 가능한 작업:

- `Dataset` 드롭다운으로 데이터셋 전환
- split 전환
- 이미지 선택
- 영상 위 탭(`Default`, `Manual`, `Monai`, `Qwen` 등)으로 annotation 출처 전환. 숫자 키 `1`부터 순서대로 선택. `Default`는 최종 레이블(`annotation`)이고, 나머지는 그 프레임에 결과가 있을 때만 활성화
- bbox 이동 (겹친 경우 가장 작은 박스가 선택된다)
- bbox 리사이즈
- tip 드래그 수정
- 마우스 오른쪽 버튼 메뉴로 도구 삭제(`Delete Tool`), 두 번째 tip 추가·삭제(`Add Second Tip`/`Remove Second Tip`), 선택된 도구가 없을 때는 도구 추가(`Add Tool`)
- `Add Tool[INS/Wheel]`로 annotation 추가 (이미지 위에서 마우스 휠 버튼 클릭으로도 가능하며, 추가 중에 휠 버튼이나 `Adding...` 버튼을 다시 누르면 `Esc`처럼 취소)
- 방향키 또는 이미지 위에서 마우스 휠 스크롤로 이전/다음 영상 이동 (휠 위: 이전, 휠 아래: 다음)
- `Delete Tool[DEL]`로 annotation 삭제
- `Save[F2]` 또는 `Ctrl+S`로 저장. 편집했으면 수동 보정본으로 저장하고, `Monai`/`Qwen` 탭에서 편집 없이 누르면 그 결과를 최종 레이블로 채택
- `Reload[F3]`로 `annotation`에서 다시 읽기
- `Auto Save`(기본 켜짐)는 다른 이미지로 이동할 때 묻지 않고 자동 저장. 끄려면 체크박스를 해제하거나 `--no-auto-save`로 실행
- `Screenshot[F5]`로 현재 이미지를 화면에 표시 중인 overlay와 함께 `data/dataset/<dataset>/screenshot/`에 저장 (발표 자료용)

편집해 저장하면 `annotation-manual/{split}/`에 원본이 기록되고 같은 내용이 `annotation/{split}/`에도 반영된다. 자동 annotation을 채택하면 `annotation/{split}/`에만 그 파일의 사본이 생긴다. 편집기는 `annotation-monai`, `annotation-qwen` 같은 자동 annotation 디렉터리에는 쓰지 않는다. 좌측 이미지 목록에서 수동 보정된 프레임은 **노란색 배경**으로 강조되고 파일명 앞에 `*` 표시가 붙는다.

보정 결과는 데이터셋별 독립 저장소에 커밋한다. 바깥 저장소는 건드릴 필요가 없다.

```bash
cd data/dataset/cholec80/annotation-manual
git add -A && git commit -m "Correct 20 frames in train" && git push
```

문서: [docs/annotation_editor.md](./docs/annotation_editor.md), [docs/annotation_manual.md](./docs/annotation_manual.md)

![Screen](./screen.png)

## scripts 요약

- `scripts/download-model.py`
  - Hugging Face Hub에서 MONAI segmentation 모델 다운로드
- `scripts/generate-progressive.py`
  - 원본 비디오를 ffmpeg로 디인터레이스 및 재인코딩
- `scripts/generate-dataset.py`
  - 비디오 프레임 추출 후 `train/val/test` 분할 이미지 생성
- `scripts/check-cuda.py`
  - PyTorch CUDA/cuDNN 런타임 점검 및 문제 분석
- `scripts/generate-segmentation.py`
  - 모델을 이용해 이미지별 binary segmentation mask 생성
- `scripts/generate-annotation-monai.py`
  - segmentation mask로부터 bbox/tip annotation JSON을 계산해 `annotation-monai`에 저장
- `scripts/generate-annotation-qwen.py`
  - 로컬 VLM(Qwen3-VL-8B)이 이미지를 직접 보고 bbox/tip을 지정해 `annotation-qwen`에 저장 (`source: "qwen"`, 벌어진 jaw 등은 선택 필드 `tip2`로 두 번째 tip 기록, 모델은 `data/models`)
- `scripts/generate-annotation-opus.py`
  - Anthropic API로 Claude Opus에 프레임을 보내 bbox/tip을 지정해 `annotation-opus`에 저장 (`source: "opus"`, `tip2` 지원, 실시간/Batch API 모드)
- `scripts/generate-annotation-qwen25.py`
  - Qwen2.5-VL을 쓰던 이전 버전. 비교·재현용으로 남겨 두었으며 `annotation-qwen2.5`에 저장
- `scripts/annotation-editor.py`
  - 최종 annotation을 확정하는 GUI 편집기. `annotation`, `annotation-manual`, 자동 annotation(`annotation-*`)을 탭으로 비교하고, 채택하거나 보정한 결과를 `annotation`에 쓴다. 보정 결과는 `annotation-manual`에도 보존한다
- `scripts/count-dataset.py`
  - 데이터셋별 `train/val/test` 프레임 수와 비율, split별 manual/자동 레이블 수와 비율을 콘솔에 출력 (`run count-dataset [--dataset <name>]`)
- `scripts/pipeline.py`
  - 전체 파이프라인 단계를 실행하고 진행 상태를 보여주는 통합 GUI. 상단 `Dataset` 드롭다운으로 `data/dataset-src`/`data/dataset` 아래 발견된 데이터셋을 전환하며 실행/상태를 확인할 수 있다.
- `tooltip/dataset_paths.py`
  - `--dataset` 옵션의 기본 경로 계산과 데이터셋 목록 조회를 담당하는 공용 모듈(직접 실행하지 않음)
- `tooltip/annotation.py`
  - mask에서 bbox/tip을 계산하고 annotation JSON payload를 만드는 공용 모듈. `generate-annotation-monai.py`가 사용하고, `annotation-editor.py`는 payload 생성과 저장 함수를 공유한다(직접 실행하지 않음)

## 문서 목록

- [docs/commands.md](./docs/commands.md)
- [docs/download_model.md](./docs/download_model.md)
- [docs/generate_progressive.md](./docs/generate_progressive.md)
- [docs/generate_dataset.md](./docs/generate_dataset.md)
- [docs/generate_segmentation.md](./docs/generate_segmentation.md)
- [docs/generate_annotation_monai.md](./docs/generate_annotation_monai.md)
- [docs/generate_annotation_qwen.md](./docs/generate_annotation_qwen.md)
- [docs/generate_annotation_opus.md](./docs/generate_annotation_opus.md)
- [docs/annotation_editor.md](./docs/annotation_editor.md)
- [docs/annotation_manual.md](./docs/annotation_manual.md)
- [docs/pipeline.md](./docs/pipeline.md)
