# 자취생 요리 추천 (LLM + Multi-Agent 개인 프로젝트)

집에 있는 재료·조리도구와 원하는 요리 종류만 고르면, AI가 만들 수 있는 메뉴를 골라 레시피를 생성하고 스스로 평가까지 해주는 요리 추천 서비스.

## 데모

| 재료·조리도구 선택 | 카테고리 선택 | 레시피 결과 |
|---|---|---|
| ![재료 선택](images/ingredients.png) | ![카테고리 선택](images/category.png) | ![결과](images/result.png) |

## 프로젝트 목적

- LLM에게 맡길 판단(재료 대체, 레시피 생성, 맛 평가)과 코드로 처리할 로직(재고·도구 대조, 조건 분기, 재시도 여부)을 명확히 분리하는 구조 연습
- 생성 에이전트와 평가 에이전트를 분리한 Multi-Agent 구조로 self-consistency 문제 회피
- LangGraph 기반 State 관리 및 조건부 분기(재생성 사이클) 연습

## 전체 흐름

```
[재료 / 조리도구 입력 - 토글] (DB 저장)
        ↓
[카테고리 선택] (한식/중식/양식 등, 면류/밥류 등)
        ↓
[레시피 후보 확정] POST /recipe/candidate
   카테고리와 일치하는 레시피 문서 중,
     - main_tool을 보유하지 않음 → 후보 제외
     - base_ingredients가 부족해도 substitution_table의 대체품을 보유 → 대체재로 인정
     - 그래도 부족 → 후보 제외
   위 조건을 만족하는 첫 번째 메뉴를 후보로 확정 (없으면 "no_candidate")
        ↓
[맵기 / 굽기 선택] (필요한 단계가 있고, 그 단계에 필요한 재료를 보유한 경우만 옵션으로 노출)
        ↓
[레시피 생성] POST /recipe/generate (LangGraph)
   요리사 에이전트 → 레시피 생성
        ↓
   코드 검증: 맵기 재료 언급 여부 / 굽기 시간·온도 반영 여부 / 대체재 반영 여부
        ↓
   미식가 에이전트 → 점수 + comment + issues/suggestions
        ↓
   (검증 실패 또는 점수 < 임계값) && 재시도 안 했음?
     ├─ Yes → 1회 재생성 (이전 결과는 보여주지 않고, 어떤 실수를 피해야 하는지만 알려주고 처음부터 재작성) → 결과 그대로 표시
     └─ No  → 바로 표시
        ↓
[결과 화면] 메뉴 / 재료 / 조리순서 / 대체 재료 안내 / 미식가 평가(점수·코멘트·이슈) 표시
```

## 기술 스택

- **Backend**: FastAPI, SQLAlchemy, MySQL
- **Frontend**: React (Vite), Axios, React Router
- **LLM**: OpenAI GPT-3.5-turbo
- **Agent Orchestration**: LangGraph
## 실행 방법

### Backend

```bash
cd backend
venv\Scripts\activate
uvicorn main:app --reload
```

`backend/.env`에 `OPENAI_API_KEY`, `OPENAI_MODEL`(기본 gpt-3.5-turbo)을 설정해야 합니다. MySQL 접속 정보는 `backend/database.py`에 있습니다.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### 재료 시드 데이터

```bash
cd backend
python table.py
```

`ingredients_seed.csv`를 읽어 DB에 없는 재료만 추가합니다 (재실행해도 중복 삽입되지 않음).

## API 명세

| Method | Endpoint | 설명 |
|---|---|---|
| GET | `/ingredient/` | 전체 재료·조리도구 목록 조회 |
| POST | `/ingredient/{id}` | 특정 재료의 `owned` 토글 |
| POST | `/category/` | 카테고리(cuisine, dish_type) 선택값 저장 |
| GET | `/category/{id}` | 저장된 카테고리 조회 |
| POST | `/recipe/candidate` | 카테고리 + 보유 재료·도구로 레시피 후보 확정 |
| POST | `/recipe/generate` | 확정된 후보 + 맵기/굽기/대체재로 최종 레시피 생성 |

**`POST /recipe/candidate` 응답 예시**
```json
{
  "status": "ready",
  "recipe_ref": "동남아식_면류_팟타이",
  "menu": "팟타이",
  "needs_spice": true,
  "needs_doneness": false,
  "spice_options": ["순한맛", "매운맛"],
  "doneness_options": [],
  "substitutions": { "새우": "돼지고기", "피시소스": "멸치액젓" }
}
```

**`POST /recipe/generate` 응답 예시**
```json
{
  "status": "done",
  "menu": "팟타이",
  "ingredients": ["쌀국수", "돼지고기", "계란", "숙주", "다진마늘", "멸치액젓", "설탕", "식용유", "고춧가루", "청양고추"],
  "steps": "...",
  "score": 7,
  "feedback": {
    "score": 7,
    "comment": "조리 순서가 구체적이고 따라하기 쉬움",
    "issues": [],
    "suggestions": ["양념의 양과 맛의 조절법에 대해 더 자세히 설명하는 것이 도움이 될 것"]
  }
}
```

## 데이터 설계

### 재료 / 조리도구 (MySQL, `ingredients` 테이블)

```python
class Ingredients(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255))
    category = Column(String(100))
    type = Column(String(100))       # 토글 UI 그룹핑 기준 (조미료/채소/조리도구 등)
    owned = Column(Boolean, default=False, nullable=False)
```

조리도구도 같은 테이블에 `category="조리도구"`로 저장해서, 재료와 동일한 토글 UI/보유 여부 로직을 그대로 재사용합니다.

### 레시피 문서 (`backend/recipes/<cuisine>/<dish_type>/<menu>.md`)

MySQL이 아니라 마크다운 파일로 관리 (YAML frontmatter + 자유 텍스트 조리방법). `crud/recipe.py`가 실행 시점에 전체 파일을 읽어 `cuisine`/`dish_type` 필드 기준으로 필터링합니다.

| 필드 | 내용 |
|---|---|
| `base_ingredients` | 기본 재료 목록 |
| `substitution_table` | 재료별 대체 가능 품목 |
| `spice_level_table` | 맵기 단계별 재료/양 |
| `doneness_table` | 굽기 단계별 시간/온도 (nullable) |
| `main_tool` | 필수 조리도구 |

## 역할 분리

| 코드(결정론적)가 처리 | LLM이 처리 |
|---|---|
| 재고·조리도구 보유 대조 | 레시피 생성 (요리사 에이전트) |
| 대체 재료 후보 조회 (substitution_table) | 레시피 전반적인 완성도 평가 (미식가 에이전트) |
| 맵기 재료 언급 여부 / 굽기 시간·온도 반영 여부 / 대체재 반영 여부 검증 | — |
| 임계값·검증 결과 기반 재시도 여부 판단 | — |

레시피 생성 결과가 지시(필수 재료 언급, 대체재 반영 등)를 지켰는지는 LLM 자체 판단에 맡기지 않고 문자열 검증으로 코드가 직접 확인합니다 — 미식가 에이전트가 이 판단을 종종 틀리게 내리는 걸 확인했기 때문입니다.
