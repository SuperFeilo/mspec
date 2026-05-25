import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import NewProject from './pages/NewProject'
import ProjectDetail from './pages/ProjectDetail'
import ProjectSessions from './pages/ProjectSessions'
import ProjectMemory from './pages/ProjectMemory'
import ProjectGit from './pages/ProjectGit'
import ProjectContext from './pages/ProjectContext'
import Activity from './pages/Activity'
import Settings from './pages/Settings'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="new" element={<NewProject />} />
        <Route path="project/:projectId" element={<ProjectDetail />} />
        <Route path="project/:projectId/sessions" element={<ProjectSessions />} />
        <Route path="project/:projectId/memory" element={<ProjectMemory />} />
        <Route path="project/:projectId/git" element={<ProjectGit />} />
        <Route path="project/:projectId/context" element={<ProjectContext />} />
        <Route path="activity" element={<Activity />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default App
