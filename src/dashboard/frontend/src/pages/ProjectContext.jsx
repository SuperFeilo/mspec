import { useState, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, Check, Loader, FileText,
  ArrowRight, Box, Cpu, Database, GitFork,
  Settings, Workflow, RefreshCw, AlertTriangle,
  CheckCircle, XCircle, Lightbulb, Plus,
  Lock, Unlock, Trash2, GripVertical,
} from 'lucide-react'

async function fetchContextFlow(projectId) {
  const res = await fetch(`/api/projects/${projectId}/context-flow`)
  if (!res.ok) throw new Error('Failed to fetch context flow')
  return res.json()
}

async function fetchProviderConfig() {
  const res = await fetch('/api/config/provider')
  if (!res.ok) throw new Error('Failed to fetch provider')
  return res.json()
}

const CATEGORY_CONFIG = {
  requirement: { icon: Box, label: 'Requirements', color: 'border-l-blue-500 bg-blue-950/20' },
  input: { icon: ArrowRight, label: 'Inputs', color: 'border-l-emerald-500 bg-emerald-950/20' },
  architecture: { icon: GitFork, label: 'Architecture', color: 'border-l-purple-500 bg-purple-950/20' },
  decision: { icon: Cpu, label: 'Decisions', color: 'border-l-amber-500 bg-amber-950/20' },
  tech_stack: { icon: Database, label: 'Tech Stack', color: 'border-l-cyan-500 bg-cyan-950/20' },
  output: { icon: Workflow, label: 'Outputs', color: 'border-l-rose-500 bg-rose-950/20' },
  structure: { icon: FileText, label: 'Structure', color: 'border-l-indigo-500 bg-indigo-950/20' },
  setup: { icon: Settings, label: 'Setup', color: 'border-l-teal-500 bg-teal-950/20' },
}

function FlowArrow() {
  return (
    <div className="flex justify-center py-1">
      <div className="flex flex-col items-center text-gray-600">
        <div className="w-0.5 h-5 bg-gray-600" />
        <ArrowRight className="w-4 h-4 -mt-1" />
      </div>
    </div>
  )
}

