import { useState, useEffect } from 'react';
import { History, RotateCcw } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import type { ManualQCEdit } from './ManualQCEditor';

interface ManualQCHistoryProps {
  sessionId: string;
  onEditsChange?: () => void;
  onRevert?: () => void; // Callback when revert is clicked
}

const CHANNEL_LABELS: Record<string, string> = {
  vwc: 'Moisture (VWC)',
  t1: 'T1 (temperature)',
  t2: 'T2 (temperature)',
  t3: 'T3 (temperature)',
  signal: 'Signal (raw)',
  all: 'Whole sensor (all channels)',
};

function formatEditSummary(edit: ManualQCEdit): string {
  const sensorId = edit.sensor_id;
  const channelLabel = CHANNEL_LABELS[edit.channel] || edit.channel;
  const window = `${edit.start} → ${edit.end}`;
  const reason = edit.reason ? ` - _${edit.reason}_` : '';
  const audit = `by ${edit.created_by} at ${new Date(edit.created_at).toLocaleString()}`;

  return `**${sensorId}** - ${channelLabel} - ${window}${reason}  \n_${audit}_`;
}

// Helper to get edits from localStorage
function getManualQCEdits(sessionId: string): Array<ManualQCEdit & { index: number }> {
  const key = `manual_qc_edits_${sessionId}`;
  const stored = localStorage.getItem(key);
  if (!stored) return [];
  try {
    const edits = JSON.parse(stored);
    return edits.map((edit: ManualQCEdit, index: number) => ({ ...edit, index }));
  } catch {
    return [];
  }
}

// Helper to set edits in localStorage
function setManualQCEdits(sessionId: string, edits: ManualQCEdit[]) {
  const key = `manual_qc_edits_${sessionId}`;
  localStorage.setItem(key, JSON.stringify(edits));
}

export function ManualQCHistory({
  sessionId,
  onEditsChange,
  onRevert,
}: ManualQCHistoryProps) {
  const [edits, setEditsState] = useState<Array<ManualQCEdit & { index: number }>>([]);

  // Load edits on mount
  useEffect(() => {
    setEditsState(getManualQCEdits(sessionId));
  }, [sessionId]);

  // Handle revert
  const handleRevert = async (editId: string) => {
    console.log('Reverting edit:', editId);

    // Remove from manual_qc_edits
    const allEdits = edits.filter(e => e.edit_id !== editId).map(e => ({ ...e, index: undefined }));
    setManualQCEdits(sessionId, allEdits as ManualQCEdit[]);
    setEditsState(getManualQCEdits(sessionId));

    // Remove from field_events (which is what the backend uses)
    const fieldEventsKey = `field_events_${sessionId}`;
    const stored = localStorage.getItem(fieldEventsKey);
    if (stored) {
      const fieldEvents = JSON.parse(stored);
      const updatedEvents = fieldEvents.filter((event: any) => event.edit_id !== editId);
      localStorage.setItem(fieldEventsKey, JSON.stringify(updatedEvents));
      console.log('Removed from field_events. Remaining:', updatedEvents.length);
    }

    // Notify parent that edits changed
    if (onEditsChange) {
      onEditsChange();
    }

    // Trigger auto-recompute
    if (onRevert) {
      console.log('Triggering auto-recompute after revert');
      onRevert();
    }
  };

  // Group edits by edit_id (multiple channels from one box-select)
  const editGroups = edits.reduce((acc, edit) => {
    if (!acc[edit.edit_id]) {
      acc[edit.edit_id] = [];
    }
    acc[edit.edit_id].push(edit);
    return acc;
  }, {} as Record<string, Array<ManualQCEdit & { index: number }>>);

  const groupIds = Object.keys(editGroups).sort((a, b) => {
    const timeA = new Date(editGroups[a][0].created_at).getTime();
    const timeB = new Date(editGroups[b][0].created_at).getTime();
    return timeB - timeA; // Most recent first
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <History className="h-5 w-5" />
          <CardTitle>Manual QC Edit History</CardTitle>
        </div>
        <CardDescription>
          All manual quality control overrides with audit tracking
        </CardDescription>
      </CardHeader>
      <CardContent>
        {edits.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No manual QC edits yet - use the editor above to mark intervals as invalid.
          </p>
        ) : (
          <div className="space-y-4">
            <p className="text-sm font-medium">{edits.length} edit(s) across {groupIds.length} operation(s)</p>
            {groupIds.map((editId) => {
              const group = editGroups[editId];
              const firstEdit = group[0];
              const channels = group.map(e => CHANNEL_LABELS[e.channel] || e.channel).join(', ');

              return (
                <div key={editId} className="border rounded-lg p-3 space-y-2">
                  <div className="flex items-start gap-2">
                    <div className="flex-1">
                      <div className="text-sm font-medium">
                        {firstEdit.sensor_id} - {firstEdit.start} → {firstEdit.end}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        Channels: {channels}
                      </div>
                      {firstEdit.reason && (
                        <div className="text-xs text-muted-foreground mt-1">
                          Reason: <em>{firstEdit.reason}</em>
                        </div>
                      )}
                      <div className="text-xs text-muted-foreground mt-1">
                        by {firstEdit.created_by} at {new Date(firstEdit.created_at).toLocaleString()}
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRevert(editId)}
                      title="Revert this edit"
                    >
                      <RotateCcw className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
