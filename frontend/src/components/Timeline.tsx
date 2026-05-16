import { useState } from 'react'

function Timeline() {
  const [currentTime, setCurrentTime] = useState(new Date())

  const handleTimeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTime = new Date(e.target.value)
    setCurrentTime(newTime)
  }

  return (
    <div className="timeline">
      <h2>Timeline</h2>
      <div className="timeline-controls">
        <label htmlFor="time-slider">Time:</label>
        <input
          id="time-slider"
          type="datetime-local"
          value={currentTime.toISOString().slice(0, 16)}
          onChange={handleTimeChange}
        />
      </div>
      <div className="timeline-info">
        <p>Current: {currentTime.toLocaleString()}</p>
        <p>View: Historical (-24 hours)</p>
      </div>
    </div>
  )
}

export default Timeline