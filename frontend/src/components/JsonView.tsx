import { useEffect, useRef, useState } from 'react';
import type { LookupResponse } from '../types';
import { UiIcon } from '../icons';

function JsonCode({ text }: { text: string }) {
  const parts = text.split(
    /("(?:[^"\\]|\\.)*"(?=\s*:)|"(?:[^"\\]|\\.)*"|\b(?:true|false|null)\b|\b\d+(?:\.\d+)?\b)/g,
  );
  return (
    <>
      {parts.map((part, index) => (
        <span
          key={index}
          className={
            part.startsWith('"')
              ? /^".*"$/.test(part) && text.includes(`${part}:`)
                ? 'json-key'
                : 'json-string'
              : /^(true|false|null|\d)/.test(part)
                ? 'json-literal'
                : undefined
          }
        >
          {part}
        </span>
      ))}
    </>
  );
}

export function JsonView({
  data,
  loading,
  latency,
}: {
  data: LookupResponse | null;
  loading: boolean;
  latency: number | null;
}) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const copyTimer = useRef<number | undefined>(undefined);
  useEffect(() => {
    setCopied(false);
    setCopyError(false);
    return () => window.clearTimeout(copyTimer.current);
  }, [data]);
  const text = data ? JSON.stringify(data, null, 2) : '';
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setCopyError(false);
      window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopyError(true);
    }
  }
  return (
    <section className="json-panel panel" aria-labelledby="json-title">
      <div className="json-heading">
        <div className="section-heading">
          <h2 id="json-title">API response</h2>
          <span className="status-tag neutral">JSON</span>
        </div>
        <button
          className="icon-button copy-button"
          onClick={copy}
          disabled={!data || loading}
          aria-label={copied ? 'JSON copied' : 'Copy JSON response'}
        >
          <UiIcon name={copied ? 'check' : 'copy'} />
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
      <div className="request-line">
        <span className="request-method">GET</span>
        <code>/v1/lookup/{data?.ip || '{ip_address}'}</code>
      </div>
      <div className="response-meta">
        <span>
          {data ? (
            <>
              <span className="response-dot" />
              200 OK
            </>
          ) : loading ? (
            'Request in progress'
          ) : (
            'Awaiting a lookup'
          )}
        </span>
        {latency !== null && data && (
          <span className="num">{Math.round(latency)} ms · client request</span>
        )}
      </div>
      {data ? (
        <pre
          className="json-code"
          tabIndex={0}
          aria-label={`Exact API response for ${data.ip}`}
          data-lenis-prevent
        >
          <code>
            <JsonCode text={text} />
          </code>
        </pre>
      ) : (
        <div className="json-empty">
          <UiIcon name="code" size={32} />
          <p>{loading ? 'Waiting for the response…' : 'The full response will appear here.'}</p>
          <span>Readable fields and raw evidence, side by side.</span>
        </div>
      )}
      <div className="json-foot">
        <UiIcon name="code" size={16} />
        <span>Exact response. No invented fields.</span>
        <span role="status" aria-live="polite">
          {copyError
            ? 'Copy unavailable. Select the JSON to copy it.'
            : copied
              ? 'Response copied to clipboard.'
              : ''}
        </span>
      </div>
    </section>
  );
}
