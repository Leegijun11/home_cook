import api from "../hook/api"

// 사용자가 고른 cuisine/dish_type 조합을 저장하고, 저장된 row(id 포함)를 받아옴
// -> id는 이후 LLM 호출 단계에서 get_category(id)로 다시 조회할 때 사용
export const post_category = async (cuisine, dishType) => {
    const response = await api.post("/category/", { cuisine:cuisine, dish_type: dishType })
    return response.data
}

// 저장된 선택값을 id로 조회 (LLM 프롬프트 구성 시 사용)
export const get_category = async (category_id) => {
    const response = await api.get(`/category/${category_id}`)
    return response.data
}
