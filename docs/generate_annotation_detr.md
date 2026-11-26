# `scripts/generate-annotation-detr.py`

`scripts/generate-annotation-detr.py`는 상위 tooltip-detector 저장소의 detrtooltip 검출기로 데이터셋 이미지마다 수술도구의 bounding box와 tip 1〜2개를 예측해 annotation JSON으로 저장하는 스크립트다.

detrtooltip은 ResNet-50 + FPN 백본에 Deformable DETR 헤드를 붙인 모델이다. 클래스는 `tool` 하나이고, 도구마다 box 하나와 tip을 내며, 벌어진 가위처럼 끝이 둘인 도구에는 두 번째 tip(`tip2`)도 낸다.

## 요구 사항

- tooltip-annotator가 상위 tooltip-detector 저장소 안에 있어야 한다. 스크립트는 `../standalone/detrtooltip`의 `common.inference.Detector`를 그대로 불러 쓴다.
- 학습된 체크포인트: 기본값 `../standalone/detrtooltip/data/model/<dataset>/model.pt` (현재 `cholec80`)
- `uv sync` (`torch`, `torchvision`, `opencv-python` 사용)
- 입력 이미지 `data/dataset/<name>/images/{train,val,test}`
- GPU 권장. A6000 기준 초당 약 28장(cholec80 전체 약 1.8시간)

## 실행 예시

```bash
# 시험 실행
uv run python -m scripts.generate-annotation-detr --dataset cholec80 --splits val --limit 20 --device cuda:1

# 전체 실행 (기존 JSON은 건너뛰므로 중단 후 다시 실행하면 이어서 진행)
uv run python -m scripts.generate-annotation-detr --dataset cholec80 --device cuda:1
```

## CLI 옵션

- `--dataset`: 데이터셋 이름. `--input`/`--output`/`--model` 기본값 계산에 쓰인다.
- `--input`: `train/val/test` 이미지 루트. 기본값 `data/dataset/<dataset>/images`.
- `--output`: annotation JSON 루트. 기본값 `data/dataset/<dataset>/annotation-detr`.
- `--model`: detrtooltip 체크포인트. 기본값 `../standalone/detrtooltip/data/model/<dataset>/model.pt`.
- `--splits`: 처리할 split 목록. 기본값 `train val test`.
- `--limit`: split마다 새로 처리할 최대 장수(시험 실행용).
- `--device`: torch 디바이스. 기본값은 CUDA가 있으면 `cuda`.
- `--conf`: 검출 신뢰도 임계값. 기본값 `0.5`(검출기 프로젝트와 같다).
- `--overwrite`: 이미 있는 JSON도 다시 생성한다.

## 처리 방식

1. 이미지를 모델 입력 크기(736 × 480)로 맞춰 추론하고, box와 tip을 원본 좌표로 되돌린다. `tip2`는 모델의 P(두 번째 tip 존재)가 0.5를 넘을 때만 낸다. 두 tip이 20 px 이내이면 detrtooltip의 `postprocess()`가 두 점의 평균을 `tip` 하나로 내고 `tip2`는 내지 않는다(레이블 규칙과 같다).
2. 검출마다 annotation 하나를 만든다. tip은 반올림해 프레임 안으로 자르고, box는 모든 tip 픽셀을 포함하도록 넓힌다. `generate-annotation-yolo`와 같은 규칙이다.
3. 모델의 두 tip 슬롯에는 순서가 없다. 그래서 다른 자동 annotation(opus, qwen)과 같이 프레임 중심에 가까운 쪽을 `tip`, 다른 쪽을 `tip2`로 쓴다.
4. annotation을 box 좌상단 좌표 순으로 정렬해 저장한다. 검출이 없으면 `"annotations": []`로 저장한다.

## 출력 형식

`source`는 체크포인트 경로를 저장소 루트 기준 상대 경로로 적는다.

```json
{
  "annotations": [
    {"bbox": {"height": 241, "width": 361, "x": 42, "y": 125},
     "tip": {"x": 397, "y": 212}, "tip2": {"x": 310, "y": 344}},
    {"bbox": {"height": 71, "width": 217, "x": 297, "y": 46}, "tip": {"x": 301, "y": 111}}
  ],
  "height": 480,
  "image": "video41_00000025.png",
  "source": "standalone/detrtooltip/data/model/cholec80/model.pt",
  "width": 736
}
```

## 주의

cholec80 체크포인트는 `video42`를 뺀 train, val, test 전체로 학습했다. 따라서 `video42` 외 프레임의 결과는 모델이 학습 중에 본 레이블에 가까워, 처음 보는 영상보다 좋게 나온다.
