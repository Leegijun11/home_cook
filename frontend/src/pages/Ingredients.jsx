import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { toggle_ingredient, get_ingredients } from "../service/ingredient"
import IngredientGroup from "../components/IngredientGroup"
import "../style/Ingredients.css"


export default function Ingredients() {
    const [ingredients ,setIngredients] = useState([])
    const [loading, setLoading] = useState(true)
    const navigate = useNavigate()

    useEffect(()=>{
        get_ingredients()
            .then(setIngredients)
            .finally(()=> setLoading(false))

    },[])

    const handleToggle = async (id,owned) => {
        setIngredients((prev) =>
            prev.map((item)=> (item.id=== id ? {...item, owned} : item))
        )

        try {
            await toggle_ingredient(id,owned)
        } catch(err){
            setIngredients((prev)=>
                prev.map((item)=> (item.id === id ? {...item, owned:!owned}: item))
            )
            console.error(err)
        }
    }
    const handleComplete = () => {
        const confirmed = window.confirm("재료 입력이 완료되었나요?")
        if (confirmed) {
            navigate("/category")
        }
    }

    if (loading) return <p className="ingredients-loading">불러오는 중 ...</p>


    const grouped = ingredients.reduce((acc,item)=>{
        if (!acc[item.type]) acc[item.type] = []
        acc[item.type].push(item)
        return acc
    },{})
    return (
        <div className="ingredients-page">
            <h1 className="ingredients-title">가지고 있는 재료를 선택해주세요</h1>
            <p className="ingredients-subtitle">보유한 재료를 모두 선택한 뒤 완료 버튼을 눌러주세요</p>
            {Object.entries(grouped).map(([type, items])=>(
                <IngredientGroup
                    key ={type} type={type} items={items} onToggle={handleToggle}/>
            ))}
            <div className="ingredients-footer">
                <button className="ingredients-submit-btn" onClick={handleComplete}>
                    입력 완료
                </button>
            </div>
        </div>

    )
}