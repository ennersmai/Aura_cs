import { useEffect, useRef, forwardRef, useImperativeHandle, useCallback } from 'react'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { useGlobeStore } from '../stores/globeStore'

// Handle exposed to parent component
export interface GlobeHandle {
  flyTo: (lat: number, lon: number, height?: number) => void
  trackEntity: (entityId: string) => void
}

const entityBillboards = new Map<string, Cesium.Entity>()

const Globe = forwardRef<GlobeHandle>((_props, ref) => {
  const globeRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<Cesium.Viewer | null>(null)
  const prevEntitiesRef = useRef<Set<string>>(new Set())

  // Store subscribers
  const getVisibleAircraft = useGlobeStore((s) => s.getVisibleAircraft)
  const getVisibleEvents = useGlobeStore((s) => s.getVisibleEvents)
  // Expose imperative handle
  useImperativeHandle(ref, () => ({
    flyTo: (lat: number, lon: number, height: number = 100000) => {
      viewerRef.current?.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(lon, lat, height),
        duration: 2,
      })
    },
    trackEntity: (entityId: string) => {
      const entity = entityBillboards.get(entityId)
      if (entity && viewerRef.current) {
        viewerRef.current.trackedEntity = entity
      }
    },
  }), [])

  // Initialize Cesium
  useEffect(() => {
    if (!globeRef.current) return

    // Set Cesium Ion token if available
    const ionToken = import.meta.env.VITE_CESIUM_ION_ACCESS_TOKEN
    if (ionToken) {
      Cesium.Ion.defaultAccessToken = ionToken
    }

    const viewer = new Cesium.Viewer(globeRef.current, {
      // Use default ellipsoid terrain (no network dependency)
      // World terrain can be loaded later: Cesium.createWorldTerrainAsync()
      animation: false,
      timeline: false,
      baseLayerPicker: true,
      geocoder: true,
      homeButton: true,
      sceneModePicker: true,
      navigationHelpButton: true,
      fullscreenButton: true,
      vrButton: false,
    })

    // Set default camera: Black Sea Region
    viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(31.0, 44.0, 20000000),
    })

    // Entity click handler — select entity and show detail card
    const clickHandler = viewer.screenSpaceEventHandler
    clickHandler.setInputAction((movement: { position: Cesium.Cartesian2 }) => {
      const picked = viewer.scene.pick(movement.position)
      if (Cesium.defined(picked) && picked.id) {
        const entityId = (picked.id as Cesium.Entity).id
        if (typeof entityId === 'string') {
          useGlobeStore.getState().setSelectedEntity(entityId)
        }
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK)

    // Add default imagery with labels
    viewer.scene.globe.enableLighting = false

    viewerRef.current = viewer

    return () => {
      // Clean up all billboards
      entityBillboards.forEach((entity) => {
        viewer.entities.remove(entity)
      })
      entityBillboards.clear()
      viewer.destroy()
    }
  }, [])

  // Update entities on every frame
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return

    const tick = () => {
      try {
        const aircraft = getVisibleAircraft()
        const events = getVisibleEvents()
        const currentIds = new Set<string>()

        // Render aircraft
        aircraft.forEach((entity) => {
          currentIds.add(entity.id)
          const existing = entityBillboards.get(entity.id)

          if (existing && entity.aircraft) {
            // Update position
            ; (existing as any).position = Cesium.Cartesian3.fromDegrees(
              entity.aircraft.lon,
              entity.aircraft.lat,
              entity.aircraft.altitude * 0.3048, // feet to meters
            )
          } else if (!existing && entity.aircraft) {
            // Create new aircraft entity
            const cesiumEntity = viewer.entities.add({
              id: entity.id,
              position: Cesium.Cartesian3.fromDegrees(
                entity.aircraft.lon,
                entity.aircraft.lat,
                entity.aircraft.altitude * 0.3048,
              ),
              billboard: {
                image: createAircraftIcon(),
                scale: 0.05,
                verticalOrigin: Cesium.VerticalOrigin.CENTER,
                horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
              },
              label: {
                text: entity.aircraft.callsign || entity.aircraft.icao_hex,
                font: '12px sans-serif',
                style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                outlineWidth: 2,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -20),
                showBackground: true,
                backgroundColor: new Cesium.Color(0, 0, 0, 0.7),
              },
              description: `
                <div style="font-family: sans-serif;">
                  <h3>${entity.aircraft.callsign || entity.aircraft.icao_hex}</h3>
                  <p><b>ICAO:</b> ${entity.aircraft.icao_hex}</p>
                  <p><b>Altitude:</b> ${entity.aircraft.altitude} ft</p>
                  <p><b>Velocity:</b> ${entity.aircraft.velocity} kts</p>
                  <p><b>Heading:</b> ${entity.aircraft.heading}°</p>
                </div>
              `,
            })
            entityBillboards.set(entity.id, cesiumEntity)
          }
        })

        // Render events
        events.forEach((entity) => {
          currentIds.add(entity.id)
          const existing = entityBillboards.get(entity.id)

          if (!existing && entity.event && entity.event.lat && entity.event.lon) {
            const cesiumEntity = viewer.entities.add({
              id: entity.id,
              position: Cesium.Cartesian3.fromDegrees(
                entity.event.lon,
                entity.event.lat,
              ),
              billboard: {
                image: createEventIcon(),
                scale: 0.04,
                verticalOrigin: Cesium.VerticalOrigin.CENTER,
                horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
              },
              label: {
                text: (entity.event.title || 'Event').substring(0, 30),
                font: '11px sans-serif',
                style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                outlineWidth: 2,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -18),
                showBackground: true,
                backgroundColor: new Cesium.Color(0.1, 0.1, 0.2, 0.8),
              },
              description: `
                <div style="font-family: sans-serif;">
                  <h3>${entity.event.title}</h3>
                  <p>${entity.event.description?.substring(0, 200) || ''}</p>
                  <p><b>Source:</b> ${entity.event.source}</p>
                </div>
              `,
            })
            entityBillboards.set(entity.id, cesiumEntity)
          }
        })

        // Clean up removed entities
        const prevIds = prevEntitiesRef.current
        prevIds.forEach((id) => {
          if (!currentIds.has(id)) {
            const cesiumEntity = entityBillboards.get(id)
            if (cesiumEntity) {
              viewer.entities.remove(cesiumEntity)
              entityBillboards.delete(id)
            }
          }
        })
        prevEntitiesRef.current = currentIds

      } catch {
        // Silently handle errors in render loop
      }
    }

    viewer.scene.postRender.addEventListener(tick)
    return () => {
      viewer.scene.postRender.removeEventListener(tick)
    }
  }, [getVisibleAircraft, getVisibleEvents])

  return (
    <div className="globe-container">
      <div ref={globeRef} className="globe" />
    </div>
  )
})

// Create a simple aircraft icon as data URL (small triangle pointing up)
function createAircraftIcon(): string {
  const canvas = document.createElement('canvas')
  canvas.width = 32
  canvas.height = 32
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.fillStyle = '#4ade80' // Green for military ADS-B
    ctx.beginPath()
    ctx.moveTo(16, 2)
    ctx.lineTo(28, 28)
    ctx.lineTo(4, 28)
    ctx.closePath()
    ctx.fill()
    ctx.strokeStyle = '#22c55e'
    ctx.lineWidth = 2
    ctx.stroke()
  }
  return canvas.toDataURL()
}

// Create a simple event icon as data URL (diamond)
function createEventIcon(): string {
  const canvas = document.createElement('canvas')
  canvas.width = 32
  canvas.height = 32
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.fillStyle = '#facc15' // Yellow for events
    ctx.beginPath()
    ctx.moveTo(16, 2)
    ctx.lineTo(28, 16)
    ctx.lineTo(16, 30)
    ctx.lineTo(4, 16)
    ctx.closePath()
    ctx.fill()
    ctx.strokeStyle = '#eab308'
    ctx.lineWidth = 2
    ctx.stroke()
  }
  return canvas.toDataURL()
}

export default Globe