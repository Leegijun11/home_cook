import { useState } from "react"
import { useNavigate } from "react-router-dom"
import CategoryGroup from "../components/CategoryGroup"
import { CUISINE_OPTIONS, DISH_TYPE_OPTIONS } from "../constants/category"
import { post_category } from "../service/category"
import "../style/Category.css"


export default function Category() {
    const navigate = useNavigate()

    const [selectedCuisine, setSelectedCuisine] = useState(null)
    const [selectedDishType, setSelectedDishType] = useState(null)
    const [submitting, setSubmitting] = useState(false)

    const canSubmit = selectedCuisine && selectedDishType && !submitting

    const handleComplete = async () => {
        if (!canSubmit) return

        setSubmitting(true)
        try {
            const saved = await post_category(selectedCuisine, selectedDishType)
            navigate("/result", { state: { categoryId: saved.id } })
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <div className="category-page">
            <h1 className="category-title">오늘 뭐 먹고 싶으세요?</h1>
            <p className="category-subtitle">종류를 선택하면 어울리는 자취 레시피를 추천해드려요</p>

            <CategoryGroup
                type="cuisine"
                title="음식 종류"
                options={CUISINE_OPTIONS}
                selectedId={selectedCuisine}
                onSelect={setSelectedCuisine}
            />

            <CategoryGroup
                type="dish_type"
                title="요리 형태"
                options={DISH_TYPE_OPTIONS}
                selectedId={selectedDishType}
                onSelect={setSelectedDishType}
            />

            <div className="category-footer">
                <button
                    className="category-submit-btn"
                    disabled={!canSubmit}
                    onClick={handleComplete}
                >
                    선택 완료
                </button>
            </div>
        </div>
    )
}
