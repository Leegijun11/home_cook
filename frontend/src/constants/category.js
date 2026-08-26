// 자취생이 흔히 만들만한 음식 종류 / 요리 형태 기준 상수
// id는 그대로 백엔드로 넘길 문자열 값(=label)과 동일하게 사용

export const CUISINE_OPTIONS = [
    { id: "한식", label: "한식" },
    { id: "중식", label: "중식" },
    { id: "일식", label: "일식" },
    { id: "양식", label: "양식" },
    { id: "분식", label: "분식" },
    { id: "동남아식", label: "동남아식" },
]

export const DISH_TYPE_OPTIONS = [
    { id: "밥류", label: "밥류" },
    { id: "면류", label: "면류" },
    { id: "국물/찌개류", label: "국물/찌개류" },
    { id: "볶음류", label: "볶음류" },
    { id: "구이류", label: "구이류" },
    { id: "샐러드/간편식", label: "샐러드/간편식" },
]
