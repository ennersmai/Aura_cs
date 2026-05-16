import { create } from 'zustand'

export interface AircraftEntity {
  icao_hex: string
  callsign: string
  lat: number
  lon: number
  altitude: number
  velocity: number
  heading: number
  last_seen: string
}

export interface EventEntity {
  id: string
  title: string
  description: string
  lat: number
  lon: number
  timestamp: string
  source: string
}

export interface EntityData {
  id: string
  type: 'aircraft' | 'event'
  aircraft?: AircraftEntity
  event?: EventEntity
  visible: boolean
  addedAt: number
}

interface GlobeState {
  activeLayers: string[]
  selectedEntity: string | null
  cameraPosition: { lat: number; lon: number; height: number }
  entities: Map<string, EntityData>

  // Layer management
  toggleLayer: (layerId: string) => void

  // Entity management
  addAircraftEntity: (id: string, data: AircraftEntity) => void
  addEventEntity: (id: string, data: EventEntity) => void
  setSelectedEntity: (entityId: string | null) => void
  setCameraPosition: (position: { lat: number; lon: number; height: number }) => void

  // Accessors for rendering
  getVisibleAircraft: () => EntityData[]
  getVisibleEvents: () => EntityData[]
}

export const useGlobeStore = create<GlobeState>((set, get) => ({
  activeLayers: ['ADS-B_Military'],
  selectedEntity: null,
  cameraPosition: { lat: 44.0, lon: 31.0, height: 20000000 },
  entities: new Map<string, EntityData>(),

  toggleLayer: (layerId: string) => {
    set((state) => ({
      activeLayers: state.activeLayers.includes(layerId)
        ? state.activeLayers.filter((id) => id !== layerId)
        : [...state.activeLayers, layerId],
    }))
  },

  addAircraftEntity: (id: string, data: AircraftEntity) => {
    set((state) => {
      const newEntities = new Map(state.entities)
      const existing = newEntities.get(id)
      newEntities.set(id, {
        id,
        type: 'aircraft',
        aircraft: { ...existing?.aircraft, ...data },
        visible: state.activeLayers.includes('ADS-B_Military'),
        addedAt: existing?.addedAt || Date.now(),
      })
      return { entities: newEntities }
    })
  },

  addEventEntity: (id: string, data: EventEntity) => {
    set((state) => {
      const newEntities = new Map(state.entities)
      const existing = newEntities.get(id)
      newEntities.set(id, {
        id,
        type: 'event',
        event: { ...existing?.event, ...data },
        visible: state.activeLayers.includes('X_Scraper_Alerts'),
        addedAt: existing?.addedAt || Date.now(),
      })
      return { entities: newEntities }
    })
  },

  setSelectedEntity: (entityId) => set({ selectedEntity: entityId }),
  setCameraPosition: (position) => set({ cameraPosition: position }),

  getVisibleAircraft: () => {
    const state = get()
    return Array.from(state.entities.values()).filter(
      (e) => e.type === 'aircraft' && e.visible,
    )
  },

  getVisibleEvents: () => {
    const state = get()
    return Array.from(state.entities.values()).filter(
      (e) => e.type === 'event' && e.visible,
    )
  },
}))