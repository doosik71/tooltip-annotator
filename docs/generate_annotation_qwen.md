# `scripts/generate-annotation-qwen.py`

`scripts/generate-annotation-qwen.py`는 로컬 vision-language model(VLM)이 데이터셋 이미지를 직접 보고 수술도구의 bounding box와 tip 좌표를 지정하도록 해서, Claude가 영상을 보고 레이블을 다는 방식을 로컬에서 재현하는 스크립트다. 외부 API는 호출하지 않는다.

segmentation mask에서 tip을 기하학적으로 계산하는 `generate-annotation-monai.py`와 달리, 이 스크립트는 mask를 쓰지 않고 모델이 원본 이미지에서 도구 종류, box, tip을 한꺼번에 답한다.

## 모델

- 기본 모델: `Qwen/Qwen3-VL-8B-Instruct` (가중치 약 17.5GB, bf16 기준 24GB 이상 GPU 권장)
- 저장 위치: `data/models/Qwen3-VL-8B-Instruct`
- 해당 디렉터리에 `config.json`이 없으면 첫 실행 때 Hugging Face Hub에서 내려받는다. 이후에는 로컬 파일만 사용한다.
- 다른 크기를 쓰려면 `--model-id Qwen/Qwen3-VL-4B-Instruct`처럼 지정한다. 저장 위치는 `data/models/<모델 이름>`이 된다. 스크립트는 Qwen3-VL 계열(dense 모델)만 지원한다. 32B 모델은 GPU 1장(48GB)에 올라가지 않는다.
- Qwen2.5-VL에서 바꾼 이유: cholec80 수동 보정 프레임 120장에서 비교했을 때, 프레임당 도구를 1개만 찾던 Qwen2.5-VL-7B(이전 프롬프트)보다 도구 검출이 크게 나아졌다. 반면 tip 정확도는 오히려 떨어졌다.

  | 항목 | Qwen2.5-VL-7B (이전 프롬프트) | Qwen3-VL-8B |
  | --- | --- | --- |
  | 프레임당 평균 도구 수 (정답 1.82) | 1.00 | 1.50 |
  | 도구 수가 정답과 같은 프레임 | 32% | 65% |
  | 정답 도구 검출률 (IoU ≥ 0.5) | 45% | 73% |
  | 검출 정밀도 | 82% | 88% |
  | tip 오차 중앙값 (검출된 도구) | 38px | 54px |

### Qwen2.5-VL 버전 (`generate-annotation-qwen25.py`)

비교와 재현을 위해 Qwen2.5-VL을 쓰던 이전 버전을 `scripts/generate-annotation-qwen25.py`로 남겨 두었다. 옵션과 처리 방식은 이전 그대로이고 출력 위치만 다르다.

- 기본 모델: `Qwen/Qwen2.5-VL-7B-Instruct` (`data/models/Qwen2.5-VL-7B-Instruct`)
- 출력: `data/dataset/<dataset>/annotation-qwen2.5`, `--save-raw` 출력: `data/dataset/<dataset>/annotation-qwen2.5-raw`
- 이미지를 28px 배수로 리사이즈하고, 모델이 답한 픽셀 좌표를 원본 크기로 다시 스케일한다.
- 프롬프트에 구체적인 예시 값이 그대로 남아 있다. 모델이 이 값을 베껴 답하는 문제가 있으므로 새 레이블 생성에는 권하지 않는다.

```bash
uv run python -m scripts.generate-annotation-qwen25 --dataset cholec80 --device cuda:1
```

## 실행 전 요구 사항

- 프로젝트 의존성 설치: `uv sync` (`transformers>=4.57`, `accelerate` 추가됨)
- CUDA가 동작하는 PyTorch 환경 (CPU에서도 돌지만 실사용이 어려울 만큼 느리다)
- 입력 이미지 디렉터리 `data/dataset/<name>/images/{train,val,test}`

## 실행 예시

```bash
# 먼저 split당 몇 장만 돌려 결과를 확인
uv run python -m scripts.generate-annotation-qwen --dataset cholec80 --splits val --limit 20

# 전체 실행 (기존 JSON은 건너뛰므로 중단 후 다시 실행하면 이어서 진행)
uv run python -m scripts.generate-annotation-qwen --dataset cholec80 --device cuda:1
```

## CLI 옵션

- `--dataset`: 데이터셋 이름. `--input`/`--output` 기본값 계산에 쓰인다.
- `--input`: `train/val/test` 이미지 루트. 기본값 `data/dataset/<dataset>/images`.
- `--output`: annotation JSON 루트. 기본값 `data/dataset/<dataset>/annotation-qwen`.
- `--model-id`: Hugging Face 모델 저장소(Qwen3-VL 계열). 기본값 `Qwen/Qwen3-VL-8B-Instruct`.
- `--model-dir`: 로컬 모델 디렉터리. 기본값 `data/models/<모델 이름>`.
- `--splits`: 처리할 split 목록. 기본값 `train val test`.
- `--limit`: split마다 최대 처리 장수(시험 실행용).
- `--device`: torch 디바이스. 기본값은 CUDA가 있으면 `cuda:0`.
- `--batch-size`: 한 번에 생성하는 이미지 수. 기본값 `8`. VRAM이 부족하면 줄인다.
- `--max-new-tokens`: 이미지당 생성 길이 한도. 기본값 `512`.
- `--attn`: attention 구현(`sdpa`, `flash_attention_2`, `eager`). 기본값 `sdpa`.
- `--overwrite`: 이미 있는 JSON도 다시 생성한다.
- `--save-raw`: 처리한 이미지마다 모델 원문 답변을 따로 저장한다(디버깅용). 파싱에 실패한 프레임도 저장된다.
- `--raw-output`: `--save-raw` 저장 위치. 기본값 `data/dataset/<dataset>/annotation-qwen-raw`.

