# `scripts/generate-annotation-opus.py`

`scripts/generate-annotation-opus.py`는 Anthropic API로 Claude Opus에 프레임을 보내, 보이는 수술도구마다 도구 종류, bounding box, tip 좌표를 받아 annotation JSON으로 저장하는 스크립트다. 로컬 모델(`generate-annotation-qwen.py`)로는 두 번째 도구를 놓치고 tip과 도구 이름이 부정확했던 문제를 해결하기 위해 추가했다.

## 요구 사항

- `uv sync` (`anthropic` 패키지 추가됨)
- 환경 변수 `ANTHROPIC_API_KEY`에 Anthropic API 키
- 입력 이미지 `data/dataset/<name>/images/{train,val,test}`
- GPU 불필요

## 실행 예시

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# 1) 시험 실행: split당 몇 장, 실시간 호출, 원문·토큰 사용량 저장
uv run python -m scripts.generate-annotation-opus --dataset cholec80 --splits val --limit 20 --save-raw

# 2) 전체 실행: Batch API(반값). 제출 후 종료하며, 같은 명령을 다시 실행하면 끝난 batch의 결과를 받아 저장한다
uv run python -m scripts.generate-annotation-opus --dataset cholec80 --mode batch

# 결과가 나올 때까지 기다리며 받으려면
uv run python -m scripts.generate-annotation-opus --dataset cholec80 --mode batch --wait
```

실행이 끝나면 저장/실패 수, 토큰 사용량(입력, thinking을 포함한 출력), 추정 비용과 프레임당 비용을 출력한다. batch 모드의 사용량과 비용은 그 실행에서 결과를 받은 프레임만 집계한다.

## CLI 옵션

- `--dataset`, `--input`, `--output`: 다른 스크립트와 같다. 출력 기본값은 `data/dataset/<dataset>/annotation-opus`.
- `--model`: 기본값 `claude-opus-5-5`.
- `--effort`: `low`(기본), `medium`, `high`, `xhigh`, `max`. Opus 5.5는 thinking을 끌 수 없고, thinking 토큰은 출력 토큰으로 과금되므로 비용을 좌우하는 주요 값이다.
- `--max-tokens`: 프레임당 출력 한도(thinking 포함). 기본값 `16000`. 한도에 걸린 프레임은 실패로 처리된다.
- `--max-edge`: 긴 변이 이보다 큰 이미지는 먼저 축소해 보낸다. 기본값 `1568`. 736×480 프레임은 그대로 보낸다.
- `--mode`: `sync`(기본, 프레임마다 즉시 호출, 정가) 또는 `batch`(Message Batches API, 반값, 비동기).
- `--workers`: sync 모드 동시 요청 수. 기본값 `4`.
- `--batch-requests`: batch 하나에 넣을 최대 요청 수. 기본값 `2000`. 요청마다 이미지가 들어가므로 실제로는 batch당 200MB 한도에서 먼저 잘린다(PNG 프레임 기준 약 450장).
- `--wait`: batch 모드에서 모든 batch가 끝나 결과를 저장할 때까지 기다린다.
- `--splits`, `--limit`, `--overwrite`: qwen 스크립트와 같다.
- `--save-raw`, `--raw-output`: 원문 답변, stop reason, 토큰 사용량을 `annotation-opus-raw/{split}/{stem}.json`에 저장한다.

## 처리 방식

1. 프레임을 PNG 그대로 base64로 보낸다. 긴 변이 `--max-edge`보다 크면 축소하고, 받은 좌표를 원본 크기로 되돌린다.
2. system prompt로 작업 기준(모든 도구 찾기, 도구 종류 8가지, tip은 shaft 반대쪽 끝, jaw가 크게 벌어졌을 때만 tip 2개, hook은 절연 sheath가 아니라 금속 hook 끝)을 준다.
3. 답은 structured outputs(JSON schema)로 받는다. Opus 5.5는 tool 강제 호출을 지원하지 않아 이 방식을 쓴다.
4. 좌표를 이미지 안으로, tip을 box 안으로 clamp하고, 너무 작은 box를 버린다. tip이 둘이면 이미지 중심에 가까운 쪽이 `tip`, 나머지가 `tip2`다.
5. 거절(`refusal`), 출력 한도 초과, API 오류, 읽을 수 없는 답은 파일을 만들지 않는다. 다음 실행 때 다시 시도된다.

## Batch 모드 상태 파일

제출한 batch의 id와 각 요청이 어느 프레임인지는 `data/dataset/<dataset>/annotation-opus-batches.json`에 기록한다. 다시 실행하면

1. 끝난 batch의 결과를 받아 저장하고,
2. 아직 annotation이 없고 진행 중인 batch에도 들어 있지 않은 프레임만 새로 제출한다.

중간에 멈춰도 같은 명령으로 이어서 진행된다. batch 결과는 제출 후 29일까지만 받을 수 있으므로 그 안에 한 번 이상 다시 실행해야 한다. `--overwrite`와 batch 모드를 함께 쓰면 실행할 때마다 모든 프레임을 다시 제출하므로, 결과를 받는 재실행에는 `--overwrite`를 빼야 한다.

## 출력 형식

`annotation-qwen`과 같은 확장 형식이며 `source`는 `"opus"`, `model`은 사용한 모델 id다.

```json
{
  "annotations": [
    {
      "bbox": {"height": 69, "width": 127, "x": 145, "y": 324},
      "label": "grasper",
      "tip": {"x": 271, "y": 349}
    }
  ],
  "height": 480,
  "image": "video33_00000000.png",
  "model": "claude-opus-5-5",
  "source": "opus",
  "width": 736
}
```

## 비용

가격(2026-11 기준, 100만 토큰당): Opus 5.5 입력 $4 / 출력 $20, Batch API는 그 절반($2 / $10). 736×480 프레임 한 장은 이미지 약 486토큰(28×28 patch 기준)이고, 프롬프트를 포함한 입력은 프레임당 약 1,100토큰이다. 출력은 JSON 답(약 100~150토큰)과 thinking 토큰의 합이라 `--effort`에 따라 크게 달라진다. 정확한 프레임당 비용은 시험 실행 끝에 출력되는 값으로 확인한다.
