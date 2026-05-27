import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, Loader, CheckCircle, XCircle, AlertTriangle,
  ChevronDown, ChevronRight, Filter, RefreshCw,
  Activity, BarChart3, Zap, TrendingDown,
} from 'lucide-react'

async function fetchAnalytics(projectId) {
  const r = await fetch(`/api/projects/${projectId}/analytics/runs`)
  if (!r.ok) throw new Error('Failed')
  return r.json()
}

// ─── Summary Cards ─────────────────────────────────────────────

function SummaryCards({ summary }) {
  const s = summary || {}
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="text-xs text-gray-500 uppercase tracking-wider">Total Runs</div>
        <div className="text-2xl font-bold text-gray-200 mt-1">{s.total || 0}</div>
      </div>
      <div className="bg-gray-900 border border-green-800/50 rounded-xl p-4">
        <div className="text-xs text-gray-500 uppercase tracking-wider">Completed</div>
        <div className="text-2xl font-bold text-green-400 mt-1">{s.completed || 0}</div>
      </div>
      <div className="bg-gray-900 border border-red-800/50 rounded-xl p-4">
        <div className="text-xs text-gray-500 uppercase tracking-wider">Failed</div>
        <div className="text-2xl font-bold text-red-400 mt-1">{s.failed || 0}</div>
      </div>
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="text-xs text-gray-500 uppercase tracking-wider">Success Rate</div>
        <div className="text-2xl font-bold text-cyan-400 mt-1">{s.success_rate || 0}%</div>
      </div>
    </div>
  )
}

// ─── Success Rate Bar Chart ────────────────────────────────────

