# 수작업 레이블 관리

사람이 직접 보정한 어노테이션(`annotation-manual`)을 데이터셋별 **독립 git 저장소**로 관리하는 방법을 설명한다.

## 왜 따로 관리하는가

파이프라인이 만드는 산출물 중 `annotation-manual`만이 **다시 만들어낼 수 없다.**

| 산출물                   | 생성 주체               | 재생성 |
| ------------------------ | ----------------------- | ------ |
| `images/`                | `generate_dataset`      | 가능   |
| `segmentation/`          | `generate_segmentation` | 가능   |
| `annotation/`            | `generate_annotation`   | 가능   |
| **`annotation-manual/`** | **사람**                | **불가** |

`annotation/`은 `annotation-manual`에 있는 프레임은 그대로 복사하고 나머지는 마스크에서 계산한 결과다. 즉 `annotation-manual`과 `segmentation`만 있으면 `annotation` 전체를 언제든 복원할 수 있다. 반대로 `annotation-manual`을 잃으면 그 작업은 사람이 다시 해야 한다.

그래서 이 디렉터리만 별도 저장소로 떼어 보관한다.

## 구조

각 데이터셋의 `annotation-manual` 디렉터리가 그 자체로 하나의 git 저장소다.

```text
tooltip-annotator/                      # 저장소 A (코드)
└── data/                               # .gitignore 의 /data/** 로 전부 제외
    └── dataset/
        ├── cholec80/
        │   ├── images/                 # 추적 안 함 (재생성 가능)
        │   ├── segmentation/           # 추적 안 함 (재생성 가능)
        │   ├── annotation/             # 추적 안 함 (재생성 가능)
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

클론 후 `generate_annotation`을 한 번 실행하면 받아온 보정 내용이 `annotation/`에 반영된다.

```bash
python -m scripts.generate_annotation --dataset cholec80
```

### 일상 작업

편집기로 보정한 뒤, 라벨 저장소 안에서 평소처럼 커밋하고 push 한다. 바깥 저장소는 건드릴 필요가 없다.

```bash
cd tooltip-annotator/data/dataset/cholec80/annotation-manual
git status
git add -A
git commit -m "Correct 20 frames in train"
git push
```

`annotation/` 쪽 사본은 생성물이므로 커밋 대상이 아니다. 편집기가 자동으로 맞춰 둔다.

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

편집기 좌측 목록에서 보정된 프레임은 노란색으로 강조되므로, 보정했던 데이터셋을 열었는데 노란 줄이 하나도 없다면 클론을 빠뜨린 것이다.

`generate_annotation`의 출력으로도 확인할 수 있다.

```text
train: saved=0, skipped=71032, manual=306 (restored=0)
```

`manual` 값이 기대한 보정 건수와 맞는지 보면 된다.

### `annotation/`을 직접 고치지 않는다

`annotation/`은 생성물이다. 직접 편집해도 다음 `generate_annotation` 실행 때 `annotation-manual`의 내용으로 되돌아간다. 수정은 반드시 `annotation_editor`로 한다.

### `annotation-manual` 디렉터리를 미리 만들지 않는다

`git clone`은 비어 있지 않은 디렉터리를 거부한다. 편집기와 `generate_annotation`은 이 디렉터리를 미리 만들지 않으므로, 보정을 시작하기 전까지는 경로가 비어 있다.

### 백업 대상은 이 저장소뿐이다

`images`, `segmentation`, `annotation`은 전부 재생성 가능하다. 백업과 이관에서 챙겨야 할 것은 각 데이터셋의 `annotation-manual` 저장소뿐이다.

## 관련 문서

- [annotation_editor.md](./annotation_editor.md) — 보정 작업에 쓰는 GUI 편집기
- [generate_annotation.md](./generate_annotation.md) — 자동 생성과 보정본 적용 규칙
