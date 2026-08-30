# 자취생 요리 추천 (RAG + Multi-Agent 개인 프로젝트)

집에 있는 재료와 카테고리 선택만으로, AI가 만들 수 있는 메뉴를 스스로 골라 레시피를 생성하고 검증까지 해주는 요리 추천 서비스.

## 프로젝트 목적

- RAG를 "단순 검색"이 아니라 **카테고리 필터 + 벡터 검색**으로 의미 있게 활용하는 구조 연습
- LLM에게 맡길 판단(재료 대체, 레시피 생성, 맛 평가)과 코드로 처리할 로직(재고 대조, 조건 분기)을 명확히 분리
- 생성 에이전트와 검증 에이전트를 분리한 Multi-Agent 구조로 self-consistency 문제 회피
- LangGraph 기반 State 관리 및 조건부 분기(재생성 사이클) 연습

## 전체 흐름

```
[재료 입력 - 토글] (DB 저장)
        ↓
[카테고리 선택 - 토글] (한식/중식/양식, 면류/밥류 등)
        ↓
[RAG 검색] → 카테고리로 필터링된 범위에서 메뉴 후보 1개 확정
        ↓
[재료 확인] (코드: 보유 재료 vs 레시피 필요 재료 대조)
   부족 재료 있음?
     ├─ 없음 → 통과
     └─ 있음 → 대체 가능성 판단 (코드: 카테고리 기반 후보 조회 + LLM: 맛 적합성 판단)
                 ├─ 대체 가능 → 통과
                 └─ 대체 불가 → "이 재료로는 어려워요" 안내 후 종료
        ↓
[요리사 에이전트] → 대체재/맵기 등 반영해 레시피 생성
        ↓
[미식가 에이전트] → 점수 + 코멘트(issues, suggestions) 생성
   점수 < 임계값?
     ├─ Yes → 1회 재생성 (이전 레시피 + 피드백을 반영해 수정) → 결과 그대로 표시
     └─ No → 바로 표시
        ↓
[사용자 최종 응답] "만들래요" / "안 할래요"
```

## 기술 스택

- **Agent Orchestration**: LangGraph
- **LLM**: 미정
- **Vector DB**: Chroma (예정)
- **DB (재료/유저 데이터)**: MySQL
- **Backend**: FastAPI
- **Frontend**: React (Node.js)

---

## DB 테이블 구조

로그인 없는 개인용 로컬 서비스 기준. 재료 하나(row)에 보유 여부(`owned`)를 바로 저장하는 단일 테이블 구조.

```python
class Ingredients(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    type = Column(String(100), nullable=False)
    owned = Column(Boolean, default=False)
```


### 레시피 원본 문서 (Vector DB, MySQL 아님)

MySQL이 아니라 Chroma 등 벡터DB에 별도 저장. 필드 구조는 아래 "레시피 문서 설계" 참고.

---

## API 명세 (FastAPI)

### 재료 관련

| Method | Endpoint | 설명 |
|---|---|---|
| GET | `/ingredients` | 전체 재료 목록 조회 (type별 그룹핑해서 반환 권장) |
| PATCH | `/ingredients/{id}` | 특정 재료의 `owned` 토글 |
| GET | `/ingredients/owned` | 보유 중(`owned=True`)인 재료만 조회 |

**`PATCH /ingredients/{id}` 요청 예시**
```json
{ "owned": true }
```

### 카테고리 관련

| Method | Endpoint | 설명 |
|---|---|---|
| GET | `/categories` | 선택 가능한 카테고리 목록 (한식/중식/양식, 면류/밥류 등 고정값이면 하드코딩도 무방) |

### 레시피 생성 파이프라인

파이프라인 전체를 하나의 엔드포인트로 묶을지, 단계별로 나눌지는 프론트 로딩 UI 구현 방식에 따라 결정.

**옵션 A: 단일 엔드포인트 (동기, 서버가 전체 그래프 실행 후 최종 결과만 반환)**

| Method | Endpoint | 설명 |
|---|---|---|
| POST | `/recipe/generate` | 보유 재료 + 카테고리로 전체 파이프라인 실행, 최종 레시피+점수 반환 |

