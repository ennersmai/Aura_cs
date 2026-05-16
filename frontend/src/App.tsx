import { useEffect, useState, useCallback, useRef } from 'react'
import Globe, { GlobeHandle } from './components/Globe'
import LayerPanel from './components/LayerPanel'
import Timeline from './components/Timeline'
import EntityCard from './components/EntityCard'
import { useGlobeStore } from './stores/globeStore'
import { useNATS, NATSMessage } from './hooks/useNATS'

function App() {
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const { activeLayers, addAircraftEntity, addEventEntity, selectedEntity, setSelectedEntity } = useGlobeStore()
  const globeRef = useRef<GlobeHandle>(null)
  const entityMapRef = useRef<Map<string, string>>(new Map()) // entity_id -> icao_hex/id

  // NATS WebSocket connection
  const { messages, connected, subscribe } = useNATS({
    url: 'ws://127.0.0.1:8080/ws',
    autoConnect: true,
  })

  // Update connection status
  useEffect(() => {
    if (connected) {
      setConnectionStatus('connected')
      // Subscribe to all active layers
      subscribe(['ADS-B_Military', 'X_Scraper_Alerts'])
    }
  }, [connected, subscribe])

  // Also check REST health
  useEffect(() => {
    const checkConnection = async () => {
      try {
        const response = await fetch('http://127.0.0.1:8080/api/health')
        if (response.ok) {
          setConnectionStatus('connected')
        } else if (!connected) {
          setConnectionStatus('disconnected')
        }
      } catch {
        if (!connected) {
          setConnectionStatus('disconnected')
        }
      }
    }

    // Check initially
    checkConnection()

    // Poll every 10 seconds as fallback
    const interval = setInterval(checkConnection, 10000)
    return () => clearInterval(interval)
  }, [connected])

  // Process incoming NATS messages
  const handleNATSMessage = useCallback((msg: NATSMessage) => {
    const { type, data } = msg

    if (type === 'adsb_telemetry') {
      // Add/update aircraft entity on the globe
      const icao = data?.hex?.toUpperCase() || data?.icao_hex?.toUpperCase()
      if (!icao) return

      const entityId = entityMapRef.current.get(icao) || `aircraft_${icao}`
      entityMapRef.current.set(icao, entityId)

      addAircraftEntity(entityId, {
        icao_hex: icao,
        callsign: data?.flight || data?.callsign || '',
        lat: parseFloat(data?.lat || 0),
        lon: parseFloat(data?.lon || 0),
        altitude: parseFloat(data?.alt_baro || 0),
        velocity: parseFloat(data?.gs || 0),
        heading: parseFloat(data?.track || 0),
        last_seen: msg.timestamp,
      })
    }

    if (type === 'x_alert') {
      // Add event entity on the globe
      const id = data?.id || `event_${Date.now()}`
      const entityId = entityMapRef.current.get(id) || `event_${id}`
      entityMapRef.current.set(id, entityId)

      addEventEntity(entityId, {
        id: data?.id || '',
        title: data?.text?.substring(0, 100) || 'X Alert',
        description: data?.text || '',
        lat: parseFloat(data?.latitude || 0),
        lon: parseFloat(data?.longitude || 0),
        timestamp: data?.created_at || msg.timestamp,
        source: 'x_twitter',
      })
    }
  }, [addAircraftEntity, addEventEntity])

  // Attach message handler
  useEffect(() => {
    if (messages.length === 0) return
    // Process the latest message
    handleNATSMessage(messages[messages.length - 1])
  }, [messages.length]) // react to message count change

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <h1>Project Panopticon</h1>
        <div className={`connection-status ${connectionStatus}`}>
          {connectionStatus === 'connected' && '● Connected'}
          {connectionStatus === 'connecting' && '● Connecting...'}
          {connectionStatus === 'disconnected' && '● Disconnected'}
        </div>
      </header>

      {/* Main Content */}
      <main className="app-main">
        <Globe ref={globeRef} />
      </main>

      {/* Entity Detail Card */}
      <EntityCard
        entityId={selectedEntity}
        onClose={() => setSelectedEntity(null)}
      />

      {/* Controls */}
      <aside className="app-controls">
        <LayerPanel
          activeLayers={activeLayers}
          onLayerToggle={(layer) => {
            useGlobeStore.getState().toggleLayer(layer)
            subscribe([layer])
          }}
        />
        <Timeline />
      </aside>
    </div>
  )
}

export default App