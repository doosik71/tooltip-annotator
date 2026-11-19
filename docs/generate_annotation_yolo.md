# `scripts/generate-annotation-yolo.py`

`scripts/generate-annotation-yolo.py`는 상위 tooltip-detector 저장소의 yolov8stooltip 검출기로 데이터셋 이미지마다 수술도구의 bounding box와 tip을 예측해 annotation JSON으로 저장하는 스크립트다.

yolov8stooltip은 YOLOv8s 백본에 pose head를 붙인 모델이다. 클래스는 `tool` 하나이고, 도구마다 keypoint 하나를 tip으로 예측하므로 box와 tip을 따로 짝지을 필요가 없다.

## 요구 사항

- tooltip-annotator가 상위 tooltip-detector 저장소 안에 있어야 한다. 스크립트는 `../standalone/yolov8stooltip`의 `common.inference.Detector`를 그대로 불러 쓴다.
- 학습된 체크포인트: 기본값 `../standalone/yolov8stooltip/data/model/<dataset>/model.pt` (현재 `cholec80`, `erop`)
- `uv sync` (`torch`, `torchvision`, `opencv-python` 사용. `ultralytics`는 필요 없다)
- 입력 이미지 `data/dataset/<name>/images/{train,val,test}`
- GPU 권장. A6000 기준 초당 약 85장(cholec80 전체 약 36분)

## 실행 예시

```bash
# 시험 실행
uv run python -m scripts.generate-annotation-yolo --dataset cholec80 --splits val --limit 20 --device cuda:0

# 전체 실행 (기존 JSON은 건너뛰므로 중단 후 다시 실행하면 이어서 진행)
uv run python -m scripts.generate-annotation-yolo --dataset cholec80 --device cuda:0
```

## CLI 옵션

- `--dataset`: 데이터셋 이름. `--input`/`--output`/`--model` 기본값 계산에 쓰인다.
- `--input`: `train/val/test` 이미지 루트. 기본값 `data/dataset/<dataset>/images`.
- `--output`: annotation JSON 루트. 기본값 `data/dataset/<dataset>/annotation-yolo`.
- `--model`: yolov8stooltip 체크포인트. 기본값 `../standalone/yolov8stooltip/data/model/<dataset>/model.pt`.
- `--splits`: 처리할 split 목록. 기본값 `train val test`.
- `--limit`: split마다 새로 처리할 최대 장수(시험 실행용).
- `--device`: torch 디바이스. 기본값은 CUDA가 있으면 `cuda:0`.
- `--conf`, `--iou`: 검출 신뢰도와 NMS IoU 임계값. 기본값 `0.25`, `0.45`(검출기 프로젝트와 같다).
- `--overwrite`: 이미 있는 JSON도 다시 생성한다.

## 처리 방식

1. 이미지를 체크포인트의 입력 크기(640)로 letterbox해 추론하고, box와 tip을 원본 좌표로 되돌린다.
2. 검출마다 annotation 하나를 만든다. tip은 반올림해 프레임 안으로 자르고, box는 tip 픽셀을 포함하도록 넓힌다. 상위 저장소의 `interactive-trainer.py`·`relabel-annotation.py`와 같은 규칙이다.
3. annotation을 box 좌상단 좌표 순으로 정렬해 저장한다. 검출이 없으면 `"annotations": []`로 저장한다.

## 출력 형식

`source`는 체크포인트 경로를 저장소 루트 기준 상대 경로로 적는다. 상위 저장소의 `scripts/relabel-annotation.py`가 `annotation`에 쓰던 값과 같다.

```json
{
  "annotations": [
    {"bbox": {"height": 69, "width": 127, "x": 145, "y": 324}, "tip": {"x": 271, "y": 349}}
  ],
  "height": 480,
  "image": "video33_00000000.png",
  "source": "standalone/yolov8stooltip/data/model/cholec80/model.pt",
  "width": 736
}
```

## `relabel-annotation.py` 결과와의 차이

`Detector`는 불러온 뒤 BatchNorm을 convolution에 합쳐(fuse) 추론한다. `relabel-annotation.py`는 학습 가능한 상태 그대로 추론하므로, 같은 체크포인트라도 일부 프레임에서 좌표가 1px 다를 수 있다. cholec80에서 `relabel-annotation.py`가 만든 레이블 391장과 비교했을 때 383장이 정확히 같았고, 나머지도 좌표 차이가 1px 이내였다.

## cholec80 `annotation-yolo`의 내력

cholec80의 `annotation`에는 예전에 `relabel-annotation.py`로 만든 yolov8stooltip 레이블이 많이 남아 있었다. 그래서 `annotation-yolo`는 다음 두 단계로 채웠다.

1. `annotation` 파일 중 `Manual`, `Monai`, `Opus`, `Qwen`, `Qwen2.5` 어느 것과도 `annotations`가 같지 않고 `source`가 위 체크포인트인 파일 156,071개를 그대로 복사했다.
2. 나머지 프레임은 이 스크립트로 생성했다.

따라서 복사한 파일은 `relabel-annotation.py`의 출력이고, 생성한 파일은 이 스크립트의 출력이다. 둘 사이에는 위의 1px 차이가 있을 수 있다. 모두 이 스크립트의 출력으로 맞추려면 `--overwrite`로 다시 실행한다.
