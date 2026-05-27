import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Play, Save, GitBranch, Trash2, CheckCircle, Loader, X, Circle, Clock, GitFork, GitCommitHorizontal, Activity, XCircle } from 'lucide-react'

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

const RUN_STATUSES = [
  { value: 'not_started', label: 'Not Started', icon: Circle, color: 'text-gray-500 bg-gray-800' },
  { value: 'in_progress', label: 'In Progress', icon: Clock, color: 'text-blue-300 bg-blue-900/30' },
  { value: 'tested', label: 'Tested', icon: CheckCircle, color: 'text-cyan-300 bg-cyan-900/30' },
  { value: 'ready_for_merge', label: 'Ready for Merge', icon: GitFork, color: 'text-amber-300 bg-amber-900/30' },
  { value: 'merged', label: 'Merged/Pushed', icon: GitCommitHorizontal, color: 'text-green-300 bg-green-900/30' },
  { value: 'starting', label: 'Starting', icon: Loader, color: 'text-blue-300 bg-blue-900/30' },
  { value: 'running', label: 'Running', icon: Loader, color: 'text-blue-300 bg-blue-900/30' },
  { value: 'completed', label: 'Completed', icon: CheckCircle, color: 'text-green-300 bg-green-900/30' },
  { value: 'failed', label: 'Failed', icon: XCircle, color: 'text-red-300 bg-red-900/30' },
]

