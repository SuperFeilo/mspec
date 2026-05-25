import { useState, useMemo, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, Check, Loader, FileText, ChevronDown, ChevronRight,
  ArrowRight, Box, Cpu, Database, GitFork,
  Settings, Workflow, RefreshCw, AlertTriangle,
  CheckCircle, XCircle, Lightbulb, Plus,
  Lock, Unlock, Trash2, Eye, Edit3, Target,
  Layers, Shield, Zap, Server, Globe, Star,
} from 'lucide-react'

async function fetchContextFlow(projectId) {
  const r = await fetch(`/api/projects/${projectId}/context-flow`)
  if (!r.ok) throw new Error('Failed')
  return r.json()
}

async function fetchProviderConfig() {
  const r = await fetch('/api/config/provider')
  if (!r.ok) throw new Error('Failed')
  return r.json()
}

// ─── Step indicators ───────────────────────────────────────────

const STEPS = [
  { id: 'goals', label: 'Goals & Requirements', icon: Target },
  { id: 'infer', label: 'Infer Tech Choices', icon: Zap },
  { id: 'decide', label: 'Critical Choices', icon: Layers },
  { id: 'finish', label: 'Review & Confirm', icon: Check },
]

function StepIndicator({ current, goTo }) {
  const idx = STEPS.findIndex(s => s.id === current)
  return (
    <div className="flex items-center gap-1">
      {STEPS.map((s, i) => {
        const Icon = s.icon
        const done = i < idx
        const active = i === idx
        return (
          <div key={s.id} className="flex items-center gap-1">
            <button
              onClick={() => done && goTo(s.id)}
              disabled={!done}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                active ? 'bg-cyan-900/40 text-cyan-300 border border-cyan-700' :
                done ? 'bg-green-900/30 text-green-300 border border-green-800 cursor-pointer hover:bg-green-900/50' :
                'bg-gray-800 text-gray-600 border border-gray-700 cursor-default'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {done ? <Check className="w-3 h-3" /> : <span className="w-3 h-3 flex items-center justify-center text-[10px]">{i + 1}</span>}
              <span className="hidden sm:inline">{s.label}</span>
            </button>
            {i < STEPS.length - 1 && <div className={`w-4 h-0.5 ${done ? 'bg-green-700' : 'bg-gray-700'}`} />}
          </div>
        )
      })}
    </div>
  )
}

// ─── Readiness Gauge ───────────────────────────────────────────

function ReadinessGauge({ score, size = 'lg' }) {
  const barColor = score >= 80 ? 'bg-green-500' : score >= 60 ? 'bg-amber-500' : 'bg-red-500'
  const textColor = score >= 80 ? 'text-green-400' : score >= 60 ? 'text-amber-400' : 'text-red-400'
  const h = size === 'lg' ? 'h-3' : 'h-2'
  const ts = size === 'lg' ? 'text-2xl' : 'text-lg'
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1">
        <div className={`${h} bg-gray-800 rounded-full overflow-hidden`}>
          <div className={`h-full ${barColor} rounded-full transition-all duration-700`} style={{ width: `${Math.min(score, 100)}%` }} />
        </div>
      </div>
      <span className={`${ts} font-bold font-mono ${textColor} min-w-[3.5rem] text-right`}>{score}%</span>
    </div>
  )
}

// ─── Diff View ─────────────────────────────────────────────────

function DiffView({ md }) {
  const [showRaw, setShowRaw] = useState(false)
  if (!md) return null
  return (
    <div>
      <button onClick={() => setShowRaw(!showRaw)} className="text-xs text-gray-400 hover:text-gray-200 border border-gray-700 rounded px-3 py-1 mb-2">
        {showRaw ? 'Hide Raw' : 'Show Raw'}
      </button>
      {showRaw && (
        <pre className="text-xs text-gray-300 bg-gray-950 rounded-lg p-4 border border-gray-800 overflow-x-auto whitespace-pre-wrap max-h-96">{md}</pre>
      )}
    </div>
  )
}

// ─── Choice Table Component ────────────────────────────────────

