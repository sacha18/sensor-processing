import { useState, useEffect, useRef } from 'react';
import { useAlertDialog } from '../../hooks/useAlertDialog';
import { AlertTriangle, User } from 'lucide-react';
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

export interface ManualQCEdit {
  sensor_id: string;
  channel: string;
  start: string;
  end: string;
  reason: string;
  // Audit fields
  edit_id: string;
  created_by: string;
  created_at: string;
}

interface ManualQCEditorProps {
  sessionId: string;
  pipelineType: string;
  data: Array<{
    timestamp: string;
    sensor_id: string;
    vwc?: number | null;
    t1?: number | null;
    t2?: number | null;
    t3?: number | null;
  }>;
  sensorOptions: string[];
  channelOptions?: string[];
  onExclusionAdded?: () => void; // Callback to trigger auto-apply
}

const DEFAULT_CHANNELS = ['vwc', 't1', 't2', 't3', 'signal', 'all'];

// Channel labels for display
const CHANNEL_LABELS: Record<string, string> = {
  vwc: 'Moisture (VWC)',
  t1: 'T1 (temperature)',
  t2: 'T2 (temperature)',
  t3: 'T3 (temperature)',
  signal: 'Signal (raw)',
  all: 'Whole sensor (all channels)',
};

export function ManualQCEditor({
  sessionId,
  pipelineType,
  data,
  sensorOptions,
  channelOptions = DEFAULT_CHANNELS,
  onExclusionAdded,
}: ManualQCEditorProps) {
  const { showAlert } = useAlertDialog();
  const [selectedSensor, setSelectedSensor] = useState<string>(sensorOptions[0] || '');
  const [userName, setUserName] = useState<string>('');
  const [selectedRange, setSelectedRange] = useState<{ start: string; end: string } | null>(null);
  const [selectedChannels, setSelectedChannels] = useState<string[]>(['all']);
  const [reason, setReason] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Load username from localStorage
  useEffect(() => {
    const stored = localStorage.getItem(`manual_qc_user_${sessionId}`);
    if (stored) {
      setUserName(stored);
    }
  }, [sessionId]);

  // Save username to localStorage on change
  useEffect(() => {
    if (userName) {
      localStorage.setItem(`manual_qc_user_${sessionId}`, userName);
    }
  }, [userName, sessionId]);

  // Filter data for selected sensor
  const sensorData = data.filter(d => d.sensor_id === selectedSensor);

  // Prepare chart data
  const timestamps = sensorData.map(d => d.timestamp);
  const vwcValues = sensorData.map(d => d.vwc ?? null);

  // Handle box selection
  const handleSelection = (event: Readonly<PlotSelectionEvent>) => {
    if (!event || !event.range) return;

    const xRange = event.range.x;
    if (!xRange || xRange.length < 2) return;

    // Convert to ISO date strings
    const start = new Date(xRange[0]).toISOString().split('T')[0];
    const end = new Date(xRange[1]).toISOString().split('T')[0];

    setSelectedRange({ start, end });
    setError(null);
  };

  // Handle channel toggle
  const toggleChannel = (channel: string) => {
    if (selectedChannels.includes(channel)) {
      const newChannels = selectedChannels.filter(c => c !== channel);
      setSelectedChannels(newChannels.length > 0 ? newChannels : ['all']);
    } else {
      setSelectedChannels([...selectedChannels, channel]);
    }
  };

  // Handle submit
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!userName.trim()) {
      setError('Please enter your name/initials');
      return;
    }

    if (!selectedRange) {
      setError('Please select a time range on the chart (use box-select)');
      return;
    }

    if (!reason.trim()) {
      setError('Please provide a reason for this manual QC edit');
      return;
    }

    setSubmitting(true);
    try {
      // Save to field_events (same structure as backend expects)
      const fieldEventsKey = `field_events_${sessionId}`;
      console.log('Saving field events with key:', fieldEventsKey);
      const stored = localStorage.getItem(fieldEventsKey);
      const existingEvents = stored ? JSON.parse(stored) : [];
      console.log('Existing events:', existingEvents);

      // Create field events for each selected channel
      // "all" means whole sensor - applied to vwc in final QC and all raw channels in initial QC
      const channelsToWrite = selectedChannels.includes('all')
        ? ['all']
        : selectedChannels;

      const edit_id = `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      const now = new Date().toISOString();

      const newEvents = channelsToWrite.map(channel => ({
        sensor_id: selectedSensor,
        treatment: null,
        channel,
        start: selectedRange.start,
        end: selectedRange.end || null,
        event_type: 'manual_exclusion',
        note: reason.trim(),
        edit_id,
        created_by: userName.trim(),
        created_at: now,
      }));
      console.log('New events to add:', newEvents);

      const allEvents = [...existingEvents, ...newEvents];
      console.log('All events to save:', allEvents);
      localStorage.setItem(fieldEventsKey, JSON.stringify(allEvents));
      console.log('Saved to localStorage. Verifying:', localStorage.getItem(fieldEventsKey));

      // Also keep in separate key for history display
      const editsKey = `manual_qc_edits_${sessionId}`;
      const storedEdits = localStorage.getItem(editsKey);
      const existingEdits: ManualQCEdit[] = storedEdits ? JSON.parse(storedEdits) : [];

      const newEdits: ManualQCEdit[] = channelsToWrite.map(channel => ({
        sensor_id: selectedSensor,
        channel,
        start: selectedRange.start,
        end: selectedRange.end,
        reason: reason.trim(),
        edit_id,
        created_by: userName.trim(),
        created_at: now,
      }));

      const allEdits = [...existingEdits, ...newEdits];
      localStorage.setItem(editsKey, JSON.stringify(allEdits));

      // Reset form
      setSelectedRange(null);
      setSelectedChannels(['all']);
      setReason('');

      // Trigger auto-apply callback if provided
      if (onExclusionAdded) {
        console.log('Triggering auto-apply after exclusion');
        onExclusionAdded();
      }

      // Success notification
      showAlert({
        variant: 'success',
        message: `Marked ${selectedSensor} invalid for ${channelsToWrite.join(', ')} from ${selectedRange.start} to ${selectedRange.end || 'ongoing'}. Final QC will be recomputed automatically.`,
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5" />
          <CardTitle>Manual QC Editing</CardTitle>
        </div>
        <CardDescription>
          Use box-select on the chart to mark intervals as invalid. These edits are tracked with your name and timestamp.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* User identification */}
        <div>
          <Label htmlFor="qc-user">Your name / initials</Label>
          <div className="flex items-center gap-2 mt-2">
            <User className="h-4 w-4 text-muted-foreground" />
            <Input
              id="qc-user"
              type="text"
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              placeholder="e.g. J. Smith or JS"
              className="flex-1"
            />
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            This will be recorded with each edit for audit purposes
          </p>
        </div>

        {/* Sensor selector */}
        <div>
          <Label htmlFor="qc-sensor">Sensor to inspect</Label>
          <Select value={selectedSensor} onValueChange={setSelectedSensor}>
            <SelectTrigger id="qc-sensor">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sensorOptions.map((sensor) => (
                <SelectItem key={sensor} value={sensor}>
                  {sensor}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* VWC Chart with box-select */}
        <div>
          <Label>VWC Time Series (box-select to mark invalid)</Label>
          <div className="mt-2 border rounded-lg p-2">
            {timestamps.length > 0 ? (
              <Plot
                data={[
                  {
                    type: 'scatter',
                    mode: 'lines+markers',
                    x: timestamps,
                    y: vwcValues,
                    name: 'VWC',
                    marker: { size: 3 },
                    line: { width: 1 },
                  },
                ]}
                layout={{
                  height: 400,
                  margin: { l: 50, r: 20, t: 20, b: 50 },
                  xaxis: { title: 'Timestamp' },
                  yaxis: { title: 'VWC (m³/m³)' },
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
            ) : (
              <p className="text-sm text-muted-foreground text-center py-8">
                No data available for selected sensor
              </p>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Click and drag to select a time range. The selection will auto-fill the form below.
          </p>
        </div>

        {/* Manual edit form */}
        <form onSubmit={handleSubmit} className="space-y-4 border rounded-lg p-4">
          <h4 className="font-medium">Mark selected interval as invalid</h4>

          {selectedRange && (
            <Alert>
              <AlertDescription>
                Selected range: <strong>{selectedRange.start}</strong> to <strong>{selectedRange.end}</strong>
              </AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="qc-start">Start date</Label>
              <Input
                id="qc-start"
                type="date"
                value={selectedRange?.start || ''}
                onChange={(e) => setSelectedRange(prev => prev ? { ...prev, start: e.target.value } : { start: e.target.value, end: '' })}
                required
              />
            </div>

            <div>
              <Label htmlFor="qc-end">End date</Label>
              <Input
                id="qc-end"
                type="date"
                value={selectedRange?.end || ''}
                onChange={(e) => setSelectedRange(prev => prev ? { ...prev, end: e.target.value } : { start: '', end: e.target.value })}
                required
              />
            </div>
          </div>

          <div>
            <Label>Channels to invalidate</Label>
            <div className="flex flex-wrap gap-2 mt-2">
              {channelOptions.map((channel) => (
                <button
                  key={channel}
                  type="button"
                  onClick={() => toggleChannel(channel)}
                  className={`px-3 py-1 text-sm rounded-md border transition-colors ${
                    selectedChannels.includes(channel)
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-background hover:bg-accent border-input'
                  }`}
                >
                  {CHANNEL_LABELS[channel] || channel}
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label htmlFor="qc-reason">Reason / Note</Label>
            <Input
              id="qc-reason"
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. sensor malfunction, obvious outlier, cross-channel inconsistency"
              required
            />
          </div>

          {error && (
            <div className="text-sm text-destructive">{error}</div>
          )}

          <Button type="submit" disabled={submitting || !userName.trim()} className="w-full">
            <AlertTriangle className="h-4 w-4 mr-2" />
            {submitting ? 'Marking invalid...' : 'Mark interval as invalid'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
