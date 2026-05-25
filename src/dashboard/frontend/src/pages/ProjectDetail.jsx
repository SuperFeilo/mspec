import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Play, Save, GitBranch, Trash2, CheckCircle, Loader, X, Circle, Clock, GitFork, GitCommitHorizontal } from 'lucide-react'

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

async function fetchBuildPlan(projectId) {
  const res = await fetch(`/api/projects/${projectId}/build-plan`)
  if (!res.ok) throw new Error('Failed')
  return res.json()
}

const STEP_STATUSES = [
  { value: 'not_started', label: 'Not Started', icon: Circle, color: 'text-gray-500 bg-gray-800 border-gray-700' },
  { value: 'in_progress', label: 'In Progress', icon: Clock, color: 'text-blue-300 bg-blue-900/30 border-blue-800/50' },
  { value: 'tested', label: 'Tested', icon: CheckCircle, color: 'text-cyan-300 bg-cyan-900/30 border-cyan-800/50' },
  { value: 'ready_for_merge', label: 'Ready for Merge', icon: GitFork, color: 'text-amber-300 bg-amber-900/30 border-amber-800/50' },
  { value: 'merged', label: 'Merged/Pushed', icon: GitCommitHorizontal, color: 'text-green-300 bg-green-900/30 border-green-800/50' },
]

function StatusIcon({ status }) {
  const cfg = STEP_STATUSES.find(s => s.value === status) || STEP_STATUSES[0]
  const Icon = cfg.icon
  return <Icon className="w-4 h-4" />
}

