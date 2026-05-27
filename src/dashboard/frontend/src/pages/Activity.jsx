import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ActivityIcon, RefreshCw, Play, CheckCircle, XCircle, Loader } from 'lucide-react'

async function fetchActivity() {
  const res = await fetch('/api/activity')
  if (!res.ok) throw new Error('Failed')
  return res.json()
}

export default function Activity() {
  const { data, isLoading } = useQuery({
    queryKey: ['activity'],
    queryFn: fetchActivity,
    refetchInterval: 5000,
  })

  if (isLoading) {
    return <div className="flex items-center justify-center py-20"><RefreshCw className="w-6 h-6 animate-spin text-cyan-400" /></div>
  }

  const cr = data?.coding_runs || {}

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Activity</h1>

      {/* Project Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-3xl font-bold text-cyan-400">{data?.total_projects || 0}</div>
          <div className="text-sm text-gray-400">Projects</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-3xl font-bold text-green-400">{data?.total_sessions || 0}</div>
          <div className="text-sm text-gray-400">Sessions</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-3xl font-bold text-yellow-400">{data?.running_projects || 0}</div>
          <div className="text-sm text-gray-400">Running</div>
        </div>
      </div>

      {/* Coding Runs Stats */}
      {cr.total > 0 && (
        <div className="grid grid-cols-4 gap-3">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-3 text-center">
            <div className="text-lg font-bold text-gray-200">{cr.total}</div>
            <div className="text-[10px] text-gray-500">Total Runs</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-3 text-center">
            <div className="text-lg font-bold text-blue-400 flex items-center justify-center gap-1">
              {cr.running > 0 && <Loader className="w-3.5 h-3.5 animate-spin" />}
              {cr.running}
            </div>
            <div className="text-[10px] text-gray-500">Running</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-3 text-center">
            <div className="text-lg font-bold text-green-400">{cr.completed}</div>
            <div className="text-[10px] text-gray-500">Completed</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-3 text-center">
            <div className="text-lg font-bold text-red-400">{cr.failed}</div>
            <div className="text-[10px] text-gray-500">Failed</div>
          </div>
        </div>
      )}

      {/* Projects with runs */}
      {data?.projects?.length > 0 ? (
        <div>
          <h2 className="text-lg font-semibold mb-3">All Projects</h2>
          <div className="space-y-2">
            {data.projects.map((p) => {
              const pRuns = data?.project_runs?.[p.id] || []
              return (
                <Link
                  key={p.id}
                  to={`/project/${p.id}`}
                  className="bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-cyan-800 transition-colors flex items-center justify-between"
                >
                  <div className="flex-1">
                    <div className="font-medium">{p.name}</div>
                    <div className="text-xs text-gray-500 mt-0.5 flex items-center gap-2">
                      <span>{p.session_count} sessions</span>
                      {pRuns.length > 0 && (
                        <>
                          <span>·</span>
                          <span>{pRuns.length} coding runs</span>
                          <span>·</span>
                          <span className={pRuns.some(r => r.status === 'running') ? 'text-blue-400' : ''}>
                            {pRuns.filter(r => r.status === 'running').length} active
                          </span>
                        </>
                      )}
                    </div>
                    {/* Show latest run */}
                    {pRuns.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {pRuns.slice(0, 3).map((run) => (
                          <span key={run.id} className={`text-[10px] px-1.5 py-0.5 rounded ${
                            run.status === 'running' ? 'bg-blue-900/40 text-blue-300' :
                            run.status === 'completed' ? 'bg-green-900/40 text-green-300' :
                            run.status === 'failed' ? 'bg-red-900/40 text-red-300' :
                            'bg-gray-800 text-gray-400'
                          }`}>
                            {run.stub_name?.slice(0, 12)}: {run.status}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded ml-3 ${
                    p.status === 'running' ? 'bg-green-900/50 text-green-300 animate-pulse' : 'bg-gray-700 text-gray-400'
                  }`}>{p.status}</span>
                </Link>
              )
            })}
          </div>
        </div>
      ) : (
        <div className="text-center py-16 text-gray-500">
          <ActivityIcon className="w-12 h-12 mx-auto mb-3 opacity-40" />
          <p>No activity yet.</p>
          <Link to="/new" className="text-cyan-400 hover:underline text-sm mt-2 inline-block">Create your first project →</Link>
        </div>
      )}
    </div>
  )
}
