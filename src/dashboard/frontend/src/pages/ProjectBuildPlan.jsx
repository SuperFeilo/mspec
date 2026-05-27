import { useState, useMemo, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, Check, Loader, FileText, ChevronDown, ChevronRight,
  RefreshCw, CheckCircle, Clock, Play, Circle,
  Zap, Target, GitBranch, GitFork, GitCommitHorizontal, BookOpen,
  AlertTriangle, XCircle, Terminal, Activity, Layers,
} from 'lucide-react'

async function fetchBuildPlan(projectId) {
  const r = await fetch(`/api/projects/${projectId}/build-plan`)
  if (!r.ok) throw new Error('Failed')
  return r.json()
}

const STEP_STATUSES = [
  { value: 'not_started', label: 'Not Started', icon: Circle, color: 'text-gray-500 bg-gray-800 border-gray-700' },
  { value: 'in_progress', label: 'In Progress', icon: Clock, color: 'text-blue-300 bg-blue-900/30 border-blue-800/50' },
  { value: 'completed', label: 'Completed', icon: CheckCircle, color: 'text-green-300 bg-green-900/30 border-green-800/50' },
  { value: 'failed', label: 'Failed', icon: XCircle, color: 'text-red-300 bg-red-900/30 border-red-800/50' },
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

const STEPS = [
  { id: 'goals', label: 'Goals & Requirements', icon: Target },
  { id: 'infer', label: 'Infer Tech Choices', icon: Zap },
  { id: 'decide', label: 'Critical Choices', icon: Layers },
  { id: 'finish', label: 'Review & Confirm', icon: Check },
]

// ─── Main Component ────────────────────────────────────────────

export default function ProjectBuildPlan() {
  const { projectId } = useParams()
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState(null)
  // Shared state between BlueprintRunner and ReasonixRunsPanel
  const [runRefreshKey, setRunRefreshKey] = useState(0)
  const [latestRunId, setLatestRunId] = useState(null)

  function handleRunStarted(runId) {
    setLatestRunId(runId)
    setRunRefreshKey(k => k + 1)
  }

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['build-plan', projectId],
    queryFn: () => fetchBuildPlan(projectId),
    refetchInterval: 3000,
  })

  // Periodically sync runs to build steps (stall detection + completion)
  useEffect(() => {
    const interval = setInterval(() => {
      fetch(`/api/projects/${projectId}/build-plan/check-runs`, { method: 'POST' })
        .catch(() => {})
    }, 15000)  // every 15 seconds on Build Plan page
    return () => clearInterval(interval)
  }, [projectId])

  async function handleGenerate() {
    setGenerating(true)
    setGenError(null)
    try {
      await fetch(`/api/projects/${projectId}/build-plan`, { method: 'POST' })
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

  if (!data?.exists) {
    return (
      <div className="space-y-6 max-w-3xl mx-auto">
        <div className="flex items-center gap-3">
          <Link to={`/project/${projectId}`}><ArrowLeft className="w-5 h-5 text-gray-400 hover:text-gray-200" /></Link>
          <h1 className="text-2xl font-bold">Build Plan</h1>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center space-y-5">
          <div className="flex justify-center"><div className="p-4 bg-cyan-950/20 rounded-full"><Zap className="w-10 h-10 text-cyan-400" /></div></div>
          <div>
            <h2 className="text-lg font-semibold text-gray-200 mb-2">Break Down the Architecture</h2>
            <p className="text-sm text-gray-400 max-w-md mx-auto">Generate a step-by-step build plan from your confirmed architecture.</p>
          </div>
          {genError && <div className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded p-3">{genError}</div>}
          <button onClick={handleGenerate} disabled={generating}
            className="flex items-center gap-2 bg-cyan-700 hover:bg-cyan-600 disabled:bg-gray-700 text-white px-6 py-2.5 rounded-lg text-sm font-medium mx-auto">
            {generating ? <><Loader className="w-4 h-4 animate-spin" /> Generating...</> : <><Zap className="w-4 h-4" /> Generate Build Plan</>}
          </button>
          <div className="text-xs text-gray-600">
            Requires a confirmed architecture (mspec.md). Go to <Link to={`/project/${projectId}/context`} className="text-cyan-400 hover:underline">Context</Link> first.
          </div>
        </div>
      </div>
    )
  }

  const steps = data.steps || []
  const progressPct = data.progress_pct || 0

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-3">
        <Link to={`/project/${projectId}`}><ArrowLeft className="w-5 h-5 text-gray-400 hover:text-gray-200" /></Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">Build Plan</h1>
            <span className="text-xs bg-green-900/40 text-green-300 px-2 py-0.5 rounded-full border border-green-800/50">{data.total} steps</span>
          </div>
        </div>
        <button onClick={handleGenerate} disabled={generating}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 border border-gray-700 rounded px-3 py-1.5">
          <RefreshCw className={`w-3.5 h-3.5 ${generating ? 'animate-spin' : ''}`} /> Regenerate
        </button>
      </div>

      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-gray-400">
            <GitBranch className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Progress</span>
          </div>
          <span className="text-sm font-mono text-gray-300">{data.done}/{data.total} complete{data.in_progress > 0 && <span className="text-blue-400 ml-2">({data.in_progress} building)</span>}</span>
        </div>
        <div className="h-2.5 bg-gray-800 rounded-full overflow-hidden">
          <div className="h-full bg-green-500 rounded-full transition-all duration-500" style={{ width: `${progressPct}%` }} />
        </div>
      </div>

      <div className="space-y-3">
        {steps.map((step, i) => (
          <BuildStepCard key={step.id} step={step} index={i} projectId={projectId} onRefresh={() => refetch()} />
        ))}
      </div>

      {/* Blueprint Runner — always visible */}
      <BlueprintRunner projectId={projectId} onRunStarted={handleRunStarted} />

      {/* Reasonix Runs Panel — sorted by time, milestone status at top */}
      <ReasonixRunsPanel projectId={projectId} refreshKey={runRefreshKey} latestRunId={latestRunId} />

      <div className="flex justify-center gap-4 pt-2">
        <Link to={`/project/${projectId}/architecture`} className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-200 border border-gray-700 rounded-lg px-4 py-2">
          <ArrowLeft className="w-4 h-4" /> Back to Architecture
        </Link>
      </div>
    </div>
  )
}

// ─── Build Step Card ───────────────────────────────────────────

function BuildStepCard({ step, index, projectId, onRefresh }) {
  const [expanded, setExpanded] = useState(false)
  const [updating, setUpdating] = useState(false)
  const isDone = step.status === 'done' || step.status === 'merged' || step.status === 'completed' || step.status === 'tested'
  const isFailed = step.status === 'failed'
  const isRunning = step.status === 'in_progress'

  async function handleStatusChange(newStatus) {
    setUpdating(true)
    try {
      await fetch(`/api/projects/${projectId}/build-plan/step/${step.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
      onRefresh()
    } catch (err) { alert(err.message) }
    finally { setUpdating(false) }
  }

  return (
    <div className={`bg-gray-900 border rounded-xl overflow-hidden ${isFailed ? 'border-red-800/50' : isDone ? 'border-green-800/50' : isRunning ? 'border-blue-800/50' : 'border-gray-800'}`}>
      <button onClick={() => setExpanded(!expanded)} className="w-full flex items-center gap-3 px-5 py-3.5 text-left hover:bg-gray-800/30 transition-colors">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold ${isFailed ? 'bg-red-900/50 text-red-300' : isDone ? 'bg-green-900/50 text-green-300' : isRunning ? 'bg-blue-900/50 text-blue-300' : 'bg-gray-800 text-gray-500'}`}>
          {isFailed ? <XCircle className="w-4 h-4" /> : isDone ? <Check className="w-4 h-4" /> : isRunning ? <Loader className="w-4 h-4 animate-spin" /> : index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-gray-200">{step.title}</span>
            <StatusBadge status={step.status} />
          </div>
          <div className="text-xs text-gray-500 mt-0.5">~{step.context_tokens?.toLocaleString() || '?'} tokens</div>
        </div>
        <select value={step.status} onChange={(e) => { e.stopPropagation(); handleStatusChange(e.target.value) }} onClick={(e) => e.stopPropagation()}
          className={`text-xs px-2 py-1 rounded border ${(STEP_STATUSES.find(s => s.value === step.status) || STEP_STATUSES[0]).color}`}>
          {STEP_STATUSES.map(ss => <option key={ss.value} value={ss.value}>{ss.label}</option>)}
        </select>
        {expanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
      </button>
      {expanded && (
        <div className="px-5 pb-4 pt-1 border-t border-gray-800 space-y-4">
          <div><div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1.5"><BookOpen className="w-3.5 h-3.5" /> Context</div>
            <pre className="text-xs text-gray-300 bg-gray-950 rounded-lg p-3 border border-gray-800 whitespace-pre-wrap font-sans max-h-48 overflow-y-auto">{step.context}</pre></div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="bg-gray-950 border border-gray-800 rounded-lg p-3"><div className="text-[10px] text-gray-500 uppercase mb-1">Inputs</div><div className="text-xs text-gray-300">{step.contract?.inputs || '—'}</div></div>
            <div className="bg-gray-950 border border-gray-800 rounded-lg p-3"><div className="text-[10px] text-gray-500 uppercase mb-1">Outputs</div><div className="text-xs text-gray-300">{step.contract?.outputs || '—'}</div></div>
          </div>
          <div><div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1.5"><Target className="w-3.5 h-3.5" /> Test Scenarios</div>
            <div className="space-y-1">{step.tests?.map((t, i) => <div key={i} className="flex items-start gap-2 text-xs text-gray-400"><Circle className="w-3 h-3 text-gray-600 mt-0.5 flex-shrink-0" />{t}</div>)}</div></div>
          <div className="flex items-center gap-2 pt-1">
            <span className="text-xs text-gray-500">Status:</span>
            <select value={step.status} onChange={(e) => handleStatusChange(e.target.value)} disabled={updating}
              className={`text-xs px-2 py-1 rounded border ${(STEP_STATUSES.find(s => s.value === step.status) || STEP_STATUSES[0]).color}`}>
              {STEP_STATUSES.map(ss => <option key={ss.value} value={ss.value}>{ss.label}</option>)}
            </select>
            {updating && <Loader className="w-3 h-3 animate-spin text-gray-500" />}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Stub Generator ────────────────────────────────────────────

function StubGenerator({ projectId }) {
  const [collapsed, setCollapsed] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(0)
  const [progressStage, setProgressStage] = useState('')
  const [stubs, setStubs] = useState(null)
  const [validation, setValidation] = useState(null)
  const [error, setError] = useState(null)

  async function handleGenerate() {
    setGenerating(true); setProgress(0); setValidation(null); setError(null)
    const stages = [
      { at: 10, label: 'Stage 1/3: Injecting project context...' },
      { at: 30, label: 'Stage 1/3: Resolving placeholders...' },
      { at: 45, label: 'Stage 2/3: Pressure testing stub files...' },
      { at: 65, label: 'Stage 2/3: Checking for stall triggers...' },
      { at: 80, label: 'Stage 3/3: Validating structure & completeness...' },
      { at: 95, label: 'Stage 3/3: Generating final recommendations...' },
    ]
    let stageIdx = 0
    const pi = setInterval(() => {
      if (stageIdx < stages.length && progress < stages[stageIdx].at) setProgress(p => Math.min(p + 2, stages[stageIdx].at))
      else if (stageIdx < stages.length - 1) { stageIdx++; setProgressStage(stages[stageIdx].label) }
    }, 200)
    try {
      const res = await fetch(`/api/projects/${projectId}/build-plan/stubs`, { method: 'POST' })
      clearInterval(pi)
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Failed') }
      const data = await res.json()
      setProgress(100); setProgressStage('Complete'); setTimeout(() => setProgressStage(''), 800)
      setStubs(data.stubs); setValidation(data.validation)
    } catch (err) { clearInterval(pi); setError(err.message); setProgress(0) }
    finally { setGenerating(false) }
  }

  const { data: existingStubs } = useQuery({ queryKey: ['build-stubs', projectId], queryFn: async () => { const res = await fetch(`/api/projects/${projectId}/build-plan/stubs`); if (!res.ok) throw new Error('Failed'); return res.json() } })
  const hasStubs = existingStubs?.exists && existingStubs?.stubs?.length > 0
  const stubList = stubs || (hasStubs ? existingStubs.stubs : null)
  const valSummary = validation?.summary

  return (
    <div className="border border-green-800 rounded-xl bg-green-950/10 p-6 space-y-4">
      <button onClick={() => setCollapsed(!collapsed)} className="flex items-center gap-2 text-green-400 w-full text-left">
        <Check className="w-5 h-5" /><span className="text-sm font-semibold">Stub Files</span>
        {collapsed ? <ChevronRight className="w-4 h-4 ml-auto" /> : <ChevronDown className="w-4 h-4 ml-auto" />}
      </button>
      {collapsed ? null : (<>
      {generating && <div className="space-y-2">
        <div className="flex items-center justify-between text-xs"><span className="text-cyan-400">{progressStage}</span><span className="text-gray-500 font-mono">{progress}%</span></div>
        <div className="h-2.5 bg-gray-800 rounded-full overflow-hidden"><div className="h-full bg-cyan-500 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} /></div>
      </div>}
      <div className="flex items-center gap-3">
        <button onClick={handleGenerate} disabled={generating}
          className="flex items-center gap-2 bg-green-700 hover:bg-green-600 disabled:bg-gray-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium">
          {generating ? <><Loader className="w-4 h-4 animate-spin" /> Generating...</> : <><Zap className="w-4 h-4" /> {stubList ? 'Regenerate' : 'Generate'} Stub Files</>}
        </button>
        {stubList && !generating && <span className="text-xs text-green-400">{stubList.length} files</span>}
      </div>
      {error && <div className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded p-3">{error}</div>}
      {valSummary && !generating && (
        <div className={`rounded-lg p-4 border ${valSummary.all_passed ? 'bg-green-950/20 border-green-800/40' : 'bg-amber-950/20 border-amber-800/40'}`}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              {valSummary.all_passed ? <CheckCircle className="w-5 h-5 text-green-400" /> : <AlertTriangle className="w-5 h-5 text-amber-400" />}
              <span className={`text-sm font-semibold ${valSummary.all_passed ? 'text-green-300' : 'text-amber-300'}`}>{valSummary.all_passed ? 'All validation checks passed' : 'Some checks need attention'}</span>
            </div>
            <span className={`text-sm font-mono font-bold ${valSummary.score >= 80 ? 'text-green-400' : 'text-amber-400'}`}>{valSummary.score}%</span>
          </div>
          <div className="h-2 bg-gray-800 rounded-full overflow-hidden"><div className={`h-full rounded-full transition-all ${valSummary.all_passed ? 'bg-green-500' : 'bg-amber-500'}`} style={{ width: `${valSummary.score}%` }} /></div>
          <div className="text-xs text-gray-500 mt-2">{valSummary.passed_checks}/{valSummary.total_checks} checks passed{!valSummary.all_passed && ' — review details below'}</div>
        </div>
      )}
      {stubList && !generating && <CodeScriptsSection projectId={projectId} stubs={stubList} validation={validation} />}
      </>)}
    </div>
  )
}

// ─── Code Scripts Section ──────────────────────────────────────

// ─── Run Button ────────────────────────────────────────────────

function RunButton({ projectId, stubName, agent }) {
  const [state, setState] = useState('idle') // idle | running | done | error
  const [msg, setMsg] = useState('')
  const [runId, setRunId] = useState(null)

  async function handleRun() {
    setState('running')
    setMsg('')
    setRunId(null)
    try {
      if (agent === 'reasonix') {
        // Use the Reasonix runner endpoint
        const res = await fetch(`/api/projects/${projectId}/reasonix-run`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stub_path: stubName }),
        })
        if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Failed') }
        const data = await res.json()
        setState('done')
        const rid = data.run?.id
        setRunId(rid)
        setMsg(`✓ Reasonix run ${rid?.slice(0,8) || ''} started — monitoring in Reasonix Runs panel`)
        setTimeout(() => setState('idle'), 5000)
      } else {
        // Original opencode flow
        const res = await fetch(`/api/projects/${projectId}/build-plan/start-run`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stub_name: stubName, agent }),
        })
        if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Failed') }
        const data = await res.json()
        setState('done')
        setMsg(`✓ Run ${data.run?.id?.slice(0,8)} started`)
        setTimeout(() => setState('idle'), 3000)
      }
    } catch (err) {
      setState('error')
      setMsg(`✗ ${err.message}`)
      setTimeout(() => setState('idle'), 4000)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={handleRun}
        disabled={state === 'running'}
        className={`flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors ${
          state === 'running' ? 'bg-blue-900/30 text-blue-300 border-blue-800 cursor-wait' :
          state === 'done' ? 'bg-green-900/30 text-green-300 border-green-800' :
          state === 'error' ? 'bg-red-900/30 text-red-300 border-red-800' :
          'text-green-400 hover:text-green-300 border-green-800 hover:bg-green-900/20'
        }`}
      >
        {state === 'running' ? <><Loader className="w-3 h-3 animate-spin" /> Starting...</> :
         state === 'done' ? <><CheckCircle className="w-3 h-3" /> Started</> :
         state === 'error' ? <><XCircle className="w-3 h-3" /> Failed</> :
         <><Play className="w-3 h-3" /> Run</>}
      </button>
      {runId && agent === 'reasonix' && (
        <span className="text-[10px] text-cyan-400">ID: {runId.slice(0,8)}</span>
      )}
      {msg && <span className={`text-[10px] ${state === 'done' ? 'text-green-400' : 'text-red-400'}`}>{msg}</span>}
    </div>
  )
}

function CodeScriptsSection({ projectId, stubs }) {
  const [generating, setGenerating] = useState(false)
  const [scripts, setScripts] = useState(null)
  const [agent, setAgent] = useState('opencode')
  const [error, setError] = useState(null)
  const [copiedId, setCopiedId] = useState(null)

  async function handleGenerate() {
    setGenerating(true); setError(null)
    try {
      const res = await fetch(`/api/projects/${projectId}/build-plan/code-scripts?agent=${agent}`, { method: 'POST' })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Failed') }
      setScripts((await res.json()).scripts)
    } catch (err) { setError(err.message) }
    finally { setGenerating(false) }
  }

  const { data: existingScripts } = useQuery({ queryKey: ['code-scripts', projectId], queryFn: async () => { const res = await fetch(`/api/projects/${projectId}/build-plan/code-scripts`); if (!res.ok) throw new Error('Failed'); return res.json() } })
  const hasScripts = existingScripts?.exists && existingScripts?.scripts?.length > 0
  const scriptList = scripts || (hasScripts ? existingScripts.scripts : null)

  return (
    <div className="border-t border-green-800/30 pt-4 mt-4 space-y-3">
      <div className="flex items-center gap-2 text-cyan-400"><Zap className="w-4 h-4" /><span className="text-sm font-semibold">Code Scripts</span></div>
      <div className="flex items-center gap-3">
        <select value={agent} onChange={(e) => setAgent(e.target.value)} className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200">
          <option value="opencode">opencode</option>
          <option value="reasonix">reasonix code</option>
        </select>
        <button onClick={handleGenerate} disabled={generating}
          className="flex items-center gap-2 bg-cyan-700 hover:bg-cyan-600 disabled:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
          {generating ? <><Loader className="w-4 h-4 animate-spin" /> Generating...</> : <><Zap className="w-4 h-4" /> {scriptList ? 'Regenerate' : 'Generate'} Scripts</>}
        </button>
        {scriptList && !generating && <span className="text-xs text-cyan-400">{scriptList.length} scripts</span>}
      </div>
      {error && <div className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded p-3">{error}</div>}
      {scriptList && !generating && (
        <div className="grid grid-cols-1 gap-2">
          {scriptList.map((s) => {
            const isCopied = copiedId === s.name
            return (
              <div key={s.name} className="bg-gray-950 border border-cyan-800/30 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Play className="w-4 h-4 text-cyan-400" />
                    <span className="text-sm font-medium text-gray-200">{s.name.replace(/-/g, ' ').replace('BP ', 'BP-')}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <RunButton projectId={projectId} stubName={s.name} agent={agent} />
                    <button onClick={() => { navigator.clipboard.writeText(s.command); setCopiedId(s.name); setTimeout(() => setCopiedId(null), 2000) }}
                      className="text-xs text-gray-500 hover:text-gray-300 border border-gray-700 rounded px-2 py-1">
                      {isCopied ? '✓ Copied!' : 'Copy'}
                    </button>
                  </div>
                </div>
                <pre className="text-xs text-green-300 bg-black/40 rounded p-2 overflow-x-auto font-mono">$ {s.command}</pre>
                <div className="flex items-center gap-3 text-[10px] text-gray-600">
                  <span>Model: {s.model || 'default'}</span><span>·</span><span>Prompt: {s.prompt_file}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── Runs Dashboard ────────────────────────────────────────────

function RunsDashboard({ projectId }) {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['runs', projectId],
    queryFn: async () => {
      const res = await fetch(`/api/projects/${projectId}/build-plan/runs`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
    refetchInterval: 3000,
  })

  const [selectedRun, setSelectedRun] = useState(null)
  const [runDetail, setRunDetail] = useState(null)

  useEffect(() => {
    if (!selectedRun) return
    fetch(`/api/projects/${projectId}/build-plan/runs/${selectedRun}`)
      .then(r => r.json())
      .then(setRunDetail)
      .catch(() => {})
  }, [selectedRun, data])

  if (!data || (!data.total && isLoading)) return null

  return (
    <div className="border border-gray-800 rounded-xl bg-gray-900/50 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-gray-400">
          <Activity className="w-4 h-4" />
          <span className="text-xs font-medium uppercase tracking-wider">Coding Runs</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-gray-500">{data.total || 0} total</span>
          {data.running > 0 && <span className="flex items-center gap-1 text-blue-400"><Loader className="w-3 h-3 animate-spin" />{data.running} running</span>}
          <span className="text-green-400">{data.completed || 0} done</span>
          {data.failed > 0 && <span className="text-red-400">{data.failed} failed</span>}
        </div>
      </div>

      {data.runs?.length > 0 ? (
        <div className="space-y-1.5 max-h-80 overflow-y-auto">
          {data.runs.map((run) => {
            const isSelected = selectedRun === run.id
            const isRunning = run.status === 'running' || run.status === 'starting'
            const isFailed = run.status === 'failed'
            return (
              <div key={run.id}>
                <button
                  onClick={() => setSelectedRun(isSelected ? null : run.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors ${
                    isSelected ? 'bg-gray-800 border border-gray-700' : 'bg-gray-950 border border-gray-800 hover:bg-gray-800/50'
                  }`}
                >
                  {isRunning ? <Loader className="w-3.5 h-3.5 animate-spin text-blue-400 flex-shrink-0" /> :
                   isFailed ? <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" /> :
                   <CheckCircle className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-gray-200 truncate">{run.stub_name.replace(/-/g, ' ')}</div>
                    <div className="text-[10px] text-gray-500">
                      {run.agent} · {run.model} · {run.start_time ? new Date(run.start_time).toLocaleTimeString() : '?'}
                    </div>
                  </div>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                    isRunning ? 'bg-blue-900/30 text-blue-300' :
                    isFailed ? 'bg-red-900/30 text-red-300' :
                    'bg-gray-800 text-gray-400'
                  }`}>{run.status}</span>
                  {isSelected ? <ChevronDown className="w-3.5 h-3.5 text-gray-500" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-500" />}
                </button>
                {isSelected && runDetail && runDetail.id === run.id && (
                  <div className="ml-3 mt-1 bg-gray-950 border border-gray-800 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between text-[10px] text-gray-500">
                      <span>Session: <code className="text-gray-400">{run.session_id?.slice(0, 20)}...</code></span>
                      <span>{run.event_count || 0} events</span>
                    </div>
                    {runDetail.events?.slice(-10).map((ev, i) => (
                      <div key={i} className={`flex items-start gap-2 text-[10px] ${
                        ev.level === 'error' ? 'text-red-400' : ev.level === 'warn' ? 'text-amber-400' : 'text-gray-400'
                      }`}>
                        <span className="text-gray-600 w-16 flex-shrink-0">{ev.timestamp?.slice(11, 19)}</span>
                        <span className="font-medium w-10 flex-shrink-0">[{ev.level}]</span>
                        <span>{ev.message}</span>
                      </div>
                    ))}
                    {isFailed && (
                      <button onClick={async () => {
                        try {
                          const res = await fetch(`/api/projects/${projectId}/build-plan/runs/${run.id}/resume`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ debug_model: 'deepseek-v4-pro' }),
                          })
                          if (!res.ok) { const err = await res.json(); alert(err.detail || 'Failed') }
                          refetch()
                        } catch (err) { alert(err.message) }
                      }} className="flex items-center gap-1.5 text-xs text-amber-400 hover:text-amber-300 border border-amber-800 rounded px-3 py-1.5 mt-2">
                        <Zap className="w-3.5 h-3.5" /> Resume with Debugger (deepseek-v4-pro)
                      </button>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="text-center py-6 text-gray-500 text-sm">
          <p>No coding runs yet. Generate code scripts and click <strong className="text-gray-400">Run</strong> to start one.</p>
        </div>
      )}
    </div>
  )
}

// ─── Blueprint Runner ─────────────────────────────────────────

function BlueprintRunner({ projectId, onRunStarted }) {
  const [collapsed, setCollapsed] = useState(true)
  const [blueprints, setBlueprints] = useState(null)
  const [runningId, setRunningId] = useState(null)
  const [error, setError] = useState(null)
  const [validatingId, setValidatingId] = useState(null)
  const [validationResults, setValidationResults] = useState({})

  // Fetch blueprints + validation on mount
  useEffect(() => {
    async function fetchBlueprints() {
      try {
        const res = await fetch(`/api/blueprints?project_id=${projectId}`)
        if (res.ok) setBlueprints((await res.json()).stubs || [])
      } catch {}
    }
    fetchBlueprints()
  }, [projectId])

  async function handleRun(bp) {
    setRunningId(bp.name)
    setError(null)
    try {
      // Use filename only from the blueprint path
      const stubPath = bp.path ? bp.path.split(/[\\/]/).pop() : `${bp.bp.toLowerCase()}-${bp.name}.md`
      const res = await fetch(`/api/projects/${projectId}/reasonix-run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stub_path: stubPath }),
      })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Failed') }
      const data = await res.json()
      const newRunId = data?.run?.id
      setRunningId(null)
      if (newRunId && onRunStarted) onRunStarted(newRunId)
    } catch (err) {
      setError(err.message)
      setRunningId(null)
    }
  }

  async function handleValidate(bp) {
    setValidatingId(bp.name)
    try {
      const res = await fetch(`/api/stubs/${bp.name}/validate`)
      if (res.ok) {
        const data = await res.json()
        setValidationResults(prev => ({ ...prev, [bp.name]: data }))
      }
    } catch {}
    setValidatingId(null)
  }

  if (!blueprints || blueprints.length === 0) return null

  return (
    <div className="border border-cyan-800 rounded-xl bg-cyan-950/10 p-6 space-y-4">
      <button onClick={() => setCollapsed(!collapsed)} className="flex items-center gap-2 text-cyan-400 w-full text-left">
        <Zap className="w-5 h-5" />
        <span className="text-sm font-semibold">Blueprint Runner</span>
        <span className="text-xs text-gray-500 ml-2">({blueprints.length} available)</span>
        {collapsed ? <ChevronRight className="w-4 h-4 ml-auto" /> : <ChevronDown className="w-4 h-4 ml-auto" />}
      </button>
      {!collapsed && (
        <div className="space-y-2">
          {error && <div className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded p-3">{error}</div>}
          {blueprints.map((bp) => {
            const isRunning = runningId === bp.name
            const isValidating = validatingId === bp.name
            const validation = validationResults[bp.name]
            return (
              <div key={bp.name} className="bg-gray-950 border border-cyan-800/30 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-cyan-900/30 flex items-center justify-center">
                      <span className="text-xs font-bold text-cyan-400">{bp.bp}</span>
                    </div>
                    <div>
                      <div className="text-sm font-medium text-gray-200">{bp.title}</div>
                      <div className="text-[10px] text-gray-500">
                        {bp.name} · {bp.init ? 'Initializes project' : 'No init'}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button onClick={() => handleValidate(bp)} disabled={isValidating}
                      className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 border border-gray-700 rounded px-2 py-1">
                      {isValidating ? <Loader className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
                      Validate
                    </button>
                    <button onClick={() => handleRun(bp)} disabled={isRunning}
                      className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                        isRunning ? 'bg-cyan-900/30 text-cyan-300 border-cyan-800 cursor-wait'
                                 : 'text-cyan-400 hover:text-cyan-300 border-cyan-800 hover:bg-cyan-900/20'
                      }`}>
                      {isRunning ? <><Loader className="w-3 h-3 animate-spin" /> Starting...</> : <><Play className="w-3 h-3" /> Run</>}
                    </button>
                  </div>
                </div>
                {/* Pressure test results */}
                {validation && (
                  <div className={`rounded-lg p-3 border text-xs ${
                    validation.valid ? 'bg-green-950/20 border-green-800/40' : 'bg-amber-950/20 border-amber-800/40'
                  }`}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className={`font-semibold ${validation.valid ? 'text-green-300' : 'text-amber-300'}`}>
                        {validation.valid ? '✅ Actionable' : '❌ Needs work'} — Score: {validation.score}/100
                      </span>
                      <span className="text-gray-500">{validation.summary}</span>
                    </div>
                    <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden mb-2">
                      <div className={`h-full rounded-full transition-all ${validation.score >= 80 ? 'bg-green-500' : validation.score >= 50 ? 'bg-amber-500' : 'bg-red-500'}`}
                           style={{ width: `${validation.score}%` }} />
                    </div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                      {validation.checks?.map((c, i) => (
                        <div key={i} className="flex items-center gap-1.5">
                          <span>{c.passed ? '✅' : c.severity === 'error' ? '❌' : '⚠️'}</span>
                          <span className={c.passed ? 'text-gray-400' : 'text-red-400'}>{c.message}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}


// ─── Reasonix Runs Panel ──────────────────────────────────────

function ReasonixRunsPanel({ projectId, refreshKey, latestRunId }) {
  const [collapsed, setCollapsed] = useState(false)  // start expanded
  const [runs, setRuns] = useState(null)
  const [selectedRun, setSelectedRun] = useState(null)
  const [runDetail, setRunDetail] = useState(null)
  const [error, setError] = useState(null)

  // Fetch runs list on mount, every 3 min, and when refreshKey changes
  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch(`/api/projects/${projectId}/reasonix-runs`)
      if (res.ok) setRuns(await res.json())
    } catch {}
  }, [projectId])

  useEffect(() => {
    fetchRuns()
    const interval = setInterval(fetchRuns, 60000) // poll every 60s for live updates
    return () => clearInterval(interval)
  }, [projectId, refreshKey, fetchRuns])

  // When latestRunId changes, auto-select and fetch detail
  useEffect(() => {
    if (latestRunId) {
      setCollapsed(false)
      setSelectedRun(latestRunId)
    }
  }, [latestRunId])

  // Fetch detail for selected run — fast while running, stops when done
  useEffect(() => {
    if (!selectedRun) { setRunDetail(null); return }
    let interval
    async function fetchDetail() {
      try {
        const res = await fetch(`/api/projects/${projectId}/reasonix-run/${selectedRun}`)
        if (res.ok) {
          const data = await res.json()
          setRunDetail(data)
          if (data.status === 'completed' || data.status === 'failed') {
            clearInterval(interval)
          }
        }
      } catch {}
    }
    fetchDetail()
    interval = setInterval(fetchDetail, 5000) // poll every 5s while active
    return () => clearInterval(interval)
  }, [selectedRun, projectId, latestRunId])

  // Manual poll button
  async function handlePoll(runId) {
    try {
      const res = await fetch(`/api/projects/${projectId}/reasonix-run/${runId}/poll`, { method: 'POST' })
      if (res.ok) {
        const updated = await res.json()
        setRunDetail(updated)
      }
    } catch {}
  }

  // Sort runs by start_time descending (most recent first)
  const allRuns = (runs?.runs || []).slice().sort((a, b) => {
    return new Date(b.start_time || 0).getTime() - new Date(a.start_time || 0).getTime()
  })
  const runningCount = runs?.running || 0
  const completedCount = runs?.completed || 0
  const failedCount = runs?.failed || 0

  // Build milestone status from latest run per stub
  const latestPerStub = {}
  allRuns.forEach(run => {
    const key = run.stub_name || run.bp_id || 'unknown'
    if (!latestPerStub[key] || new Date(run.start_time || 0) > new Date(latestPerStub[key].start_time || 0)) {
      latestPerStub[key] = run
    }
  })
  const milestones = Object.values(latestPerStub).sort((a, b) => {
    return new Date(b.start_time || 0).getTime() - new Date(a.start_time || 0).getTime()
  })

  return (
    <div className="border border-cyan-800 rounded-xl bg-cyan-950/10 p-6 space-y-4">
      <button onClick={() => setCollapsed(!collapsed)} className="flex items-center gap-2 text-cyan-400 w-full text-left">
        <Zap className="w-5 h-5" />
        <span className="text-sm font-semibold">Reasonix Runs</span>
        <span className="text-xs text-gray-500 ml-2">({allRuns.length} total{runningCount > 0 ? `, ${runningCount} running` : ''})</span>
        {collapsed ? <ChevronRight className="w-4 h-4 ml-auto" /> : <ChevronDown className="w-4 h-4 ml-auto" />}
      </button>
      {!collapsed && (
        <>
          {/* Summary bar */}
          <div className="flex items-center gap-4 text-xs">
            {runningCount > 0 && <span className="flex items-center gap-1 text-blue-400"><Loader className="w-3 h-3 animate-spin" />{runningCount} running</span>}
            {completedCount > 0 && <span className="text-green-400">{completedCount} completed</span>}
            {failedCount > 0 && <span className="text-red-400">{failedCount} failed</span>}
            {allRuns.length > 0 && <span className="text-gray-500">{allRuns.length} total</span>}
          </div>

          {error && <div className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded p-3">{error}</div>}

          {/* Milestone status — latest run per stub */}
          {milestones.length > 0 && (
            <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-3 space-y-1.5">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1.5">Milestone Status</div>
              <div className="grid grid-cols-1 gap-1.5">
                {milestones.map((run) => {
                  const isRunning = run.status === 'running' || run.status === 'starting'
                  const isFailed = run.status === 'failed'
                  const isDone = run.status === 'completed'
                  return (
                    <button key={run.id} onClick={() => { setCollapsed(false); setSelectedRun(run.id) }}
                      className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-gray-950 border border-gray-800 hover:border-cyan-800/50 transition-colors text-left">
                      {isRunning ? <Loader className="w-3.5 h-3.5 animate-spin text-cyan-400" /> :
                       isFailed ? <XCircle className="w-3.5 h-3.5 text-red-400" /> :
                       <CheckCircle className="w-3.5 h-3.5 text-green-400" />}
                      <div className="flex-1 min-w-0">
                        <div className="text-xs text-gray-200 truncate">{run.bp_id || run.stub_name}: {run.title || run.stub_name}</div>
                        <div className="text-[10px] text-gray-500">{run.start_time ? new Date(run.start_time).toLocaleString() : '?'}</div>
                      </div>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                        isRunning ? 'bg-cyan-900/30 text-cyan-300' :
                        isFailed ? 'bg-red-900/30 text-red-300' :
                        'bg-green-900/30 text-green-300'
                      }`}>{isRunning ? 'Running' : isFailed ? 'Failed' : 'Completed'}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {allRuns.length === 0 ? (
            <div className="text-center py-6 text-gray-500 text-sm">
              <p>No Reasonix runs yet. Use the Blueprint Runner above to start one.</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {allRuns.map((run) => {
                const isSelected = selectedRun === run.id
                const isRunning = run.status === 'running' || run.status === 'starting'
                const isFailed = run.status === 'failed'
                const hasFiles = run.files_changed?.length > 0
                return (
                  <div key={run.id}>
                    <button
                      onClick={() => setSelectedRun(isSelected ? null : run.id)}
                      className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors ${
                        isSelected ? 'bg-gray-800 border border-gray-700' : 'bg-gray-950 border border-gray-800 hover:bg-gray-800/50'
                      }`}
                    >
                      {isRunning ? <Loader className="w-3.5 h-3.5 animate-spin text-cyan-400 flex-shrink-0" /> :
                       isFailed ? <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" /> :
                       <CheckCircle className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />}
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-gray-200 truncate">
                          {run.bp_id || run.stub_name}: {run.title || run.stub_name}
                        </div>
                        <div className="text-[10px] text-gray-500 flex items-center gap-2">
                          <span>ID: {run.id?.slice(0, 8)}</span>
                          <span>·</span>
                          <span>{run.start_time ? new Date(run.start_time).toLocaleTimeString() : '?'}</span>
                          {hasFiles && <><span>·</span><span className="text-green-400">{run.files_changed.length} files</span></>}
                        </div>
                      </div>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                        isRunning ? 'bg-cyan-900/30 text-cyan-300' :
                        isFailed ? 'bg-red-900/30 text-red-300' :
                        'bg-gray-800 text-gray-400'
                      }`}>{run.status}</span>
                      {isSelected ? <ChevronDown className="w-3.5 h-3.5 text-gray-500" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-500" />}
                    </button>

                    {isSelected && runDetail && runDetail.id === run.id && (
                      <div className="ml-3 mt-1 bg-gray-950 border border-cyan-800/20 rounded-lg p-3 space-y-3">
                        {/* Status & actions */}
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <button onClick={() => handlePoll(run.id)}
                              className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 border border-cyan-800/50 rounded px-2 py-1">
                              <RefreshCw className="w-3 h-3" /> Poll Now
                            </button>
                          </div>
                          <div className="text-[10px] text-gray-500">
                            {runDetail.event_count || runDetail.events?.length || 0} events
                          </div>
                        </div>

                        {/* Output preview */}
                        {runDetail.output_preview && (
                          <div>
                            <div className="text-[10px] text-gray-500 uppercase mb-1">Output</div>
                            <pre className="text-[10px] text-green-300 bg-black/60 rounded p-2 max-h-32 overflow-y-auto font-mono whitespace-pre-wrap">
                              {runDetail.output_preview}
                            </pre>
                          </div>
                        )}

                        {/* Files changed */}
                        {runDetail.files_changed?.length > 0 && (
                          <div>
                            <div className="text-[10px] text-gray-500 uppercase mb-1">Files Changed ({runDetail.files_changed.length})</div>
                            <div className="grid grid-cols-1 gap-1 max-h-24 overflow-y-auto">
                              {runDetail.files_changed.map((f, i) => (
                                <div key={i} className="flex items-center gap-2 text-[10px]">
                                  <span className={`px-1 py-0.5 rounded text-[9px] font-mono ${
                                    f.status === 'added' ? 'bg-green-900/30 text-green-400' :
                                    f.status === 'modified' ? 'bg-amber-900/30 text-amber-400' :
                                    f.status === 'deleted' ? 'bg-red-900/30 text-red-400' :
                                    'bg-gray-800 text-gray-400'
                                  }`}>{f.status}</span>
                                  <span className="text-gray-300">{f.path}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Events log */}
                        {runDetail.events?.length > 0 && (
                          <div>
                            <div className="text-[10px] text-gray-500 uppercase mb-1">Events</div>
                            <div className="max-h-40 overflow-y-auto space-y-1">
                              {(runDetail.events || []).slice(-15).map((ev, i) => (
                                <div key={i} className={`flex items-start gap-2 text-[10px] ${
                                  ev.level === 'error' ? 'text-red-400' :
                                  ev.level === 'warn' ? 'text-amber-400' :
                                  'text-gray-400'
                                }`}>
                                  <span className="text-gray-600 w-14 flex-shrink-0">{ev.timestamp?.slice(11, 19)}</span>
                                  <span className="font-medium w-10 flex-shrink-0">[{ev.level}]</span>
                                  <span className="break-words">{ev.message}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Error detail */}
                        {runDetail.error && (
                          <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded p-2">
                            <span className="font-semibold">Error:</span> {runDetail.error}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}
