import IngredientToggle from "./IngredientToggle";


export default function IngredientGroup({type, items, onToggle}){
    return (
        <div>
            <h3>{type}</h3>
            <div style={{display:"flex", flexWrap:"wrap",gap:"12px"}}>
                {items.map((ingredient)=>(
                    <IngredientToggle key={ingredient.id}
                        ingredient={ingredient} onToggle={onToggle}/>
                ))}
            </div>
        </div>
    )
}