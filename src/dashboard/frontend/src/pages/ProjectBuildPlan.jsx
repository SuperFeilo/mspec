import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, Check, Loader, FileText, ChevronDown, ChevronRight,
  RefreshCw, CheckCircle, Clock, Play, Circle,
  Zap, Target, GitBranch, GitFork, GitCommitHorizontal, BookOpen,
} from 'lucide-react'

async function fetchBuildPlan(projectId) {
  const r = await fetch(`/api/projects/${projectId}/build-plan`)
  if (!r.ok) throw new Error('Failed')
  return r.json()
}

async function generateBuildPlan(projectId) {
  const r = await fetch(`/api/projects/${projectId}/build-plan`, { method: 'POST' })
  if (!r.ok) {
    const err = await r.json()
    throw new Error(err.detail || 'Failed to generate')
  }
  return r.json()
}

async function updateStepStatus(projectId, stepId, status) {
  const r = await fetch(`/api/projects/${projectId}/build-plan/step/${stepId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
  if (!r.ok) throw new Error('Failed to update')
  return r.json()
}

const STEP_STATUSES = [
  { value: 'not_started', label: 'Not Started', icon: Circle, color: 'text-gray-500 bg-gray-800 border-gray-700' },
  { value: 'in_progress', label: 'In Progress', icon: Play, color: 'text-blue-300 bg-blue-900/30 border-blue-800/50' },
  { value: 'tested', label: 'Tested', icon: CheckCircle, color: 'text-cyan-300 bg-cyan-900/30 border-cyan-800/50' },
  { value: 'ready_for_merge', label: 'Ready for Merge', icon: GitFork, color: 'text-amber-300 bg-amber-900/30 border-amber-800/50' },
  { value: 'merged', label: 'Merged/Pushed', icon: GitCommitHorizontal, color: 'text-green-300 bg-green-900/30 border-green-800/50' },
]

function StatusBadge({ status }) {
  const cfg = STEP_STATUSES.find(s => s.value === status)
  if (!cfg) return <span className="text-xs text-gray-500">Unknown</span>
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${cfg.color}`}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  )
}

