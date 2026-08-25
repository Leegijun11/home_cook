import api from "../hook/api"

//export const get_ingredients
export const get_ingredients = async () => {
    const response = await api.get("/ingredient")
    return response.data
}



export const toggle_ingredient = async (id, owned) => {
    const response = await api.post(`/ingredient/${id}`, {}, { params: { owned } })
    return response.data
}