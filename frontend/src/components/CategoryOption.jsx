// option: { id, label } 형태로 부모(CategoryGroup)에서 가공해서 내려줌
// - cuisine 그룹이면 label = row.cuisine
// - dish_type 그룹이면 label = row.dish_type
export default function CategoryOption({ option, selected, onSelect }) {
    return (
        <button
            type="button"
            className={`category-option${selected ? " selected" : ""}`}
            onClick={() => onSelect?.(option.id)}
        >
            {option.label}
        </button>
    )
}