```json
// Request
{ "category": { "cuisine": "양식", "type": "면류" } }

// Response
{
  "status": "done",
  "menu": "토마토파스타",
  "recipe": { "ingredients": [...], "steps": "..." },
  "substitutions": { "생크림": "우유+버터" },
  "score": 8.2,
  "feedback": { "issues": [], "suggestions": [] }
}
```

## LangGraph State 스키마 (예상)

```python
from typing import TypedDict

class RecipeState(TypedDict):
    user_inventory: list[str]        # 보유 재료
    category_filter: dict            # {"cuisine": "양식", "dish_type": "면류"}

    matched_menu: dict               # RAG 검색으로 확정된 메뉴/레시피
    substitutions: dict              # 확정된 대체 재료 매핑

    generated_recipe: dict           # 요리사 에이전트 출력
    critic_feedback: dict            # {score, issues, suggestions}

    retry_done: bool                 # 재생성 1회 소진 여부
    status: str                      # "checking_ingredients" / "generating" /
                                      # "reviewing" / "done" / "no_candidate"
```

---

## 데이터 설계

### 재료 DB
- 사용자가 토글로 입력한 재료를 카테고리로 태깅해서 저장
- 예: 라면사리 / 우동사리 / 밀면사리 → `면류`
- 목적: 대체 재료 후보를 코드로 빠르게 조회 (LLM 호출 없이)

### 레시피 문서 (벡터DB, 구조화 저장)

| 필드 | 내용 |
|---|---|
| `category` | 한식/중식/양식, 면류/밥류 등 (검색 필터용) |
| `base_ingredients` | 기본 재료 목록 |
| `substitution_table` | 재료별 대체 가능 품목 |
| `spice_level_table` | 맵기 단계별 재료 양 |
| `steps` | 조리 순서 (자유 텍스트) |

자유 텍스트로 통째로 저장하지 않고 필드별로 구조화하여, 필요한 정보만 선택적으로 검색하고 할루시네이션 위험을 줄임.
또한 정보 검색 시 불필요한 낭비를 줄임 (예: 사용자가 맵기를 선택 안 한다면 `spice_level_table` 필드를 조회 안 함).

## 역할 분리 원칙

| 코드(결정론적)가 처리 | LLM이 처리 |
|---|---|
| 재고 수량 대조 | 대체재의 맛 적합성 최종 판단 |
| 카테고리 기반 대체 후보 조회 | 레시피 생성, 맵기 조정 |
| 임계값 기반 재시도 여부 판단 | 미식가 평가 및 피드백 생성 |

## MVP 범위 (추후 개선 예정)

이번 버전에서 **의도적으로 제외**한 것들 (추후 확장 가능성으로 남겨둠):

- 메뉴 후보 여러 개를 순회하며 탈락시키는 로직 → 후보 1개만 확정
- RAG를 2단계(메뉴 탐색용 / 세부 규칙 참조용)로 나누는 구조 → 1단계로 통합 (검색 시 필요 필드 한 번에 조회)
- 미식가 평가 후 무제한 재시도 → 1회로 제한
- 메뉴판 이미지 인식(멀티모달)
- 사용자 식단 히스토리 기반 개인화
- SSE 기반 단계별 진행상황 스트리밍 (`/recipe/generate/stream`)
- `recipe_sessions` 히스토리 저장

## To-Do

- [x] 재료 카테고리 태깅 테이블 설계 및 시드 데이터 작성
- [x] `GET /ingredients`, `PATCH /ingredients/{id}` API 구현
- [x] 레시피 문서 5~10개 작성 (양식/한식/중식 각 2~3개, 커스터마이징 옵션 포함)
- [ ] 벡터 DB 구축 및 카테고리 필터 검색 테스트
- [ ] 요리사 에이전트 프롬프트 설계
- [ ] 미식가 에이전트 프롬프트 설계 (score/issues/suggestions 구조화 출력)
- [ ] LangGraph 그래프 구성 (노드/조건부 엣지)
- [ ] `POST /recipe/generate` 엔드포인트 구현
- [ ] 토글 UI 및 결과 표시 화면 구현 (React)
- [ ] 엔드투엔드 테스트 (재료 부족 케이스, 저품질 재생성 케이스 포함)
