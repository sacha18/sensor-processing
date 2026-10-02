import { useState, useEffect } from 'react';
import { useAlertDialog } from '../../hooks/useAlertDialog';
import { useConfirmDialog } from '../../hooks/useConfirmDialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Save, Plus, Trash2, Edit, ChevronDown, ChevronRight } from 'lucide-react';

interface MetadataTableEditorProps {
  sessionId: string;
  tableName: string;
  pipelineType?: string;
  refreshTrigger?: number;
}

interface ColumnGroup {
  name: string;
  columns: string[];
}

const COLUMN_LABELS: Record<string, string> = {
  sensor_id: 'Sensor ID',
  group_key: 'Group',
  site: 'Site',
  treatment: 'Treatment',
  position: 'Position',
  position_depth: 'Position (depth)',
  row: 'Row',
  transect: 'Transect',
  depth_cm: 'Depth (cm)',
  t1_label: 'T1 label',
  t2_label: 'T2 label',
  t3_label: 'T3 label',
  install_start: 'Install start',
  install_end: 'Install end',
  notes: 'Notes',
};

export function MetadataTableEditor({
  sessionId,
  tableName,
  pipelineType = 'tms',
  refreshTrigger = 0
}: MetadataTableEditorProps) {
  const [data, setData] = useState<any[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const [editingCell, setEditingCell] = useState<{row: number, col: string} | null>(null);
  const { showAlert } = useAlertDialog();
  const { confirm } = useConfirmDialog();

  const columnGroups: ColumnGroup[] = [
    { name: 'Basic Info', columns: ['sensor_id', 'site', 'treatment'] },
    { name: 'Location', columns: ['position', 'row', 'transect', 'depth_cm'] },
    { name: 'Channel Labels', columns: ['t1_label', 't2_label', 't3_label'] },
    { name: 'Install Period', columns: ['install_start', 'install_end'] },
    { name: 'Other', columns: ['group_key', 'notes'] },
  ];

  useEffect(() => {
    loadData();
  }, [sessionId, tableName, pipelineType, refreshTrigger]);

  const loadData = async () => {
    setLoading(true);
    try {
      const response = await fetch(
        `http://localhost:8000/api/sessions/${sessionId}/metadata/${tableName}?pipeline_type=${pipelineType}`
      );

      if (!response.ok) {
        throw new Error('Failed to load metadata');
      }

      const result = await response.json();
      setColumns(result.columns);
      setData(result.data);
    } catch (error) {
      console.error('Failed to load metadata:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetch(
        `http://localhost:8000/api/sessions/${sessionId}/metadata/${tableName}?pipeline_type=${pipelineType}`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(data),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to save metadata');
      }

      showAlert({
        variant: 'success',
        message: 'Metadata saved successfully',
      });
    } catch (error) {
      console.error('Failed to save metadata:', error);
      showAlert({
        variant: 'error',
        message: 'Failed to save metadata',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleCellChange = (rowIndex: number, column: string, value: any) => {
    const newData = [...data];
    newData[rowIndex] = {...newData[rowIndex], [column]: value};
    setData(newData);
  };

  const handleAddRow = () => {
    const newRow: Record<string, any> = {};
    columns.forEach(col => {
      newRow[col] = '';
    });
    setData([...data, newRow]);
    // Auto-expand new row
    setExpandedRows(new Set([...expandedRows, data.length]));
  };

  const handleDeleteRow = async (index: number) => {
    const confirmed = await confirm({
      title: 'Delete Row',
      message: 'Delete this row?',
      confirmText: 'Delete',
      variant: 'destructive',
    });

    if (confirmed) {
      const newData = data.filter((_, i) => i !== index);
      setData(newData);
    }
  };

  const toggleRowExpand = (index: number) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedRows(newExpanded);
  };

  if (loading) {
    return <div>Loading...</div>;
  }

  // Compact view columns (always visible)
  const compactColumns = ['sensor_id', 'site', 'treatment', 'position'];
  // All editable columns
  const allColumns = columns.filter(col => col !== 'position_depth');

  const renderInput = (rowIndex: number, col: string, value: any) => {
    const isDateCol = col.includes('start') || col.includes('end');
    const isNumberCol = col.includes('_cm');

    if (col === 'notes') {
      return (
        <textarea
          value={value || ''}
          onChange={(e) => handleCellChange(rowIndex, col, e.target.value)}
          className="w-full px-2 py-1 border rounded text-xs"
          placeholder={COLUMN_LABELS[col] || col}
          rows={2}
        />
      );
    }

    return (
      <input
        type={isNumberCol ? 'number' : isDateCol ? 'datetime-local' : 'text'}
        value={value || ''}
        onChange={(e) => handleCellChange(rowIndex, col, e.target.value)}
        className="w-full px-2 py-1 border rounded text-xs"
        placeholder={COLUMN_LABELS[col] || col}
      />
    );
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Metadata Table</CardTitle>
            <CardDescription>
              Edit metadata directly. Click expand to see all fields. Click Save when done.
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button onClick={handleAddRow} size="sm" variant="outline">
              <Plus className="h-4 w-4 mr-2" />
              Add Row
            </Button>
            <Button onClick={handleSave} size="sm" disabled={saving}>
              <Save className="h-4 w-4 mr-2" />
              {saving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground border rounded">
            No data. Click "Add Row" to start.
          </div>
        ) : (
          <div className="space-y-2">
            {data.map((row, rowIndex) => {
              const isExpanded = expandedRows.has(rowIndex);

              return (
                <div key={rowIndex} className="border rounded">
                  {/* Compact row - always visible */}
                  <div className="flex items-center gap-2 p-3 hover:bg-muted/50">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleRowExpand(rowIndex)}
                      className="h-8 w-8 p-0 flex-shrink-0"
                    >
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </Button>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 flex-1 min-w-0">
                      {compactColumns.map(col => (
                        columns.includes(col) && (
                          <div key={col} className="min-w-0">
                            <label className="text-xs font-medium text-muted-foreground block mb-1">
                              {COLUMN_LABELS[col] || col}
                            </label>
                            {renderInput(rowIndex, col, row[col])}
                          </div>
                        )
                      ))}
                    </div>

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteRow(rowIndex)}
                      className="h-8 w-8 p-0 flex-shrink-0"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>

                  {/* Expanded fields - grouped by category */}
                  {isExpanded && (
                    <div className="p-4 pt-0 space-y-4 border-t bg-muted/20">
                      {columnGroups.map(group => {
                        const groupCols = group.columns.filter(col =>
                          columns.includes(col) && !compactColumns.includes(col)
                        );

                        if (groupCols.length === 0) return null;

                        return (
                          <div key={group.name}>
                            <h4 className="text-xs font-semibold mb-2 text-muted-foreground">
                              {group.name}
                            </h4>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                              {groupCols.map(col => (
                                <div key={col}>
                                  <label className="text-xs font-medium block mb-1">
                                    {COLUMN_LABELS[col] || col}
                                  </label>
                                  {renderInput(rowIndex, col, row[col])}
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {data.length > 0 && (
          <div className="mt-4 text-sm text-muted-foreground">
            {data.length} row(s) • Click chevron to expand and edit all fields
          </div>
        )}
      </CardContent>
    </Card>
  );
}
