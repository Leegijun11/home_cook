

export default function IngredientToggle({ingredient, onToggle}){

    return (
        <label className={`ingredient-toggle${ingredient.owned ? " owned" : ""}`}>
            <input type ="checkbox" checked={ingredient.owned}
                onChange={(e)=> onToggle(ingredient.id, e.target.checked)}/>
                {ingredient.name}
        </label>
    )
}