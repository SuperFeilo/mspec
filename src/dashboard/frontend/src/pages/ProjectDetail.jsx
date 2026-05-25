import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTask } from '../hooks/useTask'
import { ArrowLeft, Play, Save, FileCode, GitBranch } from 'lucide-react'

async function fetchProject(projectId) {
  const res = await fetch(`/api/projects/${projectId}`)
  if (!res.ok) throw new Error('Project not found')
  return res.json()
}

async function fetchMemory(projectId) {
  const res = await fetch(`/api/projects/${projectId}/memory`)
  if (!res.ok) throw new Error('Failed to fetch memory')
  return res.json()
}

export default function ProjectDetail() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [planning, setPlanning] = useState(false)
  const [running, setRunning] = useState(false)
  const [checkpointing, setCheckpointing] = useState(false)
  const [taskId, setTaskId] = useState(null)

  const { data: projectData, isLoading, refetch } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => fetchProject(projectId),
    refetchInterval: 3000,
  })

  const { data: memoryData } = useQuery({
    queryKey: ['memory', projectId],
    queryFn: () => fetchMemory(projectId),
    enabled: !!projectData,
  })

  const task = useTask(taskId)

  async function handlePlan() {
    setPlanning(true)
    const res = await fetch(`/api/projects/${projectId}/plan`, { method: 'POST' })
    const data = await res.json()
    setTaskId(data.task_id)
    setTimeout(() => { setPlanning(false); refetch() }, 1000)
  }

  async function handleRun() {
    setRunning(true)
    const res = await fetch(`/api/projects/${projectId}/run`, { method: 'POST' })
    const data = await res.json()
    setTaskId(data.task_id)
    setTimeout(() => { setRunning(false); refetch() }, 1000)
  }

  async function handleCheckpoint() {
    setCheckpointing(true)
    await fetch(`/api/projects/${projectId}/checkpoint`, { method: 'POST' })
    setCheckpointing(false)
    refetch()
  }

  if (isLoading) {
    return <div className="text-gray-400 py-10">Loading...</div>
  }

  const project = projectData?.project
  if (!project) {
    return (
      <div className="text-center py-16 text-gray-500">
        <p>Project not found.</p>
        <Link to="/" className="text-cyan-400 hover:underline text-sm mt-2 inline-block">Back to Home</Link>
      </div>
    )
  }

  const phaseProgress = memoryData?.phase_progress || {}

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/" className="text-gray-400 hover:text-gray-200">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold">{project.name}</h1>
            <div className="text-sm text-gray-400 flex items-center gap-2">
              <GitBranch className="w-3 h-3" />
              {project.git_branch}
              {project.git_uncommitted_count > 0 && (
                <span className="text-yellow-400">({project.git_uncommitted_count} uncommitted)</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handlePlan}
            disabled={planning}
            className="flex items-center gap-1.5 bg-blue-700 hover:bg-blue-600 disabled:bg-gray-700 text-white text-sm px-3 py-1.5 rounded transition-colors"
          >
            <FileCode className="w-4 h-4" />
            {planning ? 'Planning...' : 'Plan'}
          </button>
          <button
            onClick={handleRun}
            disabled={running}
            className="flex items-center gap-1.5 bg-green-700 hover:bg-green-600 disabled:bg-gray-700 text-white text-sm px-3 py-1.5 rounded transition-colors"
          >
            <Play className="w-4 h-4" />
            {running ? 'Running...' : 'Run'}
          </button>
          <button
            onClick={handleCheckpoint}
            disabled={checkpointing}
            className="flex items-center gap-1.5 bg-amber-700 hover:bg-amber-600 disabled:bg-gray-700 text-white text-sm px-3 py-1.5 rounded transition-colors"
          >
            <Save className="w-4 h-4" />
            {checkpointing ? 'Saving...' : 'Checkpoint'}
          </button>
        </div>
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-sm text-gray-400">Status</div>
          <div className="text-lg font-semibold mt-1 capitalize">{project.status}</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-sm text-gray-400">Phase</div>
          <div className="text-lg font-semibold mt-1">{project.current_phase || '—'}</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-sm text-gray-400">Sessions</div>
          <div className="text-lg font-semibold mt-1">{project.session_count}</div>
        </div>
      </div>

      {/* Phase progress */}
      {Object.keys(phaseProgress).length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">Phase Progress</h2>
          <div className="space-y-2">
            {Object.entries(phaseProgress).map(([phase, stats]) => (
              <div key={phase} className="bg-gray-900 border border-gray-800 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm">{phase}</span>
                  <span className="text-xs text-gray-400">
                    {stats.done}/{stats.total} done
                  </span>
                </div>
                <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-cyan-600 rounded-full transition-all"
                    style={{ width: `${stats.total > 0 ? (stats.done / stats.total) * 100 : 0}%` }}
                  />
                </div>
                {stats.blocked > 0 && (
                  <div className="mt-1 text-xs text-red-400">{stats.blocked} blocked</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Task progress */}
      {task && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-sm font-medium mb-2">Task: {task.operation}</div>
          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-cyan-500 rounded-full transition-all"
              style={{ width: `${task.progress || 0}%` }}
            />
          </div>
          <div className="text-xs text-gray-400 mt-1">{task.message}</div>
        </div>
      )}

      {/* Nav links */}
      <div className="flex gap-3">
        <Link to={`/project/${projectId}/sessions`} className="text-cyan-400 hover:underline text-sm">Sessions</Link>
        <Link to={`/project/${projectId}/memory`} className="text-cyan-400 hover:underline text-sm">Memory</Link>
        <Link to={`/project/${projectId}/git`} className="text-cyan-400 hover:underline text-sm">Git</Link>
        <Link to={`/project/${projectId}/context`} className="text-cyan-400 hover:underline text-sm">Context</Link>
      </div>
    </div>
  )
}
