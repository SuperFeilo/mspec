import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'

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
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Link to={`/project/${projectId}`} className="text-gray-400 hover:text-gray-200">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold">Sessions</h1>
      </div>

      {isLoading ? (
        <div className="text-gray-400">Loading...</div>
      ) : !data?.sessions?.length ? (
        <div className="text-gray-500 py-8 text-center">No sessions yet.</div>
      ) : (
        <div className="space-y-2">
          {data.sessions.map((s) => (
            <div key={s.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-mono text-sm text-cyan-400">{s.tag}</span>
                  {s.summary && (
                    <div className="text-sm text-gray-400 mt-1 truncate max-w-lg">
                      {s.summary.slice(0, 200)}
                    </div>
                  )}
                </div>
                <div className="text-xs text-gray-500">
                  {s.created_at ? new Date(s.created_at).toLocaleDateString() : ''}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
