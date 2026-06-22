import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import SearchPage from './pages/SearchPage'
import DecisionPage from './pages/DecisionPage'
import ReportsPage from './pages/ReportsPage'
import AljProfilePage from './pages/AljProfilePage'
import NoAccess from './pages/NoAccess'

export default function App() {
  return (
    <Routes>
      {/* NoAccess renders outside the chrome so it reads as a gate, not a page. */}
      <Route path="/no-access" element={<NoAccess />} />
      <Route element={<Layout />}>
        <Route path="/" element={<SearchPage />} />
        <Route path="/decision/:caseNo" element={<DecisionPage />} />
        <Route path="/alj/:name" element={<AljProfilePage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="*" element={<SearchPage />} />
      </Route>
    </Routes>
  )
}
