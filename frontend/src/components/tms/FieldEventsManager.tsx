import { useState, useEffect } from 'react';
import { Upload, PlusCircle, Trash2, CalendarX } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Alert, AlertDescription } from '../ui/alert';
import Plot from 'react-plotly.js';
import type { PlotSelectionEvent } from 'plotly.js';

export interface FieldEvent {
  sensor_id: string;
  treatment?: string | null;
  channel: string;
  start: string;
  end?: string | null;
  event_type: string;
  note?: string | null;
  // Audit fields (for manual QC edits)
  edit_id?: string | null;
  created_by?: string | null;
  created_at?: string | null;
}

interface FieldEventsManagerProps {
  sessionId: string;
  sensorOptions: string[]; // ["*", "sensor1", "sensor2"]
  channelOptions?: string[]; // ["vwc", "t1", "t2", "t3", "signal", "all"]
  eventTypeOptions?: string[]; // ["disturbance", "maintenance", "harvest", etc.]
  data?: Array<{
    timestamp: string;
    sensor_id: string;
    t1_raw?: number | null;
    t2_raw?: number | null;
    t3_raw?: number | null;
    signal_raw?: number | null;
  }>;
}

const DEFAULT_CHANNELS = ['vwc', 't1', 't2', 't3', 'signal', 'all'];
const DEFAULT_EVENT_TYPES = ['field_disturbance', 'maintenance', 'harvest', 'vegetation_cut', 'sensor_moved', 'manual_exclusion'];

// Channel labels for display
const CHANNEL_LABELS: Record<string, string> = {
  vwc: 'Moisture (VWC)',
  t1: 'T1 (temperature)',
  t2: 'T2 (temperature)',
  t3: 'T3 (temperature)',
  signal: 'Signal (raw)',
  all: 'Whole sensor (all channels)',
};

// Helper functions for localStorage
function getFieldEvents(sessionId: string): Array<FieldEvent & { index: number }> {
  const key = `field_events_${sessionId}`;
  const stored = localStorage.getItem(key);
  if (!stored) return [];
  try {
    const events = JSON.parse(stored);
    return events.map((event: FieldEvent, index: number) => ({ ...event, index }));
  } catch {
    return [];
  }
}

function setFieldEvents(sessionId: string, events: FieldEvent[]) {
  const key = `field_events_${sessionId}`;
  localStorage.setItem(key, JSON.stringify(events));
}

function formatEventSummary(event: FieldEvent): string {
  const sensorId = event.sensor_id || '*';
  const treatment = event.treatment ? ` (${event.treatment})` : '';
  const channelLabel = CHANNEL_LABELS[event.channel] || event.channel;
  const window = `${event.start || '...'} → ${event.end || 'ongoing'}`;
  const note = event.note ? ` - _${event.note}_` : '';

  // If created_by exists, it's a manual edit - show audit info
  if (event.created_by) {
    return `\`${sensorId}${treatment}\` - **${channelLabel}** - ${window}${note}  \nby ${event.created_by} at ${event.created_at}`;
  }

  return `\`${sensorId}${treatment}\` - **${channelLabel}** - ${window}${note}`;
}

