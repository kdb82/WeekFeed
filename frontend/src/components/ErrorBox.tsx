import { errorMessage } from '../api'

export default function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="error-box" role="alert">
      <span>{errorMessage(error)}</span>
      {onRetry && (
        <button className="btn btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}
