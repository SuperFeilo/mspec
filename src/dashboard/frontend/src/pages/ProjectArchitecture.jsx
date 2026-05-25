import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, Check, FileText, GitFork, Cpu, Database, Globe,
  Lock, Unlock, Edit3, ArrowRight, RefreshCw, Server, Layers,
  AlertTriangle, CheckCircle, XCircle, BookOpen, Terminal,
  Shield, Wrench, FolderTree,
} from 'lucide-react'

async function fetchArchitecture(projectId) {
  const res = await fetch(`/api/projects/${projectId}/architecture`)
  if (!res.ok) throw new Error('Failed')
  return res.json()
}

const LAYER_COLORS = {
  'Client Layer': 'border-l-blue-500',
  'API Layer': 'border-l-cyan-500',
  'Service Layer': 'border-l-purple-500',
  'Data Layer': 'border-l-green-500',
  'Database Layer': 'border-l-emerald-500',
}

const TECH_COLORS = {
  backend: { border: 'border-l-cyan-500', bg: 'bg-cyan-500/10', text: 'text-cyan-400' },
  frontend: { border: 'border-l-blue-500', bg: 'bg-blue-500/10', text: 'text-blue-400' },
  database: { border: 'border-l-green-500', bg: 'bg-green-500/10', text: 'text-green-400' },
  cache: { border: 'border-l-purple-500', bg: 'bg-purple-500/10', text: 'text-purple-400' },
  deployment: { border: 'border-l-amber-500', bg: 'bg-amber-500/10', text: 'text-amber-400' },
  testing: { border: 'border-l-rose-500', bg: 'bg-rose-500/10', text: 'text-rose-400' },
}

function SectionBadge({ present, label, icon: Icon }) {
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs border ${
      present ? 'bg-green-950/20 border-green-800/40 text-green-300' : 'bg-gray-800/50 border-gray-700 text-gray-500'
    }`}>
      {present ? <CheckCircle className="w-3.5 h-3.5 text-green-400" /> : <XCircle className="w-3.5 h-3.5 text-gray-600" />}
      <Icon className="w-3.5 h-3.5" />
      {label}
    </div>
  )
}

function TechCard({ label, value, color }) {
  if (!value) return null
  return (
    <div className={`flex items-center gap-3 bg-gray-900 border ${color.border} rounded-xl p-4`}>
      <div className={`p-2 rounded-lg ${color.bg}`}>
        <div className={`w-2 h-2 rounded-full ${color.text}`} />
      </div>
      <div>
        <div className="text-xs text-gray-500 uppercase tracking-wider">{label}</div>
        <div className="text-sm font-semibold text-gray-200">{value}</div>
      </div>
    </div>
  )
}

function RequirementCard({ req }) {
  return (
    <div className={`border-l-2 rounded-r-lg p-3 ${
      req.priority === 'P0' ? 'border-l-red-500 bg-red-950/10' :
      req.priority === 'P1' ? 'border-l-amber-500 bg-amber-950/10' :
      'border-l-gray-600 bg-gray-900/30'
    }`}>
      <div className="flex items-center gap-2">
        {req.locked ? <Lock className="w-3 h-3 text-green-400 flex-shrink-0" /> : <Unlock className="w-3 h-3 text-gray-500 flex-shrink-0" />}
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
          req.priority === 'P0' ? 'bg-red-900/50 text-red-300' :
          req.priority === 'P1' ? 'bg-amber-900/50 text-amber-300' :
          'bg-gray-800 text-gray-400'
        }`}>{req.priority}</span>
        <span className="text-sm text-gray-200">{req.title}</span>
      </div>
      {req.acceptance && (
        <div className="mt-1 ml-7 text-xs text-gray-500">✓ {req.acceptance}</div>
      )}
    </div>
  )
}