function StubBarChart({ byStub, onFilterStub }) {
  if (!byStub?.length) return null
  const maxTotal = Math.max(...byStub.map(s => s.total), 1)
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wider flex items-center gap-2">
        <BarChart3 className="w-3.5 h-3.5" /> Success Rate by Blueprint
      </h3>
      <div className="space-y-1.5">
        {byStub.map((s) => (
          <button
            key={s.stub_name}
            onClick={() => onFilterStub(s.stub_name)}
            className="w-full flex items-center gap-3 group hover:bg-gray-800/30 rounded-lg px-3 py-2 transition-colors text-left"
          >
            <span className="text-xs text-gray-400 w-32 truncate font-mono">{s.stub_name}</span>
            <div className="flex-1 h-5 bg-gray-800 rounded-full overflow-hidden flex">
              <div
                className="h-full bg-green-500/70 rounded-l-full"
                style={{ width: `${(s.completed / maxTotal) * 100 * 0.6}%` }}
              />
              <div
                className="h-full bg-red-500/50 rounded-r-full"
                style={{ width: `${(s.failed / maxTotal) * 100 * 0.6}%` }}
              />
            </div>
            <span className={`text-xs font-mono font-semibold min-w-[3rem] text-right ${
              s.success_rate >= 70 ? 'text-green-400' : s.success_rate >= 40 ? 'text-amber-400' : 'text-red-400'
            }`}>{s.success_rate}%</span>
            <span className="text-[10px] text-gray-600 min-w-[3rem]">{s.completed}/{s.total}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

// ─── Run Outcome Table ─────────────────────────────────────────

function RunTable({ runs, filter, setFilter }) {
  const [sortKey, setSortKey] = useState('start_time')
  const [sortDir, setSortDir] = useState('desc')

  if (!runs?.length) {
    return <div className="text-center py-8 text-gray-500 text-sm">No runs match the filter.</div>
  }

  const filtered = runs.filter(r => {
    if (filter.stub && !(r.stub_name || '').includes(filter.stub)) return false
    if (filter.status && r.status !== filter.status) return false
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    const av = a[sortKey] || ''
    const bv = b[sortKey] || ''
    const cmp = av < bv ? -1 : av > bv ? 1 : 0
    return sortDir === 'asc' ? cmp : -cmp
  })

  function toggleSort(key) {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-gray-500">{filtered.length} runs</span>
        {filter.stub && (
          <button onClick={() => setFilter({})} className="text-[10px] bg-gray-800 text-gray-300 px-2 py-0.5 rounded-full hover:bg-gray-700">
            stub: {filter.stub} ✕
          </button>
        )}
        <select value={filter.status || ''} onChange={e => setFilter(f => ({ ...f, status: e.target.value || undefined }))}
          className="text-[10px] bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-300">
          <option value="">All statuses</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="stalled">Stalled</option>
          <option value="running">Running</option>
        </select>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left py-2 px-2 font-medium cursor-pointer hover:text-gray-300" onClick={() => toggleSort('stub_name')}>Blueprint {sortKey === 'stub_name' && (sortDir === 'asc' ? '↑' : '↓')}</th>
              <th className="text-left py-2 px-2 font-medium cursor-pointer hover:text-gray-300" onClick={() => toggleSort('agent')}>Agent</th>
              <th className="text-left py-2 px-2 font-medium cursor-pointer hover:text-gray-300" onClick={() => toggleSort('status')}>Outcome</th>
              <th className="text-left py-2 px-2 font-medium cursor-pointer hover:text-gray-300" onClick={() => toggleSort('start_time')}>Started</th>
              <th className="text-left py-2 px-2 font-medium">Error / Note</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(r => {
              const isFailed = r.status === 'failed' || r.status === 'stalled'
              const isCompleted = r.status === 'completed'
              const isRunning = r.status === 'running' || r.status === 'starting'
              return (
                <tr key={r.id} className={`border-b border-gray-800/50 hover:bg-gray-800/20 ${
                  isFailed ? 'bg-red-950/10' : isCompleted ? 'bg-green-950/5' : ''
                }`}>
                  <td className="py-2 px-2 font-mono text-gray-300 max-w-[160px] truncate">{r.stub_name}</td>
                  <td className="py-2 px-2 text-gray-500">{r.agent || '?'}</td>
                  <td className="py-2 px-2">
                    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full ${
                      isCompleted ? 'bg-green-900/30 text-green-300' :
                      isFailed ? 'bg-red-900/30 text-red-300' :
                      isRunning ? 'bg-blue-900/30 text-blue-300' :
                      'bg-gray-800 text-gray-400'
                    }`}>
                      {isCompleted ? <CheckCircle className="w-2.5 h-2.5" /> :
                       isFailed ? <XCircle className="w-2.5 h-2.5" /> :
                       isRunning ? <Loader className="w-2.5 h-2.5 animate-spin" /> : null}
                      {r.status}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-gray-500 whitespace-nowrap">
                    {(r.start_time || '').slice(0, 16).replace('T', ' ')}
                  </td>
                  <td className="py-2 px-2 text-gray-600 max-w-[200px] truncate">{r.error || (isCompleted ? '—' : '')}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Failure Theme Cards ───────────────────────────────────────

function FailureThemes({ themes, onFilterStub }) {
  if (!themes?.length) {
    return (
      <div className="text-center py-6 text-gray-500 text-sm">
        <CheckCircle className="w-8 h-8 text-green-500 mx-auto mb-2" />
        No failure themes — all runs succeeded!
      </div>
    )
  }

  const themeIcons = {
    'Stall / Timeout': <TrendingDown className="w-4 h-4" />,
    'Process Crash / Exit Code': <XCircle className="w-4 h-4" />,
    'Configuration / Path': <AlertTriangle className="w-4 h-4" />,
    'API / Network': <Zap className="w-4 h-4" />,
    'Code Error / Syntax': <AlertTriangle className="w-4 h-4" />,
    'Agent / Model Issue': <Activity className="w-4 h-4" />,
    'Git / Filesystem': <Filter className="w-4 h-4" />,
  }

  const themeColors = {
    'Stall / Timeout': 'border-amber-800/50 bg-amber-950/10',
    'Process Crash / Exit Code': 'border-red-800/50 bg-red-950/10',
    'Configuration / Path': 'border-orange-800/50 bg-orange-950/10',
    'API / Network': 'border-purple-800/50 bg-purple-950/10',
    'Code Error / Syntax': 'border-pink-800/50 bg-pink-950/10',
    'Agent / Model Issue': 'border-blue-800/50 bg-blue-950/10',
    'Git / Filesystem': 'border-gray-700 bg-gray-900/50',
  }

  return (
    <div className="space-y-3">
      <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wider flex items-center gap-2">
        <AlertTriangle className="w-3.5 h-3.5 text-red-400" /> Top Failure Themes
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {themes.slice(0, 5).map((t, i) => (
          <div key={t.theme} className={`border rounded-xl p-4 space-y-3 ${themeColors[t.theme] || 'border-gray-800 bg-gray-900/50'}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-gray-400">{themeIcons[t.theme] || <AlertTriangle className="w-4 h-4" />}</span>
                <span className="text-sm font-semibold text-gray-200">{t.theme}</span>
              </div>
              <span className="text-lg font-bold font-mono text-gray-300">{t.count}</span>
            </div>
            <div className="space-y-1.5">
              {t.examples.slice(0, 2).map((ex, j) => (
                <div key={j} className="text-[10px] text-gray-500 bg-black/30 rounded p-2 font-mono leading-relaxed max-h-12 overflow-hidden">
                  {ex.error}
                </div>
              ))}
            </div>
            {t.affected_stubs?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {t.affected_stubs.slice(0, 3).map(s => (
                  <button key={s} onClick={() => onFilterStub(s)}
                    className="text-[10px] bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded-full hover:bg-gray-700 hover:text-gray-200">
                    {s.replace(/^BP-\d+-/i, '').replace(/-/g, ' ')}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Main Component ────────────────────────────────────────────

export default function ProjectAnalytics() {
  const { projectId } = useParams()
  const [filter, setFilter] = useState({})
  const [showThemes, setShowThemes] = useState(true)
  const [showChart, setShowChart] = useState(true)
  const [showTable, setShowTable] = useState(true)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['analytics', projectId],
    queryFn: () => fetchAnalytics(projectId),
    refetchInterval: 15000,
  })

  if (isLoading) return (
    <div className="flex items-center gap-2 text-gray-400 py-16 justify-center">
      <Loader className="w-5 h-5 animate-spin" /> Loading analytics...
    </div>
  )

  if (!data) return (
    <div className="text-center py-16 text-gray-500">
      <p>No analytics data available yet. Run some blueprints first.</p>
    </div>
  )

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to={`/project/${projectId}`}><ArrowLeft className="w-5 h-5 text-gray-400 hover:text-gray-200" /></Link>
          <div>
            <h1 className="text-2xl font-bold">Run Analytics</h1>
            <p className="text-xs text-gray-500 mt-0.5">Success patterns, failure themes, root cause analysis</p>
          </div>
        </div>
        <button onClick={() => refetch()} className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 border border-gray-700 rounded px-3 py-1.5">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Summary */}
      <SummaryCards summary={data.summary} />

      {/* Toggle sections */}
      <div className="flex items-center gap-4 text-xs">
        <button onClick={() => setShowChart(!showChart)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border ${showChart ? 'bg-gray-800 border-gray-600 text-gray-200' : 'text-gray-500 border-gray-700'}`}>
          <BarChart3 className="w-3.5 h-3.5" /> Success Rates {showChart ? '▼' : '▶'}
        </button>
        <button onClick={() => setShowThemes(!showThemes)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border ${showThemes ? 'bg-gray-800 border-gray-600 text-gray-200' : 'text-gray-500 border-gray-700'}`}>
          <AlertTriangle className="w-3.5 h-3.5" /> Failure Themes {showThemes ? '▼' : '▶'}
        </button>
        <button onClick={() => setShowTable(!showTable)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border ${showTable ? 'bg-gray-800 border-gray-600 text-gray-200' : 'text-gray-500 border-gray-700'}`}>
          <Activity className="w-3.5 h-3.5" /> Run Table {showTable ? '▼' : '▶'}
        </button>
      </div>

      {/* Success rate chart */}
      {showChart && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5">
          <StubBarChart byStub={data.by_stub} onFilterStub={(s) => setFilter({ stub: s })} />
        </div>
      )}

      {/* Failure themes */}
      {showThemes && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5">
          <FailureThemes themes={data.failure_themes} onFilterStub={(s) => setFilter({ stub: s })} />
        </div>
      )}

      {/* Run outcome table */}
      {showTable && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5">
          <RunTable runs={data.recent_runs} filter={filter} setFilter={setFilter} />
        </div>
      )}

      {/* Nav back */}
      <div className="flex justify-center pt-2">
        <Link to={`/project/${projectId}`} className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-200 border border-gray-700 rounded-lg px-4 py-2">
          <ArrowLeft className="w-4 h-4" /> Back to Project
        </Link>
      </div>
    </div>
  )
}
