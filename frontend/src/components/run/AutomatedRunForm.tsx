import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreateAutomatedSession } from '../../api/hooks';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Upload, X, Play, Loader2, AlertCircle } from 'lucide-react';
import { ConfigSourceSelector } from './ConfigSourceSelector';
import type { ConfigSource } from './types';
import { Alert, AlertDescription } from '../ui/alert';
import { toast } from 'sonner';

// Automated runs only support the TMS pipeline - see the "Pipeline Type" card below.
const pipelineType = 'tms';

export function AutomatedRunForm() {
  const navigate = useNavigate();
  const [files, setFiles] = useState<File[]>([]);
  const [userEmail, setUserEmail] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [configSource, setConfigSource] = useState<ConfigSource>({
    type: 'dataset'
  });

  const createAutomatedSession = useCreateAutomatedSession();

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);

    const droppedFiles = Array.from(e.dataTransfer.files);
    setFiles(prev => [...prev, ...droppedFiles]);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files);
      setFiles(prev => [...prev, ...selectedFiles]);
    }
  };

  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    if (files.length === 0) {
      toast.error('Please upload at least one sensor data file');
      return;
    }

    if (configSource.type === 'dataset' && !configSource.datasetId) {
      toast.error('Please select a dataset to copy configuration from, or switch to file upload mode');
      return;
    }

    try {
      const result = await createAutomatedSession.mutateAsync({
        files,
        pipelineType,
        user: userEmail || 'anonymous',
        // Source dataset (for hybrid mode or full dataset mode)
        sourceDatasetId: configSource.type === 'dataset' ? configSource.datasetId : undefined,
        // Manual file uploads (used in upload mode OR in hybrid mode for unchecked items)
        // Backend will prioritize uploaded files over dataset config
        metadataFile: configSource.metadataFile,
        qcParamsFile: configSource.qcParamsFile,
        correctionsFile: configSource.correctionsFile,
        calibrationsFile: configSource.calibrationsFile,
        // Column mappings
        metadataMapping: configSource.metadataMapping,
        correctionsMapping: configSource.correctionsMapping,
        calibrationsMapping: configSource.calibrationsMapping,
      });

      // Show success toast
      toast.success('Automated run started successfully!', {
        description: `Session ${result.session_id} has been queued for processing. You can monitor progress in My Drafts.`,
        duration: 5000,
      });

      // Navigate to My Drafts page
      navigate('/drafts');
    } catch (error) {
      console.error('Failed to create automated session:', error);
      toast.error('Failed to create automated session', {
        description: error instanceof Error ? error.message : String(error),
        duration: 7000,
      });
    }
  };

  const expectedFiles = '.csv, .TMS, .xlsx files (TOMST sensor data)';

  const isSubmitting = createAutomatedSession.isPending;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Info Alert */}
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Automated runs will execute all pipeline stages automatically. You can monitor progress from the "My Drafts" page.
          If any stage fails, you'll be able to review and fix the issue in the wizard.
        </AlertDescription>
      </Alert>

      {/* Pipeline Type Selection - Only TMS for now */}
      <Card>
        <CardHeader>
          <CardTitle>1. Pipeline Type</CardTitle>
          <CardDescription>Currently only TMS pipeline supports automated runs</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="p-4 border-2 border-primary rounded-lg bg-primary/5">
            <div className="font-semibold mb-1">TMS Data</div>
            <div className="text-sm text-muted-foreground">
              TOMST TMS-4 soil sensor data with calibration & correction
            </div>
          </div>
        </CardContent>
      </Card>

      {/* File Upload */}
      <Card>
        <CardHeader>
          <CardTitle>2. Upload Sensor Data Files</CardTitle>
          <CardDescription>
            Drag & drop files or click to browse - {expectedFiles}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Drop Zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
              isDragging
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-primary/50'
            }`}
          >
            <Upload className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-sm font-medium mb-1">
              Drag & drop sensor data files here
            </p>
            <p className="text-xs text-muted-foreground mb-4">
              or click below to browse
            </p>
            <Input
              type="file"
              multiple
              accept=".csv,.TMS,.xlsx"
              onChange={handleFileInput}
              className="max-w-xs mx-auto"
            />
          </div>

          {/* File List */}
          {files.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">{files.length} file(s) selected:</p>
              <div className="space-y-1">
                {files.map((file, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-2 bg-muted rounded-md"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Badge variant="outline" className="shrink-0">
                        {file.name.split('.').pop()?.toUpperCase()}
                      </Badge>
                      <span className="text-sm truncate">{file.name}</span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        ({(file.size / 1024).toFixed(2)} KB)
                      </span>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => removeFile(index)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Configuration Source */}
      <div>
        <div className="mb-2">
          <h3 className="text-lg font-semibold">3. Pipeline Configuration</h3>
          <p className="text-sm text-muted-foreground">
            Choose configuration source for automated processing
          </p>
        </div>
        <ConfigSourceSelector
          pipelineType={pipelineType}
          value={configSource}
          onChange={setConfigSource}
        />
      </div>

      {/* User Information */}
      <Card>
        <CardHeader>
          <CardTitle>4. User Information</CardTitle>
          <CardDescription>Optional: enter your email for tracking</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Label htmlFor="user-email">Email</Label>
            <Input
              id="user-email"
              type="email"
              placeholder="your.email@example.com (optional)"
              value={userEmail}
              onChange={(e) => setUserEmail(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Submit Button */}
      <div className="flex justify-end gap-4">
        <Button
          type="button"
          variant="outline"
          onClick={() => navigate('/run')}
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          disabled={isSubmitting || files.length === 0}
        >
          {isSubmitting ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Starting Automated Run...
            </>
          ) : (
            <>
              <Play className="mr-2 h-4 w-4" />
              Start Automated Run
            </>
          )}
        </Button>
      </div>
    </form>
  );
}