export function FieldEventsManager({
  sessionId,
  sensorOptions,
  channelOptions = DEFAULT_CHANNELS,
  eventTypeOptions = DEFAULT_EVENT_TYPES,
  data,
}: FieldEventsManagerProps) {
  const [events, setEventsState] = useState<Array<FieldEvent & { index: number }>>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ success: boolean; message: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Chart selection state
  const [selectedSensor, setSelectedSensor] = useState<string>('*');
  const [selectedRange, setSelectedRange] = useState<{ start: string; end: string } | null>(null);

  // Form state
  const [formData, setFormData] = useState<FieldEvent>({
    sensor_id: '*',
    treatment: null,
    channel: 'all',
    start: '',
    end: null,
    event_type: 'field_disturbance',
    note: null,
  });

  // Load events on mount
  useEffect(() => {
    setEventsState(getFieldEvents(sessionId));
  }, [sessionId]);

  // Handle box selection on chart
  const handleSelection = (event: Readonly<PlotSelectionEvent>) => {
    if (!event || !event.range) return;

    const xRange = event.range.x;
    if (!xRange || xRange.length < 2) return;

    // Convert to ISO date strings
    const start = new Date(xRange[0]).toISOString().split('T')[0];
    const end = new Date(xRange[1]).toISOString().split('T')[0];

    setSelectedRange({ start, end });

    // Update form directly when selection changes
    setFormData(prev => ({
      ...prev,
      start: start,
      end: end,
    }));

    setError(null);
  };

  // Handle file upload
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadResult(null);

    try {
      const text = await file.text();
      let newEvents: FieldEvent[] = [];

      if (file.name.endsWith('.json')) {
        newEvents = JSON.parse(text);
      } else if (file.name.endsWith('.csv')) {
        const lines = text.split('\n').filter(l => l.trim());
        const headers = lines[0].split(',').map(h => h.trim());

        for (let i = 1; i < lines.length; i++) {
          const values = lines[i].split(',');
          const event: any = {};
          headers.forEach((header, idx) => {
            const value = values[idx]?.trim();
            if (value) {
              event[header] = value;
            }
          });
          if (event.sensor_id && event.channel && event.start) {
            newEvents.push(event as FieldEvent);
          }
        }
      }

      if (newEvents.length === 0) {
        setUploadResult({ success: false, message: 'No valid events found in file' });
      } else {
        const allEvents = [...events.map(e => ({ ...e, index: undefined })), ...newEvents];
        setFieldEvents(sessionId, allEvents as FieldEvent[]);
        setEventsState(getFieldEvents(sessionId));
        setUploadResult({ success: true, message: `Added ${newEvents.length} event(s) from ${file.name}` });
      }
    } catch (error) {
      setUploadResult({ success: false, message: `Upload failed: ${String(error)}` });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  // Handle form submit
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!formData.start) {
      setError('Start date is required');
      return;
    }

    setSubmitting(true);
    try {
      const allEvents = [...events.map(e => ({ ...e, index: undefined })), formData];
      setFieldEvents(sessionId, allEvents as FieldEvent[]);
      setEventsState(getFieldEvents(sessionId));

      // Reset form
      setFormData({
        sensor_id: '*',
        treatment: null,
        channel: 'all',
        start: '',
        end: null,
        event_type: 'field_disturbance',
        note: null,
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  };

  // Handle delete
  const handleDelete = async (index: number) => {
    const allEvents = events.filter(e => e.index !== index).map(e => ({ ...e, index: undefined }));
    setFieldEvents(sessionId, allEvents as FieldEvent[]);
    setEventsState(getFieldEvents(sessionId));
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <CalendarX className="h-5 w-5" />
          <CardTitle>Field Events</CardTitle>
        </div>
        <CardDescription>
          Known disturbance periods (harvest, maintenance, etc.) that mask QC failures
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* File upload */}
        <div>
          <Label htmlFor="field-events-upload">Upload field events CSV/JSON</Label>
          <div className="flex items-center gap-2 mt-2">
            <label
              htmlFor="field-events-upload"
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 border border-dashed rounded-lg cursor-pointer hover:border-primary hover:bg-accent transition-colors"
            >
              <Upload className="h-4 w-4" />
              <span className="text-sm">{uploading ? 'Uploading...' : 'Choose CSV or JSON file'}</span>
              <input
                id="field-events-upload"
                type="file"
                accept=".csv,.json"
                onChange={handleFileChange}
                disabled={uploading}
                className="hidden"
              />
            </label>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Columns: sensor_id, treatment, channel, start, end, event_type, note
          </p>
        </div>

        {uploadResult && (
          <Alert variant={uploadResult.success ? 'default' : 'destructive'}>
            <AlertDescription>{uploadResult.message}</AlertDescription>
          </Alert>
        )}

        {/* Interactive chart for time range selection */}
        {data && data.length > 0 && (
          <div className="space-y-3">
            <div>
              <Label htmlFor="chart-sensor">Sensor to inspect</Label>
              <Select value={selectedSensor} onValueChange={setSelectedSensor}>
                <SelectTrigger id="chart-sensor" className="mt-2">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {sensorOptions.filter(s => s !== '*').map((sensor) => (
                    <SelectItem key={sensor} value={sensor}>
                      {sensor}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>Time Series (box-select to mark event period)</Label>
              <div className="mt-2 border rounded-lg p-2">
                {(() => {
                  // Filter data for selected sensor
                  const sensorData = selectedSensor !== '*'
                    ? data.filter(d => d.sensor_id === selectedSensor)
                    : [];

                  if (sensorData.length === 0) {
                    return (
                      <p className="text-sm text-muted-foreground text-center py-8">
                        Select a specific sensor to view the chart
                      </p>
                    );
                  }

                  const timestamps = sensorData.map(d => d.timestamp);
                  const t1Values = sensorData.map(d => d.t1_raw ?? null);

                  return (
                    <Plot
                      data={[
                        {
                          type: 'scatter',
                          mode: 'lines+markers',
                          x: timestamps,
                          y: t1Values,
                          name: 'T1',
                          marker: { size: 3 },
                          line: { width: 1 },
                        },
                      ]}
                      layout={{
                        height: 300,
                        margin: { l: 50, r: 20, t: 20, b: 50 },
                        xaxis: { title: 'Timestamp' },
                        yaxis: { title: 'T1 (°C)' },
                        dragmode: 'select',
                        selectdirection: 'h',
                        hovermode: 'closest',
                      }}
                      config={{
                        displayModeBar: true,
                        modeBarButtonsToRemove: ['lasso2d'],
                        displaylogo: false,
                      }}
                      onSelected={handleSelection}
                      style={{ width: '100%' }}
                    />
                  );
                })()}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Click and drag on the chart to select a time range. The dates will auto-fill below.
              </p>
            </div>

            {selectedRange && (
              <Alert>
                <AlertDescription>
                  Selected range: <strong>{selectedRange.start}</strong> to <strong>{selectedRange.end}</strong>
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}

        {/* Add event form */}
        <form onSubmit={handleSubmit} className="space-y-4 border rounded-lg p-4">
          <h4 className="font-medium">Add a field event</h4>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="event-sensor">Sensor or group</Label>
              <Select
                value={formData.sensor_id}
                onValueChange={(value) => setFormData({ ...formData, sensor_id: value })}
              >
                <SelectTrigger id="event-sensor">
                  <SelectValue placeholder="*" />
                </SelectTrigger>
                <SelectContent>
                  {sensorOptions.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="event-treatment">Treatment</Label>
              <Input
                id="event-treatment"
                type="text"
                value={formData.treatment ?? ''}
                onChange={(e) => setFormData({ ...formData, treatment: e.target.value || null })}
                placeholder="Optional"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="event-channel">Channel</Label>
              <Select
                value={formData.channel}
                onValueChange={(value) => setFormData({ ...formData, channel: value })}
              >
                <SelectTrigger id="event-channel">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {channelOptions.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {CHANNEL_LABELS[opt] || opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="event-type">Event type</Label>
              <Select
                value={formData.event_type}
                onValueChange={(value) => setFormData({ ...formData, event_type: value })}
              >
                <SelectTrigger id="event-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {eventTypeOptions.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt.replace(/_/g, ' ')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="event-start">Start date</Label>
              <Input
                id="event-start"
                type="date"
                value={formData.start}
                onChange={(e) => setFormData({ ...formData, start: e.target.value })}
                required
              />
            </div>

            <div>
              <Label htmlFor="event-end">End date</Label>
              <Input
                id="event-end"
                type="date"
                value={formData.end ?? ''}
                onChange={(e) => setFormData({ ...formData, end: e.target.value || null })}
              />
              <p className="text-xs text-muted-foreground mt-1">Blank = ongoing</p>
            </div>
          </div>

          <div>
            <Label htmlFor="event-note">Note / Reason</Label>
            <Input
              id="event-note"
              type="text"
              value={formData.note ?? ''}
              onChange={(e) => setFormData({ ...formData, note: e.target.value || null })}
              placeholder="e.g. harvest, animal disturbance, maintenance visit"
            />
          </div>

          {error && (
            <div className="text-sm text-destructive">{error}</div>
          )}

          <Button type="submit" disabled={submitting} className="w-full">
            <PlusCircle className="h-4 w-4 mr-2" />
            {submitting ? 'Adding...' : 'Add event'}
          </Button>
        </form>

        {/* Events list */}
        <div>
          {events.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No field events yet - add one above, or upload a file.
            </p>
          ) : (
            <div className="space-y-3">
              <p className="text-sm font-medium">{events.length} event(s)</p>
              {events.map((event) => (
                <div key={event.index} className="flex items-start gap-2 p-3 border rounded-lg">
                  <div className="flex-1 text-sm">
                    <span dangerouslySetInnerHTML={{
                      __html: formatEventSummary(event)
                        .replace(/`([^`]+)`/g, '<code class="bg-muted px-1 rounded text-xs">$1</code>')
                        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                        .replace(/_([^_]+)_/g, '<em>$1</em>')
                        .replace(/\n/g, '<br/>')
                    }} />
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(event.index)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