function FlowSection({ items, icon: Icon, label, color }) {
  if (!items || items.length === 0) return null
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 mb-2">
        <div className="p-1.5 rounded bg-gray-800">
          <Icon className="w-4 h-4" />
        </div>
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">{label}</h3>
        <span className="text-xs text-gray-600 ml-auto">{items.length} item{items.length !== 1 ? 's' : ''}</span>
      </div>
      <div className="space-y-1.5">
        {items.map((item, i) => (
          <div key={i} className={`border-l-2 ${color} rounded-r-lg p-3 text-sm`}>
            {typeof item === 'string' ? (
              <pre className="text-gray-300 font-mono text-xs whitespace-pre-wrap overflow-x-auto">{item}</pre>
            ) : item.type === 'diagram' ? (
              <pre className="text-green-300 font-mono text-xs whitespace-pre bg-black/30 rounded p-2 overflow-x-auto">{item.content}</pre>
            ) : (
              <div className="text-gray-300 text-xs">• {item.content}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function buildFlowLayout(flow) {
  const order = ['requirement', 'input', 'architecture', 'decision', 'tech_stack', 'output', 'structure', 'setup']
  const sections = []
  for (const cat of order) {
    if (flow[cat] && flow[cat].length > 0) {
      const config = CATEGORY_CONFIG[cat] || { icon: FileText, label: cat, color: 'border-l-gray-500' }
      sections.push({ category: cat, items: flow[cat], ...config })
    }
  }
  return sections
}

function ReadinessGauge({ score }) {
  const barColor = score >= 80 ? 'bg-green-500' : score >= 60 ? 'bg-amber-500' : 'bg-red-500'
  const textColor = score >= 80 ? 'text-green-400' : score >= 60 ? 'text-amber-400' : 'text-red-400'
  return (
    <div className="flex items-center gap-4">
      <div className="flex-1">
        <div className="h-3 bg-gray-800 rounded-full overflow-hidden">
          <div className={`h-full ${barColor} rounded-full transition-all duration-500`} style={{ width: `${Math.min(score, 100)}%` }} />
        </div>
      </div>
      <span className={`text-2xl font-bold font-mono ${textColor} min-w-[4rem] text-right`}>{score}%</span>
    </div>
  )
}

function DimensionCard({ dim }) {
  const barColor = dim.score >= 80 ? 'bg-green-500' : dim.score >= 60 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            {dim.score >= 80
              ? <CheckCircle className="w-4 h-4 text-green-400" />
              : <XCircle className="w-4 h-4 text-red-400" />
            }
            <span className="text-sm font-semibold text-gray-200">{dim.label}</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">{dim.description}</p>
        </div>
        <span className={`text-lg font-bold font-mono ${dim.score >= 80 ? 'text-green-400' : dim.score >= 60 ? 'text-amber-400' : 'text-red-400'}`}>{dim.score}%</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${dim.score}%` }} />
      </div>
      {dim.score < 80 && dim.suggestions?.length > 0 && (
        <div className="bg-amber-950/20 border border-amber-800/40 rounded p-2.5 space-y-1.5">
          <div className="flex items-center gap-1.5 text-amber-400 text-xs font-medium">
            <Lightbulb className="w-3 h-3" /> Suggestions
          </div>
          {dim.suggestions.map((s, i) => (
            <div key={i} className="text-xs text-amber-300/80 flex gap-2">
              <span className="text-amber-500 mt-0.5">→</span>
              <span>{s}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Requirement Card Editor ───────────────────────────────────

function RequirementCard({ req, index, onChange, onRemove }) {
  return (
    <div className="bg-gray-950 border border-gray-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-2">
        <GripVertical className="w-4 h-4 text-gray-600 flex-shrink-0" />
        <select
          value={req.priority}
          onChange={(e) => onChange(index, { ...req, priority: e.target.value })}
          className={`text-xs font-bold px-2 py-1 rounded ${
            req.priority === 'P0' ? 'bg-red-900/50 text-red-300 border border-red-800' :
            req.priority === 'P1' ? 'bg-amber-900/50 text-amber-300 border border-amber-800' :
            'bg-gray-800 text-gray-400 border border-gray-700'
          }`}
        >
          <option value="P0">P0 — Must Have</option>
          <option value="P1">P1 — Should Have</option>
          <option value="P2">P2 — Nice to Have</option>
        </select>
        <input
          type="text"
          value={req.title}
          onChange={(e) => onChange(index, { ...req, title: e.target.value })}
          className="flex-1 bg-transparent border-b border-transparent hover:border-gray-700 focus:border-cyan-600 text-sm font-medium text-gray-200 outline-none px-1 py-0.5"
          placeholder="Requirement title..."
        />
        <button
          type="button"
          onClick={() => onChange(index, { ...req, locked: !req.locked })}
          className={`p-1.5 rounded transition-colors ${req.locked ? 'text-green-400 bg-green-950/30' : 'text-gray-600 hover:text-gray-400'}`}
          title={req.locked ? 'Locked' : 'Click to lock'}
        >
          {req.locked ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
        </button>
        <button type="button" onClick={() => onRemove(index)} className="p-1.5 text-gray-600 hover:text-red-400 rounded transition-colors">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="pl-7 space-y-2">
        <textarea
          value={req.description}
          onChange={(e) => onChange(index, { ...req, description: e.target.value })}
          rows={2}
          className="w-full bg-gray-900 border border-gray-800 rounded px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-cyan-600 resize-none"
          placeholder="Description — what this requirement means..."
        />
        <input
          type="text"
          value={req.acceptance}
          onChange={(e) => onChange(index, { ...req, acceptance: e.target.value })}
          className="w-full bg-gray-900 border border-gray-800 rounded px-2.5 py-1.5 text-xs text-gray-400 focus:outline-none focus:border-cyan-600"
          placeholder="Acceptance criteria — how to verify this is done..."
        />
      </div>
    </div>
  )
}

// ─── Main Component ────────────────────────────────────────────

export default function ProjectContext() {
  const { projectId } = useParams()
  const [confirming, setConfirming] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [commitHash, setCommitHash] = useState(null)
  const [confirmError, setConfirmError] = useState(null)
  const [showDiagram, setShowDiagram] = useState(true)

  const { data: flow, isLoading, error } = useQuery({
    queryKey: ['context-flow', projectId],
    queryFn: () => fetchContextFlow(projectId),
  })

  const { data: providerCfg } = useQuery({
    queryKey: ['provider-config'],
    queryFn: fetchProviderConfig,
  })

  const sections = useMemo(() => flow ? buildFlowLayout(flow) : [], [flow])
  const readiness = flow?.readiness

  // ── Interactive state ────────────────────────────────────
  const [requirements, setRequirements] = useState([])
  const [techStack, setTechStack] = useState({})
  const [decisions, setDecisions] = useState([])
  const [newDecision, setNewDecision] = useState({ decision: '', rationale: '' })

  // Init from context flow data once loaded
  useMemo(() => {
    if (!flow) return
    // Seed requirements from context
    if (requirements.length === 0 && flow.requirement?.length > 0) {
      const seeded = []
      for (const text of flow.requirement) {
        const lines = text.split('\n').filter(l => l.trim().startsWith('-'))
        for (const line of lines) {
          const clean = line.replace(/^[-\*\s]+/, '').trim()
          if (clean) {
            seeded.push({
              title: clean,
              priority: 'P1',
              description: '',
              acceptance: '',
              locked: false,
            })
          }
        }
      }
      if (seeded.length > 0) setRequirements(seeded)
    }
    // Seed tech stack from flow
    if (Object.keys(techStack).length === 0) {
      const ts = {}
      if (flow.tech_stack?.length > 0) {
        const allTech = flow.tech_stack.join('\n')
        if (allTech.match(/(python|fastapi|flask|django|react|vue|angular)/i)) ts.backend = ''
        if (allTech.match(/(sqlite|postgres|mysql|mongodb|redis)/i)) ts.database = ''
        if (allTech.match(/(react|vue|angular|svelte|html|css|javascript|typescript)/i)) ts.frontend = ''
        if (allTech.match(/(docker|kubernetes)/i)) ts.deployment = ''
      }
      if (Object.keys(ts).length > 0) {
        // Try to extract values
        const allTech = flow.tech_stack.join('\n')
        for (const key of Object.keys(ts)) {
          const match = allTech.match(new RegExp(key + '[:\\s]+([^\\n]+)', 'i'))
          if (match) ts[key] = match[1].trim()
        }
        setTechStack(ts)
      }
    }
  }, [flow])

  function addRequirement() {
    setRequirements([...requirements, { title: '', priority: 'P1', description: '', acceptance: '', locked: false }])
  }

  function updateRequirement(index, updated) {
    const next = [...requirements]
    next[index] = updated
    setRequirements(next)
  }

  function removeRequirement(index) {
    setRequirements(requirements.filter((_, i) => i !== index))
  }

  function addDecision() {
    if (!newDecision.decision.trim()) return
    setDecisions([...decisions, { ...newDecision }])
    setNewDecision({ decision: '', rationale: '' })
  }

  function removeDecision(index) {
    setDecisions(decisions.filter((_, i) => i !== index))
  }

  async function handleConfirm() {
    setConfirming(true)
    setConfirmError(null)

    try {
      const payload = {
        requirements: requirements.filter(r => r.title.trim()),
        tech_stack: techStack,
        decisions,
        source_contexts: flow?.files || [],
        provider: {
          provider: providerCfg?.provider || 'localllm',
          model: providerCfg?.localllm?.model || providerCfg?.deepseek?.model || '',
        },
      }

      const res = await fetch(`/api/projects/${projectId}/confirm-context`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to confirm context')
      }

      const result = await res.json()
      setConfirmed(true)
      setCommitHash(result.commit_hash || null)
    } catch (err) {
      setConfirmError(err.message)
    } finally {
      setConfirming(false)
    }
  }

  if (isLoading) {
    return <div className="flex items-center gap-2 text-gray-400 py-16 justify-center">
      <Loader className="w-5 h-5 animate-spin" /> Analyzing project context...
    </div>
  }

  if (error) {
    return <div className="text-center py-16 text-gray-500">
      <p className="text-red-400">Failed to load context: {error.message}</p>
      <Link to={`/project/${projectId}`} className="text-cyan-400 hover:underline text-sm mt-2 inline-block">Back to project</Link>
    </div>
  }

  if (!readiness) {
    return <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to={`/project/${projectId}`} className="text-gray-400 hover:text-gray-200"><ArrowLeft className="w-5 h-5" /></Link>
        <h1 className="text-2xl font-bold">Context Review</h1>
      </div>
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-8 text-center">
        <FileText className="w-10 h-10 text-gray-600 mx-auto mb-3" />
        <p className="text-gray-400">No structured context found.</p>
      </div>
    </div>
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to={`/project/${projectId}`} className="text-gray-400 hover:text-gray-200"><ArrowLeft className="w-5 h-5" /></Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{flow?.project_name || 'Context Review'}</h1>
          <p className="text-sm text-gray-400 mt-0.5">{sections.length} categories · {flow?.files?.length || 0} source files</p>
        </div>
        <button onClick={() => setShowDiagram(!showDiagram)} className="text-xs text-gray-400 hover:text-gray-200 border border-gray-700 rounded px-3 py-1.5">
          {showDiagram ? 'Hide Flow' : 'Show Flow'}
        </button>
      </div>

      {/* ── Readiness Score ─────────────────────────────────── */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6 space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-gray-400">
            <RefreshCw className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Agentic Readiness Score</span>
          </div>
          <span className={`text-xs font-medium px-2 py-0.5 rounded ${readiness.overall >= 80 ? 'bg-green-900/40 text-green-300' : 'bg-amber-900/40 text-amber-300'}`}>
            {readiness.overall >= 80 ? '✓ Ready' : 'Needs Work'}
          </span>
        </div>
        <ReadinessGauge score={readiness.overall} />
        {readiness.overall < 80 && readiness.gaps?.length > 0 && (
          <div className="flex items-start gap-2 bg-amber-950/15 border border-amber-800/30 rounded-lg p-3">
            <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-amber-300/80">
              <span className="font-medium">{readiness.gaps.length} area(s)</span> need improvement. Use the form below to lock in clear requirements and decisions.
            </div>
          </div>
        )}
        {readiness.overall >= 80 && (
          <div className="flex items-start gap-2 bg-green-950/15 border border-green-800/30 rounded-lg p-3">
            <CheckCircle className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-green-300/80">Context is agentic-ready. Lock in requirements below and confirm.</div>
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {readiness.dimensions?.map(dim => <DimensionCard key={dim.id} dim={dim} />)}
        </div>
      </div>

      {/* ── Flow Diagram ────────────────────────────────────── */}
      {showDiagram && sections.length > 0 && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center gap-2 mb-6 text-gray-400 border-b border-gray-800 pb-3">
            <GitFork className="w-4 h-4" /> <span className="text-xs font-medium uppercase tracking-wider">Context Flow</span>
          </div>
          <div className="space-y-1">
            {sections.map((section, idx) => (
              <div key={section.category}>
                <FlowSection {...section} />
                {idx < sections.length - 1 && <FlowArrow />}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Source files ────────────────────────────────────── */}
      {flow?.files?.length > 0 && (
        <div className="bg-gray-900/30 border border-gray-800 rounded-lg p-4">
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Source Files ({flow.files.length})</h3>
          <div className="flex flex-wrap gap-2">
            {flow.files.map(f => <span key={f} className="text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded font-mono">{f}</span>)}
          </div>
        </div>
      )}

      {/* ── Interactive Requirement Locking ─────────────────── */}
      <div className="border border-gray-800 rounded-xl bg-gray-900/50 p-6 space-y-5">
        <div className="flex items-center gap-2 text-gray-400 border-b border-gray-800 pb-3">
          <Box className="w-4 h-4" />
          <span className="text-xs font-medium uppercase tracking-wider">Lock In Requirements</span>
          <span className="text-xs text-gray-600 ml-auto">{requirements.filter(r => r.locked).length} locked · {requirements.length} total</span>
        </div>

        {requirements.length === 0 ? (
          <div className="text-center py-6 text-gray-500">
            <p className="text-sm">No requirements yet. Click below to add one.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {requirements.map((req, i) => (
              <RequirementCard key={i} req={req} index={i} onChange={updateRequirement} onRemove={removeRequirement} />
            ))}
          </div>
        )}

        <button
          type="button"
          onClick={addRequirement}
          className="flex items-center gap-2 text-sm text-cyan-400 hover:text-cyan-300 transition-colors"
        >
          <Plus className="w-4 h-4" /> Add Requirement
        </button>
      </div>

      {/* ── Tech Stack Decisions ────────────────────────────── */}
      <div className="border border-gray-800 rounded-xl bg-gray-900/50 p-6 space-y-4">
        <div className="flex items-center gap-2 text-gray-400 border-b border-gray-800 pb-3">
          <Database className="w-4 h-4" />
          <span className="text-xs font-medium uppercase tracking-wider">Tech Stack Decisions</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {['backend', 'frontend', 'database', 'deployment'].map((cat) => (
            <label key={cat} className="block">
              <span className="text-xs text-gray-500 uppercase tracking-wider">{cat}</span>
              <input
                type="text"
                value={techStack[cat] || ''}
                onChange={(e) => setTechStack({ ...techStack, [cat]: e.target.value })}
                className="w-full mt-1 bg-gray-950 border border-gray-800 rounded px-3 py-2 text-sm font-mono text-gray-200 focus:outline-none focus:border-cyan-600"
                placeholder={`e.g. Python 3.11 + FastAPI`}
              />
            </label>
          ))}
        </div>
      </div>

      {/* ── Architecture Decisions ──────────────────────────── */}
      <div className="border border-gray-800 rounded-xl bg-gray-900/50 p-6 space-y-4">
        <div className="flex items-center gap-2 text-gray-400 border-b border-gray-800 pb-3">
          <Cpu className="w-4 h-4" />
          <span className="text-xs font-medium uppercase tracking-wider">Architecture Decisions</span>
        </div>

        {decisions.length > 0 && (
          <div className="space-y-2">
            {decisions.map((d, i) => (
              <div key={i} className="flex items-start gap-2 bg-gray-950 border border-gray-800 rounded-lg p-3">
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-200">{d.decision}</div>
                  {d.rationale && <div className="text-xs text-gray-500 mt-0.5">{d.rationale}</div>}
                </div>
                <button type="button" onClick={() => removeDecision(i)} className="p-1 text-gray-600 hover:text-red-400">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <div className="flex-1 space-y-2">
            <input
              type="text"
              value={newDecision.decision}
              onChange={(e) => setNewDecision({ ...newDecision, decision: e.target.value })}
              className="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-cyan-600"
              placeholder="e.g. REST API with service layer pattern"
            />
            <input
              type="text"
              value={newDecision.rationale}
              onChange={(e) => setNewDecision({ ...newDecision, rationale: e.target.value })}
              className="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-sm text-gray-400 focus:outline-none focus:border-cyan-600"
              placeholder="Rationale — why this decision?"
            />
          </div>
          <button
            type="button"
            onClick={addDecision}
            disabled={!newDecision.decision.trim()}
            className="bg-cyan-700 hover:bg-cyan-600 disabled:bg-gray-700 text-white px-4 py-2 rounded text-sm self-start"
          >
            Add
          </button>
        </div>
      </div>

      {/* ── Confirm ─────────────────────────────────────────── */}
      <div className="border border-gray-800 rounded-xl bg-gray-900/50 p-6 space-y-4">
        <div className="flex items-center gap-2 text-gray-400 border-b border-gray-800 pb-3">
          <Check className="w-4 h-4" />
          <span className="text-xs font-medium uppercase tracking-wider">
            Generate mspec.md {confirmed && <span className="text-green-400 ml-2">✓ Confirmed</span>}
          </span>
        </div>

        <div className="text-sm text-gray-400 space-y-2">
          <p>This will generate a structured <code className="text-cyan-400 font-mono">mspec.md</code> file containing:</p>
          <ul className="list-disc list-inside text-xs text-gray-500 space-y-1">
            <li><strong className="text-gray-300">{requirements.filter(r => r.title.trim()).length}</strong> locked requirements with priorities</li>
            <li><strong className="text-gray-300">{Object.values(techStack).filter(Boolean).length}</strong> tech stack decisions</li>
            <li><strong className="text-gray-300">{decisions.length}</strong> architecture decisions</li>
            <li>Provider: <strong className="text-gray-300">{providerCfg?.provider || 'localllm'}</strong></li>
            <li>The file will be <strong className="text-gray-300">committed to git</strong> for portable resume</li>
          </ul>
        </div>

        {confirmError && (
          <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">{confirmError}</div>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={handleConfirm}
            disabled={confirming || confirmed}
            className={`flex items-center gap-2 px-6 py-2.5 rounded text-sm font-medium transition-colors ${
              confirmed
                ? 'bg-green-800 text-green-200 cursor-default'
                : 'bg-cyan-700 hover:bg-cyan-600 disabled:bg-gray-700 disabled:text-gray-500 text-white'
            }`}
          >
            {confirmed ? (
              <><Check className="w-4 h-4" /> Confirmed & Committed</>
            ) : confirming ? (
              <><Loader className="w-4 h-4 animate-spin" /> Generating...</>
            ) : (
              <><Check className="w-4 h-4" /> Generate & Confirm</>
            )}
          </button>
          {confirmed && (
            <span className="text-sm text-green-400">
              ✓ Saved to <code className="font-mono">.harness/mspec.md</code>
              {commitHash ? (
                <> and committed as <code className="font-mono">{commitHash}</code></>
              ) : (
                <> (git commit skipped — configure git user)</>
              )}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