export default function ProjectDetail() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [running, setRunning] = useState(false)
  const [taskId, setTaskId] = useState(null)
  const [showCheckpoint, setShowCheckpoint] = useState(false)
  const [stepStatuses, setStepStatuses] = useState({})
  const [checkpointSaving, setCheckpointSaving] = useState(false)
  const [checkpointMsg, setCheckpointMsg] = useState('')

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

  const { data: buildPlan } = useQuery({
    queryKey: ['build-plan-small', projectId],
    queryFn: () => fetchBuildPlan(projectId),
    enabled: showCheckpoint,
  })

  async function handleRun() {
    setRunning(true)
    const res = await fetch(`/api/projects/${projectId}/run`, { method: 'POST' })
    const data = await res.json()
    setTaskId(data.task_id)
    setTimeout(() => { setRunning(false); refetch() }, 1000)
  }

  async function openCheckpoint() {
    setShowCheckpoint(true)
    setCheckpointMsg('')
    // Load current step statuses
    try {
      const res = await fetch(`/api/projects/${projectId}/build-plan`)
      if (res.ok) {
        const data = await res.json()
        if (data.exists && data.steps) {
          const statuses = {}
          data.steps.forEach(s => { statuses[s.id] = s.status || 'not_started' })
          setStepStatuses(statuses)
        }
      }
    } catch (e) {
      // No build plan yet, that's fine
    }
  }

  async function handleStepStatusChange(stepId, newStatus) {
    setStepStatuses(prev => ({ ...prev, [stepId]: newStatus }))
    // Also update via API
    try {
      await fetch(`/api/projects/${projectId}/build-plan/step/${stepId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
    } catch (e) { /* ignore */ }
  }

  async function handleCheckpointCommit() {
    setCheckpointSaving(true)
    setCheckpointMsg('')
    try {
      // Save all step statuses
      for (const [stepId, status] of Object.entries(stepStatuses)) {
        await fetch(`/api/projects/${projectId}/build-plan/step/${stepId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status }),
        })
      }

      // Run git checkpoint
      const res = await fetch(`/api/projects/${projectId}/checkpoint`, { method: 'POST' })
      if (!res.ok) throw new Error('Checkpoint failed')

      // Build progress summary for commit
      const total = Object.keys(stepStatuses).length
      const merged = Object.values(stepStatuses).filter(s => s === 'merged').length
      const tested = Object.values(stepStatuses).filter(s => s === 'tested' || s === 'ready_for_merge' || s === 'merged').length
      const inProg = Object.values(stepStatuses).filter(s => s === 'in_progress').length

      const summary = `Build progress: ${merged}/${total} merged, ${tested}/${total} tested, ${inProg} in progress`
      setCheckpointMsg(`✓ Checkpoint saved! ${summary}`)
      setTimeout(() => { setShowCheckpoint(false); refetch() }, 2000)
    } catch (err) {
      setCheckpointMsg(`Error: ${err.message}`)
    } finally {
      setCheckpointSaving(false)
    }
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
  const steps = buildPlan?.steps || []
  const mergedCount = Object.values(stepStatuses).filter(s => s === 'merged').length
  const totalSteps = Object.keys(stepStatuses).length || steps.length

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
            onClick={handleRun}
            disabled={running}
            className="flex items-center gap-1.5 bg-green-700 hover:bg-green-600 disabled:bg-gray-700 text-white text-sm px-3 py-1.5 rounded transition-colors"
          >
            <Play className="w-4 h-4" />
            {running ? 'Running...' : 'Run'}
          </button>
          <button
            onClick={openCheckpoint}
            className="flex items-center gap-1.5 bg-amber-700 hover:bg-amber-600 text-white text-sm px-3 py-1.5 rounded transition-colors"
          >
            <Save className="w-4 h-4" />
            Checkpoint
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
          <div className="text-sm text-gray-400">Build Progress</div>
          <div className="text-lg font-semibold mt-1">
            {totalSteps > 0 ? `${mergedCount}/${totalSteps} merged` : '—'}
          </div>
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
                  <span className="text-xs text-gray-400">{stats.done}/{stats.total} done</span>
                </div>
                <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                  <div className="h-full bg-cyan-600 rounded-full transition-all" style={{ width: `${stats.total > 0 ? (stats.done / stats.total) * 100 : 0}%` }} />
                </div>
                {stats.blocked > 0 && <div className="mt-1 text-xs text-red-400">{stats.blocked} blocked</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Nav links */}
      <div className="flex gap-3">
        <Link to={`/project/${projectId}/sessions`} className="text-cyan-400 hover:underline text-sm">Sessions</Link>
        <Link to={`/project/${projectId}/memory`} className="text-cyan-400 hover:underline text-sm">Memory</Link>
        <Link to={`/project/${projectId}/git`} className="text-cyan-400 hover:underline text-sm">Git</Link>
        <Link to={`/project/${projectId}/context`} className="text-cyan-400 hover:underline text-sm">Context</Link>
        <Link to={`/project/${projectId}/architecture`} className="text-cyan-400 hover:underline text-sm">Architecture</Link>
        <Link to={`/project/${projectId}/build-plan`} className="text-cyan-400 hover:underline text-sm">Build Plan</Link>
      </div>

      {/* Delete */}
      <div className="border-t border-gray-800 pt-4 mt-8">
        <button onClick={() => {
          if (window.confirm(`Delete project "${project.name}"? This cannot be undone.`)) {
            fetch(`/api/projects/${projectId}`, { method: 'DELETE' })
              .then(() => navigate('/'))
              .catch(err => alert('Failed: ' + err.message))
          }
        }} className="flex items-center gap-1.5 text-red-400 hover:text-red-300 text-sm transition-colors">
          <Trash2 className="w-4 h-4" />
          Delete Project
        </button>
      </div>

      {/* ═══ Checkpoint Modal ═══ */}
      {showCheckpoint && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
              <div>
                <h2 className="text-lg font-semibold text-gray-200">Checkpoint — Build Progress</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  {steps.length > 0
                    ? `${mergedCount}/${steps.length} merged · ${Object.values(stepStatuses).filter(s => s === 'tested' || s === 'ready_for_merge').length} ready`
                    : 'Generate a Build Plan first to track step progress'}
                </p>
              </div>
              <button onClick={() => setShowCheckpoint(false)} className="text-gray-500 hover:text-gray-200">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Steps list */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
              {steps.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <p className="text-sm">No build plan found.</p>
                  <Link to={`/project/${projectId}/build-plan`} className="text-cyan-400 hover:underline text-sm mt-2 inline-block">
                    Generate Build Plan →
                  </Link>
                </div>
              ) : (
                steps.map((step, i) => {
                  const currentStatus = stepStatuses[step.id] || step.status || 'not_started'
                  return (
                    <div key={step.id} className="bg-gray-950 border border-gray-800 rounded-lg p-3 flex items-center gap-3">
                      <div className="w-6 h-6 rounded-full bg-gray-800 flex items-center justify-center text-xs text-gray-500 font-bold flex-shrink-0">
                        {i + 1}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-200 truncate">{step.title}</div>
                        <div className="text-xs text-gray-600">{step.context_tokens?.toLocaleString() || '?'} tokens</div>
                      </div>
                      <select
                        value={currentStatus}
                        onChange={(e) => handleStepStatusChange(step.id, e.target.value)}
                        className={`text-xs px-2 py-1.5 rounded-lg border appearance-none cursor-pointer ${
                          (STEP_STATUSES.find(s => s.value === currentStatus) || STEP_STATUSES[0]).color
                        }`}
                      >
                        {STEP_STATUSES.map(ss => (
                          <option key={ss.value} value={ss.value}>{ss.label}</option>
                        ))}
                      </select>
                    </div>
                  )
                })
              )}

              {/* Progress bar */}
              {steps.length > 0 && (
                <div className="bg-gray-950 border border-gray-800 rounded-lg p-3 mt-3">
                  <div className="flex items-center justify-between text-xs text-gray-500 mb-1.5">
                    <span>Overall Progress</span>
                    <span className="font-mono">{mergedCount}/{steps.length} merged</span>
                  </div>
                  <div className="h-2 bg-gray-800 rounded-full overflow-hidden flex">
                    {['merged', 'ready_for_merge', 'tested', 'in_progress'].map(status => {
                      const count = Object.values(stepStatuses).filter(s => s === status).length
                      if (count === 0) return null
                      const colors = { merged: 'bg-green-500', ready_for_merge: 'bg-amber-500', tested: 'bg-cyan-500', in_progress: 'bg-blue-500' }
                      return <div key={status} className={`${colors[status]} h-full first:rounded-l-full last:rounded-r-full`} style={{ width: `${(count / steps.length) * 100}%` }} />
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-gray-800 flex items-center justify-between">
              <div className="text-xs text-gray-500">
                {checkpointMsg && <span className={checkpointMsg.startsWith('✓') ? 'text-green-400' : 'text-red-400'}>{checkpointMsg}</span>}
              </div>
              <div className="flex gap-2">
                <button onClick={() => setShowCheckpoint(false)} className="text-sm text-gray-400 hover:text-gray-200 border border-gray-700 rounded-lg px-4 py-2">
                  Cancel
                </button>
                <button
                  onClick={handleCheckpointCommit}
                  disabled={checkpointSaving || steps.length === 0}
                  className="flex items-center gap-2 bg-amber-700 hover:bg-amber-600 disabled:bg-gray-700 text-white px-5 py-2 rounded-lg text-sm font-medium"
                >
                  {checkpointSaving ? <><Loader className="w-4 h-4 animate-spin" /> Saving...</> : <><Save className="w-4 h-4" /> Checkpoint & Commit</>}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
