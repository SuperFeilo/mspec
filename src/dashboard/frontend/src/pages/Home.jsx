import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { FolderKanban, GitBranch, RefreshCw } from 'lucide-react'

async function fetchProjects() {
  const res = await fetch('/api/projects')
  if (!res.ok) throw new Error('Failed to fetch projects')
  const data = await res.json()
  return data.projects
}

async function fetchActivity() {
  const res = await fetch('/api/activity')
  if (!res.ok) throw new Error('Failed to fetch activity')
  return res.json()
}

function StatusBadge({ status }) {
  const colors = {
    idle: 'bg-gray-700 text-gray-300',
    running: 'bg-green-900/60 text-green-300 animate-pulse',
    checkpointed: 'bg-blue-900/60 text-blue-300',
    error: 'bg-red-900/60 text-red-300',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${colors[status] || 'bg-gray-700 text-gray-300'}`}>
      {status}
    </span>
  )
}

export default function Home() {
  const { data: projects, isLoading: loadingProjects } = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  })

  const { data: activity } = useQuery({
    queryKey: ['activity'],
    queryFn: fetchActivity,
  })

  if (loadingProjects) {
    return (
      <div className="flex items-center justify-center py-20">
        <RefreshCw className="w-6 h-6 animate-spin text-cyan-400" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Stats */}
      {activity && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
            <div className="text-2xl font-bold text-cyan-400">{activity.total_projects}</div>
            <div className="text-sm text-gray-400">Projects</div>
          </div>
          <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
            <div className="text-2xl font-bold text-green-400">{activity.total_sessions}</div>
            <div className="text-sm text-gray-400">Sessions</div>
          </div>
          <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
            <div className="text-2xl font-bold text-yellow-400">{activity.running_projects}</div>
            <div className="text-sm text-gray-400">Running</div>
          </div>
          <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
            <div className="text-2xl font-bold text-gray-300">{projects?.length || 0}</div>
            <div className="text-sm text-gray-400">Active</div>
          </div>
        </div>
      )}

      {/* Project list */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Projects</h2>
        <Link
          to="/new"
          className="bg-cyan-700 hover:bg-cyan-600 text-white text-sm px-4 py-2 rounded transition-colors"
        >
          + New Project
        </Link>
      </div>

      {!projects || projects.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <FolderKanban className="w-12 h-12 mx-auto mb-3 opacity-40" />
          <p>No projects yet.</p>
          <Link to="/new" className="text-cyan-400 hover:underline text-sm mt-2 inline-block">
            Create your first project →
          </Link>
        </div>
      ) : (
        <div className="grid gap-3">
          {projects.map((p) => (
            <Link
              key={p.id}
              to={`/project/${p.id}`}
              className="bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-cyan-800 transition-colors flex items-center justify-between"
            >
              <div>
                <div className="font-medium">{p.name}</div>
                <div className="text-sm text-gray-400 flex items-center gap-2 mt-1">
                  <GitBranch className="w-3 h-3" />
                  {p.git_branch}
                  {p.git_uncommitted_count > 0 && (
                    <span className="text-yellow-400 text-xs">
                      ({p.git_uncommitted_count} uncommitted)
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge status={p.status} />
                {p.current_phase && (
                  <span className="text-xs text-gray-500">{p.current_phase}</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
