import { BrowserRouter,Routes, Route} from 'react-router-dom'
import Category from "./pages/Category"
import Ingredients from "./pages/Ingredients"
import Result from "./pages/Result"

function App() {


  return (
    <BrowserRouter>
      <Routes>
        <Route path='/' element={<Ingredients/>}/>
        <Route path='/category' element={<Category/>}/>
        <Route path='/result' element={<Result/>}/>
      </Routes>
    </BrowserRouter>
  )
}

export default App
