import { useState } from "react"
import { useNavigate } from "react-router-dom"
import "../style/Category.css"
import "../style/Search.css"

export default function Search() {
    const navigate = useNavigate()
    const [query, setQuery] = useState("")

    const canSubmit = query.trim().length > 0

    const handleSubmit = () => {
        if (!canSubmit) return
        navigate("/result", { state: { query: query.trim() } })
    }

    return (
        <div className="category-page">
            <h1 className="category-title">어떤 음식이 먹고 싶으세요?</h1>
            <p className="category-subtitle">
                원하는 느낌을 자유롭게 적어주시면 어울리는 레시피를 찾아드려요
            </p>

            <textarea
                className="search-input"
                placeholder="예: 매콤하고 혼자 먹기 좋은 국물요리"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                rows={4}
            />

            <div className="category-footer">
                <button className="category-back-btn" onClick={() => navigate("/category")}>
                    뒤로
                </button>
                <button
                    className="category-submit-btn"
                    disabled={!canSubmit}
                    onClick={handleSubmit}
                >
                    검색
                </button>
            </div>
        </div>
    )
}
