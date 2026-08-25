import { useEffect, useState } from "react"
import { toggle_ingredient, get_ingredients } from "../service/ingredient"
import IngredientGroup from "../components/IngredientGroup"


export default function Ingredients() {
    const [ingredients ,setIngredients] = useState([])
    const [loading, setLoading] = useState(true)

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
    if (loading) return <p>불러오는 중 ...</p>


    const grouped = ingredients.reduce((acc,item)=>{
        if (!acc[item.type]) acc[item.type] = []
        acc[item.type].push(item)
        return acc
    },{})
    return (
        <>
        <h1>재료 입력 페이지</h1>  
        {Object.entries(grouped).map(([type, items])=>(
            <IngredientGroup 
                key ={type} type={type} items={items} onToggle={handleToggle}/>
        ))}    
        </>

    )
}