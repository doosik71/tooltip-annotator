# 수작업 레이블 관리

사람이 직접 보정한 어노테이션(`annotation-manual`)을 데이터셋별 **독립 git 저장소**로 관리하는 방법을 설명한다.

## 왜 따로 관리하는가

`annotation-manual`은 사람이 직접 한 작업이라 **다시 만들어낼 수 없다.**

| 산출물                   | 생성 주체                     | 재생성 |
| ------------------------ | ----------------------------- | ------ |
| `images/`                | `generate-dataset`            | 가능   |
| `segmentation/`          | `generate-segmentation`       | 가능   |
| `annotation-monai/`      | `generate-annotation-monai`   | 가능   |
| `annotation-qwen/`       | `generate-annotation-qwen`    | 가능   |
| `annotation/`            | `annotation-editor` (사람의 선택) | **불가** |
| **`annotation-manual/`** | **사람**                      | **불가** |

`annotation-manual`을 잃으면 그 작업은 사람이 다시 해야 한다. 그래서 이 디렉터리를 별도 저장소로 떼어 보관한다.

`annotation/`도 재생성할 수 없다. 편집기에서 프레임마다 어느 자동 결과를 채택했는지가 기록되는 곳이고, 이 선택을 다시 계산해 주는 스크립트는 없다. 현재 `annotation/`은 이 라벨 저장소에 포함되지 않으므로 따로 백업해야 한다(아래 "백업 대상" 참고).

## 구조

각 데이터셋의 `annotation-manual` 디렉터리가 그 자체로 하나의 git 저장소다.

```text
tooltip-annotator/                      # 저장소 A (코드)
└── data/                               # .gitignore 의 /data/** 로 전부 제외
    └── dataset/
        ├── cholec80/
        │   ├── images/                 # 추적 안 함 (재생성 가능)
        │   ├── segmentation/           # 추적 안 함 (재생성 가능)
        │   ├── annotation-monai/       # 추적 안 함 (재생성 가능)
        │   ├── annotation/             # 추적 안 함 (재생성 불가, 따로 백업)
        │   └── annotation-manual/      # 저장소 B (독립)
        │       └── .git/
        └── erop/
            └── annotation-manual/      # 저장소 C (독립)
                └── .git/
```

`tooltip-annotator`의 `.gitignore`는 `/data/**`로 `data/` 전체를 제외한다. 따라서 바깥 저장소는 라벨 저장소의 존재조차 모르고, `git status`에도 아무것도 뜨지 않는다.

**서브모듈이 아니다.** `.gitmodules`도, gitlink도 없다. 두 저장소는 경로만 겹칠 뿐 서로를 참조하지 않는다.

### 서브모듈 대신 이 방식을 쓰는 이유

| 항목                  | 서브모듈                                    | 독립 저장소       |
| --------------------- | ------------------------------------------- | ----------------- |
| HEAD 상태             | detached. 커밋이 어느 브랜치에도 붙지 않는다 | `main` 유지       |
| 라벨 한 장 수정 시    | 커밋 2회 (안쪽 + gitlink 갱신)              | 커밋 1회          |
| 데이터셋 추가         | 저장소 생성 + `submodule add -f` + 커밋     | 저장소 생성 + 클론 |
| 바깥 저장소 이력      | 라벨 커밋마다 gitlink 커밋이 쌓인다          | 영향 없음         |

서브모듈은 detached HEAD 상태로 체크아웃되므로, 라벨 저장소 안에서 커밋한 뒤 `git submodule update`를 실행하면 그 커밋이 미아가 된다. 재생성이 불가능한 자산에 이 위험을 얹을 이유가 없다.

## 데이터셋별 저장소 목록

| 데이터셋   | 저장소                                                           | 상태        |
| ---------- | ---------------------------------------------------------------- | ----------- |
| `cholec80` | https://github.com/doosik71/cholec80-annotation-manual.git        | 운영 중     |
| `erop`     | (없음)                                                           | 보정 전     |

## 사용법