export default function ProjectArchitecture() {
  const { projectId } = useParams()
  const { data, isLoading } = useQuery({
    queryKey: ['architecture', projectId],
    queryFn: () => fetchArchitecture(projectId),
    refetchInterval: 5000,
  })

  if (isLoading) {
    return <div className="flex items-center gap-2 text-gray-400 py-16 justify-center">
      <RefreshCw className="w-5 h-5 animate-spin" /> Loading architecture...
    </div>
  }

  if (!data) {
    return <div className="text-center py-16 text-gray-500">Failed to load architecture.</div>
  }

  // ── Not confirmed state ──
  if (!data.confirmed) {
    return (
      <div className="space-y-6 max-w-3xl mx-auto">
        <div className="flex items-center gap-3">
          <Link to={`/project/${projectId}`}><ArrowLeft className="w-5 h-5 text-gray-400 hover:text-gray-200" /></Link>
          <h1 className="text-2xl font-bold">Architecture</h1>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center space-y-5">
          <div className="flex justify-center">
            <div className="p-4 bg-amber-950/20 rounded-full">
              <AlertTriangle className="w-10 h-10 text-amber-400" />
            </div>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-200 mb-2">No Architecture Generated Yet</h2>
            <p className="text-sm text-gray-400 max-w-md mx-auto">
              {data.message || "Complete the Context workflow to generate your architecture blueprint. This will create the mspec.md file that powers this view."}
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to={`/project/${projectId}/context`}
              className="flex items-center gap-2 bg-cyan-700 hover:bg-cyan-600 text-white px-5 py-2.5 rounded-lg text-sm font-medium"
            >
              <Edit3 className="w-4 h-4" /> Go to Context Workflow
            </Link>
            <Link
              to={`/project/${projectId}`}
              className="flex items-center gap-2 text-gray-400 hover:text-gray-200 border border-gray-700 px-5 py-2.5 rounded-lg text-sm"
            >
              <ArrowLeft className="w-4 h-4" /> Back to Project
            </Link>
          </div>
        </div>
      </div>
    )
  }

  // ── Confirmed state ──
  const reqKeys = { P0: [], P1: [], P2: [] }
  for (const req of data.requirements || []) {
    if (reqKeys[req.priority]) reqKeys[req.priority].push(req)
  }
  const techEntries = Object.entries(data.tech_stack || {})

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to={`/project/${projectId}`}><ArrowLeft className="w-5 h-5 text-gray-400 hover:text-gray-200" /></Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">Architecture</h1>
            <span className="flex items-center gap-1 text-xs bg-green-900/40 text-green-300 px-2.5 py-1 rounded-full border border-green-800/50">
              <CheckCircle className="w-3 h-3" /> Confirmed
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-0.5">{data.project_name} · {data.total_sections || 0} sections</p>
        </div>
        <Link
          to={`/project/${projectId}/context`}
          className="flex items-center gap-2 text-sm text-cyan-400 hover:text-cyan-300 border border-cyan-800 rounded-lg px-4 py-2 transition-colors"
        >
          <Edit3 className="w-4 h-4" /> Edit
        </Link>
      </div>

      {/* Section completeness badges */}
      <div className="flex flex-wrap gap-2">
        <SectionBadge present={true} label="Requirements" icon={FileText} />
        <SectionBadge present={true} label="Tech Stack" icon={Database} />
        <SectionBadge present={data.layers?.length > 0} label="Architecture" icon={GitFork} />
        <SectionBadge present={data.has_setup} label="Setup" icon={Terminal} />
        <SectionBadge present={data.has_business_rules} label="Business Rules" icon={Shield} />
        <SectionBadge present={data.has_api} label="API Specs" icon={Wrench} />
        <SectionBadge present={data.has_dependencies} label="Dependencies" icon={Globe} />
        <SectionBadge present={data.has_structure} label="File Structure" icon={FolderTree} />
      </div>

      {/* ── Main Architecture Flow ── */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <div className="flex items-center gap-2 text-gray-400 mb-6 border-b border-gray-800 pb-3">
          <GitFork className="w-4 h-4" />
          <span className="text-xs font-medium uppercase tracking-wider">Architecture Flow</span>
        </div>

        <div className="space-y-0">
          {/* 1. Requirements */}
          <div className="bg-gray-950/50 border border-gray-800 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <FileText className="w-4 h-4 text-blue-400" />
              <span className="text-sm font-semibold text-gray-300">Requirements</span>
              <span className="text-xs text-gray-600 ml-auto">{data.requirements?.length || 0} defined</span>
            </div>
            {data.requirements?.length > 0 ? (
              <div className="space-y-3">
                {['P0','P1','P2'].map(p => reqKeys[p]?.length > 0 && (
                  <div key={p}>
                    <div className={`text-xs font-medium mb-1.5 ${
                      p === 'P0' ? 'text-red-400' : p === 'P1' ? 'text-amber-400' : 'text-gray-400'
                    }`}>
                      {p} — {p === 'P0' ? 'Must Have' : p === 'P1' ? 'Should Have' : 'Nice to Have'}
                    </div>
                    <div className="space-y-1.5">
                      {reqKeys[p].map((req, i) => <RequirementCard key={i} req={req} />)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-gray-500 text-center py-3 italic">Parsed from mspec.md</div>
            )}
          </div>

          {/* Arrow */}
          <div className="flex justify-center py-1">
            <div className="flex flex-col items-center text-gray-600">
              <div className="w-0.5 h-4 bg-gray-600" />
              <ArrowRight className="w-4 h-4 -mt-1" />
            </div>
          </div>

          {/* 2. Tech Stack */}
          <div className="bg-gray-950/50 border border-gray-800 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <Database className="w-4 h-4 text-cyan-400" />
              <span className="text-sm font-semibold text-gray-300">Tech Stack</span>
              <span className="text-xs text-gray-600 ml-auto">{techEntries.length} layers</span>
            </div>
            {techEntries.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {techEntries.map(([key, value]) => (
                  <TechCard
                    key={key}
                    label={key.charAt(0).toUpperCase() + key.slice(1)}
                    value={value}
                    color={TECH_COLORS[key] || { border: 'border-l-gray-500', bg: 'bg-gray-500/10', text: 'text-gray-400' }}
                  />
                ))}
              </div>
            ) : (
              <div className="text-sm text-gray-500 text-center py-3 italic">No tech stack defined in mspec.md</div>
            )}
          </div>

          {/* Arrow */}
          <div className="flex justify-center py-1">
            <div className="flex flex-col items-center text-gray-600">
              <div className="w-0.5 h-4 bg-gray-600" />
              <ArrowRight className="w-4 h-4 -mt-1" />
            </div>
          </div>

          {/* 3. Architecture Layers + Decisions */}
          <div className="bg-gray-950/50 border border-gray-800 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <Layers className="w-4 h-4 text-purple-400" />
              <span className="text-sm font-semibold text-gray-300">Architecture</span>
              <span className="text-xs text-gray-600 ml-auto">{data.layers?.length || 0} layers · {data.decisions?.length || 0} decisions</span>
            </div>

            {data.layers?.length > 0 && (
              <div className="space-y-2 mb-4">
                {data.layers.map((layer, i) => (
                  <div key={i} className={`flex items-center gap-3 border-l-2 ${LAYER_COLORS[layer.name] || 'border-l-gray-500'} pl-3 py-1.5`}>
                    <div className="text-sm font-medium text-gray-200 min-w-[7rem]">{layer.name}</div>
                    {layer.description && <div className="text-xs text-gray-400">{layer.description}</div>}
                  </div>
                ))}
              </div>
            )}

            {data.decisions?.length > 0 && (
              <div className="border-t border-gray-800 pt-4 mt-2">
                <div className="text-xs text-gray-500 mb-2 uppercase tracking-wider">Decisions</div>
                <div className="space-y-1.5">
                  {data.decisions.map((d, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm text-gray-300">
                      <Check className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                      {d}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(!data.layers?.length && !data.decisions?.length) && (
              <div className="text-sm text-gray-500 text-center py-3 italic">Architecture details from mspec.md</div>
            )}
          </div>

          {/* 4. Setup Commands (if present) */}
          {data.setup_commands?.length > 0 && (
            <>
              <div className="flex justify-center py-1">
                <div className="flex flex-col items-center text-gray-600">
                  <div className="w-0.5 h-4 bg-gray-600" />
                  <ArrowRight className="w-4 h-4 -mt-1" />
                </div>
              </div>
              <div className="bg-gray-950/50 border border-gray-800 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-3">
                  <Terminal className="w-4 h-4 text-teal-400" />
                  <span className="text-sm font-semibold text-gray-300">Quick Start</span>
                </div>
                <pre className="bg-gray-950 border border-gray-800 rounded-lg p-3 text-xs text-green-300 font-mono overflow-x-auto">
                  {data.setup_commands.map((cmd, i) => `$ ${cmd}`).join('\n')}
                </pre>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Bottom actions */}
      <div className="flex justify-center gap-4">
        <Link
          to={`/project/${projectId}/context`}
          className="flex items-center gap-2 bg-cyan-700 hover:bg-cyan-600 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
        >
          <Edit3 className="w-4 h-4" /> Edit Architecture in Context
        </Link>
        <Link
          to={`/project/${projectId}`}
          className="flex items-center gap-2 text-gray-400 hover:text-gray-200 border border-gray-700 px-5 py-2.5 rounded-lg text-sm transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Project
        </Link>
      </div>
    </div>
  )
}
