import { useEffect, useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import CategoryGroup from "../components/CategoryGroup"
import { get_recipe_candidate, generate_recipe } from "../service/recipe"
import "../style/Category.css"
import "../style/Result.css"

const toOptions = (values = []) => values.map((value) => ({ id: value, label: value }))

// steps 문자열("1. ... \n2. ...")을 번호 없이 단계별 텍스트 배열로 분리
const parseSteps = (steps) =>
    (steps ?? "")
        .split("\n")
        .map((line) => line.trim().replace(/^\d+\.\s*/, ""))
        .filter(Boolean)

export default function Result() {
    const location = useLocation()
    const navigate = useNavigate()
    const categoryId = location.state?.categoryId

    const [status, setStatus] = useState("checking_candidate")
    const [candidate, setCandidate] = useState(null)
    const [spiceLevel, setSpiceLevel] = useState(null)
    const [doneness, setDoneness] = useState(null)
    const [recipe, setRecipe] = useState(null)
    const [errorMessage, setErrorMessage] = useState(null)

    useEffect(() => {
        if (!categoryId) {
            navigate("/category")
            return
        }

        get_recipe_candidate(categoryId)
            .then((data) => {
                if (data.status === "no_candidate") {
                    setStatus("no_candidate")
                    return
                }

                setCandidate(data)
                setStatus(data.needs_spice || data.needs_doneness ? "awaiting_attributes" : "generating")
            })
            .catch((err) => {
                console.error(err)
                setErrorMessage("후보 레시피를 확인하지 못했어요")
                setStatus("error")
            })
    }, [categoryId, navigate])

    useEffect(() => {
        if (status !== "generating" || !candidate) return

        generate_recipe({
            recipe_ref: candidate.recipe_ref,
            spice_level: spiceLevel,
            doneness: doneness,
            substitutions: candidate.substitutions,
        })
            .then((data) => {
                setRecipe(data)
                setStatus("done")
            })
            .catch((err) => {
                console.error(err)
                setErrorMessage("레시피 생성에 실패했어요")
                setStatus("error")
            })
    }, [status, candidate, spiceLevel, doneness])

    if (status === "checking_candidate") {
        return <p className="result-loading">후보 레시피를 확인하는 중 ...</p>
    }

    if (status === "no_candidate") {
        return (
            <div className="result-page">
                <p className="result-message">이 재료로는 어려워요</p>
                <div className="result-footer">
                    <button className="result-submit-btn" onClick={() => navigate("/category")}>
                        다시 선택하기
                    </button>
                </div>
            </div>
        )
    }

    if (status === "error") {
        return (
            <div className="result-page">
                <p className="result-message">{errorMessage}</p>
                <div className="result-footer">
                    <button className="result-submit-btn" onClick={() => navigate("/category")}>
                        뒤로가기
                    </button>
                </div>
            </div>
        )
    }

    if (status === "awaiting_attributes") {
        const canConfirm =
            (!candidate.needs_spice || spiceLevel) && (!candidate.needs_doneness || doneness)

        return (
            <div className="result-page">
                <h1 className="result-title">{candidate.menu} 세부 옵션을 선택해주세요</h1>

                {candidate.needs_spice && (
                    <CategoryGroup
                        type="spice_level"
                        title="맵기 선택"
                        options={toOptions(candidate.spice_options)}
                        selectedId={spiceLevel}
                        onSelect={setSpiceLevel}
                    />
                )}

                {candidate.needs_doneness && (
                    <CategoryGroup
                        type="doneness"
                        title="굽기 선택"
                        options={toOptions(candidate.doneness_options)}
                        selectedId={doneness}
                        onSelect={setDoneness}
                    />
                )}

                <div className="result-footer">
                    <button className="result-back-btn" onClick={() => navigate("/category")}>
                        뒤로
                    </button>
                    <button
                        className="result-submit-btn"
                        disabled={!canConfirm}
                        onClick={() => setStatus("generating")}
                    >
                        선택 완료
                    </button>
                </div>
            </div>
        )
    }

    if (status === "generating") {
        return <p className="result-loading">{candidate?.menu} 레시피를 생성하는 중 ...</p>
    }

    return (
        <div className="result-page">
            <h1 className="result-title">{recipe?.menu ?? candidate?.menu}</h1>

            {candidate?.substitutions && Object.keys(candidate.substitutions).length > 0 && (
                <p className="result-substitution-note">
                    {Object.entries(candidate.substitutions)
                        .map(([original, replacement]) => `${original} → ${replacement}`)
                        .join(", ")}{" "}
                    로 대체해서 만들었어요
                </p>
            )}

            <div className="result-section">
                <h3 className="result-section-title">재료</h3>
                <ul className="result-ingredients">
                    {(recipe?.ingredients ?? []).map((ingredient) => (
                        <li key={ingredient} className="result-ingredient-chip">
                            {ingredient}
                        </li>
                    ))}
                </ul>
            </div>

            <div className="result-section">
                <h3 className="result-section-title">조리 순서</h3>
                <ol className="result-steps-list">
                    {parseSteps(recipe?.steps).map((step, index) => (
                        <li key={index} className="result-steps-item">
                            {step}
                        </li>
                    ))}
                </ol>
            </div>

            <div className="result-section">
                <h3 className="result-section-title">미식가 평가</h3>

                <div className="result-feedback-card">
                    {recipe?.score != null && (
                        <div className="result-score-row">
                            <span className="result-score-badge">{recipe.score}</span>
                            <span className="result-score-max">/ 10</span>
                        </div>
                    )}
                    {recipe?.feedback?.comment && (
                        <p className="result-comment">{recipe.feedback.comment}</p>
                    )}

                    {recipe?.feedback?.strengths?.length > 0 && (
                        <ul className="result-strengths-list">
                            {recipe.feedback.strengths.map((strength) => (
                                <li key={strength}>{strength}</li>
                            ))}
                        </ul>
                    )}
                </div>

                {(recipe?.feedback?.issues?.length > 0 || recipe?.feedback?.suggestions?.length > 0) && (
                    <details className="result-feedback-more">
                        <summary>아쉬운 점 / 개선 제안 보기</summary>

                        {recipe?.feedback?.issues?.length > 0 && (
                            <div className="result-feedback-group">
                                <p className="result-feedback-label issue">아쉬운 점</p>
                                <ul className="result-feedback-list issue">
                                    {recipe.feedback.issues.map((issue) => (
                                        <li key={issue}>{issue}</li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {recipe?.feedback?.suggestions?.length > 0 && (
                            <div className="result-feedback-group">
                                <p className="result-feedback-label suggestion">개선 제안</p>
                                <ul className="result-feedback-list suggestion">
                                    {recipe.feedback.suggestions.map((suggestion) => (
                                        <li key={suggestion}>{suggestion}</li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </details>
                )}
            </div>

            <div className="result-footer">
                <button className="result-submit-btn" onClick={() => navigate("/")}>
                    다른 레시피 생성하기
                </button>
            </div>
        </div>
    )
}
