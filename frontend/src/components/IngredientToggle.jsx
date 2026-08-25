

export default function IngredientToggle({ingredient, onToggle}){

    return (
        <label style={{display:"flex",alignItems:"center",gap:"8px"}}>
            <input type ="checkbox" checked={ingredient.owned}
                onChange={(e)=> onToggle(ingredient.id, e.target.checked)}/>
                {ingredient.name}
        </label>
    )
}