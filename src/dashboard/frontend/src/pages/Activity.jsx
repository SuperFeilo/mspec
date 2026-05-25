import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ActivityIcon, RefreshCw, FolderKanban } from 'lucide-react'

async function fetchActivity() {
  const res = await fetch('/api/activity')
  if (!res.ok) throw new Error('Failed to fetch activity')
  return res.json()
}

export default function Activity() {
  const { data, isLoading } = useQuery({
    queryKey: ['activity'],
    queryFn: fetchActivity,
    refetchInterval: 10000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <RefreshCw className="w-6 h-6 animate-spin text-cyan-400" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Activity</h1>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-3xl font-bold text-cyan-400">{data?.total_projects || 0}</div>
          <div className="text-sm text-gray-400">Total Projects</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-3xl font-bold text-green-400">{data?.total_sessions || 0}</div>
          <div className="text-sm text-gray-400">Total Sessions</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="text-3xl font-bold text-yellow-400">{data?.running_projects || 0}</div>
          <div className="text-sm text-gray-400">Running</div>
        </div>
      </div>

      {data?.projects?.length > 0 ? (
        <div>
          <h2 className="text-lg font-semibold mb-3">All Projects</h2>
          <div className="space-y-2">
            {data.projects.map((p) => (
              <Link
                key={p.id}
                to={`/project/${p.id}`}
                className="bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-cyan-800 transition-colors flex items-center justify-between"
              >
                <div>
                  <div className="font-medium">{p.name}</div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {p.session_count} sessions · {p.current_phase || 'no phase'}
                  </div>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded ${
                  p.status === 'running' ? 'bg-green-900/50 text-green-300 animate-pulse' :
                  'bg-gray-700 text-gray-400'
                }`}>
                  {p.status}
                </span>
              </Link>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-center py-16 text-gray-500">
          <ActivityIcon className="w-12 h-12 mx-auto mb-3 opacity-40" />
          <p>No activity yet.</p>
          <Link to="/new" className="text-cyan-400 hover:underline text-sm mt-2 inline-block">
            Create your first project →
          </Link>
        </div>
      )}
    </div>
  )
}