function BuildStepCard({ step, index, projectId, onRefresh }) {
  const [expanded, setExpanded] = useState(false)
  const [updating, setUpdating] = useState(false)

  async function handleStatusChange(newStatus) {
    setUpdating(true)
    try {
      await updateStepStatus(projectId, step.id, newStatus)
      onRefresh()
    } catch (err) {
      alert(err.message)
    } finally {
      setUpdating(false)
    }
  }

  const isDone = step.status === 'done'
  const isInProgress = step.status === 'in_progress'

  return (
    <div className={`bg-gray-900 border rounded-xl overflow-hidden transition-all ${
      isDone ? 'border-green-800/50' : isInProgress ? 'border-blue-800/50' : 'border-gray-800'
    }`}>
      {/* Header - clickable */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-5 py-3.5 text-left hover:bg-gray-800/30 transition-colors"
      >
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold ${
          isDone ? 'bg-green-900/50 text-green-300' :
          isInProgress ? 'bg-blue-900/50 text-blue-300' :
          'bg-gray-800 text-gray-500'
        }`}>
          {isDone ? <Check className="w-4 h-4" /> : index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-gray-200">{step.title}</span>
            <StatusBadge status={step.status} />
          </div>
          <div className="text-xs text-gray-500 mt-0.5">~{step.context_tokens?.toLocaleString() || '?'} tokens</div>
        </div>
        <div className="flex items-center gap-1">
          <select
            value={step.status}
            onChange={(e) => { e.stopPropagation(); handleStatusChange(e.target.value) }}
            onClick={(e) => e.stopPropagation()}
            className={`text-xs px-2 py-1 rounded border ${
              (STEP_STATUSES.find(s => s.value === step.status) || STEP_STATUSES[0]).color
            }`}
          >
            {STEP_STATUSES.map(ss => (
              <option key={ss.value} value={ss.value}>{ss.label}</option>
            ))}
          </select>
          {expanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
        </div>
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="px-5 pb-4 pt-1 border-t border-gray-800 space-y-4">
          {/* Context */}
          <div>
            <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1.5">
              <BookOpen className="w-3.5 h-3.5" />
              Context
            </div>
            <pre className="text-xs text-gray-300 bg-gray-950 rounded-lg p-3 border border-gray-800 whitespace-pre-wrap font-sans max-h-48 overflow-y-auto">
              {step.context}
            </pre>
          </div>

          {/* Contract */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="bg-gray-950 border border-gray-800 rounded-lg p-3">
              <div className="text-[10px] text-gray-500 uppercase mb-1">Inputs</div>
              <div className="text-xs text-gray-300">{step.contract?.inputs || '—'}</div>
            </div>
            <div className="bg-gray-950 border border-gray-800 rounded-lg p-3">
              <div className="text-[10px] text-gray-500 uppercase mb-1">Outputs</div>
              <div className="text-xs text-gray-300">{step.contract?.outputs || '—'}</div>
            </div>
          </div>

          {/* Test scenarios */}
          <div>
            <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1.5">
              <Target className="w-3.5 h-3.5" />
              Test Scenarios
            </div>
            <div className="space-y-1">
              {step.tests?.map((t, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-gray-400">
                  <Circle className="w-3 h-3 text-gray-600 mt-0.5 flex-shrink-0" />
                  {t}
                </div>
              ))}
            </div>
          </div>

          {/* Dependencies */}
          {step.dependencies?.length > 0 && (
            <div className="text-xs text-gray-500">
              <span className="text-gray-600">Depends on: </span>
              {step.dependencies.map((d, i) => (
                <span key={d} className="text-gray-400">
                  {i > 0 && ', '}{d}
                </span>
              ))}
            </div>
          )}

          {/* Status selector */}
          <div className="flex items-center gap-2 pt-1">
            <span className="text-xs text-gray-500">Status:</span>
            <select
              value={step.status}
              onChange={(e) => handleStatusChange(e.target.value)}
              disabled={updating}
              className={`text-xs px-2 py-1 rounded border ${
                (STEP_STATUSES.find(s => s.value === step.status) || STEP_STATUSES[0]).color
              }`}
            >
              {STEP_STATUSES.map(ss => (
                <option key={ss.value} value={ss.value}>{ss.label}</option>
              ))}
            </select>
            {updating && <Loader className="w-3 h-3 animate-spin text-gray-500" />}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ProjectBuildPlan() {
  const { projectId } = useParams()
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['build-plan', projectId],
    queryFn: () => fetchBuildPlan(projectId),
    refetchInterval: 3000,
  })

  async function handleGenerate() {
    setGenerating(true)
    setGenError(null)
    try {
      await generateBuildPlan(projectId)
      refetch()
    } catch (err) {
      setGenError(err.message)
    } finally {
      setGenerating(false)
    }
  }

  if (isLoading) {
    return <div className="flex items-center gap-2 text-gray-400 py-16 justify-center">
      <Loader className="w-5 h-5 animate-spin" /> Loading build plan...
    </div>
  }

  // ── No build plan yet ──
  if (!data?.exists) {
    return (
      <div className="space-y-6 max-w-3xl mx-auto">
        <div className="flex items-center gap-3">
          <Link to={`/project/${projectId}`}><ArrowLeft className="w-5 h-5 text-gray-400 hover:text-gray-200" /></Link>
          <h1 className="text-2xl font-bold">Build Plan</h1>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center space-y-5">
          <div className="flex justify-center">
            <div className="p-4 bg-cyan-950/20 rounded-full">
              <Zap className="w-10 h-10 text-cyan-400" />
            </div>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-200 mb-2">Break Down the Architecture</h2>
            <p className="text-sm text-gray-400 max-w-md mx-auto">
              Generate a step-by-step build plan from your confirmed architecture.
              Each step is a self-contained unit with context, contract, and tests — all under 50k tokens.
            </p>
          </div>
          {genError && <div className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded p-3">{genError}</div>}
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 bg-cyan-700 hover:bg-cyan-600 disabled:bg-gray-700 text-white px-6 py-2.5 rounded-lg text-sm font-medium mx-auto"
          >
            {generating ? <><Loader className="w-4 h-4 animate-spin" /> Generating...</> : <><Zap className="w-4 h-4" /> Generate Build Plan</>}
          </button>
          <div className="text-xs text-gray-600">
            Requires a confirmed architecture (mspec.md). Go to <Link to={`/project/${projectId}/context`} className="text-cyan-400 hover:underline">Context</Link> first if you haven't.
          </div>
        </div>
      </div>
    )
  }

  const steps = data.steps || []
  const progressPct = data.progress_pct || 0

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to={`/project/${projectId}`}><ArrowLeft className="w-5 h-5 text-gray-400 hover:text-gray-200" /></Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">Build Plan</h1>
            <span className="text-xs bg-green-900/40 text-green-300 px-2 py-0.5 rounded-full border border-green-800/50">
              {data.total} steps
            </span>
          </div>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 border border-gray-700 rounded px-3 py-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${generating ? 'animate-spin' : ''}`} />
          Regenerate
        </button>
      </div>

      {/* Progress */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-gray-400">
            <GitBranch className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Progress</span>
          </div>
          <span className="text-sm font-mono text-gray-300">
            {data.done}/{data.total} complete
            {data.in_progress > 0 && <span className="text-blue-400 ml-2">({data.in_progress} building)</span>}
          </span>
        </div>
        <div className="h-2.5 bg-gray-800 rounded-full overflow-hidden">
          <div className="h-full bg-green-500 rounded-full transition-all duration-500" style={{ width: `${progressPct}%` }} />
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-3">
        {steps.map((step, i) => (
          <BuildStepCard
            key={step.id}
            step={step}
            index={i}
            projectId={projectId}
            onRefresh={() => refetch()}
          />
        ))}
      </div>

      {/* Stub files - show when build plan exists */}
      {data.total > 0 && <StubGenerator projectId={projectId} />}

      {/* Bottom actions */}
      <div className="flex justify-center gap-4 pt-2">
        <Link
          to={`/project/${projectId}/architecture`}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-200 border border-gray-700 rounded-lg px-4 py-2"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Architecture
        </Link>
      </div>
    </div>
  )
}

// ─── Stub Generator Component ───────────────────────────────────

function StubGenerator({ projectId }) {
  const [generating, setGenerating] = useState(false)
  const [stubs, setStubs] = useState(null)
  const [error, setError] = useState(null)

  async function handleGenerate() {
    setGenerating(true)
    setError(null)
    try {
      const res = await fetch(`/api/projects/${projectId}/build-plan/stubs`, { method: 'POST' })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed')
      }
      const data = await res.json()
      setStubs(data.stubs)
    } catch (err) {
      setError(err.message)
    } finally {
      setGenerating(false)
    }
  }

  // Load existing stubs
  const { data: existingStubs } = useQuery({
    queryKey: ['build-stubs', projectId],
    queryFn: async () => {
      const res = await fetch(`/api/projects/${projectId}/build-plan/stubs`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const hasStubs = existingStubs?.exists && existingStubs?.stubs?.length > 0
  const stubList = stubs || (hasStubs ? existingStubs.stubs : null)

  return (
    <div className="border border-green-800 rounded-xl bg-green-950/10 p-6 space-y-4">
      <div className="flex items-center gap-2 text-green-400">
        <Check className="w-5 h-5" />
        <span className="text-sm font-semibold">All Build Steps Complete</span>
      </div>
      <p className="text-sm text-gray-400">
        All build steps are marked done. Generate stub files — each is a self-contained markdown file with
        detailed context, coding architecture, implementation checklist, and test scenarios.
      </p>

      <div className="flex items-center gap-3">
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="flex items-center gap-2 bg-green-700 hover:bg-green-600 disabled:bg-gray-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium"
        >
          {generating ? <><Loader className="w-4 h-4 animate-spin" /> Generating...</> : <><Zap className="w-4 h-4" /> {stubList ? 'Regenerate' : 'Generate'} Stub Files</>}
        </button>
        {stubList && (
          <span className="text-xs text-green-400">{stubList.length} files already generated</span>
        )}
      </div>

      {error && <div className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded p-3">{error}</div>}

      {stubList && (
        <div className="space-y-2">
          <div className="text-xs text-green-400">{stubList.length} stub files generated</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {stubList.map((s) => (
              <div key={s.id} className="bg-gray-950 border border-green-800/30 rounded-lg p-3 flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium text-gray-200">{s.id}: {s.title}</div>
                  <div className="text-xs text-gray-500">~{s.tokens?.toLocaleString() || '?'} tokens · {s.path}</div>
                </div>
                <Check className="w-4 h-4 text-green-500 flex-shrink-0" />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
