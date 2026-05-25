import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, GitCommit, GitBranch, Tags } from 'lucide-react'

async function fetchGit(projectId) {
  const res = await fetch(`/api/projects/${projectId}/git`)
  if (!res.ok) throw new Error('Failed to fetch git data')
  return res.json()
}

export default function ProjectGit() {
  const { projectId } = useParams()
  const { data, isLoading } = useQuery({
    queryKey: ['git', projectId],
    queryFn: () => fetchGit(projectId),
  })

  if (isLoading) return <div className="text-gray-400 py-10">Loading...</div>
  if (!data) return <div className="text-gray-500 py-8 text-center">No git data.</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to={`/project/${projectId}`} className="text-gray-400 hover:text-gray-200">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold">Git</h1>
      </div>

      {/* Branch */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="flex items-center gap-2 text-cyan-400 mb-1">
          <GitBranch className="w-4 h-4" />
          <span className="text-sm font-medium">Branch</span>
        </div>
        <div className="text-lg font-mono">{data.branch || 'none'}</div>
      </div>

      {/* Tags */}
      {data.tags?.length > 0 && (
        <div>
          <div className="flex items-center gap-2 text-amber-400 mb-2">
            <Tags className="w-4 h-4" />
            <span className="text-sm font-medium">Tags ({data.tags.length})</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {data.tags.map((t) => (
              <span key={t} className="bg-amber-900/30 text-amber-300 text-xs px-2 py-1 rounded font-mono">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Commits */}
      {data.commits?.length > 0 && (
        <div>
          <div className="flex items-center gap-2 text-green-400 mb-2">
            <GitCommit className="w-4 h-4" />
            <span className="text-sm font-medium">Recent Commits</span>
          </div>
          <div className="space-y-1">
            {data.commits.map((c) => (
              <div key={c.hash} className="bg-gray-900 border border-gray-800 rounded px-3 py-2 flex items-center gap-3 text-sm">
                <span className="font-mono text-xs text-gray-500">{c.hash}</span>
                <span className="flex-1">{c.message}</span>
                <span className="text-xs text-gray-500">{c.date}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Diff summary */}
      {data.diff_summary && (
        <div>
          <h2 className="text-sm font-medium text-gray-400 mb-2">Uncommitted Diff</h2>
          <pre className="bg-gray-900 border border-gray-800 rounded-lg p-3 text-xs text-gray-400 overflow-x-auto">
            {data.diff_summary}
          </pre>
        </div>
      )}
    </div>
  )
}