## 처리 방식

1. 이미지를 원본 크기 그대로 모델에 넣는다. Qwen3-VL은 이미지 크기와 상관없이 좌표를 가로·세로 모두 0~1000으로 정규화해 답한다(픽셀 좌표를 요청해도 마찬가지다). 그래서 답한 좌표에 `원본 크기 / 1000`을 곱해 원본 좌표로 되돌린다.
2. 프롬프트로 도구마다 `label`, `bbox_2d`, `point_2d`(tip = shaft 반대편의 작업 끝단)를 JSON 목록으로 요청한다. `point_2d`는 보통 점 하나 `[x, y]`이고, jaw가 벌어져 끝단이 둘로 보이는 도구만 `[[x1, y1], [x2, y2]]`로 두 점을 답하게 한다. 답의 형식은 자리 표시(`"<instrument type>"`, `[x1, y1, x2, y2]`)로만 보여 준다. 구체적인 값을 예시로 넣었을 때 모델이 그 좌표와 도구 이름을 그대로 베껴 답했기 때문이다. greedy decoding이라 같은 입력에는 같은 결과가 나온다.
3. 답을 다음과 같이 정리한다.
   - 좌표를 이미지 안으로, tip을 box 안으로 clamp
   - 도구당 tip은 최대 2개. 이미지 중심에 더 가까운 점이 `tip`, 나머지가 `tip2`. 6px 이내로 붙은 두 점은 하나로 본다. 3개 이상 답하면 앞의 2개만 쓴다
   - `tooltip/annotation.py`의 기준으로 너무 작거나 얇은 box 제거
   - IoU 0.9 이상으로 겹치는 중복 box 제거. 이때 버리는 box의 tip은 먼저 나온 도구의 `tip2`로 합친다(벌어진 jaw를 도구 두 개로 답하는 경우 대비)
   - tip이 없으면 box 꼭짓점 중 이미지 중심에 가장 가까운 점을 tip으로 사용
4. 답에서 JSON을 찾지 못한 프레임은 파일을 만들지 않는다. 다음 실행 때 다시 시도되며, 실행 끝에 실패 목록을 출력한다.

## 출력 형식

`annotation-manual`과 같은 형식을 확장한 것이며 `source`는 `"qwen"`이다.

- `tip`: 필수. 도구의 tip. tip이 둘이면 이미지 중심에 더 가까운 쪽
- `tip2`: 선택. 끝단이 둘로 보이는 도구(벌어진 grasper/scissors/bipolar jaw 등)의 두 번째 tip. 없으면 키 자체가 없다

`tip`은 그대로 필수 필드로 남기 때문에 `tip`만 읽는 기존 코드(학습·평가 코드, `annotation-editor`)는 수정 없이 동작한다. 단 `annotation-editor`는 `tip2`를 표시·편집하지 않으며, 편집기로 저장하면 `tip2`는 사라진다.
 실제로 레이블을 만든 로컬 모델은 `model`에, 모델이 답한 도구 이름은 각 annotation의 `label`에 추가로 기록한다(`annotation-editor`는 `label`을 표시하지는 않지만 저장할 때 보존한다).

```json
{
  "annotations": [
    {
      "bbox": {"height": 59, "width": 196, "x": 58, "y": 113},
      "label": "grasper",
      "tip": {"x": 250, "y": 154}
    },
    {
      "bbox": {"height": 130, "width": 200, "x": 400, "y": 200},
      "label": "scissors",
      "tip": {"x": 405, "y": 210},
      "tip2": {"x": 420, "y": 240}
    }
  ],
  "height": 480,
  "image": "video01_00000000.png",
  "model": "Qwen/Qwen3-VL-8B-Instruct",
  "source": "qwen",
  "width": 736
}
```

## 처리 시간

이미지당 대략 수백 ms~수 초가 걸린다(GPU, batch 크기, 도구 수에 따라 다름). cholec80 전체(약 18.4만 장)는 수십 시간 이상 걸릴 수 있으므로 `--splits`, `--limit`으로 나눠 실행하는 것을 권장한다. 기존 파일은 건너뛰므로 언제든 중단하고 이어서 실행할 수 있다.

## 원문 답변 저장 (`--save-raw`)

모델이 실제로 무엇을 답했는지 확인하기 위한 디버깅 옵션이다. 이번 실행에서 실제로 처리한 프레임만 저장되므로, 이미 annotation이 있는 프레임을 다시 보려면 `--overwrite`를 함께 준다.

```bash
uv run python -m scripts.generate-annotation-qwen --dataset cholec80 --splits val --limit 50 --device cuda:1 --overwrite --save-raw
```

`annotation-qwen-raw/{split}/{stem}.json`에 다음 내용이 저장된다.

| 필드 | 내용 |
| --- | --- |
| `image`, `width`, `height` | 원본 프레임 이름과 크기 |
| `coordinate_range` | `answer` 좌표의 범위(`1000`). `answer`의 좌표는 0~이 값으로 정규화되어 있다 |
| `model`, `batch_size`, `max_new_tokens` | 실행 조건 (batch 크기에 따른 차이 비교용) |
| `prompt` | 모델에 준 프롬프트 전문 |
| `answer` | 모델이 생성한 답변 원문 그대로 |
| `error` | 파싱 실패 사유. 성공하면 `null` |
| `annotations` | 스크립트가 `answer`를 후처리한 결과(원본 프레임 좌표). 실패하면 `null` |

`answer`와 `annotations`를 비교하면 모델이 애초에 몇 개를 답했는지, 후처리(clamp, 작은 box 제거, 중복 병합)에서 무엇이 바뀌었는지 구분할 수 있다.
