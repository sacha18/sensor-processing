import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '../ui/dialog';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Badge } from '../ui/badge';
import { AlertCircle, CheckCircle, Settings2 } from 'lucide-react';
import { Alert, AlertDescription } from '../ui/alert';

interface ColumnMapping {
  [expectedColumn: string]: string; // expectedColumn -> actualColumn from file
}

interface ColumnMappingDialogProps {
  fileType: 'metadata' | 'corrections' | 'calibrations';
  file: File | undefined;
  onMappingChange: (mapping: ColumnMapping) => void;
}

const REQUIRED_COLUMNS: Record<string, string[]> = {
  metadata: ['sensor_id'],
  corrections: ['sensor_id', 'correction_type', 'factor_a'],
  calibrations: ['sensor_id'],
};

const OPTIONAL_COLUMNS: Record<string, string[]> = {
  metadata: [
    'group_key', 'site', 'treatment', 'position', 'position_depth',
    'row', 'transect', 'depth_cm', 't1_label', 't2_label', 't3_label',
    'install_start', 'install_end', 'notes'
  ],
  corrections: ['factor_b', 'valid_from', 'valid_to', 'notes'],
  calibrations: ['coef_0', 'coef_1', 'coef_2', 'coef_3', 'coef_4', 'coef_5', 'valid_from', 'valid_to', 'notes'],
};

export function ColumnMappingDialog({ fileType, file, onMappingChange }: ColumnMappingDialogProps) {
  const [open, setOpen] = useState(false);
  const [detectedColumns, setDetectedColumns] = useState<string[]>([]);
  const [mapping, setMapping] = useState<ColumnMapping>({});
  const [autoMapped, setAutoMapped] = useState<Set<string>>(new Set());

  const requiredColumns = REQUIRED_COLUMNS[fileType] || [];
  const optionalColumns = OPTIONAL_COLUMNS[fileType] || [];

  // Read file and detect columns using backend API
  useEffect(() => {
    if (!file) {
      setDetectedColumns([]);
      setMapping({});
      setAutoMapped(new Set());
      return;
    }

    const parseFile = async () => {
      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('skiprows', '0');

        const response = await fetch('http://localhost:8000/api/preview/parse-file', {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          throw new Error(`Failed to parse file: ${response.statusText}`);
        }

        const data = await response.json();
        const columns: string[] = data.columns;

        setDetectedColumns(columns);

        // Auto-map columns (case-insensitive, whitespace-insensitive)
        const newMapping: ColumnMapping = {};
        const mapped = new Set<string>();

        [...requiredColumns, ...optionalColumns].forEach(expectedCol => {
          const normalizedExpected = expectedCol.toLowerCase().replace(/[_\s]/g, '');

          const match = columns.find(actualCol => {
            const normalizedActual = actualCol.toLowerCase().replace(/[_\s]/g, '');
            return normalizedActual === normalizedExpected;
          });

          if (match) {
            newMapping[expectedCol] = match;
            mapped.add(expectedCol);
          }
        });

        setMapping(newMapping);
        setAutoMapped(mapped);
      } catch (err) {
        console.error('Failed to parse file for column detection:', err);
      }
    };

    parseFile();
  }, [file, fileType, requiredColumns, optionalColumns]);

  const handleMappingChange = (expectedCol: string, actualCol: string) => {
    const newMapping = { ...mapping };
    if (actualCol === '_none_') {
      delete newMapping[expectedCol];
    } else {
      newMapping[expectedCol] = actualCol;
    }
    setMapping(newMapping);
  };

  const handleApply = () => {
    onMappingChange(mapping);
    setOpen(false);
  };

  const allRequiredMapped = requiredColumns.every(col => mapping[col]);
  const mappedCount = Object.keys(mapping).length;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-2"
          disabled={!file}
        >
          <Settings2 className="h-4 w-4 mr-2" />
          Map Columns
          {mappedCount > 0 && (
            <Badge variant="secondary" className="ml-2">
              {mappedCount} mapped
            </Badge>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Column Mapping - {fileType.charAt(0).toUpperCase() + fileType.slice(1)}</DialogTitle>
          <DialogDescription>
            Map columns from your file to the expected format. Auto-detected mappings are highlighted.
          </DialogDescription>
        </DialogHeader>

        {!allRequiredMapped && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              All required columns must be mapped before you can proceed.
            </AlertDescription>
          </Alert>
        )}

        <div className="space-y-6">
          {/* Detected Columns */}
          <div>
            <Label className="text-sm font-medium">Detected Columns in File</Label>
            <div className="flex flex-wrap gap-2 mt-2">
              {detectedColumns.map(col => (
                <Badge key={col} variant="outline">
                  {col}
                </Badge>
              ))}
            </div>
          </div>

          {/* Required Columns Mapping */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Required Columns</Label>
            {requiredColumns.map(expectedCol => (
              <div key={expectedCol} className="flex items-center gap-3">
                <div className="w-40">
                  <Label className="text-sm">{expectedCol}</Label>
                  <Badge variant="destructive" className="text-xs ml-2">Required</Badge>
                </div>
                <div className="flex-1">
                  <Select
                    value={mapping[expectedCol] || '_none_'}
                    onValueChange={(value) => handleMappingChange(expectedCol, value)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select column from file" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_none_">
                        <span className="text-muted-foreground">-- None --</span>
                      </SelectItem>
                      {detectedColumns.map(col => (
                        <SelectItem key={col} value={col}>
                          {col}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {autoMapped.has(expectedCol) && (
                  <CheckCircle className="h-4 w-4 text-green-600" />
                )}
              </div>
            ))}
          </div>

          {/* Optional Columns Mapping */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Optional Columns</Label>
            {optionalColumns.map(expectedCol => (
              <div key={expectedCol} className="flex items-center gap-3">
                <div className="w-40">
                  <Label className="text-sm text-muted-foreground">{expectedCol}</Label>
                  <Badge variant="secondary" className="text-xs ml-2">Optional</Badge>
                </div>
                <div className="flex-1">
                  <Select
                    value={mapping[expectedCol] || '_none_'}
                    onValueChange={(value) => handleMappingChange(expectedCol, value)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select column from file" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_none_">
                        <span className="text-muted-foreground">-- None --</span>
                      </SelectItem>
                      {detectedColumns.map(col => (
                        <SelectItem key={col} value={col}>
                          {col}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {autoMapped.has(expectedCol) && (
                  <CheckCircle className="h-4 w-4 text-green-600" />
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button type="button" variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleApply}
            disabled={!allRequiredMapped}
          >
            Apply Mapping
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
