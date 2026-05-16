interface LayerPanelProps {
  activeLayers: string[]
  onLayerToggle: (layer: string) => void
}

const LAYERS = [
  { id: 'ADS-B_Military', name: 'ADS-B Military', description: 'Real-time military aircraft telemetry' },
  { id: 'X_Scraper_Alerts', name: 'X/Twitter Alerts', description: 'Social media OSINT events' },
  { id: 'Geopolitical_Events', name: 'Geopolitical Events', description: 'Historical and current events' },
  { id: 'Air_Traffic', name: 'Air Traffic', description: 'Commercial and private aircraft' },
]

function LayerPanel({ activeLayers, onLayerToggle }: LayerPanelProps) {
  return (
    <div className="layer-panel">
      <h2>Data Layers</h2>
      <div className="layer-list">
        {LAYERS.map((layer) => (
          <div
            key={layer.id}
            className={`layer-item ${activeLayers.includes(layer.id) ? 'active' : ''}`}
            onClick={() => onLayerToggle(layer.id)}
          >
            <div className="layer-header">
              <span className="layer-name">{layer.name}</span>
              <span className="layer-status">
                {activeLayers.includes(layer.id) ? '● Active' : '○ Inactive'}
              </span>
            </div>
            <p className="layer-description">{layer.description}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default LayerPanel