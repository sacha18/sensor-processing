interface SensorSelectorProps {
  sensors: string[];
  selectedSensor: string;
  onSensorChange: (sensor: string) => void;
  getSensorLabel?: (sensor: string) => string;
}

export function SensorSelector({
  sensors,
  selectedSensor,
  onSensorChange,
  getSensorLabel,
}: SensorSelectorProps) {
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="sensor-select" className="text-sm font-medium">
        Sensor:
      </label>
      <select
        id="sensor-select"
        value={selectedSensor}
        onChange={(e) => onSensorChange(e.target.value)}
        className="px-3 py-2 border border-input bg-background rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {sensors.map((sensor) => (
          <option key={sensor} value={sensor}>
            {getSensorLabel ? getSensorLabel(sensor) : sensor}
          </option>
        ))}
      </select>
    </div>
  );
}
