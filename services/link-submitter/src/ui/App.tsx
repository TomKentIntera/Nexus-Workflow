import React, { useMemo, useState } from 'react'

type LinkSubmissionResponse = {
  id: string
  url: string
  source_url: string | null
  created_at: string
  webhook_status: string
  webhook_attempts: number
  webhook_last_error: string | null
}

function normalizeUrl(input: string): string {
  const raw = input.trim()
  if (!raw) return ''
  // If user pastes "example.com", treat as https.
  if (!/^https?:\/\//i.test(raw) && raw.includes('.')) return `https://${raw}`
  return raw
}

async function submitLink(url: string, sourceUrl: string): Promise<LinkSubmissionResponse> {
  const payload: Record<string, string> = { url }
  const source = sourceUrl.trim()
  if (source) payload.source_url = source

  const resp = await fetch('/api/links', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  })

  const text = await resp.text()
  if (!resp.ok) {
    // FastAPI default error is JSON; keep it readable if parsing fails.
    try {
      const parsed = JSON.parse(text) as { detail?: unknown }
      throw new Error(typeof parsed.detail === 'string' ? parsed.detail : text)
    } catch {
      throw new Error(text || `Request failed (${resp.status})`)
    }
  }
  return JSON.parse(text) as LinkSubmissionResponse
}

export function App() {
  const [url, setUrl] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<LinkSubmissionResponse | null>(null)

  const normalizedUrl = useMemo(() => normalizeUrl(url), [url])
  const normalizedSourceUrl = useMemo(() => normalizeUrl(sourceUrl), [sourceUrl])

  const canSubmit = normalizedUrl.length > 0 && !busy

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const res = await submitLink(normalizedUrl, normalizedSourceUrl)
      setResult(res)
      // Keep source (often reused); clear main URL for fast next submit.
      setUrl('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="wrap">
      <div className="card">
        <div className="header">
          <h1 className="title">Link Submitter</h1>
          <p className="hint">Sends URL to API, triggers n8n webhook</p>
        </div>

        <form onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="url">URL (required)</label>
            <input
              id="url"
              type="url"
              inputMode="url"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              placeholder="https://…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="source">Source URL (optional)</label>
            <input
              id="source"
              type="url"
              inputMode="url"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              placeholder="https://…"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
            />
          </div>

          <div className="actions">
            <button className="primary" type="submit" disabled={!canSubmit}>
              {busy ? 'Submitting…' : 'Submit'}
            </button>
          </div>
        </form>

        {error ? (
          <div className="status bad" role="alert">
            <strong>Submit failed.</strong>
            <div style={{ height: 8 }} />
            <div>{error}</div>
          </div>
        ) : null}

        {result ? (
          <div className={`status ${result.webhook_status === 'sent' ? 'ok' : 'bad'}`}>
            <strong>
              {result.webhook_status === 'sent'
                ? 'Submitted + webhook sent.'
                : 'Submitted, but webhook delivery failed.'}
            </strong>
            <div style={{ height: 10 }} />
            <dl className="kv">
              <dt>ID</dt>
              <dd>{result.id}</dd>
              <dt>Webhook</dt>
              <dd>
                {result.webhook_status} (attempts: {result.webhook_attempts})
              </dd>
              {result.webhook_last_error ? (
                <>
                  <dt>Error</dt>
                  <dd>{result.webhook_last_error}</dd>
                </>
              ) : null}
            </dl>
          </div>
        ) : null}

        <p className="hint" style={{ marginTop: 14 }}>
          Tip: if you paste “example.com/path”, it will auto-prefix https://
        </p>
      </div>
    </div>
  )
}