### 기존 저장소 받아오기

작업 트리에 `annotation-manual` 디렉터리가 **없는 상태에서** 클론한다. 디렉터리가 이미 있으면 `git clone`이 거부한다.

```bash
cd tooltip-annotator
git clone https://github.com/doosik71/cholec80-annotation-manual.git \
  data/dataset/cholec80/annotation-manual
```

클론한 보정 내용은 편집기의 `Manual` 탭에서 바로 볼 수 있다. 다만 `annotation/`에 자동으로 반영되지는 않는다. 수동 보정본을 `annotation/`에 일괄로 다시 반영하는 스크립트는 현재 없으며, 편집기에서 프레임을 열어 저장해야 `annotation/`에 기록된다.

### 일상 작업

편집기로 보정한 뒤, 라벨 저장소 안에서 평소처럼 커밋하고 push 한다. 바깥 저장소는 건드릴 필요가 없다.

```bash
cd tooltip-annotator/data/dataset/cholec80/annotation-manual
git status
git add -A
git commit -m "Correct 20 frames in train"
git push
```

편집기는 보정본을 저장할 때 같은 내용을 `annotation/`에도 쓴다. `annotation/`은 이 라벨 저장소의 커밋 대상이 아니다.

### 새 데이터셋에 보정 저장소 만들기

보정을 시작하면 `annotation-manual/{split}/`이 자동으로 생성된다. 어느 정도 작업한 뒤 저장소로 만든다.

```bash
cd tooltip-annotator/data/dataset/erop/annotation-manual
git init -b main
git add -A
git commit -m "Import hand-corrected erop tool annotations"
git remote add origin <새 저장소 URL>
git push -u origin main
```

그 다음 위의 "데이터셋별 저장소 목록" 표에 한 줄 추가한다.

## 주의할 점

### 클론을 빠뜨리면 조용히 0건으로 시작한다

새 장비에서 라벨 저장소를 클론하지 않으면, 편집기는 오류 없이 **보정본이 하나도 없는 상태로** 열린다. 이미 보정한 프레임을 다시 작업하게 될 수 있다.

편집기 좌측 목록에서 보정된 프레임은 `Manual` 색(노란색)으로 칠해지고 스크롤바 옆 표시 막대에 호박색 눈금이 생긴다. 보정했던 데이터셋을 열었는데 표시 막대에 눈금이 하나도 없다면 클론을 빠뜨린 것이다.

`count-dataset`의 출력으로도 split별 manual 레이블 수를 확인할 수 있다.

```bash
uv run python -m scripts.count-dataset --dataset cholec80
```

### `annotation/`과 `annotation-manual/`을 직접 고치지 않는다

두 디렉터리는 `annotation-editor`가 함께 맞춰 쓴다. 한쪽만 손으로 고치면 두 디렉터리가 어긋난다. 수정은 반드시 `annotation-editor`로 한다.

### `annotation-manual` 디렉터리를 미리 만들지 않는다

`git clone`은 비어 있지 않은 디렉터리를 거부한다. 편집기는 이 디렉터리를 미리 만들지 않으므로, 보정을 시작하기 전까지는 경로가 비어 있다.

### 백업 대상

`images`, `segmentation`, `annotation-monai`, `annotation-qwen` 같은 자동 annotation은 전부 재생성 가능하다. 백업과 이관에서 챙겨야 할 것은 다음 두 가지다.

- 각 데이터셋의 `annotation-manual` 저장소
- 각 데이터셋의 `annotation/` 디렉터리. 편집기에서 채택한 자동 결과가 여기에만 기록되며, 현재는 git 저장소로 관리되지 않는다

## 관련 문서

- [annotation_editor.md](./annotation_editor.md) — 자동 결과 채택과 보정에 쓰는 GUI 편집기
- [generate_annotation_monai.md](./generate_annotation_monai.md) — mask 기반 자동 annotation
- [generate_annotation_qwen.md](./generate_annotation_qwen.md) — VLM 기반 자동 annotation
