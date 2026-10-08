import { Route, Routes } from 'react-router'
import Layout from './components/Layout'
import AskPage from './pages/AskPage'
import DraftWorkspacePage from './pages/DraftWorkspacePage'
import ProjectsPage from './pages/ProjectsPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<DraftWorkspacePage />} />
        <Route path="labels/:label/draft" element={<DraftWorkspacePage />} />
        <Route path="ask" element={<AskPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<main style={{ padding: 24 }}>Page not found.</main>} />
      </Route>
    </Routes>
  )
}
