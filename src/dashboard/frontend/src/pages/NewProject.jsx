import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function NewProject() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [spec, setSpec] = useState('')
  const [sourceType, setSourceType] = useState('blank')
  const [source, setSource] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)

  async function handleCreate(e) {
    e.preventDefault()
    setCreating(true)
    setError(null)

    try {
      let res
      if (sourceType === 'blank' || sourceType === 'spec') {
        res = await fetch(`/api/projects?name=${encodeURIComponent(name)}${spec ? `&spec=${encodeURIComponent(spec)}` : ''}`, {
          method: 'POST',
        })
      } else {
        res = await fetch('/api/projects/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, source_type: sourceType, source }),
        })
      }

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to create project')
      }

      const data = await res.json()
      navigate(`/project/${data.project.id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">New Project</h1>

      <div className="flex gap-2">
        {[
          { id: 'blank', label: 'Blank' },
          { id: 'spec', label: 'From Spec' },
          { id: 'git', label: 'Git Clone' },
          { id: 'local', label: 'Local Path' },
        ].map((opt) => (
          <button
            key={opt.id}
            onClick={() => setSourceType(opt.id)}
            className={`px-4 py-2 rounded text-sm transition-colors ${
              sourceType === opt.id
                ? 'bg-cyan-700 text-white'
                : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleCreate} className="space-y-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">Project Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-600"
            placeholder="my-project"
            required
          />
        </div>

        {sourceType === 'spec' && (
          <div>
            <label className="block text-sm text-gray-400 mb-1">Spec (Markdown)</label>
            <textarea
              value={spec}
              onChange={(e) => setSpec(e.target.value)}
              rows={10}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-cyan-600"
              placeholder="# Project: ..."
            />
          </div>
        )}

        {sourceType === 'git' && (
          <div>
            <label className="block text-sm text-gray-400 mb-1">Git URL</label>
            <input
              type="text"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-600"
              placeholder="https://github.com/user/repo.git"
            />
          </div>
        )}

        {sourceType === 'local' && (
          <div>
            <label className="block text-sm text-gray-400 mb-1">Local Path</label>
            <input
              type="text"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-600"
              placeholder="/path/to/existing/project"
            />
          </div>
        )}

        {error && (
          <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={creating || !name}
          className="bg-cyan-700 hover:bg-cyan-600 disabled:bg-gray-700 disabled:text-gray-500 text-white px-6 py-2 rounded transition-colors"
        >
          {creating ? 'Creating...' : 'Create Project'}
        </button>
      </form>
    </div>
  )
}
