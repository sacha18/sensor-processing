import { useState } from 'react';
import { useAlertDialog } from '../../hooks/useAlertDialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Upload, FileUp, CheckCircle, AlertCircle, AlertTriangle } from 'lucide-react';

interface MetadataUploaderProps {
  sessionId: string;
  tableName: string;
  pipelineType?: string;
  onImportComplete?: () => void;
}

const SCHEMA_COLUMNS: Record<string, string[]> = {
  metadata: [
    'sensor_id', 'group_key', 'site', 'treatment', 'position', 'position_depth',
    'row', 'transect', 'depth_cm', 't1_label', 't2_label', 't3_label',
    'install_start', 'install_end', 'notes'
  ],
};

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

function guessSensorColumn(columns: string[]): number {
  const normalize = (s: string) => s.toLowerCase().replace(/[\s_]+/g, '_');
  const normalized = columns.map(c => normalize(c));

  for (const target of ['sensor_id', 'sensor', 'id']) {
    const idx = normalized.indexOf(target);
    if (idx >= 0) return idx;
  }
  return 0;
}

export function MetadataUploader({
  sessionId,
  tableName,
  pipelineType = 'tms',
  onImportComplete
}: MetadataUploaderProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [sensorColumn, setSensorColumn] = useState<string>('');
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [skipRows, setSkipRows] = useState(0);
  const { showAlert } = useAlertDialog();

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    setFile(selectedFile);
    setPreview(null);
    setImportResult(null);
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('skiprows', String(skipRows));

      const response = await fetch(
        `http://localhost:8000/api/sessions/${sessionId}/metadata/${tableName}/upload?pipeline_type=${pipelineType}`,
        {
          method: 'POST',
          body: formData,
        }
      );

      if (!response.ok) {
        throw new Error('Failed to upload file');
      }

      const data = await response.json();
      setPreview(data);

      // Auto-guess sensor column
      const sensorColIdx = guessSensorColumn(data.columns);
      setSensorColumn(data.columns[sensorColIdx]);

      // Auto-guess column mapping with better fuzzy matching
      const guessed: Record<string, string> = {};
      const normalize = (s: string) => s.toLowerCase().replace(/[\s_\-()[\]]+/g, '_').replace(/_+/g, '_');
      const normalizedFileCols = data.columns.map((c: string) => normalize(c));

      SCHEMA_COLUMNS[tableName].forEach(schemaCol => {
        if (schemaCol === 'sensor_id') return; // Skip, handled separately

        const normalized = normalize(schemaCol);
        // Try exact match first
        let idx = normalizedFileCols.indexOf(normalized);

        // Try partial matches
        if (idx === -1) {
          idx = normalizedFileCols.findIndex(col =>
            col.includes(normalized) || normalized.includes(col)
          );
        }

        if (idx >= 0) {
          guessed[schemaCol] = data.columns[idx];
        }
      });

      setColumnMapping(guessed);
    } catch (error) {
      console.error('Upload failed:', error);
      showAlert({
        variant: 'error',
        message: 'Failed to upload file',
      });
    } finally {
      setUploading(false);
    }
  };

  const handleImport = async () => {
    if (!file || !sensorColumn) return;

    setImporting(true);
    setImportResult(null);

    try {
      // Build full mapping including sensor_id
      const fullMapping = {
        sensor_id: sensorColumn,
        ...columnMapping
      };

      const formData = new FormData();
      formData.append('file', file);
      formData.append('column_mapping', JSON.stringify(fullMapping));
      formData.append('skiprows', String(skipRows));

      const response = await fetch(
        `http://localhost:8000/api/sessions/${sessionId}/metadata/${tableName}/import?pipeline_type=${pipelineType}`,
        {
          method: 'POST',
          body: formData,
        }
      );

      if (!response.ok) {
        throw new Error('Failed to import file');
      }

      const data = await response.json();
      setImportResult(data);

      // Clear state
      setFile(null);
      setPreview(null);
      setSensorColumn('');

      // Notify parent
      if (onImportComplete) {
        onImportComplete();
      }
    } catch (error) {
      console.error('Import failed:', error);
      showAlert({
        variant: 'error',
        message: 'Failed to import file',
      });
    } finally {
      setImporting(false);
    }
  };

  const schemaColumns = SCHEMA_COLUMNS[tableName] || [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload Metadata File</CardTitle>
        <CardDescription>
          Upload CSV/JSON/XLSX with sensor deployment info: site, treatment, position, depth, install dates, and channel labels for non-standard installations. Sensors already loaded are pre-filled below. Upload to add more, then edit directly. The metadata table is what the pipeline uses.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* File Upload */}
        <div className="flex items-center gap-4">
          <input
            type="file"
            accept=".csv,.json,.xlsx"
            onChange={handleFileSelect}
            className="hidden"
            id="metadata-file-upload"
          />
          <label htmlFor="metadata-file-upload" className="cursor-pointer">
            <div className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2">
              <FileUp className="h-4 w-4 mr-2" />
              {file ? file.name : 'Choose File'}
            </div>
          </label>

          {(file?.name.endsWith('.csv') || file?.name.endsWith('.xlsx')) && (
            <div className="flex items-center gap-2">
              <label className="text-sm">Header Row:</label>
              <input
                type="number"
                min="1"
                value={skipRows + 1}
                onChange={(e) => setSkipRows(Math.max(0, parseInt(e.target.value) - 1))}
                className="w-20 px-2 py-1 border rounded text-sm"
              />
            </div>
          )}
        </div>

        {/* Preview & Column Mapping */}
        {preview && (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Found {preview.total_rows} rows with {preview.columns.length} columns
            </div>

            {/* File Preview */}
            <div>
              <h4 className="text-sm font-medium mb-2">File Preview (first 10 rows)</h4>
              <div className="overflow-x-auto border rounded">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      {preview.columns.map((col: string) => (
                        <th key={col} className="p-2 text-left font-medium">{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.preview.map((row: any, idx: number) => (
                      <tr key={idx} className="border-b">
                        {preview.columns.map((col: string) => (
                          <td key={col} className="p-2">{row[col]}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Sensor ID Column Selector */}
            <div>
              <h4 className="text-sm font-medium mb-2">Sensor ID Column</h4>
              <p className="text-xs text-muted-foreground mb-2">
                Which column contains the sensor serial number (used to match sensors already loaded)?
              </p>
              <select
                value={sensorColumn}
                onChange={(e) => setSensorColumn(e.target.value)}
                className="px-3 py-2 border rounded text-sm w-full md:w-64"
              >
                {preview.columns.map((col: string) => (
                  <option key={col} value={col}>{col}</option>
                ))}
              </select>
            </div>

            {/* Column Mapping */}
            <div>
              <h4 className="text-sm font-medium mb-2">Column Mapping</h4>
              <p className="text-xs text-muted-foreground mb-3">
                Map the file's columns to metadata fields. Only needed where headers don't already match. Leave "Don't import" to skip a field.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {schemaColumns.filter(c => c !== 'sensor_id').map(schemaCol => (
                  <div key={schemaCol} className="flex flex-col gap-1">
                    <label className="text-xs font-medium">
                      {COLUMN_LABELS[schemaCol] || schemaCol}
                    </label>
                    <select
                      value={columnMapping[schemaCol] || ''}
                      onChange={(e) => setColumnMapping({...columnMapping, [schemaCol]: e.target.value})}
                      className="px-2 py-1 border rounded text-sm"
                    >
                      <option value="">Don't import</option>
                      {preview.columns.map((col: string) => (
                        <option key={col} value={col}>{col}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>

            <Button onClick={handleImport} disabled={importing || !sensorColumn}>
              <Upload className="h-4 w-4 mr-2" />
              {importing ? 'Importing...' : 'Import Data'}
            </Button>
          </div>
        )}

        {/* Import Result */}
        {importResult && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 p-3 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-md">
              <CheckCircle className="h-5 w-5 text-green-600" />
              <div className="text-sm text-green-900 dark:text-green-100">
                <p className="font-medium">
                  Updated {importResult.rows_updated} existing row(s) and added {importResult.rows_added} new row(s).
                </p>
                <p className="text-xs mt-1">
                  Total: {importResult.total_rows} row(s) in metadata table
                </p>
              </div>
            </div>
            {importResult.rows_skipped > 0 && (
              <div className="flex items-center gap-2 p-3 bg-yellow-50 dark:bg-yellow-950 border border-yellow-200 dark:border-yellow-800 rounded-md">
                <AlertTriangle className="h-5 w-5 text-yellow-600" />
                <span className="text-sm text-yellow-900 dark:text-yellow-100">
                  Skipped {importResult.rows_skipped} row(s) whose sensor ID doesn't match any loaded sensor.
                </span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
