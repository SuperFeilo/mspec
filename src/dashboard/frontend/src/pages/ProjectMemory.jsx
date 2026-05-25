import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'

async function fetchMemory(projectId) {
  const res = await fetch(`/api/projects/${projectId}/memory`)
  if (!res.ok) throw new Error('Failed to fetch memory')
  return res.json()
}

export default function ProjectMemory() {
  const { projectId } = useParams()
  const { data, isLoading } = useQuery({
    queryKey: ['memory', projectId],
    queryFn: () => fetchMemory(projectId),
  })

  const memory = data?.memory

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Link to={`/project/${projectId}`} className="text-gray-400 hover:text-gray-200">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold">Memory</h1>
      </div>

      {isLoading ? (
        <div className="text-gray-400">Loading...</div>
      ) : !memory ? (
        <div className="text-gray-500 py-8 text-center">No memory data.</div>
      ) : (
        <div className="space-y-4">
          {/* Decisions */}
          {memory.decisions?.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold mb-2">Decisions ({memory.decisions.length})</h2>
              <div className="space-y-2">
                {memory.decisions.map((d) => (
                  <div key={d.id} className="bg-gray-900 border border-gray-800 rounded-lg p-3">
                    <div className="text-sm font-medium text-cyan-300">{d.decision}</div>
                    {d.context && <div className="text-xs text-gray-400 mt-1">Context: {d.context}</div>}
                    {d.rationale && <div className="text-xs text-gray-500 mt-1">{d.rationale}</div>}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Tasks */}
          {memory.tasks?.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold mb-2">Tasks ({memory.tasks.length})</h2>
              <div className="space-y-1">
                {memory.tasks.map((t) => (
                  <div key={t.id} className="bg-gray-900 border border-gray-800 rounded px-3 py-2 flex items-center justify-between text-sm">
                    <div>
                      <span className="font-mono text-xs text-gray-500">{t.id}</span>
                      <span className="ml-2">{t.description}</span>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      t.status === 'done' ? 'bg-green-900/50 text-green-300' :
                      t.status === 'blocked' ? 'bg-red-900/50 text-red-300' :
                      'bg-gray-700 text-gray-400'
                    }`}>
                      {t.status}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Tech stack */}
          {memory.tech_stack && Object.keys(memory.tech_stack).length > 0 && (
            <section>
              <h2 className="text-lg font-semibold mb-2">Tech Stack</h2>
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
                {Object.entries(memory.tech_stack).map(([k, v]) => (
                  <div key={k} className="text-sm flex gap-2">
                    <span className="text-gray-400 capitalize">{k}:</span>
                    <span>{v}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Raw JSON */}
          <details className="bg-gray-900 border border-gray-800 rounded-lg p-3">
            <summary className="text-sm text-gray-400 cursor-pointer hover:text-gray-200">Raw JSON</summary>
            <pre className="mt-2 text-xs text-gray-500 overflow-x-auto max-h-96">
              {JSON.stringify(memory, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  )
}