function ChoiceTable({ choices, onSelect }) {
  if (!choices || Object.keys(choices).length === 0) {
    return <div className="text-gray-500 text-sm py-4 text-center">No choices to display. Complete Step 1 first.</div>
  }

  return (
    <div className="space-y-4">
      {Object.entries(choices).map(([catId, choice]) => (
        <div key={catId} className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <div className="px-4 py-2.5 bg-gray-800/50 border-b border-gray-800">
            <span className="text-sm font-semibold text-gray-200">{choice.label}</span>
            {choice.existing && (
              <span className="ml-2 text-xs text-green-400">(detected: {choice.existing})</span>
            )}
          </div>
          <div className="p-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {choice.options?.map((opt) => {
                const isSelected = choice.selected === opt.name
                const isExisting = choice.existing && opt.name.toLowerCase().includes(choice.existing.toLowerCase())
                return (
                  <button
                    key={opt.name}
                    onClick={() => onSelect(catId, opt.name)}
                    className={`text-left px-3 py-2.5 rounded-lg border text-sm transition-all ${
                      isSelected
                        ? 'bg-cyan-900/30 border-cyan-700 text-cyan-300 shadow-sm shadow-cyan-900/30'
                        : isExisting
                        ? 'bg-green-900/20 border-green-800/60 text-green-300'
                        : 'bg-gray-950 border-gray-700 text-gray-400 hover:border-gray-600'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {isSelected ? <CheckCircle className="w-4 h-4 text-cyan-400 flex-shrink-0" /> : <div className="w-4 h-4 rounded-full border-2 border-gray-600 flex-shrink-0" />}
                      <div>
                        <div className="text-sm flex items-center gap-1.5">
                          {opt.name}
                          {opt.default && <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />}
                        </div>
                        {opt.default && <div className="text-[10px] text-amber-400">★ recommended</div>}
                        {isExisting && <div className="text-[10px] text-green-500">in project</div>}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

export default function ProjectContext() {
  const { projectId } = useParams()
  const [step, setStep] = useState('goals')

  // Step 1 state
  const [overview, setOverview] = useState('')
  const [requirements, setRequirements] = useState([])

  // Step 2-3 state (from inference)
  const [inference, setInference] = useState(null)
  const [choices, setChoices] = useState({})
  const [inferring, setInferring] = useState(false)

  // Step 4 state
  const [confirming, setConfirming] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [commitHash, setCommitHash] = useState(null)
  const [confirmError, setConfirmError] = useState(null)
  const [previewData, setPreviewData] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  // Data
  const { data: flow, isLoading } = useQuery({
    queryKey: ['context-flow', projectId],
    queryFn: () => fetchContextFlow(projectId),
  })
  const { data: providerCfg } = useQuery({
    queryKey: ['provider-config'],
    queryFn: fetchProviderConfig,
  })

  const readiness = flow?.readiness

  // Seed requirements from context flow
  useMemo(() => {
    if (!flow || requirements.length > 0) return
    const seeded = []
    if (flow.requirement?.length > 0) {
      for (const text of flow.requirement) {
        const lines = text.split('\n').filter(l => l.trim().startsWith('-'))
        for (const line of lines) {
          const clean = line.replace(/^[-\*\s]+/, '').trim()
          if (clean) seeded.push({ title: clean, priority: 'P1', description: '', acceptance: '', locked: false })
        }
      }
    }
    if (seeded.length > 0) setRequirements(seeded)
  }, [flow])

  // ── Step 1: Goals ───────────────────────────────────────

  function addRequirement() {
    setRequirements([...requirements, { title: '', priority: 'P1', description: '', acceptance: '', locked: false }])
  }

  function updateReq(idx, updated) {
    const next = [...requirements]; next[idx] = updated; setRequirements(next)
  }

  function removeReq(idx) {
    setRequirements(requirements.filter((_, i) => i !== idx))
  }

  async function handleInfer() {
    setInferring(true)
    try {
      const res = await fetch(`/api/projects/${projectId}/infer-options`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          overview,
          requirements: requirements.filter(r => r.title.trim()),
        }),
      })
      if (!res.ok) throw new Error('Inference failed')
      const data = await res.json()
      setInference(data)
      // Initialize choices from inference
      const initChoices = {}
      for (const [k, v] of Object.entries(data.choices || {})) {
        initChoices[k] = v.selected || v.recommended
      }
      setChoices(initChoices)
      setStep('infer')
    } catch (err) {
      setConfirmError(err.message)
    } finally {
      setInferring(false)
    }
  }

  // ── Step 3: Select Choice ───────────────────────────────

  function handleChoiceSelect(catId, value) {
    setChoices(prev => ({ ...prev, [catId]: value }))
    // Update inference choices
    if (inference?.choices?.[catId]) {
      setInference(prev => ({
        ...prev,
        choices: {
          ...prev.choices,
          [catId]: { ...prev.choices[catId], selected: value },
        },
      }))
    }
  }

  // ── Step 4: Preview & Confirm ───────────────────────────

  async function handlePreview() {
    setPreviewLoading(true)
    try {
      // Build tech_stack from choices
      const techStack = {}
      if (inference?.choices) {
        for (const [k, v] of Object.entries(inference.choices)) {
          if (v.type === 'tech_stack') {
            techStack[k] = choices[k] || v.selected
          }
        }
      }

      const payload = {
        overview,
        profile: inference?.profile || '',
        requirements: requirements.filter(r => r.title.trim()),
        tech_stack: techStack,
        decisions: inference?.patterns?.map(p => ({ decision: p, rationale: `Inferred from ${inference.profile} profile` })) || [],
        source_contexts: flow?.files || [],
        provider: {
          provider: providerCfg?.provider || 'localllm',
          model: providerCfg?.localllm?.model || providerCfg?.deepseek?.model || '',
        },
      }

      const res = await fetch(`/api/projects/${projectId}/preview-mspec`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error('Preview failed')
      const data = await res.json()
      setPreviewData(data)
      setStep('finish')
    } catch (err) {
      setConfirmError(err.message)
    } finally {
      setPreviewLoading(false)
    }
  }

  async function handleConfirm() {
    setConfirming(true)
    try {
      const techStack = {}
      if (inference?.choices) {
        for (const [k, v] of Object.entries(inference.choices)) {
          if (v.type === 'tech_stack') techStack[k] = choices[k] || v.selected
        }
      }
      const payload = {
        overview,
        profile: inference?.profile || '',
        requirements: requirements.filter(r => r.title.trim()),
        tech_stack: techStack,
        decisions: inference?.patterns?.map(p => ({ decision: p, rationale: `Inferred from ${inference.profile}` })) || [],
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
        throw new Error(err.detail || 'Failed')
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

  // ── Render ──────────────────────────────────────────────

  if (isLoading) return <div className="flex items-center gap-2 text-gray-400 py-16 justify-center"><Loader className="w-5 h-5 animate-spin" /> Loading...</div>
  if (!readiness) return <div className="text-center py-16 text-gray-500">No context data.</div>

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to={`/project/${projectId}`}><ArrowLeft className="w-5 h-5 text-gray-400 hover:text-gray-200" /></Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{flow?.project_name || 'Context'}</h1>
        </div>
      </div>

      {/* Step indicator */}
      <StepIndicator current={step} goTo={(s) => { if (s !== 'finish' || previewData) setStep(s) }} />

      {/* ══════════════════════════════════════════════════════
         STEP 1: Goals & Requirements
         ══════════════════════════════════════════════════════ */}
      {step === 'goals' && (
        <div className="space-y-5">
          {/* Readiness gauge */}
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5">
            <div className="flex items-center gap-2 text-gray-400 mb-3">
              <Target className="w-4 h-4" />
              <span className="text-xs font-medium uppercase tracking-wider">Current Readiness</span>
            </div>
            <ReadinessGauge score={readiness.overall} />
          </div>

          {/* Overview */}
          <div className="border border-gray-800 rounded-xl bg-gray-900/50 p-6 space-y-4">
            <div className="flex items-center gap-2 text-gray-400 border-b border-gray-800 pb-3">
              <FileText className="w-4 h-4" />
              <span className="text-xs font-medium uppercase tracking-wider">Project Overview</span>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">What is this project? Who is it for?</label>
              <textarea
                value={overview}
                onChange={(e) => setOverview(e.target.value)}
                rows={4}
                className="w-full bg-gray-950 border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-200 focus:outline-none focus:border-cyan-600 resize-y"
                placeholder={`e.g. "${flow?.project_name || 'Project'} is a web application that enables users to ..."`}
              />
              <div className="mt-2 bg-gray-950/50 border border-gray-800 rounded-lg p-3 text-xs text-gray-500">
                <Lightbulb className="w-3 h-3 inline mr-1 text-amber-400" />
                Best practice: Start with "<strong className="text-gray-400">{flow?.project_name || 'Project'}</strong> is a <strong className="text-gray-400">[type]</strong> that enables users to <strong className="text-gray-400">[core action]</strong>."
              </div>
            </div>
          </div>

          {/* Requirements */}
          <div className="border border-gray-800 rounded-xl bg-gray-900/50 p-6 space-y-4">
            <div className="flex items-center gap-2 text-gray-400 border-b border-gray-800 pb-3">
              <Box className="w-4 h-4" />
              <span className="text-xs font-medium uppercase tracking-wider">Requirements</span>
              <span className="text-xs text-gray-600 ml-auto">{requirements.filter(r => r.title.trim()).length} defined · {requirements.filter(r => r.locked).length} locked</span>
            </div>

            {requirements.length === 0 && (
              <div className="text-center py-4 text-gray-500 text-sm">
                <p>No requirements defined yet. Add your first requirement below.</p>
              </div>
            )}

            <div className="space-y-3">
              {requirements.map((req, i) => (
                <div key={i} className="bg-gray-950 border border-gray-800 rounded-lg p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <select
                      value={req.priority}
                      onChange={(e) => updateReq(i, { ...req, priority: e.target.value })}
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
                      onChange={(e) => updateReq(i, { ...req, title: e.target.value })}
                      className="flex-1 bg-transparent border-b border-transparent hover:border-gray-700 focus:border-cyan-600 text-sm font-medium text-gray-200 outline-none px-1 py-0.5"
                      placeholder="Requirement title..."
                    />
                    <button onClick={() => updateReq(i, { ...req, locked: !req.locked })}
                      className={`p-1.5 rounded ${req.locked ? 'text-green-400 bg-green-950/30' : 'text-gray-600'}`}>
                      {req.locked ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
                    </button>
                    <button onClick={() => removeReq(i)} className="p-1.5 text-gray-600 hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                  <div className="pl-9 space-y-2">
                    <textarea
                      value={req.description}
                      onChange={(e) => updateReq(i, { ...req, description: e.target.value })}
                      rows={1}
                      className="w-full bg-gray-900 border border-gray-800 rounded px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-cyan-600 resize-none"
                      placeholder="Description — what, why, for whom..."
                    />
                    <input
                      type="text"
                      value={req.acceptance}
                      onChange={(e) => updateReq(i, { ...req, acceptance: e.target.value })}
                      className="w-full bg-gray-900 border border-gray-800 rounded px-2.5 py-1.5 text-xs text-gray-400 focus:outline-none focus:border-cyan-600"
                      placeholder="Acceptance criteria — how to verify..."
                    />
                  </div>
                </div>
              ))}
            </div>

            <button onClick={addRequirement} className="flex items-center gap-2 text-sm text-cyan-400 hover:text-cyan-300">
              <Plus className="w-4 h-4" /> Add Requirement
            </button>
          </div>

          {confirmError && <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">{confirmError}</div>}

          {/* Template Save/Load */}
          <div className="flex items-center gap-3 border-t border-gray-800 pt-4">
            <button
              onClick={async () => {
                const name = prompt('Template name:', `${flow?.project_name || 'Project'} Requirements`)
                if (!name) return
                try {
                  const res = await fetch('/api/templates', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, overview, requirements: requirements.filter(r => r.title.trim()) }),
                  })
                  if (!res.ok) throw new Error('Failed to save')
                  alert('Template saved!')
                } catch (err) { alert(err.message) }
              }}
              className="text-xs text-gray-400 hover:text-gray-200 border border-gray-700 rounded px-3 py-1.5"
            >
              💾 Save as Template
            </button>
            <button
              onClick={async () => {
                try {
                  const res = await fetch('/api/templates')
                  if (!res.ok) throw new Error('Failed to load')
                  const data = await res.json()
                  const tpls = data.templates
                  if (!tpls || tpls.length === 0) { alert('No saved templates'); return }
                  const names = tpls.map((t, i) => `${i+1}. ${t.name} (${t.requirements?.length || 0} reqs)`)
                  const pick = prompt(`Saved templates:\n${names.join('\n')}\n\nEnter number to load:`)
                  if (!pick) return
                  const idx = parseInt(pick) - 1
                  if (idx < 0 || idx >= tpls.length) { alert('Invalid selection'); return }
                  const tpl = tpls[idx]
                  if (tpl.overview) setOverview(tpl.overview)
                  if (tpl.requirements?.length) setRequirements(tpl.requirements.map(r => ({...r, locked: false})))
                } catch (err) { alert(err.message) }
              }}
              className="text-xs text-gray-400 hover:text-gray-200 border border-gray-700 rounded px-3 py-1.5"
            >
              📂 Load Template
            </button>
          </div>

          <div className="flex justify-end">
            <button
              onClick={handleInfer}
              disabled={inferring || !overview.trim()}
              className="flex items-center gap-2 bg-cyan-700 hover:bg-cyan-600 disabled:bg-gray-700 text-white px-6 py-2.5 rounded-lg text-sm font-medium"
            >
              {inferring ? <><Loader className="w-4 h-4 animate-spin" /> Analyzing...</> : <><Zap className="w-4 h-4" /> Infer Tech Choices →</>}
            </button>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════
         STEP 2: Inferred Tech/Dependencies
         ══════════════════════════════════════════════════════ */}
      {step === 'infer' && inference && (
        <div className="space-y-5">
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5 space-y-4">
            <div className="flex items-center gap-2 text-gray-400">
              <Zap className="w-4 h-4" />
              <span className="text-xs font-medium uppercase tracking-wider">Inferred Profile</span>
            </div>

            <div className="bg-cyan-950/20 border border-cyan-800/40 rounded-lg p-4">
              <div className="text-sm font-semibold text-cyan-300">{inference.profile}</div>
              <div className="text-xs text-gray-400 mt-1">{inference.description}</div>
              {inference.architecture_pattern && (
                <div className="mt-2 text-xs text-gray-500">
                  <span className="text-gray-400">Architecture:</span> {inference.architecture_pattern}
                </div>
              )}
            </div>

            {inference.patterns?.length > 0 && (
              <div>
                <div className="text-xs text-gray-500 mb-2">Recommended Patterns</div>
                <div className="flex flex-wrap gap-2">
                  {inference.patterns.map(p => (
                    <span key={p} className="text-xs bg-gray-800 text-cyan-300 px-2.5 py-1 rounded-full border border-cyan-800/50">{p}</span>
                  ))}
                </div>
              </div>
            )}

            <div className="text-xs text-gray-500 bg-gray-950/50 rounded-lg p-3 border border-gray-800">
              <Lightbulb className="w-3 h-3 inline mr-1 text-amber-400" />
              These recommendations are based on your project goals. Click <strong className="text-gray-400">Proceed to Choices</strong> to review and select your preferred options.
            </div>
          </div>

          <div className="flex justify-between">
            <button onClick={() => setStep('goals')} className="text-sm text-gray-400 hover:text-gray-200 border border-gray-700 rounded-lg px-4 py-2">
              ← Back to Goals
            </button>
            <button
              onClick={() => setStep('decide')}
              className="flex items-center gap-2 bg-cyan-700 hover:bg-cyan-600 text-white px-6 py-2.5 rounded-lg text-sm font-medium"
            >
              Proceed to Choices <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════
         STEP 3: Critical Choices — Option Table
         ══════════════════════════════════════════════════════ */}
      {step === 'decide' && inference && (
        <div className="space-y-5">
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5">
            <div className="flex items-center gap-2 text-gray-400 mb-4">
              <Layers className="w-4 h-4" />
              <span className="text-xs font-medium uppercase tracking-wider">Critical Choices</span>
              <span className="text-xs text-gray-600 ml-auto">{Object.values(choices).filter(Boolean).length} selected</span>
            </div>

            <div className="text-xs text-gray-500 mb-4 bg-gray-950/50 rounded-lg p-3 border border-gray-800">
              <Lightbulb className="w-3 h-3 inline mr-1 text-amber-400" />
              For each category, choose your preferred option. <strong className="text-green-400">Green</strong> = detected in existing code. <strong className="text-cyan-400">Cyan</strong> = your selection. Click to change.
            </div>

            <ChoiceTable choices={inference.choices} onSelect={handleChoiceSelect} />
          </div>

          <div className="flex justify-between">
            <button onClick={() => setStep('infer')} className="text-sm text-gray-400 hover:text-gray-200 border border-gray-700 rounded-lg px-4 py-2">
              ← Back to Inference
            </button>
            <button
              onClick={handlePreview}
              disabled={previewLoading}
              className="flex items-center gap-2 bg-cyan-700 hover:bg-cyan-600 disabled:bg-gray-700 text-white px-6 py-2.5 rounded-lg text-sm font-medium"
            >
              {previewLoading ? <><Loader className="w-4 h-4 animate-spin" /> Processing...</> : <><Eye className="w-4 h-4" /> Review & Finalize →</>}
            </button>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════
         STEP 4: Review & Confirm
         ══════════════════════════════════════════════════════ */}
      {step === 'finish' && previewData && (
        <div className="space-y-5">
          {/* Score comparison */}
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5 space-y-4">
            <div className="flex items-center gap-2 text-gray-400">
              <RefreshCw className="w-4 h-4" />
              <span className="text-xs font-medium uppercase tracking-wider">Readiness Score Change</span>
            </div>
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
              <div className="space-y-1">
                <div className="text-xs text-gray-500">Before</div>
                <ReadinessGauge score={previewData.before?.overall || 0} size="sm" />
              </div>
              <ArrowRight className="w-6 h-6 text-gray-600" />
              <div className="space-y-1">
                <div className="text-xs text-gray-500">After</div>
                <ReadinessGauge score={previewData.after?.overall || 0} size="sm" />
              </div>
            </div>
            {previewData.after?.overall > previewData.before?.overall && (
              <div className="text-center text-sm text-green-400 font-medium">
                +{(previewData.after.overall - previewData.before.overall).toFixed(0)} point improvement
              </div>
            )}

            {/* Dimension breakdown */}
            <div className="grid grid-cols-2 gap-2">
              {previewData.before?.dimensions?.map((bDim) => {
                const aDim = previewData.after?.dimensions?.find(d => d.id === bDim.id)
                const aScore = aDim?.score ?? bDim.score
                return (
                  <div key={bDim.id} className="bg-gray-950 border border-gray-800 rounded p-2">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-[10px] text-gray-500 truncate">{bDim.label}</span>
                      <span className={`text-[10px] font-mono ${aScore > bDim.score ? 'text-green-400' : ''}`}>{bDim.score}→{aScore}</span>
                    </div>
                    <div className="flex gap-0.5 h-1">
                      <div className="flex-1 bg-gray-800 rounded-full overflow-hidden">
                        <div className="h-full bg-gray-600 rounded-full" style={{ width: `${bDim.score}%` }} />
                      </div>
                      <div className="flex-1 bg-gray-800 rounded-full overflow-hidden">
                        <div className={`h-full ${aScore >= 80 ? 'bg-green-500' : aScore >= 60 ? 'bg-amber-500' : 'bg-red-500'} rounded-full`} style={{ width: `${aScore}%` }} />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Final selections summary */}
          {inference && (
            <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5 space-y-3">
              <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">Your Choices</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {Object.entries(inference.choices || {}).map(([k, v]) => (
                  <div key={k} className="bg-gray-950 border border-gray-800 rounded-lg p-3">
                    <div className="text-[10px] text-gray-500 uppercase">{v.label}</div>
                    <div className="text-sm font-medium text-cyan-300 mt-0.5">{choices[k] || v.selected}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Pattern finalization */}
          {inference?.patterns && (
            <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-2 text-gray-400">
                <GitFork className="w-4 h-4" />
                <span className="text-xs font-medium uppercase tracking-wider">Final Architecture Pattern</span>
              </div>
              <div className="bg-gray-950 border border-gray-800 rounded-lg p-4">
                <div className="text-sm font-medium text-green-300">{inference.architecture_pattern}</div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {inference.patterns.map(p => (
                    <span key={p} className="text-[10px] bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full">{p}</span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* mspec.md */}
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5 space-y-3">
            <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wider">Generated mspec.md</h3>
            <DiffView md={previewData.mspec_md} />
          </div>

          {confirmError && <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">{confirmError}</div>}

          <div className="flex items-center gap-3 justify-between">
            <button onClick={() => setStep('decide')} className="text-sm text-gray-400 hover:text-gray-200 border border-gray-700 rounded-lg px-4 py-2">
              ← Back to Choices
            </button>
            <div className="flex items-center gap-3">
              <button
                onClick={handleConfirm}
                disabled={confirming || confirmed}
                className={`flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  confirmed
                    ? 'bg-green-800 text-green-200 cursor-default'
                    : 'bg-cyan-700 hover:bg-cyan-600 disabled:bg-gray-700 text-white'
                }`}
              >
                {confirmed ? <><Check className="w-4 h-4" /> Confirmed ✓</> : confirming ? <><Loader className="w-4 h-4 animate-spin" /> Confirming...</> : <><Check className="w-4 h-4" /> Confirm & Generate</>}
              </button>
              {confirmed && commitHash && <span className="text-sm text-green-400">Committed <code className="font-mono">{commitHash}</code></span>}
              {confirmed && (
                <button onClick={() => window.location.href = `/project/${projectId}`} className="text-sm text-cyan-400 hover:underline">
                  Back to Project
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
