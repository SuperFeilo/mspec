import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, CheckCircle, XCircle, Loader, ChevronDown, ChevronRight } from 'lucide-react'

async function fetchSessions(projectId) {
  const res = await fetch(`/api/projects/${projectId}/sessions`)
  if (!res.ok) throw new Error('Failed to fetch sessions')
  return res.json()
}

export default function ProjectSessions() {
  const { projectId } = useParams()
  const { data, isLoading } = useQuery({
    queryKey: ['sessions', projectId],
    queryFn: () => fetchSessions(projectId),
    refetchInterval: 5000,
  })

  const [expandedId, setExpandedId] = useState(null)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Link to={`/project/${projectId}`} className="text-gray-400 hover:text-gray-200">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold">Sessions</h1>
        {data?.sessions && (
          <span className="text-xs text-gray-500">
            {data.sessions.length} total · {data.sessions.filter(s => s.run_status === 'failed').length} failed
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="text-gray-400">Loading...</div>
      ) : !data?.sessions?.length ? (
        <div className="text-gray-500 py-8 text-center">No sessions yet.</div>
      ) : (
        <div className="space-y-2">
          {data.sessions.map((s) => {
            const isFailed = s.run_status === 'failed' || s.tag?.startsWith('failed:')
            const isExpanded = expandedId === s.id
            return (
              <div key={s.id} className={`border rounded-lg overflow-hidden ${isFailed ? 'bg-red-950/10 border-red-800/50' : 'bg-gray-900 border-gray-800'}`}>
                <button
                  onClick={() => setExpandedId(isExpanded ? null : s.id)}
                  className="w-full text-left p-4 flex items-center gap-3 hover:bg-gray-800/30 transition-colors"
                >
                  {isFailed ? (
                    <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                  ) : s.tag?.startsWith('checkpoint:') ? (
                    <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
                  ) : (
                    <div className="w-5 h-5 rounded-full bg-gray-700 flex-shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`font-mono text-sm ${isFailed ? 'text-red-300' : 'text-cyan-400'}`}>
                        {s.tag || 'session'}
                      </span>
                      {isFailed && (
                        <span className="text-[10px] bg-red-900/40 text-red-300 px-1.5 py-0.5 rounded">failed</span>
                      )}
                    </div>
                    {s.summary && (
                      <div className="text-sm text-gray-400 mt-0.5 truncate max-w-lg">
                        {s.summary.slice(0, 200)}
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 flex-shrink-0">
                    {s.created_at ? new Date(s.created_at).toLocaleString() : ''}
                  </div>
                  {isExpanded ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
                </button>
                {isExpanded && isFailed && (
                  <div className="px-4 pb-4 pt-1 border-t border-red-900/30 space-y-1.5">
                    <div className="text-xs text-gray-500">Run ID: <code className="text-gray-400">{s.run_id || '—'}</code></div>
                    <div className="text-xs text-gray-500">Full error: {s.summary}</div>
                    <Link
                      to={`/project/${projectId}/build-plan`}
                      className="inline-flex items-center gap-1.5 text-xs text-amber-400 hover:text-amber-300 border border-amber-800 rounded px-2.5 py-1 mt-1"
                    >
                      View in Build Plan
                    </Link>
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
