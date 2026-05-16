import { useEffect, useState } from 'react'
import { useGlobeStore, EntityData } from '../stores/globeStore'

interface EntityCardProps {
  entityId: string | null
  onClose: () => void
}

function EntityCard({ entityId, onClose }: EntityCardProps) {
  const [entity, setEntity] = useState<EntityData | null>(null)
  const entities = useGlobeStore((s) => s.entities)

  useEffect(() => {
    if (entityId && entities.has(entityId)) {
      setEntity(entities.get(entityId) || null)
    } else {
      setEntity(null)
    }
  }, [entityId, entities])

  // Listen for Escape key
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  if (!entity || !entityId) return null

  const { aircraft, event, type } = entity

  return (
    <div className="entity-card">
      <div className="entity-card-header">
        <h2>
          {type === 'aircraft' && (aircraft?.callsign || aircraft?.icao_hex || 'Aircraft')}
          {type === 'event' && (event?.title || 'Event')}
        </h2>
        <button className="entity-card-close" onClick={onClose} title="Close (Esc)">
          ✕
        </button>
      </div>

      <div className="entity-card-body">
        {type === 'aircraft' && aircraft && (
          <div className="entity-details">
            <div className="entity-detail-row">
              <span className="entity-label">ICAO HEX</span>
              <span className="entity-value mono">{aircraft.icao_hex}</span>
            </div>
            <div className="entity-detail-row">
              <span className="entity-label">Callsign</span>
              <span className="entity-value">{aircraft.callsign || 'N/A'}</span>
            </div>
            <div className="entity-detail-row">
              <span className="entity-label">Position</span>
              <span className="entity-value">
                {aircraft.lat.toFixed(4)}°, {aircraft.lon.toFixed(4)}°
              </span>
            </div>
            <div className="entity-detail-row">
              <span className="entity-label">Altitude</span>
              <span className="entity-value">{aircraft.altitude.toLocaleString()} ft</span>
            </div>
            <div className="entity-detail-row">
              <span className="entity-label">Velocity</span>
              <span className="entity-value">{aircraft.velocity} kts</span>
            </div>
            <div className="entity-detail-row">
              <span className="entity-label">Heading</span>
              <span className="entity-value">{aircraft.heading}°</span>
            </div>
            <div className="entity-detail-row">
              <span className="entity-label">Last Seen</span>
              <span className="entity-value">
                {new Date(aircraft.last_seen).toLocaleTimeString()}
              </span>
            </div>
          </div>
        )}

        {type === 'event' && event && (
          <div className="entity-details">
            <div className="entity-detail-row">
              <span className="entity-label">Description</span>
              <span className="entity-value">{event.description?.substring(0, 300) || 'No description'}</span>
            </div>
            {event.lat !== 0 && event.lon !== 0 && (
              <div className="entity-detail-row">
                <span className="entity-label">Location</span>
                <span className="entity-value">
                  {event.lat.toFixed(4)}°, {event.lon.toFixed(4)}°
                </span>
              </div>
            )}
            <div className="entity-detail-row">
              <span className="entity-label">Source</span>
              <span className="entity-value">{event.source}</span>
            </div>
            <div className="entity-detail-row">
              <span className="entity-label">Timestamp</span>
              <span className="entity-value">
                {new Date(event.timestamp).toLocaleString()}
              </span>
            </div>
          </div>
        )}
      </div>

      <div className="entity-card-footer">
        <span className="entity-type-badge">
          {type === 'aircraft' ? '🛩 Aircraft' : '📡 Event'}
        </span>
        <span className="entity-id-badge mono">ID: {entityId.substring(0, 24)}</span>
      </div>
    </div>
  )
}

export default EntityCard
