import CategoryOption from "./CategoryOption"


// type: "cuisine" | "dish_type" 구분용 (제목 표시 및 onSelect 시 어떤 축인지 구분할 때 사용)
export default function CategoryGroup({ type, title, options = [], selectedId, onSelect }) {
    return (
        <div className="category-group">
            <h3 className="category-group-title">{title}</h3>
            <div className="category-group-items">
                {options.map((option) => (
                    <CategoryOption
                        key={option.id}
                        option={option}
                        selected={option.id === selectedId}
                        onSelect={onSelect}
                    />
                ))}
            </div>
        </div>
    )
}