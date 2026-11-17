# 검색 평가 (bench)

자연어 검색(후보 검색 + LLM 재랭킹)을 쿼리 217개로 비교하는 평가 도구입니다. MySQL과 ChromaDB 없이 `backend/recipes/*.md`만으로 돌아갑니다.

## 평가셋 만드는 방법 (`gen_queries.py`)

- 레시피 110개마다 LLM이 "메뉴 이름을 모르는 사람이 입력할 법한 문장" 2개(느낌 중심, 상황 중심)를 만듭니다. 정답은 그 레시피 1개입니다.
- 정답 이름이나 주재료가 들어간 문장은 코드가 걸러서 다시 만들게 합니다(정답 누출 방지).
- 개발용(97개)과 최종용(120개)은 **레시피 단위**로 나눕니다. 같은 레시피의 두 문장이 양쪽에 섞이지 않습니다.
- 결과: `queries.jsonl` (id, query, gold, style, split)

## 실행

```bash
cd backend/evaluation/bench
python gen_queries.py          # 평가셋 생성 (이미 queries.jsonl 이 있습니다)
python run_eval.py dev         # 개발용: 구성을 고르는 데 씁니다
python run_eval.py test        # 최종용: 구성을 정한 뒤 한 번만 돌립니다
python verify_service.py       # 서비스 코드(chroma_store, reranker)가 이 도구와 같은 후보를 내는지 확인
```

LLM 결과는 `cache/`에 쌓여서 다시 돌려도 호출이 중복되지 않습니다(`cache/`는 git에 올리지 않습니다). `backend/.env`의 `OPENAI_API_KEY`를 씁니다.

## 비교하는 구성

| 구성 | 내용 |
|---|---|
| C1 | 벡터 유사도 top-10 |
| C2 | C1 + 카테고리 필터 (이전 서비스의 재랭킹 전 단계) |
| C3 | 키워드(BM25) top-10 |
| C4 | C2와 C3의 순위를 합산 (LLM 없음) |
| C5 | C2 → LLM 재랭킹 (이전 서비스) |
| **C6** | C2와 C3 후보를 한 풀로 합쳐(최대 20개) LLM 재랭킹 (**현재 서비스**) |
| C7 | 같은 풀을 LLM이 0~10점으로 채점 |

결과는 `results_dev.json`, `results_test.json`과 프로젝트 README에 있습니다.

## 한계

- 정답이 1개뿐인 엄격한 기준입니다. 다른 레시피도 맞는 쿼리(예: "시원한 국물")는 점수가 낮게 나옵니다.
- 쿼리를 LLM이 만들었습니다. 정답이 하나로 정해지지 않는 쿼리가 섞여 있고, 사람이 전부 검수하지는 않았습니다.
- 각 구성은 한 번씩만 돌렸습니다. LLM 호출의 재실행 변동은 측정하지 않았습니다.
- 평가의 LLM 호출은 `reasoning_effort="minimal"`입니다. 12개 쿼리 파일럿에서 기본 설정과 점수가 같았습니다.
- 기존 `eval_cases.py`의 12개 쿼리는 현재 구성에서 12/12로 만점이라 구성을 구분하지 못합니다. 회귀 테스트로만 씁니다.
