import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw, Check, Eye, EyeOff, Globe, Server } from 'lucide-react'

async function fetchConfig() {
  const res = await fetch('/api/config')
  if (!res.ok) throw new Error('Failed to fetch config')
  return res.json()
}

async function fetchLmsStatus() {
  const res = await fetch('/api/lms/status')
  if (!res.ok) throw new Error('Failed to fetch LM Studio status')
  return res.json()
}

async function fetchProviderConfig() {
  const res = await fetch('/api/config/provider')
  if (!res.ok) throw new Error('Failed to fetch provider config')
  return res.json()
}

export default function Settings() {
  const { data: config, isLoading: configLoading } = useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
  })

  const { data: lmsStatus } = useQuery({
    queryKey: ['lms-status'],
    queryFn: fetchLmsStatus,
  })

  const { data: providerConfig, refetch: refetchProvider } = useQuery({
    queryKey: ['provider-config'],
    queryFn: fetchProviderConfig,
  })

  const [provider, setProvider] = useState('localllm')
  const [localUrl, setLocalUrl] = useState('')
  const [localModel, setLocalModel] = useState('')
  const [deepseekKey, setDeepseekKey] = useState('')
  const [deepseekModel, setDeepseekModel] = useState('deepseek-chat')
  const [showKey, setShowKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState({ type: '', text: '' })

  // Populate form when provider config loads
  useEffect(() => {
    if (providerConfig) {
      setProvider(providerConfig.provider || 'localllm')
      setLocalUrl(providerConfig.localllm?.base_url || 'http://127.0.0.1:1234/v1')
      setLocalModel(providerConfig.localllm?.model || '')
      setDeepseekKey(providerConfig.deepseek?.api_key || '')
      setDeepseekModel(providerConfig.deepseek?.model || 'deepseek-chat')
    }
  }, [providerConfig])

  async function handleSaveProvider(e) {
    e.preventDefault()
    setSaving(true)
    setSaveMsg({ type: '', text: '' })

    try {
      const payload = {
        provider,
        localllm: {
          base_url: localUrl,
          model: localModel,
        },
        deepseek: {
          api_key: deepseekKey,
          model: deepseekModel,
        },
      }

      const res = await fetch('/api/config/provider', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to save')
      }

      setSaveMsg({ type: 'success', text: 'LLM provider configuration saved' })
      refetchProvider()
    } catch (err) {
      setSaveMsg({ type: 'error', text: `Error: ${err.message}` })
    } finally {
      setSaving(false)
    }
  }

  if (configLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <RefreshCw className="w-6 h-6 animate-spin text-cyan-400" />
      </div>
    )
  }

  const deepseekModels = ['deepseek-chat', 'deepseek-reasoner']

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* ── LLM Provider ───────────────────────────────────── */}
      <section className="bg-gray-900 border border-gray-800 rounded-lg p-5 space-y-4">
        <h2 className="text-lg font-semibold">LLM Provider</h2>
        <p className="text-xs text-gray-500">
          Select which LLM engine powers agentic coding. Changes apply to new agent runs.
        </p>

        <form onSubmit={handleSaveProvider} className="space-y-4">
          {/* Provider selector */}
          <div className="flex gap-2">
            {[
              { id: 'localllm', label: 'Local (LM Studio)', icon: Server },
              { id: 'deepseek', label: 'DeepSeek API', icon: Globe },
            ].map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setProvider(opt.id)}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors flex-1 ${
                  provider === opt.id
                    ? 'bg-cyan-900/40 text-cyan-300 border border-cyan-700'
                    : 'bg-gray-800 text-gray-400 border border-gray-700 hover:border-gray-600'
                }`}
              >
                <opt.icon className="w-4 h-4" />
                {opt.label}
              </button>
            ))}
          </div>

          {/* LM Studio config */}
          {provider === 'localllm' && (
            <div className="space-y-3 bg-gray-950/50 rounded-lg p-4 border border-gray-800">
              <label className="block">
                <span className="text-sm text-gray-400">Base URL</span>
                <input
                  type="text"
                  value={localUrl}
                  onChange={(e) => setLocalUrl(e.target.value)}
                  className="w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-600 font-mono"
                  placeholder="http://127.0.0.1:1234/v1"
                />
              </label>
              <label className="block">
                <span className="text-sm text-gray-400">Model (optional)</span>
                <input
                  type="text"
                  value={localModel}
                  onChange={(e) => setLocalModel(e.target.value)}
                  className="w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-600 font-mono"
                  placeholder="e.g. qwen3.6-27b"
                />
              </label>

              {/* LM Studio status */}
              <div className="border-t border-gray-800 pt-3 mt-3">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${lmsStatus?.connected ? 'bg-green-400' : 'bg-red-400'}`} />
                  <span className="text-sm text-gray-400">
                    {lmsStatus?.connected ? 'Connected' : 'Not connected'}
                  </span>
                </div>
                {lmsStatus?.models?.length > 0 && (
                  <div className="mt-2">
                    <div className="text-xs text-gray-500 mb-1">Available models:</div>
                    <div className="flex flex-wrap gap-1">
                      {lmsStatus.models.map((m) => (
                        <button
                          key={m}
                          type="button"
                          onClick={() => setLocalModel(m)}
                          className={`text-xs px-2 py-0.5 rounded font-mono transition-colors ${
                            localModel === m
                              ? 'bg-cyan-900/50 text-cyan-300 border border-cyan-700'
                              : 'bg-gray-800 text-gray-300 hover:bg-gray-700 border border-gray-700'
                          }`}
                        >
                          {m}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* DeepSeek config */}
          {provider === 'deepseek' && (
            <div className="space-y-3 bg-gray-950/50 rounded-lg p-4 border border-gray-800">
              <label className="block">
                <span className="text-sm text-gray-400">API Key</span>
                <div className="flex gap-2 mt-1">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={deepseekKey}
                    onChange={(e) => setDeepseekKey(e.target.value)}
                    className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-600 font-mono"
                    placeholder="sk-..."
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-gray-400 hover:text-gray-200"
                  >
                    {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </label>
              <label className="block">
                <span className="text-sm text-gray-400">Model</span>
                <select
                  value={deepseekModel}
                  onChange={(e) => setDeepseekModel(e.target.value)}
                  className="w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-600"
                >
                  {deepseekModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </label>
            </div>
          )}

          {/* Save */}
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={saving}
              className="bg-cyan-700 hover:bg-cyan-600 disabled:bg-gray-700 text-white px-5 py-2 rounded text-sm font-medium transition-colors flex items-center gap-2"
            >
              {saving ? (
                <><RefreshCw className="w-4 h-4 animate-spin" /> Saving...</>
              ) : (
                <><Check className="w-4 h-4" /> Save Provider</>
              )}
            </button>
            {saveMsg.text && (
              <span className={`text-sm ${saveMsg.type === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                {saveMsg.text}
              </span>
            )}
          </div>
        </form>
      </section>

      {/* Agent Configuration */}
      {config?.agents && (
        <section className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
          <h2 className="text-lg font-semibold">Agent Configuration</h2>
          <div className="space-y-2">
            {Object.entries(config.agents).map(([name, cfg]) => (
              <div key={name} className="flex items-center justify-between bg-gray-800/50 rounded px-3 py-2">
                <div>
                  <div className="text-sm font-medium capitalize">{name}</div>
                  <div className="text-xs text-gray-500">
                    {cfg.direct ? 'Direct' : 'opencode'} · {cfg.context_length} ctx
                  </div>
                </div>
                <div className="text-sm font-mono text-cyan-400">{cfg.model}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* General Config */}
      {config && (
        <section className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
          <h2 className="text-lg font-semibold">General</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-gray-400">Projects Directory:</span>
              <div className="font-mono text-xs mt-0.5">{config.projects_dir}</div>
            </div>
            <div>
              <span className="text-gray-400">Dashboard Port:</span>
              <div className="mt-0.5">{config.dashboard_port}</div>
            </div>
            <div>
              <span className="text-gray-400">Max Retries:</span>
              <div className="mt-0.5">{config.max_retries}</div>
            </div>
            <div>
              <span className="text-gray-400">Poll Interval:</span>
              <div className="mt-0.5">{config.poll_interval}s</div>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
