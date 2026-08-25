import IngredientToggle from "./IngredientToggle";


export default function IngredientGroup({type, items, onToggle}){
    return (
        <div className="ingredient-group">
            <h3 className="ingredient-group-title">{type}</h3>
            <div className="ingredient-group-items">
                {items.map((ingredient)=>(
                    <IngredientToggle key={ingredient.id}
                        ingredient={ingredient} onToggle={onToggle}/>
                ))}
            </div>
        </div>
    )
}