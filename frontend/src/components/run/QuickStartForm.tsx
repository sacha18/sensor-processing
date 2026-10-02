import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreateSession } from '../../api/hooks';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Upload, X, Play, FileText } from 'lucide-react';
import { toast } from 'sonner';

// Quick Start only supports the TMS pipeline for now.
const pipelineType = 'tms';

export function QuickStartForm() {
  const navigate = useNavigate();
  const [files, setFiles] = useState<File[]>([]);
  const [userEmail, setUserEmail] = useState('');
  const [isDragging, setIsDragging] = useState(false);

  const createSession = useCreateSession();

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

    if (files.length === 0) {
      toast.error('Please upload at least one file');
      return;
    }

    try {
      const result = await createSession.mutateAsync({
        files,
        pipelineType,
        user: userEmail || 'anonymous'
      });

      // Show success toast
      toast.success('Session created successfully!', {
        description: `Redirecting to wizard...`,
        duration: 2000,
      });

      // Navigate directly to the wizard
      navigate(`/sessions/${result.session_id}/wizard`);
    } catch (error) {
      console.error('Failed to create session:', error);
      toast.error('Failed to create session', {
        description: error instanceof Error ? error.message : 'Check console for details.',
        duration: 5000,
      });
    }
  };

  const expectedFiles = 'TOMST CSV files (.csv) and/or Excel metadata file (.xlsx)';

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Pipeline Type - a plain select once more than one pipeline exists to choose from;
          for now TMS is the only one, so this just states that rather than offering a choice. */}
      <Card>
        <CardHeader>
          <CardTitle>1. Pipeline Type</CardTitle>
          <CardDescription>Currently only the TMS pipeline is available</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="p-4 border-2 border-primary rounded-lg bg-primary/5">
            <div className="font-semibold mb-1">TMS Data</div>
            <div className="text-sm text-muted-foreground">
              TOMST TMS sensor data with calibration & correction
            </div>
          </div>
        </CardContent>
      </Card>

      {/* File Upload */}
      <Card>
        <CardHeader>
          <CardTitle>2. Upload Files</CardTitle>
          <CardDescription>Drag & drop files or click to browse</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="p-3 bg-muted rounded-md text-sm">
            <p className="font-medium mb-1">Expected files:</p>
            <p className="text-muted-foreground">{expectedFiles}</p>
          </div>

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
              Drag & drop files here, or click to select
            </p>
            <p className="text-xs text-muted-foreground mb-4">
              Supports: .csv, .TMS, .xlsx
            </p>
            <Input
              type="file"
              multiple
              onChange={handleFileInput}
              accept=".csv,.TMS,.xlsx"
              className="max-w-xs mx-auto"
            />
          </div>

          {/* File List */}
          {files.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Uploaded files ({files.length}):</p>
              <div className="space-y-1">
                {files.map((file, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-2 bg-muted rounded"
                  >
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">{file.name}</span>
                      <Badge variant="outline" className="text-xs">
                        {(file.size / 1024).toFixed(1)} KB
                      </Badge>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeFile(index)}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* User Info */}
      <Card>
        <CardHeader>
          <CardTitle>3. User Information</CardTitle>
          <CardDescription>Optional: for tracking who ran this pipeline</CardDescription>
        </CardHeader>
        <CardContent>
          <Input
            type="email"
            placeholder="your.email@example.com"
            value={userEmail}
            onChange={(e) => setUserEmail(e.target.value)}
          />
        </CardContent>
      </Card>

      {/* Submit */}
      <div className="flex justify-end gap-4">
        <Button
          type="button"
          variant="outline"
          onClick={() => setFiles([])}
          disabled={files.length === 0}
        >
          Clear Files
        </Button>
        <Button
          type="submit"
          disabled={files.length === 0 || createSession.isPending}
        >
          <Play className="h-4 w-4 mr-2" />
          {createSession.isPending ? 'Creating Session...' : 'Start Pipeline'}
        </Button>
      </div>
    </form>
  );
}
