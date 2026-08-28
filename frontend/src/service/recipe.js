import api from "../hook/api"

export const get_recipe_candidate = async (categoryId) => {
    const response = await api.post("/recipe/candidate", { category_id: categoryId })
    return response.data
}

export const generate_recipe = async ({ recipe_ref, spice_level, doneness }) => {
    const response = await api.post("/recipe/generate", { recipe_ref, spice_level, doneness })
    return response.data
}