function RunStatusBadge({ status }) {
  const cfg = RUN_STATUSES.find(s => s.value === status) || RUN_STATUSES[0]
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full ${cfg.color}`}>
      {status === 'running' || status === 'starting' ? <Loader className="w-2.5 h-2.5 animate-spin" /> : null}
      {cfg.label}
    </span>
  )
}

export default function ProjectDetail() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [running, setRunning] = useState(false)
  const [taskId, setTaskId] = useState(null)
  const [showCheckpoint, setShowCheckpoint] = useState(false)
  const [checkpointSaving, setCheckpointSaving] = useState(false)
  const [checkpointMsg, setCheckpointMsg] = useState('')
  const [stepStatuses, setStepStatuses] = useState({})
  const [checkpointSteps, setCheckpointSteps] = useState([])
  const [testingSteps, setTestingSteps] = useState({})  // stepId → true while testing

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

  // Periodically check runs for stalls, completions, and save logs
  useEffect(() => {
    const interval = setInterval(() => {
      fetch(`/api/projects/${projectId}/build-plan/check-runs`, { method: 'POST' })
        .catch(() => {})  // silently fail — not critical
    }, 10000)  // every 10 seconds
    return () => clearInterval(interval)
  }, [projectId])

  // Auto-refresh checkpoint modal while open
  useEffect(() => {
    if (!showCheckpoint) return
    const interval = setInterval(() => {
      openCheckpoint()
    }, 8000)  // refresh every 8 seconds while modal is open
    return () => clearInterval(interval)
  }, [showCheckpoint, projectId])

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
    setStepStatuses({})
    try {
      // Fetch build plan steps + runs in parallel
      const [bpRes, runsRes] = await Promise.all([
        fetch(`/api/projects/${projectId}/build-plan`),
        fetch(`/api/projects/${projectId}/build-plan/runs`),
      ])
      // Build run lookup by ID for FK resolution
      let runsById = {}
      if (runsRes.ok) {
        const runsData = await runsRes.json()
        ;(runsData.runs || []).forEach(r => { runsById[r.id] = r })
      }
      if (bpRes.ok) {
        const data = await bpRes.json()
        if (data.exists && data.steps) {
          setCheckpointSteps(data.steps)
          const statuses = {}
          data.steps.forEach(s => {
            const storedStatus = s.status || 'not_started'
            let resolvedStatus = storedStatus

            // Primary: use FK link (latest_run_id) from DB if available
            if (s.latest_run_id && runsById[s.latest_run_id]) {
              const run = runsById[s.latest_run_id]
              if (run.status === 'running' || run.status === 'starting') {
                resolvedStatus = 'in_progress'
              } else if (run.status === 'completed') {
                resolvedStatus = 'completed'
              } else if (run.status === 'failed') {
                resolvedStatus = 'failed'
              }
            }
            // Secondary: use _latest_run_status from DB query if no FK match
            else if (s._latest_run_status) {
              if (s._latest_run_status === 'running' || s._latest_run_status === 'starting') {
                resolvedStatus = 'in_progress'
              } else if (s._latest_run_status === 'completed') {
                resolvedStatus = 'completed'
              } else if (s._latest_run_status === 'failed') {
                resolvedStatus = 'failed'
              }
            }
            // Tertiary: if stored says in_progress but no run backs it, demote
            else if (storedStatus === 'in_progress') {
              resolvedStatus = 'not_started'
            }

            statuses[s.id] = resolvedStatus
          })
          setStepStatuses(statuses)
        }
      }
    } catch (e) {}
  }

  async function handleTestStep(stepId) {
    setTestingSteps(prev => ({ ...prev, [stepId]: true }))
    try {
      // Mark as tested in build-steps.json
      await fetch(`/api/projects/${projectId}/build-plan/step/${stepId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'tested' }),
      })
      setStepStatuses(prev => ({ ...prev, [stepId]: 'tested' }))
    } catch (e) {
      console.error('Test failed:', e)
    }
    setTestingSteps(prev => ({ ...prev, [stepId]: false }))
  }

  async function handleStepStatusChange(stepId, newStatus) {
    setStepStatuses(prev => ({ ...prev, [stepId]: newStatus }))
    try {
      await fetch(`/api/projects/${projectId}/build-plan/step/${stepId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
    } catch (e) {}
  }

  async function handleCheckpointCommit() {
    setCheckpointSaving(true); setCheckpointMsg('')
    try {
      const res = await fetch(`/api/projects/${projectId}/checkpoint`, { method: 'POST' })
      if (!res.ok) throw new Error('Checkpoint failed')
      setCheckpointMsg('✓ Checkpoint saved!')
      setTimeout(() => { setShowCheckpoint(false); refetch() }, 2000)
    } catch (err) { setCheckpointMsg(`Error: ${err.message}`) }
    finally { setCheckpointSaving(false) }
  }

  if (isLoading) return <div className="text-gray-400 py-10">Loading...</div>

  const project = projectData?.project
  if (!project) {
    return <div className="text-center py-16 text-gray-500">
      <p>Project not found.</p>
      <Link to="/" className="text-cyan-400 hover:underline text-sm mt-2 inline-block">Back to Home</Link>
    </div>
  }

  const phaseProgress = memoryData?.phase_progress || {}
  const steps = checkpointSteps
  const completedCount = Object.values(stepStatuses).filter(s => s === 'completed' || s === 'merged').length
  const buildingCount = Object.values(stepStatuses).filter(s => s === 'in_progress').length
  const failedCount = Object.values(stepStatuses).filter(s => s === 'failed').length
  const pendingCount = Object.values(stepStatuses).filter(s => s === 'not_started').length
  const totalBuildSteps = steps.length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/" className="text-gray-400 hover:text-gray-200"><ArrowLeft className="w-5 h-5" /></Link>
          <div>
            <h1 className="text-2xl font-bold">{project.name}</h1>
            <div className="text-sm text-gray-400 flex items-center gap-2">
              <GitBranch className="w-3 h-3" />
              {project.git_branch}
              {project.git_uncommitted_count > 0 && <span className="text-yellow-400">({project.git_uncommitted_count} uncommitted)</span>}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={handleRun} disabled={running}
            className="flex items-center gap-1.5 bg-green-700 hover:bg-green-600 disabled:bg-gray-700 text-white text-sm px-3 py-1.5 rounded transition-colors">
            <Play className="w-4 h-4" />{running ? 'Running...' : 'Run'}
          </button>
          <button onClick={openCheckpoint}
            className="flex items-center gap-1.5 bg-amber-700 hover:bg-amber-600 text-white text-sm px-3 py-1.5 rounded transition-colors">
            <Save className="w-4 h-4" />Checkpoint
          </button>
        </div>
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-sm text-gray-400">Status</div>
          <div className="text-lg font-semibold mt-1 capitalize">
            {project.status}
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-sm text-gray-400">Build Steps</div>
          <div className="text-lg font-semibold mt-1">
            {totalBuildSteps > 0 ? `${completedCount}/${totalBuildSteps} done` : '—'}
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
      <div className="flex gap-3 flex-wrap">
        <Link to={`/project/${projectId}/sessions`} className="text-cyan-400 hover:underline text-sm">Sessions</Link>
        <Link to={`/project/${projectId}/memory`} className="text-cyan-400 hover:underline text-sm">Memory</Link>
        <Link to={`/project/${projectId}/git`} className="text-cyan-400 hover:underline text-sm">Git</Link>
        <Link to={`/project/${projectId}/context`} className="text-cyan-400 hover:underline text-sm">Context</Link>
        <Link to={`/project/${projectId}/architecture`} className="text-cyan-400 hover:underline text-sm">Architecture</Link>
        <Link to={`/project/${projectId}/build-plan`} className="text-cyan-400 hover:underline text-sm">Build Plan</Link>
        <Link to={`/project/${projectId}/analytics`} className="text-cyan-400 hover:underline text-sm">Analytics</Link>
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
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
              <div>
                <h2 className="text-lg font-semibold text-gray-200">Checkpoint — Build Steps</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  {steps.length > 0
                    ? `${pendingCount} pending · ${buildingCount} running · ${completedCount} completed${failedCount > 0 ? ` · ${failedCount} failed` : ''}`
                    : 'Generate a Build Plan first'}
                </p>
              </div>
              <button onClick={() => setShowCheckpoint(false)} className="text-gray-500 hover:text-gray-200"><X className="w-5 h-5" /></button>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
              {steps.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <p className="text-sm">No build plan yet.</p>
                  <Link to={`/project/${projectId}/build-plan`} className="text-cyan-400 hover:underline text-sm mt-2 inline-block">Generate Build Plan →</Link>
                </div>
              ) : (
                steps.map((step, i) => {
                  const currentStatus = stepStatuses[step.id] || step.status || 'not_started'
                  const isCurrentlyRunning = currentStatus === 'in_progress'
                  const isFailed = currentStatus === 'failed'
                  const isCompleted = currentStatus === 'completed'
                  const isTested = currentStatus === 'tested'
                  const isTesting = testingSteps[step.id]
                  return (
                    <div key={step.id} className={`border rounded-lg p-3 flex items-center gap-3 ${isFailed ? 'bg-red-950/20 border-red-800/60' : isCurrentlyRunning ? 'bg-blue-950/20 border-blue-800/60' : isTested ? 'bg-cyan-950/20 border-cyan-800/50' : isCompleted ? 'bg-green-950/10 border-green-800/40' : 'bg-gray-950 border-gray-800'}`}>
                      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${isFailed ? 'bg-red-900/50 text-red-300' : isCurrentlyRunning ? 'bg-blue-900/50 text-blue-300' : isTested ? 'bg-cyan-900/50 text-cyan-300' : isCompleted ? 'bg-green-900/50 text-green-300' : 'bg-gray-800 text-gray-500'}`}>
                        {isFailed ? '!' : isCurrentlyRunning ? <Loader className="w-3.5 h-3.5 animate-spin" /> : isTested ? <CheckCircle className="w-3.5 h-3.5" /> : isCompleted ? <CheckCircle className="w-3.5 h-3.5" /> : i + 1}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className={`text-sm font-medium truncate ${isCurrentlyRunning ? 'text-blue-200' : isFailed ? 'text-red-200' : isTested ? 'text-cyan-200' : isCompleted ? 'text-green-200' : 'text-gray-200'}`}>{step.title}</div>
                        <div className="text-xs text-gray-600">{step.context_tokens?.toLocaleString() || '?'} tokens</div>
                      </div>
                      <div className="flex items-center gap-2">
                        {isCompleted && !isTested && (
                          <button onClick={() => handleTestStep(step.id)} disabled={isTesting}
                            className="flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-green-700 bg-green-900/20 text-green-300 hover:bg-green-800/30 disabled:opacity-50">
                            {isTesting ? <><Loader className="w-3 h-3 animate-spin" /> Testing...</> : <><Play className="w-3 h-3" /> Test</>}
                          </button>
                        )}
                        <select value={currentStatus} onChange={(e) => handleStepStatusChange(step.id, e.target.value)}
                          className={`text-xs px-2 py-1.5 rounded-lg border appearance-none cursor-pointer ${(RUN_STATUSES.find(s => s.value === currentStatus) || RUN_STATUSES[0]).color}`}>
                          {RUN_STATUSES.map(ss => <option key={ss.value} value={ss.value}>{ss.label}</option>)}
                        </select>
                      </div>
                    </div>
                  )
                })
              )}
              {steps.length > 0 && (
                <div className="bg-gray-950 border border-gray-800 rounded-lg p-3 mt-3">
                  <div className="flex items-center justify-between text-xs text-gray-500 mb-1.5">
                    <span>{pendingCount} pending · {buildingCount} running · {completedCount} completed{failedCount > 0 ? ` · ${failedCount} failed` : ''}</span>
                    <span className="font-mono">{completedCount}/{steps.length}</span>
                  </div>
                  <div className="h-2 bg-gray-800 rounded-full overflow-hidden flex">
                    {['completed', 'ready_for_merge', 'tested', 'in_progress', 'failed', 'merged'].map(status => {
                      const count = Object.values(stepStatuses).filter(s => s === status).length
                      if (count === 0) return null
                      const colors = { completed: 'bg-green-500', merged: 'bg-green-500', ready_for_merge: 'bg-amber-500', tested: 'bg-cyan-500', in_progress: 'bg-blue-500', failed: 'bg-red-500' }
                      return <div key={status} className={`${colors[status]} h-full first:rounded-l-full last:rounded-r-full`} style={{ width: `${(count / steps.length) * 100}%` }} />
                    })}
                  </div>
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-gray-800 flex items-center justify-between">
              <div className="text-xs text-gray-500">
                {checkpointMsg && <span className={checkpointMsg.startsWith('✓') ? 'text-green-400' : 'text-red-400'}>{checkpointMsg}</span>}
              </div>
              <div className="flex gap-2">
                <button onClick={() => setShowCheckpoint(false)} className="text-sm text-gray-400 hover:text-gray-200 border border-gray-700 rounded-lg px-4 py-2">Cancel</button>
                <button onClick={handleCheckpointCommit} disabled={checkpointSaving || steps.length === 0}
                  className="flex items-center gap-2 bg-amber-700 hover:bg-amber-600 disabled:bg-gray-700 text-white px-5 py-2 rounded-lg text-sm font-medium">
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


